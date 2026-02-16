"""
Masscan MCP Server — Ultra-fast port discovery.

Wraps masscan for rapid full-port scanning of large networks.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .base import BaseMCPServer, ToolSchema


class MasscanServer(BaseMCPServer):
    def __init__(self, session_manager=None):
        super().__init__(session_manager, name="masscan")

    def get_tools(self) -> list[ToolSchema]:
        return [ToolSchema(
            name="masscan_scan",
            description="Ultra-fast port scanning for large networks",
            parameters={
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Target IP/CIDR"},
                    "ports": {"type": "string", "description": "Port range (e.g., '0-65535')"},
                    "rate": {"type": "integer", "description": "Packets per second (default: 10000)"},
                    "extra_args": {"type": "string"},
                },
                "required": ["target"],
            },
        )]

    def build_command(self, tool_name: str = "masscan_scan", **params) -> str:
        target = params.get("target", "")
        parts = ["masscan", target]
        parts.append(f"-p {params.get('ports', '1-65535')}")
        parts.append(f"--rate={params.get('rate', 10000)}")
        parts.append("-oJ -")  # JSON output
        if extra := params.get("extra_args"):
            parts.append(extra)
        return " ".join(parts)

    def parse_output(self, tool_name: str, raw_output: str) -> dict[str, Any]:
        ports: list[dict[str, Any]] = []
        for line in raw_output.strip().split("\n"):
            line = line.strip().rstrip(",")
            if not line or line in ("[", "]"):
                continue
            try:
                entry = json.loads(line)
                if "ports" in entry:
                    for p in entry["ports"]:
                        ports.append({
                            "ip": entry.get("ip", ""),
                            "port": p.get("port"),
                            "protocol": p.get("proto", "tcp"),
                            "status": p.get("status", "open"),
                        })
            except json.JSONDecodeError:
                continue
        return {"ports": ports, "total": len(ports)}
