# 🧠 REDCLAW MEMAGENT

## Progress File System + Context Compaction + Session Recovery

---

## PURPOSE

- **Session Recovery:** Resume after crash
- **Context Compaction:** Prevent context overflow
- **Teammate Coordination:** Shared state awareness

---

## PROGRESS FILE STRUCTURE

```
# claude-progress.txt

## CURRENT STATUS
Phase: Exploitation
Target: 10.10.10.5
Active Teammates: 3
- teammate_recon_1 (COMPLETE)
- teammate_exploit_1 (RUNNING)
- teammate_validator_1 (PENDING)

## COMPLETED TASKS
✓ Task 1 [teammate_recon_1]: Nmap scan
  Result: Ports 22, 80, 443 open
  Timestamp: 2026-02-25 14:30:00

✓ Task 2 [teammate_recon_1]: Nuclei scan
  Result: CVE-2021-41773 found (Apache 2.4.49)
  Timestamp: 2026-02-25 14:50:00

## ONGOING TASKS
⏳ Task 3 [teammate_exploit_1]: Apache exploit
  Started: 2026-02-25 15:00:00
  Status: Downloading PoC from GitHub
  Progress: 60%

## PENDING TASKS
○ Task 4: Validation (depends on Task 3)
○ Task 5: Post-exploitation (depends on Task 4)

## FAILED ATTEMPTS (for MCTS backtracking)
✗ SMB Relay attack
  Reason: SMB signing enabled
  Attempted: 2026-02-25 14:45:00
  Branch: Abandoned

## KEY FINDINGS
- Apache 2.4.49 vulnerable to CVE-2021-41773
- No WAF detected
- SSH password authentication enabled

## NEXT PLANNED
→ After Task 3: Validate exploit with Validator Agent
→ If validated: Privilege escalation via LinPEAS
```

---

## IMPLEMENTATION

```python
class MemAgent:
    """
    Progress File manager
    """
    
    def __init__(self, progress_file="claude-progress.txt"):
        self.file_path = progress_file
    
    def update_task_status(self, task_id, status, result=None):
        """
        Update task in progress file
        """
        content = self.read()
        
        # Parse existing content
        lines = content.split('\n')
        
        # Find task line
        for i, line in enumerate(lines):
            if f"Task {task_id}" in line:
                if status == "COMPLETE":
                    lines[i] = f"✓ Task {task_id} [COMPLETE]: {result}"
                elif status == "RUNNING":
                    lines[i] = f"⏳ Task {task_id} [RUNNING]: {result}"
                elif status == "FAILED":
                    lines[i] = f"✗ Task {task_id} [FAILED]: {result}"
        
        self.write('\n'.join(lines))
    
    def add_finding(self, finding: str):
        """
        Add to KEY FINDINGS section
        """
        content = self.read()
        
        # Find KEY FINDINGS section
        findings_section = "## KEY FINDINGS\n"
        if findings_section in content:
            content = content.replace(
                findings_section,
                f"{findings_section}- {finding}\n"
            )
        
        self.write(content)
    
    def get_context_summary(self):
        """
        Compressed summary for new teammates
        """
        content = self.read()
        
        summary = {
            "completed_tasks": [],
            "ongoing_tasks": [],
            "key_findings": [],
            "failed_attempts": []
        }
        
        # Parse each section
        for line in content.split('\n'):
            if line.startswith('✓'):
                summary["completed_tasks"].append(line)
            elif line.startswith('⏳'):
                summary["ongoing_tasks"].append(line)
            elif line.startswith('✗'):
                summary["failed_attempts"].append(line)
            elif line.startswith('- ') and '## KEY FINDINGS' in content[:content.index(line)]:
                summary["key_findings"].append(line[2:])
        
        return summary
    
    def read(self):
        with open(self.file_path, 'r') as f:
            return f.read()
    
    def write(self, content):
        with open(self.file_path, 'w') as f:
            f.write(content)
```

---

## CONTEXT COMPACTION

```python
class ContextCompactor:
    """
    Prevent context overflow
    """
    
    async def compact_if_needed(self, conversation_history):
        """
        If context > 80% of limit, compact
        """
        token_count = self.count_tokens(conversation_history)
        limit = 32000  # qwen3-coder context limit
        
        if token_count > limit * 0.8:
            # Compact old messages
            compacted = await self.compress_history(conversation_history)
            
            # Keep only:
            # 1. System prompt
            # 2. Last 10 messages
            # 3. Compacted summary of older messages
            
            return [
                conversation_history[0],  # System prompt
                {"role": "assistant", "content": f"[Previous context summary: {compacted}]"},
                *conversation_history[-10:]  # Recent messages
            ]
        
        return conversation_history
    
    async def compress_history(self, messages):
        """
        Use LLM to summarize old messages
        """
        old_messages = messages[1:-10]  # Exclude system + recent
        
        prompt = f"""
        Summarize this conversation history in 200 words:
        
        {json.dumps(old_messages, indent=2)}
        
        Focus on: key decisions, findings, failed attempts.
        """
        
        summary = await openrouter_client.call_brain(prompt, temperature=0.3)
        return summary
```

---

## CRASH RECOVERY

```python
async def resume_teammate_after_crash(agent_id: str):
    """
    Resume teammate from Progress File
    """
    
    mem_agent = MemAgent()
    
    # 1. Read progress file
    summary = mem_agent.get_context_summary()
    
    # 2. Find last known state for this agent
    last_task = None
    for task in summary["ongoing_tasks"]:
        if agent_id in task:
            last_task = task
            break
    
    # 3. Reconstruct context
    recovery_context = f"""
    You are {agent_id} resuming after a crash.
    
    Your last task was: {last_task}
    
    Completed so far:
    {chr(10).join(summary["completed_tasks"])}
    
    Key findings:
    {chr(10).join(summary["key_findings"])}
    
    Continue from where you left off.
    """
    
    # 4. Spawn new teammate with recovery context
    teammate = Teammate(
        agent_id=agent_id,
        initial_context=recovery_context
    )
    
    await teammate.run()
```

---

## INTEGRATION WITH AGENT TEAMS

```python
# Teammate updates progress after each action

async def teammate_execute_task(self, task):
    # Before starting
    mem_agent.update_task_status(task.id, "RUNNING", "Started")
    
    # During execution
    result = await self.run_tool(task.tool, task.args)
    
    # If important finding
    if result.is_important:
        mem_agent.add_finding(result.description)
    
    # After completion
    mem_agent.update_task_status(task.id, "COMPLETE", result.summary)
    
    # Notify Team Lead via Mailbox
    await mailbox.send(
        from_agent=self.agent_id,
        to_agent="team_lead",
        message=f"Task {task.id} complete"
    )
```

---

**VERSION:** 3.1  
**COMPONENTS:** Progress File + Context Compaction + Crash Recovery
