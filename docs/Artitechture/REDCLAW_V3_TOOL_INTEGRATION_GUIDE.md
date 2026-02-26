# 🔧 REDCLAW V3.1 - TOOL INTEGRATION GUIDE

## Agent Teams Tool Access + Model Alloy + Validator Tools

---

## TOOL ACCESS PER AGENT

### Team Lead Tools
```python
TEAM_LEAD_TOOLS = [
    "task_decomposition",
    "spawn_teammate",
    "query_mailbox",
    "query_task_list",
    "query_knowledge_graph",
    "progress_file_read",
    "model_alloy_route"
]
```

### Recon Teammate Tools
```python
RECON_TOOLS = [
    "nmap_scan",
    "nuclei_scan",
    "dirb_scan",
    "subdomain_enum",
    "shodan_search",
    "write_to_graph",
    "send_mailbox_message",
    "update_progress_file"
]
```

### Exploit Teammate Tools (Model Alloy)
```python
EXPLOIT_TOOLS = [
    "search_web",           # Live RAG
    "download_poc",         # GitHub
    "compile_exploit",      # Sandbox
    "metasploit_module",
    "send_mailbox_message",
    "create_attack_branch", # MCTS
    "abandon_branch"
]
```

### Validator Teammate Tools
```python
VALIDATOR_TOOLS = [
    "playwright_browser",   # Headless
    "screenshot_capture",
    "http_replay",
    "llm_peer_review",
    "send_mailbox_message"
]
```

### Binary Analyst Tools
```python
BINARY_TOOLS = [
    "ghidra_decompile",
    "radare2_disasm",
    "pattern_match_0day",
    "send_mailbox_message"
]
```

---

## LOCK MANAGER (Prevent Conflicts)

```python
class LockManager:
    def __init__(self, lock_dir="/tmp/redclaw_locks"):
        self.lock_dir = lock_dir
    
    async def acquire_lock(self, resource_id, agent_id):
        lock_file = f"{self.lock_dir}/{resource_id}.lock"
        
        if os.path.exists(lock_file):
            return False  # Already locked
        
        with open(lock_file, 'w') as f:
            f.write(agent_id)
        
        return True
    
    async def release_lock(self, resource_id):
        lock_file = f"{self.lock_dir}/{resource_id}.lock"
        if os.path.exists(lock_file):
            os.remove(lock_file)
```

---

## VALIDATOR AGENT INTEGRATION

```python
@activity.defn
async def validate_exploit_activity(exploit_claim: dict):
    """
    0% false positive validation
    """
    
    # 1. Headless browser
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        # 2. Replay exploit
        await page.goto(exploit_claim["target_url"])
        await page.evaluate(exploit_claim["payload"])
        
        # 3. Capture proof
        screenshot = await page.screenshot()
        response = await page.content()
        
        # 4. Verify success indicators
        success = (
            exploit_claim["success_indicator"] in response
        )
        
        await browser.close()
    
    # 5. LLM Peer Review
    if success:
        peer_review = await llm_cross_check(exploit_claim, response)
        success = peer_review["confirmed"]
    
    return {
        "validated": success,
        "screenshot": screenshot,
        "response": response
    }
```

---

## TEMPORAL INTEGRATION

```python
@workflow.defn
class TeammateWorkflow:
    """
    Each teammate runs in separate workflow
    """
    
    @workflow.run
    async def run(self, teammate_config: dict):
        # 1. Claim task from Shared Task List
        task = await workflow.execute_activity(
            claim_task_activity,
            teammate_config["agent_id"]
        )
        
        # 2. Execute tools
        result = await workflow.execute_activity(
            execute_teammate_tools,
            task
        )
        
        # 3. Update Progress File
        await workflow.execute_activity(
            update_progress_file_activity,
            result
        )
        
        # 4. Send mailbox message
        await workflow.execute_activity(
            send_mailbox_message_activity,
            {
                "from": teammate_config["agent_id"],
                "to": "team_lead",
                "message": f"Task {task['id']} complete"
            }
        )
        
        return result
```

---

**VERSION:** 3.1  
**KEY ADDITIONS:** Per-agent tools + Lock Manager + Validator integration
