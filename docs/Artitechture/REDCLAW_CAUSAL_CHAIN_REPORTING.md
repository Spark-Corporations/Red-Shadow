# 📊 REDCLAW CAUSAL CHAIN REPORTING

## Why-What-How Enterprise Reports

---

## FORMAT

Every finding follows:

**WHY:** Root cause  
**WHAT:** Vulnerability details  
**HOW:** Exploitation path  
**PROOF:** Screenshot + evidence  
**FIX:** Stack-specific recommendation

---

## EXAMPLE

```
═══════════════════════════════════════════
FINDING #1: Apache Path Traversal RCE
═══════════════════════════════════════════

WHY (Root Cause):
Apache 2.4.49 contains CVE-2021-41773, a path 
normalization flaw that allows directory traversal.

WHAT (Vulnerability):
- CVE: CVE-2021-41773
- CVSS: 9.8 (Critical)
- Service: Apache 2.4.49 on port 80
- Impact: Remote Code Execution

HOW (Exploitation Path):
1. Discovered Apache 2.4.49 via nmap service detection
2. Queried CVE database via Memory RAG
3. Downloaded PoC from GitHub
4. Adapted payload for target architecture
5. Executed: GET /cgi-bin/.%2e/.%2e/.%2e/etc/passwd
6. Verified: Obtained /etc/passwd contents
7. Validated: Independent reproduction confirmed

PROOF (Evidence):
[Screenshot: passwd_file_accessed.png]
[HTTP Response: 200 OK, contents shown]
Timestamp: 2026-02-25 15:30:45 UTC

FIX (Recommendation):
Target Stack: Ubuntu 20.04 + Apache 2.4.49

Immediate:
1. apt-get update && apt-get install apache2=2.4.51-1ubuntu1
2. Verify: apache2 -v (should show 2.4.51+)
3. Restart: systemctl restart apache2

Long-term:
- Enable automatic security updates
- Implement WAF rules for path traversal patterns
- Monitor /var/log/apache2/access.log for suspicious requests

Estimated Downtime: <5 minutes
Priority: CRITICAL (exploit actively validated)
```

---

## IMPLEMENTATION

```python
class CausalChainReport:
    def generate(self, finding: dict, validation: dict):
        return f"""
═══════════════════════════════════════════
FINDING #{finding['id']}: {finding['title']}
═══════════════════════════════════════════

WHY (Root Cause):
{finding['root_cause']}

WHAT (Vulnerability):
- CVE: {finding['cve']}
- CVSS: {finding['cvss']}
- Service: {finding['service']}
- Impact: {finding['impact']}

HOW (Exploitation Path):
{self.format_exploitation_path(finding['steps'])}

PROOF (Evidence):
{self.format_proof(validation['proof'])}

FIX (Recommendation):
{self.format_fix(finding, validation)}
"""
    
    def format_exploitation_path(self, steps):
        return '\n'.join(f"{i+1}. {step}" for i, step in enumerate(steps))
    
    def format_proof(self, proof):
        return f"""
[Screenshot: {proof['screenshot_path']}]
[HTTP Response: {proof['http_status']}, {proof['response_size']} bytes]
Timestamp: {proof['timestamp']}
"""
    
    def format_fix(self, finding, validation):
        # Stack-specific recommendations
        stack = self.detect_stack(finding['target'])
        
        return f"""
Target Stack: {stack['os']} + {stack['software']}

Immediate:
{self.get_immediate_fix(finding, stack)}

Long-term:
{self.get_longterm_recommendations(finding, stack)}

Estimated Downtime: {self.estimate_downtime(finding)}
Priority: {self.calculate_priority(finding, validation)}
"""
```

---

## OUTPUT FORMATS

### HTML (Interactive)
- Clickable screenshots
- Collapsible sections
- Search/filter findings

### PDF (Executive)
- Professional layout
- Summary dashboard
- Risk matrix

### JSON (API)
```json
{
  "finding_id": 1,
  "title": "Apache RCE",
  "why": "...",
  "what": {...},
  "how": [...],
  "proof": {...},
  "fix": {...},
  "validation": {
    "validated": true,
    "false_positive": false
  }
}
```

---

**VERSION:** 3.1  
**FORMAT:** Why-What-How-Proof-Fix  
**OUTPUT:** HTML + PDF + JSON
