---
name: vulnerability_assessment
description: Vulnerability scanning with Nuclei and Nmap NSE scripts
phase: vulnerability_assessment
tools: [nuclei, nmap]
triggers: ["vuln", "vulnerability", "cve", "exploit-db", "nuclei"]
priority: 3
requires_approval: false
---
# Vulnerability Assessment Skill

## Objective
Identify vulnerabilities in discovered services using templated scanning.

## Workflow
1. Run Nuclei with critical + high severity templates against all targets
2. Run Nmap NSE vulnerability scripts (--script vuln) on key services
3. Cross-reference findings with CVE databases
4. Prioritize findings by severity and exploitability

## Tools
- **nuclei**: Template-based vulnerability scanner (JSONL output)
- **nmap**: NSE vulnerability scripts for targeted checks

## Decision Criteria
- Phase complete when: all discovered services scanned, findings prioritized
- Escalate if: critical RCE vulnerabilities found
