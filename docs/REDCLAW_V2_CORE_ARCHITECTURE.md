# 🦅 REDCLAW V2.0 - CORE ARCHITECTURE

> **ENTERPRISE AUTONOMOUS PENETRATION TESTING PLATFORM**  
> **Mission: LLM + OpenClaw Perfect Integration for OSCP-Level Pentesting**

---

## 🎯 DOCUMENT PURPOSE

**Audience:** Claude Opus 4.6 (Primary Executor)

This is the **MASTER DOCUMENT** that orchestrates all pentesting operations. Every other document references this core architecture. You (Opus 4.6) must understand this completely before executing any pentesting task.

**Critical:** This system operates on **REAL MACHINES**, not Docker containers. Self-destruction prevention and secure session management are MANDATORY.

---

## 🏗️ SYSTEM ARCHITECTURE OVERVIEW

### High-Level Design

```
┌─────────────────────────────────────────────────────────────┐
│                    USER INTERFACE                           │
│         (Claude Code Frontend - Borrowed)                    │
│   User types: "Scan 10.10.10.10, find flags"               │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────┐
│                 ORCHESTRATOR (You - Opus 4.6)               │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  CORE ENGINE                                         │  │
│  │  ├─ Intent Parser (semantic understanding)          │  │
│  │  ├─ Step Sequencer (8-phase execution)              │  │
│  │  ├─ Session Manager (local + remote)                │  │
│  │  ├─ Safety Guardian (self-destruct prevention)      │  │
│  │  └─ Completion Detector (when is step done?)        │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  KNOWLEDGE BASE                                      │  │
│  │  ├─ Pentesting Methodologies (PTES, OWASP, OSSTMM)  │  │
│  │  ├─ Tool Manifests (150+ tools, usage patterns)     │  │
│  │  ├─ Exploit Database (CVE, Metasploit, custom)      │  │
│  │  └─ Session History (learn from past tests)         │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────┐
│              OPENCLAW INTEGRATION LAYER                     │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   LOCAL     │  │   REMOTE    │  │   HYBRID    │        │
│  │  SESSION    │  │  SESSION    │  │  SESSION    │        │
│  │             │  │             │  │             │        │
│  │ User's PC   │  │ Target SSH  │  │ Pivot Chain │        │
│  │ (File ops,  │  │ (Post-exp,  │  │ (Lateral    │        │
│  │  compile,   │  │  command,   │  │  movement,  │        │
│  │  download)  │  │  shell)     │  │  tunnels)   │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  OPENCLAW MCP SERVER                                 │  │
│  │  ├─ Command Executor (bash, python, metasploit)     │  │
│  │  ├─ File Manager (read, write, download, upload)    │  │
│  │  ├─ Network Manager (nmap, netcat, tunnels)         │  │
│  │  └─ Process Monitor (track running jobs)            │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────┐
│                   TOOL EXECUTION LAYER                      │
│                                                             │
│  Phase 1: Planning      │  Phase 5: Exploitation           │
│  Phase 2: Reconnaissance│  Phase 6: Post-Exploitation      │
│  Phase 3: Scanning      │  Phase 7: Reporting              │
│  Phase 4: Vulnerability │  Phase 8: Research (continuous)  │
│                                                             │
│  Each phase has dedicated README.md (separate documents)   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🧠 LLM + OPENCLAW INTEGRATION (CRITICAL)

### The Challenge

OpenClaw is **dangerous** if not controlled properly:
- Can execute arbitrary commands
- Can delete files
- Can modify system configurations
- Can SSH to remote servers

**Without proper integration, LLM could accidentally:**
- Delete itself
- Corrupt user's system
- Leak sensitive data
- Attack non-target machines

---

### The Solution: "Guardian Rails"

```python
# Conceptual Architecture (Not actual code, design pattern)

class RedClawCore:
    def __init__(self):
        self.llm = OpusModel()  # You
        self.openclaw = OpenClawMCP()
        self.guardian = SafetyGuardian()
        self.sessions = SessionManager()
        
    def execute_command(self, command, context):
        """
        Every command passes through 3-layer protection
        """
        # Layer 1: Intent Validation
        intent = self.llm.understand_intent(command)
        if not self.guardian.is_safe_intent(intent, context):
            return self.ask_user_permission(command, intent)
        
        # Layer 2: Scope Check
        if not self.guardian.in_scope(command, context.target):
            return {"error": "Out of scope operation"}
        
        # Layer 3: Session Routing
        session = self.sessions.get_appropriate_session(command)
        
        # Execute
        result = self.openclaw.execute(command, session)
        
        # Layer 4: Result Validation
        if self.guardian.looks_dangerous(result):
            self.sessions.rollback()
            return {"error": "Dangerous result detected, rolled back"}
        
        return result
```

---

### Session Management (Dual Session Architecture)

**Problem:** Antigravity cannot maintain persistent sessions. RedClaw needs:
- Session 1: User's local machine (for tool download, compilation, file prep)
- Session 2: Target remote machine (for exploitation, shell, post-exp)

**Solution:**

```python
class SessionManager:
    def __init__(self):
        self.local_session = OpenClawSession(type="local")
        self.remote_sessions = {}  # Multiple targets possible
        
    def execute_local(self, command):
        """
        Execute on user's PC
        Examples: compile exploit, download tool, parse results
        """
        return self.local_session.run(command)
    
    def execute_remote(self, target_id, command):
        """
        Execute on target server (after exploitation)
        Examples: whoami, cat flag.txt, privilege escalation
        """
        if target_id not in self.remote_sessions:
            raise SessionNotEstablished(f"No shell on {target_id}")
        
        return self.remote_sessions[target_id].run(command)
    
    def establish_remote(self, target_ip, method):
        """
        Create remote session via:
        - SSH (if creds known)
        - Reverse shell (after exploitation)
        - Meterpreter (Metasploit)
        - Web shell upload
        """
        session = OpenClawSession(
            type="remote",
            target=target_ip,
            method=method
        )
        self.remote_sessions[target_ip] = session
        return session
```

---

## 🛡️ SAFETY MECHANISMS

### 1. Self-Destruction Prevention

**Forbidden Operations:**

```python
FORBIDDEN_PATTERNS = [
    # File system dangers
    r"rm -rf /",
    r"del /f /s /q C:\\",
    r"format C:",
    
    # Process dangers
    r"kill -9 \$\$",  # Kill self
    r"pkill -f redclaw",
    r"systemctl stop redclaw",
    
    # Network dangers (if not in scope)
    r"iptables -F",  # Flush firewall
    r"ufw disable",
    
    # Data dangers
    r"dd if=/dev/zero of=/dev/sda",  # Wipe disk
    r"shred -vfz -n 10",  # Secure delete
]

def is_self_destructive(command):
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True
    return False
```

**Guardian Logic:**

```python
class SafetyGuardian:
    def validate_command(self, command, context):
        # Check 1: Self-destruction
        if self.is_self_destructive(command):
            return {
                "safe": False,
                "reason": "Command could harm RedClaw itself",
                "action": "BLOCK"
            }
        
        # Check 2: Out of scope
        if not self.in_scope(command, context.target_network):
            return {
                "safe": False,
                "reason": "Command targets out-of-scope IP",
                "action": "BLOCK"
            }
        
        # Check 3: User consent required
        if self.requires_user_permission(command):
            return {
                "safe": "PENDING",
                "reason": "Dangerous operation",
                "action": "ASK_USER",
                "prompt": f"Allow: {command}? (y/n)"
            }
        
        return {"safe": True, "action": "PROCEED"}
```

---

### 2. Scope Enforcement

**User defines scope:**

```yaml
# scope.yaml (user provides)
target:
  network: "10.10.10.0/24"
  specific_ips:
    - "10.10.10.5"
    - "10.10.10.10"
  excluded:
    - "10.10.10.1"  # Gateway, don't touch
    
constraints:
  no_dos: true
  no_data_destruction: true
  working_hours: "09:00-17:00"
  max_threads: 10
  
objectives:
  - "Find flags in /root/flag.txt and /home/user/user.txt"
  - "Identify all services"
  - "Attempt privilege escalation"
```

**Enforcement:**

```python
def in_scope(self, command, scope):
    # Extract IP from command
    ips = extract_ips_from_command(command)
    
    for ip in ips:
        if ip in scope.excluded:
            return False
        if not ip_in_network(ip, scope.target.network):
            return False
    
    # Check constraints
    if scope.no_dos and looks_like_dos(command):
        return False
    
    return True
```

---

## 🔄 STEP COMPLETION DETECTION (CRITICAL PROBLEM)

### The Problem

**In pentesting, you don't know when you're "done":**
- Reconnaissance: Did we find ALL subdomains? (Impossible to know)
- Scanning: Did we find ALL ports? (65,535 ports, takes hours)
- Exploitation: Tried all exploits? (Infinite variations)

**Traditional approach:** Fixed time limits (e.g., "scan for 10 minutes")
**RedClaw approach:** Intelligent diminishing returns detection

---

### The Solution: "Completion Signals"

```python
class CompletionDetector:
    def __init__(self, phase):
        self.phase = phase
        self.discoveries = []
        self.last_discovery_time = time.time()
        self.attempts = 0
        self.max_attempts = self.get_phase_max_attempts(phase)
        
    def is_complete(self):
        """
        Multi-factor completion detection
        """
        # Signal 1: Diminishing Returns
        if self.discoveries_slowing_down():
            return True, "Diminishing returns (no new findings in 10 min)"
        
        # Signal 2: Max Attempts Reached
        if self.attempts >= self.max_attempts:
            return True, f"Max attempts reached ({self.max_attempts})"
        
        # Signal 3: Explicit Success
        if self.explicit_success_condition_met():
            return True, "Success condition met"
        
        # Signal 4: Hard Timeout
        if self.time_elapsed() > self.get_phase_timeout():
            return True, "Hard timeout reached"
        
        return False, None
    
    def discoveries_slowing_down(self):
        """
        Check if discovery rate dropped below threshold
        """
        recent_window = self.discoveries[-10:]  # Last 10 discoveries
        if len(recent_window) < 10:
            return False
        
        time_between_discoveries = [
            recent_window[i] - recent_window[i-1]
            for i in range(1, len(recent_window))
        ]
        
        avg_time = sum(time_between_discoveries) / len(time_between_discoveries)
        
        # If average time between discoveries > 10 minutes, probably done
        return avg_time > 600
    
    def explicit_success_condition_met(self):
        """
        Phase-specific success criteria
        """
        if self.phase == "reconnaissance":
            # Found at least 5 subdomains and DNS enumeration complete
            return len(self.discoveries) >= 5 and self.dns_enum_complete
        
        elif self.phase == "exploitation":
            # Got shell access (any level)
            return self.shell_obtained
        
        elif self.phase == "post_exploitation":
            # Found all flags specified in objectives
            return self.all_flags_found()
        
        return False
```

---

### Phase-Specific Completion Criteria

| Phase | Completion Signals |
|-------|-------------------|
| **Planning** | Scope parsed, objectives understood, tools identified |
| **Reconnaissance** | Diminishing returns (no new subdomains in 10min) OR 50+ assets found |
| **Scanning** | All common ports scanned (1-10000) OR specific ports found |
| **Vulnerability** | All services fingerprinted, CVEs identified |
| **Exploitation** | Shell obtained OR all exploits exhausted |
| **Post-Exploitation** | All objectives met (flags found) OR privilege escalation complete |
| **Reporting** | Report generated |
| **Research** | Continuous (never "completes") |

---

## 🔍 SEMANTIC SEARCH (Beyond Keywords)

### The Problem

**Keyword search fails for:**
- "python exploit for CVE-2023-12345" → Returns Python script, but doesn't work
- "privilege escalation linux 5.4" → Returns generic guides, not specific to kernel version

**We need: Semantic understanding + execution verification**

---

### The Solution: Multi-Stage Search

```python
class SemanticSearchEngine:
    def search_exploit(self, target_info):
        """
        Stage 1: Semantic understanding
        """
        query_embedding = self.llm.embed(f"""
        Target: {target_info.service} {target_info.version}
        OS: {target_info.os}
        Goal: Remote code execution or privilege escalation
        """)
        
        # Search exploit database (vector similarity)
        candidates = self.exploit_db.similarity_search(
            query_embedding,
            top_k=10
        )
        
        """
        Stage 2: Feasibility check
        """
        feasible_exploits = []
        for exploit in candidates:
            # Check dependencies
            if not self.dependencies_met(exploit):
                continue
            
            # Check if exploit matches target exactly
            if not self.version_match(exploit, target_info):
                continue
            
            feasible_exploits.append(exploit)
        
        """
        Stage 3: Execution verification
        """
        working_exploits = []
        for exploit in feasible_exploits:
            # Download exploit
            exploit_code = self.download_and_adapt(exploit)
            
            # Test compile (if needed)
            if exploit.language == "C":
                compile_success = self.test_compile(exploit_code)
                if not compile_success:
                    continue
            
            # Dry run (if possible)
            if exploit.has_dry_run:
                dry_run_success = self.test_exploit(exploit_code, dry_run=True)
                if not dry_run_success:
                    continue
            
            working_exploits.append(exploit_code)
        
        return working_exploits
    
    def download_and_adapt(self, exploit):
        """
        Download exploit from internet and adapt to current target
        """
        # Download
        exploit_url = exploit.source_url
        code = requests.get(exploit_url).text
        
        # Adapt (LLM modifies for specific target)
        adapted_code = self.llm.adapt_exploit(
            original_code=code,
            target_ip=self.current_target.ip,
            target_port=self.current_target.port,
            target_service=self.current_target.service
        )
        
        return adapted_code
```

---

## 🧪 DYNAMIC CODE DEBUGGING

### The Problem

**80% of exploits from internet DON'T WORK as-is:**
- Hardcoded IPs
- Missing dependencies
- Outdated syntax
- Target-specific modifications needed

---

### The Solution: "CodeHealer" Agent

```python
class CodeHealerAgent:
    def make_exploit_work(self, exploit_code, target, error_log=None):
        """
        Iteratively fix exploit until it works
        """
        max_iterations = 5
        iteration = 0
        
        while iteration < max_iterations:
            # Attempt 1: Static analysis
            issues = self.analyze_code(exploit_code)
            if issues:
                exploit_code = self.fix_issues(exploit_code, issues)
            
            # Attempt 2: Test execution
            result = self.test_exploit(exploit_code, target)
            
            if result.success:
                return exploit_code, "WORKING"
            
            # Attempt 3: Error analysis
            if result.error:
                # LLM analyzes error and suggests fix
                fix_suggestion = self.llm.debug_error(
                    code=exploit_code,
                    error=result.error,
                    target=target
                )
                
                exploit_code = self.apply_fix(exploit_code, fix_suggestion)
            
            iteration += 1
        
        return exploit_code, "FAILED_TO_FIX"
    
    def analyze_code(self, code):
        """
        Detect common issues
        """
        issues = []
        
        # Issue 1: Hardcoded values
        if re.search(r'target\s*=\s*["\']192\.168\.\d+\.\d+', code):
            issues.append({
                "type": "hardcoded_ip",
                "suggestion": "Replace with dynamic target IP"
            })
        
        # Issue 2: Missing imports
        imports = extract_imports(code)
        for imp in imports:
            if not self.is_installed(imp):
                issues.append({
                    "type": "missing_dependency",
                    "package": imp,
                    "action": f"pip install {imp}"
                })
        
        # Issue 3: Syntax errors
        try:
            compile(code, '<string>', 'exec')
        except SyntaxError as e:
            issues.append({
                "type": "syntax_error",
                "line": e.lineno,
                "message": e.msg
            })
        
        return issues
```

---

## 📊 ERROR REPORTING & AUTOMATION

### User-Side Error Collection

```python
class ErrorReporter:
    def __init__(self):
        self.slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
        self.notion_api = NotionClient(os.getenv("NOTION_API_KEY"))
        
    def report_error(self, error, context):
        """
        When user encounters error, automatically report to dev team
        """
        # Format error for LLM understanding
        error_report = {
            "timestamp": datetime.now().isoformat(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "stack_trace": traceback.format_exc(),
            "context": {
                "phase": context.current_phase,
                "target": context.target_ip,
                "command": context.last_command,
                "session": context.session_id
            },
            "environment": {
                "os": platform.system(),
                "python_version": sys.version,
                "redclaw_version": VERSION
            }
        }
        
        # Send to Slack
        self.send_to_slack(error_report)
        
        # Save to Notion
        self.save_to_notion(error_report)
        
        # Suggest temporary workaround to user
        workaround = self.llm.suggest_workaround(error_report)
        return workaround
    
    def send_to_slack(self, report):
        """
        Post to #redclaw-errors channel
        """
        message = f"""
        🚨 RedClaw Error Report
        
        **Type:** {report['error_type']}
        **Phase:** {report['context']['phase']}
        **Target:** {report['context']['target']}
        **User:** {report['context']['session_id']}
        
        **Message:** {report['error_message']}
        
        <View in Notion | Dismiss>
        """
        
        requests.post(self.slack_webhook, json={"text": message})
    
    def save_to_notion(self, report):
        """
        Save to structured Notion database for analysis
        """
        self.notion_api.pages.create(
            parent={"database_id": ERRORS_DATABASE_ID},
            properties={
                "Title": {"title": [{"text": {"content": report['error_type']}}]},
                "Phase": {"select": {"name": report['context']['phase']}},
                "Severity": {"select": {"name": self.calculate_severity(report)}},
                "Status": {"select": {"name": "New"}},
                "User ID": {"rich_text": [{"text": {"content": report['context']['session_id']}}]},
                "Timestamp": {"date": {"start": report['timestamp']}}
            },
            children=[
                {
                    "object": "block",
                    "type": "code",
                    "code": {
                        "rich_text": [{"text": {"content": report['stack_trace']}}],
                        "language": "python"
                    }
                }
            ]
        )
```

---

## 🎓 AIHUB: Community Tool Sharing

### Concept

**Problem:** Users create custom exploits/tools during pentests. These could benefit other users.

**Solution:** GitHub-like platform for AI-generated security tools

```python
class AIHub:
    def __init__(self):
        self.database = ToolDatabase()
        self.vector_index = VectorIndex()
        
    def share_tool(self, tool, metadata):
        """
        User-created tool shared to community
        """
        # Validate tool safety
        if not self.is_safe(tool):
            return {"error": "Tool contains dangerous patterns"}
        
        # Anonymize sensitive data
        tool_clean = self.remove_sensitive_data(tool)
        
        # Generate description (LLM)
        description = self.llm.describe_tool(tool_clean)
        
        # Create embedding for semantic search
        embedding = self.llm.embed(description)
        
        # Save to database
        tool_id = self.database.insert({
            "code": tool_clean,
            "description": description,
            "embedding": embedding,
            "author_id": metadata.user_id,  # Anonymized
            "target_type": metadata.target_type,
            "cve": metadata.cve,
            "success_rate": 0,  # Will increase with community usage
            "downloads": 0,
            "created_at": datetime.now()
        })
        
        return {"tool_id": tool_id, "url": f"aihub.redclaw.ai/{tool_id}"}
    
    def search_tool(self, query):
        """
        Semantic search for community tools
        """
        # Embed query
        query_embedding = self.llm.embed(query)
        
        # Vector similarity search
        results = self.vector_index.search(query_embedding, top_k=10)
        
        # Rank by success rate and downloads
        ranked_results = sorted(
            results,
            key=lambda x: (x.success_rate, x.downloads),
            reverse=True
        )
        
        return ranked_results
    
    def use_tool(self, tool_id, target):
        """
        Download and adapt community tool
        """
        tool = self.database.get(tool_id)
        
        # Adapt to current target (LLM)
        adapted = self.llm.adapt_tool(
            tool.code,
            target_ip=target.ip,
            target_service=target.service
        )
        
        # Track usage
        self.database.increment_downloads(tool_id)
        
        return adapted
```

---

## 📝 OPUS 4.6 EXECUTION CHECKLIST

Before you start any pentesting task, verify:

```markdown
## PRE-EXECUTION CHECKLIST

### Understanding
- [ ] Read user's objective completely
- [ ] Parsed scope.yaml (targets, constraints, objectives)
- [ ] Identified which phases are needed
- [ ] Estimated total time (inform user)

### Safety
- [ ] Confirmed target IPs are in scope
- [ ] Reviewed forbidden operations list
- [ ] Session isolation configured (local vs remote)
- [ ] Guardian Rails active

### Resources
- [ ] Required tools available or can be downloaded
- [ ] Sufficient disk space for logs
- [ ] Network connectivity verified
- [ ] Permission levels understood (what needs user approval)

### Execution Plan
- [ ] Created step-by-step plan
- [ ] Defined completion criteria for each phase
- [ ] Prepared rollback strategy if something fails
- [ ] Set up error reporting to Notion/Slack

### Communication
- [ ] Informed user of plan
- [ ] Set expectations (time, what might be found)
- [ ] Established check-in points (every 30 min or after each phase)
```

---

## 🔗 DOCUMENT STRUCTURE

This CORE document ties together:

1. **PLANNING.md** - Pre-engagement, scope definition, objectives
2. **RECONNAISSANCE.md** - OSINT, subdomain enum, initial footprinting
3. **SCANNING.md** - Port scanning, service detection, banner grabbing
4. **VULNERABILITY.md** - Vuln scanning, CVE matching, exploit search
5. **EXPLOITATION.md** - Exploit execution, shell obtaining, initial access
6. **POST_EXPLOITATION.md** - Privilege escalation, lateral movement, persistence
7. **REPORTING.md** - Documentation generation, findings summary
8. **RESEARCH.md** - Continuous learning, tool discovery, technique improvement

**Each document references this CORE for:**
- Session management
- Safety checks
- Completion detection
- Error handling

---

## 🚀 CURRENT DEPLOYMENT

**Model:** Phi-4 on Kaggle (temporary, for testing)
**Access:** ngrok public tunnel
**Frontend:** Claude Code (borrowed UI)

**Production Plan:**
- Model: Deploy to Google Cloud (stronger model)
- Access: Direct API endpoint (no ngrok)
- Frontend: Customized Claude Code UI

**What's NOT working yet:**
- MCP tool switching (single model only)
- Model selection in UI (hardcoded to Phi-4)
- Some advanced features (marked "Coming Soon")

---

## ⚠️ CRITICAL WARNINGS FOR OPUS 4.6

1. **NEVER execute commands without Guardian validation**
2. **ALWAYS verify target IP is in scope before ANY action**
3. **ASK user permission for:**
   - Data destruction
   - Privilege escalation attempts
   - Lateral movement to new hosts
   - Tool downloads from internet
4. **STOP immediately if:**
   - Self-destruction pattern detected
   - Out-of-scope target detected
   - User types "stop" or "abort"
   - Unrecoverable error (after 3 retry attempts)
5. **REPORT errors automatically to dev team**

---

<div align="center">

**🦅 YOU ARE NOW THE ORCHESTRATOR 🦅**

**Your mission: Execute OSCP-level pentesting autonomously while keeping the system and user safe.**

**Reference documents for each phase. Execute with precision. Report with clarity.**

</div>

---

**VERSION:** 2.0.0  
**LAST UPDATED:** 2026-02-13  
**NEXT DOCUMENT:** PLANNING.md  
**STATUS:** ✅ CORE ARCHITECTURE COMPLETE
