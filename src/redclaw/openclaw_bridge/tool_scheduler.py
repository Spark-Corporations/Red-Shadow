"""
Tool Dependency Graph (TDG) + ToolScheduler — deterministic tool sequencing.

Enterprise pattern: Tools execute based on pre-conditions, not LLM decisions.
Each tool has pre-conditions (what must exist in KG) and post-conditions (what
it produces). ToolScheduler runs tools when their pre-conditions are met,
runs independent tools in parallel, and auto-skips tools whose pre-conditions
can never be satisfied.

Usage:
    scheduler = ToolScheduler(kg=self.kg, target="10.10.10.5")
    results = await scheduler.run()
    # → deterministic execution order, parallel where possible, auto-skip

    print(scheduler.get_execution_log())
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("redclaw.tool_scheduler")


# ── Tool Status ───────────────────────────────────────────────────────────────


class ToolStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETE = "complete"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class ToolResult:
    """Result from a single tool execution."""
    tool: str
    status: ToolStatus
    duration: float = 0.0
    output: str = ""
    capabilities_produced: List[str] = field(default_factory=list)
    error: str = ""

    @property
    def icon(self) -> str:
        return {
            ToolStatus.COMPLETE: "✅",
            ToolStatus.FAILED: "❌",
            ToolStatus.SKIPPED: "⏭️",
            ToolStatus.RUNNING: "🔄",
            ToolStatus.PENDING: "⏳",
            ToolStatus.READY: "🟢",
        }.get(self.status, "?")


# ── Tool Dependency Graph ─────────────────────────────────────────────────────
# pre:  capabilities that MUST exist in KG before this tool can run
# post: capabilities this tool PRODUCES (written to KG after completion)
# cmd:  actual command template (target/port substituted at runtime)
# available_check: system binary that must exist (checked via shutil.which)

TOOL_DEPENDENCY_GRAPH: Dict[str, Dict[str, Any]] = {
    "nmap_scan": {
        "pre": [],
        "post": ["open_ports", "services", "os_detection"],
        "cmd": "nmap -sV -sC -O {target}",
        "binary": "nmap",
        "timeout": 300,
        "description": "Port scan + service version detection",
    },
    "nuclei_scan": {
        "pre": ["open_ports"],
        "post": ["cve_matches", "nuclei_results"],
        "cmd": "nuclei -u {target} -severity critical,high,medium -silent",
        "binary": "nuclei",
        "timeout": 180,
        "description": "CVE + vulnerability template scanning",
    },
    "gobuster_scan": {
        "pre": ["http_confirmed"],
        "post": ["directories", "hidden_paths"],
        "cmd": "gobuster dir -u http://{target}:{http_port} -w /usr/share/wordlists/dirb/common.txt -q",
        "binary": "gobuster",
        "timeout": 120,
        "description": "Directory/file brute-forcing on HTTP",
    },
    "ffuf_scan": {
        "pre": ["http_confirmed"],
        "post": ["fuzz_results", "hidden_endpoints"],
        "cmd": "ffuf -u http://{target}:{http_port}/FUZZ -w /usr/share/wordlists/dirb/common.txt -mc 200,301,302,403 -s",
        "binary": "ffuf",
        "timeout": 120,
        "description": "Web fuzzing for hidden endpoints",
    },
    "sqlmap_scan": {
        "pre": ["http_confirmed", "directories"],
        "post": ["sqli_results", "db_access"],
        "cmd": "sqlmap -u http://{target}:{http_port}/ --batch --level=1 --risk=1 --smart",
        "binary": "sqlmap",
        "timeout": 180,
        "description": "SQL injection testing (requires discovered paths)",
    },
    "hydra_ssh": {
        "pre": ["ssh_confirmed"],
        "post": ["ssh_creds"],
        "cmd": "hydra -l admin -P /usr/share/wordlists/rockyou.txt ssh://{target} -t 4 -f",
        "binary": "hydra",
        "timeout": 120,
        "description": "SSH brute-force (only if SSH is confirmed)",
    },
    "hydra_ftp": {
        "pre": ["ftp_confirmed"],
        "post": ["ftp_creds"],
        "cmd": "hydra -l anonymous -P /usr/share/wordlists/rockyou.txt ftp://{target} -t 4 -f",
        "binary": "hydra",
        "timeout": 120,
        "description": "FTP brute-force (only if FTP is confirmed)",
    },
}


# ── Capability Auto-Detection from KG ─────────────────────────────────────────


def auto_detect_capabilities(kg: Any, target: str) -> List[str]:
    """Scan KG and set capability flags based on discovered data.

    This runs AFTER phase_ingest to populate capabilities from services.
    """
    capabilities = []

    services = kg.get_services_for_host(target)
    for svc in services.get("services", []):
        port = svc.get("port", 0)
        name = (svc.get("name", "") or "").lower()

        # Port/service based capabilities
        if port:
            capabilities.append("open_ports")

        if name in ("http", "https") or port in (80, 443, 8080, 8443):
            capabilities.append("http_confirmed")
            kg.set_capability("http_port", port)

        if name in ("ssh", "openssh") or port == 22:
            capabilities.append("ssh_confirmed")

        if name == "ftp" or port == 21:
            capabilities.append("ftp_confirmed")

        if name in ("mysql", "postgresql", "mssql") or port in (3306, 5432, 1433):
            capabilities.append("db_confirmed")

        if name in ("smb", "samba") or port == 445:
            capabilities.append("smb_confirmed")

    # Deduplicate and set
    for cap in set(capabilities):
        kg.set_capability(cap)

    # Check for existing data
    vulns = kg.get_vulnerabilities_for_host(target)
    if vulns.get("count", 0) > 0:
        kg.set_capability("cve_matches")

    return list(set(capabilities))


# ── Tool Scheduler ────────────────────────────────────────────────────────────


class ToolScheduler:
    """Deterministic tool execution based on dependency graph.

    Features:
      - Pre-condition checking: tool only runs when KG has required capabilities
      - Parallel execution: independent tools run simultaneously
      - Auto-skip: tools whose pre-conditions can't be met are skipped
      - Binary availability check: missing tools are skipped gracefully
      - Post-condition writing: completed tools set new capability flags

    Usage:
        scheduler = ToolScheduler(kg=self.kg, target="10.10.10.5")
        scheduler.check_available_tools()
        results = await scheduler.run()
    """

    def __init__(
        self,
        kg: Any,
        target: str,
        tdg: Optional[Dict] = None,
        log_fn: Optional[Callable] = None,
        max_parallel: int = 3,
    ):
        self.kg = kg
        self.target = target
        self.tdg = tdg or TOOL_DEPENDENCY_GRAPH
        self._log = log_fn or (lambda msg: logger.info(msg))
        self.max_parallel = max_parallel

        self.results: Dict[str, ToolResult] = {}
        self.execution_order: List[str] = []
        self._unavailable_tools: Set[str] = set()

    def check_available_tools(self) -> Dict[str, bool]:
        """Check which tools are installed on the system."""
        availability = {}
        for tool_name, spec in self.tdg.items():
            binary = spec.get("binary", "")
            if binary:
                available = shutil.which(binary) is not None
                availability[tool_name] = available
                if not available:
                    self._unavailable_tools.add(tool_name)
                    self._log(f"  ⚠️  {tool_name}: binary '{binary}' not found — will skip")
            else:
                availability[tool_name] = True

        installed = sum(1 for v in availability.values() if v)
        self._log(f"  Tool availability: {installed}/{len(availability)} installed")
        return availability

    def get_ready_tools(self) -> List[str]:
        """Get tools whose pre-conditions are ALL met and haven't run yet."""
        ready = []
        for tool_name, spec in self.tdg.items():
            # Skip already completed/failed/skipped
            if tool_name in self.results:
                continue

            # Skip unavailable tools
            if tool_name in self._unavailable_tools:
                continue

            # Check ALL pre-conditions
            pre = spec.get("pre", [])
            if all(self.kg.has_capability(p) for p in pre):
                ready.append(tool_name)

        return ready

    def get_blocked_tools(self) -> List[str]:
        """Get tools that are waiting on unmet pre-conditions."""
        blocked = []
        for tool_name, spec in self.tdg.items():
            if tool_name in self.results or tool_name in self._unavailable_tools:
                continue
            pre = spec.get("pre", [])
            missing = [p for p in pre if not self.kg.has_capability(p)]
            if missing:
                blocked.append(f"{tool_name} (waiting: {', '.join(missing)})")
        return blocked

    def get_skippable_tools(self) -> List[str]:
        """Get tools that can NEVER run (pre-conditions impossible).

        A tool is skippable if its pre-conditions depend on capabilities that
        no remaining tool can produce.
        """
        # Collect all capabilities that could still be produced
        produceable = set()
        for tool_name, spec in self.tdg.items():
            if tool_name not in self.results and tool_name not in self._unavailable_tools:
                produceable.update(spec.get("post", []))

        # Also include what's already in KG
        existing = set(self.kg.get_capabilities().keys())
        possible = produceable | existing

        skippable = []
        for tool_name, spec in self.tdg.items():
            if tool_name in self.results or tool_name in self._unavailable_tools:
                continue
            pre = spec.get("pre", [])
            if not all(p in possible for p in pre):
                skippable.append(tool_name)

        return skippable

    async def execute_tool(self, tool_name: str) -> ToolResult:
        """Execute a single tool and record results."""
        spec = self.tdg[tool_name]
        self._log(f"  🔄 RUNNING: {tool_name} — {spec.get('description', '')}")

        start = time.time()

        # Build command with target substitution
        http_port = self.kg._capabilities.get("http_port", 80)
        cmd = spec["cmd"].format(
            target=self.target,
            http_port=http_port,
        )

        try:
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                ),
                timeout=5,  # timeout for process creation only
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=spec.get("timeout", 120),
                )
                output = stdout.decode("utf-8", errors="replace")[:5000]
                duration = time.time() - start

                # Set post-conditions in KG
                for cap in spec.get("post", []):
                    self.kg.set_capability(cap)

                result = ToolResult(
                    tool=tool_name,
                    status=ToolStatus.COMPLETE,
                    duration=duration,
                    output=output,
                    capabilities_produced=spec.get("post", []),
                )

                self._log(f"  ✅ {tool_name}: completed in {duration:.1f}s, "
                          f"produced: {spec.get('post', [])}")

            except asyncio.TimeoutError:
                proc.kill()
                duration = time.time() - start
                result = ToolResult(
                    tool=tool_name,
                    status=ToolStatus.FAILED,
                    duration=duration,
                    error=f"Timeout after {spec.get('timeout', 120)}s",
                )
                self._log(f"  ❌ {tool_name}: timed out after {duration:.1f}s")

        except Exception as e:
            duration = time.time() - start
            result = ToolResult(
                tool=tool_name,
                status=ToolStatus.FAILED,
                duration=duration,
                error=str(e),
            )
            self._log(f"  ❌ {tool_name}: error — {e}")

        self.results[tool_name] = result
        self.execution_order.append(tool_name)
        return result

    async def run(self) -> Dict[str, ToolResult]:
        """Execute all tools respecting dependency graph.

        Algorithm:
          1. Check which tools are ready (pre-conditions met)
          2. Check which tools are permanently skippable
          3. Run ready tools in parallel (up to max_parallel)
          4. After each batch, re-check readiness (new capabilities may unlock tools)
          5. Repeat until no more tools can run
        """
        iteration = 0
        max_iterations = 10  # Safety limit

        self._log(f"\n  Tool Scheduler — {len(self.tdg)} tools in dependency graph")
        self._log(f"  KG capabilities: {list(self.kg.get_capabilities().keys())}")

        while iteration < max_iterations:
            iteration += 1

            # Skip permanently blocked tools
            for tool_name in self.get_skippable_tools():
                if tool_name not in self.results:
                    self.results[tool_name] = ToolResult(
                        tool=tool_name,
                        status=ToolStatus.SKIPPED,
                        error="Pre-conditions can never be met",
                    )
                    self._log(f"  ⏭️  {tool_name}: auto-skipped (impossible pre-conditions)")

            # Skip unavailable tools
            for tool_name in self._unavailable_tools:
                if tool_name not in self.results:
                    self.results[tool_name] = ToolResult(
                        tool=tool_name,
                        status=ToolStatus.SKIPPED,
                        error=f"Binary '{self.tdg[tool_name].get('binary', '?')}' not installed",
                    )

            # Find ready tools
            ready = self.get_ready_tools()
            if not ready:
                blocked = self.get_blocked_tools()
                if blocked:
                    self._log(f"  ⚠️  Remaining tools blocked: {blocked}")
                break

            self._log(f"\n  Iteration {iteration}: {len(ready)} tools ready → {ready}")

            # Run ready tools in parallel batches
            batch = ready[:self.max_parallel]
            tasks = [self.execute_tool(tool) for tool in batch]
            await asyncio.gather(*tasks, return_exceptions=True)

        return self.results

    def get_execution_log(self) -> str:
        """Human-readable execution summary."""
        lines = [f"Tool Execution Summary ({len(self.results)}/{len(self.tdg)} tools):"]

        for tool_name in self.execution_order:
            r = self.results[tool_name]
            lines.append(f"  {r.icon} {tool_name}: {r.status.value} "
                         f"({r.duration:.1f}s)" if r.duration else
                         f"  {r.icon} {tool_name}: {r.status.value}")

        # Show skipped tools
        for tool_name, r in self.results.items():
            if tool_name not in self.execution_order:
                reason = r.error or "skipped"
                lines.append(f"  {r.icon} {tool_name}: {r.status.value} ({reason})")

        completed = sum(1 for r in self.results.values() if r.status == ToolStatus.COMPLETE)
        failed = sum(1 for r in self.results.values() if r.status == ToolStatus.FAILED)
        skipped = sum(1 for r in self.results.values() if r.status == ToolStatus.SKIPPED)

        lines.append(f"  ───")
        lines.append(f"  Complete: {completed}, Failed: {failed}, Skipped: {skipped}")
        lines.append(f"  Capabilities: {list(self.kg.get_capabilities().keys())}")

        return "\n".join(lines)

    def get_produced_capabilities(self) -> Set[str]:
        """Get all capabilities produced by completed tools."""
        caps = set()
        for r in self.results.values():
            if r.status == ToolStatus.COMPLETE:
                caps.update(r.capabilities_produced)
        return caps
