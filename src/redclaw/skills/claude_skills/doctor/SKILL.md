---
name: doctor
description: Health check — verify all tool dependencies and system status
invocation: user
tools:
  - Bash
---

# Doctor Skill — RedClaw v2.0

## Overview
Run a comprehensive health check on the RedClaw system:

1. **Tool Dependencies** — Check all 10 pentesting tools
   - Binary exists on PATH
   - Version detection
   - Minimum version validation
2. **Python Packages** — Verify all required pip packages
3. **LLM Provider** — Test Kaggle/Ollama endpoint connectivity
4. **MCP Servers** — Verify all 10 servers can initialize
5. **GuardianRails** — Validate safety rules are loaded
6. **Disk Space** — Check available storage for logs/reports

## Output Format
```
╭───────────────── RedClaw Doctor ─────────────────╮
│  ✅ nmap        7.94    /usr/bin/nmap             │
│  ✅ masscan     1.3.2   /usr/bin/masscan          │
│  ❌ metasploit  —       NOT FOUND                 │
│  8/10 tools ready  •  Run: redclaw setup-tools    │
╰───────────────────────────────────────────────────╯
```

## Example Usage
```
/doctor
```

Use `/setup-tools` to automatically install any missing tools.
