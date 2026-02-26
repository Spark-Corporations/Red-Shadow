"""
OpenRouterClient — Dual-Brain LLM client for RedClaw V3.1

Connects to OpenRouter API with two model profiles:
  - Brain (openai/gpt-oss-120b:free): Strategic reasoning, planning, analysis
  - Hands (arcee-ai/trinity-large-preview:free): Code generation, exploit scripting, automation

Features:
  - Rate limiting per model
  - Automatic retries with exponential backoff
  - Token usage tracking
  - Streaming support
  - Error classification and recovery
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Optional

import aiohttp

logger = logging.getLogger("redclaw.router.openrouter_client")


# ── Data Classes ──────────────────────────────────────────────────────────────


class TaskType(Enum):
    """Task classification for dual-brain routing."""
    REASONING = "reasoning"   # -> Brain (openai/gpt-oss-120b:free)
    CODING = "coding"         # -> Hands (arcee-ai/trinity-large-preview:free)
    BOTH = "both"             # -> Brain plans -> Hands codes


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
class ModelProfile:
    """Configuration for a specific model."""
    name: str
    model_id: str
    temperature: float
    max_tokens: int
    rate_limit_rpm: int    # requests per minute
    description: str = ""


# ── Rate Limiter ──────────────────────────────────────────────────────────────


class RateLimiter:
    """Token bucket rate limiter for API calls."""

    def __init__(self, max_requests_per_minute: int):
        self.max_rpm = max_requests_per_minute
        self.tokens = max_requests_per_minute
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        """Wait until a request slot is available."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill

            # Refill tokens based on elapsed time
            refill = elapsed * (self.max_rpm / 60.0)
            self.tokens = min(self.max_rpm, self.tokens + refill)
            self.last_refill = now

            if self.tokens < 1:
                # Wait for next available slot
                wait_time = (1 - self.tokens) / (self.max_rpm / 60.0)
                logger.debug(f"Rate limited, waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
                self.tokens = 0
            else:
                self.tokens -= 1


# ── OpenRouter Client ─────────────────────────────────────────────────────────


class OpenRouterClient:
    """
    Dual-Brain LLM client using OpenRouter API.

    Usage:
        client = OpenRouterClient(api_key="sk-or-...")

        # Strategic reasoning (Brain)
        plan = await client.call_brain("Analyze nmap results and plan attack")

        # Code generation (Hands)
        code = await client.call_hands("Write Python exploit for CVE-2021-41773")

        # Auto-route based on task type
        result = await client.route_task("Exploit Apache 2.4.49", context)
    """

    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    # Model profiles
    BRAIN = ModelProfile(
        name="Brain",
        model_id="openai/gpt-oss-120b:free",
        temperature=0.6,
        max_tokens=4096,
        rate_limit_rpm=60,
        description="Strategic reasoning, planning, analysis",
    )

    HANDS = ModelProfile(
        name="Hands",
        model_id="arcee-ai/trinity-large-preview:free",
        temperature=0.2,
        max_tokens=8192,
        rate_limit_rpm=200,
        description="Code generation, exploit scripting, automation",
    )

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 120,
        retry_count: int = 5,
        app_name: str = "RedClaw v3.1",
        app_url: str = "https://github.com/redclaw",
    ):
        # API key from param, env var, or config file
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY") or self._load_api_key()
        if not self.api_key:
            logger.warning("No OpenRouter API key configured. Set OPENROUTER_API_KEY or use ~/.redclaw/api_key.txt")

        self.base_url = base_url or self.BASE_URL
        self.timeout = timeout
        self.retry_count = retry_count
        self.app_name = app_name
        self.app_url = app_url

        # Rate limiters per model
        self._rate_limiters = {
            self.BRAIN.model_id: RateLimiter(self.BRAIN.rate_limit_rpm),
            self.HANDS.model_id: RateLimiter(self.HANDS.rate_limit_rpm),
        }

        # Usage tracking
        self._stats = {
            "brain_calls": 0,
            "hands_calls": 0,
            "brain_tokens": 0,
            "hands_tokens": 0,
            "total_latency": 0.0,
            "errors": 0,
        }

        logger.info(
            f"OpenRouterClient initialized | "
            f"Brain: {self.BRAIN.model_id} | "
            f"Hands: {self.HANDS.model_id}"
        )

    # ── API Key Loading ───────────────────────────────────────────────────

    @staticmethod
    def _load_api_key() -> Optional[str]:
        """Load API key from ~/.redclaw/api_key.txt"""
        key_path = os.path.expanduser("~/.redclaw/api_key.txt")
        if os.path.exists(key_path):
            with open(key_path, "r") as f:
                key = f.read().strip()
                if key:
                    return key
        return None

    # ── Core API Call ─────────────────────────────────────────────────────

    async def _call_api(
        self,
        messages: list[dict[str, str]],
        model: ModelProfile,
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> LLMResponse:
        """
        Make an API call to OpenRouter.

        Args:
            messages: Chat messages ([{"role": "user", "content": "..."}])
            model: Model profile (BRAIN or HANDS)
            tools: Optional tool definitions for function calling
            temperature: Override model default temperature
            max_tokens: Override model default max_tokens
            stream: Enable streaming (not yet used)

        Returns:
            LLMResponse with content, tool_calls, usage stats
        """
        if not self.api_key:
            raise ValueError("OpenRouter API key not configured")

        # Rate limiting
        limiter = self._rate_limiters.get(model.model_id)
        if limiter:
            await limiter.acquire()

        # Build payload
        payload: dict[str, Any] = {
            "model": model.model_id,
            "messages": messages,
            "temperature": temperature if temperature is not None else model.temperature,
            "max_tokens": max_tokens or model.max_tokens,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        # Headers
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.app_url,
            "X-Title": self.app_name,
        }

        # Retry loop
        last_error = None
        for attempt in range(self.retry_count):
            start_time = time.monotonic()

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        self.base_url,
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=self.timeout),
                    ) as resp:
                        if resp.status == 429:
                            # Rate limited — parse wait time from header or body
                            retry_after = 10
                            try:
                                retry_after = int(resp.headers.get("Retry-After", 0))
                            except (ValueError, TypeError):
                                pass
                            if retry_after < 1:
                                # Try to parse from response body (OpenRouter specific)
                                try:
                                    body = await resp.json()
                                    retry_ms = body.get("error", {}).get("metadata", {}).get("rateLimit", {}).get("resetRequests", "")
                                    if retry_ms:
                                        # Parse "Xs" or milliseconds
                                        import re
                                        sec_match = re.search(r"(\d+)", str(retry_ms))
                                        if sec_match:
                                            retry_after = int(sec_match.group(1))
                                except Exception:
                                    pass
                            # Minimum 15s for free-tier, with exponential backoff
                            retry_after = max(retry_after, 15) + (attempt * 5)
                            logger.warning(f"Rate limited (429), waiting {retry_after}s (attempt {attempt + 1}/{self.retry_count})")
                            await asyncio.sleep(retry_after)
                            continue

                        if resp.status != 200:
                            error_text = await resp.text()
                            logger.error(f"API error {resp.status}: {error_text[:200]}")
                            if resp.status >= 500:
                                # Server error — retry
                                await asyncio.sleep(2 ** attempt)
                                continue
                            raise RuntimeError(f"OpenRouter API error {resp.status}: {error_text[:200]}")

                        data = await resp.json()

                latency = time.monotonic() - start_time

                # Parse response
                choice = data.get("choices", [{}])[0]
                message = choice.get("message", {})
                usage = data.get("usage", {})

                # Extract tool calls if present
                tool_calls = []
                if message.get("tool_calls"):
                    for tc in message["tool_calls"]:
                        tool_calls.append({
                            "id": tc.get("id", ""),
                            "type": tc.get("type", "function"),
                            "function": {
                                "name": tc.get("function", {}).get("name", ""),
                                "arguments": tc.get("function", {}).get("arguments", "{}"),
                            },
                        })

                # Update stats
                self._update_stats(model, usage, latency)

                return LLMResponse(
                    content=message.get("content", ""),
                    tool_calls=tool_calls,
                    finish_reason=choice.get("finish_reason", ""),
                    usage=usage,
                    model=data.get("model", model.model_id),
                    latency=latency,
                )

            except asyncio.TimeoutError:
                last_error = f"Timeout after {self.timeout}s (attempt {attempt + 1})"
                logger.warning(last_error)
                await asyncio.sleep(2 ** attempt)

            except aiohttp.ClientError as e:
                last_error = f"Connection error: {e} (attempt {attempt + 1})"
                logger.warning(last_error)
                await asyncio.sleep(2 ** attempt)

        self._stats["errors"] += 1
        raise RuntimeError(f"OpenRouter API call failed after {self.retry_count} attempts: {last_error}")

    def _update_stats(self, model: ModelProfile, usage: dict, latency: float):
        """Update internal statistics."""
        if model.name == "Brain":
            self._stats["brain_calls"] += 1
            self._stats["brain_tokens"] += usage.get("total_tokens", 0)
        else:
            self._stats["hands_calls"] += 1
            self._stats["hands_tokens"] += usage.get("total_tokens", 0)
        self._stats["total_latency"] += latency

    # ── High-Level API ────────────────────────────────────────────────────

    async def call_brain(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        context: Optional[str] = None,
        temperature: Optional[float] = None,
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> str:
        """
        Call the Brain model (gpt-oss-120B) for strategic reasoning.

        Args:
            prompt: The reasoning task
            system_prompt: Override system prompt
            context: Additional context to prepend
            temperature: Override default (0.6)
            tools: Optional tool definitions

        Returns:
            Model response text
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        else:
            messages.append({
                "role": "system",
                "content": (
                    "You are an elite red team AI operator — the strategic brain of RedClaw. "
                    "You excel at analyzing situations, planning attack strategies, evaluating risks, "
                    "and making tactical decisions. Think step by step. "
                    "Provide clear, actionable strategic plans."
                ),
            })

        if context:
            prompt = f"Context:\n{context}\n\nTask:\n{prompt}"

        messages.append({"role": "user", "content": prompt})

        response = await self._call_api(
            messages=messages,
            model=self.BRAIN,
            temperature=temperature,
            tools=tools,
        )

        logger.debug(f"Brain response ({response.latency:.2f}s): {response.content[:100]}...")
        return response.content

    async def call_hands(
        self,
        task: str,
        system_prompt: Optional[str] = None,
        context: Optional[str] = None,
        temperature: Optional[float] = None,
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> str:
        """
        Call the Hands model (qwen3-coder:free) for code generation.

        Args:
            task: The coding task
            system_prompt: Override system prompt
            context: Additional context to prepend
            temperature: Override default (0.2)
            tools: Optional tool definitions

        Returns:
            Model response text (typically code)
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        else:
            messages.append({
                "role": "system",
                "content": (
                    "You are an expert security coding assistant — the hands of RedClaw. "
                    "You write precise, functional code for authorized red team operations. "
                    "Output clean, executable code with minimal comments. "
                    "Focus on correctness, efficiency, and reliability."
                ),
            })

        if context:
            task = f"Context:\n{context}\n\nTask:\n{task}"

        messages.append({"role": "user", "content": task})

        response = await self._call_api(
            messages=messages,
            model=self.HANDS,
            temperature=temperature,
            tools=tools,
        )

        logger.debug(f"Hands response ({response.latency:.2f}s): {response.content[:100]}...")
        return response.content

    async def call_raw(
        self,
        messages: list[dict[str, str]],
        model: Optional[ModelProfile] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """
        Raw API call with full control over messages and model.

        Args:
            messages: Full message list
            model: Model profile (defaults to Brain)
            tools: Optional tool definitions
            temperature: Override temperature
            max_tokens: Override max_tokens

        Returns:
            Full LLMResponse object
        """
        return await self._call_api(
            messages=messages,
            model=model or self.BRAIN,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    # ── Dual-Brain Collaboration ──────────────────────────────────────────

    async def dual_brain(
        self,
        task: str,
        context: Optional[str] = None,
        review: bool = False,
    ) -> dict[str, str]:
        """
        Full dual-brain collaboration: Brain plans -> Hands codes -> Brain reviews (optional).

        Args:
            task: The complex task requiring both reasoning and coding
            context: Additional context
            review: Whether Brain should review the code

        Returns:
            Dict with "plan", "code", and optionally "review"
        """
        # Step 1: Brain plans
        plan = await self.call_brain(
            prompt=f"Plan the implementation strategy for: {task}",
            context=context,
            temperature=0.6,
        )

        # Step 2: Hands codes
        code = await self.call_hands(
            task=f"Implement this plan:\n{plan}",
            context=context,
            temperature=0.2,
        )

        result = {"plan": plan, "code": code}

        # Step 3: Brain reviews (optional)
        if review:
            review_result = await self.call_brain(
                prompt=f"Review this code for correctness and security:\n{code}",
                context=f"Original plan:\n{plan}",
                temperature=0.4,
            )
            result["review"] = review_result

        return result

    # ── Utility Methods ───────────────────────────────────────────────────

    async def health_check(self) -> dict[str, Any]:
        """Check if OpenRouter API is reachable."""
        try:
            response = await self.call_brain("Respond with 'OK'", temperature=0.0)
            return {"healthy": True, "response": response[:50]}
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    def get_stats(self) -> dict[str, Any]:
        """Get usage statistics."""
        total_calls = self._stats["brain_calls"] + self._stats["hands_calls"]
        return {
            **self._stats,
            "total_calls": total_calls,
            "brain_ratio": (
                self._stats["brain_calls"] / total_calls if total_calls > 0 else 0
            ),
            "avg_latency": (
                self._stats["total_latency"] / total_calls if total_calls > 0 else 0
            ),
        }
