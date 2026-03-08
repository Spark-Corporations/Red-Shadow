"""
PhaseAgent — Base class for isolated-context phase execution.

Solves the structural contradiction: 3 parallel execution layers
(socket tests, LLM-gen code, BashWrapper) none fully working.

Each PhaseAgent:
  1. Gets its own isolated conversation thread (no context bleed)
  2. Reads from KG only what it needs
  3. Runs tools via BashWrapper (real subprocess) or direct Python
  4. Validates output externally (not trusting LLM)
  5. Writes results back to KG for next phase to read

Usage:
    agent = ReconPhaseAgent(target, kg, memory, call_llm, tools)
    result = await agent.run()
    # result.status == PhaseStatus.COMPLETE
    # KG now has host/port/service nodes
"""
from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("redclaw.phase_agent")


# ── Phase Context Map (what each phase reads from KG) ─────────────────────────

PHASE_CONTEXT_MAP: Dict[str, List[str]] = {
    "planning":     [],
    "recon":        [],
    "ingest":       ["services"],
    "analysis":     ["services", "vulnerabilities"],
    "exploit_gen":  ["services", "vulnerabilities"],
    "exploit_exec": ["services", "vulnerabilities", "exploits"],
    "zeroday":      ["services"],
    "post_exploit": ["services", "vulnerabilities", "exploits", "credentials"],
    "summary":      ["services", "vulnerabilities", "exploits", "credentials"],
}

# ── Phase System Prompts ──────────────────────────────────────────────────────

PHASE_SYSTEM_PROMPTS: Dict[str, str] = {
    "planning": (
        "You are a penetration test planner. Analyze the target scope "
        "and produce a structured JSON plan specifying which phases to run."
    ),
    "recon": "",  # No LLM needed — tool-driven
    "analysis": (
        "You are a vulnerability analyst. Given scan results, identify CVEs, "
        "rate severity, and suggest exploit approaches. Be concise."
    ),
    "exploit_gen": (
        "You are an exploit developer. Given a hypothesis, write a Python "
        "function that tests exactly that hypothesis. Use only stdlib."
    ),
    "exploit_exec": (
        "You are an exploitation execution specialist. Select the most promising "
        "targets based on vulnerability data."
    ),
    "post_exploit": (
        "You are a post-exploitation specialist. Enumerate the compromised system, "
        "harvest credentials, and identify lateral movement opportunities."
    ),
    "summary": (
        "You are a cybersecurity report writer. Write a professional executive "
        "summary covering scope, methodology, findings, and remediation."
    ),
}


# ── Phase Result ──────────────────────────────────────────────────────────────


class AgentPhaseStatus(Enum):
    """Phase execution status."""
    PENDING    = "pending"
    RUNNING    = "running"
    COMPLETE   = "complete"
    INCOMPLETE = "incomplete"
    FAILED     = "failed"
    SKIPPED    = "skipped"


@dataclass
class PhaseResult:
    """Structured result from a phase execution."""
    phase_name: str
    status: AgentPhaseStatus
    data: Dict[str, Any] = field(default_factory=dict)
    missing_fields: List[str] = field(default_factory=list)
    iterations_used: int = 0
    elapsed_seconds: float = 0.0
    error: Optional[str] = None

    @property
    def is_complete(self) -> bool:
        return self.status == AgentPhaseStatus.COMPLETE

    @property
    def is_actionable(self) -> bool:
        """Has enough data for next phase to use."""
        return self.status in (AgentPhaseStatus.COMPLETE, AgentPhaseStatus.INCOMPLETE) and bool(self.data)

    def summary_line(self) -> str:
        icon = {
            AgentPhaseStatus.COMPLETE: "✅",
            AgentPhaseStatus.INCOMPLETE: "⚠️",
            AgentPhaseStatus.FAILED: "❌",
            AgentPhaseStatus.SKIPPED: "⏭️",
            AgentPhaseStatus.RUNNING: "🔄",
            AgentPhaseStatus.PENDING: "⏳",
        }.get(self.status, "?")
        missing = f" missing={self.missing_fields}" if self.missing_fields else ""
        return (f"{icon} {self.phase_name}: {self.status.value} "
                f"({self.iterations_used} iter, {self.elapsed_seconds:.1f}s){missing}")


# ── Phase Agent Base ──────────────────────────────────────────────────────────


class PhaseAgentBase(ABC):
    """
    Base class for every phase in the pentest pipeline.

    Rules:
      1. Each instance owns an isolated conversation thread
      2. Reads from KG only what this phase needs
      3. Runs tools via BashWrapper (real subprocess) or direct Python
      4. Validates output externally (LLM output checked by _validate())
      5. Tools are phase-specific — recon gets nmap, exploit gets sqlmap

    Subclasses implement:
      - PHASE_NAME: str
      - REQUIRED_OUTPUT_FIELDS: list[str]
      - execute() -> dict
      - _system_prompt() -> str
      - _load_context_from_kg() -> str
      - _write_to_kg(result) -> None
    """

    PHASE_NAME: str = ""
    REQUIRED_OUTPUT_FIELDS: List[str] = []

    def __init__(
        self,
        target: str,
        kg: Any,
        memory: Any = None,
        call_llm: Optional[Callable] = None,
        tools: Optional[Dict[str, Any]] = None,
        log_fn: Optional[Callable] = None,
    ):
        self.target = target
        self.kg = kg
        self.memory = memory
        self.call_llm = call_llm
        self.tools = tools or {}
        self._log = log_fn or (lambda msg: logger.info(msg))

        # Isolated conversation — each agent starts clean
        self.conversation: List[Dict[str, str]] = []
        self.max_iterations = 3

    async def run(self) -> PhaseResult:
        """
        Main execution loop. Subclasses do NOT override this.

        Flow:
          1. Load context from KG
          2. Initialize clean conversation
          3. Execute (may use tools and/or LLM)
          4. Validate externally (don't trust LLM)
          5. If invalid, retry with feedback
          6. Write to KG
          7. Return PhaseResult
        """
        start = time.time()
        self._log(f"\n  🔷 PhaseAgent: {self.PHASE_NAME} starting")

        try:
            # 1. Load context from KG
            context = self._load_context_from_kg()

            # 2. Clean conversation (isolated from all other phases)
            sys_prompt = self._system_prompt()
            if sys_prompt:
                self.conversation = [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": context},
                ]
            else:
                self.conversation = []

            # 3-5. Execute + validate loop
            raw_result = {}
            validation = {"valid": False, "missing": []}

            for attempt in range(self.max_iterations):
                self._log(f"    Iteration {attempt + 1}/{self.max_iterations}")

                try:
                    raw_result = await self.execute()
                except Exception as e:
                    self._log(f"    ❌ Execute failed: {e}")
                    raw_result = {}

                # 4. External validation — LLM's opinion is irrelevant
                validation = self._validate(raw_result)

                if validation["valid"]:
                    # 6. Write to KG
                    try:
                        self._write_to_kg(raw_result)
                    except Exception as e:
                        self._log(f"    ⚠️ KG write failed: {e}")

                    elapsed = time.time() - start
                    self._log(f"    ✅ {self.PHASE_NAME} COMPLETE "
                              f"({attempt + 1} iter, {elapsed:.1f}s)")

                    return PhaseResult(
                        phase_name=self.PHASE_NAME,
                        status=AgentPhaseStatus.COMPLETE,
                        data=raw_result,
                        iterations_used=attempt + 1,
                        elapsed_seconds=elapsed,
                    )

                # Tell LLM what's missing (for next attempt)
                missing_msg = f"Validation failed. Missing: {validation['missing']}. Retry."
                self._log(f"    ⚠️ {missing_msg}")
                self.conversation.append({"role": "user", "content": missing_msg})

            # Max iterations exhausted
            elapsed = time.time() - start
            self._log(f"    ⚠️ {self.PHASE_NAME} INCOMPLETE after {self.max_iterations} iterations")

            # Write whatever we have
            if raw_result:
                try:
                    self._write_to_kg(raw_result)
                except Exception:
                    pass

            return PhaseResult(
                phase_name=self.PHASE_NAME,
                status=AgentPhaseStatus.INCOMPLETE,
                data=raw_result,
                missing_fields=validation.get("missing", []),
                iterations_used=self.max_iterations,
                elapsed_seconds=elapsed,
            )

        except Exception as e:
            elapsed = time.time() - start
            self._log(f"    ❌ {self.PHASE_NAME} FAILED: {e}")
            return PhaseResult(
                phase_name=self.PHASE_NAME,
                status=AgentPhaseStatus.FAILED,
                error=str(e),
                elapsed_seconds=elapsed,
            )

    # ── Abstract methods — subclasses implement these ─────────────────────

    @abstractmethod
    async def execute(self) -> dict:
        """The phase's actual work. Returns structured dict."""
        ...

    @abstractmethod
    def _system_prompt(self) -> str:
        """LLM system prompt for this phase. Return '' if no LLM needed."""
        ...

    @abstractmethod
    def _load_context_from_kg(self) -> str:
        """Read only what this phase needs from KG."""
        ...

    @abstractmethod
    def _write_to_kg(self, result: dict) -> None:
        """Write phase results to KG for downstream phases."""
        ...

    # ── Validation ────────────────────────────────────────────────────────

    def _validate(self, result: dict) -> dict:
        """
        External state checker.

        Does NOT ask LLM. Checks data structure only.
        If REQUIRED_OUTPUT_FIELDS has items, all must be non-empty in result.
        """
        if not result:
            return {"valid": False, "missing": self.REQUIRED_OUTPUT_FIELDS or ["(empty result)"]}

        missing = [
            f for f in self.REQUIRED_OUTPUT_FIELDS
            if not result.get(f)
        ]
        return {"valid": len(missing) == 0, "missing": missing}

    # ── LLM Helper ────────────────────────────────────────────────────────

    async def ask_llm(self, prompt: str, temperature: float = 0.3) -> str:
        """Send prompt to LLM using this agent's isolated conversation."""
        if not self.call_llm:
            raise RuntimeError(f"{self.PHASE_NAME}: no LLM callable provided")

        self.conversation.append({"role": "user", "content": prompt})

        response = await self.call_llm(
            messages=self.conversation,
            temperature=temperature,
        )

        # Extract text from response
        if isinstance(response, str):
            text = response
        elif hasattr(response, "content"):
            text = response.content
        elif isinstance(response, dict):
            text = response.get("content", response.get("text", str(response)))
        else:
            text = str(response)

        self.conversation.append({"role": "assistant", "content": text})
        return text

    # ── Tool Helper ───────────────────────────────────────────────────────

    async def run_tool(self, tool_name: str, action: str, params: dict) -> Any:
        """Run a tool by name. Returns CleanedOutput or raw result."""
        tool = self.tools.get(tool_name)
        if not tool:
            self._log(f"    ⚠️ Tool not available: {tool_name}")
            return None

        try:
            result = await tool.execute(action, params)
            return result
        except Exception as e:
            self._log(f"    ❌ Tool {tool_name}.{action} failed: {e}")
            return None

    async def run_command(self, command: str, timeout: int = 120) -> str:
        """Shortcut: run a shell command via BashWrapper. Returns raw output."""
        bash = self.tools.get("bash")
        if not bash:
            self._log("    ⚠️ BashWrapper not available")
            return ""

        try:
            result = await bash.execute("exec_command", {
                "command": command,
                "cwd": "/tmp",
            })
            # CleanedOutput → extract content
            if hasattr(result, "structured"):
                content = result.structured.get("content", "")
                if content:
                    return content
                return result.summary
            return str(result)
        except Exception as e:
            self._log(f"    ❌ Command failed: {command[:60]}: {e}")
            return ""


# ── Legacy PhaseAgent (backward compat) ───────────────────────────────────────
# The old PhaseAgent from the previous implementation is kept as-is for
# backward compatibility. New phases should subclass PhaseAgentBase instead.


class PhaseAgent:
    """
    Isolated agent context for a single pentest phase (legacy).

    Maintained for backward compatibility with existing pentest.py code.
    New phases should subclass PhaseAgentBase instead.
    """

    def __init__(
        self,
        phase_name: str,
        kg: Any,
        target: str,
        log_fn: Optional[Callable] = None,
    ):
        self.phase_name = phase_name
        self.kg = kg
        self.target = target
        self._log = log_fn or (lambda msg: logger.info(msg))
        self.conversation: List[Dict[str, str]] = []
        self._call_count = 0
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0

        # System prompt
        system_prompt = PHASE_SYSTEM_PROMPTS.get(phase_name, "")
        if system_prompt:
            self.conversation.append({"role": "system", "content": system_prompt})

        # KG context
        kg_context = self.build_context()
        if kg_context:
            self.conversation.append({"role": "user", "content": kg_context})

    def build_context(self) -> str:
        """Build KG context string with ONLY this phase's allowed sections."""
        allowed = PHASE_CONTEXT_MAP.get(self.phase_name, [])
        if not allowed:
            return ""

        sections = []

        if "services" in allowed:
            try:
                svc_data = self.kg.get_services_for_host(self.target)
                svc_list = svc_data.get("services", [])
                if svc_list:
                    svc_lines = [f"  {s['port']}/{s.get('name', '?')} "
                                 f"v{s.get('version', '?')}" for s in svc_list]
                    sections.append("Services:\n" + "\n".join(svc_lines))
            except Exception:
                pass

        if "vulnerabilities" in allowed:
            try:
                vuln_data = self.kg.get_vulnerabilities_for_host(self.target)
                vulns = vuln_data.get("vulnerabilities", [])
                if vulns:
                    vuln_lines = [f"  {v['cve']} [{v.get('severity', '?')}] "
                                  f"on {v.get('service', '?')}" for v in vulns]
                    sections.append("Vulnerabilities:\n" + "\n".join(vuln_lines))
            except Exception:
                pass

        if "credentials" in allowed:
            try:
                cred_data = self.kg.get_credentials_for_host(self.target)
                creds = cred_data.get("credentials", [])
                if creds:
                    cred_lines = [f"  {c.get('username', '?')}:{c.get('password', '***')} "
                                  f"from {c.get('source', '?')}" for c in creds]
                    sections.append("Credentials:\n" + "\n".join(cred_lines))
            except Exception:
                pass

        return "\n\n".join(sections) if sections else ""

    async def ask(
        self,
        prompt: str,
        llm_call_fn: Callable,
        temperature: float = 0.2,
        extra_context: str = "",
    ) -> str:
        """Make an isolated LLM call with clean context."""
        user_msg = prompt
        if extra_context:
            user_msg = f"{prompt}\n\nAdditional context:\n{extra_context}"

        self.conversation.append({"role": "user", "content": user_msg})
        self._call_count += 1

        try:
            response = await llm_call_fn(
                messages=self.conversation,
                temperature=temperature,
            )

            if isinstance(response, str):
                text = response
            elif hasattr(response, "content"):
                text = response.content
            elif isinstance(response, dict):
                text = response.get("content", response.get("text", str(response)))
            else:
                text = str(response)

            self.conversation.append({"role": "assistant", "content": text})

            self._total_prompt_tokens += len(user_msg) // 4
            self._total_completion_tokens += len(text) // 4

            return text

        except Exception as e:
            self._log(f"    Phase {self.phase_name} LLM call failed: {e}")
            raise

    def get_diagnostics(self) -> dict:
        """Get token/call diagnostics for this phase."""
        return {
            "phase": self.phase_name,
            "calls": self._call_count,
            "conversation_length": len(self.conversation),
            "est_prompt_tokens": self._total_prompt_tokens,
            "est_completion_tokens": self._total_completion_tokens,
        }
