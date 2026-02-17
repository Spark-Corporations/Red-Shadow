"""
Phi4Provider — Kaggle Phi-4 as an OpenClaw-compatible LLM provider.

Connects to:
  1. Kaggle notebook endpoint (via ngrok tunnel) — primary
  2. Local Ollama instance — fallback
  3. Any OpenAI-compatible API — generic fallback

Implements streaming, tool-calling format, token counting, and retry logic.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

import aiohttp
import requests

logger = logging.getLogger("redclaw.openclaw_bridge.phi4_provider")


@dataclass
class LLMResponse:
    """Response from the LLM provider."""
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    model: str = ""
    latency: float = 0.0


@dataclass
class ProviderConfig:
    """Configuration for an LLM provider endpoint."""
    name: str
    endpoint: str
    model: str
    api_key: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.1
    timeout: int = 120
    retry_count: int = 3


class Phi4Provider:
    """
    Kaggle Phi-4 LLM provider with fallback support.

    Priority:
      1. Kaggle endpoint (ngrok tunnel from notebook)
      2. Ollama local (if configured)
      3. Any OpenAI-compatible endpoint

    Usage:
        provider = Phi4Provider(
            kaggle_endpoint="https://xxxx.ngrok.io/v1",
            ollama_endpoint="http://localhost:11434/v1",
        )
        response = await provider.chat(messages=[
            {"role": "system", "content": "You are a pentester."},
            {"role": "user", "content": "Scan port 80."},
        ])
    """

    @staticmethod
    def _normalize_endpoint(url: str) -> str:
        """Strip trailing slashes to prevent double-slash in URL paths.

        Without this:
            'https://xxx.ngrok-free.app/' + '/v1' = '//v1' → HTTP 404
        With this:
            'https://xxx.ngrok-free.app'  + '/v1' = '/v1' → 200 OK
        """
        return url.rstrip("/")

    def __init__(
        self,
        kaggle_endpoint: str = "http://localhost:5000/v1",
        kaggle_api_key: Optional[str] = None,
        ollama_endpoint: str = "http://localhost:11434/v1",
        model: str = "phi-4",
        max_tokens: int = 4096,
        temperature: float = 0.1,
        timeout: int = 120,
        retry_count: int = 3,
    ):
        self._providers: list[ProviderConfig] = []

        # Primary: Kaggle Phi-4
        kaggle_ep = self._normalize_endpoint(kaggle_endpoint)
        self._providers.append(ProviderConfig(
            name="kaggle_phi4",
            endpoint=kaggle_ep,
            model=model,
            api_key=kaggle_api_key,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
            retry_count=retry_count,
        ))

        # Fallback: Ollama
        if ollama_endpoint:
            ollama_ep = self._normalize_endpoint(ollama_endpoint)
            self._providers.append(ProviderConfig(
                name="ollama",
                endpoint=ollama_ep,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout,
                retry_count=retry_count,
            ))

        self._active_provider: Optional[ProviderConfig] = None
        self._total_tokens_used = 0
        self._request_count = 0
        logger.info(
            f"Phi4Provider initialized: {len(self._providers)} endpoints, "
            f"primary={self._providers[0].endpoint}"
        )

    @property
    def active_provider(self) -> Optional[str]:
        return self._active_provider.name if self._active_provider else None

    async def chat(
        self,
        messages: list[dict[str, str]],
        tools: Optional[list[dict[str, Any]]] = None,
        stream: bool = False,
    ) -> LLMResponse:
        """
        Send a chat completion request to the LLM.
        Tries each provider in order until one succeeds.
        """
        last_error = None

        for provider in self._providers:
            for attempt in range(1, provider.retry_count + 1):
                try:
                    response = await self._call_provider(
                        provider, messages, tools, stream
                    )
                    self._active_provider = provider
                    self._request_count += 1
                    if response.usage:
                        self._total_tokens_used += response.usage.get("total_tokens", 0)
                    return response
                except Exception as e:
                    last_error = e
                    err_msg = str(e)[:200]
                    logger.warning(
                        f"Provider {provider.name} attempt {attempt}/{provider.retry_count} "
                        f"failed: {err_msg}"
                    )
                    if attempt < provider.retry_count:
                        await self._async_sleep(2 ** attempt)  # exponential backoff

            logger.debug(f"Provider {provider.name} exhausted all retries")

        raise RuntimeError(
            f"All LLM providers failed. Last error: {last_error}"
        )

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AsyncIterator[str]:
        """
        Stream chat completion tokens from the LLM.
        Yields individual tokens/chunks as they arrive.
        """
        provider = self._providers[0]  # use primary for streaming

        payload = {
            "model": provider.model,
            "messages": messages,
            "max_tokens": provider.max_tokens,
            "temperature": provider.temperature,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        headers = {"Content-Type": "application/json"}
        if provider.api_key:
            headers["Authorization"] = f"Bearer {provider.api_key}"

        url = f"{provider.endpoint}/chat/completions"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=provider.timeout)
                ) as resp:
                    async for line in resp.content:
                        line_str = line.decode("utf-8").strip()
                        if line_str.startswith("data: "):
                            data = line_str[6:]
                            if data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                                delta = chunk.get("choices", [{}])[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                            except json.JSONDecodeError:
                                continue
        except Exception as e:
            err_msg = str(e)[:200]
            logger.error(f"Streaming error: {err_msg}")
            yield f"\n[Streaming error: {err_msg}]"

    async def _call_provider(
        self,
        provider: ProviderConfig,
        messages: list[dict[str, str]],
        tools: Optional[list[dict[str, Any]]],
        stream: bool,
    ) -> LLMResponse:
        """Make an API call to a specific provider."""
        start = time.monotonic()

        payload = {
            "model": provider.model,
            "messages": messages,
            "max_tokens": provider.max_tokens,
            "temperature": provider.temperature,
            "stream": False,  # non-streaming for this method
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        headers = {"Content-Type": "application/json"}
        if provider.api_key:
            headers["Authorization"] = f"Bearer {provider.api_key}"

        url = f"{provider.endpoint}/chat/completions"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=provider.timeout)
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"HTTP {resp.status}: {text[:200]}")

                data = await resp.json()

        latency = time.monotonic() - start
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})

        # Parse tool calls if present
        tool_calls = []
        if "tool_calls" in message:
            for tc in message["tool_calls"]:
                tool_calls.append({
                    "id": tc.get("id", ""),
                    "name": tc.get("function", {}).get("name", ""),
                    "arguments": json.loads(tc.get("function", {}).get("arguments", "{}")),
                })

        return LLMResponse(
            content=message.get("content", ""),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", ""),
            usage=data.get("usage", {}),
            model=data.get("model", provider.model),
            latency=latency,
        )

    async def _async_sleep(self, seconds: float) -> None:
        """Async sleep for retry backoff."""
        import asyncio
        await asyncio.sleep(seconds)

    def health_check(self) -> dict[str, Any]:
        """Check if any LLM provider is reachable."""
        results = {}
        for provider in self._providers:
            url = f"{provider.endpoint}/models"
            try:
                resp = requests.get(url, timeout=5)
                results[provider.name] = {
                    "reachable": resp.status_code == 200,
                    "status_code": resp.status_code,
                }
            except Exception as e:
                results[provider.name] = {
                    "reachable": False,
                    "error": str(e),
                }
        return results

    def get_stats(self) -> dict[str, Any]:
        return {
            "active_provider": self.active_provider,
            "total_requests": self._request_count,
            "total_tokens": self._total_tokens_used,
            "providers": [p.name for p in self._providers],
        }
