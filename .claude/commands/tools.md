List all available MCP pentesting tool servers and their status.

Display the following tools with their descriptions and availability:

| Tool | MCP Server | Description |
|------|-----------|-------------|
| nmap | redclaw-nmap | Port scanning & service detection |
| masscan | redclaw-masscan | Ultra-fast port discovery |
| nuclei | redclaw-nuclei | Template-based vulnerability scanning |
| metasploit | redclaw-msf | Exploitation framework |
| sqlmap | redclaw-sqlmap | SQL injection detection |
| hydra | redclaw-hydra | Network login brute-force |
| linpeas | redclaw-linpeas | Linux privilege escalation |
| winpeas | redclaw-winpeas | Windows privilege escalation |
| bloodhound | redclaw-bloodhound | Active Directory analysis |
| custom_exploit | redclaw-custom | Custom Python/Bash exploits |

Check which tools are actually available using the Bash tool: `which nmap masscan nuclei msfconsole sqlmap hydra 2>/dev/null`

Show 🟢 for available and 🔴 for missing tools.
