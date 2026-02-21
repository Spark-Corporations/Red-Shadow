"""
AgentControlServer — Agent lifecycle tools: user approval, session switching, findings, memory.

These tools give the agent self-awareness and human-in-the-loop capabilities:
  - request_user_approval: Pause and ask user before high-risk operations
  - switch_session: Toggle between local and remote shells
  - save_finding: Record pentest findings with CVSS severity
  - update_memory: Store key/value pairs in agent memory
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

from .base import BaseMCPServer, ToolSchema, ToolResult

logger = logging.getLogger("redclaw.mcp_servers.agent_control")


class AgentControlServer(BaseMCPServer):
    """MCP server for agent lifecycle and control operations."""

    def __init__(self, session_manager=None):
        super().__init__(session_manager, name="agent_control")
        self._findings: list[dict[str, Any]] = []
        self._memory: dict[str, str] = {}
        self._active_session: str = "local"
        self._pending_approval: Optional[dict[str, Any]] = None

    def get_tools(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="request_user_approval",
                description=(
                    "Request explicit user approval before executing a high-risk action. "
                    "MUST be called before: exploit execution, privilege escalation, "
                    "lateral movement, data exfiltration. The agent will PAUSE until "
                    "the user approves or denies."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "description": "What action you want to execute",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Why this action is necessary",
                        },
                        "risk_level": {
                            "type": "string",
                            "enum": ["low", "medium", "high", "critical"],
                            "description": "Risk level of the action",
                        },
                    },
                    "required": ["action", "reason", "risk_level"],
                },
            ),
            ToolSchema(
                name="switch_session",
                description=(
                    "Switch between local and remote shell sessions. "
                    "Use 'remote' after establishing a reverse shell or SSH connection."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "session": {
                            "type": "string",
                            "enum": ["local", "remote"],
                            "description": "Session to switch to",
                        },
                    },
                    "required": ["session"],
                },
            ),
            ToolSchema(
                name="save_finding",
                description=(
                    "Save a security finding to the pentest report. "
                    "Call this whenever you discover a vulnerability, misconfiguration, "
                    "or security issue."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Finding title (e.g., 'Apache 2.4.49 RCE - CVE-2021-41773')",
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["critical", "high", "medium", "low", "info"],
                            "description": "CVSS severity rating",
                        },
                        "description": {
                            "type": "string",
                            "description": "Detailed description of the finding",
                        },
                        "cve": {
                            "type": "string",
                            "description": "CVE identifier if applicable",
                        },
                        "proof": {
                            "type": "string",
                            "description": "Evidence/proof of the vulnerability",
                        },
                    },
                    "required": ["title", "severity", "description"],
                },
            ),
            ToolSchema(
                name="update_memory",
                description=(
                    "Store a key-value pair in agent memory for later reference. "
                    "Use this to remember: discovered credentials, open ports, "
                    "service versions, attack paths, etc."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "key": {
                            "type": "string",
                            "description": "Memory key (e.g., 'target_os', 'admin_password')",
                        },
                        "value": {
                            "type": "string",
                            "description": "Value to store",
                        },
                    },
                    "required": ["key", "value"],
                },
            ),
        ]

    def build_command(self, tool_name: str, **params) -> str:
        """Agent control tools don't build shell commands."""
        return ""

    def parse_output(self, tool_name: str, raw_output: str) -> dict[str, Any]:
        return {"output": raw_output}

    async def execute_tool(
        self,
        command: str = "",
        target: str = "",
        options: Optional[dict[str, Any]] = None,
        timeout: int = 30,
        tool_name: str = "",
    ) -> ToolResult:
        """Route to the appropriate handler based on the tool name."""
        options = options or {}
        start = time.monotonic()

        try:
            if tool_name == "request_user_approval":
                return await self._handle_approval(options, start)
            elif tool_name == "switch_session":
                return self._handle_switch_session(options, start)
            elif tool_name == "save_finding":
                return self._handle_save_finding(options, start)
            elif tool_name == "update_memory":
                return self._handle_update_memory(options, start)
            else:
                return ToolResult(
                    tool="agent_control",
                    success=False,
                    raw_output="",
                    error=f"Unknown agent control tool: {tool_name}",
                    duration=time.monotonic() - start,
                )
        except Exception as e:
            return ToolResult(
                tool="agent_control",
                success=False,
                raw_output="",
                error=f"Agent control error: {type(e).__name__}: {e}",
                duration=time.monotonic() - start,
            )

    async def _handle_approval(self, options: dict, start: float) -> ToolResult:
        """Request user approval — pauses execution until user responds."""
        action = options.get("action", "Unknown action")
        reason = options.get("reason", "No reason given")
        risk = options.get("risk_level", "medium")

        # Store pending approval
        self._pending_approval = {
            "action": action,
            "reason": reason,
            "risk_level": risk,
            "timestamp": time.time(),
        }

        # Interactive approval via terminal
        risk_icon = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}.get(risk, "⚪")

        prompt_text = (
            f"\n{risk_icon} APPROVAL REQUIRED [{risk.upper()}]\n"
            f"  Action: {action}\n"
            f"  Reason: {reason}\n"
            f"  Approve? [Y/n]: "
        )

        try:
            user_response = input(prompt_text).strip().lower()
            approved = user_response in ("", "y", "yes", "evet", "e")
        except (EOFError, KeyboardInterrupt):
            approved = False

        self._pending_approval = None

        return ToolResult(
            tool="agent_control",
            success=True,
            raw_output="APPROVED" if approved else "DENIED",
            parsed_data={"approved": approved, "action": action, "risk_level": risk},
            duration=time.monotonic() - start,
        )

    def _handle_switch_session(self, options: dict, start: float) -> ToolResult:
        """Switch active session."""
        session = options.get("session", "local")
        old = self._active_session
        self._active_session = session

        return ToolResult(
            tool="agent_control",
            success=True,
            raw_output=f"Session switched: {old} → {session}",
            parsed_data={"active_session": session, "previous": old},
            duration=time.monotonic() - start,
        )

    def _handle_save_finding(self, options: dict, start: float) -> ToolResult:
        """Save a finding to the report."""
        finding = {
            "title": options.get("title", ""),
            "severity": options.get("severity", "info"),
            "description": options.get("description", ""),
            "cve": options.get("cve", ""),
            "proof": options.get("proof", ""),
            "timestamp": time.time(),
        }
        self._findings.append(finding)

        # Also persist to disk
        findings_dir = Path.home() / ".redclaw" / "findings"
        findings_dir.mkdir(parents=True, exist_ok=True)
        findings_file = findings_dir / "findings.json"

        try:
            existing = json.loads(findings_file.read_text()) if findings_file.exists() else []
            existing.append(finding)
            findings_file.write_text(json.dumps(existing, indent=2))
        except Exception as e:
            logger.warning(f"Failed to persist finding: {e}")

        return ToolResult(
            tool="agent_control",
            success=True,
            raw_output=f"Finding saved: [{finding['severity'].upper()}] {finding['title']}",
            parsed_data={"finding_id": len(self._findings), "total_findings": len(self._findings)},
            duration=time.monotonic() - start,
        )

    def _handle_update_memory(self, options: dict, start: float) -> ToolResult:
        """Store a key-value pair in agent memory."""
        key = options.get("key", "")
        value = options.get("value", "")
        self._memory[key] = value

        return ToolResult(
            tool="agent_control",
            success=True,
            raw_output=f"Memory updated: {key} = {value[:100]}",
            parsed_data={"key": key, "total_entries": len(self._memory)},
            duration=time.monotonic() - start,
        )

    @property
    def findings(self) -> list[dict[str, Any]]:
        return self._findings

    @property
    def memory(self) -> dict[str, str]:
        return self._memory

    @property
    def active_session(self) -> str:
        return self._active_session
