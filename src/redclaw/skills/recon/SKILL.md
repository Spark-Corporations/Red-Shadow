---
name: reconnaissance
description: Reconnaissance and OSINT gathering — DNS, subdomains, live host discovery
phase: reconnaissance
tools: [nmap, masscan]
triggers: ["recon", "scan", "enumerate", "discover", "osint", "dns"]
priority: 1
requires_approval: false
---
# Reconnaissance Skill

## Objective
Gather intelligence about the target environment before active scanning.

## Workflow
1. **DNS Enumeration**: Resolve target domains, find subdomains
2. **Ping Sweep**: Identify live hosts in the target range
3. **Quick Port Scan**: Fast scan (masscan) for open ports on live hosts
4. **Service Detection**: Targeted nmap -sV on discovered ports

## Tools Used
- **nmap**: DNS resolution, ping sweep, service version detection
- **masscan**: Ultra-fast full-port discovery

## Decision Criteria
- Phase complete when: all targets enumerated, live hosts identified, key ports mapped
- Escalate if: network appears segmented or IDS is detected

## Output Format
Report all findings as structured data:
- Live hosts with hostnames
- Open ports per host
- Service banners where available
