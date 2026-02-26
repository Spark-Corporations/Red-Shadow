"""
Model Alloy — XBOW-Inspired Strategic Model Switching for RedClaw V3.1

Components:
  - ModelSelector: Task classification using keyword analysis
  - BalancedRouter: Enforces 60/40 distribution (gpt-oss / qwen3)
  - ModelPerformanceTracker: Tracks success rates per model
  - ModelAlloyRouter: High-level router combining all components

Target Distribution: 60% openai/gpt-oss-120b:free (reasoning) + 40% qwen/qwen3-coder:free (coding)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("redclaw.router.model_alloy")


# ── Constants ─────────────────────────────────────────────────────────────────

BRAIN_MODEL = "openai/gpt-oss-120b:free"
HANDS_MODEL = "arcee-ai/trinity-large-preview:free"
TARGET_BRAIN_RATIO = 0.6  # 60% brain, 40% hands


# ── Model Selector ────────────────────────────────────────────────────────────


class ModelSelector:
    """
    Classify tasks to determine optimal model.

    Uses keyword analysis and context hints to route tasks.
    """

    REASONING_KEYWORDS = [
        "analyze", "assess", "evaluate", "plan", "decide",
        "strategy", "why", "how", "should", "recommend",
        "compare", "investigate", "review", "think", "reason",
        "approach", "prioritize", "risk", "threat",
    ]

    CODING_KEYWORDS = [
        "write", "code", "script", "generate", "implement",
        "function", "class", "def", "import", "compile",
        "automate", "bash", "command", "execute", "python",
        "exploit", "payload", "shellcode",
    ]

    BOTH_KEYWORDS = [
        "exploit", "vulnerability", "attack", "pentest",
        "hack", "breach", "compromise",
    ]

    def classify_task(self, task_description: str) -> str:
        """
        Classify a task and select the optimal model.

        Returns:
            "gpt-oss-120B", "qwen3-coder:free", or "BOTH"
        """
        desc_lower = task_description.lower()

        # Check for "both" indicators first (complex tasks)
        if any(kw in desc_lower for kw in self.BOTH_KEYWORDS):
            return "BOTH"

        # Count keyword matches
        reasoning_score = sum(1 for kw in self.REASONING_KEYWORDS if kw in desc_lower)
        coding_score = sum(1 for kw in self.CODING_KEYWORDS if kw in desc_lower)

        if reasoning_score > coding_score:
            return BRAIN_MODEL
        elif coding_score > reasoning_score:
            return HANDS_MODEL
        else:
            # Tie or no clear match — use context hints
            return self._use_context_hint(task_description)

    @staticmethod
    def _use_context_hint(description: str) -> str:
        """Use additional context when keywords don't help."""
        # Check for code-like patterns
        if re.search(r'[{}\[\]();]', description):
            return HANDS_MODEL

        # Check for question marks (reasoning)
        if '?' in description:
            return BRAIN_MODEL

        # Default to brain (better at ambiguous tasks)
        return BRAIN_MODEL


# ── Balanced Router ───────────────────────────────────────────────────────────


class BalancedRouter:
    """
    Enforce 60/40 model distribution while respecting task classification.

    Adjusts model selection to maintain the target ratio, only overriding
    the natural classification when the distribution is significantly off.
    """

    def __init__(self, target_brain_ratio: float = TARGET_BRAIN_RATIO):
        self.target_ratio = target_brain_ratio
        self.brain_count = 0
        self.hands_count = 0
        self._selector = ModelSelector()

    def route(self, task: dict[str, Any]) -> str:
        """
        Route a task while maintaining balance.

        Args:
            task: Dict with at least "description" key

        Returns:
            Model ID string
        """
        description = task.get("description", "")

        # Get natural classification
        natural_choice = self._selector.classify_task(description)

        # Handle BOTH — always return BOTH, let caller decide
        if natural_choice == "BOTH":
            # Count as brain call for ratio tracking (brain leads in BOTH)
            self.brain_count += 1
            return "BOTH"

        # Calculate current ratio
        total = self.brain_count + self.hands_count
        current_ratio = self.brain_count / max(total, 1)

        # Determine if we need to rebalance
        choice = self._apply_balance(natural_choice, current_ratio)

        # Update counters
        if choice == BRAIN_MODEL:
            self.brain_count += 1
        else:
            self.hands_count += 1

        return choice

    def _apply_balance(self, natural_choice: str, current_ratio: float) -> str:
        """Apply balance enforcement to the natural choice."""
        off_balance_minor = 0.05
        off_balance_major = 0.15

        if current_ratio < self.target_ratio - off_balance_minor:
            # Too few brain calls
            if natural_choice == BRAIN_MODEL:
                return BRAIN_MODEL
            elif current_ratio < self.target_ratio - off_balance_major:
                # Severely off — force brain
                logger.debug(f"Forcing brain (ratio={current_ratio:.2f}, target={self.target_ratio})")
                return BRAIN_MODEL
            else:
                return natural_choice

        elif current_ratio > self.target_ratio + off_balance_minor:
            # Too many brain calls
            if natural_choice == HANDS_MODEL:
                return HANDS_MODEL
            elif current_ratio > self.target_ratio + off_balance_major:
                # Severely off — force hands
                logger.debug(f"Forcing hands (ratio={current_ratio:.2f}, target={self.target_ratio})")
                return HANDS_MODEL
            else:
                return natural_choice

        else:
            # Balanced — use natural choice
            return natural_choice

    def get_stats(self) -> dict[str, Any]:
        """Get distribution statistics."""
        total = self.brain_count + self.hands_count
        return {
            "brain_count": self.brain_count,
            "hands_count": self.hands_count,
            "brain_ratio": self.brain_count / max(total, 1),
            "hands_ratio": self.hands_count / max(total, 1),
            "target_ratio": self.target_ratio,
            "balanced": abs(self.brain_count / max(total, 1) - self.target_ratio) < 0.05,
            "total_calls": total,
        }

    def reset(self):
        """Reset counters."""
        self.brain_count = 0
        self.hands_count = 0


# ── Performance Tracker ───────────────────────────────────────────────────────


class ModelPerformanceTracker:
    """
    Track success rates per model for adaptive routing.
    """

    def __init__(self):
        self._results: dict[str, dict[str, int]] = {
            BRAIN_MODEL: {"success": 0, "failure": 0},
            HANDS_MODEL: {"success": 0, "failure": 0},
        }

    def record(self, model: str, success: bool):
        """Record a task outcome."""
        if model not in self._results:
            self._results[model] = {"success": 0, "failure": 0}

        if success:
            self._results[model]["success"] += 1
        else:
            self._results[model]["failure"] += 1

    def get_success_rate(self, model: str) -> float:
        """Get success rate for a model."""
        stats = self._results.get(model, {"success": 0, "failure": 0})
        total = stats["success"] + stats["failure"]
        return stats["success"] / max(total, 1)

    def get_report(self) -> dict[str, Any]:
        """Get performance report for all models."""
        return {
            model: {
                "success_rate": self.get_success_rate(model),
                "total_tasks": stats["success"] + stats["failure"],
                "successes": stats["success"],
                "failures": stats["failure"],
            }
            for model, stats in self._results.items()
        }

    def recommend_adjustment(self) -> str:
        """Suggest routing adjustments based on performance."""
        brain_rate = self.get_success_rate(BRAIN_MODEL)
        hands_rate = self.get_success_rate(HANDS_MODEL)

        if brain_rate > hands_rate + 0.1:
            return "Consider increasing brain (gpt-oss) usage"
        elif hands_rate > brain_rate + 0.1:
            return "Consider increasing hands (qwen3) usage"
        else:
            return "Current balance is optimal"


# ── Model Alloy Router (High-Level) ──────────────────────────────────────────


class ModelAlloyRouter:
    """
    High-level Model Alloy router combining all components.

    Usage:
        from redclaw.router import OpenRouterClient, ModelAlloyRouter

        client = OpenRouterClient(api_key="sk-or-...")
        router = ModelAlloyRouter(client)

        result = await router.execute_task({
            "id": "scan_1",
            "description": "Analyze nmap results and plan attack strategy"
        })
    """

    def __init__(self, client, target_ratio: float = TARGET_BRAIN_RATIO):
        """
        Args:
            client: OpenRouterClient instance
            target_ratio: Target brain/total ratio (default 0.6)
        """
        self.client = client
        self.balanced_router = BalancedRouter(target_ratio)
        self.performance_tracker = ModelPerformanceTracker()

    async def execute_task(
        self,
        task: dict[str, Any],
        context: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Execute a task using the optimal model.

        Args:
            task: Dict with "description" (required) and "id" (optional)
            context: Additional context for the LLM

        Returns:
            Dict with "model", "result", "success", "task_id"
        """
        task_id = task.get("id", "unknown")
        description = task.get("description", "")

        # Route to model
        model = self.balanced_router.route(task)

        logger.info(f"Task {task_id} -> {model} (desc: {description[:50]}...)")

        try:
            if model == "BOTH":
                # Dual-brain collaboration
                result = await self.client.dual_brain(description, context=context)
                combined = f"Plan:\n{result['plan']}\n\nCode:\n{result['code']}"
                self.performance_tracker.record(BRAIN_MODEL, True)
                self.performance_tracker.record(HANDS_MODEL, True)
                return {
                    "model": "BOTH",
                    "result": combined,
                    "plan": result["plan"],
                    "code": result["code"],
                    "success": True,
                    "task_id": task_id,
                }

            elif model == BRAIN_MODEL:
                result = await self.client.call_brain(description, context=context)
                self.performance_tracker.record(BRAIN_MODEL, True)
                return {
                    "model": BRAIN_MODEL,
                    "result": result,
                    "success": True,
                    "task_id": task_id,
                }

            else:  # HANDS_MODEL
                result = await self.client.call_hands(description, context=context)
                self.performance_tracker.record(HANDS_MODEL, True)
                return {
                    "model": HANDS_MODEL,
                    "result": result,
                    "success": True,
                    "task_id": task_id,
                }

        except Exception as e:
            logger.error(f"Task {task_id} failed on {model}: {e}")
            if model != "BOTH":
                self.performance_tracker.record(model, False)
            return {
                "model": model,
                "result": "",
                "error": str(e),
                "success": False,
                "task_id": task_id,
            }

    def get_stats(self) -> dict[str, Any]:
        """Get combined routing and performance stats."""
        return {
            "routing": self.balanced_router.get_stats(),
            "performance": self.performance_tracker.get_report(),
            "recommendation": self.performance_tracker.recommend_adjustment(),
        }

    def log_stats(self):
        """Log current stats to logger."""
        stats = self.get_stats()
        routing = stats["routing"]
        logger.info(
            f"Model Alloy — Brain: {routing['brain_count']} ({routing['brain_ratio']:.1%}) | "
            f"Hands: {routing['hands_count']} ({routing['hands_ratio']:.1%}) | "
            f"Balanced: {routing['balanced']}"
        )
