"""
ReportGenerator — Generates structured penetration testing reports.

Produces reports in Markdown and HTML formats with:
  - Executive summary
  - Methodology description
  - Findings table with severity ratings
  - Evidence and proof-of-concept details
  - Remediation recommendations
  - Timeline and audit trail
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("redclaw.reporting.generator")


class ReportGenerator:
    """
    Generates engagement reports from pipeline state and findings.

    Usage:
        gen = ReportGenerator(state_manager)
        gen.generate_markdown("./output/report.md")
        gen.generate_html("./output/report.html")
    """

    def __init__(self, state_manager=None, config_manager=None):
        self._state = state_manager
        self._config = config_manager
        logger.info("ReportGenerator initialized")

    def generate_markdown(self, output_path: str | Path, title: str = "Penetration Test Report") -> str:
        """Generate a Markdown report."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            f"# {title}",
            f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Tool**: RedClaw v2.0 (OpenClaw Runtime + Kaggle Phi-4)",
            "",
            "---",
            "",
            "## Executive Summary",
            "",
        ]

        # Add findings summary
        findings = self._get_findings()
        severity_counts = self._count_by_severity(findings)

        lines.append(f"Total findings: **{len(findings)}**\n")
        lines.append("| Severity | Count |")
        lines.append("|----------|-------|")
        for sev in ["critical", "high", "medium", "low", "info"]:
            count = severity_counts.get(sev, 0)
            if count > 0:
                lines.append(f"| {sev.upper()} | {count} |")

        lines.extend(["", "---", "", "## Methodology", ""])
        lines.append("The assessment followed an 8-phase automated penetration testing pipeline:")
        lines.append("1. **Planning** — Scope validation and configuration")
        lines.append("2. **Reconnaissance** — OSINT, DNS, and host discovery")
        lines.append("3. **Scanning** — Port scanning and service detection")
        lines.append("4. **Vulnerability Assessment** — Automated vulnerability scanning")
        lines.append("5. **Exploitation** — Controlled exploitation of confirmed vulnerabilities")
        lines.append("6. **Post-Exploitation** — Privilege escalation and lateral movement")
        lines.append("7. **Reporting** — This report")
        lines.append("8. **Cleanup** — Artifact removal and session cleanup")

        # Findings detail
        lines.extend(["", "---", "", "## Detailed Findings", ""])

        for i, finding in enumerate(findings, 1):
            sev = finding.get("severity", "info").upper()
            title_text = finding.get("title", f"Finding #{i}")
            lines.append(f"### {i}. [{sev}] {title_text}")
            lines.append("")
            if desc := finding.get("description"):
                lines.append(f"**Description**: {desc}")
            if phase := finding.get("phase"):
                lines.append(f"**Phase**: {phase}")
            if details := finding.get("details"):
                lines.append(f"\n```\n{details[:2000]}\n```")
            lines.append("")

        # Recommendations
        lines.extend(["---", "", "## Recommendations", ""])
        critical_findings = [f for f in findings if f.get("severity") in ("critical", "high")]
        if critical_findings:
            for f in critical_findings:
                lines.append(f"- **Remediate**: {f.get('title', 'N/A')}")
        else:
            lines.append("No critical or high-severity findings. Standard hardening recommended.")

        report_text = "\n".join(lines)
        output_path.write_text(report_text, encoding="utf-8")
        logger.info(f"Markdown report generated: {output_path}")
        return report_text

    def generate_html(self, output_path: str | Path, title: str = "Penetration Test Report") -> str:
        """Generate an HTML report from the Markdown content."""
        md_content = self.generate_markdown(
            Path(output_path).with_suffix(".md"), title=title
        )

        # Simple Markdown-to-HTML conversion
        html = self._markdown_to_html(md_content, title)
        output_path = Path(output_path)
        output_path.write_text(html, encoding="utf-8")
        logger.info(f"HTML report generated: {output_path}")
        return html

    def _get_findings(self) -> list[dict[str, Any]]:
        """Get findings from the state manager."""
        if self._state and hasattr(self._state, "state"):
            return [
                {
                    "id": f.id,
                    "title": f.title,
                    "severity": f.severity,
                    "description": f.description,
                    "phase": f.phase,
                    "details": getattr(f, "details", ""),
                }
                for f in self._state.state.findings
            ]
        return []

    def _count_by_severity(self, findings: list[dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in findings:
            s = f.get("severity", "info")
            counts[s] = counts.get(s, 0) + 1
        return counts

    def _markdown_to_html(self, md: str, title: str) -> str:
        """Basic Markdown-to-HTML conversion."""
        html_lines = [
            "<!DOCTYPE html>",
            "<html><head>",
            f"<title>{title}</title>",
            '<meta charset="utf-8">',
            "<style>",
            "  body { font-family: 'Segoe UI', sans-serif; max-width: 900px; margin: 0 auto; padding: 2rem; background: #1a1a2e; color: #e0e0e0; }",
            "  h1, h2, h3 { color: #ff4444; }",
            "  table { border-collapse: collapse; width: 100%; margin: 1rem 0; }",
            "  th, td { border: 1px solid #333; padding: 8px; text-align: left; }",
            "  th { background: #2a2a3e; }",
            "  code, pre { background: #0d0d1a; padding: 2px 6px; border-radius: 4px; }",
            "  pre { padding: 1rem; overflow-x: auto; }",
            "  hr { border: 1px solid #333; }",
            "</style>",
            "</head><body>",
        ]

        for line in md.split("\n"):
            if line.startswith("### "):
                html_lines.append(f"<h3>{line[4:]}</h3>")
            elif line.startswith("## "):
                html_lines.append(f"<h2>{line[3:]}</h2>")
            elif line.startswith("# "):
                html_lines.append(f"<h1>{line[2:]}</h1>")
            elif line.startswith("---"):
                html_lines.append("<hr>")
            elif line.startswith("| "):
                # Table row
                cells = [c.strip() for c in line.split("|")[1:-1]]
                if all(c.startswith("-") for c in cells):
                    continue  # separator row
                row = "".join(f"<td>{c}</td>" for c in cells)
                html_lines.append(f"<tr>{row}</tr>")
            elif line.startswith("- "):
                html_lines.append(f"<li>{line[2:]}</li>")
            elif line.startswith("```"):
                html_lines.append("<pre><code>" if "```" == line.strip() else "</code></pre>")
            else:
                html_lines.append(f"<p>{line}</p>" if line.strip() else "<br>")

        html_lines.append("</body></html>")
        return "\n".join(html_lines)
