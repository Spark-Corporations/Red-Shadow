"""
GobusterWrapper — Minimal gobuster directory/DNS bruteforcing wrapper.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from typing import Any, Optional

from .output_cleaner import OutputCleaner, CleanedOutput
from .nmap_wrapper import ToolSchema

logger = logging.getLogger("redclaw.tools.gobuster")


class GobusterWrapper:
    """
    Gobuster wrapper for directory/DNS bruteforcing.

    Usage:
        gb = GobusterWrapper()
        result = await gb.execute("gobuster_scan", {"url": "http://10.10.10.5", "wordlist": "/usr/share/wordlists/dirb/common.txt"})
    """

    def __init__(self, cleaner: Optional[OutputCleaner] = None, timeout: int = 600):
        self._cleaner = cleaner or OutputCleaner()
        self._timeout = timeout
        self._binary = shutil.which("gobuster")

    def get_tools(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="gobuster_scan",
                description="Run gobuster directory bruteforce on a target URL. Returns discovered paths.",
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Target URL (e.g., http://10.10.10.5)"},
                        "wordlist": {
                            "type": "string",
                            "description": "Path to wordlist file",
                            "default": "/usr/share/wordlists/dirb/common.txt",
                        },
                        "mode": {
                            "type": "string",
                            "description": "Gobuster mode: dir, dns, vhost, fuzz",
                            "default": "dir",
                        },
                        "extensions": {
                            "type": "string",
                            "description": "File extensions to search (e.g., php,html,txt)",
                            "default": "",
                        },
                    },
                    "required": ["url"],
                },
            ),
        ]

    async def execute(self, name: str, params: dict[str, Any]) -> CleanedOutput:
        url = params.get("url", "")
        wordlist = params.get("wordlist", "/usr/share/wordlists/dirb/common.txt")
        mode = params.get("mode", "dir")
        extensions = params.get("extensions", "")

        if not self._binary:
            return CleanedOutput(
                tool="gobuster", success=False,
                summary="gobuster not found in PATH.",
                structured={}, raw_length=0, cleaned_length=0,
            )

        cmd = f"{self._binary} {mode} -u {url} -w {wordlist} -q --no-color"
        if extensions:
            cmd += f" -x {extensions}"

        logger.info(f"Running: {cmd}")

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
            output = stdout.decode("utf-8", errors="replace")
            return self._cleaner.clean("gobuster", output, success=(proc.returncode == 0))
        except asyncio.TimeoutError:
            return CleanedOutput(
                tool="gobuster", success=False,
                summary=f"gobuster timed out after {self._timeout}s",
                structured={}, raw_length=0, cleaned_length=0,
            )
        except Exception as e:
            return CleanedOutput(
                tool="gobuster", success=False,
                summary=f"gobuster failed: {e}",
                structured={}, raw_length=0, cleaned_length=0,
            )
