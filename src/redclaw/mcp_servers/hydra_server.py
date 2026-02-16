"""
Hydra MCP Server — Brute-force password attacks.
"""

from __future__ import annotations

import re
from typing import Any

from .base import BaseMCPServer, ToolSchema


class HydraServer(BaseMCPServer):
    def __init__(self, session_manager=None):
        super().__init__(session_manager, name="hydra")

    def get_tools(self) -> list[ToolSchema]:
        return [ToolSchema(
            name="hydra_attack",
            description="Brute-force login credentials for network services",
            parameters={
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Target host"},
                    "service": {"type": "string", "description": "Service (ssh, ftp, http-post-form, smb, etc.)"},
                    "username": {"type": "string", "description": "Single username or -L for file"},
                    "password": {"type": "string", "description": "Single password or -P for file"},
                    "userlist": {"type": "string", "description": "Path to username wordlist"},
                    "passlist": {"type": "string", "description": "Path to password wordlist"},
                    "threads": {"type": "integer", "description": "Number of threads (default: 16)"},
                    "extra_args": {"type": "string"},
                },
                "required": ["target", "service"],
            },
        )]

    def build_command(self, tool_name: str = "hydra_attack", **params) -> str:
        target = params.get("target", "")
        service = params.get("service", "ssh")
        parts = ["hydra"]

        if ul := params.get("userlist"):
            parts.extend(["-L", ul])
        elif u := params.get("username"):
            parts.extend(["-l", u])

        if pl := params.get("passlist"):
            parts.extend(["-P", pl])
        elif p := params.get("password"):
            parts.extend(["-p", p])

        threads = params.get("threads", 16)
        parts.extend(["-t", str(threads)])
        if extra := params.get("extra_args"):
            parts.append(extra)
        parts.extend([target, service])
        return " ".join(parts)

    def parse_output(self, tool_name: str, raw_output: str) -> dict[str, Any]:
        creds = []
        for line in raw_output.split("\n"):
            match = re.search(
                r"\[(\d+)\]\[(\w+)\]\s+host:\s+(\S+)\s+login:\s+(\S+)\s+password:\s+(\S+)",
                line,
            )
            if match:
                creds.append({
                    "port": int(match.group(1)),
                    "service": match.group(2),
                    "host": match.group(3),
                    "username": match.group(4),
                    "password": match.group(5),
                })
        return {"credentials": creds, "cracked": len(creds)}
