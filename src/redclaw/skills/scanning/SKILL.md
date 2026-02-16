---
name: scanning
description: Port scanning and service version detection
phase: scanning
tools: [nmap, masscan]
triggers: ["scan", "ports", "services", "version"]
priority: 2
requires_approval: false
---
# Scanning Skill

## Objective
Comprehensive port and service enumeration on all discovered targets.

## Workflow
1. Full TCP port scan (masscan --rate 10000)
2. Targeted service detection (nmap -sV -sC) on open ports
3. UDP scan on common ports (nmap -sU --top-ports 100)
4. OS fingerprinting (nmap -O) where possible

## Output
- Complete port map per target
- Service versions with CPE identifiers
- OS detection results
