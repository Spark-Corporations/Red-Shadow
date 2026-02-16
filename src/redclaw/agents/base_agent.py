"""
BaseAgent — Abstract base for phase-specific pentesting agents.

Implements the ReAct loop: Observe → Think → Act → Evaluate
Each phase agent specializes this pattern for its domain.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger("redclaw.agents.base")


class AgentAction(str, Enum):
    OBSERVE = "observe"
    THINK = "think"
    ACT = "act"
    EVALUATE = "evaluate"
    COMPLETE = "complete"
    ESCALATE = "escalate"  # requires human intervention


@dataclass
class AgentStep:
    """A single step in the ReAct loop."""
    iteration: int
    action: AgentAction
    input_data: str
    output_data: str
    tool_used: Optional[str] = None
    duration: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Final result from an agent's execution."""
    phase: str
    success: bool
    steps: list[AgentStep] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    total_duration: float = 0.0
    error: Optional[str] = None


class BaseAgent(ABC):
    """
    Abstract pentesting agent with ReAct loop.

    Lifecycle:
      1. initialize() — set phase context, load relevant tools
      2. run() — execute the ReAct loop until completion
      3. report() — summarize findings for the pipeline

    Subclasses implement:
      - observe(): gather data about the current state
      - think(): analyze observations and decide next action
      - act(): execute the chosen tool/action
      - evaluate(): assess results and decide if phase is complete
    """

    def __init__(self, name: str, phase: str, runtime=None, state_manager=None):
        self._name = name
        self._phase = phase
        self._runtime = runtime  # OpenClawRuntime
        self._state = state_manager
        self._steps: list[AgentStep] = []
        self._findings: list[dict[str, Any]] = []
        self._max_iterations = 30
        self._initialized = False
        logger.info(f"Agent '{name}' created for phase: {phase}")

    @property
    def name(self) -> str:
        return self._name

    @property
    def phase(self) -> str:
        return self._phase

    def initialize(self, context: dict[str, Any]) -> None:
        """Initialize the agent with engagement context."""
        self._context = context
        self._initialized = True
        logger.info(f"Agent '{self._name}' initialized with context")

    async def run(self, context: Optional[dict[str, Any]] = None) -> AgentResult:
        """
        Execute the full ReAct loop for this phase.
        """
        if context:
            self.initialize(context)

        start = time.monotonic()
        iteration = 0

        try:
            while iteration < self._max_iterations:
                iteration += 1

                # OBSERVE
                observation = await self.observe(iteration)
                self._steps.append(AgentStep(
                    iteration=iteration, action=AgentAction.OBSERVE,
                    input_data="", output_data=observation,
                ))

                # THINK
                decision = await self.think(observation, iteration)
                self._steps.append(AgentStep(
                    iteration=iteration, action=AgentAction.THINK,
                    input_data=observation, output_data=decision,
                ))

                # Check if we should complete
                if self._should_complete(decision):
                    break

                # ACT
                action_result, tool_used = await self.act(decision, iteration)
                self._steps.append(AgentStep(
                    iteration=iteration, action=AgentAction.ACT,
                    input_data=decision, output_data=action_result,
                    tool_used=tool_used,
                ))

                # EVALUATE
                evaluation = await self.evaluate(action_result, iteration)
                self._steps.append(AgentStep(
                    iteration=iteration, action=AgentAction.EVALUATE,
                    input_data=action_result, output_data=evaluation,
                ))

                if self._is_phase_complete(evaluation):
                    break

        except Exception as e:
            logger.error(f"Agent '{self._name}' error: {e}")
            return AgentResult(
                phase=self._phase, success=False,
                steps=self._steps, findings=self._findings,
                error=str(e), total_duration=time.monotonic() - start,
            )

        return AgentResult(
            phase=self._phase, success=True,
            steps=self._steps, findings=self._findings,
            recommendations=self._generate_recommendations(),
            total_duration=time.monotonic() - start,
        )

    @abstractmethod
    async def observe(self, iteration: int) -> str:
        """Gather data about the current state of the engagement."""
        ...

    @abstractmethod
    async def think(self, observation: str, iteration: int) -> str:
        """Analyze observations and decide what to do next."""
        ...

    @abstractmethod
    async def act(self, decision: str, iteration: int) -> tuple[str, Optional[str]]:
        """Execute the chosen action. Returns (result, tool_used)."""
        ...

    @abstractmethod
    async def evaluate(self, action_result: str, iteration: int) -> str:
        """Evaluate the action result and decide if the phase is complete."""
        ...

    def add_finding(self, finding: dict[str, Any]) -> None:
        """Record a finding discovered during this phase."""
        finding.setdefault("phase", self._phase)
        finding.setdefault("agent", self._name)
        self._findings.append(finding)
        logger.info(f"Finding added: {finding.get('title', 'untitled')}")

    def _should_complete(self, decision: str) -> bool:
        return "COMPLETE" in decision.upper()

    def _is_phase_complete(self, evaluation: str) -> bool:
        return "PHASE_COMPLETE" in evaluation.upper()

    def _generate_recommendations(self) -> list[str]:
        """Generate recommendations based on findings."""
        recs = []
        for f in self._findings:
            sev = f.get("severity", "info")
            if sev in ("critical", "high"):
                recs.append(f"[{sev.upper()}] Remediate: {f.get('title', '')}")
        return recs
