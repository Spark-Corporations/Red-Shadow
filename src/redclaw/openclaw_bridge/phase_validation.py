"""
Phase Validation System — 3-layer termination control.

Enterprise-grade phase completion verification:
  Layer 1: Structured Output Validation — LLM must return JSON with required fields
  Layer 2: External State Checker — Python functions verify KG state independently
  Layer 3: Max Iteration + Incomplete Flag — retry N times, then mark incomplete and move on

No phase trusts the LLM's claim of completion. The system verifies via data.

Usage:
    result = await run_phase_with_validation(
        phase_fn=self.phase_recon,
        checker=is_recon_complete,
        kg=self.kg,
        target=self.target,
        max_retries=2,
    )
    if result.status == PhaseStatus.COMPLETE:
        ...  # proceed
    elif result.status == PhaseStatus.INCOMPLETE:
        ...  # log warning, proceed anyway
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("redclaw.validation")


# ── Enums & Data Types ────────────────────────────────────────────────────────


class PhaseStatus(str, Enum):
    """Phase completion status — determined by system, not LLM."""
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PhaseResult:
    """Structured result from any phase — replaces raw strings."""
    phase: str
    status: PhaseStatus
    data: Dict[str, Any] = field(default_factory=dict)
    required_fields: Dict[str, Any] = field(default_factory=dict)
    missing_fields: List[str] = field(default_factory=list)
    iterations: int = 0
    notes: str = ""

    @property
    def is_complete(self) -> bool:
        return self.status == PhaseStatus.COMPLETE

    @property
    def is_actionable(self) -> bool:
        """True if we have enough data to proceed to next phase."""
        return self.status in (PhaseStatus.COMPLETE, PhaseStatus.INCOMPLETE)

    def summary_line(self) -> str:
        status_icon = {
            PhaseStatus.COMPLETE: "✅",
            PhaseStatus.INCOMPLETE: "⚠️",
            PhaseStatus.FAILED: "❌",
            PhaseStatus.SKIPPED: "⏭️",
        }
        icon = status_icon.get(self.status, "?")
        missing = f" (missing: {', '.join(self.missing_fields)})" if self.missing_fields else ""
        iters = f" [{self.iterations} iter]" if self.iterations > 1 else ""
        return f"{icon} {self.phase}: {self.status.value}{missing}{iters}"


# ── Layer 1: Structured Output Validation ─────────────────────────────────────


def validate_required_fields(
    data: Dict[str, Any],
    required: Dict[str, type],
) -> List[str]:
    """Check that all required fields exist and are non-empty.

    Args:
        data: The output dict from a phase
        required: Mapping of field_name → expected type (list, str, dict, bool)

    Returns:
        List of missing/empty field names. Empty list = all good.
    """
    missing = []
    for field_name, expected_type in required.items():
        value = data.get(field_name)

        if value is None:
            missing.append(field_name)
            continue

        # Type-specific emptiness checks
        if expected_type == list and (not isinstance(value, list) or len(value) == 0):
            missing.append(field_name)
        elif expected_type == str and (not isinstance(value, str) or value.strip() == ""):
            missing.append(field_name)
        elif expected_type == dict and (not isinstance(value, dict) or len(value) == 0):
            missing.append(field_name)
        elif expected_type == bool and not isinstance(value, bool):
            missing.append(field_name)

    return missing


# ── Layer 2: External State Checkers ──────────────────────────────────────────
# These functions NEVER trust LLM. They only look at KG/data state.


def is_recon_complete(kg: Any, target: str) -> bool:
    """Verify recon phase produced real data in KnowledgeGraph."""
    if target not in kg.graph:
        return False

    # Must have at least 1 port discovered
    services = kg.get_services_for_host(target)
    return services.get("count", 0) > 0


def is_analysis_complete(kg: Any, target: str) -> bool:
    """Verify analysis phase wrote vulnerabilities to KG."""
    vulns = kg.get_vulnerabilities_for_host(target)
    # At least 1 vulnerability identified (or explicit "no vulns" flag)
    return vulns.get("count", 0) > 0


def is_exploit_complete(kg: Any, target: str) -> bool:
    """Verify exploit phase tested at least one attack."""
    attack = kg.get_attack_path()
    return attack.get("exploit_count", 0) > 0


def is_ingest_complete(kg: Any, target: str) -> bool:
    """Verify scan results were written to KG."""
    return target in kg.graph and len(list(kg.graph.successors(target))) > 0


def is_always_complete(kg: Any, target: str) -> bool:
    """For phases that don't need external validation (summary, report)."""
    return True


# Map phase names to their external checkers
PHASE_CHECKERS: Dict[str, Callable] = {
    "recon": is_recon_complete,
    "ingest": is_ingest_complete,
    "analysis": is_analysis_complete,
    "exploit_gen": is_always_complete,  # code generation — no KG write
    "exploit_exec": is_exploit_complete,
    "zeroday": is_always_complete,
    "post_exploit": is_always_complete,
    "summary": is_always_complete,
    "report": is_always_complete,
}

# Required fields per phase — Layer 1 validation
PHASE_REQUIRED_FIELDS: Dict[str, Dict[str, type]] = {
    "recon": {
        "open_ports": list,
        "services": list,
        "target": str,
    },
    "ingest": {
        "graph_written": bool,
    },
    "analysis": {
        "vulnerabilities_found": bool,
        "analysis_text": str,
    },
    "exploit_gen": {
        "exploit_code": str,
    },
    "exploit_exec": {
        "tests_run": list,
    },
}


# ── Layer 3: Phase Runner with Retry ──────────────────────────────────────────


class PhaseRunner:
    """Executes a phase with 3-layer validation and retry logic.

    Usage:
        runner = PhaseRunner(kg=self.kg, target=self.target)
        result = await runner.run(
            phase_name="recon",
            phase_fn=self.phase_recon,
            max_retries=2,
        )
    """

    def __init__(self, kg: Any, target: str, log_fn: Optional[Callable] = None):
        self.kg = kg
        self.target = target
        self._log = log_fn or (lambda msg: logger.info(msg))
        self.results: Dict[str, PhaseResult] = {}

    async def run(
        self,
        phase_name: str,
        phase_fn: Callable,
        max_retries: int = 2,
        phase_args: tuple = (),
        phase_kwargs: dict = None,
    ) -> PhaseResult:
        """Execute a phase with full validation.

        Retry logic:
          1. Call phase_fn → get raw output
          2. Layer 1: Check required fields in output
          3. Layer 2: Run external checker against KG
          4. If both pass → COMPLETE
          5. If either fails and retries left → retry
          6. If max retries hit → INCOMPLETE (proceed anyway)
        """
        phase_kwargs = phase_kwargs or {}
        checker = PHASE_CHECKERS.get(phase_name, is_always_complete)
        required = PHASE_REQUIRED_FIELDS.get(phase_name, {})

        for attempt in range(1, max_retries + 1):
            self._log(f"  [{phase_name}] Attempt {attempt}/{max_retries}")

            try:
                # Execute the phase
                raw_output = await phase_fn(*phase_args, **phase_kwargs)

                # Normalize output to dict
                if isinstance(raw_output, dict):
                    output_data = raw_output
                elif isinstance(raw_output, str):
                    output_data = {"raw_text": raw_output}
                elif isinstance(raw_output, list):
                    output_data = {"results": raw_output}
                else:
                    output_data = {"value": raw_output}

                # ── Layer 1: Structured field validation ──
                missing = validate_required_fields(output_data, required)

                # ── Layer 2: External state checker ──
                external_ok = checker(self.kg, self.target)

                if not missing and external_ok:
                    # All clear — phase is truly complete
                    result = PhaseResult(
                        phase=phase_name,
                        status=PhaseStatus.COMPLETE,
                        data=output_data,
                        required_fields=required,
                        missing_fields=[],
                        iterations=attempt,
                    )
                    self.results[phase_name] = result
                    self._log(f"  [{phase_name}] ✅ COMPLETE (attempt {attempt})")
                    return result

                # Something failed — log and maybe retry
                reasons = []
                if missing:
                    reasons.append(f"missing fields: {missing}")
                if not external_ok:
                    reasons.append("external checker failed (KG state)")
                self._log(f"  [{phase_name}] ⚠️ Validation failed: {', '.join(reasons)}")

                if attempt < max_retries:
                    self._log(f"  [{phase_name}] Retrying...")
                    continue

                # Max retries hit → INCOMPLETE but proceed
                result = PhaseResult(
                    phase=phase_name,
                    status=PhaseStatus.INCOMPLETE,
                    data=output_data,
                    required_fields=required,
                    missing_fields=missing,
                    iterations=attempt,
                    notes=f"Incomplete after {attempt} attempts: {', '.join(reasons)}",
                )
                self.results[phase_name] = result
                self._log(f"  [{phase_name}] ⚠️ INCOMPLETE — moving on. {result.notes}")
                return result

            except Exception as e:
                logger.error(f"  [{phase_name}] Error on attempt {attempt}: {e}")
                if attempt >= max_retries:
                    result = PhaseResult(
                        phase=phase_name,
                        status=PhaseStatus.FAILED,
                        data={},
                        iterations=attempt,
                        notes=f"Failed after {attempt} attempts: {e}",
                    )
                    self.results[phase_name] = result
                    self._log(f"  [{phase_name}] ❌ FAILED: {e}")
                    return result

        # Should never reach here, but just in case
        return PhaseResult(phase=phase_name, status=PhaseStatus.FAILED, notes="Unexpected exit")

    def get_summary(self) -> str:
        """Get a summary of all phase results."""
        lines = ["Phase Execution Summary:"]
        for name, result in self.results.items():
            lines.append(f"  {result.summary_line()}")
        return "\n".join(lines)

    def get_incomplete_phases(self) -> List[str]:
        """Get list of phases that didn't fully complete."""
        return [
            name for name, result in self.results.items()
            if result.status in (PhaseStatus.INCOMPLETE, PhaseStatus.FAILED)
        ]
