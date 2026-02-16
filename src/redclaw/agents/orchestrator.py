"""
PipelineOrchestrator — Orchestrates the 8-phase pentesting pipeline.

Manages the sequence of phase agents, transitions, findings accumulation,
and reporting.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from ..core.state import PipelinePhase, StateManager
from .base_agent import AgentResult
from .phase_agents import (
    ExploitAgent,
    PostExploitAgent,
    ReconAgent,
    ScanAgent,
    VulnAssessAgent,
)

logger = logging.getLogger("redclaw.agents.orchestrator")


class PipelineOrchestrator:
    """
    Orchestrates the full 8-phase pentesting pipeline.

    Flow:
      Planning → Recon → Scanning → VulnAssess → Exploitation → PostExploit → Reporting → Cleanup

    Usage:
        orchestrator = PipelineOrchestrator(state_manager, runtime)
        results = await orchestrator.run(engagement_context)
    """

    def __init__(self, state_manager: StateManager, runtime=None):
        self._state = state_manager
        self._runtime = runtime
        self._results: dict[str, AgentResult] = {}
        self._start_time: float = 0

        # Map phases to agents
        self._agents = {
            PipelinePhase.RECONNAISSANCE: ReconAgent(runtime, state_manager),
            PipelinePhase.SCANNING: ScanAgent(runtime, state_manager),
            PipelinePhase.VULNERABILITY_ASSESSMENT: VulnAssessAgent(runtime, state_manager),
            PipelinePhase.EXPLOITATION: ExploitAgent(runtime, state_manager),
            PipelinePhase.POST_EXPLOITATION: PostExploitAgent(runtime, state_manager),
        }

        # Phases executed in order
        self._phase_order = [
            PipelinePhase.PLANNING,
            PipelinePhase.RECONNAISSANCE,
            PipelinePhase.SCANNING,
            PipelinePhase.VULNERABILITY_ASSESSMENT,
            PipelinePhase.EXPLOITATION,
            PipelinePhase.POST_EXPLOITATION,
            PipelinePhase.REPORTING,
            PipelinePhase.CLEANUP,
        ]

        logger.info("PipelineOrchestrator initialized")

    async def run(
        self,
        context: dict[str, Any],
        start_phase: Optional[PipelinePhase] = None,
        skip_phases: Optional[list[PipelinePhase]] = None,
    ) -> dict[str, AgentResult]:
        """
        Execute the full pipeline.

        Args:
            context: Engagement context (targets, scope, config)
            start_phase: Phase to start from (for resuming)
            skip_phases: Phases to skip
        """
        self._start_time = time.monotonic()
        skip = set(skip_phases or [])
        started = start_phase is None

        for phase in self._phase_order:
            if not started:
                if phase == start_phase:
                    started = True
                else:
                    continue

            if phase in skip:
                logger.info(f"Skipping phase: {phase.value}")
                continue

            logger.info(f"═══ Starting phase: {phase.value} ═══")
            self._state.start_phase(phase)

            # Planning, Reporting, and Cleanup are handled differently
            if phase in (PipelinePhase.PLANNING, PipelinePhase.REPORTING, PipelinePhase.CLEANUP):
                await self._handle_non_agent_phase(phase, context)
                self._state.complete_phase(phase)
                continue

            # Execute phase agent
            agent = self._agents.get(phase)
            if not agent:
                logger.warning(f"No agent for phase: {phase.value}")
                self._state.complete_phase(phase)
                continue

            try:
                # Enrich context with findings from previous phases
                enriched_context = {**context, "findings": self._collect_all_findings()}
                result = await agent.run(enriched_context)
                self._results[phase.value] = result

                # Record findings in state manager
                for finding in result.findings:
                    from ..core.state import Finding
                    self._state.add_finding(Finding(
                        id=f"{phase.value}_{len(self._state.state.findings)}",
                        phase=phase.value,
                        title=finding.get("title", ""),
                        severity=finding.get("severity", "info"),
                        description=finding.get("details", ""),
                    ))

                self._state.complete_phase(phase)
                self._state.checkpoint()

                logger.info(
                    f"Phase {phase.value} complete: "
                    f"{len(result.findings)} findings, "
                    f"{'SUCCESS' if result.success else 'FAILED'}"
                )

            except Exception as e:
                logger.error(f"Phase {phase.value} failed: {e}")
                self._state.fail_phase(phase, str(e))
                # Continue to next phase on failure (graceful degradation)

        total_time = time.monotonic() - self._start_time
        logger.info(f"Pipeline complete: {total_time:.2f}s total")
        return self._results

    async def _handle_non_agent_phase(self, phase: PipelinePhase, context: dict) -> None:
        """Handle phases without dedicated agents (planning, reporting, cleanup)."""
        if phase == PipelinePhase.PLANNING:
            logger.info("Planning phase: validating scope and configuration")
        elif phase == PipelinePhase.REPORTING:
            logger.info("Reporting phase: generating engagement report")
            # Report generation would go here
        elif phase == PipelinePhase.CLEANUP:
            logger.info("Cleanup phase: removing artifacts and closing sessions")

    def _collect_all_findings(self) -> list[dict[str, Any]]:
        """Collect findings from all completed phases."""
        findings = []
        for result in self._results.values():
            findings.extend(result.findings)
        return findings

    def get_progress(self) -> dict[str, Any]:
        """Get pipeline progress summary."""
        completed = [p for p in self._phase_order if p.value in self._results]
        total_findings = sum(len(r.findings) for r in self._results.values())
        return {
            "phases_completed": len(completed),
            "phases_total": len(self._phase_order),
            "total_findings": total_findings,
            "elapsed": f"{time.monotonic() - self._start_time:.2f}s" if self._start_time else "0s",
        }
