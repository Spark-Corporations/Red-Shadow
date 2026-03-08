"""
OutputCleaner — Parse and structure raw tool output before sending to LLM.

The #1 problem with function calling + pentesting tools: raw output is enormous.
A single nmap -sV scan can generate 10,000+ lines. Sending this raw to the LLM:
  - Wastes tokens (cost + latency)
  - Overflows context window
  - Degrades reasoning quality (signal buried in noise)

Solution: parse tool output into structured, concise summaries.
"""

from __future__ import annotations

import json
import re
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("redclaw.tools.output_cleaner")


@dataclass
class CleanedOutput:
    """Structured output from a tool, ready for LLM consumption."""
    tool: str
    success: bool
    summary: str           # 1-2 sentence executive summary
    structured: dict       # Parsed data (ports, vulns, etc.)
    raw_length: int        # Original output length
    cleaned_length: int    # Cleaned output length
    warnings: list[str] = field(default_factory=list)
    response_class: str = "unknown"  # ResponseClassifier result

    def to_llm_context(self) -> str:
        """Format for LLM context — concise and structured."""
        parts = [f"[{self.tool}] {self.summary}"]
        if self.structured:
            parts.append(json.dumps(self.structured, indent=1, ensure_ascii=False))
        if self.warnings:
            parts.append("Warnings: " + "; ".join(self.warnings))
        result = "\n".join(parts)
        self.cleaned_length = len(result)
        return result


class OutputCleaner:
    """
    Central output cleaning/parsing engine.

    Knows how to parse output from specific tools (nmap, nuclei, sqlmap, etc.)
    and falls back to generic truncation for unknown tools.

    Usage:
        cleaner = OutputCleaner(max_chars=4000)
        cleaned = cleaner.clean("nmap", raw_output)
        llm_context = cleaned.to_llm_context()
    """

    def __init__(self, max_chars: int = 4000):
        self._max_chars = max_chars
        self._parsers = {
            "nmap": self._parse_nmap,
            "nuclei": self._parse_nuclei,
            "sqlmap": self._parse_sqlmap,
            "gobuster": self._parse_gobuster,
            "ffuf": self._parse_ffuf,
            "hydra": self._parse_hydra,
        }

    def clean(self, tool_name: str, raw_output: str, success: bool = True,
              status_code: int = 0, headers: dict = None) -> CleanedOutput:
        """
        Clean and structure tool output + classify response.

        Args:
            tool_name: Name of the tool (nmap, nuclei, etc.)
            raw_output: Raw stdout/stderr from the tool
            success: Whether the tool execution succeeded
            status_code: HTTP status code (0 if not HTTP)
            headers: HTTP response headers (optional)

        Returns:
            CleanedOutput with structured data + response_class
        """
        # Normalize tool name
        tool_key = tool_name.lower().split("/")[-1].split("_")[0]

        parser = self._parsers.get(tool_key, self._parse_generic)

        try:
            result = parser(raw_output, success)
            result.tool = tool_name
            result.raw_length = len(raw_output)

            # Classify the response for adaptive mutation
            try:
                from redclaw.openclaw_bridge.adaptive_mutation import ResponseClassifier
                classifier = ResponseClassifier()
                classified = classifier.classify(raw_output, status_code, headers or {})
                result.response_class = classified.classification.value
                if classified.signals:
                    result.warnings.extend(classified.signals[:3])
            except ImportError:
                pass

            logger.info(
                f"OutputCleaner: {tool_name} "
                f"{len(raw_output)} chars → {result.cleaned_length} chars "
                f"({100 - (result.cleaned_length / max(len(raw_output), 1)) * 100:.0f}% reduction) "
                f"[{result.response_class}]"
            )
            return result
        except Exception as e:
            logger.warning(f"Parser failed for {tool_name}: {e}. Falling back to generic.")
            return self._parse_generic(raw_output, success)

    # ── Nmap Parser ───────────────────────────────────────────────────────

    def _parse_nmap(self, output: str, success: bool) -> CleanedOutput:
        """Parse nmap output into structured port/service data."""
        ports = []
        os_info = []
        scripts = []
        warnings = []
        host_status = "unknown"

        for line in output.split("\n"):
            line = line.strip()

            # Host status
            if "Host is up" in line:
                host_status = "up"
                latency_match = re.search(r"\(([\d.]+)s latency\)", line)
                if latency_match:
                    host_status = f"up ({latency_match.group(1)}s latency)"

            # Port lines: "22/tcp   open  ssh     OpenSSH 8.2p1"
            port_match = re.match(
                r"(\d+)/(tcp|udp)\s+(open|closed|filtered)\s+(\S+)\s*(.*)",
                line
            )
            if port_match:
                port_info = {
                    "port": int(port_match.group(1)),
                    "proto": port_match.group(2),
                    "state": port_match.group(3),
                    "service": port_match.group(4),
                    "version": port_match.group(5).strip(),
                }
                ports.append(port_info)
                continue

            # OS detection
            if line.startswith("OS details:") or line.startswith("Running:"):
                os_info.append(line)

            # Script output (CVE mentions, vulns)
            if "|" in line and ("VULNERABLE" in line.upper() or "CVE-" in line.upper()):
                scripts.append(line.strip("| ").strip())

            # Warnings
            if "warning" in line.lower() or "error" in line.lower():
                warnings.append(line[:200])

        # Build summary
        open_ports = [p for p in ports if p["state"] == "open"]
        summary = f"Host {host_status}. {len(open_ports)} open port(s) found."
        if open_ports:
            port_list = ", ".join(f"{p['port']}/{p['proto']}({p['service']})" for p in open_ports[:10])
            summary += f" Ports: {port_list}"
        if scripts:
            summary += f" ⚠️ {len(scripts)} potential vulnerability(s) found."

        structured = {
            "host_status": host_status,
            "open_ports": open_ports,
            "closed_filtered": [p for p in ports if p["state"] != "open"],
            "os": os_info,
            "vulns_from_scripts": scripts,
        }

        result = CleanedOutput(
            tool="nmap", success=success, summary=summary,
            structured=structured, raw_length=len(output), cleaned_length=0,
            warnings=warnings[:5],
        )
        result.to_llm_context()  # compute cleaned_length
        return result

    # ── Nuclei Parser ─────────────────────────────────────────────────────

    def _parse_nuclei(self, output: str, success: bool) -> CleanedOutput:
        """Parse nuclei output into structured vulnerability findings."""
        findings = []
        info_count = 0
        warnings = []

        for line in output.split("\n"):
            line = line.strip()
            if not line:
                continue

            # Nuclei output format: [severity] [template-id] [protocol] url [extra]
            # Or ANSI-stripped: [2024-01-01] [template-id] [severity] [protocol] url
            severity_match = re.search(
                r"\[(critical|high|medium|low|info|unknown)\]",
                line, re.IGNORECASE
            )
            if severity_match:
                severity = severity_match.group(1).lower()

                # Extract template ID
                template_match = re.search(r"\[([a-zA-Z0-9_-]+)\]", line)
                template = template_match.group(1) if template_match else "unknown"

                # Extract URL
                url_match = re.search(r"(https?://\S+)", line)
                url = url_match.group(1) if url_match else ""

                if severity == "info":
                    info_count += 1
                else:
                    findings.append({
                        "severity": severity,
                        "template": template,
                        "url": url,
                        "raw": line[:300],
                    })

            if "error" in line.lower():
                warnings.append(line[:200])

        # Sort by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unknown": 4}
        findings.sort(key=lambda x: severity_order.get(x["severity"], 5))

        summary = f"{len(findings)} vulnerability(s) found"
        if findings:
            by_sev = {}
            for f in findings:
                by_sev.setdefault(f["severity"], 0)
                by_sev[f["severity"]] += 1
            sev_str = ", ".join(f"{s}: {c}" for s, c in by_sev.items())
            summary += f" ({sev_str})"
        summary += f". {info_count} info findings filtered."

        result = CleanedOutput(
            tool="nuclei", success=success, summary=summary,
            structured={"findings": findings[:50], "info_count": info_count},
            raw_length=len(output), cleaned_length=0,
            warnings=warnings[:5],
        )
        result.to_llm_context()
        return result

    # ── Sqlmap Parser ─────────────────────────────────────────────────────

    def _parse_sqlmap(self, output: str, success: bool) -> CleanedOutput:
        """Parse sqlmap output into structured injection findings."""
        injections = []
        databases = []
        tables = []
        warnings = []
        is_vulnerable = False

        for line in output.split("\n"):
            line = line.strip()

            # Injection point found
            if "is vulnerable" in line.lower() or "injectable" in line.lower():
                is_vulnerable = True
                injections.append(line[:300])

            # Type of injection
            type_match = re.search(r"Type:\s*(.+)", line)
            if type_match:
                injections.append(f"Type: {type_match.group(1)}")

            # Databases
            if line.startswith("[*]") and "available databases" not in line.lower():
                item = line.lstrip("[*] ").strip()
                if item:
                    databases.append(item)

            # DBMS info
            if "back-end DBMS" in line.lower():
                injections.append(line[:300])

            if "warning" in line.lower():
                warnings.append(line[:200])

        summary = "SQL injection " + ("FOUND" if is_vulnerable else "not found") + "."
        if databases:
            summary += f" {len(databases)} database(s) enumerated."

        result = CleanedOutput(
            tool="sqlmap", success=success, summary=summary,
            structured={
                "vulnerable": is_vulnerable,
                "injections": injections[:20],
                "databases": databases[:30],
            },
            raw_length=len(output), cleaned_length=0,
            warnings=warnings[:5],
        )
        result.to_llm_context()
        return result

    # ── Gobuster Parser ───────────────────────────────────────────────────

    def _parse_gobuster(self, output: str, success: bool) -> CleanedOutput:
        """Parse gobuster output into discovered paths."""
        paths = []
        warnings = []

        for line in output.split("\n"):
            line = line.strip()

            # Gobuster dir mode: /path (Status: 200) [Size: 1234]
            path_match = re.match(r"(/\S+)\s+\(Status:\s*(\d+)\)(?:\s+\[Size:\s*(\d+)\])?", line)
            if path_match:
                paths.append({
                    "path": path_match.group(1),
                    "status": int(path_match.group(2)),
                    "size": int(path_match.group(3)) if path_match.group(3) else None,
                })
                continue

            # Alternate format: /path              (Status: 200)
            alt_match = re.match(r"(/\S+)\s+(\d{3})\s", line)
            if alt_match:
                paths.append({
                    "path": alt_match.group(1),
                    "status": int(alt_match.group(2)),
                })

            if "error" in line.lower():
                warnings.append(line[:200])

        # Group by status code
        by_status = {}
        for p in paths:
            by_status.setdefault(p["status"], []).append(p["path"])

        summary = f"{len(paths)} path(s) discovered."
        if by_status:
            status_str = ", ".join(f"{s}: {len(ps)}" for s, ps in sorted(by_status.items()))
            summary += f" Status codes: {status_str}"

        result = CleanedOutput(
            tool="gobuster", success=success, summary=summary,
            structured={"paths": paths[:100], "by_status": {str(k): v for k, v in by_status.items()}},
            raw_length=len(output), cleaned_length=0,
            warnings=warnings[:5],
        )
        result.to_llm_context()
        return result

    # ── Ffuf Parser ───────────────────────────────────────────────────────

    def _parse_ffuf(self, output: str, success: bool) -> CleanedOutput:
        """Parse ffuf output into discovered endpoints."""
        results = []
        warnings = []

        for line in output.split("\n"):
            line = line.strip()

            # ffuf output: URL [Status: 200, Size: 1234, Words: 56, Lines: 12]
            match = re.match(
                r"(\S+)\s+\[Status:\s*(\d+),\s*Size:\s*(\d+),\s*Words:\s*(\d+),\s*Lines:\s*(\d+)\]",
                line
            )
            if match:
                results.append({
                    "url": match.group(1),
                    "status": int(match.group(2)),
                    "size": int(match.group(3)),
                    "words": int(match.group(4)),
                    "lines": int(match.group(5)),
                })

            if "error" in line.lower():
                warnings.append(line[:200])

        summary = f"{len(results)} endpoint(s) discovered by ffuf."

        result = CleanedOutput(
            tool="ffuf", success=success, summary=summary,
            structured={"results": results[:100]},
            raw_length=len(output), cleaned_length=0,
            warnings=warnings[:5],
        )
        result.to_llm_context()
        return result

    # ── Hydra Parser ──────────────────────────────────────────────────────

    def _parse_hydra(self, output: str, success: bool) -> CleanedOutput:
        """Parse hydra output into cracked credentials."""
        credentials = []
        warnings = []

        for line in output.split("\n"):
            line = line.strip()

            # Hydra: [22][ssh] host: 10.10.10.5   login: admin   password: admin123
            cred_match = re.search(
                r"\[(\d+)\]\[(\w+)\]\s+host:\s*(\S+)\s+login:\s*(\S+)\s+password:\s*(\S+)",
                line
            )
            if cred_match:
                credentials.append({
                    "port": int(cred_match.group(1)),
                    "service": cred_match.group(2),
                    "host": cred_match.group(3),
                    "login": cred_match.group(4),
                    "password": cred_match.group(5),
                })

            if "error" in line.lower():
                warnings.append(line[:200])

        summary = f"{len(credentials)} credential(s) found." if credentials else "No credentials cracked."

        result = CleanedOutput(
            tool="hydra", success=success, summary=summary,
            structured={"credentials": credentials},
            raw_length=len(output), cleaned_length=0,
            warnings=warnings[:5],
        )
        result.to_llm_context()
        return result

    # ── Generic Parser ────────────────────────────────────────────────────

    def _parse_generic(self, output: str, success: bool) -> CleanedOutput:
        """Fallback parser — smart truncation for unknown tools."""
        lines = output.split("\n")
        total_lines = len(lines)

        if len(output) <= self._max_chars:
            return CleanedOutput(
                tool="generic", success=success,
                summary=f"{total_lines} lines of output.",
                structured={"output": output},
                raw_length=len(output), cleaned_length=len(output),
            )

        # Smart truncation: first 40 + last 20 lines
        head = "\n".join(lines[:40])
        tail = "\n".join(lines[-20:])
        truncated = f"{head}\n\n... [{total_lines - 60} lines omitted] ...\n\n{tail}"

        if len(truncated) > self._max_chars:
            truncated = truncated[:self._max_chars - 50] + f"\n[TRUNCATED: {len(output)} chars total]"

        return CleanedOutput(
            tool="generic", success=success,
            summary=f"{total_lines} lines of output (truncated from {len(output)} chars).",
            structured={"output": truncated},
            raw_length=len(output), cleaned_length=len(truncated),
        )
