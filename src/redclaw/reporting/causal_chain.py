"""
CausalChainReport — Why-What-How-Proof-Fix reporting for RedClaw V3.1

Every finding follows the Causal Chain format:
  WHY: Root cause analysis
  WHAT: Vulnerability details (CVE, CVSS, Service, Impact)
  HOW: Step-by-step exploitation path
  PROOF: Screenshot + evidence (timestamp, HTTP response)
  FIX: Stack-specific remediation (immediate + long-term)

Output formats: HTML (interactive), PDF (executive), JSON (API)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("redclaw.reporting.causal_chain")


class CausalChainReport:
    """
    Generate professional pentest reports in Causal Chain format.

    Usage:
        reporter = CausalChainReport()

        finding = {
            "id": 1,
            "title": "Apache RCE via Path Traversal",
            "cve": "CVE-2021-41773",
            "cvss": 9.8,
            "service": "Apache 2.4.49 on port 80",
            "impact": "Remote Code Execution",
            "root_cause": "Path normalization flaw in Apache 2.4.49",
            "steps": ["Discovered Apache 2.4.49 via nmap", "Queried CVE database", ...],
            "target": {"os": "Ubuntu 20.04", "software": "Apache 2.4.49"},
        }

        validation = {
            "validated": True,
            "proof": {"screenshot_path": "...", "http_status": "200 OK", ...},
        }

        report_text = reporter.generate(finding, validation)
    """

    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = output_dir or os.path.expanduser("~/.redclaw/reports")
        os.makedirs(self.output_dir, exist_ok=True)

    def generate(self, finding: Dict[str, Any], validation: Dict[str, Any]) -> str:
        """Generate a single finding report in Causal Chain format."""
        return f"""
===================================================
FINDING #{finding.get('id', '?')}: {finding.get('title', 'Unknown')}
==================================================="

WHY (Root Cause):
{finding.get('root_cause', 'Unknown root cause')}

WHAT (Vulnerability):
- CVE: {finding.get('cve', 'N/A')}
- CVSS: {finding.get('cvss', 'N/A')}
- Service: {finding.get('service', 'N/A')}
- Impact: {finding.get('impact', 'N/A')}

HOW (Exploitation Path):
{self._format_exploitation_path(finding.get('steps', []))}

PROOF (Evidence):
{self._format_proof(validation.get('proof', {}))}

FIX (Recommendation):
{self._format_fix(finding, validation)}
"""

    def generate_full_report(
        self, results: Dict[str, Any], engagement_name: str = ""
    ) -> Dict[str, str]:
        """
        Generate complete report with all findings.

        Returns dict with report in multiple formats.
        """
        findings = results.get("completed_tasks", [])
        executive_summary = results.get("executive_summary", "")
        attack_path = results.get("attack_path", {})

        # Build report sections
        header = self._build_header(engagement_name)
        exec_section = self._build_executive_summary(executive_summary, findings)
        findings_section = self._build_findings_section(findings)
        attack_section = self._build_attack_path_section(attack_path)
        remediation = self._build_remediation_section(findings)

        # Combine
        full_text = "\n".join([
            header, exec_section, findings_section,
            attack_section, remediation,
        ])

        # JSON format
        json_report = {
            "engagement": engagement_name,
            "generated_at": datetime.now().isoformat(),
            "executive_summary": executive_summary,
            "findings": findings,
            "attack_path": attack_path,
            "total_findings": len(findings),
        }

        return {
            "text": full_text,
            "json": json.dumps(json_report, indent=2, default=str),
        }

    # ── Format Helpers ────────────────────────────────────────────────────

    def _format_exploitation_path(self, steps: List[str]) -> str:
        if not steps:
            return "  No exploitation steps recorded"
        return "\n".join(f"  {i+1}. {step}" for i, step in enumerate(steps))

    def _format_proof(self, proof: Dict[str, Any]) -> str:
        if not proof:
            return "  No proof captured"
        lines = []
        if proof.get("screenshot_path"):
            lines.append(f"  [Screenshot: {proof['screenshot_path']}]")
        if proof.get("http_status"):
            lines.append(f"  [HTTP Response: {proof['http_status']}]")
        if proof.get("response_size"):
            lines.append(f"  [Response Size: {proof['response_size']} bytes]")
        lines.append(f"  Timestamp: {proof.get('timestamp', datetime.now().isoformat())}")
        return "\n".join(lines) if lines else "  Evidence pending"

    def _format_fix(self, finding: Dict, validation: Dict) -> str:
        target = finding.get("target", {})
        os_name = target.get("os", "Unknown OS") if isinstance(target, dict) else str(target)
        software = target.get("software", "Unknown") if isinstance(target, dict) else ""

        severity = finding.get("cvss", 0)
        priority = "CRITICAL" if severity >= 9.0 else "HIGH" if severity >= 7.0 else "MEDIUM" if severity >= 4.0 else "LOW"

        return f"""  Target Stack: {os_name} + {software}

  Immediate:
  1. Patch {finding.get('service', 'affected service')} to latest version
  2. Verify patch applied successfully
  3. Restart affected services

  Long-term:
  - Enable automatic security updates
  - Implement WAF rules
  - Regular vulnerability scanning

  Priority: {priority} (CVSS {severity})"""

    # ── Report Sections ───────────────────────────────────────────────────

    def _build_header(self, engagement_name: str) -> str:
        return f"""
+==============================================================+
|              REDCLAW PENETRATION TEST REPORT                |
|                                                              |
|  Engagement: {engagement_name:<46}|
|  Date: {datetime.now().strftime('%Y-%m-%d %H:%M'):<51}|
|  Generated by: RedClaw V3.1                                 |
+==============================================================+
"""

    def _build_executive_summary(self, summary: str, findings: list) -> str:
        critical = sum(1 for f in findings if f.get("cvss", 0) >= 9.0)
        high = sum(1 for f in findings if 7.0 <= f.get("cvss", 0) < 9.0)

        return f"""
--------------------------------------------------------------
EXECUTIVE SUMMARY
--------------------------------------------------------------

{summary}

Total Findings: {len(findings)}
  Critical: {critical}
  High: {high}
  Other: {len(findings) - critical - high}
"""

    def _build_findings_section(self, findings: list) -> str:
        if not findings:
            return "\n  No exploitable vulnerabilities confirmed.\n"

        sections = ["\n======================================\nDETAILED FINDINGS\n======================================\n"]
        for i, finding in enumerate(findings, 1):
            validation = finding.get("validation", {})
            finding["id"] = i
            sections.append(self.generate(finding, validation))
        return "\n".join(sections)

    def _build_attack_path_section(self, attack_path: Dict) -> str:
        return f"""
--------------------------------------------------------------
ATTACK PATH
--------------------------------------------------------------

{json.dumps(attack_path, indent=2, default=str) if attack_path else 'No exploitation path recorded.'}
"""

    def _build_remediation_section(self, findings: list) -> str:
        return f"""
--------------------------------------------------------------
REMEDIATION SUMMARY
--------------------------------------------------------------

Total findings requiring remediation: {len(findings)}

Priority Matrix:
  [!!!] Critical (patch within 24h): {sum(1 for f in findings if f.get('cvss', 0) >= 9.0)}
  [!!]  High (patch within 7 days): {sum(1 for f in findings if 7.0 <= f.get('cvss', 0) < 9.0)}
  [!]   Medium (patch within 30 days): {sum(1 for f in findings if 4.0 <= f.get('cvss', 0) < 7.0)}
  [-]   Low (patch within 90 days): {sum(1 for f in findings if f.get('cvss', 0) < 4.0)}
"""

    # ── Export ────────────────────────────────────────────────────────────

    def export_text(self, report: Dict[str, str], filename: str = "report.txt"):
        """Save report as plain text."""
        path = os.path.join(self.output_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(report["text"])
        logger.info(f"Report exported: {path}")
        return path

    def export_json(self, report: Dict[str, str], filename: str = "report.json"):
        """Save report as JSON."""
        path = os.path.join(self.output_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(report["json"])
        logger.info(f"Report exported: {path}")
        return path
