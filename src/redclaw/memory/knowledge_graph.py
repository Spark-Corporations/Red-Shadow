"""
PentestKnowledgeGraph — NetworkX-based graph for pentest data relationships.

Stores structured relationships: Host -> Port -> Service -> Vulnerability -> Exploit
Supports natural language queries for LLM context enrichment.

Node Types: HOST, PORT, SERVICE, VERSION, VULNERABILITY, EXPLOIT, CREDENTIAL, FILE
Edge Types: HAS_PORT, RUNS_SERVICE, HAS_VERSION, HAS_VULN, EXPLOITABLE_VIA, etc.
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import re
from enum import Enum
from typing import Any, Dict, List, Optional

import networkx as nx

logger = logging.getLogger("redclaw.memory.knowledge_graph")


# ── Enums ─────────────────────────────────────────────────────────────────────


class NodeType(Enum):
    """Node types in pentest graph."""
    HOST = "host"
    PORT = "port"
    SERVICE = "service"
    VERSION = "version"
    VULNERABILITY = "vulnerability"
    EXPLOIT = "exploit"
    CREDENTIAL = "credential"
    FILE = "file"


class EdgeType(Enum):
    """Edge types (relationships)."""
    HAS_PORT = "HAS_PORT"
    RUNS_SERVICE = "RUNS_SERVICE"
    HAS_VERSION = "HAS_VERSION"
    HAS_VULN = "HAS_VULN"
    EXPLOITABLE_VIA = "EXPLOITABLE_VIA"
    USES_CREDENTIAL = "USES_CREDENTIAL"
    CONTAINS_FILE = "CONTAINS_FILE"
    CONNECTS_TO = "CONNECTS_TO"


# ── Knowledge Graph ──────────────────────────────────────────────────────────


class PentestKnowledgeGraph:
    """
    Knowledge Graph for pentest data.

    Usage:
        graph = PentestKnowledgeGraph()
        graph.add_host("10.10.10.5", os="Linux")
        graph.add_port("10.10.10.5", 80, "open")
        graph.add_service("10.10.10.5", 80, "Apache", "2.4.49")
        graph.add_vulnerability("10.10.10.5:80:Apache", "CVE-2021-41773", "critical")

        results = graph.query_natural_language("Find all CVEs on 10.10.10.5")
    """

    def __init__(self):
        self.graph = nx.DiGraph()
        self._node_count_before = 0
        self._edge_count_before = 0
        logger.info("Knowledge Graph initialized")

    # ═══════════════════════════════════════════════════════════════════════
    # GRAPH OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════

    def add_host(self, ip: str, os: Optional[str] = None, hostname: Optional[str] = None):
        """Add host node."""
        self.graph.add_node(
            ip, type=NodeType.HOST.value, os=os, hostname=hostname
        )
        logger.debug(f"Added host: {ip}")

    def add_port(self, ip: str, port: int, state: str):
        """Add port node and link to host."""
        port_id = f"{ip}:{port}"
        self.graph.add_node(
            port_id, type=NodeType.PORT.value, port=port, state=state
        )
        self.graph.add_edge(ip, port_id, type=EdgeType.HAS_PORT.value)
        logger.debug(f"Added port: {port_id} ({state})")

    def add_service(self, ip: str, port: int, name: str, version: Optional[str] = None):
        """Add service node and link to port."""
        port_id = f"{ip}:{port}"
        service_id = f"{ip}:{port}:{name}"
        self.graph.add_node(
            service_id, type=NodeType.SERVICE.value, name=name, version=version
        )
        self.graph.add_edge(port_id, service_id, type=EdgeType.RUNS_SERVICE.value)
        logger.debug(f"Added service: {service_id}")

    def add_vulnerability(
        self, service_id: str, cve: str, severity: str, cvss: Optional[float] = None
    ):
        """Add vulnerability node and link to service."""
        vuln_id = f"vuln:{cve}"
        self.graph.add_node(
            vuln_id, type=NodeType.VULNERABILITY.value,
            cve=cve, severity=severity, cvss=cvss
        )
        self.graph.add_edge(service_id, vuln_id, type=EdgeType.HAS_VULN.value)
        logger.debug(f"Added vulnerability: {cve} on {service_id}")

    def add_exploit(
        self, cve: str, exploit_name: str, url: str = "", tested: bool = False
    ):
        """Add exploit node and link to vulnerability."""
        vuln_id = f"vuln:{cve}"
        exploit_id = f"exploit:{cve}:{exploit_name}"
        self.graph.add_node(
            exploit_id, type=NodeType.EXPLOIT.value,
            name=exploit_name, url=url, tested=tested
        )
        self.graph.add_edge(vuln_id, exploit_id, type=EdgeType.EXPLOITABLE_VIA.value)
        logger.debug(f"Added exploit: {exploit_name} for {cve}")

    def add_credential(
        self, host_ip: str, username: str, password: str = "", source: str = ""
    ):
        """Add credential node and link to host."""
        cred_id = f"cred:{host_ip}:{username}"
        self.graph.add_node(
            cred_id, type=NodeType.CREDENTIAL.value,
            username=username, password=password, source=source
        )
        self.graph.add_edge(host_ip, cred_id, type=EdgeType.USES_CREDENTIAL.value)
        logger.debug(f"Added credential for {host_ip}: {username}")

    def add_file(self, host_ip: str, path: str, content_preview: str = ""):
        """Add discovered file node."""
        file_id = f"file:{host_ip}:{path}"
        self.graph.add_node(
            file_id, type=NodeType.FILE.value,
            path=path, content_preview=content_preview[:200]
        )
        self.graph.add_edge(host_ip, file_id, type=EdgeType.CONTAINS_FILE.value)

    # ═══════════════════════════════════════════════════════════════════════
    # QUERY OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════

    def query_natural_language(self, query: str) -> Dict[str, Any]:
        """
        Query graph using natural language.

        Supported queries:
          - "Find all vulnerabilities on 10.10.10.5"
          - "Show exploits for CVE-2021-41773"
          - "List all services on 10.10.10.5"
          - "Summary of 10.10.10.5"
        """
        query_lower = query.lower()

        # Extract IP
        ip_match = re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', query)
        # Extract CVE
        cve_match = re.search(r'CVE-\d{4}-\d{4,7}', query, re.IGNORECASE)

        if "vulnerabilities" in query_lower or "vulns" in query_lower or "cves" in query_lower:
            if ip_match:
                return self.get_vulnerabilities_for_host(ip_match.group(0))

        elif "exploits" in query_lower:
            if cve_match:
                return self.get_exploits_for_cve(cve_match.group(0).upper())

        elif "services" in query_lower:
            if ip_match:
                return self.get_services_for_host(ip_match.group(0))

        elif "summary" in query_lower or "overview" in query_lower:
            if ip_match:
                return self.get_host_summary(ip_match.group(0))

        elif "credentials" in query_lower or "creds" in query_lower:
            if ip_match:
                return self.get_credentials_for_host(ip_match.group(0))

        elif "attack" in query_lower and "path" in query_lower:
            return self.get_attack_path()

        return {"error": "Could not parse query", "raw_query": query}

    def get_vulnerabilities_for_host(self, ip: str) -> Dict[str, Any]:
        """Get all vulnerabilities for a host."""
        vulns = []
        if ip not in self.graph:
            return {"host": ip, "vulnerabilities": [], "count": 0}

        # Traverse: Host -> Port -> Service -> Vuln
        for port_id in self.graph.successors(ip):
            for service_id in self.graph.successors(port_id):
                for vuln_id in self.graph.successors(service_id):
                    node = self.graph.nodes.get(vuln_id, {})
                    if node.get("type") == NodeType.VULNERABILITY.value:
                        vulns.append({
                            "cve": node.get("cve"),
                            "severity": node.get("severity"),
                            "cvss": node.get("cvss"),
                            "service": service_id,
                        })

        return {"host": ip, "vulnerabilities": vulns, "count": len(vulns)}

    def get_exploits_for_cve(self, cve: str) -> Dict[str, Any]:
        """Get all exploits for a CVE."""
        vuln_id = f"vuln:{cve}"
        if vuln_id not in self.graph:
            return {"error": f"CVE {cve} not found in graph"}

        exploits = []
        for exploit_id in self.graph.successors(vuln_id):
            node = self.graph.nodes.get(exploit_id, {})
            if node.get("type") == NodeType.EXPLOIT.value:
                exploits.append({
                    "name": node.get("name"),
                    "url": node.get("url"),
                    "tested": node.get("tested", False),
                })

        return {"cve": cve, "exploits": exploits, "count": len(exploits)}

    def get_services_for_host(self, ip: str) -> Dict[str, Any]:
        """Get all services for a host."""
        services = []
        if ip not in self.graph:
            return {"host": ip, "services": [], "count": 0}

        for port_id in self.graph.successors(ip):
            port_data = self.graph.nodes.get(port_id, {})
            for service_id in self.graph.successors(port_id):
                node = self.graph.nodes.get(service_id, {})
                if node.get("type") == NodeType.SERVICE.value:
                    services.append({
                        "port": port_data.get("port"),
                        "name": node.get("name"),
                        "version": node.get("version"),
                    })

        return {"host": ip, "services": services, "count": len(services)}

    def get_credentials_for_host(self, ip: str) -> Dict[str, Any]:
        """Get all discovered credentials for a host."""
        creds = []
        if ip not in self.graph:
            return {"host": ip, "credentials": [], "count": 0}

        for node_id in self.graph.successors(ip):
            node = self.graph.nodes.get(node_id, {})
            if node.get("type") == NodeType.CREDENTIAL.value:
                creds.append({
                    "username": node.get("username"),
                    "password": "***" if node.get("password") else "",
                    "source": node.get("source"),
                })

        return {"host": ip, "credentials": creds, "count": len(creds)}

    def get_host_summary(self, ip: str) -> Dict[str, Any]:
        """Get complete summary for a host."""
        if ip not in self.graph:
            return {"error": f"Host {ip} not found"}

        host_data = self.graph.nodes[ip]
        services = self.get_services_for_host(ip)
        vulns = self.get_vulnerabilities_for_host(ip)

        return {
            "host": ip,
            "os": host_data.get("os"),
            "hostname": host_data.get("hostname"),
            "open_ports": len(list(self.graph.successors(ip))),
            "services": services["services"],
            "vulnerabilities": vulns["vulnerabilities"],
            "total_vulns": vulns["count"],
        }

    def get_attack_path(self) -> Dict[str, Any]:
        """Get the exploitation path across all hosts."""
        exploits = []
        for node_id, data in self.graph.nodes(data=True):
            if data.get("type") == NodeType.EXPLOIT.value and data.get("tested"):
                # Trace back to host
                exploits.append({
                    "exploit_id": node_id,
                    "name": data.get("name"),
                    "tested": True,
                })

        return {"attack_path": exploits, "exploit_count": len(exploits)}

    # ═══════════════════════════════════════════════════════════════════════
    # UTILITY
    # ═══════════════════════════════════════════════════════════════════════

    def node_count_delta(self) -> int:
        """Get node count change since last check."""
        current = self.graph.number_of_nodes()
        delta = current - self._node_count_before
        self._node_count_before = current
        return delta

    def edge_count_delta(self) -> int:
        """Get edge count change since last check."""
        current = self.graph.number_of_edges()
        delta = current - self._edge_count_before
        self._edge_count_before = current
        return delta

    def export(self, path: Optional[str] = None) -> dict:
        """Export graph as JSON dict (optionally save to file)."""
        data = nx.node_link_data(self.graph)
        if path:
            with open(path, "w") as f:
                json.dump(data, f, indent=2, default=str)
            logger.info(f"Graph exported to {path}")
        return data

    def import_data(self, data: dict):
        """Import graph from JSON dict."""
        self.graph = nx.node_link_graph(data)
        logger.info(f"Graph imported: {self.graph.number_of_nodes()} nodes")

    def save(self, path: str):
        """Save graph to pickle file."""
        with open(path, "wb") as f:
            pickle.dump(self.graph, f)
        logger.info(f"Graph saved to {path}")

    def load(self, path: str):
        """Load graph from pickle file."""
        with open(path, "rb") as f:
            self.graph = pickle.load(f)
        logger.info(f"Graph loaded from {path}: {self.graph.number_of_nodes()} nodes")

    def get_stats(self) -> Dict[str, int]:
        """Get graph statistics."""
        type_counts = {}
        for _, data in self.graph.nodes(data=True):
            ntype = data.get("type", "unknown")
            type_counts[ntype] = type_counts.get(ntype, 0) + 1

        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "node_types": type_counts,
        }


# ── Global Instance ──────────────────────────────────────────────────────────

_graph_instance: Optional[PentestKnowledgeGraph] = None


def get_knowledge_graph() -> PentestKnowledgeGraph:
    """Get global graph instance (singleton)."""
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = PentestKnowledgeGraph()
    return _graph_instance
