Show the full system status of the RedClaw pentesting engagement.

Use the Bash tool to run: `python -m redclaw.claude_skin.hook_handler status`

This performs REAL checks:
- **LLM Backend**: Tests actual HTTP connectivity to the configured endpoint
- **Tool Health**: Checks which pentesting tools (nmap, masscan, nuclei, etc.) are installed
- **Engagement State**: Reads pipeline state and findings from disk
- **GuardianRails**: Shows audit log statistics

Format the output clearly with emoji indicators (🟢 reachable, 🟡 unreachable, 🔴 not configured).
