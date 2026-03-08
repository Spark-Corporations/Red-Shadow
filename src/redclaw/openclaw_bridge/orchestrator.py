"""
PentestOrchestrator — Event-driven phase execution.

Replaces the 176-line monolithic run() method in pentest.py.

Old: Phase1 → Phase2 → ... → Phase10 (sequential if/await chain)
New: Event queue with transition map, parallel-capable, exploit_success
     triggers post_exploit immediately without waiting for zeroday.

Architecture:
  ┌─────────────┐
  │  EventQueue  │◄──── Events from completed phases
  └──────┬──────┘
         │
  ┌──────▼──────┐
  │  Dispatcher  │──── Reads events, triggers next phases
  └──────┬──────┘
         │
  ┌──────▼──────────────────────────────────┐
  │  Transition Map                         │
  │  planning → recon → ingest → analysis   │
  │  analysis → exploit_gen → exploit_exec  │
  │  exploit_success → post_exploit (ASYNC) │
  │  exploit_exec → zeroday (parallel)      │
  │  {zeroday, post_exploit} → summary_gate │
  │  summary → report → ALL_COMPLETE        │
  └─────────────────────────────────────────┘

Usage:
    orchestrator = PentestOrchestrator(pentest_instance, plan_json)
    results = await orchestrator.run()
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("redclaw.orchestrator")


# ── Event Types ───────────────────────────────────────────────────────────────


class EventType(Enum):
    PHASE_COMPLETE   = "phase_complete"
    PHASE_INCOMPLETE = "phase_incomplete"
    PHASE_FAILED     = "phase_failed"
    EXPLOIT_SUCCESS  = "exploit_success"
    ALL_COMPLETE     = "all_complete"
    CRITICAL_FAIL    = "critical_fail"


@dataclass
class PentestEvent:
    """Event emitted when a phase completes or fails."""
    type: EventType
    phase: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


# ── Orchestrator ──────────────────────────────────────────────────────────────


class PentestOrchestrator:
    """
    Event-driven pentest orchestrator.

    Replaces monolithic run() with:
      - Event queue for phase transitions
      - Transition map defining phase dependencies
      - Parallel execution for independent phases
      - Summary gate (waits for zeroday + post_exploit before summary)
      - Graceful degradation (incomplete phases still trigger next)
    """

    # Phase transition map: phase → list of phases to trigger on completion
    TRANSITION_MAP = {
        "planning":     ["recon"],
        "recon":        ["ingest"],
        "ingest":       ["analysis"],
        "analysis":     ["exploit_gen"],
        "exploit_gen":  ["exploit_exec"],
        "exploit_exec": ["zeroday"],       # post_exploit via EXPLOIT_SUCCESS event
        "zeroday":      [],                # summary via gate
        "post_exploit": [],                # summary via gate
        "summary":      ["report"],
        "report":       [],
    }

    # Phases that have been migrated to PhaseAgent
    AGENT_PHASES = {"recon", "exploit_exec", "post_exploit"}

    # Phases that gate the summary
    SUMMARY_GATE_PHASES = {"zeroday", "post_exploit"}

    def __init__(
        self,
        pentest: Any,           # RedClawPentest instance
        plan_json: Dict,        # Planning phase output
        log_fn: Optional[Callable] = None,
    ):
        self.pentest = pentest
        self.plan_json = plan_json
        self._log = log_fn or pentest._log

        # State
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self.completed_phases: Set[str] = set()
        self.skipped_phases: Set[str] = set()
        self.running_phases: Set[str] = set()
        self.phase_results: Dict[str, Dict] = {}
        self.phase_tasks: Dict[str, asyncio.Task] = {}

        # Intermediate data (for legacy phases that pass data between them)
        self._scan_result: Dict = {}
        self._analysis_text: str = ""
        self._exploit_plans: List = []
        self._exploit_results: List[Dict] = []

        # Tracking
        self.start_time = time.time()
        self.phases_incomplete: List[str] = []

    async def run(self) -> Dict[str, Any]:
        """
        Main event loop. Blocking — returns when all phases complete.

        Returns dict of {phase_name: result_data} for all executed phases.
        """
        self._log("\n  🔷 PentestOrchestrator: event-driven mode")
        self._log(f"    Plan: {self.plan_json.get('phases_to_run', 'all')}")
        self._log(f"    Skip: {self.plan_json.get('phases_to_skip', 'none')}")

        # Seed the event queue — planning already done
        await self.event_queue.put(PentestEvent(
            type=EventType.PHASE_COMPLETE,
            phase="planning",
            data=self.plan_json,
        ))
        self.completed_phases.add("planning")

        # Event loop
        while True:
            try:
                event = await asyncio.wait_for(
                    self.event_queue.get(), timeout=600,  # 10 min max
                )
            except asyncio.TimeoutError:
                self._log("    ⚠️ Orchestrator timeout (600s)")
                break

            if event.type == EventType.ALL_COMPLETE:
                self._log("    ✅ ALL_COMPLETE — orchestrator done")
                break

            if event.type == EventType.CRITICAL_FAIL:
                self._log(f"    ❌ CRITICAL_FAIL in {event.phase}: {event.data}")
                break

            await self._dispatch(event)

        # Final summary
        elapsed = time.time() - self.start_time
        self._log(f"\n    Orchestrator finished in {elapsed:.1f}s")
        self._log(f"    Completed: {sorted(self.completed_phases)}")
        self._log(f"    Skipped: {sorted(self.skipped_phases)}")
        if self.phases_incomplete:
            self._log(f"    Incomplete: {self.phases_incomplete}")

        return self.phase_results

    async def _dispatch(self, event: PentestEvent) -> None:
        """Handle an event and trigger next phases."""

        if event.type in (EventType.PHASE_COMPLETE, EventType.PHASE_INCOMPLETE):
            phase = event.phase
            self.completed_phases.add(phase)
            self.running_phases.discard(phase)
            self.phase_results[phase] = event.data

            if event.type == EventType.PHASE_INCOMPLETE:
                self.phases_incomplete.append(phase)

            self._log(f"    📨 {event.type.value}: {phase}")

            # ── Special: exploit_exec success → trigger post_exploit ──
            if phase == "exploit_exec":
                successes = event.data.get("successes", [])
                if successes:
                    await self.event_queue.put(PentestEvent(
                        type=EventType.EXPLOIT_SUCCESS,
                        phase="exploit_exec",
                        data={"successes": successes},
                    ))

            # ── Normal transition: trigger next phases ──
            next_phases = self.TRANSITION_MAP.get(phase, [])
            for next_phase in next_phases:
                await self._maybe_start_phase(next_phase)

        elif event.type == EventType.EXPLOIT_SUCCESS:
            self._log("    🎯 EXPLOIT_SUCCESS → triggering post_exploit immediately")
            await self._maybe_start_phase("post_exploit")

        # ── Check summary gate ──
        await self._check_summary_gate()

        # ── Check if all done ──
        await self._check_all_complete()

    async def _maybe_start_phase(self, phase_name: str) -> None:
        """Start a phase if it should run and isn't already running/done."""
        if phase_name in self.completed_phases:
            return
        if phase_name in self.running_phases:
            return
        if phase_name in self.skipped_phases:
            return

        if not self._should_run(phase_name):
            self.skipped_phases.add(phase_name)
            self._log(f"    ⏭️ Skipping {phase_name}")
            # Still need to check gates after skip
            await self._check_summary_gate()
            await self._check_all_complete()
            return

        # Data prerequisites for legacy phases
        if not self._check_data_prereqs(phase_name):
            self.skipped_phases.add(phase_name)
            self._log(f"    ⏭️ Skipping {phase_name} (no data)")
            await self._check_summary_gate()
            await self._check_all_complete()
            return

        self.running_phases.add(phase_name)
        task = asyncio.create_task(self._run_phase(phase_name))
        self.phase_tasks[phase_name] = task

    async def _run_phase(self, phase_name: str) -> None:
        """Execute a phase and emit result event."""
        self._log(f"\n    ▶️ Starting: {phase_name}")

        try:
            if phase_name in self.AGENT_PHASES:
                result_data = await self._run_agent_phase(phase_name)
            else:
                result_data = await self._run_legacy_phase(phase_name)

            event_type = EventType.PHASE_COMPLETE
            if not result_data:
                event_type = EventType.PHASE_INCOMPLETE
                result_data = {}

            await self.event_queue.put(PentestEvent(
                type=event_type, phase=phase_name, data=result_data,
            ))

        except Exception as e:
            self._log(f"    ❌ {phase_name} failed: {e}")
            self.pentest.errors.append({"phase": phase_name, "error": str(e)})
            await self.event_queue.put(PentestEvent(
                type=EventType.PHASE_INCOMPLETE,
                phase=phase_name,
                data={"error": str(e)},
            ))

    # ── Agent Phases (new architecture) ───────────────────────────────────

    async def _run_agent_phase(self, phase_name: str) -> Dict:
        """Run a phase using the new PhaseAgent architecture."""
        from .recon_phase_agent import ReconPhaseAgent
        from .exploit_phase_agent import ExploitPhaseAgent
        from .post_exploit_phase_agent import PostExploitPhaseAgent

        # Build LLM callable adapter (pentest.call_llm takes prompt/system_prompt,
        # but PhaseAgent.ask_llm sends messages list — need adapter)
        async def llm_adapter(messages=None, temperature=0.2, **kwargs):
            """Adapt pentest.call_llm to work with PhaseAgent's messages format."""
            if messages:
                # Extract system prompt and last user message from messages list
                system = ""
                user_msg = ""
                context = ""
                for m in messages:
                    if m["role"] == "system":
                        if not system:
                            system = m["content"]
                        else:
                            context += m["content"] + "\n"
                    elif m["role"] == "user":
                        user_msg = m["content"]
                    elif m["role"] == "assistant":
                        context += f"Previous response: {m['content'][:200]}\n"

                return await self.pentest.call_llm(
                    prompt=user_msg,
                    system_prompt=system,
                    context=context if context else None,
                    temperature=temperature,
                )
            return ""

        # Build tools dict
        tools = {}
        try:
            from redclaw.tools.bash_wrapper import BashWrapper
            tools["bash"] = BashWrapper(
                working_dir=self.pentest.work_dir,
                log_fn=self._log,
            )
        except Exception:
            pass

        base_args = dict(
            target=self.pentest.target,
            kg=self.pentest.kg,
            memory=self.pentest.persistent_memory if hasattr(self.pentest, 'persistent_memory') else None,
            call_llm=llm_adapter,
            tools=tools,
            log_fn=self._log,
        )

        if phase_name == "recon":
            agent = ReconPhaseAgent(**base_args)
            result = await agent.run()
            # Store scan_result for legacy phases
            if result.is_actionable:
                self._scan_result = result.data
            return {**result.data, "status": result.status.value,
                    "iterations": result.iterations_used}

        elif phase_name == "exploit_exec":
            agent = ExploitPhaseAgent(**base_args)
            result = await agent.run()
            if result.is_actionable:
                self._exploit_results = result.data.get("successes", [])
            return {**result.data, "status": result.status.value,
                    "successes": result.data.get("successes", [])}

        elif phase_name == "post_exploit":
            agent = PostExploitPhaseAgent(**base_args)
            result = await agent.run()
            return {**result.data, "status": result.status.value}

        return {}

    # ── Legacy Phases (not yet migrated) ──────────────────────────────────

    async def _run_legacy_phase(self, phase_name: str) -> Dict:
        """Run legacy phases via existing pentest.py methods."""
        p = self.pentest

        if phase_name == "ingest":
            if self._scan_result:
                result = await p.runner.run(
                    phase_name="ingest",
                    phase_fn=p.phase_ingest,
                    max_retries=2,
                    phase_args=(self._scan_result,),
                )
                return result.data if result.is_actionable else {}
            return {}

        elif phase_name == "analysis":
            if self._scan_result:
                result = await p.runner.run(
                    phase_name="analysis",
                    phase_fn=p.phase_analyze,
                    max_retries=2,
                    phase_args=(self._scan_result,),
                )
                if result.is_actionable:
                    self._analysis_text = result.data.get("raw_text", "")
                return result.data if result.is_actionable else {}
            return {}

        elif phase_name == "exploit_gen":
            if self._analysis_text:
                result = await p.runner.run(
                    phase_name="exploit_gen",
                    phase_fn=p.phase_exploit,
                    max_retries=2,
                    phase_args=(self._analysis_text, self._scan_result),
                )
                if result.is_actionable:
                    self._exploit_plans = result.data.get("results", [])
                return result.data if result.is_actionable else {}
            return {}

        elif phase_name == "zeroday":
            findings = await p.phase_zeroday_hunt(self._scan_result)
            for f in findings:
                self._exploit_results.append(f)
            return {"findings": findings, "count": len(findings)}

        elif phase_name == "summary":
            await p.phase_brain_summary(self._scan_result, self._exploit_results)
            return {"completed": True}

        elif phase_name == "report":
            await p.phase_report(self._scan_result, self._analysis_text)
            return {"completed": True}

        return {}

    # ── Summary Gate ──────────────────────────────────────────────────────

    async def _check_summary_gate(self) -> None:
        """
        Summary can only start when ALL gate phases are done (or skipped).
        Gate phases: zeroday, post_exploit

        This prevents summary from running before post-exploitation completes.
        """
        if "summary" in self.completed_phases or "summary" in self.running_phases:
            return

        gate_done = True
        for gate_phase in self.SUMMARY_GATE_PHASES:
            if gate_phase in self.completed_phases or gate_phase in self.skipped_phases:
                continue
            if not self._should_run(gate_phase):
                continue
            # This gate phase is still pending or running
            gate_done = False
            break

        # Also need exploit_exec to be done
        if "exploit_exec" not in self.completed_phases and "exploit_exec" not in self.skipped_phases:
            gate_done = False

        if gate_done:
            await self._maybe_start_phase("summary")

    async def _check_all_complete(self) -> None:
        """Check if all phases are done or skipped."""
        all_phases = set(self.TRANSITION_MAP.keys())
        finished = self.completed_phases | self.skipped_phases

        # Remove phases that shouldn't run from the requirement
        for phase in list(all_phases):
            if not self._should_run(phase) and phase not in self.completed_phases:
                finished.add(phase)

        if finished >= all_phases:
            await self.event_queue.put(PentestEvent(
                type=EventType.ALL_COMPLETE,
                phase="orchestrator",
                data=self.phase_results,
            ))

    # ── Helpers ───────────────────────────────────────────────────────────

    def _should_run(self, phase_name: str) -> bool:
        """Check plan JSON for skip/whitelist — same logic as pentest._should_run()."""
        skip = self.plan_json.get("phases_to_skip", [])
        run_list = self.plan_json.get("phases_to_run", [])

        if phase_name in skip:
            return False
        if run_list and phase_name not in run_list:
            return False
        return True

    def _check_data_prereqs(self, phase_name: str) -> bool:
        """Check if a phase has the data it needs to run."""
        prereqs = {
            "ingest":       lambda: bool(self._scan_result),
            "analysis":     lambda: bool(self._scan_result),
            "exploit_gen":  lambda: bool(self._analysis_text),
            "post_exploit": lambda: True,  # Reads from KG directly
        }
        check = prereqs.get(phase_name)
        return check() if check else True

    def get_summary(self) -> str:
        """Get human-readable orchestrator summary."""
        elapsed = time.time() - self.start_time
        lines = [
            f"  Orchestrator: {elapsed:.1f}s",
            f"  Completed: {len(self.completed_phases)} phases",
            f"  Skipped: {len(self.skipped_phases)} phases",
        ]
        if self.phases_incomplete:
            lines.append(f"  Incomplete: {', '.join(self.phases_incomplete)}")

        for phase, data in self.phase_results.items():
            status = data.get("status", "done")
            lines.append(f"    {phase}: {status}")

        return "\n".join(lines)
