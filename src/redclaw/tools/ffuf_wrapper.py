"""
FfufWrapper — Minimal ffuf web fuzzer wrapper.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from typing import Any, Optional

from .output_cleaner import OutputCleaner, CleanedOutput
from .nmap_wrapper import ToolSchema

logger = logging.getLogger("redclaw.tools.ffuf")


class FfufWrapper:
    """
    Ffuf wrapper for web fuzzing.

    Usage:
        ffuf = FfufWrapper()
        result = await ffuf.execute("ffuf_scan", {"url": "http://10.10.10.5/FUZZ", "wordlist": "/usr/share/wordlists/dirb/common.txt"})
    """

    def __init__(self, cleaner: Optional[OutputCleaner] = None, timeout: int = 600):
        self._cleaner = cleaner or OutputCleaner()
        self._timeout = timeout
        self._binary = shutil.which("ffuf")

    def get_tools(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="ffuf_scan",
                description="Run ffuf web fuzzer on a target URL. Use FUZZ keyword for injection point. Returns discovered endpoints.",
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Target URL with FUZZ keyword (e.g., http://10.10.10.5/FUZZ)"},
                        "wordlist": {
                            "type": "string",
                            "description": "Path to wordlist file",
                            "default": "/usr/share/wordlists/dirb/common.txt",
                        },
                        "flags": {
                            "type": "string",
                            "description": "Additional ffuf flags (e.g., -mc 200,301 -fs 0)",
                            "default": "-mc all -fc 404",
                        },
                    },
                    "required": ["url"],
                },
            ),
        ]

    async def execute(self, name: str, params: dict[str, Any]) -> CleanedOutput:
        url = params.get("url", "")
        wordlist = params.get("wordlist", "/usr/share/wordlists/dirb/common.txt")
        flags = params.get("flags", "-mc all -fc 404")

        if not self._binary:
            return CleanedOutput(
                tool="ffuf", success=False,
                summary="ffuf not found in PATH.",
                structured={}, raw_length=0, cleaned_length=0,
            )

        cmd = f"{self._binary} -u {url} -w {wordlist} {flags} -s"
        logger.info(f"Running: {cmd}")

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
            output = stdout.decode("utf-8", errors="replace")
            return self._cleaner.clean("ffuf", output, success=(proc.returncode == 0))
        except asyncio.TimeoutError:
            return CleanedOutput(
                tool="ffuf", success=False,
                summary=f"ffuf timed out after {self._timeout}s",
                structured={}, raw_length=0, cleaned_length=0,
            )
        except Exception as e:
            return CleanedOutput(
                tool="ffuf", success=False,
                summary=f"ffuf failed: {e}",
                structured={}, raw_length=0, cleaned_length=0,
            )
