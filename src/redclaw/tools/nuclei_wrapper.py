"""
NucleiWrapper — Minimal nuclei vulnerability scanner wrapper.

Runs nuclei via subprocess, parses structured findings.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from typing import Any, Optional

from .output_cleaner import OutputCleaner, CleanedOutput
from .nmap_wrapper import ToolSchema

logger = logging.getLogger("redclaw.tools.nuclei")


class NucleiWrapper:
    """
    Nuclei vulnerability scanner wrapper.

    Usage:
        nuclei = NucleiWrapper()
        result = await nuclei.execute("nuclei_scan", {"target": "http://10.10.10.5"})
    """

    def __init__(self, cleaner: Optional[OutputCleaner] = None, timeout: int = 600):
        self._cleaner = cleaner or OutputCleaner()
        self._timeout = timeout
        self._binary = shutil.which("nuclei")

    def get_tools(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="nuclei_scan",
                description="Run nuclei vulnerability scanner on a target URL. Returns structured vulnerability findings.",
                parameters={
                    "type": "object",
                    "properties": {
                        "target": {"type": "string", "description": "Target URL (e.g., http://10.10.10.5)"},
                        "severity": {
                            "type": "string",
                            "description": "Severity filter: critical,high,medium,low",
                            "default": "critical,high,medium",
                        },
                        "tags": {
                            "type": "string",
                            "description": "Template tags to filter (e.g., cve,rce,sqli)",
                            "default": "",
                        },
                    },
                    "required": ["target"],
                },
            ),
        ]

    async def execute(self, name: str, params: dict[str, Any]) -> CleanedOutput:
        target = params.get("target", "")
        severity = params.get("severity", "critical,high,medium")
        tags = params.get("tags", "")

        if not self._binary:
            return CleanedOutput(
                tool="nuclei", success=False,
                summary="nuclei not found in PATH.",
                structured={}, raw_length=0, cleaned_length=0,
            )

        cmd = f"{self._binary} -u {target} -severity {severity} -no-color"
        if tags:
            cmd += f" -tags {tags}"

        logger.info(f"Running: {cmd}")

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
            output = stdout.decode("utf-8", errors="replace")
            return self._cleaner.clean("nuclei", output, success=(proc.returncode == 0))
        except asyncio.TimeoutError:
            return CleanedOutput(
                tool="nuclei", success=False,
                summary=f"nuclei scan timed out after {self._timeout}s",
                structured={}, raw_length=0, cleaned_length=0,
            )
        except Exception as e:
            return CleanedOutput(
                tool="nuclei", success=False,
                summary=f"nuclei failed: {e}",
                structured={}, raw_length=0, cleaned_length=0,
            )
