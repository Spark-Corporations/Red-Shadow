Auto-install missing pentesting tool dependencies.

Mode: $ARGUMENTS (options: interactive, auto, dry-run; default: interactive)

Use the Bash tool to run: `python -m redclaw.tooling.installer $ARGUMENTS`

If that fails, manually check and install each tool:

## Tools to check:
1. **nmap** — `apt install -y nmap` or `brew install nmap`
2. **masscan** — `apt install -y masscan` or `brew install masscan`
3. **nuclei** — `go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest`
4. **metasploit** — Follow msf install guide for your OS
5. **sqlmap** — `apt install -y sqlmap` or `pip install sqlmap`
6. **hydra** — `apt install -y hydra` or `brew install hydra`
7. **linpeas/winpeas** — Download from GitHub releases
8. **bloodhound** — `pip install bloodhound`

For each tool, check if already installed before attempting installation.
Always ask for confirmation before installing system packages.
