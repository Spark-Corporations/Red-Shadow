"""
Nuclei MCP Server — Template-based vulnerability scanning.

Wraps nuclei for automated vulnerability detection using YAML templates.
"""

from __future__ import annotations

import json
from typing import Any

from .base import BaseMCPServer, ToolSchema


class NucleiServer(BaseMCPServer):
    def __init__(self, session_manager=None):
        super().__init__(session_manager, name="nuclei")

    def get_tools(self) -> list[ToolSchema]:
        return [ToolSchema(
            name="nuclei_scan",
            description="Template-based vulnerability scanning",
            parameters={
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Target URL or file of URLs"},
                    "templates": {"type": "string", "description": "Template IDs or tags (e.g., 'cve,misconfig')"},
                    "severity": {"type": "string", "description": "Filter by severity (critical,high,medium,low,info)"},
                    "rate_limit": {"type": "integer", "description": "Max requests per second"},
                    "extra_args": {"type": "string"},
                },
                "required": ["target"],
            },
        )]

    def build_command(self, tool_name: str = "nuclei_scan", **params) -> str:
        target = params.get("target", "")
        parts = ["nuclei", "-u", target, "-jsonl"]
        if t := params.get("templates"):
            parts.extend(["-tags", t])
        if s := params.get("severity"):
            parts.extend(["-severity", s])
        if r := params.get("rate_limit"):
            parts.extend(["-rate-limit", str(r)])
        if extra := params.get("extra_args"):
            parts.append(extra)
        return " ".join(parts)

    def parse_output(self, tool_name: str, raw_output: str) -> dict[str, Any]:
        findings: list[dict[str, Any]] = []
        for line in raw_output.strip().split("\n"):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                findings.append({
                    "template_id": entry.get("template-id", ""),
                    "name": entry.get("info", {}).get("name", ""),
                    "severity": entry.get("info", {}).get("severity", "info"),
                    "matched_at": entry.get("matched-at", ""),
                    "type": entry.get("type", ""),
                    "description": entry.get("info", {}).get("description", ""),
                })
            except json.JSONDecodeError:
                continue
        severity_count = {}
        for f in findings:
            s = f.get("severity", "info")
            severity_count[s] = severity_count.get(s, 0) + 1
        return {"findings": findings, "total": len(findings), "by_severity": severity_count}
