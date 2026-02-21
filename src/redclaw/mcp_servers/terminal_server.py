"""
TerminalServer — Run arbitrary shell commands on local or remote sessions.

This is the MOST CRITICAL tool for autonomous agent behavior.
Without this, the agent can only use pre-wrapped tools (nmap, nuclei, etc.).
With this, the agent can run ANY command — just like Claude Code does.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import shlex
from typing import Any, Optional

from .base import BaseMCPServer, ToolSchema

logger = logging.getLogger("redclaw.mcp_servers.terminal")


class TerminalServer(BaseMCPServer):
    """MCP server for executing arbitrary shell commands."""

    def __init__(self, session_manager=None):
        super().__init__(session_manager, name="terminal")

    def get_tools(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="run_terminal_command",
                description=(
                    "Execute a shell command on the local or remote session. "
                    "Use this for any command not covered by specialized tools. "
                    "Examples: whoami, cat /etc/passwd, curl, wget, python scripts, etc."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The bash command to execute",
                        },
                        "session": {
                            "type": "string",
                            "enum": ["local", "remote"],
                            "description": "Which session to run in (local=your machine, remote=target)",
                            "default": "local",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Max execution time in seconds (default: 60)",
                            "default": 60,
                        },
                    },
                    "required": ["command"],
                },
            ),
        ]

    def build_command(self, tool_name: str = "run_terminal_command", **params) -> str:
        command = params.get("command", "")
        if not command:
            raise ValueError("run_terminal_command requires a command")
        return command

    def parse_output(self, tool_name: str, raw_output: str) -> dict[str, Any]:
        """Terminal output is already text — just return it."""
        lines = raw_output.strip().split("\n")
        return {
            "output": raw_output.strip(),
            "line_count": len(lines),
        }

    async def execute_tool(
        self,
        command: str = "",
        target: str = "",
        options: Optional[dict[str, Any]] = None,
        timeout: int = 60,
        tool_name: str = "",
    ):
        """Execute the command directly via subprocess if no session manager."""
        options = options or {}
        session = options.get("session", "local")
        timeout = options.get("timeout", timeout)

        if not command and options.get("command"):
            command = options["command"]

        if not command:
            from .base import ToolResult
            return ToolResult(
                tool="terminal",
                success=False,
                raw_output="",
                error="No command provided",
            )

        # If we have a session manager, use it
        if self._session:
            return await super().execute_tool(
                command=command, target=target, options=options,
                timeout=timeout, tool_name=tool_name,
            )

        # Direct execution via subprocess (local session)
        from .base import ToolResult
        import time
        start = time.monotonic()

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            raw_output = stdout.decode("utf-8", errors="replace")
            err_output = stderr.decode("utf-8", errors="replace")
            success = proc.returncode == 0

            if err_output and not success:
                raw_output = f"{raw_output}\n[STDERR]:\n{err_output}"

            duration = time.monotonic() - start
            return ToolResult(
                tool="terminal",
                success=success,
                raw_output=raw_output,
                parsed_data=self.parse_output(tool_name, raw_output),
                error=err_output if not success else None,
                duration=duration,
                command_executed=command,
            )

        except asyncio.TimeoutError:
            duration = time.monotonic() - start
            return ToolResult(
                tool="terminal",
                success=False,
                raw_output="",
                error=f"Command timed out after {timeout}s",
                duration=duration,
                command_executed=command,
            )
        except Exception as e:
            duration = time.monotonic() - start
            return ToolResult(
                tool="terminal",
                success=False,
                raw_output="",
                error=f"Execution error: {type(e).__name__}: {e}",
                duration=duration,
                command_executed=command,
            )
