"""
Temporal Activities — Discrete retryable tasks for RedClaw V3.1

Each activity is a standalone unit of work that can be:
  - Retried automatically on failure
  - Timed out independently
  - Run on any worker in the cluster

Also works without Temporal as regular async functions.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import tempfile
from typing import Any, Dict

logger = logging.getLogger("redclaw.orchestrator.activities")

# Try to import Temporal activity decorator
try:
    from temporalio import activity
    HAS_TEMPORAL = True
except ImportError:
    HAS_TEMPORAL = False
    # Create no-op decorator
    class _FakeActivity:
        @staticmethod
        def defn(fn):
            return fn
    activity = _FakeActivity()


# ── Tool Activities ──────────────────────────────────────────────────────────


@activity.defn
async def run_nmap_activity(target: str) -> Dict[str, Any]:
    """
    Run nmap scan on target.

    Returns structured results with open ports and services.
    """
    logger.info(f"Running nmap on {target}")

    try:
        cmd = [
            "nmap", "-sV", "-p-", "--min-rate=1000",
            target, "-oX", os.path.join(tempfile.gettempdir(), "nmap_scan.xml"),
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=1800  # 30 min max
        )

        # Parse results (simplified — production would use python-nmap)
        output = stdout.decode("utf-8", errors="replace")

        # Extract open ports from nmap output
        open_ports = []
        services = []
        import re
        for line in output.split("\n"):
            port_match = re.match(r"(\d+)/tcp\s+open\s+(\S+)\s*(.*)", line)
            if port_match:
                port = int(port_match.group(1))
                service_name = port_match.group(2)
                version = port_match.group(3).strip()
                open_ports.append(port)
                services.append({
                    "port": port,
                    "name": service_name,
                    "version": version,
                })

        return {
            "target": target,
            "open_ports": open_ports,
            "services": services,
            "raw_output_length": len(output),
        }

    except FileNotFoundError:
        logger.warning("nmap not found in PATH")
        return {"target": target, "open_ports": [], "services": [], "error": "nmap not installed"}

    except asyncio.TimeoutError:
        logger.warning(f"nmap scan of {target} timed out")
        return {"target": target, "open_ports": [], "services": [], "error": "timeout"}

    except Exception as e:
        logger.error(f"nmap scan failed: {e}")
        return {"target": target, "open_ports": [], "services": [], "error": str(e)}


@activity.defn
async def run_nuclei_activity(target: str) -> Dict[str, Any]:
    """Run Nuclei vulnerability scanner."""
    logger.info(f"Running nuclei on {target}")

    try:
        cmd = ["nuclei", "-target", target, "-j", "-silent"]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=1200)
        output = stdout.decode("utf-8", errors="replace")

        # Parse JSON lines output
        vulnerabilities = []
        for line in output.strip().split("\n"):
            if line.strip():
                try:
                    vuln = json.loads(line)
                    vulnerabilities.append({
                        "template_id": vuln.get("template-id", ""),
                        "name": vuln.get("info", {}).get("name", ""),
                        "severity": vuln.get("info", {}).get("severity", ""),
                        "matched_at": vuln.get("matched-at", ""),
                    })
                except json.JSONDecodeError:
                    pass

        return {"target": target, "vulnerabilities": vulnerabilities}

    except FileNotFoundError:
        logger.warning("nuclei not found in PATH")
        return {"target": target, "vulnerabilities": [], "error": "nuclei not installed"}

    except Exception as e:
        return {"target": target, "vulnerabilities": [], "error": str(e)}


@activity.defn
async def run_dirb_activity(url: str) -> Dict[str, Any]:
    """Run directory enumeration."""
    logger.info(f"Running dirb on {url}")

    try:
        cmd = ["dirb", url, "-S", "-r", "-o", os.path.join(tempfile.gettempdir(), "dirb_output.txt")]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=900)
        output = stdout.decode("utf-8", errors="replace")

        # Parse found paths
        paths = []
        import re
        for line in output.split("\n"):
            if "CODE:" in line:
                url_match = re.search(r'\+ (http\S+)', line)
                code_match = re.search(r'CODE:(\d+)', line)
                if url_match:
                    paths.append({
                        "url": url_match.group(1),
                        "status_code": int(code_match.group(1)) if code_match else 0,
                    })

        return {"url": url, "paths": paths}

    except FileNotFoundError:
        logger.warning("dirb not found in PATH")
        return {"url": url, "paths": [], "error": "dirb not installed"}

    except Exception as e:
        return {"url": url, "paths": [], "error": str(e)}


# ── Graph Activities ─────────────────────────────────────────────────────────


@activity.defn
async def ingest_to_graph_activity(data: Dict[str, Any]) -> Dict[str, Any]:
    """Ingest scan results into Knowledge Graph."""
    from ..memory.knowledge_graph import get_knowledge_graph

    logger.info(f"Ingesting data to graph for {data['target']}")
    graph = get_knowledge_graph()

    target = data["target"]
    results = data.get("results", [])

    # Add host
    graph.add_host(target)

    # Process nmap results (first result)
    if results and isinstance(results[0], dict):
        nmap_result = results[0]
        for port in nmap_result.get("open_ports", []):
            graph.add_port(target, port, "open")

        for svc in nmap_result.get("services", []):
            graph.add_service(
                target, svc["port"], svc["name"], svc.get("version")
            )

    # Process nuclei results (second result)
    if len(results) > 1 and isinstance(results[1], dict):
        nuclei_result = results[1]
        for vuln in nuclei_result.get("vulnerabilities", []):
            # Link to appropriate service if possible
            matched_at = vuln.get("matched_at", "")
            service_id = f"{target}:80:http"  # Default
            graph.add_vulnerability(
                service_id,
                vuln.get("template_id", "unknown"),
                vuln.get("severity", "info"),
            )

    return {
        "nodes_added": graph.node_count_delta(),
        "edges_added": graph.edge_count_delta(),
    }


@activity.defn
async def query_knowledge_graph_activity(query: str) -> Dict[str, Any]:
    """Query Knowledge Graph with natural language."""
    from ..memory.knowledge_graph import get_knowledge_graph

    logger.info(f"Querying graph: {query}")
    graph = get_knowledge_graph()
    return graph.query_natural_language(query)
