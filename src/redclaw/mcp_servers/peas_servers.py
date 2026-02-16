"""
LinPEAS & WinPEAS MCP Servers — Privilege escalation enumeration.
"""

from __future__ import annotations

import re
from typing import Any

from .base import BaseMCPServer, ToolSchema


class LinPEASServer(BaseMCPServer):
    def __init__(self, session_manager=None):
        super().__init__(session_manager, name="linpeas")

    def get_tools(self) -> list[ToolSchema]:
        return [ToolSchema(
            name="linpeas_enum",
            description="Run LinPEAS for Linux privilege escalation enumeration",
            parameters={
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Target (for remote sessions)"},
                    "intensity": {"type": "string", "enum": ["fast", "normal", "thorough"]},
                    "checks": {"type": "string", "description": "Specific checks (e.g., 'SuidSgid,Capabilities')"},
                },
            },
        )]

    def build_command(self, tool_name: str = "linpeas_enum", **params) -> str:
        parts = ["./linpeas.sh"]
        intensity = params.get("intensity", "normal")
        if intensity == "fast":
            parts.append("-s")
        elif intensity == "thorough":
            parts.append("-a")
        if checks := params.get("checks"):
            parts.extend(["-c", checks])
        return " ".join(parts)

    def parse_output(self, tool_name: str, raw_output: str) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        # LinPEAS uses color codes and markers for severity
        critical_markers = ["95%", "99%", "PE -"]
        for line in raw_output.split("\n"):
            clean = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()  # strip ANSI
            if not clean:
                continue
            severity = "info"
            for marker in critical_markers:
                if marker in clean:
                    severity = "high"
                    break
            if severity == "high" or "SUID" in clean or "writable" in clean.lower():
                findings.append({"text": clean[:200], "severity": severity})
        return {"findings": findings[:50], "total": len(findings)}


class WinPEASServer(BaseMCPServer):
    def __init__(self, session_manager=None):
        super().__init__(session_manager, name="winpeas")

    def get_tools(self) -> list[ToolSchema]:
        return [ToolSchema(
            name="winpeas_enum",
            description="Run WinPEAS for Windows privilege escalation enumeration",
            parameters={
                "type": "object",
                "properties": {
                    "target": {"type": "string"},
                    "checks": {"type": "string", "description": "Specific checks (e.g., 'servicesinfo,userinfo')"},
                },
            },
        )]

    def build_command(self, tool_name: str = "winpeas_enum", **params) -> str:
        parts = ["winPEASx64.exe"]
        if checks := params.get("checks"):
            parts.append(checks)
        return " ".join(parts)

    def parse_output(self, tool_name: str, raw_output: str) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        for line in raw_output.split("\n"):
            clean = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
            if not clean:
                continue
            if any(k in clean.lower() for k in ["vulnerable", "writable", "password", "credentials"]):
                findings.append({"text": clean[:200], "severity": "high"})
        return {"findings": findings[:50], "total": len(findings)}
