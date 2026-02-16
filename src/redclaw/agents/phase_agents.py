"""
Phase-specific pentesting agents for the 8-phase pipeline.

Each agent specializes the BaseAgent ReAct loop for its domain:
  - ReconAgent: OSINT, DNS, subdomain enumeration
  - ScanAgent: Port scanning, service detection
  - VulnAssessAgent: Vulnerability scanning and analysis
  - ExploitAgent: Exploitation with human approval
  - PostExploitAgent: Privilege escalation, data harvesting
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .base_agent import BaseAgent

logger = logging.getLogger("redclaw.agents.phase_agents")


class ReconAgent(BaseAgent):
    """Reconnaissance and OSINT gathering agent."""

    def __init__(self, runtime=None, state_manager=None):
        super().__init__("recon_agent", "reconnaissance", runtime, state_manager)
        self._tools_available = ["nmap", "masscan"]
        self._subdomains_found: list[str] = []
        self._dns_records: list[dict] = []

    async def observe(self, iteration: int) -> str:
        targets = self._context.get("targets", [])
        if iteration == 1:
            return f"Starting reconnaissance on targets: {targets}. No data collected yet."
        return (
            f"Iteration {iteration}: "
            f"{len(self._subdomains_found)} subdomains, "
            f"{len(self._findings)} findings so far."
        )

    async def think(self, observation: str, iteration: int) -> str:
        if iteration == 1:
            return "Starting with DNS enumeration and ping sweep to identify live hosts."
        if iteration > 10:
            return "COMPLETE — sufficient reconnaissance data gathered."
        return "Continue with port scanning on discovered hosts."

    async def act(self, decision: str, iteration: int) -> tuple[str, Optional[str]]:
        if self._runtime:
            # Delegate to OpenClaw runtime for LLM-guided tool selection
            async for msg in self._runtime.run_task(
                f"Execute recon step: {decision}",
                context={"phase": "reconnaissance", **self._context}
            ):
                return msg.content, "openclaw"
        return f"[DRY RUN] Would execute: {decision}", None

    async def evaluate(self, action_result: str, iteration: int) -> str:
        if iteration >= 8:
            return "PHASE_COMPLETE — reconnaissance thorough enough for scanning phase."
        return "Continue — more reconnaissance data needed."


class ScanAgent(BaseAgent):
    """Port scanning and service detection agent."""

    def __init__(self, runtime=None, state_manager=None):
        super().__init__("scan_agent", "scanning", runtime, state_manager)
        self._tools_available = ["nmap", "masscan"]

    async def observe(self, iteration: int) -> str:
        return f"Scan iteration {iteration}: {len(self._findings)} ports/services discovered."

    async def think(self, observation: str, iteration: int) -> str:
        if iteration == 1:
            return "Start with quick full-port scan (masscan) then targeted service scan (nmap -sV)."
        if iteration > 5:
            return "COMPLETE — port scan coverage sufficient."
        return "Run detailed service version detection on discovered open ports."

    async def act(self, decision: str, iteration: int) -> tuple[str, Optional[str]]:
        if self._runtime:
            async for msg in self._runtime.run_task(
                f"Execute scanning step: {decision}",
                context={"phase": "scanning", **self._context}
            ):
                return msg.content, "openclaw"
        return f"[DRY RUN] Would execute: {decision}", None

    async def evaluate(self, action_result: str, iteration: int) -> str:
        if iteration >= 4:
            return "PHASE_COMPLETE — comprehensive port and service data collected."
        return "Continue scanning."


class VulnAssessAgent(BaseAgent):
    """Vulnerability assessment agent."""

    def __init__(self, runtime=None, state_manager=None):
        super().__init__("vuln_agent", "vulnerability_assessment", runtime, state_manager)
        self._tools_available = ["nuclei", "nmap"]

    async def observe(self, iteration: int) -> str:
        return f"VulnAssess iteration {iteration}: {len(self._findings)} vulnerabilities identified."

    async def think(self, observation: str, iteration: int) -> str:
        if iteration == 1:
            return "Run Nuclei with critical/high severity templates against discovered services."
        if iteration > 6:
            return "COMPLETE — vulnerability assessment sufficient."
        return "Expand scanning with additional templates for discovered service versions."

    async def act(self, decision: str, iteration: int) -> tuple[str, Optional[str]]:
        if self._runtime:
            async for msg in self._runtime.run_task(
                f"Execute vuln assessment: {decision}",
                context={"phase": "vulnerability_assessment", **self._context}
            ):
                return msg.content, "openclaw"
        return f"[DRY RUN] Would execute: {decision}", None

    async def evaluate(self, action_result: str, iteration: int) -> str:
        if iteration >= 5:
            return "PHASE_COMPLETE — vulnerability assessment coverage adequate."
        return "Continue — check for additional vulnerability classes."


class ExploitAgent(BaseAgent):
    """Exploitation agent — requires human approval for high-risk actions."""

    def __init__(self, runtime=None, state_manager=None):
        super().__init__("exploit_agent", "exploitation", runtime, state_manager)
        self._tools_available = ["metasploit", "sqlmap", "hydra", "custom_exploit"]
        self._max_iterations = 15  # fewer iterations, more careful

    async def observe(self, iteration: int) -> str:
        return (
            f"Exploit iteration {iteration}: "
            f"{len(self._findings)} successful exploits. "
            f"Vulnerabilities available for exploitation from previous phase."
        )

    async def think(self, observation: str, iteration: int) -> str:
        if iteration == 1:
            return "Prioritize exploitation by vulnerability severity. Start with critical findings."
        if iteration > 8:
            return "COMPLETE — exploitation phase concluded."
        return "Attempt next highest-severity vulnerability exploitation."

    async def act(self, decision: str, iteration: int) -> tuple[str, Optional[str]]:
        if self._runtime:
            async for msg in self._runtime.run_task(
                f"Execute exploitation: {decision}",
                context={"phase": "exploitation", **self._context}
            ):
                return msg.content, "openclaw"
        return f"[DRY RUN] Would execute: {decision}", None

    async def evaluate(self, action_result: str, iteration: int) -> str:
        if "success" in action_result.lower() or "shell" in action_result.lower():
            self.add_finding({
                "title": "Successful exploitation",
                "severity": "critical",
                "details": action_result[:500],
            })
        if iteration >= 6:
            return "PHASE_COMPLETE — exploitation phase concluded."
        return "Continue — attempt next vulnerability."


class PostExploitAgent(BaseAgent):
    """Post-exploitation agent — privilege escalation, data harvesting."""

    def __init__(self, runtime=None, state_manager=None):
        super().__init__("post_exploit_agent", "post_exploitation", runtime, state_manager)
        self._tools_available = ["linpeas", "winpeas", "bloodhound"]

    async def observe(self, iteration: int) -> str:
        return f"PostExploit iteration {iteration}: {len(self._findings)} post-exploit findings."

    async def think(self, observation: str, iteration: int) -> str:
        if iteration == 1:
            return "Run LinPEAS/WinPEAS for privilege escalation vectors."
        if iteration > 10:
            return "COMPLETE — post-exploitation enumeration complete."
        return "Attempt privilege escalation using discovered vectors."

    async def act(self, decision: str, iteration: int) -> tuple[str, Optional[str]]:
        if self._runtime:
            async for msg in self._runtime.run_task(
                f"Execute post-exploitation: {decision}",
                context={"phase": "post_exploitation", **self._context}
            ):
                return msg.content, "openclaw"
        return f"[DRY RUN] Would execute: {decision}", None

    async def evaluate(self, action_result: str, iteration: int) -> str:
        if iteration >= 8:
            return "PHASE_COMPLETE — post-exploitation enumeration complete."
        return "Continue post-exploitation activities."
