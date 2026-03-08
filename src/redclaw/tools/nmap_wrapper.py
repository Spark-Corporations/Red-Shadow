"""
NmapWrapper — Minimal nmap wrapper with OutputCleaner integration.

Runs nmap via subprocess, parses output through OutputCleaner,
returns structured results. Exposes function-calling schema for the LLM.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import dataclass
from typing import Any, Optional

from .output_cleaner import OutputCleaner, CleanedOutput

logger = logging.getLogger("redclaw.tools.nmap")


@dataclass
class ToolSchema:
    """OpenAI function-calling tool schema."""
    name: str
    description: str
    parameters: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class NmapWrapper:
    """
    Minimal nmap wrapper.

    Usage:
        nmap = NmapWrapper()
        result = await nmap.scan("10.10.10.5", flags="-sV -sC")
    """

    def __init__(self, cleaner: Optional[OutputCleaner] = None, timeout: int = 300):
        self._cleaner = cleaner or OutputCleaner()
        self._timeout = timeout
        self._binary = shutil.which("nmap")

    def get_tools(self) -> list[ToolSchema]:
        """Return function-calling schemas."""
        return [
            ToolSchema(
                name="nmap_scan",
                description="Run an nmap scan on a target. Returns structured port/service data.",
                parameters={
                    "type": "object",
                    "properties": {
                        "target": {"type": "string", "description": "Target IP, hostname, or CIDR range"},
                        "flags": {
                            "type": "string",
                            "description": "Nmap flags (default: -sV -sC -O). Examples: -sV -sC, -p-, -sU",
                            "default": "-sV -sC -O",
                        },
                    },
                    "required": ["target"],
                },
            ),
        ]

    async def execute(self, name: str, params: dict[str, Any]) -> CleanedOutput:
        """Execute an nmap scan and return cleaned structured output."""
        target = params.get("target", "")
        flags = params.get("flags", "-sV -sC -O")

        if not self._binary:
            return CleanedOutput(
                tool="nmap", success=False,
                summary="nmap not found in PATH. Install nmap first.",
                structured={}, raw_length=0, cleaned_length=0,
                warnings=["nmap binary not found"],
            )

        cmd = f"{self._binary} {flags} {target}"
        logger.info(f"Running: {cmd}")

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout
            )
            output = stdout.decode("utf-8", errors="replace")
            if stderr:
                output += "\n[STDERR]\n" + stderr.decode("utf-8", errors="replace")

            return self._cleaner.clean("nmap", output, success=(proc.returncode == 0))

        except asyncio.TimeoutError:
            return CleanedOutput(
                tool="nmap", success=False,
                summary=f"nmap scan timed out after {self._timeout}s",
                structured={}, raw_length=0, cleaned_length=0,
                warnings=["timeout"],
            )
        except Exception as e:
            return CleanedOutput(
                tool="nmap", success=False,
                summary=f"nmap failed: {e}",
                structured={}, raw_length=0, cleaned_length=0,
                warnings=[str(e)],
            )
