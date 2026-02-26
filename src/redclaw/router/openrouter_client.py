"""
OpenRouterClient — Dual-Brain LLM client for RedClaw V3.1

NOW delegates all API calls through LLMClient for:
  - Rate limiting (token bucket per model)
  - Automatic retries with exponential backoff + jitter
  - Provider failover (OpenRouter → Gemini → Ollama)
  - Context auto-compaction
  - Cost tracking
  - Message consistency (fix_message_list)

High-level API remains identical:
  - call_brain()   → gpt-oss-120B (strategic reasoning)
  - call_hands()   → trinity-large (code generation)
  - call_raw()     → full control
  - dual_brain()   → Brain plans → Hands codes → Brain reviews
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

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


# ── OpenRouter Client ─────────────────────────────────────────────────────────


class OpenRouterClient:
    """
    Dual-Brain LLM client using OpenRouter API.

    Delegates all calls through LLMClient for enterprise reliability.

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
        llm_client=None,
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

        # ── LLMClient integration (NEW) ──────────────────────────────────
        # If an LLMClient is provided, delegate all calls through it for
        # rate limiting, retry, failover, compaction, and cost tracking.
        # If not, fall back to direct aiohttp calls (legacy behavior).
        self._llm_client = llm_client
        self._use_llm_client = llm_client is not None

        if self._use_llm_client:
            # Register Brain and Hands as providers in the LLMClient
            from .llm_client import ProviderConfig

            if self.api_key:
                self._llm_client.add_provider(ProviderConfig(
                    model=self.BRAIN.model_id,
                    api_key=self.api_key,
                    base_url="https://openrouter.ai/api/v1",
                    priority=10,
                    rpm_limit=self.BRAIN.rate_limit_rpm,
                    description=f"OpenRouter Brain ({self.BRAIN.model_id})",
                ))
                self._llm_client.add_provider(ProviderConfig(
                    model=self.HANDS.model_id,
                    api_key=self.api_key,
                    base_url="https://openrouter.ai/api/v1",
                    priority=20,
                    rpm_limit=self.HANDS.rate_limit_rpm,
                    description=f"OpenRouter Hands ({self.HANDS.model_id})",
                ))

            logger.info("OpenRouterClient using LLMClient for reliability")
        else:
            logger.info("OpenRouterClient using legacy aiohttp (no LLMClient)")

        # Usage tracking (maintained for backward compatibility)
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

    # ── Core API Call (delegates to LLMClient when available) ─────────────

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

        If LLMClient is available, delegates through it for full reliability.
        Otherwise, falls back to direct aiohttp calls.
        """
        start_time = time.monotonic()

        if self._use_llm_client:
            return await self._call_via_llm_client(
                messages, model, tools, temperature, max_tokens
            )
        else:
            return await self._call_via_aiohttp(
                messages, model, tools, temperature, max_tokens
            )

    async def _call_via_llm_client(
        self,
        messages: list[dict[str, str]],
        model: ModelProfile,
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Delegate API call through LLMClient (with retry, failover, etc.)."""
        start_time = time.monotonic()

        try:
            result = await self._llm_client.chat(
                messages=messages,
                model=model.model_id,
                tools=tools,
                temperature=temperature if temperature is not None else model.temperature,
                max_tokens=max_tokens or model.max_tokens,
            )

            latency = time.monotonic() - start_time
            content = result.get("content", "")
            tool_calls_raw = result.get("tool_calls", [])
            usage = result.get("usage", {})

            # Parse tool calls
            tool_calls = []
            if tool_calls_raw:
                for tc in tool_calls_raw:
                    if isinstance(tc, dict):
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
                content=content,
                tool_calls=tool_calls,
                finish_reason=result.get("finish_reason", ""),
                usage=usage,
                model=result.get("model", model.model_id),
                latency=latency,
            )

        except Exception as e:
            self._stats["errors"] += 1
            raise

    async def _call_via_aiohttp(
        self,
        messages: list[dict[str, str]],
        model: ModelProfile,
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Legacy direct aiohttp call (fallback when no LLMClient)."""
        import asyncio
        import aiohttp

        if not self.api_key:
            raise ValueError("OpenRouter API key not configured")

        payload: dict[str, Any] = {
            "model": model.model_id,
            "messages": messages,
            "temperature": temperature if temperature is not None else model.temperature,
            "max_tokens": max_tokens or model.max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.app_url,
            "X-Title": self.app_name,
        }

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
                            retry_after = max(int(resp.headers.get("Retry-After", 15)), 15) + (attempt * 5)
                            logger.warning(f"Rate limited (429), waiting {retry_after}s (attempt {attempt + 1}/{self.retry_count})")
                            await asyncio.sleep(retry_after)
                            continue
                        if resp.status != 200:
                            error_text = await resp.text()
                            if resp.status >= 500:
                                await asyncio.sleep(2 ** attempt)
                                continue
                            raise RuntimeError(f"OpenRouter API error {resp.status}: {error_text[:200]}")
                        data = await resp.json()

                latency = time.monotonic() - start_time
                choice = data.get("choices", [{}])[0]
                message = choice.get("message", {})
                usage = data.get("usage", {})
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
        """Call the Brain model (gpt-oss-120B) for strategic reasoning."""
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
            messages=messages, model=self.BRAIN,
            temperature=temperature, tools=tools,
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
        """Call the Hands model for code generation."""
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
            messages=messages, model=self.HANDS,
            temperature=temperature, tools=tools,
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
        """Raw API call with full control over messages and model."""
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
        """Full dual-brain collaboration: Brain plans -> Hands codes -> Brain reviews."""
        plan = await self.call_brain(
            prompt=f"Plan the implementation strategy for: {task}",
            context=context, temperature=0.6,
        )
        code = await self.call_hands(
            task=f"Implement this plan:\n{plan}",
            context=context, temperature=0.2,
        )
        result = {"plan": plan, "code": code}
        if review:
            review_result = await self.call_brain(
                prompt=f"Review this code for correctness and security:\n{code}",
                context=f"Original plan:\n{plan}", temperature=0.4,
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
        stats = {
            **self._stats,
            "total_calls": total_calls,
            "brain_ratio": self._stats["brain_calls"] / total_calls if total_calls > 0 else 0,
            "avg_latency": self._stats["total_latency"] / total_calls if total_calls > 0 else 0,
        }

        # Merge LLMClient stats if available
        if self._use_llm_client:
            report = self._llm_client.get_health_report()
            stats["llm_client_health"] = report.get("health", {})
            stats["llm_client_cost"] = report.get("cost", {})

        return stats
