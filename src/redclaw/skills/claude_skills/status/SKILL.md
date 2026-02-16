---
name: status
description: Show current pipeline status, findings count, and active sessions
invocation: user
tools:
  - Bash
---

# Status Skill — RedClaw v2.0

## Overview
Display the current state of the pentesting engagement:
- Current pipeline phase (Planning → Recon → Scan → VulnAssess → Exploit → PostExploit → Report → Cleanup)
- Finding count by severity (critical/high/medium/low/info)
- Active sessions (SSH, Meterpreter)
- OpenClaw runtime health
- LLM provider status (Kaggle/Ollama)
- Tool bridge statistics
- Elapsed engagement time

## Example Usage
```
/status
```
