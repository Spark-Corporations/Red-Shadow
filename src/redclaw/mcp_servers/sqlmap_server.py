"""
SQLMap MCP Server — SQL injection detection and exploitation.
"""

from __future__ import annotations

import json
from typing import Any

from .base import BaseMCPServer, ToolSchema


class SQLMapServer(BaseMCPServer):
    def __init__(self, session_manager=None):
        super().__init__(session_manager, name="sqlmap")

    def get_tools(self) -> list[ToolSchema]:
        return [ToolSchema(
            name="sqlmap_scan",
            description="Test for SQL injection vulnerabilities",
            parameters={
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Target URL with parameter (e.g., 'http://example.com/page?id=1')"},
                    "method": {"type": "string", "enum": ["GET", "POST"]},
                    "data": {"type": "string", "description": "POST data"},
                    "level": {"type": "integer", "minimum": 1, "maximum": 5},
                    "risk": {"type": "integer", "minimum": 1, "maximum": 3},
                    "technique": {"type": "string", "description": "SQLi techniques (B,T,E,U,S,Q)"},
                    "dump": {"type": "boolean", "description": "Dump database tables"},
                    "dbs": {"type": "boolean", "description": "Enumerate databases"},
                    "extra_args": {"type": "string"},
                },
                "required": ["target"],
            },
        )]

    def build_command(self, tool_name: str = "sqlmap_scan", **params) -> str:
        target = params.get("target", "")
        parts = ["sqlmap", "-u", f'"{target}"', "--batch"]
        if params.get("method") == "POST" and (data := params.get("data")):
            parts.extend(["--data", f'"{data}"'])
        if level := params.get("level"):
            parts.extend(["--level", str(level)])
        if risk := params.get("risk"):
            parts.extend(["--risk", str(risk)])
        if technique := params.get("technique"):
            parts.extend(["--technique", technique])
        if params.get("dump"):
            parts.append("--dump")
        if params.get("dbs"):
            parts.append("--dbs")
        if extra := params.get("extra_args"):
            parts.append(extra)
        return " ".join(parts)

    def parse_output(self, tool_name: str, raw_output: str) -> dict[str, Any]:
        vulns = []
        for line in raw_output.split("\n"):
            if "injectable" in line.lower() or "is vulnerable" in line.lower():
                vulns.append(line.strip())
        return {"vulnerabilities": vulns, "injectable": len(vulns) > 0, "count": len(vulns)}
