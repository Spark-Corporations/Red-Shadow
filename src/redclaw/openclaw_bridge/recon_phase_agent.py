"""
ReconPhaseAgent — Recon phase with real tool execution.

First phase in the pipeline. No KG input needed (starts blind).
Runs nmap via BashWrapper (real subprocess), parses XML output,
falls back to Python socket scan if nmap unavailable.

Writes to KG:
  - Host node
  - Port nodes (open ports)
  - Service nodes (name + version)
  - Capability flags for ToolScheduler

Reads from KG: Nothing (first phase)
Tools: BashWrapper (nmap), Python socket fallback
LLM: Not used — recon is deterministic tool output
"""
from __future__ import annotations

import asyncio
import logging
import re
import socket
import xml.etree.ElementTree as ET
from typing import Any, Callable, Dict, List, Optional

from .phase_agent import PhaseAgentBase

logger = logging.getLogger("redclaw.recon_agent")


# Common ports for fallback scan
COMMON_PORTS = [
    21, 22, 23, 25, 53, 80, 110, 111, 135, 139, 143, 443, 445,
    993, 995, 1433, 1521, 2049, 3306, 3389, 5432, 5900, 6379,
    8080, 8443, 8888, 9090, 27017,
]

# Service detection from banners
BANNER_SIGNATURES = {
    "SSH":        re.compile(r"^SSH-[\d.]+-(.+)", re.IGNORECASE),
    "FTP":        re.compile(r"^220[- ](.+)", re.IGNORECASE),
    "SMTP":       re.compile(r"^220[- ](.+SMTP.+)", re.IGNORECASE),
    "HTTP":       re.compile(r"^HTTP/[\d.]+\s+\d+", re.IGNORECASE),
    "MySQL":      re.compile(r"^\x00.+mysql|MariaDB", re.IGNORECASE),
    "PostgreSQL": re.compile(r"^.*PostgreSQL|^E\x00", re.IGNORECASE),
    "Redis":      re.compile(r"^\-ERR|^\+PONG|\$\d+\r\nredis", re.IGNORECASE),
}

# Port → likely service name mapping (when banner detection fails)
PORT_SERVICE_MAP = {
    21: "ftp", 22: "ssh", 23: "telnet", 25: "smtp", 53: "dns",
    80: "http", 110: "pop3", 111: "rpcbind", 135: "msrpc",
    139: "netbios-ssn", 143: "imap", 443: "https", 445: "microsoft-ds",
    993: "imaps", 995: "pop3s", 1433: "ms-sql-s", 1521: "oracle",
    2049: "nfs", 3306: "mysql", 3389: "ms-wbt-server",
    5432: "postgresql", 5900: "vnc", 6379: "redis",
    8080: "http-proxy", 8443: "https-alt", 8888: "http",
    9090: "http", 27017: "mongodb",
}


class ReconPhaseAgent(PhaseAgentBase):
    """
    Recon phase — discovers open ports and services.

    Execution strategy:
      1. Try nmap via BashWrapper (real subprocess)
      2. Parse XML output deterministically
      3. If nmap unavailable → Python async socket scan
      4. Banner grabbing for service identification
      5. Write everything to KG

    No LLM involvement — output is 100% tool-driven.
    """

    PHASE_NAME = "recon"
    REQUIRED_OUTPUT_FIELDS = ["target", "open_ports", "services"]

    def _system_prompt(self) -> str:
        return ""  # No LLM needed

    def _load_context_from_kg(self) -> str:
        return f"Target: {self.target}"  # First phase — KG is empty

    async def execute(self) -> dict:
        """
        Run recon: nmap first, Python fallback second.

        Returns:
            {
                "target": "10.10.10.5",
                "open_ports": [22, 80, 443],
                "services": [
                    {"port": 22, "name": "ssh", "version": "OpenSSH 8.2p1", "product": "OpenSSH"},
                    {"port": 80, "name": "http", "version": "1.24.0", "product": "nginx"},
                ],
                "scan_type": "nmap" | "python_fallback",
                "os_guess": "Linux" | None,
                "raw_truncated": "..."
            }
        """
        self._log("    Trying nmap scan...")

        # Strategy 1: nmap via BashWrapper
        result = await self._nmap_scan()
        if result and result.get("open_ports"):
            result["scan_type"] = "nmap"
            self._log(f"    nmap found {len(result['open_ports'])} open ports")
            return result

        # Strategy 2: Python socket scan fallback
        self._log("    nmap unavailable or failed — running Python fallback scan")
        result = await self._python_scan()
        result["scan_type"] = "python_fallback"
        self._log(f"    Python scan found {len(result['open_ports'])} open ports")
        return result

    # ── Nmap Scan ─────────────────────────────────────────────────────────

    async def _nmap_scan(self) -> Optional[dict]:
        """Run nmap via BashWrapper → parse XML output."""
        try:
            # Run nmap with XML output to stdout
            output = await self.run_command(
                f"nmap -sV -sC -T4 --open -oX - {self.target}",
                timeout=120,
            )

            if not output or "nmap" not in output.lower():
                return None

            return self._parse_nmap_xml(output)

        except Exception as e:
            self._log(f"    nmap failed: {e}")
            return None

    def _parse_nmap_xml(self, raw_xml: str) -> dict:
        """Parse nmap XML output into structured dict."""
        result = {
            "target": self.target,
            "open_ports": [],
            "services": [],
            "os_guess": None,
            "raw_truncated": raw_xml[:500],
        }

        try:
            # Extract XML portion (nmap may have non-XML output before/after)
            xml_start = raw_xml.find("<?xml")
            if xml_start < 0:
                xml_start = raw_xml.find("<nmaprun")
            if xml_start < 0:
                return self._parse_nmap_text(raw_xml)

            xml_data = raw_xml[xml_start:]
            root = ET.fromstring(xml_data)

            for host in root.findall("host"):
                # Parse ports
                for port_el in host.findall(".//port"):
                    state_el = port_el.find("state")
                    if state_el is None or state_el.get("state") != "open":
                        continue

                    port_id = int(port_el.get("portid", 0))
                    result["open_ports"].append(port_id)

                    svc_el = port_el.find("service")
                    svc_entry = {
                        "port": port_id,
                        "name": "unknown",
                        "version": "",
                        "product": "",
                    }
                    if svc_el is not None:
                        svc_entry["name"] = svc_el.get("name", "unknown")
                        svc_entry["version"] = svc_el.get("version", "")
                        svc_entry["product"] = svc_el.get("product", "")

                    result["services"].append(svc_entry)

                # Parse OS detection
                for os_el in host.findall(".//osmatch"):
                    result["os_guess"] = os_el.get("name", "")
                    break  # Take first (highest accuracy)

        except ET.ParseError:
            return self._parse_nmap_text(raw_xml)

        return result

    def _parse_nmap_text(self, raw: str) -> dict:
        """Fallback: parse nmap plain text output when XML fails."""
        result = {
            "target": self.target,
            "open_ports": [],
            "services": [],
            "os_guess": None,
            "raw_truncated": raw[:500],
        }

        # Match lines like: 80/tcp  open  http    nginx 1.24.0
        port_pattern = re.compile(
            r"(\d+)/tcp\s+open\s+(\S+)\s*(.*)", re.IGNORECASE
        )

        for line in raw.split("\n"):
            m = port_pattern.search(line)
            if m:
                port = int(m.group(1))
                service = m.group(2)
                extra = m.group(3).strip()

                result["open_ports"].append(port)

                # Try to extract version from extra
                version = ""
                product = ""
                if extra:
                    parts = extra.split()
                    if parts:
                        product = parts[0]
                    if len(parts) > 1:
                        version = parts[1]

                result["services"].append({
                    "port": port,
                    "name": service,
                    "version": version,
                    "product": product,
                })

        return result

    # ── Python Socket Scan ────────────────────────────────────────────────

    async def _python_scan(self) -> dict:
        """Pure Python async port scan + banner grabbing."""
        result = {
            "target": self.target,
            "open_ports": [],
            "services": [],
            "os_guess": None,
            "raw_truncated": "python_fallback_scan",
        }

        # Phase 1: Async port scan
        open_ports = await self._async_port_scan()
        result["open_ports"] = open_ports

        # Phase 2: Banner grab on open ports
        for port in open_ports:
            svc = await self._banner_grab(port)
            result["services"].append(svc)

        return result

    async def _async_port_scan(self) -> List[int]:
        """Scan COMMON_PORTS with async socket connections."""
        open_ports = []

        async def check_port(port: int) -> Optional[int]:
            try:
                conn = asyncio.open_connection(self.target, port)
                reader, writer = await asyncio.wait_for(conn, timeout=1.5)
                writer.close()
                await writer.wait_closed()
                return port
            except Exception:
                return None

        # Run all port checks concurrently
        tasks = [check_port(p) for p in COMMON_PORTS]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, int):
                open_ports.append(r)

        return sorted(open_ports)

    async def _banner_grab(self, port: int) -> dict:
        """Try to grab service banner from an open port."""
        svc = {
            "port": port,
            "name": PORT_SERVICE_MAP.get(port, "unknown"),
            "version": "",
            "product": "",
        }

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.target, port),
                timeout=3.0,
            )

            # Some services send banner immediately
            try:
                banner = await asyncio.wait_for(reader.read(1024), timeout=2.0)
                banner_text = banner.decode("utf-8", errors="replace").strip()
            except asyncio.TimeoutError:
                # HTTP/HTTPS — need to send request first
                if port in (80, 443, 8080, 8443, 8888, 9090):
                    writer.write(b"GET / HTTP/1.0\r\nHost: target\r\n\r\n")
                    await writer.drain()
                    try:
                        banner = await asyncio.wait_for(reader.read(2048), timeout=2.0)
                        banner_text = banner.decode("utf-8", errors="replace").strip()
                    except asyncio.TimeoutError:
                        banner_text = ""
                else:
                    banner_text = ""

            writer.close()
            await writer.wait_closed()

            # Match banner against known signatures
            if banner_text:
                for svc_name, pattern in BANNER_SIGNATURES.items():
                    m = pattern.search(banner_text)
                    if m:
                        svc["name"] = svc_name.lower()
                        svc["product"] = m.group(1)[:50] if m.lastindex else svc_name
                        # Try to extract version
                        ver_match = re.search(r"(\d+\.\d+[\.\d]*\w*)", banner_text)
                        if ver_match:
                            svc["version"] = ver_match.group(1)
                        break

                # HTTP Server header
                if port in (80, 443, 8080, 8443):
                    server_match = re.search(
                        r"Server:\s*(.+)", banner_text, re.IGNORECASE
                    )
                    if server_match:
                        server = server_match.group(1).strip()
                        svc["product"] = server.split("/")[0]
                        ver = re.search(r"/([\d.]+)", server)
                        if ver:
                            svc["version"] = ver.group(1)

        except Exception:
            pass

        return svc

    # ── KG Write ──────────────────────────────────────────────────────────

    def _write_to_kg(self, result: dict) -> None:
        """Write recon results to KG: host → ports → services."""
        self.kg.add_host(self.target)

        for svc in result.get("services", []):
            self.kg.add_port(self.target, svc["port"], "open")
            self.kg.add_service(
                self.target, svc["port"],
                svc["name"], svc.get("version", ""),
            )

        # Set capability flags for ToolScheduler
        ports = result.get("open_ports", [])
        if ports:
            self.kg.set_capability("open_ports", True)

        # Detect specific capabilities
        for svc in result.get("services", []):
            name = svc.get("name", "").lower()
            port = svc.get("port", 0)
            if name in ("http", "https", "http-proxy", "https-alt") or port in (80, 443, 8080):
                self.kg.set_capability("http_confirmed", True)
            if name == "ssh" or port == 22:
                self.kg.set_capability("ssh_confirmed", True)
            if name in ("ftp",) or port == 21:
                self.kg.set_capability("ftp_confirmed", True)
            if name in ("mysql", "postgresql", "ms-sql-s", "oracle", "mongodb"):
                self.kg.set_capability("db_confirmed", True)

        if result.get("os_guess"):
            self.kg.set_capability("os_detected", result["os_guess"])

        stats = self.kg.get_stats()
        self._log(f"    KG updated: {stats['total_nodes']} nodes, "
                  f"{stats['total_edges']} edges")
