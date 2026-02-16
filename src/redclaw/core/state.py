"""
StateManager — Tracks pipeline progress with checkpoint/restore, phase tracking, and findings accumulation.

Responsibilities:
  - Track current phase and sub-phase
  - Checkpoint/restore state to JSON files
  - Accumulate findings per phase
  - Pause/resume pipeline execution
  - Phase transition validation
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("redclaw.core.state")


class PipelinePhase(str, Enum):
    """The 8 phases of the RedClaw pentesting pipeline."""
    PLANNING = "planning"
    RECONNAISSANCE = "reconnaissance"
    SCANNING = "scanning"
    VULNERABILITY_ASSESSMENT = "vulnerability_assessment"
    EXPLOITATION = "exploitation"
    POST_EXPLOITATION = "post_exploitation"
    REPORTING = "reporting"
    CLEANUP = "cleanup"

    @property
    def next_phase(self) -> Optional["PipelinePhase"]:
        """Get the next phase in the pipeline."""
        phases = list(PipelinePhase)
        idx = phases.index(self)
        return phases[idx + 1] if idx < len(phases) - 1 else None

    @property
    def display_name(self) -> str:
        return self.value.replace("_", " ").title()


class Finding(BaseModel):
    """A single finding discovered during the engagement."""
    id: str
    phase: str
    severity: str = "info"  # critical, high, medium, low, info
    title: str
    description: str = ""
    evidence: list[str] = Field(default_factory=list)
    tool: str = ""
    target: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)


class PhaseState(BaseModel):
    """State for a single phase."""
    status: str = "pending"  # pending, running, completed, failed, skipped
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    findings: list[Finding] = Field(default_factory=list)
    sub_phase: str = ""
    iteration: int = 0
    error: Optional[str] = None


class PipelineState(BaseModel):
    """Complete pipeline state for checkpoint/restore."""
    engagement_name: str = ""
    current_phase: str = PipelinePhase.PLANNING.value
    paused: bool = False
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_checkpoint: Optional[str] = None
    phases: dict[str, PhaseState] = Field(default_factory=dict)
    global_findings: list[Finding] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StateManager:
    """
    Manages the pipeline state with checkpoint/restore capability.

    Usage:
        state = StateManager(output_dir="./output/engagement_1")
        state.start_phase(PipelinePhase.RECONNAISSANCE)
        state.add_finding(Finding(id="f1", phase="recon", title="Open port 80"))
        state.complete_phase(PipelinePhase.RECONNAISSANCE)
        state.checkpoint()  # saves to disk
    """

    @property
    def state(self) -> "PipelineState":
        """Public accessor for the pipeline state."""
        return self._state

    def __init__(self, output_dir: str | Path = "./output", engagement_name: str = ""):
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._state = PipelineState(engagement_name=engagement_name)
        self._initialize_phases()
        logger.info(f"StateManager initialized: output_dir={self._output_dir}")

    def _initialize_phases(self) -> None:
        """Initialize state for all pipeline phases."""
        for phase in PipelinePhase:
            if phase.value not in self._state.phases:
                self._state.phases[phase.value] = PhaseState()

    # ── Phase lifecycle ───────────────────────────────────────────────────

    @property
    def current_phase(self) -> PipelinePhase:
        return PipelinePhase(self._state.current_phase)

    @property
    def is_paused(self) -> bool:
        return self._state.paused

    def start_phase(self, phase: PipelinePhase) -> None:
        """Begin a new phase."""
        self._state.current_phase = phase.value
        ps = self._state.phases[phase.value]
        ps.status = "running"
        ps.started_at = datetime.now(timezone.utc).isoformat()
        ps.iteration += 1
        logger.info(f"Phase started: {phase.display_name} (iteration {ps.iteration})")

    def complete_phase(self, phase: PipelinePhase) -> None:
        """Mark phase as completed."""
        ps = self._state.phases[phase.value]
        ps.status = "completed"
        ps.completed_at = datetime.now(timezone.utc).isoformat()
        logger.info(
            f"Phase completed: {phase.display_name} "
            f"({len(ps.findings)} findings)"
        )

    def fail_phase(self, phase: PipelinePhase, error: str) -> None:
        """Mark phase as failed."""
        ps = self._state.phases[phase.value]
        ps.status = "failed"
        ps.error = error
        ps.completed_at = datetime.now(timezone.utc).isoformat()
        logger.error(f"Phase failed: {phase.display_name} — {error}")

    def skip_phase(self, phase: PipelinePhase) -> None:
        """Skip a phase (disabled in config)."""
        ps = self._state.phases[phase.value]
        ps.status = "skipped"
        logger.info(f"Phase skipped: {phase.display_name}")

    def advance_phase(self) -> Optional[PipelinePhase]:
        """Advance to the next phase in the pipeline."""
        next_phase = self.current_phase.next_phase
        if next_phase:
            self.complete_phase(self.current_phase)
            self.start_phase(next_phase)
            return next_phase
        return None

    def set_sub_phase(self, sub_phase: str) -> None:
        """Set the current sub-phase within the active phase."""
        ps = self._state.phases[self._state.current_phase]
        ps.sub_phase = sub_phase
        logger.debug(f"Sub-phase: {sub_phase}")

    # ── Findings ──────────────────────────────────────────────────────────

    def add_finding(self, finding: Finding) -> None:
        """Add a finding to the current phase and global list."""
        phase_key = finding.phase or self._state.current_phase
        if phase_key in self._state.phases:
            self._state.phases[phase_key].findings.append(finding)
        self._state.global_findings.append(finding)
        logger.info(f"Finding added: [{finding.severity}] {finding.title}")

    def get_findings(
        self, phase: Optional[PipelinePhase] = None, severity: Optional[str] = None
    ) -> list[Finding]:
        """Get findings, optionally filtered by phase and/or severity."""
        if phase:
            findings = self._state.phases[phase.value].findings
        else:
            findings = self._state.global_findings

        if severity:
            findings = [f for f in findings if f.severity == severity]
        return findings

    @property
    def all_findings(self) -> list[Finding]:
        return self._state.global_findings

    @property
    def finding_count(self) -> dict[str, int]:
        """Count findings by severity."""
        counts: dict[str, int] = {}
        for f in self._state.global_findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        return counts

    # ── Pause/Resume ──────────────────────────────────────────────────────

    def pause(self) -> None:
        """Pause the pipeline."""
        self._state.paused = True
        self.checkpoint()
        logger.info("Pipeline PAUSED")

    def resume(self) -> None:
        """Resume the pipeline."""
        self._state.paused = False
        logger.info("Pipeline RESUMED")

    # ── Checkpoint/Restore ────────────────────────────────────────────────

    def checkpoint(self) -> Path:
        """Save current state to a JSON checkpoint file."""
        self._state.last_checkpoint = datetime.now(timezone.utc).isoformat()
        checkpoint_path = self._output_dir / "checkpoint.json"
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(self._state.model_dump(), f, indent=2)
        logger.info(f"Checkpoint saved: {checkpoint_path}")
        return checkpoint_path

    @classmethod
    def restore(cls, checkpoint_path: str | Path) -> "StateManager":
        """Restore state from a checkpoint file."""
        path = Path(checkpoint_path)
        if not path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        state = PipelineState(**data)
        output_dir = path.parent
        manager = cls(output_dir=output_dir, engagement_name=state.engagement_name)
        manager._state = state
        logger.info(f"State restored from {path}")
        return manager

    # ── Status ────────────────────────────────────────────────────────────

    def get_phase_status(self, phase: PipelinePhase) -> str:
        """Get status of a specific phase."""
        return self._state.phases[phase.value].status

    def get_progress(self) -> dict[str, Any]:
        """Get overall pipeline progress."""
        total = len(PipelinePhase)
        completed = sum(
            1 for ps in self._state.phases.values() if ps.status in ("completed", "skipped")
        )
        return {
            "current_phase": self.current_phase.display_name,
            "progress": f"{completed}/{total}",
            "percent": round(completed / total * 100),
            "paused": self.is_paused,
            "findings": self.finding_count,
        }

    def to_dict(self) -> dict[str, Any]:
        return self._state.model_dump()

    def __repr__(self) -> str:
        return (
            f"StateManager(phase={self.current_phase.display_name}, "
            f"paused={self.is_paused}, "
            f"findings={len(self.all_findings)})"
        )
