"""
ContextWindowManager — LLM token budget management with sliding window and priority compression.

Manages the limited context window of the LLM by:
  - Tracking token usage across system prompt, history, tool outputs, and user messages
  - Implementing a sliding window that drops oldest low-priority content first
  - Summarizing old findings to save tokens
  - Prioritizing recent tool outputs and critical findings
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

logger = logging.getLogger("redclaw.core.context")


class Priority(IntEnum):
    """Content priority for context window allocation."""
    CRITICAL = 0   # system prompt, current phase instructions
    HIGH = 1       # recent tool outputs, critical findings
    MEDIUM = 2     # older findings, phase summaries
    LOW = 3        # historical context, verbose logs
    EPHEMERAL = 4  # can be dropped freely


@dataclass
class ContextBlock:
    """A block of content in the context window."""
    id: str
    content: str
    token_count: int
    priority: Priority
    source: str  # "system", "user", "tool", "finding", "summary"
    phase: str = ""
    timestamp: float = 0.0
    compressed: bool = False

    @property
    def can_compress(self) -> bool:
        return not self.compressed and self.priority >= Priority.MEDIUM

    @property
    def can_drop(self) -> bool:
        return self.priority == Priority.EPHEMERAL


class ContextWindowManager:
    """
    Manages LLM context window with priority-based allocation.

    Usage:
        ctx = ContextWindowManager(max_tokens=4096)
        ctx.add_system_prompt("You are a penetration tester...", tokens=200)
        ctx.add_tool_output("nmap_scan_1", "<nmap output>", tokens=500)
        messages = ctx.build_messages()  # returns within token budget
    """

    def __init__(self, max_tokens: int = 4096, reserve_tokens: int = 512):
        self._max_tokens = max_tokens
        self._reserve_tokens = reserve_tokens  # reserved for LLM response
        self._available_tokens = max_tokens - reserve_tokens
        self._blocks: list[ContextBlock] = []
        self._total_tokens = 0
        logger.info(
            f"ContextWindowManager: max={max_tokens}, "
            f"available={self._available_tokens}, reserve={reserve_tokens}"
        )

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    @property
    def used_tokens(self) -> int:
        return self._total_tokens

    @property
    def remaining_tokens(self) -> int:
        return max(0, self._available_tokens - self._total_tokens)

    @property
    def utilization(self) -> float:
        return self._total_tokens / self._available_tokens if self._available_tokens else 0

    # ── Add content ──────────────────────────────────────────────────────

    def add_system_prompt(self, content: str, tokens: Optional[int] = None) -> None:
        """Add system prompt (highest priority, never dropped)."""
        tokens = tokens or self._estimate_tokens(content)
        self._add_block(
            ContextBlock(
                id="system_prompt",
                content=content,
                token_count=tokens,
                priority=Priority.CRITICAL,
                source="system",
            )
        )

    def add_user_message(self, content: str, tokens: Optional[int] = None) -> None:
        """Add a user/operator message."""
        tokens = tokens or self._estimate_tokens(content)
        block_id = f"user_{len(self._blocks)}"
        self._add_block(
            ContextBlock(
                id=block_id,
                content=content,
                token_count=tokens,
                priority=Priority.HIGH,
                source="user",
            )
        )

    def add_tool_output(
        self, tool_id: str, content: str, tokens: Optional[int] = None, phase: str = ""
    ) -> None:
        """Add tool output (high priority initially, degrades over time)."""
        tokens = tokens or self._estimate_tokens(content)
        self._add_block(
            ContextBlock(
                id=f"tool_{tool_id}",
                content=content,
                token_count=tokens,
                priority=Priority.HIGH,
                source="tool",
                phase=phase,
            )
        )

    def add_finding(
        self, finding_id: str, content: str, severity: str = "info",
        tokens: Optional[int] = None
    ) -> None:
        """Add a finding with priority based on severity."""
        tokens = tokens or self._estimate_tokens(content)
        priority = {
            "critical": Priority.CRITICAL,
            "high": Priority.HIGH,
            "medium": Priority.MEDIUM,
            "low": Priority.LOW,
            "info": Priority.EPHEMERAL,
        }.get(severity, Priority.MEDIUM)

        self._add_block(
            ContextBlock(
                id=f"finding_{finding_id}",
                content=content,
                token_count=tokens,
                priority=priority,
                source="finding",
            )
        )

    def add_phase_summary(
        self, phase: str, summary: str, tokens: Optional[int] = None
    ) -> None:
        """Add a compressed phase summary (replaces detailed findings)."""
        tokens = tokens or self._estimate_tokens(summary)
        self._add_block(
            ContextBlock(
                id=f"summary_{phase}",
                content=summary,
                token_count=tokens,
                priority=Priority.MEDIUM,
                source="summary",
                phase=phase,
                compressed=True,
            )
        )

    def _add_block(self, block: ContextBlock) -> None:
        """Add a block, evicting lower-priority content if needed."""
        # Remove existing block with same ID
        self._blocks = [b for b in self._blocks if b.id != block.id]
        self._blocks.append(block)
        self._recalculate_tokens()

        # Evict if over budget
        while self._total_tokens > self._available_tokens:
            if not self._evict_lowest_priority():
                break  # nothing left to evict

    # ── Build messages ───────────────────────────────────────────────────

    def build_messages(self) -> list[dict[str, str]]:
        """Build LLM message list from current context blocks."""
        messages: list[dict[str, str]] = []

        # Sort: system first, then by priority (lowest number = highest priority)
        sorted_blocks = sorted(self._blocks, key=lambda b: (b.source != "system", b.priority))

        for block in sorted_blocks:
            if block.source == "system":
                messages.append({"role": "system", "content": block.content})
            elif block.source == "user":
                messages.append({"role": "user", "content": block.content})
            else:
                # Tool outputs, findings, summaries → assistant context
                messages.append({"role": "assistant", "content": block.content})

        return messages

    # ── Eviction and compression ─────────────────────────────────────────

    def _evict_lowest_priority(self) -> bool:
        """Remove the lowest-priority block to free tokens."""
        # Sort by priority descending (highest number = lowest priority)
        candidates = [b for b in self._blocks if b.priority > Priority.CRITICAL]
        if not candidates:
            return False

        candidates.sort(key=lambda b: (-b.priority, b.timestamp))
        victim = candidates[0]
        self._blocks.remove(victim)
        self._recalculate_tokens()
        logger.debug(f"Evicted context block: {victim.id} ({victim.token_count} tokens)")
        return True

    def compress_phase(self, phase: str, summary: str) -> int:
        """Compress all blocks from a phase into a single summary. Returns tokens saved."""
        phase_blocks = [
            b for b in self._blocks
            if b.phase == phase and b.source in ("tool", "finding") and not b.compressed
        ]
        if not phase_blocks:
            return 0

        old_tokens = sum(b.token_count for b in phase_blocks)
        for block in phase_blocks:
            self._blocks.remove(block)

        self.add_phase_summary(phase, summary)
        self._recalculate_tokens()
        saved = old_tokens - self._estimate_tokens(summary)
        logger.info(f"Compressed phase '{phase}': saved {saved} tokens")
        return saved

    def _recalculate_tokens(self) -> None:
        self._total_tokens = sum(b.token_count for b in self._blocks)

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimate: ~4 chars per token."""
        return max(1, len(text) // 4)

    # ── Status ───────────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        return {
            "max_tokens": self._max_tokens,
            "used_tokens": self._total_tokens,
            "remaining": self.remaining_tokens,
            "utilization": f"{self.utilization:.1%}",
            "blocks": len(self._blocks),
            "by_priority": {
                p.name: sum(1 for b in self._blocks if b.priority == p)
                for p in Priority
            },
        }

    def clear(self) -> None:
        """Clear all context blocks."""
        self._blocks.clear()
        self._total_tokens = 0

    def __repr__(self) -> str:
        return (
            f"ContextWindowManager("
            f"used={self._total_tokens}/{self._available_tokens}, "
            f"blocks={len(self._blocks)})"
        )
