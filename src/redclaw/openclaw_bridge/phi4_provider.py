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
    max_tokens: int = 8192
    temperature: float = 0.1
    timeout: int = 120
    retry_count: int = 3


class Phi4Provider:
    """
    LLM provider with fallback support for any OpenAI-compatible API.

    Supports: Gemini, OpenAI, Groq, OpenRouter, Ollama, vLLM, etc.
    Priority: primary API endpoint → Ollama fallback.

    Usage:
        provider = Phi4Provider(
            primary_endpoint="https://generativelanguage.googleapis.com/v1beta/openai",
            api_key="AIza...",
            model="gemini-2.5-flash",
        )
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
        primary_endpoint: str = "https://generativelanguage.googleapis.com/v1beta/openai",
        api_key: Optional[str] = None,
        ollama_endpoint: str = "http://localhost:11434/v1",
        model: str = "gemini-2.5-flash",
        max_tokens: int = 8192,
        temperature: float = 0.1,
        timeout: int = 120,
        retry_count: int = 3,
    ):
        self._providers: list[ProviderConfig] = []

        # Primary: API provider (Gemini, OpenAI, Groq, etc.)
        primary_ep = self._normalize_endpoint(primary_endpoint)
        self._providers.append(ProviderConfig(
            name="api_provider",
            endpoint=primary_ep,
            model=model,
            api_key=api_key,
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
        """Make an API call to a specific provider.
        
        Supports two tool-calling modes:
          1. Native API tool-calling (tools + tool_choice=auto in payload)
          2. Prompt-based fallback (tools embedded in system prompt, parse JSON output)
        
        Falls back to mode 2 if mode 1 returns HTTP 400 (vLLM without --enable-auto-tool-choice).
        """
        start = time.monotonic()

        payload = {
            "model": provider.model,
            "messages": messages,
            "max_tokens": provider.max_tokens,
            "temperature": provider.temperature,
            "stream": False,
        }

        # Try native tool-calling first
        use_native_tools = tools is not None
        if use_native_tools:
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
                if resp.status == 400:
                    error_text = await resp.text()
                    error_lower = error_text.lower()

                    # Case 1: Native tool-calling not supported → prompt-based fallback
                    if use_native_tools and ("tool" in error_lower or "auto" in error_lower):
                        logger.info(
                            "Native tool-calling not available, switching to prompt-based mode"
                        )
                        return await self._call_provider_prompt_tools(
                            provider, messages, tools, headers, url, start
                        )

                    # Case 2: max_tokens too large → retry with adaptive value
                    if "max_tokens" in error_lower or "max_completion_tokens" in error_lower:
                        # Halve max_tokens and retry
                        adaptive_max = max(provider.max_tokens // 2, 512)
                        logger.info(
                            f"max_tokens too large ({provider.max_tokens}), "
                            f"retrying with {adaptive_max}"
                        )
                        payload["max_tokens"] = adaptive_max
                        if use_native_tools:
                            # Also try without tools to reduce input size
                            return await self._call_provider_prompt_tools(
                                provider, messages, tools, headers, url, start
                            )

                    raise RuntimeError(f"HTTP 400: {error_text[:200]}")

                if resp.status == 404:
                    error_text = await resp.text()
                    error_lower = error_text.lower()

                    # OpenRouter: model doesn't support tool use → prompt-based fallback
                    if use_native_tools and ("tool use" in error_lower or "endpoints" in error_lower):
                        logger.info(
                            "Model doesn't support native tool use (HTTP 404), "
                            "switching to prompt-based mode"
                        )
                        return await self._call_provider_prompt_tools(
                            provider, messages, tools, headers, url, start
                        )

                    # OpenRouter: data policy issue → retry without tools, log hint
                    if "data policy" in error_lower:
                        logger.warning(
                            "OpenRouter data policy error — configure at "
                            "https://openrouter.ai/settings/privacy"
                        )
                        if use_native_tools:
                            return await self._call_provider_prompt_tools(
                                provider, messages, tools, headers, url, start
                            )

                    raise RuntimeError(f"HTTP 404: {error_text[:200]}")

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

    async def _call_provider_prompt_tools(
        self,
        provider: ProviderConfig,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        headers: dict[str, str],
        url: str,
        start: float,
    ) -> LLMResponse:
        """
        Prompt-based tool-calling fallback.
        
        When vLLM doesn't support native tool-calling (no --enable-auto-tool-choice),
        we embed tool schemas directly into the system prompt and instruct the model
        to output JSON tool calls, which we then parse.
        """
        import re

        # Build tool schema text for the system prompt
        tool_descriptions = []
        for tool in tools:
            func = tool.get("function", tool)
            name = func.get("name", "unknown")
            desc = func.get("description", "")
            params = func.get("parameters", {})
            props = params.get("properties", {})
            required = params.get("required", [])

            param_lines = []
            for pname, pinfo in props.items():
                req_mark = " (REQUIRED)" if pname in required else ""
                ptype = pinfo.get("type", "string")
                pdesc = pinfo.get("description", "")
                param_lines.append(f"    - {pname}: {ptype}{req_mark} — {pdesc}")

            tool_descriptions.append(
                f"  {name}: {desc}\n" + "\n".join(param_lines)
            )

        tools_text = "\n".join(tool_descriptions)

        # Inject tool instructions into system message
        tool_instruction = (
            "\n\nTo call a tool, output a JSON block: "
            '{"tool_call": {"name": "TOOL_NAME", "arguments": {"param": "value"}}}\n'
            f"Available tools:\n{tools_text}\n"
        )

        # Modify messages: append tool instruction to system message
        modified_messages = []
        system_injected = False
        for msg in messages:
            if msg.get("role") == "system" and not system_injected:
                modified_messages.append({
                    **msg,
                    "content": msg.get("content", "") + tool_instruction,
                })
                system_injected = True
            else:
                modified_messages.append(msg)

        if not system_injected:
            # No system message found — add one
            modified_messages.insert(0, {
                "role": "system",
                "content": tool_instruction,
            })

        # Send without API tools — use adaptive max_tokens
        # Dynamically cap to leave room for input tokens within context window
        # Context limit — generous for Gemini (1M context), adaptive retry handles if server caps lower
        context_limit = 131072
        safety_margin = 64
        # Start conservative: leave ~40% for output, but never exceed 1024
        adaptive_max = min(provider.max_tokens, 1024)
        payload = {
            "model": provider.model,
            "messages": modified_messages,
            "max_tokens": adaptive_max,
            "temperature": provider.temperature,
            "stream": False,
        }

        # Inner retry: if 400 due to max_tokens, parse input count and recompute
        max_retries = 2
        data = None
        for attempt in range(max_retries):
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=provider.timeout)
                ) as resp:
                    if resp.status == 400:
                        error_text = await resp.text()
                        error_lower = error_text.lower()
                        if "max_tokens" in error_lower or "max_completion_tokens" in error_lower:
                            # Parse input token count from error message
                            import re as _re
                            input_match = _re.search(r'(\d+)\s*input\s*tokens', error_text)
                            if input_match:
                                input_tokens = int(input_match.group(1))
                                new_max = context_limit - input_tokens - safety_margin
                                new_max = max(new_max, 256)  # floor
                                logger.info(
                                    f"max_tokens adaptive retry: input={input_tokens}, "
                                    f"context={context_limit}, new_max={new_max}"
                                )
                                payload["max_tokens"] = new_max
                                continue  # retry with corrected value
                            else:
                                # Can't parse — halve current value
                                new_max = max(payload["max_tokens"] // 2, 256)
                                logger.info(
                                    f"max_tokens halved: {payload['max_tokens']} → {new_max}"
                                )
                                payload["max_tokens"] = new_max
                                continue
                        raise RuntimeError(f"HTTP 400 (prompt-tools): {error_text[:200]}")
                    if resp.status != 200:
                        text = await resp.text()
                        raise RuntimeError(f"HTTP {resp.status} (prompt-tools): {text[:200]}")
                    data = await resp.json()
                    break  # success

        if data is None:
            raise RuntimeError(
                f"prompt-tools failed after {max_retries} retries: "
                f"max_tokens could not fit within context window"
            )

        latency = time.monotonic() - start
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        content = message.get("content", "")

        # Parse tool calls from model's text output
        tool_calls = []
        remaining_text = content

        # Strategy: extract all complete JSON objects from text using brace-balancing
        # This handles nested braces (e.g. {"arguments": {"target": "..."}} )
        def extract_json_objects(text: str) -> list[tuple[str, int, int]]:
            """Find all complete JSON objects in text via brace counting."""
            results = []
            i = 0
            while i < len(text):
                if text[i] == '{':
                    depth = 0
                    start = i
                    in_string = False
                    escape = False
                    for j in range(i, len(text)):
                        c = text[j]
                        if escape:
                            escape = False
                            continue
                        if c == '\\':
                            escape = True
                            continue
                        if c == '"' and not escape:
                            in_string = not in_string
                        elif not in_string:
                            if c == '{':
                                depth += 1
                            elif c == '}':
                                depth -= 1
                                if depth == 0:
                                    results.append((text[start:j+1], start, j+1))
                                    i = j + 1
                                    break
                    else:
                        i += 1  # unclosed brace, skip
                else:
                    i += 1
            return results

        # Also handle fenced code blocks: ```json ... ```
        fenced_pattern = re.compile(r'```(?:json)?\s*(\{.*?\})\s*```', re.DOTALL)
        for fm in fenced_pattern.finditer(content):
            try:
                parsed = json.loads(fm.group(1))
                tc = parsed.get("tool_call", parsed)
                name = tc.get("name", "")
                args = tc.get("arguments", tc.get("args", {}))
                if name:
                    tool_calls.append({
                        "id": f"prompt_call_{len(tool_calls)}",
                        "name": name,
                        "arguments": args if isinstance(args, dict) else {},
                    })
                    remaining_text = remaining_text.replace(fm.group(0), "").strip()
            except (json.JSONDecodeError, AttributeError):
                continue

        # Extract bare JSON objects if no fenced blocks found tool calls
        if not tool_calls:
            for json_str, start_idx, end_idx in extract_json_objects(content):
                try:
                    parsed = json.loads(json_str)
                    # Accept {"tool_call": {"name": ..., "arguments": ...}}
                    # or direct {"name": ..., "arguments": ...}
                    tc = parsed.get("tool_call", parsed)
                    name = tc.get("name", "")
                    args = tc.get("arguments", tc.get("args", {}))
                    if name and ("arguments" in tc or "args" in tc):
                        tool_calls.append({
                            "id": f"prompt_call_{len(tool_calls)}",
                            "name": name,
                            "arguments": args if isinstance(args, dict) else {},
                        })
                        remaining_text = remaining_text.replace(json_str, "").strip()
                except (json.JSONDecodeError, AttributeError):
                    continue

        # Strip hallucinated <tool_response> blocks — model sometimes fakes results
        remaining_text = re.sub(
            r'<tool_response>.*?</tool_response>',
            '', remaining_text, flags=re.DOTALL
        ).strip()
        # Also strip unclosed <tool_response> at end
        remaining_text = re.sub(
            r'<tool_response>.*$',
            '', remaining_text, flags=re.DOTALL
        ).strip()

        return LLMResponse(
            content=remaining_text,
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
