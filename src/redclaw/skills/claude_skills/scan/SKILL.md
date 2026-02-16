---
name: scan
description: Run a comprehensive scan on a target (Nmap + Masscan pipeline)
invocation: user
arguments:
  - name: target
    description: IP address, hostname, or CIDR range to scan
    required: true
  - name: options
    description: "Additional scan options: full|quick|stealth|udp"
    required: false
tools:
  - Bash
  - redclaw-nmap
  - redclaw-masscan
---

# Scan Skill — RedClaw v2.0

## Overview
Run a comprehensive network scan on the specified target using Nmap and Masscan.

## Workflow

1. **Quick Discovery** (Masscan)
   - Ultra-fast SYN scan on all 65535 ports
   - Identify open ports in seconds
   - Command: `masscan -p0-65535 --rate=1000 <target>`

2. **Detailed Scan** (Nmap)
   - Service version detection on discovered ports
   - OS fingerprinting
   - NSE vulnerability scripts
   - Command: `nmap -sV -sC -O -p <ports> <target>`

3. **Results Analysis**
   - Parse scan output
   - Identify interesting services (HTTP, SMB, SSH, RDP)
   - Flag potential vulnerabilities
   - Generate findings with severity ratings

## Scan Modes

| Mode | Description |
|------|-------------|
| `full` | All ports + all NSE scripts (slow but thorough) |
| `quick` | Top 1000 ports + version detection (default) |
| `stealth` | SYN scan with timing control (-T2) |
| `udp` | UDP scan on common ports + TCP scan |

## Example Usage
```
/scan 10.10.10.5
/scan 192.168.1.0/24 full
/scan target.htb stealth
```

## Safety
- All scans pass through GuardianRails validation
- Rate limiting is enforced (default: 1000 pps)
- Scope check: target must be within engagement scope
