"""
FileServer — Read and write files on local or remote sessions.

Essential for: reading config files, writing exploit payloads, examining logs,
downloading results, reading /etc/passwd, etc.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Optional

from .base import BaseMCPServer, ToolSchema, ToolResult

logger = logging.getLogger("redclaw.mcp_servers.file_server")


class FileServer(BaseMCPServer):
    """MCP server for file read/write operations."""

    def __init__(self, session_manager=None):
        super().__init__(session_manager, name="file_ops")

    def get_tools(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="read_file",
                description=(
                    "Read the contents of a file on the local or remote session. "
                    "Use for: /etc/passwd, config files, logs, source code, etc."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Absolute path to the file",
                        },
                        "session": {
                            "type": "string",
                            "enum": ["local", "remote"],
                            "description": "Which session to read from",
                            "default": "local",
                        },
                        "max_lines": {
                            "type": "integer",
                            "description": "Maximum number of lines to return (default: 500)",
                            "default": 500,
                        },
                    },
                    "required": ["path"],
                },
            ),
            ToolSchema(
                name="write_file",
                description=(
                    "Write content to a file on the local or remote session. "
                    "Use for: creating exploit scripts, config files, payloads, reports."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Absolute path where the file will be written",
                        },
                        "content": {
                            "type": "string",
                            "description": "Content to write to the file",
                        },
                        "session": {
                            "type": "string",
                            "enum": ["local", "remote"],
                            "description": "Which session to write on",
                            "default": "local",
                        },
                    },
                    "required": ["path", "content"],
                },
            ),
        ]

    def build_command(self, tool_name: str, **params) -> str:
        path = params.get("path", "")
        if tool_name == "read_file":
            return f"cat {path}"
        elif tool_name == "write_file":
            content = params.get("content", "")
            # Use heredoc for multi-line content
            return f"cat << 'REDCLAW_EOF' > {path}\n{content}\nREDCLAW_EOF"
        return ""

    def parse_output(self, tool_name: str, raw_output: str) -> dict[str, Any]:
        lines = raw_output.strip().split("\n")
        return {
            "content": raw_output.strip(),
            "line_count": len(lines),
        }

    async def execute_tool(
        self,
        command: str = "",
        target: str = "",
        options: Optional[dict[str, Any]] = None,
        timeout: int = 30,
        tool_name: str = "",
    ) -> ToolResult:
        """Execute file operations — direct filesystem access for local."""
        options = options or {}
        start = time.monotonic()
        session = options.get("session", "local")
        path = options.get("path", target)

        # If we have a session manager (especially for remote), use it
        if self._session and session == "remote":
            return await super().execute_tool(
                command=self.build_command(tool_name, **options),
                target=target,
                options=options,
                timeout=timeout,
                tool_name=tool_name,
            )

        try:
            if tool_name == "read_file":
                return self._read_file_local(path, options, start)
            elif tool_name == "write_file":
                return self._write_file_local(path, options, start)
            else:
                return ToolResult(
                    tool="file_ops", success=False, raw_output="",
                    error=f"Unknown file tool: {tool_name}",
                    duration=time.monotonic() - start,
                )
        except Exception as e:
            return ToolResult(
                tool="file_ops", success=False, raw_output="",
                error=f"File operation error: {type(e).__name__}: {e}",
                duration=time.monotonic() - start,
            )

    def _read_file_local(self, path: str, options: dict, start: float) -> ToolResult:
        """Read a file from the local filesystem."""
        max_lines = options.get("max_lines", 500)

        try:
            file_path = Path(path)
            if not file_path.exists():
                return ToolResult(
                    tool="file_ops", success=False, raw_output="",
                    error=f"File not found: {path}",
                    duration=time.monotonic() - start,
                )

            content = file_path.read_text(encoding="utf-8", errors="replace")
            lines = content.split("\n")

            if len(lines) > max_lines:
                truncated = "\n".join(lines[:max_lines])
                content = f"{truncated}\n\n[TRUNCATED: {len(lines)} total lines, showing first {max_lines}]"

            return ToolResult(
                tool="file_ops",
                success=True,
                raw_output=content,
                parsed_data={"path": path, "line_count": len(lines), "size_bytes": file_path.stat().st_size},
                duration=time.monotonic() - start,
                command_executed=f"read_file({path})",
            )
        except PermissionError:
            return ToolResult(
                tool="file_ops", success=False, raw_output="",
                error=f"Permission denied: {path}",
                duration=time.monotonic() - start,
            )

    def _write_file_local(self, path: str, options: dict, start: float) -> ToolResult:
        """Write content to a local file."""
        content = options.get("content", "")

        try:
            file_path = Path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")

            return ToolResult(
                tool="file_ops",
                success=True,
                raw_output=f"File written: {path} ({len(content)} bytes)",
                parsed_data={"path": path, "size_bytes": len(content)},
                duration=time.monotonic() - start,
                command_executed=f"write_file({path})",
            )
        except PermissionError:
            return ToolResult(
                tool="file_ops", success=False, raw_output="",
                error=f"Permission denied: {path}",
                duration=time.monotonic() - start,
            )
