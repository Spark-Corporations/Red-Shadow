---
name: report
description: Generate an OSCP-style penetration testing report
invocation: user
arguments:
  - name: format
    description: "Output format: markdown|html|pdf (default: markdown)"
    required: false
  - name: output
    description: Output file path (default: ./output/report.md)
    required: false
tools:
  - Bash
---

# Report Skill — RedClaw v2.0

## Overview
Generate a comprehensive penetration testing report from all findings,
tool outputs, and engagement context.

## Report Sections

1. **Executive Summary** — High-level overview for management
2. **Scope & Methodology** — Targets, tools used, testing approach
3. **Findings Summary** — Severity breakdown table
4. **Detailed Findings** — Each finding with:
   - Title, severity, CVSS score
   - Affected target/service
   - Description and impact
   - Evidence (command output, screenshots)
   - Remediation recommendations
5. **Tool Output Appendix** — Raw scan results
6. **Timeline** — Chronological action log

## Formats

| Format | Description |
|--------|-------------|
| `markdown` | Clean .md file (default) |
| `html` | Styled HTML with CSS |
| `pdf` | PDF via wkhtmltopdf (if available) |

## Example Usage
```
/report
/report html ./output/engagement_report.html
/report markdown
```
