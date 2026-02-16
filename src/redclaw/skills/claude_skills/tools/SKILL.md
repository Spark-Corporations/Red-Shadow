---
name: tools
description: List all available pentesting tools and their installation status
invocation: user
tools:
  - Bash
---

# Tools Skill — RedClaw v2.0

## Overview
List all 10 MCP pentesting tool servers with:
- Installation status (✅ installed / ❌ missing)
- Detected version
- Binary path
- MCP server name

## Tool Catalog

| # | Tool | MCP Server | Category |
|---|------|-----------|----------|
| 1 | Nmap | redclaw-nmap | Scanning |
| 2 | Masscan | redclaw-masscan | Scanning |
| 3 | Nuclei | redclaw-nuclei | Vuln Assessment |
| 4 | Metasploit | redclaw-msf | Exploitation |
| 5 | SQLMap | redclaw-sqlmap | Exploitation |
| 6 | Hydra | redclaw-hydra | Brute-Force |
| 7 | LinPEAS | redclaw-linpeas | Post-Exploitation |
| 8 | WinPEAS | redclaw-winpeas | Post-Exploitation |
| 9 | BloodHound | redclaw-bloodhound | AD Analysis |
| 10 | Custom | redclaw-custom | Custom Scripts |

## Example Usage
```
/tools
```

Run `/doctor` for detailed health check or `/setup-tools` to install missing tools.
