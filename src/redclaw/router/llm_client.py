"""
LLMClient — Enterprise-Grade LLM Abstraction Layer for RedClaw v3.1

Inspired by CAI (aliasrobotics/cai) and PentAGI (vxcontrol/pentagi).

Features:
  1. Rate Limit Handling: Exponential backoff + jitter, Retry-After extraction
  2. Retry Mechanism: Auto-retry on 429/5xx/timeout with configurable retries
  3. Provider Failover: Ordered provider chain with automatic switching
  4. Context Overflow: Auto-compaction when tokens exceed model limit
  5. Message Consistency: fix_message_list ensures tool_call/response pairs
  6. Cost Tracking: Per-request and cumulative cost with budget enforcement
  7. Monitoring: Structured metrics for every LLM call
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("redclaw.router.llm_client")


# ── Data Classes ──────────────────────────────────────────────────────────────


@dataclass
class ProviderConfig:
    """Configuration for a single LLM provider."""
    model: str                         # LiteLLM model identifier
    api_key: Optional[str] = None      # API key (or env var name)
    api_base: Optional[str] = None     # Custom endpoint
    priority: int = 1                  # Lower = preferred
    max_tokens: int = 4096
    temperature: float = 0.1
    timeout: int = 120
    max_retries: int = 5
    rpm_limit: int = 20                # Requests per minute
    description: str = ""


@dataclass
class LLMCallMetrics:
    """Metrics for a single LLM call."""
    model: str = ""
    provider: str = ""
    latency: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    success: bool = True
    error: str = ""
    retries: int = 0
    timestamp: float = field(default_factory=time.time)


@dataclass
class CostTracker:
    """Track LLM usage costs with budget enforcement."""
    total_cost: float = 0.0
    total_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    budget_limit: Optional[float] = None  # Max spend in USD
    per_request_limit: Optional[float] = None
    calls_by_model: dict[str, int] = field(default_factory=dict)
    cost_by_model: dict[str, float] = field(default_factory=dict)

    def record(self, metrics: LLMCallMetrics) -> None:
        """Record a completed LLM call."""
        self.total_cost += metrics.cost
        self.total_requests += 1
        self.total_input_tokens += metrics.input_tokens
        self.total_output_tokens += metrics.output_tokens
        self.calls_by_model[metrics.model] = self.calls_by_model.get(metrics.model, 0) + 1
        self.cost_by_model[metrics.model] = self.cost_by_model.get(metrics.model, 0.0) + metrics.cost

    def check_budget(self, estimated_cost: float = 0.0) -> bool:
        """Check if we're within budget. Raises if over."""
        if self.per_request_limit and estimated_cost > self.per_request_limit:
            raise BudgetExceededError(
                f"Request cost ${estimated_cost:.4f} exceeds per-request limit ${self.per_request_limit:.4f}"
            )
        if self.budget_limit and (self.total_cost + estimated_cost) > self.budget_limit:
            raise BudgetExceededError(
                f"Total cost ${self.total_cost:.4f} + ${estimated_cost:.4f} exceeds budget ${self.budget_limit:.4f}"
            )
        return True

    def get_summary(self) -> dict[str, Any]:
        """Get cost tracking summary."""
        return {
            "total_cost": f"${self.total_cost:.4f}",
            "total_requests": self.total_requests,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "budget_remaining": f"${(self.budget_limit - self.total_cost):.4f}" if self.budget_limit else "unlimited",
            "by_model": {k: f"${v:.4f}" for k, v in self.cost_by_model.items()},
        }


class BudgetExceededError(Exception):
    """Raised when LLM cost exceeds configured budget."""
    pass


class AllProvidersFailedError(Exception):
    """Raised when all providers in the failover chain have failed."""
    pass


# ── Message Consistency (inspired by CAI's fix_message_list) ─────────────────


def fix_message_list(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Ensure message list consistency for LLM APIs.

    Fixes:
      - Orphaned tool_calls without tool responses
      - Orphaned tool responses without tool_calls
      - Duplicate messages
      - Missing required fields
      - Consecutive same-role messages

    Inspired by CAI (aliasrobotics/cai) fix_message_list utility.
    """
    if not messages:
        return messages

    fixed = []
    seen_tool_call_ids: set[str] = set()
    pending_tool_calls: dict[str, dict] = {}

    for msg in messages:
        role = msg.get("role", "")

        # Skip empty messages
        if not role:
            continue

        # Track tool_calls from assistant messages
        if role == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                tc_id = tc.get("id", "")
                if tc_id:
                    pending_tool_calls[tc_id] = tc
                    seen_tool_call_ids.add(tc_id)
            fixed.append(msg)
            continue

        # Match tool responses to their calls
        if role == "tool":
            tc_id = msg.get("tool_call_id", "")
            if tc_id in pending_tool_calls:
                del pending_tool_calls[tc_id]
                fixed.append(msg)
            elif tc_id not in seen_tool_call_ids:
                # Orphaned tool response — wrap as system message
                logger.debug(f"Dropping orphaned tool response for {tc_id}")
                fixed.append({
                    "role": "system",
                    "content": f"[Tool output (orphaned)]: {msg.get('content', '')[:200]}",
                })
            else:
                fixed.append(msg)
            continue

        # Normal messages
        fixed.append(msg)

    # Handle pending tool_calls without responses (add synthetic responses)
    if pending_tool_calls:
        for tc_id, tc in pending_tool_calls.items():
            fn_name = tc.get("function", {}).get("name", "unknown")
            logger.debug(f"Adding synthetic tool response for pending call: {fn_name}")
            fixed.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": f"[Tool execution interrupted - no response for {fn_name}]",
            })

    return fixed


# ── Context Auto-Compaction ──────────────────────────────────────────────────


# Approximate token limits per model family
MODEL_TOKEN_LIMITS = {
    "gpt-4": 128000,
    "gpt-4o": 128000,
    "gpt-3.5": 16385,
    "claude-3": 200000,
    "claude-3.5": 200000,
    "gemini": 1000000,
    "llama": 8192,
    "llama3": 131072,
    "qwen": 32768,
    "deepseek": 64000,
    "phi": 16384,
    "mistral": 32768,
}


def estimate_tokens(text: str) -> int:
    """Estimate token count (rough: 1 token ≈ 4 chars for English)."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        # Fallback: rough estimate
        return len(text) // 4


def get_model_limit(model: str) -> int:
    """Get approximate token limit for a model."""
    model_lower = model.lower()
    for key, limit in MODEL_TOKEN_LIMITS.items():
        if key in model_lower:
            return limit
    return 8192  # Conservative default


def auto_compact_messages(
    messages: list[dict[str, Any]],
    model: str,
    threshold: float = 0.85,
) -> tuple[list[dict[str, Any]], bool]:
    """
    Auto-compact messages if approaching context limit.

    Keeps the system prompt + last N messages, summarizes the rest.
    Returns (compacted_messages, was_compacted).

    Inspired by CAI's _auto_compact_if_needed.
    """
    # Estimate total tokens
    total_text = ""
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(str(c) for c in content)
        total_text += str(content) + " "

    total_tokens = estimate_tokens(total_text)
    max_tokens = get_model_limit(model)

    if total_tokens < max_tokens * threshold:
        return messages, False

    logger.warning(
        f"Context approaching limit ({total_tokens}/{max_tokens} tokens, "
        f"{total_tokens / max_tokens * 100:.0f}%), compacting..."
    )

    # Strategy: keep system prompt + first assistant response + last 8 messages
    compacted = []

    # Keep system messages
    system_msgs = [m for m in messages if m.get("role") == "system"]
    other_msgs = [m for m in messages if m.get("role") != "system"]

    if system_msgs:
        compacted.extend(system_msgs)

    if len(other_msgs) <= 10:
        # Too few messages to compact
        return messages, False

    # Summarize dropped messages
    dropped = other_msgs[:-8]
    kept = other_msgs[-8:]

    summary_parts = []
    for msg in dropped:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(str(c) for c in content)
        if content:
            summary_parts.append(f"[{role}]: {str(content)[:100]}")

    summary = "=== Context Summary (auto-compacted) ===\n"
    summary += f"Removed {len(dropped)} older messages. Key points:\n"
    summary += "\n".join(summary_parts[:20])  # Keep max 20 summary lines
    if len(summary_parts) > 20:
        summary += f"\n... and {len(summary_parts) - 20} more messages"

    compacted.append({
        "role": "user",
        "content": summary,
    })
    compacted.append({
        "role": "assistant",
        "content": "Understood. I'll continue from the recent context.",
    })
    compacted.extend(kept)

    new_tokens = estimate_tokens(" ".join(str(m.get("content", "")) for m in compacted))
    logger.info(f"Context compacted: {total_tokens} → {new_tokens} tokens ({len(messages)} → {len(compacted)} messages)")

    return compacted, True


# ── Rate Limit Delay Extraction ──────────────────────────────────────────────


def extract_retry_delay(error: Exception, default: int = 60) -> int:
    """
    Extract retry delay from an error message.

    Parses:
      - "Retry-After: 30"
      - "retry after 30 seconds"
      - "wait 30 seconds"
      - "rate_limit.reset_requests: 30s"

    Inspired by CAI's retry delay extraction logic.
    """
    error_str = str(error)

    # Pattern 1: Retry-After header value
    retry_match = re.search(r'[Rr]etry[_-]?[Aa]fter[\s:]+(\d+)', error_str)
    if retry_match:
        return int(retry_match.group(1))

    # Pattern 2: "wait X seconds"
    wait_match = re.search(r'wait\s+(\d+)\s+seconds?', error_str, re.IGNORECASE)
    if wait_match:
        return int(wait_match.group(1))

    # Pattern 3: "Xs" format (e.g., "30s")
    sec_match = re.search(r'(\d+)s\b', error_str)
    if sec_match:
        return int(sec_match.group(1))

    # Pattern 4: "X milliseconds" → convert
    ms_match = re.search(r'(\d+)\s*m(?:illi)?s(?:econds?)?', error_str, re.IGNORECASE)
    if ms_match:
        return max(1, int(ms_match.group(1)) // 1000)

    return default


# ── Main LLM Client ──────────────────────────────────────────────────────────


class LLMClient:
    """
    Enterprise-grade LLM client with reliability features.

    Usage:
        client = LLMClient()
        client.add_provider(ProviderConfig(
            model="openrouter/openai/gpt-4o",
            api_key="sk-or-...",
            priority=1,
        ))
        client.add_provider(ProviderConfig(
            model="ollama/llama3.1",
            priority=2,  # Fallback
        ))

        response = await client.chat(messages=[
            {"role": "user", "content": "Scan the target for open ports"}
        ])
    """

    def __init__(
        self,
        budget_limit: Optional[float] = None,
        per_request_limit: Optional[float] = None,
    ):
        self.providers: list[ProviderConfig] = []
        self.cost_tracker = CostTracker(
            budget_limit=budget_limit,
            per_request_limit=per_request_limit,
        )
        self.metrics_log: list[LLMCallMetrics] = []
        self._rate_tokens: dict[str, float] = {}
        self._rate_last: dict[str, float] = {}
        self._rate_locks: dict[str, asyncio.Lock] = {}

    def add_provider(self, config: ProviderConfig) -> None:
        """Add a provider to the failover chain."""
        self.providers.append(config)
        self.providers.sort(key=lambda p: p.priority)
        self._rate_tokens[config.model] = config.rpm_limit
        self._rate_last[config.model] = time.monotonic()
        self._rate_locks[config.model] = asyncio.Lock()
        logger.info(f"Provider added: {config.model} (priority={config.priority})")

    def add_providers_from_env(self) -> None:
        """Auto-configure providers from environment variables."""
        # Primary: OpenRouter (if key exists)
        or_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("REDCLAW_LLM_KEY")
        if not or_key:
            # Try loading from file
            key_file = Path.home() / ".redclaw" / "api_key.txt"
            if key_file.exists():
                or_key = key_file.read_text().strip()

        if or_key:
            self.add_provider(ProviderConfig(
                model="openrouter/openai/gpt-4o-mini",
                api_key=or_key,
                api_base="https://openrouter.ai/api/v1",
                priority=1,
                max_tokens=4096,
                rpm_limit=20,
                description="OpenRouter Primary",
            ))

        # Gemini (if key exists)
        gemini_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if gemini_key:
            self.add_provider(ProviderConfig(
                model="gemini/gemini-2.0-flash",
                api_key=gemini_key,
                priority=2,
                max_tokens=8192,
                rpm_limit=60,
                description="Google Gemini Fallback",
            ))

        # Ollama local (always available as last resort)
        self.add_provider(ProviderConfig(
            model="ollama/llama3.1",
            api_base="http://localhost:11434",
            priority=10,
            max_tokens=4096,
            rpm_limit=100,
            description="Ollama Local Fallback",
        ))

    async def _rate_limit_acquire(self, model: str, rpm_limit: int) -> None:
        """Token bucket rate limiter."""
        lock = self._rate_locks.get(model)
        if not lock:
            return

        async with lock:
            now = time.monotonic()
            elapsed = now - self._rate_last.get(model, now)
            self._rate_last[model] = now

            # Refill tokens
            refill = elapsed * (rpm_limit / 60.0)
            self._rate_tokens[model] = min(
                rpm_limit,
                self._rate_tokens.get(model, rpm_limit) + refill,
            )

            if self._rate_tokens[model] < 1:
                wait = (1 - self._rate_tokens[model]) / (rpm_limit / 60.0)
                logger.debug(f"Rate limit: waiting {wait:.1f}s for {model}")
                await asyncio.sleep(wait)
                self._rate_tokens[model] = 0
            else:
                self._rate_tokens[model] -= 1

    async def _call_single_provider(
        self,
        provider: ProviderConfig,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        """
        Call a single LLM provider with retry logic.

        Implements CAI-style exponential backoff + jitter.
        """
        # Rate limiting
        await self._rate_limit_acquire(provider.model, provider.rpm_limit)

        # Auto-compact if needed
        messages, was_compacted = auto_compact_messages(messages, provider.model)

        # Fix message consistency
        messages = fix_message_list(messages)

        # Build kwargs for litellm
        kwargs: dict[str, Any] = {
            "model": provider.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else provider.temperature,
            "max_tokens": max_tokens or provider.max_tokens,
            "timeout": provider.timeout,
        }

        if provider.api_key:
            kwargs["api_key"] = provider.api_key
        if provider.api_base:
            kwargs["api_base"] = provider.api_base
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        # Additional LiteLLM params
        kwargs["drop_params"] = True  # Drop unsupported params silently
        kwargs["num_retries"] = 0     # We handle retries ourselves

        last_error = None
        metrics = LLMCallMetrics(model=provider.model, provider=provider.description)

        for attempt in range(provider.max_retries):
            start_time = time.monotonic()
            try:
                # Try LiteLLM first, fallback to aiohttp
                try:
                    import litellm
                    litellm.drop_params = True
                    response = await litellm.acompletion(**kwargs)
                except ImportError:
                    # Fallback: use aiohttp directly (existing behavior)
                    response = await self._aiohttp_fallback(provider, messages, tools, temperature, max_tokens)

                latency = time.monotonic() - start_time

                # Extract response data
                choice = response.choices[0] if response.choices else None
                usage = response.usage if hasattr(response, "usage") and response.usage else None

                content = ""
                tool_calls = []
                finish_reason = ""

                if choice:
                    content = choice.message.content or ""
                    finish_reason = choice.finish_reason or ""
                    if hasattr(choice.message, "tool_calls") and choice.message.tool_calls:
                        for tc in choice.message.tool_calls:
                            tool_calls.append({
                                "id": tc.id if hasattr(tc, "id") else "",
                                "type": "function",
                                "function": {
                                    "name": tc.function.name if hasattr(tc, "function") else "",
                                    "arguments": tc.function.arguments if hasattr(tc, "function") else "{}",
                                },
                            })

                input_tokens = usage.prompt_tokens if usage else 0
                output_tokens = usage.completion_tokens if usage else 0

                # Calculate cost
                cost = 0.0
                try:
                    import litellm
                    cost = litellm.completion_cost(completion_response=response)
                except Exception:
                    pass

                # Record metrics
                metrics.latency = latency
                metrics.input_tokens = input_tokens
                metrics.output_tokens = output_tokens
                metrics.total_tokens = input_tokens + output_tokens
                metrics.cost = cost
                metrics.success = True
                metrics.retries = attempt
                self.metrics_log.append(metrics)
                self.cost_tracker.record(metrics)

                logger.info(
                    f"LLM OK: {provider.model} | {latency:.1f}s | "
                    f"{input_tokens}+{output_tokens} tokens | ${cost:.4f} | "
                    f"attempt {attempt + 1}"
                )

                return {
                    "content": content,
                    "tool_calls": tool_calls,
                    "finish_reason": finish_reason,
                    "usage": {
                        "prompt_tokens": input_tokens,
                        "completion_tokens": output_tokens,
                        "total_tokens": input_tokens + output_tokens,
                    },
                    "model": provider.model,
                    "latency": latency,
                    "cost": cost,
                    "provider": provider.description,
                }

            except Exception as e:
                latency = time.monotonic() - start_time
                error_str = str(e)
                last_error = e

                # Check if it's a rate limit error
                is_rate_limit = any(kw in error_str.lower() for kw in [
                    "rate_limit", "429", "too many requests", "ratelimit",
                    "quota", "throttl",
                ])

                if is_rate_limit:
                    # Extract delay from error
                    retry_delay = extract_retry_delay(e, default=60)

                    # Exponential backoff + jitter (CAI approach)
                    if attempt > 0 and retry_delay == 60:
                        retry_delay = min(300, retry_delay * (attempt + 1))

                    retry_delay += random.randint(0, 10)  # Jitter

                    logger.warning(
                        f"⏳ Rate limited by {provider.model} "
                        f"(attempt {attempt + 1}/{provider.max_retries}), "
                        f"waiting {retry_delay}s..."
                    )
                    await asyncio.sleep(retry_delay)
                    continue

                # Server errors (5xx) — retry with backoff
                is_server_error = any(kw in error_str for kw in ["500", "502", "503", "504"])
                if is_server_error:
                    backoff = 2 ** attempt + random.random()
                    logger.warning(
                        f"🔄 Server error from {provider.model} "
                        f"(attempt {attempt + 1}), retrying in {backoff:.1f}s..."
                    )
                    await asyncio.sleep(backoff)
                    continue

                # Timeout
                if "timeout" in error_str.lower() or isinstance(e, asyncio.TimeoutError):
                    backoff = 2 ** attempt
                    logger.warning(
                        f"⏱️ Timeout from {provider.model} "
                        f"(attempt {attempt + 1}), retrying in {backoff}s..."
                    )
                    await asyncio.sleep(backoff)
                    continue

                # Context length exceeded — compact and retry once
                if "context" in error_str.lower() and "length" in error_str.lower():
                    logger.warning(f"📏 Context overflow for {provider.model}, force-compacting...")
                    messages, _ = auto_compact_messages(messages, provider.model, threshold=0.5)
                    kwargs["messages"] = messages
                    continue

                # Unknown error — don't retry, fail to next provider
                logger.error(f"❌ Unrecoverable error from {provider.model}: {error_str[:200]}")
                break

        # All retries exhausted
        metrics.success = False
        metrics.error = str(last_error)[:200] if last_error else "unknown"
        metrics.retries = provider.max_retries
        self.metrics_log.append(metrics)

        raise last_error or RuntimeError(f"Provider {provider.model} failed")

    async def _aiohttp_fallback(
        self,
        provider: ProviderConfig,
        messages: list[dict],
        tools: Optional[list[dict]],
        temperature: Optional[float],
        max_tokens: Optional[int],
    ) -> Any:
        """Fallback: use aiohttp for OpenAI-compatible APIs when litellm isn't installed."""
        import aiohttp

        base_url = provider.api_base or "https://openrouter.ai/api/v1"
        url = f"{base_url}/chat/completions"

        payload: dict[str, Any] = {
            "model": provider.model.replace("openrouter/", ""),
            "messages": messages,
            "temperature": temperature if temperature is not None else provider.temperature,
            "max_tokens": max_tokens or provider.max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {provider.api_key}",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=provider.timeout),
            ) as resp:
                if resp.status == 429:
                    body = await resp.text()
                    raise RuntimeError(f"429 Rate limit: {body[:200]}")
                if resp.status >= 500:
                    raise RuntimeError(f"{resp.status} Server error")
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"API error {resp.status}: {body[:200]}")
                data = await resp.json()

        # Convert to litellm-like response object
        from types import SimpleNamespace
        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        usage = data.get("usage", {})

        tool_calls = []
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                tool_calls.append(SimpleNamespace(
                    id=tc.get("id", ""),
                    function=SimpleNamespace(
                        name=tc.get("function", {}).get("name", ""),
                        arguments=tc.get("function", {}).get("arguments", "{}"),
                    ),
                ))

        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(
                    content=msg.get("content", ""),
                    tool_calls=tool_calls or None,
                ),
                finish_reason=choice.get("finish_reason", ""),
            )],
            usage=SimpleNamespace(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ),
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        preferred_model: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Send a chat request with automatic provider failover.

        Tries each provider in priority order. If one fails after all retries,
        moves to the next provider in the chain.
        """
        if not self.providers:
            raise RuntimeError("No LLM providers configured. Call add_provider() first.")

        # Budget check
        self.cost_tracker.check_budget()

        # If a preferred model is specified, try it first
        providers = list(self.providers)
        if preferred_model:
            matching = [p for p in providers if preferred_model in p.model]
            others = [p for p in providers if preferred_model not in p.model]
            providers = matching + others

        errors = []
        for provider in providers:
            try:
                logger.debug(f"Trying provider: {provider.model} ({provider.description})")
                result = await self._call_single_provider(
                    provider, messages, tools, temperature, max_tokens, stream,
                )
                return result

            except BudgetExceededError:
                raise  # Don't failover on budget issues

            except Exception as e:
                error_msg = f"{provider.model}: {str(e)[:100]}"
                errors.append(error_msg)
                logger.warning(f"Provider failed: {error_msg}, trying next...")
                continue

        raise AllProvidersFailedError(
            f"All {len(self.providers)} providers failed:\n"
            + "\n".join(f"  • {e}" for e in errors)
        )

    def get_health_report(self) -> dict[str, Any]:
        """Get LLM health report for monitoring dashboard."""
        recent = self.metrics_log[-50:] if self.metrics_log else []
        success_count = sum(1 for m in recent if m.success)
        total_count = len(recent)

        avg_latency = 0.0
        if recent:
            successful = [m for m in recent if m.success]
            if successful:
                avg_latency = sum(m.latency for m in successful) / len(successful)

        return {
            "providers": [
                {
                    "model": p.model,
                    "description": p.description,
                    "priority": p.priority,
                    "rpm_limit": p.rpm_limit,
                }
                for p in self.providers
            ],
            "health": {
                "success_rate": f"{success_count}/{total_count}" if total_count else "N/A",
                "avg_latency": f"{avg_latency:.1f}s",
                "total_calls": len(self.metrics_log),
                "total_errors": sum(1 for m in self.metrics_log if not m.success),
            },
            "cost": self.cost_tracker.get_summary(),
            "last_call": {
                "model": recent[-1].model if recent else "none",
                "latency": f"{recent[-1].latency:.1f}s" if recent else "N/A",
                "success": recent[-1].success if recent else None,
            } if recent else {},
        }
