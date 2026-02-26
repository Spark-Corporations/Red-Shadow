# 👔 REDCLAW TEAM LEAD GUIDE

## Complete Orchestrator Implementation Guide

---

## PURPOSE

Team Lead is the master orchestrator that coordinates all teammates and manages the entire pentest workflow.

---

## RESPONSIBILITIES

### 1. Task Decomposition

```python
async def decompose_task(self, user_request: str) -> list:
    """
    Break down pentest into parallel subtasks
    """
    
    system_prompt = """
    You are RedClaw Team Lead. Break pentest requests into:
    1. Independent tasks (can run parallel)
    2. Dependent tasks (must wait for others)
    
    Example:
    Input: "Pentest 10.10.10.5"
    Output:
    [
      {"id": 1, "desc": "Nmap scan", "deps": []},
      {"id": 2, "desc": "Nuclei scan", "deps": []},
      {"id": 3, "desc": "Exploit CVEs", "deps": [1,2]},
      {"id": 4, "desc": "Validate exploits", "deps": [3]}
    ]
    """
    
    prompt = f"""
    User Request: {user_request}
    
    Break into subtasks with dependencies.
    Output JSON array only.
    """
    
    response = await self.client.call_brain(
        prompt,
        system_prompt=system_prompt,
        temperature=0.6
    )
    
    tasks = json.loads(response)
    return tasks
```

---

### 2. Teammate Spawning

```python
async def spawn_teammate(self, task: dict) -> Teammate:
    """
    Create specialized teammate for task
    """
    
    # Select model (Model Alloy)
    model = self.model_alloy_router.select_model(task)
    
    # Select tools based on task type
    tools = self.select_tools_for_task(task)
    
    # Create teammate
    teammate = Teammate(
        agent_id=f"teammate_{task['id']}",
        model=model,
        tools=tools,
        task_list=self.shared_task_list,
        mailbox=self.mailbox,
        progress_file=self.progress_file
    )
    
    # Add to Shared Task List
    self.shared_task_list.add_task(
        task_id=task['id'],
        description=task['desc'],
        dependencies=task.get('deps', [])
    )
    
    # Start teammate (non-blocking)
    asyncio.create_task(teammate.run())
    
    # Track teammate
    self.teammates.append(teammate)
    
    return teammate

def select_tools_for_task(self, task: dict) -> list:
    """
    Assign tools based on task description
    """
    desc = task['desc'].lower()
    
    if 'nmap' in desc or 'scan' in desc:
        return ['nmap', 'nuclei', 'dirb']
    elif 'exploit' in desc:
        return ['metasploit', 'search_web', 'download_poc']
    elif 'validate' in desc:
        return ['playwright', 'screenshot', 'http_client']
    elif 'binary' in desc:
        return ['ghidra', 'radare2', 'pattern_matcher']
    else:
        return []  # No tools (pure reasoning)
```

---

### 3. Progress Monitoring

```python
async def monitor_progress(self):
    """
    Monitor teammates and respond to messages
    """
    
    while not self.all_teammates_finished():
        # Check mailbox
        messages = self.mailbox.get_messages("team_lead")
        
        for msg in messages:
            await self.process_message(msg)
        
        # Check for stuck teammates
        await self.check_for_stuck_teammates()
        
        # Update dashboard (if UI exists)
        self.update_dashboard()
        
        await asyncio.sleep(5)

async def process_message(self, msg: dict):
    """
    Handle teammate messages
    """
    
    if msg['type'] == 'task_complete':
        logger.info(f"Task {msg['task_id']} complete by {msg['from']}")
        
        # Check if any pending tasks can now start
        await self.check_dependencies()
    
    elif msg['type'] == 'help_needed':
        logger.warning(f"{msg['from']} needs help: {msg['issue']}")
        
        # Provide guidance
        await self.provide_guidance(msg['from'], msg['issue'])
    
    elif msg['type'] == 'validation_request':
        logger.info(f"Validation request from {msg['from']}")
        
        # Spawn Validator teammate
        await self.spawn_validator(msg['exploit_data'])
    
    elif msg['type'] == 'critical_finding':
        logger.critical(f"Critical finding: {msg['finding']}")
        
        # Broadcast to all teammates
        self.mailbox.broadcast(
            from_agent="team_lead",
            message=msg['finding']
        )

async def check_for_stuck_teammates(self):
    """
    Detect and handle stuck teammates
    """
    
    for teammate in self.teammates:
        if teammate.is_stuck():
            logger.warning(f"{teammate.agent_id} appears stuck")
            
            # Send intervention message
            self.mailbox.send(
                from_agent="team_lead",
                to_agent=teammate.agent_id,
                message={
                    "type": "intervention",
                    "suggestion": "Try alternative approach or abandon task"
                }
            )
```

---

### 4. Result Synthesis

```python
async def synthesize_results(self) -> dict:
    """
    Combine all teammate results into final report
    """
    
    # Collect all completed tasks
    completed_tasks = self.shared_task_list.get_completed_tasks()
    
    # Query Knowledge Graph for full attack path
    attack_path = self.knowledge_graph.get_attack_path()
    
    # Read Progress File for timeline
    timeline = self.progress_file.get_timeline()
    
    # Generate synthesis prompt
    prompt = f"""
    Synthesize pentest results:
    
    Completed Tasks:
    {json.dumps(completed_tasks, indent=2)}
    
    Attack Path:
    {json.dumps(attack_path, indent=2)}
    
    Timeline:
    {json.dumps(timeline, indent=2)}
    
    Generate executive summary:
    1. Overall assessment
    2. Critical findings
    3. Attack path summary
    4. Recommendations
    """
    
    synthesis = await self.client.call_brain(prompt, temperature=0.3)
    
    return {
        "executive_summary": synthesis,
        "completed_tasks": completed_tasks,
        "attack_path": attack_path,
        "timeline": timeline
    }
```

---

### 5. Cleanup

```python
async def cleanup(self):
    """
    Terminate all teammates and clean up resources
    """
    
    logger.info("Starting cleanup...")
    
    # Send termination signal to all teammates
    for teammate in self.teammates:
        self.mailbox.send(
            from_agent="team_lead",
            to_agent=teammate.agent_id,
            message={"type": "terminate"}
        )
    
    # Wait for teammates to finish gracefully
    await asyncio.wait_for(
        asyncio.gather(*[t.wait_for_finish() for t in self.teammates]),
        timeout=30
    )
    
    # Archive Progress File
    self.progress_file.archive()
    
    # Export Knowledge Graph
    self.knowledge_graph.export("final_graph.json")
    
    # Close database connections
    self.shared_task_list.close()
    self.mailbox.close()
    
    logger.info("Cleanup complete")
```

---

## FULL ORCHESTRATION WORKFLOW

```python
class TeamLead:
    def __init__(self, openrouter_client, config):
        self.client = openrouter_client
        self.config = config
        
        # Core components
        self.shared_task_list = SharedTaskList()
        self.mailbox = Mailbox()
        self.progress_file = ProgressFile()
        self.knowledge_graph = get_knowledge_graph()
        self.model_alloy_router = ModelAlloyRouter()
        
        # State
        self.teammates = []
        self.running = False
    
    async def orchestrate(self, user_request: str):
        """
        Main orchestration loop
        """
        
        try:
            self.running = True
            
            # 1. Initialize Progress File
            self.progress_file.initialize(user_request)
            
            # 2. Decompose task
            logger.info("Decomposing task...")
            tasks = await self.decompose_task(user_request)
            
            # 3. Spawn teammates
            logger.info(f"Spawning {len(tasks)} teammates...")
            for task in tasks:
                await self.spawn_teammate(task)
            
            # 4. Monitor progress
            logger.info("Monitoring progress...")
            await self.monitor_progress()
            
            # 5. Synthesize results
            logger.info("Synthesizing results...")
            results = await self.synthesize_results()
            
            # 6. Generate report
            logger.info("Generating report...")
            report = await self.generate_report(results)
            
            return report
        
        finally:
            # 7. Cleanup
            await self.cleanup()
            self.running = False
    
    async def generate_report(self, results: dict):
        """
        Generate final causal chain report
        """
        from .causal_chain_reporting import CausalChainReport
        
        reporter = CausalChainReport()
        
        # Get all validated findings
        findings = results['completed_tasks']
        validated_findings = [
            f for f in findings
            if f.get('validated', False)
        ]
        
        # Generate report for each finding
        report = {
            "executive_summary": results['executive_summary'],
            "findings": [
                reporter.generate(finding, finding['validation'])
                for finding in validated_findings
            ],
            "attack_path": results['attack_path'],
            "timeline": results['timeline']
        }
        
        # Export to multiple formats
        reporter.export_html(report, "report.html")
        reporter.export_pdf(report, "report.pdf")
        reporter.export_json(report, "report.json")
        
        return report
```

---

## USAGE EXAMPLE

```python
# Initialize
client = OpenRouterClient(api_key=os.getenv("OPENROUTER_API_KEY"))
config = load_config("redclaw_v3.yaml")

team_lead = TeamLead(client, config)

# Run pentest
report = await team_lead.orchestrate("Pentest 10.10.10.5 --parallel")

print(f"Report generated: {report}")
```

---

## ERROR HANDLING

```python
async def orchestrate(self, user_request: str):
    """
    Orchestration with error handling
    """
    
    try:
        # Normal flow...
        pass
    
    except TeamLeadException as e:
        logger.error(f"Team Lead error: {e}")
        
        # Attempt recovery
        await self.attempt_recovery()
    
    except TeammateException as e:
        logger.error(f"Teammate error: {e}")
        
        # Respawn failed teammate
        await self.respawn_teammate(e.teammate_id)
    
    except Exception as e:
        logger.critical(f"Unexpected error: {e}")
        
        # Emergency cleanup
        await self.emergency_cleanup()
        
        raise

async def attempt_recovery(self):
    """
    Recover from Team Lead errors
    """
    
    # Read Progress File to determine state
    state = self.progress_file.get_current_state()
    
    # Resume from last checkpoint
    await self.resume_from_checkpoint(state)
```

---

**VERSION:** 3.1  
**ROLE:** Master Orchestrator  
**COMPLEXITY:** High  
**CRITICAL:** Yes - single point of coordination
