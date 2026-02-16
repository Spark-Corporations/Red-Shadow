"""
Metasploit MCP Server — Exploitation framework interface.

Wraps msfconsole/msfrpcd for module execution, payload generation, and session management.
"""

from __future__ import annotations

import json
from typing import Any

from .base import BaseMCPServer, ToolSchema


class MetasploitServer(BaseMCPServer):
    def __init__(self, session_manager=None):
        super().__init__(session_manager, name="metasploit")

    def get_tools(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="msf_search",
                description="Search for Metasploit modules by keyword or CVE",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query (e.g., 'cve:2021-44228')"},
                        "type": {"type": "string", "enum": ["exploit", "auxiliary", "post", "payload"]},
                    },
                    "required": ["query"],
                },
            ),
            ToolSchema(
                name="msf_exploit",
                description="Run a Metasploit exploit module",
                parameters={
                    "type": "object",
                    "properties": {
                        "module": {"type": "string", "description": "Module path (e.g., 'exploit/multi/handler')"},
                        "target": {"type": "string", "description": "RHOSTS target"},
                        "payload": {"type": "string", "description": "Payload (e.g., 'linux/x64/meterpreter/reverse_tcp')"},
                        "lhost": {"type": "string", "description": "Local host for reverse connection"},
                        "lport": {"type": "integer", "description": "Local port (default: 4444)"},
                        "options": {"type": "object", "description": "Additional module options"},
                    },
                    "required": ["module", "target"],
                },
            ),
            ToolSchema(
                name="msf_sessions",
                description="List and interact with active Meterpreter sessions",
                parameters={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["list", "interact", "kill"]},
                        "session_id": {"type": "integer"},
                        "command": {"type": "string", "description": "Command to run in session"},
                    },
                },
            ),
        ]

    def build_command(self, tool_name: str = "msf_search", **params) -> str:
        if tool_name == "msf_search":
            query = params.get("query", "")
            mod_type = params.get("type", "")
            search = f"search {query}"
            if mod_type:
                search += f" type:{mod_type}"
            return f'msfconsole -q -x "{search}; exit"'

        elif tool_name == "msf_exploit":
            module = params.get("module", "")
            target = params.get("target", "")
            payload = params.get("payload", "")
            lhost = params.get("lhost", "0.0.0.0")
            lport = params.get("lport", 4444)
            opts = params.get("options", {})

            rc_cmds = [
                f"use {module}",
                f"set RHOSTS {target}",
            ]
            if payload:
                rc_cmds.append(f"set PAYLOAD {payload}")
            rc_cmds.append(f"set LHOST {lhost}")
            rc_cmds.append(f"set LPORT {lport}")
            for k, v in opts.items():
                rc_cmds.append(f"set {k} {v}")
            rc_cmds.append("exploit -z")
            rc_cmds.append("exit")

            cmd_str = "; ".join(rc_cmds)
            return f'msfconsole -q -x "{cmd_str}"'

        elif tool_name == "msf_sessions":
            action = params.get("action", "list")
            if action == "list":
                return 'msfconsole -q -x "sessions -l; exit"'
            sid = params.get("session_id", 1)
            if action == "interact":
                cmd = params.get("command", "sysinfo")
                return f'msfconsole -q -x "sessions -C {cmd} -i {sid}; exit"'
            if action == "kill":
                return f'msfconsole -q -x "sessions -k {sid}; exit"'

        return f'msfconsole -q -x "exit"'

    def parse_output(self, tool_name: str, raw_output: str) -> dict[str, Any]:
        if tool_name == "msf_search":
            modules = []
            for line in raw_output.split("\n"):
                if line.strip().startswith(("exploit/", "auxiliary/", "post/", "payload/")):
                    parts = line.split()
                    if len(parts) >= 3:
                        modules.append({
                            "path": parts[0],
                            "date": parts[1] if len(parts) > 1 else "",
                            "name": " ".join(parts[2:]),
                        })
            return {"modules": modules, "count": len(modules)}

        return {"raw": raw_output[:4000]}
