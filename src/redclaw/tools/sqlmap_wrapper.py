"""
SqlmapWrapper — Minimal sqlmap SQL injection testing wrapper.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from typing import Any, Optional

from .output_cleaner import OutputCleaner, CleanedOutput
from .nmap_wrapper import ToolSchema

logger = logging.getLogger("redclaw.tools.sqlmap")


class SqlmapWrapper:
    """
    Sqlmap wrapper for SQL injection testing.

    Usage:
        sqlmap = SqlmapWrapper()
        result = await sqlmap.execute("sqlmap_scan", {"url": "http://target/page?id=1"})
    """

    def __init__(self, cleaner: Optional[OutputCleaner] = None, timeout: int = 600):
        self._cleaner = cleaner or OutputCleaner()
        self._timeout = timeout
        self._binary = shutil.which("sqlmap") or shutil.which("python3")

    def get_tools(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="sqlmap_scan",
                description="Run sqlmap SQL injection test on a URL with parameters. Returns injection findings.",
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Target URL with injectable parameter (e.g., http://target/page?id=1)"},
                        "flags": {
                            "type": "string",
                            "description": "Additional sqlmap flags (e.g., --dbs, --tables, --dump)",
                            "default": "--batch --level 3 --risk 2",
                        },
                    },
                    "required": ["url"],
                },
            ),
        ]

    async def execute(self, name: str, params: dict[str, Any]) -> CleanedOutput:
        url = params.get("url", "")
        flags = params.get("flags", "--batch --level 3 --risk 2")

        sqlmap_bin = shutil.which("sqlmap")
        if sqlmap_bin:
            cmd = f"{sqlmap_bin} -u \"{url}\" {flags}"
        else:
            cmd = f"python3 -m sqlmap -u \"{url}\" {flags}"

        logger.info(f"Running: {cmd}")

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
            output = stdout.decode("utf-8", errors="replace")
            return self._cleaner.clean("sqlmap", output, success=(proc.returncode == 0))
        except asyncio.TimeoutError:
            return CleanedOutput(
                tool="sqlmap", success=False,
                summary=f"sqlmap timed out after {self._timeout}s",
                structured={}, raw_length=0, cleaned_length=0,
            )
        except Exception as e:
            return CleanedOutput(
                tool="sqlmap", success=False,
                summary=f"sqlmap failed: {e}",
                structured={}, raw_length=0, cleaned_length=0,
            )
