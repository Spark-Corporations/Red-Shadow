"""
MCPConfigGenerator — Generates Claude Code MCP server configuration.

Produces the JSON config that tells Claude Code how to launch and connect
to each of RedClaw's 10 MCP pentesting tool servers.

Used with: `claude --mcp-config /path/to/redclaw_mcp.json`
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional


class MCPConfigGenerator:
    """
    Generate MCP server configuration for Claude Code.

    Each MCP server is a Python module that Claude Code launches as a subprocess.
    The config tells Claude Code:
      - How to start each server (command + args)
      - What environment variables to pass
      - Server name and type
    """

    # Python interpreter
    PYTHON = sys.executable

    # All 10 MCP servers mapping to their module paths
    MCP_SERVERS = {
        "redclaw-nmap": {
            "module": "redclaw.mcp_servers.nmap_server",
            "description": "Nmap port scanner and service detection",
        },
        "redclaw-masscan": {
            "module": "redclaw.mcp_servers.masscan_server",
            "description": "Ultra-fast port discovery",
        },
        "redclaw-nuclei": {
            "module": "redclaw.mcp_servers.nuclei_server",
            "description": "Template-based vulnerability scanner",
        },
        "redclaw-msf": {
            "module": "redclaw.mcp_servers.metasploit_server",
            "description": "Metasploit exploitation framework",
        },
        "redclaw-sqlmap": {
            "module": "redclaw.mcp_servers.sqlmap_server",
            "description": "SQL injection detection and exploitation",
        },
        "redclaw-hydra": {
            "module": "redclaw.mcp_servers.hydra_server",
            "description": "Network login cracker",
        },
        "redclaw-linpeas": {
            "module": "redclaw.mcp_servers.peas_servers",
            "args_extra": ["--type", "lin"],
            "description": "Linux privilege escalation enumeration",
        },
        "redclaw-winpeas": {
            "module": "redclaw.mcp_servers.peas_servers",
            "args_extra": ["--type", "win"],
            "description": "Windows privilege escalation enumeration",
        },
        "redclaw-bloodhound": {
            "module": "redclaw.mcp_servers.bloodhound_server",
            "description": "Active Directory attack path analysis",
        },
        "redclaw-custom": {
            "module": "redclaw.mcp_servers.custom_exploit_server",
            "description": "Custom Python/Bash exploit runner",
        },
    }

    def __init__(
        self,
        python_path: Optional[str] = None,
        env_vars: Optional[dict[str, str]] = None,
        enabled_servers: Optional[list[str]] = None,
    ):
        self.python_path = python_path or self.PYTHON
        self.env_vars = env_vars or {}
        self.enabled_servers = enabled_servers  # None = all servers

    def generate(self) -> dict[str, Any]:
        """Generate the MCP server configuration dict."""
        mcp_servers: dict[str, dict[str, Any]] = {}

        for server_name, server_info in self.MCP_SERVERS.items():
            # Filter if specific servers requested
            if self.enabled_servers and server_name not in self.enabled_servers:
                continue

            args = ["-m", server_info["module"]]
            if extra := server_info.get("args_extra"):
                args.extend(extra)

            server_config: dict[str, Any] = {
                "command": self.python_path,
                "args": args,
            }

            # Add environment variables if any
            if self.env_vars:
                server_config["env"] = self.env_vars.copy()

            mcp_servers[server_name] = server_config

        return {"mcpServers": mcp_servers}

    def generate_json(self, indent: int = 2) -> str:
        """Generate MCP config as formatted JSON string."""
        return json.dumps(self.generate(), indent=indent)

    def write_to_file(self, path: Path) -> Path:
        """Write MCP config to a JSON file and return the path."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.generate_json(), encoding="utf-8")
        return path

    @classmethod
    def list_servers(cls) -> list[dict[str, str]]:
        """List all available MCP servers with descriptions."""
        return [
            {"name": name, "description": info["description"]}
            for name, info in cls.MCP_SERVERS.items()
        ]


def get_mcp_config(
    python_path: Optional[str] = None,
    env_vars: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Convenience function to generate MCP config."""
    return MCPConfigGenerator(
        python_path=python_path,
        env_vars=env_vars,
    ).generate()
