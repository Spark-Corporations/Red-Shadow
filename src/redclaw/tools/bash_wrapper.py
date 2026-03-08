"""
BashWrapper — Generic command execution wrapper with OutputCleaner.

This is the fallback: any tool not covered by a specific wrapper
goes through bash execution. The LLM can run arbitrary commands
(after GuardianRails validation) through this wrapper.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from .output_cleaner import OutputCleaner, CleanedOutput
from .nmap_wrapper import ToolSchema

logger = logging.getLogger("redclaw.tools.bash")


class BashWrapper:
    """
    Generic bash command executor with OutputCleaner.

    Any pentesting tool not covered by a specific wrapper (like metasploit,
    hydra, john, hashcat, etc.) can be run through this wrapper.

    Usage:
        bash = BashWrapper()
        result = await bash.execute("exec_command", {"command": "curl -s http://target/"})
    """

    def __init__(self, cleaner: Optional[OutputCleaner] = None, timeout: int = 300):
        self._cleaner = cleaner or OutputCleaner()
        self._timeout = timeout

    def get_tools(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="exec_command",
                description=(
                    "Execute a shell command and return parsed output. "
                    "Use for any tool not covered by specialized wrappers "
                    "(metasploit, hydra, john, hashcat, curl, wget, etc.). "
                    "Commands are validated by GuardianRails before execution."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Shell command to execute",
                        },
                        "cwd": {
                            "type": "string",
                            "description": "Working directory (optional)",
                            "default": "/tmp",
                        },
                    },
                    "required": ["command"],
                },
            ),
            ToolSchema(
                name="read_file",
                description="Read content from a file on disk.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute file path to read"},
                        "max_lines": {
                            "type": "integer",
                            "description": "Max lines to read (default: 200)",
                            "default": 200,
                        },
                    },
                    "required": ["path"],
                },
            ),
            ToolSchema(
                name="write_file",
                description="Write content to a file on disk (for saving exploits, scripts, etc.).",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path to write to"},
                        "content": {"type": "string", "description": "Content to write"},
                    },
                    "required": ["path", "content"],
                },
            ),
            ToolSchema(
                name="save_finding",
                description="Record a vulnerability or interesting finding from the pentest.",
                parameters={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Finding title (e.g., 'Anonymous FTP Access')"},
                        "severity": {
                            "type": "string",
                            "description": "Severity level: critical, high, medium, low, info",
                        },
                        "description": {"type": "string", "description": "Detailed description"},
                        "evidence": {"type": "string", "description": "Evidence/proof (command output, etc.)"},
                    },
                    "required": ["title", "severity", "description"],
                },
            ),
        ]

    async def execute(self, name: str, params: dict[str, Any]) -> CleanedOutput:
        """Execute a tool call by name."""
        if name == "exec_command":
            return await self._exec_command(params)
        elif name == "read_file":
            return await self._read_file(params)
        elif name == "write_file":
            return await self._write_file(params)
        elif name == "save_finding":
            return self._save_finding(params)
        else:
            return CleanedOutput(
                tool="bash", success=False,
                summary=f"Unknown tool: {name}",
                structured={}, raw_length=0, cleaned_length=0,
            )

    async def _exec_command(self, params: dict[str, Any]) -> CleanedOutput:
        command = params.get("command", "")
        cwd = params.get("cwd", "/tmp")

        if not command:
            return CleanedOutput(
                tool="bash", success=False,
                summary="No command provided",
                structured={}, raw_length=0, cleaned_length=0,
            )

        logger.info(f"Running: {command}")

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout
            )
            output = stdout.decode("utf-8", errors="replace")
            if stderr:
                err = stderr.decode("utf-8", errors="replace")
                output += f"\n[STDERR]\n{err}"

            # Try to detect the tool name from the command
            tool_name = command.split()[0].split("/")[-1] if command else "bash"
            return self._cleaner.clean(tool_name, output, success=(proc.returncode == 0))

        except asyncio.TimeoutError:
            return CleanedOutput(
                tool="bash", success=False,
                summary=f"Command timed out after {self._timeout}s: {command[:100]}",
                structured={}, raw_length=0, cleaned_length=0,
            )
        except Exception as e:
            return CleanedOutput(
                tool="bash", success=False,
                summary=f"Command failed: {e}",
                structured={}, raw_length=0, cleaned_length=0,
            )

    async def _read_file(self, params: dict[str, Any]) -> CleanedOutput:
        path = params.get("path", "")
        max_lines = params.get("max_lines", 200)

        try:
            with open(path, "r", errors="replace") as f:
                lines = f.readlines()

            total = len(lines)
            content = "".join(lines[:max_lines])
            if total > max_lines:
                content += f"\n... [{total - max_lines} more lines]"

            return CleanedOutput(
                tool="read_file", success=True,
                summary=f"Read {min(total, max_lines)}/{total} lines from {path}",
                structured={"content": content},
                raw_length=len(content), cleaned_length=len(content),
            )
        except Exception as e:
            return CleanedOutput(
                tool="read_file", success=False,
                summary=f"Failed to read {path}: {e}",
                structured={}, raw_length=0, cleaned_length=0,
            )

    async def _write_file(self, params: dict[str, Any]) -> CleanedOutput:
        path = params.get("path", "")
        content = params.get("content", "")

        try:
            with open(path, "w") as f:
                f.write(content)

            return CleanedOutput(
                tool="write_file", success=True,
                summary=f"Wrote {len(content)} chars to {path}",
                structured={"path": path, "size": len(content)},
                raw_length=len(content), cleaned_length=50,
            )
        except Exception as e:
            return CleanedOutput(
                tool="write_file", success=False,
                summary=f"Failed to write {path}: {e}",
                structured={}, raw_length=0, cleaned_length=0,
            )

    def _save_finding(self, params: dict[str, Any]) -> CleanedOutput:
        """Store a finding (for now just log it — MemAgent handles persistence)."""
        title = params.get("title", "Unknown")
        severity = params.get("severity", "info")
        description = params.get("description", "")

        logger.info(f"Finding saved: [{severity}] {title}")

        return CleanedOutput(
            tool="save_finding", success=True,
            summary=f"Finding recorded: [{severity.upper()}] {title}",
            structured={
                "title": title,
                "severity": severity,
                "description": description,
                "evidence": params.get("evidence", ""),
            },
            raw_length=len(description), cleaned_length=100,
        )
