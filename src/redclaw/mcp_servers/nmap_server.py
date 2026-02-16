"""
Nmap MCP Server — Port scanning and service detection.

Wraps nmap with structured parameter building and XML output parsing.
"""

from __future__ import annotations

import re
from typing import Any

from .base import BaseMCPServer, ToolSchema


class NmapServer(BaseMCPServer):
    """MCP server wrapping nmap for port scanning and service detection."""

    def __init__(self, session_manager=None):
        super().__init__(session_manager, name="nmap")

    def get_tools(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="nmap_scan",
                description="Run an nmap port scan with service/version detection",
                parameters={
                    "type": "object",
                    "properties": {
                        "target": {"type": "string", "description": "Target IP, hostname, or CIDR range"},
                        "ports": {"type": "string", "description": "Port specification (e.g., '1-1000', '22,80,443')"},
                        "scan_type": {
                            "type": "string",
                            "enum": ["syn", "tcp", "udp", "version", "os", "aggressive", "ping"],
                            "description": "Scan type",
                        },
                        "scripts": {"type": "string", "description": "NSE scripts to run (e.g., 'vuln,default')"},
                        "timing": {
                            "type": "integer", "minimum": 0, "maximum": 5,
                            "description": "Timing template (0=paranoid to 5=insane)",
                        },
                        "extra_args": {"type": "string", "description": "Additional nmap arguments"},
                    },
                    "required": ["target"],
                },
            ),
        ]

    def build_command(self, tool_name: str = "nmap_scan", **params) -> str:
        target = params.get("target", "")
        if not target:
            raise ValueError("nmap requires a target")

        parts = ["nmap"]

        scan_type = params.get("scan_type", "syn")
        scan_flags = {
            "syn": "-sS", "tcp": "-sT", "udp": "-sU",
            "version": "-sV", "os": "-O", "aggressive": "-A", "ping": "-sn",
        }
        parts.append(scan_flags.get(scan_type, "-sS"))

        if ports := params.get("ports"):
            parts.append(f"-p {ports}")

        if scripts := params.get("scripts"):
            parts.append(f"--script={scripts}")

        timing = params.get("timing", 3)
        parts.append(f"-T{timing}")

        parts.append("-oX -")  # XML output to stdout for parsing

        if extra := params.get("extra_args"):
            parts.append(extra)

        parts.append(target)
        return " ".join(parts)

    def parse_output(self, tool_name: str, raw_output: str) -> dict[str, Any]:
        """Parse nmap output into structured data."""
        result: dict[str, Any] = {"hosts": [], "summary": ""}

        # Try XML parsing first
        if "<nmaprun" in raw_output:
            return self._parse_xml(raw_output)

        # Fallback: parse text output
        current_host: dict[str, Any] = {}
        for line in raw_output.split("\n"):
            line = line.strip()
            if line.startswith("Nmap scan report for"):
                if current_host:
                    result["hosts"].append(current_host)
                host_match = re.search(r"for\s+(\S+)", line)
                current_host = {
                    "host": host_match.group(1) if host_match else "",
                    "ports": [],
                }
            elif re.match(r"^\d+/\w+", line):
                # Port line: "80/tcp open http Apache httpd 2.4.49"
                port_match = re.match(
                    r"^(\d+)/(\w+)\s+(\w+)\s+(.*)$", line
                )
                if port_match:
                    current_host.setdefault("ports", []).append({
                        "port": int(port_match.group(1)),
                        "protocol": port_match.group(2),
                        "state": port_match.group(3),
                        "service": port_match.group(4).strip(),
                    })

        if current_host:
            result["hosts"].append(current_host)

        total_ports = sum(len(h.get("ports", [])) for h in result["hosts"])
        open_ports = sum(
            1 for h in result["hosts"]
            for p in h.get("ports", [])
            if p.get("state") == "open"
        )
        result["summary"] = f"{len(result['hosts'])} hosts, {total_ports} ports scanned, {open_ports} open"
        return result

    def _parse_xml(self, xml_output: str) -> dict[str, Any]:
        """Parse nmap XML output."""
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_output)
            hosts = []
            for host_el in root.findall(".//host"):
                addr = host_el.find("address")
                host_info: dict[str, Any] = {
                    "host": addr.get("addr", "") if addr is not None else "",
                    "ports": [],
                }
                for port_el in host_el.findall(".//port"):
                    state_el = port_el.find("state")
                    service_el = port_el.find("service")
                    host_info["ports"].append({
                        "port": int(port_el.get("portid", 0)),
                        "protocol": port_el.get("protocol", ""),
                        "state": state_el.get("state", "") if state_el is not None else "",
                        "service": service_el.get("name", "") if service_el is not None else "",
                        "version": service_el.get("version", "") if service_el is not None else "",
                    })
                hosts.append(host_info)
            return {"hosts": hosts, "format": "xml"}
        except Exception:
            return {"raw": xml_output[:4000]}
