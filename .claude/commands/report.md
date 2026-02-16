Generate a comprehensive penetration testing report for the current engagement.

Output path: $ARGUMENTS (default: ./output/report.md)

## Report Structure:
1. **Executive Summary** — High-level overview for management
2. **Scope & Methodology** — Targets, tools used, timeline
3. **Findings Summary** — Table of all findings by severity
4. **Detailed Findings** — Each finding with:
   - Severity (Critical/High/Medium/Low/Info)
   - CVSS score
   - Description
   - Evidence (command output, screenshots)
   - Remediation steps
5. **Appendix** — Raw tool outputs, scan logs

## Steps:
1. Read all findings from `~/.redclaw/state/pipeline_state.json`
2. Generate the report in Markdown format
3. Save to the specified output path

Use the Bash tool to create the report file.
