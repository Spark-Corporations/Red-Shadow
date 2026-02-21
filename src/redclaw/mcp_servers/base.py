"""
BaseMCPServer — Common base class for all RedClaw MCP tool servers.

Each MCP server wraps a specific pentesting tool (nmap, metasploit, etc.) and provides:
  - Tool schema definition (OpenAI function-calling format)
  - Command building from structured parameters
  - Execution via SessionManager
  - Output parsing into structured results
  - Error handling and timeout management
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("redclaw.mcp_servers.base")


@dataclass
class ToolSchema:
    """Tool schema in OpenAI function-calling format."""
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolResult:
    """Structured result from a tool execution."""
    tool: str
    success: bool
    raw_output: str
    parsed_data: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    duration: float = 0.0
    command_executed: str = ""

    def to_context_string(self) -> str:
        """Format for inclusion in LLM context."""
        if not self.success:
            return f"[{self.tool}] ERROR: {self.error}"
        if self.parsed_data:
            return f"[{self.tool}] Results:\n{json.dumps(self.parsed_data, indent=2)}"
        return f"[{self.tool}] Output:\n{self.raw_output[:4000]}"


class BaseMCPServer(ABC):
    """
    Abstract base class for MCP tool servers.

    Subclasses implement:
      - get_tools(): return list of ToolSchema definitions
      - build_command(): construct the CLI command from parameters
      - parse_output(): parse raw output into structured data
    """

    def __init__(self, session_manager=None, name: str = "base"):
        self._session = session_manager
        self._name = name
        self._execution_count = 0
        self._total_duration = 0.0
        logger.info(f"MCP Server '{name}' initialized")

    @property
    def name(self) -> str:
        return self._name

    @abstractmethod
    def get_tools(self) -> list[ToolSchema]:
        """Return the tool schemas this server provides."""
        ...

    @abstractmethod
    def build_command(self, tool_name: str, **params) -> str:
        """Build the CLI command from structured parameters."""
        ...

    @abstractmethod
    def parse_output(self, tool_name: str, raw_output: str) -> dict[str, Any]:
        """Parse raw tool output into structured data."""
        ...

    async def execute_tool(
        self,
        command: str = "",
        target: str = "",
        options: Optional[dict[str, Any]] = None,
        timeout: int = 300,
        tool_name: str = "",
    ) -> ToolResult:
        """
        Execute a tool command via the session manager.

        Args:
            command: Pre-built command string, OR parameters for build_command
            target: Target IP/hostname/URL
            options: Additional tool-specific options
            timeout: Execution timeout in seconds
            tool_name: Specific tool name (if server provides multiple)
        """
        start = time.monotonic()
        options = options or {}

        # Build command if not provided directly
        if not command and tool_name:
            command = self.build_command(tool_name, target=target, **options)
        elif not command:
            command = self.build_command(self._name, target=target, **options)

        # Execute
        try:
            if self._session:
                result = await self._session.execute_local(command, timeout=timeout)
                raw_output = result.output
                success = result.success
                error = result.stderr if not success else None
            else:
                # No session manager — execute directly via subprocess
                try:
                    proc = await asyncio.create_subprocess_shell(
                        command,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout_data, stderr_data = await asyncio.wait_for(
                        proc.communicate(), timeout=timeout
                    )
                    raw_output = stdout_data.decode("utf-8", errors="replace")
                    err_output = stderr_data.decode("utf-8", errors="replace")
                    success = proc.returncode == 0
                    error = err_output if (not success and err_output) else None

                    if err_output and not success:
                        raw_output = f"{raw_output}\n[STDERR]:\n{err_output}"

                except asyncio.TimeoutError:
                    raw_output = ""
                    success = False
                    error = f"Command timed out after {timeout}s"
                except Exception as e:
                    raw_output = ""
                    success = False
                    error = f"Execution error: {type(e).__name__}: {e}"

            # Parse output
            parsed = {}
            if success:
                try:
                    parsed = self.parse_output(tool_name or self._name, raw_output)
                except Exception as e:
                    logger.warning(f"Output parsing failed for {self._name}: {e}")
                    parsed = {"raw": raw_output}

        except Exception as e:
            raw_output = ""
            success = False
            error = str(e)
            parsed = {}

        duration = time.monotonic() - start
        self._execution_count += 1
        self._total_duration += duration

        return ToolResult(
            tool=self._name,
            success=success,
            raw_output=raw_output,
            parsed_data=parsed,
            error=error,
            duration=duration,
            command_executed=command,
        )

    def get_stats(self) -> dict[str, Any]:
        return {
            "name": self._name,
            "executions": self._execution_count,
            "total_duration": f"{self._total_duration:.2f}s",
        }
