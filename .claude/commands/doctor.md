Run a health check on all RedClaw tool dependencies and system status.

Use the Bash tool to run: `python -m redclaw.claude_skin.hook_handler health_check`

Then provide additional checks:
1. **Tool Dependencies** — Check if nmap, masscan, nuclei, metasploit, sqlmap, hydra, linpeas, winpeas, bloodhound are installed
2. **Python Packages** — Verify required packages are available
3. **LLM Provider** — Test endpoint connectivity
4. **Disk Space** — Check available storage

For any missing tools, suggest running `/setup-tools` to auto-install them.

Format output as a clean table with ✅/❌ indicators.
