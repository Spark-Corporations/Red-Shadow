Run a comprehensive network scan on the specified target.

Target: $ARGUMENTS

## Workflow

1. **Quick Discovery** — Use the redclaw-masscan MCP tool for fast port discovery:
   - Scan all 65535 ports at controlled rate
   - Identify open ports rapidly

2. **Detailed Scan** — Use the redclaw-nmap MCP tool on discovered ports:
   - Service and version detection (-sV)
   - Default NSE scripts (-sC)
   - OS fingerprinting (-O)

3. **Analysis** — Review the results and:
   - Identify interesting services (HTTP, SMB, SSH, RDP, etc.)
   - Flag potential vulnerabilities
   - Generate findings with severity ratings

## Safety
- All scans go through GuardianRails validation
- Rate limiting enforced (default: 1000 pps)
- Confirm target is within engagement scope before scanning

If no target is provided, ask the user for one.
