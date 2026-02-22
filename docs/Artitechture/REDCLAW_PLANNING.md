# 🎯 REDCLAW V2.0 - PLANNING PHASE

> **Phase 1 of 8: Strategic Preparation for Pentesting Success**  
> **Principle: "A Plan is Half the Victory"**

---

## 📋 PHASE OVERVIEW

### Purpose

The Planning Phase is where **every successful pentest begins**. Before a single packet is sent, we must:
- Understand **exactly** what we're testing
- Define **clear boundaries** (scope)
- Set **measurable objectives**
- Select **appropriate tools**
- Establish **safety constraints**

**OSCP Wisdom:** "OSCP isn't about finding the hardest exploit. It's about consistency: enumerate, exploit, escalate, document." Consistency starts with planning.

---

## 🎯 OBJECTIVES OF THIS PHASE

### What Success Looks Like:

```
✅ Scope document parsed and validated
✅ Target IPs/networks identified and verified
✅ Objectives converted to measurable goals
✅ Tool manifest generated (150+ tools categorized)
✅ Constraints documented (time, DoS limits, data handling)
✅ Guardian Rails configured (safety checks active)
✅ Opus 4.6 has complete execution plan
```

### Completion Criteria:

- [ ] `scope.yaml` exists and is syntactically valid
- [ ] All target IPs are within defined network ranges
- [ ] At least 1 objective is defined (e.g., "Find flags", "Gain domain admin")
- [ ] Tool dependencies verified (Nmap, Masscan, Metasploit available)
- [ ] Session Manager initialized (local + remote sessions ready)
- [ ] Guardian Rails tested (forbidden pattern detection active)

---

## 📝 INPUT: SCOPE DEFINITION

### Format: YAML Configuration

**User provides scope.yaml:**

```yaml
# scope.yaml - Pentesting Scope Definition

metadata:
  engagement_name: "TryHackMe Machine: OpenVPN"
  tester: "RedClaw v2.0"
  date: "2026-02-16"
  duration: "4 hours"
  
target:
  network: "10.10.10.0/24"  # CIDR notation
  specific_ips:
    - "10.10.10.5"    # Primary target
    - "10.10.10.10"   # Secondary target
  
  excluded:
    - "10.10.10.1"    # Gateway - DO NOT TOUCH
    - "10.10.10.254"  # DNS server - OUT OF SCOPE
  
  domains:
    - "target.thm"
    - "www.target.thm"
  
constraints:
  # Safety Limits
  no_dos: true  # No Denial of Service attacks
  no_data_destruction: true  # Don't delete/modify user data
  no_social_engineering: true  # No phishing, no pretexting
  
  # Timing Constraints
  working_hours: "24/7"  # Or "09:00-17:00 UTC"
  max_duration: "4 hours"
  
  # Resource Limits
  max_threads: 10  # Nmap, Metasploit thread limits
  max_bandwidth: "10 Mbps"  # Don't saturate network
  
  # User Interaction
  require_approval_for:
    - "privilege_escalation"  # Ask before attempting privesc
    - "lateral_movement"      # Ask before moving to new hosts
    - "data_exfiltration"     # Ask before downloading files
  
objectives:
  primary:
    - "Find user flag in /home/user/user.txt"
    - "Find root flag in /root/root.txt"
  
  secondary:
    - "Identify all running services"
    - "Document privilege escalation path"
    - "Map internal network topology"
  
  bonus:
    - "Find hidden users"
    - "Discover sensitive files (passwords, keys)"

methodology:
  required_phases:
    - "reconnaissance"
    - "scanning"
    - "vulnerability_assessment"
    - "exploitation"
    - "post_exploitation"
    - "reporting"
  
  optional_phases:
    - "research"  # Continuous, runs in background

reporting:
  format: "OSCP-style"  # Professional pentest report
  include_screenshots: true
  include_commands: true
  include_remediation: true
  
  output_directory: "./reports/tryhackme_openvpn"
```

---

## 🧠 OPUS 4.6: SCOPE PARSING LOGIC

### Step 1: Validate YAML Syntax

```python
import yaml

def parse_scope(scope_file):
    """
    Parse and validate scope.yaml
    """
    try:
        with open(scope_file, 'r') as f:
            scope = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return {
            "success": False,
            "error": f"Invalid YAML syntax: {e}",
            "action": "USER_FIX_REQUIRED"
        }
    
    # Validate required fields
    required_fields = [
        'target.network',
        'objectives.primary',
        'constraints'
    ]
    
    for field in required_fields:
        if not get_nested_value(scope, field):
            return {
                "success": False,
                "error": f"Missing required field: {field}",
                "action": "USER_FIX_REQUIRED"
            }
    
    return {"success": True, "scope": scope}
```

---

### Step 2: IP Range Validation

```python
from ipaddress import ip_network, ip_address

def validate_targets(scope):
    """
    Ensure all targets are within defined network
    """
    network = ip_network(scope['target']['network'])
    
    issues = []
    
    # Check specific IPs
    for ip in scope['target'].get('specific_ips', []):
        if ip_address(ip) not in network:
            issues.append(f"IP {ip} is outside network {network}")
    
    # Check excluded IPs
    for ip in scope['target'].get('excluded', []):
        if ip_address(ip) not in network:
            issues.append(f"Excluded IP {ip} is outside network {network}")
    
    if issues:
        return {
            "valid": False,
            "issues": issues,
            "action": "USER_FIX_SCOPE"
        }
    
    return {"valid": True}
```

---

### Step 3: Objective Conversion to Measurable Goals

```python
def parse_objectives(scope):
    """
    Convert user objectives to machine-actionable goals
    """
    objectives = scope['objectives']
    
    actionable_goals = []
    
    for obj in objectives.get('primary', []):
        # Example: "Find user flag in /home/user/user.txt"
        if 'flag' in obj.lower():
            # Extract file path
            import re
            path_match = re.search(r'(/[\w/.]+)', obj)
            if path_match:
                actionable_goals.append({
                    "type": "find_file",
                    "path": path_match.group(1),
                    "priority": "HIGH",
                    "success_criteria": "File exists and is readable"
                })
        
        elif 'identify' in obj.lower() and 'service' in obj.lower():
            actionable_goals.append({
                "type": "service_enumeration",
                "target": "all_ips",
                "priority": "MEDIUM",
                "success_criteria": "All ports scanned, services fingerprinted"
            })
    
    return actionable_goals
```

---

## 🛠️ TOOL SELECTION & MANIFEST

### Research Finding: Best-in-Class Tools (2026)

Based on OSCP preparation guides and bug bounty best practices, here are the **essential tools** RedClaw must have:

### Tool Categories:

```
1. RECONNAISSANCE (Passive)
   ├─ Amass (OWASP) - Subdomain enumeration via passive sources
   ├─ Subfinder (ProjectDiscovery) - Fast subdomain discovery
   ├─ crt.sh - Certificate Transparency logs
   ├─ theHarvester - OSINT email/subdomain gathering
   └─ Shodan API - Internet-wide service search

2. RECONNAISSANCE (Active)
   ├─ Nmap - Network mapping, host discovery
   ├─ Masscan - Ultra-fast port scanner
   ├─ DNS enumeration (dig, dnsenum, dnsrecon)
   └─ Wayback URLs (gau, waybackurls)

3. SCANNING
   ├─ Nmap (with NSE scripts)
   ├─ Masscan (1000x faster than Nmap for initial sweep)
   ├─ Naabu (ProjectDiscovery) - Fast port scanner
   └─ RustScan - Modern port scanner

4. SERVICE ENUMERATION
   ├─ Nmap service detection (-sV)
   ├─ WhatWeb - Web technology fingerprinting
   ├─ Wappalyzer - Tech stack identification
   └─ httpx - HTTP probing and metadata extraction

5. VULNERABILITY ASSESSMENT
   ├─ Nuclei (ProjectDiscovery) - Template-based vuln scanner
   ├─ Nessus (if licensed) - Professional vuln scanner
   ├─ OpenVAS - Open-source vuln scanner
   └─ SearchSploit - Exploit database search

6. EXPLOITATION
   ├─ Metasploit Framework - Exploit framework
   ├─ SQLMap - SQL injection automation
   ├─ Burp Suite - Web app testing
   └─ Custom exploits (downloaded from exploit-db)

7. POST-EXPLOITATION
   ├─ Mimikatz - Windows credential dumping
   ├─ BloodHound - Active Directory mapping
   ├─ LinPEAS / WinPEAS - Privilege escalation checkers
   └─ PowerShell Empire - Post-exploitation framework

8. UTILITIES
   ├─ netcat (nc) - Swiss army knife
   ├─ curl / wget - HTTP clients
   ├─ Python 3 - Scripting
   └─ JQ - JSON parsing
```

---

### Tool Manifest Generation

```python
def generate_tool_manifest(scope):
    """
    Based on scope, determine which tools are needed
    """
    required_phases = scope['methodology']['required_phases']
    
    manifest = {
        "reconnaissance": [],
        "scanning": [],
        "vulnerability": [],
        "exploitation": [],
        "post_exploitation": []
    }
    
    # Reconnaissance phase
    if 'reconnaissance' in required_phases:
        if scope['target'].get('domains'):
            # Domain targets = subdomain enumeration needed
            manifest['reconnaissance'].extend([
                "amass",
                "subfinder",
                "crt.sh",
                "theHarvester"
            ])
        
        # IP targets = network mapping needed
        manifest['reconnaissance'].extend([
            "nmap",
            "masscan"
        ])
    
    # Scanning phase (always needed)
    if 'scanning' in required_phases:
        manifest['scanning'] = [
            "nmap",       # Detailed scans
            "masscan",    # Fast initial sweep
            "naabu",      # Modern alternative
            "rustscan"    # Fast alternative
        ]
    
    # Vulnerability phase
    if 'vulnerability_assessment' in required_phases:
        manifest['vulnerability'] = [
            "nuclei",
            "nmap --script vuln",
            "searchsploit"
        ]
    
    # Exploitation phase
    if 'exploitation' in required_phases:
        # Check objectives for hints
        objectives_text = json.dumps(scope['objectives']).lower()
        
        if 'web' in objectives_text or 'http' in objectives_text:
            manifest['exploitation'].append("burp_suite")
            manifest['exploitation'].append("sqlmap")
        
        manifest['exploitation'].extend([
            "metasploit",
            "exploit-db"  # For downloading custom exploits
        ])
    
    # Post-exploitation phase
    if 'post_exploitation' in required_phases:
        manifest['post_exploitation'] = [
            "linpeas",     # Linux privesc
            "winpeas",     # Windows privesc
            "mimikatz",    # Windows cred dump
            "bloodhound",  # AD mapping
            "netcat"       # Reverse shells
        ]
    
    return manifest
```

---

### Tool Dependency Verification

```python
def verify_tool_availability(manifest):
    """
    Check if all required tools are installed
    """
    missing_tools = []
    
    for phase, tools in manifest.items():
        for tool in tools:
            # Check if tool exists in PATH
            result = subprocess.run(
                ["which", tool],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                missing_tools.append({
                    "tool": tool,
                    "phase": phase,
                    "install_command": get_install_command(tool)
                })
    
    if missing_tools:
        # Auto-install or ask user
        return {
            "ready": False,
            "missing": missing_tools,
            "action": "INSTALL_TOOLS"
        }
    
    return {"ready": True}

def get_install_command(tool):
    """
    Return installation command for tool
    """
    install_map = {
        "nmap": "sudo apt install nmap -y",
        "masscan": "sudo apt install masscan -y",
        "amass": "snap install amass",
        "subfinder": "go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest",
        "nuclei": "go install -v github.com/projectdiscovery/nuclei/v2/cmd/nuclei@latest",
        "rustscan": "cargo install rustscan",
        "metasploit": "curl https://raw.githubusercontent.com/rapid7/metasploit-omnibus/master/config/templates/metasploit-framework-wrappers/msfupdate.erb > msfinstall && chmod 755 msfinstall && ./msfinstall",
        # ... add more
    }
    
    return install_map.get(tool, f"# {tool} installation not automated")
```

---

## 🛡️ GUARDIAN RAILS CONFIGURATION

### Safety Constraints from Scope

```python
def configure_guardian(scope):
    """
    Initialize Guardian Rails based on scope constraints
    """
    constraints = scope['constraints']
    
    guardian_config = {
        "forbidden_operations": [],
        "approval_required": [],
        "resource_limits": {},
        "scope_enforcement": {}
    }
    
    # DoS protection
    if constraints.get('no_dos'):
        guardian_config['forbidden_operations'].extend([
            r"hping3.*--flood",
            r"slowloris",
            r"nmap.*-T5",  # Insane timing = DoS risk
        ])
    
    # Data destruction protection
    if constraints.get('no_data_destruction'):
        guardian_config['forbidden_operations'].extend([
            r"rm -rf",
            r"del /f /s",
            r"DROP TABLE",
            r"DELETE FROM.*WHERE 1=1",
        ])
    
    # Approval requirements
    if 'require_approval_for' in constraints:
        guardian_config['approval_required'] = constraints['require_approval_for']
    
    # Resource limits
    guardian_config['resource_limits'] = {
        "max_threads": constraints.get('max_threads', 10),
        "max_bandwidth": constraints.get('max_bandwidth', "10 Mbps"),
        "max_duration": constraints.get('max_duration', "24 hours")
    }
    
    # Scope enforcement
    guardian_config['scope_enforcement'] = {
        "allowed_network": scope['target']['network'],
        "allowed_ips": scope['target'].get('specific_ips', []),
        "excluded_ips": scope['target'].get('excluded', [])
    }
    
    return guardian_config
```

---

## 📊 EXECUTION PLAN GENERATION

### Converting Scope to Actionable Steps

```python
def generate_execution_plan(scope, tool_manifest, actionable_goals):
    """
    Create step-by-step execution plan for Opus 4.6
    """
    plan = {
        "phases": [],
        "estimated_time": 0,
        "checkpoints": []
    }
    
    required_phases = scope['methodology']['required_phases']
    
    # Planning (this phase) - Already done!
    plan['phases'].append({
        "name": "planning",
        "status": "COMPLETE",
        "duration": "5 minutes"
    })
    
    # Reconnaissance
    if 'reconnaissance' in required_phases:
        recon_steps = []
        
        if scope['target'].get('domains'):
            recon_steps.append({
                "action": "subdomain_enumeration",
                "tools": ["amass", "subfinder"],
                "expected_output": "List of subdomains",
                "completion_criteria": "Diminishing returns (no new subdomains in 10 min) OR 50+ found"
            })
        
        recon_steps.append({
            "action": "host_discovery",
            "tools": ["nmap -sn"],
            "expected_output": "Live hosts in network",
            "completion_criteria": "All IPs in scope probed"
        })
        
        plan['phases'].append({
            "name": "reconnaissance",
            "status": "PENDING",
            "steps": recon_steps,
            "estimated_duration": "30-60 minutes"
        })
        
        plan['estimated_time'] += 45  # Average of 30-60
    
    # Scanning
    if 'scanning' in required_phases:
        scan_steps = [
            {
                "action": "fast_port_sweep",
                "tools": ["masscan -p1-65535"],
                "expected_output": "Open ports (initial list)",
                "completion_criteria": "All 65535 ports scanned"
            },
            {
                "action": "detailed_port_scan",
                "tools": ["nmap -sV -sC"],
                "expected_output": "Service versions, OS detection",
                "completion_criteria": "All open ports fingerprinted"
            }
        ]
        
        plan['phases'].append({
            "name": "scanning",
            "status": "PENDING",
            "steps": scan_steps,
            "estimated_duration": "20-40 minutes"
        })
        
        plan['estimated_time'] += 30
    
    # Vulnerability Assessment
    if 'vulnerability_assessment' in required_phases:
        vuln_steps = [
            {
                "action": "automated_vuln_scan",
                "tools": ["nuclei", "nmap --script vuln"],
                "expected_output": "CVE list, vulnerability details",
                "completion_criteria": "All services scanned for known vulns"
            },
            {
                "action": "exploit_search",
                "tools": ["searchsploit"],
                "expected_output": "Matching exploits from exploit-db",
                "completion_criteria": "All services checked against exploit-db"
            }
        ]
        
        plan['phases'].append({
            "name": "vulnerability_assessment",
            "status": "PENDING",
            "steps": vuln_steps,
            "estimated_duration": "15-30 minutes"
        })
        
        plan['estimated_time'] += 22
    
    # Exploitation
    if 'exploitation' in required_phases:
        exploit_steps = [
            {
                "action": "attempt_exploits",
                "tools": ["metasploit", "custom exploits"],
                "expected_output": "Initial access (shell)",
                "completion_criteria": "Shell obtained OR all exploits exhausted",
                "note": "This phase is highly variable (could be 10 min or 4 hours)"
            }
        ]
        
        plan['phases'].append({
            "name": "exploitation",
            "status": "PENDING",
            "steps": exploit_steps,
            "estimated_duration": "30 minutes - 4 hours"
        })
        
        plan['estimated_time'] += 120  # Average case
    
    # Post-Exploitation
    if 'post_exploitation' in required_phases:
        postexp_steps = []
        
        # Based on objectives
        for goal in actionable_goals:
            if goal['type'] == 'find_file':
                postexp_steps.append({
                    "action": f"locate_file",
                    "target": goal['path'],
                    "tools": ["find", "cat"],
                    "expected_output": "File contents",
                    "completion_criteria": f"File {goal['path']} found and read"
                })
        
        postexp_steps.append({
            "action": "privilege_escalation",
            "tools": ["linpeas", "winpeas", "manual enum"],
            "expected_output": "Root/Admin access",
            "completion_criteria": "Highest privilege obtained",
            "requires_approval": "privilege_escalation" in scope['constraints'].get('require_approval_for', [])
        })
        
        plan['phases'].append({
            "name": "post_exploitation",
            "status": "PENDING",
            "steps": postexp_steps,
            "estimated_duration": "30-90 minutes"
        })
        
        plan['estimated_time'] += 60
    
    # Reporting
    plan['phases'].append({
        "name": "reporting",
        "status": "PENDING",
        "estimated_duration": "15 minutes (automated)"
    })
    
    plan['estimated_time'] += 15
    
    # Convert to human-readable
    plan['estimated_time_human'] = f"{plan['estimated_time'] // 60} hours {plan['estimated_time'] % 60} minutes"
    
    return plan
```

---

## 🎓 OPUS 4.6 EXECUTION CHECKLIST

Before proceeding to next phase (Reconnaissance), verify:

```markdown
## PLANNING PHASE COMPLETE ✓

### Scope Understanding
- [ ] scope.yaml parsed successfully
- [ ] All target IPs validated (within network range)
- [ ] Excluded IPs noted (will NOT be touched)
- [ ] Objectives converted to actionable goals

### Tool Readiness
- [ ] Tool manifest generated
- [ ] All required tools verified (available in PATH)
- [ ] Missing tools installed (or noted for download)

### Safety Configuration
- [ ] Guardian Rails configured
- [ ] Forbidden operations list loaded
- [ ] User approval requirements set
- [ ] Resource limits applied

### Execution Plan
- [ ] Phase sequence determined
- [ ] Estimated time calculated
- [ ] Completion criteria defined for each phase
- [ ] User informed of plan

### Communication
- [ ] User notified of plan (timeline, objectives)
- [ ] Expectations set (what will/won't be done)
- [ ] Approval received (if required)
```

---

## 🚨 COMMON PITFALLS (AVOID THESE)

### ❌ Pitfall 1: Scope Creep

**Problem:** User says "test 10.10.10.5" but you scan entire 10.0.0.0/8 network.

**Solution:** ALWAYS validate target IP against scope before ANY action.

```python
def is_in_scope(target_ip, scope):
    network = ip_network(scope['target']['network'])
    if ip_address(target_ip) not in network:
        return False
    
    if target_ip in scope['target'].get('excluded', []):
        return False
    
    return True
```

---

### ❌ Pitfall 2: Missing Tool Dependencies

**Problem:** Start exploitation phase, realize Metasploit not installed.

**Solution:** Verify ALL tools BEFORE starting any phase.

---

### ❌ Pitfall 3: Unrealistic Time Estimates

**Problem:** Tell user "this will take 2 hours", actually takes 8 hours.

**Solution:** Be realistic about preparation time. OSCP candidates need 300-500 focused hours. For single machine pentests:
- Easy box: 2-4 hours
- Medium box: 4-8 hours
- Hard box: 8-16 hours

---

### ❌ Pitfall 4: Ignoring Constraints

**Problem:** User says "no DoS", you run `nmap -T5 --max-rate 10000`.

**Solution:** Guardian Rails MUST enforce constraints. If user asks for something forbidden, BLOCK and explain why.

---

## 📤 OUTPUT: PLANNING ARTIFACTS

### 1. Validated Scope Document

```json
{
  "scope": {
    "network": "10.10.10.0/24",
    "targets": ["10.10.10.5", "10.10.10.10"],
    "excluded": ["10.10.10.1", "10.10.10.254"],
    "validated": true
  }
}
```

### 2. Tool Manifest

```json
{
  "reconnaissance": ["amass", "subfinder", "nmap", "masscan"],
  "scanning": ["nmap", "masscan", "naabu"],
  "vulnerability": ["nuclei", "searchsploit"],
  "exploitation": ["metasploit", "sqlmap"],
  "post_exploitation": ["linpeas", "winpeas", "mimikatz"]
}
```

### 3. Execution Plan

```json
{
  "phases": [
    {"name": "reconnaissance", "estimated_time": "45 min"},
    {"name": "scanning", "estimated_time": "30 min"},
    {"name": "vulnerability", "estimated_time": "22 min"},
    {"name": "exploitation", "estimated_time": "120 min"},
    {"name": "post_exploitation", "estimated_time": "60 min"},
    {"name": "reporting", "estimated_time": "15 min"}
  ],
  "total_estimated_time": "4 hours 52 minutes"
}
```

### 4. Guardian Configuration

```json
{
  "forbidden_operations": [
    "rm -rf",
    "hping3.*--flood",
    "DROP TABLE"
  ],
  "approval_required": [
    "privilege_escalation",
    "lateral_movement"
  ],
  "resource_limits": {
    "max_threads": 10,
    "max_bandwidth": "10 Mbps"
  }
}
```

---

## 🎬 NEXT PHASE

Once Planning is complete, proceed to **RECONNAISSANCE.md**.

**Handoff to Reconnaissance:**
- ✅ Scope validated
- ✅ Tools ready
- ✅ Safety configured
- ✅ Plan established

→ **BEGIN: Reconnaissance Phase**

---

**VERSION:** 2.0.0  
**REFERENCES:** CORE_ARCHITECTURE.md  
**NEXT:** RECONNAISSANCE.md  
**STATUS:** ✅ PLANNING COMPLETE
