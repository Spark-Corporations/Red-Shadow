Run a comprehensive health check on all RedClaw dependencies and system status.

Use the Bash tool to run: `python -m redclaw.claude_skin.hook_handler status`

This performs the full system check including:
1. **LLM Provider** — Tests actual HTTP connectivity to the ngrok/Kaggle endpoint
2. **Tool Dependencies** — Checks if nmap, masscan, nuclei, metasploit, sqlmap, hydra, linpeas, winpeas, bloodhound are installed
3. **Engagement State** — Shows current phase and findings count
4. **GuardianRails** — Shows audit log statistics

For any missing tools, suggest running `/setup-tools` to auto-install them.
Format output as a clean table with ✅/❌ indicators.
