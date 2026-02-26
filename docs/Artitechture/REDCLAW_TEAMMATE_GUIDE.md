# 👨‍💻 REDCLAW TEAMMATE GUIDE

## Worker Agent Implementation Guide

---

## PURPOSE

Teammates are specialized worker agents that execute specific tasks independently while coordinating via Shared Task List and Mailbox.

---

## CORE BEHAVIOR

### 1. Claim Task from Queue

```python
async def claim_task(self) -> Optional[dict]:
    """
    Claim next available task from Shared Task List
    """
    
    # Loop until task found or no tasks left
    while True:
        task = self.task_list.claim_task(self.agent_id)
        
        if task:
            logger.info(f"{self.agent_id} claimed task {task['task_id']}")
            
            # Update Progress File
            self.progress_file.update_task_status(
                task['task_id'],
                "RUNNING",
                f"Started by {self.agent_id}"
            )
            
            return task
        
        # No available tasks (all taken or dependencies not met)
        await asyncio.sleep(2)
        
        # Check if all tasks complete
        if self.task_list.all_tasks_complete():
            return None  # No more work
```

---

### 2. Execute Task with Tools

```python
async def execute_task(self, task: dict) -> dict:
    """
    Execute task using available tools
    """
    
    # Build execution context
    context = await self.build_context(task)
    
    # Select tool based on task
    tool = self.select_tool(task['description'])
    
    if tool:
        # Execute tool
        result = await self.execute_tool(tool, task, context)
    else:
        # Pure reasoning task (no tools)
        result = await self.reason_about_task(task, context)
    
    return result

async def build_context(self, task: dict) -> str:
    """
    Build context from Progress File + Knowledge Graph
    """
    
    # Read Progress File
    progress_summary = self.progress_file.get_context_summary()
    
    # Query Knowledge Graph
    graph_data = self.knowledge_graph.query_natural_language(
        f"What do we know about the target for task {task['task_id']}?"
    )
    
    # Check Memory RAG
    rag_results = await self.memory_rag.query_relevant_info(task['description'])
    
    context = f"""
Previous work completed:
{chr(10).join(progress_summary['completed_tasks'])}

Current knowledge:
{json.dumps(graph_data, indent=2)}

Similar past exploits:
{json.dumps(rag_results, indent=2)}

Your task: {task['description']}
"""
    
    return context

async def execute_tool(self, tool: str, task: dict, context: str):
    """
    Execute specific tool
    """
    
    if tool == 'nmap':
        return await self.run_nmap(task, context)
    elif tool == 'nuclei':
        return await self.run_nuclei(task, context)
    elif tool == 'exploit':
        return await self.run_exploit(task, context)
    # ... more tools
```

---

### 3. Report Results via Mailbox

```python
async def report_result(self, task: dict, result: dict):
    """
    Report task completion to Team Lead
    """
    
    # Update Shared Task List
    self.task_list.complete_task(
        task['task_id'],
        json.dumps(result)
    )
    
    # Update Progress File
    self.progress_file.update_task_status(
        task['task_id'],
        "COMPLETE",
        result['summary']
    )
    
    # Add findings to Knowledge Graph
    if result.get('findings'):
        await self.update_knowledge_graph(result['findings'])
    
    # Send mailbox message to Team Lead
    self.mailbox.send(
        from_agent=self.agent_id,
        to_agent="team_lead",
        message={
            "type": "task_complete",
            "task_id": task['task_id'],
            "summary": result['summary'],
            "critical": result.get('critical', False)
        }
    )
```

---

### 4. Handle Mailbox Messages

```python
async def check_mailbox(self):
    """
    Check for messages from Team Lead or other teammates
    """
    
    messages = self.mailbox.get_messages(self.agent_id)
    
    for msg in messages:
        await self.handle_message(msg)

async def handle_message(self, msg: dict):
    """
    Handle different message types
    """
    
    if msg['type'] == 'terminate':
        logger.info(f"{self.agent_id} received termination signal")
        self.running = False
    
    elif msg['type'] == 'intervention':
        logger.warning(f"Team Lead intervention: {msg['suggestion']}")
        
        # Adjust behavior based on suggestion
        await self.apply_intervention(msg['suggestion'])
    
    elif msg['type'] == 'broadcast':
        logger.info(f"Broadcast message: {msg['message']}")
        
        # Update context with broadcast info
        self.additional_context = msg['message']
    
    elif msg['type'] == 'peer_request':
        logger.info(f"Peer request from {msg['from']}: {msg['request']}")
        
        # Respond to peer teammate
        await self.respond_to_peer(msg)
```

---

## SPECIALIZED TEAMMATE TYPES

### Recon Teammate

```python
class ReconTeammate(Teammate):
    """
    Specializes in reconnaissance
    """
    
    tools = ['nmap', 'nuclei', 'dirb', 'subdomain_enum']
    
    async def run_nmap(self, task, context):
        """
        Execute nmap scan
        """
        target = self.extract_target(task['description'])
        
        # Call nmap activity (via Temporal)
        result = await self.temporal_client.execute_activity(
            run_nmap_activity,
            target
        )
        
        return {
            "summary": f"Scanned {target}, found {len(result['open_ports'])} ports",
            "findings": result,
            "critical": any(p in [21, 23, 445] for p in result['open_ports'])
        }
```

---

### Exploit Teammate (Model Alloy)

```python
class ExploitTeammate(Teammate):
    """
    Specializes in exploitation (uses Model Alloy)
    """
    
    tools = ['metasploit', 'search_web', 'download_poc', 'compile_exploit']
    
    async def run_exploit(self, task, context):
        """
        Execute exploit using Model Alloy
        """
        
        # Step 1: gpt-oss plans
        plan = await self.client.call_brain(
            f"Context: {context}\nPlan exploitation strategy",
            model="gpt-oss-120B"
        )
        
        # Step 2: qwen3 codes
        exploit_code = await self.client.call_hands(
            f"Implement: {plan}",
            model="qwen3-coder:free"
        )
        
        # Step 3: Execute
        result = await self.execute_exploit_code(exploit_code)
        
        # Step 4: If successful, request validation
        if result['success']:
            self.mailbox.send(
                from_agent=self.agent_id,
                to_agent="team_lead",
                message={
                    "type": "validation_request",
                    "exploit_data": result
                }
            )
        
        return result
```

---

### Validator Teammate

```python
class ValidatorTeammate(Teammate):
    """
    Specializes in validation (0% false positive)
    """
    
    tools = ['playwright', 'screenshot', 'http_client']
    
    async def validate_exploit(self, exploit_claim):
        """
        Independent validation
        """
        
        # Reproduce exploit
        success = await self.reproduce_exploit(exploit_claim)
        
        if not success:
            return {"validated": False, "reason": "Cannot reproduce"}
        
        # Capture proof
        screenshot = await self.capture_screenshot()
        
        # LLM Peer Review
        peer_review = await self.llm_peer_review(exploit_claim, screenshot)
        
        if not peer_review['confirmed']:
            return {"validated": False, "reason": "Peer review failed"}
        
        # All checks passed
        return {
            "validated": True,
            "proof": {"screenshot": screenshot},
            "confidence": "high"
        }
```

---

## MAIN RUN LOOP

```python
class Teammate:
    async def run(self):
        """
        Main execution loop
        """
        
        self.running = True
        
        try:
            while self.running:
                # 1. Check mailbox
                await self.check_mailbox()
                
                # 2. Claim task
                task = await self.claim_task()
                
                if not task:
                    break  # No more tasks
                
                # 3. Execute task
                result = await self.execute_task(task)
                
                # 4. Report result
                await self.report_result(task, result)
        
        except Exception as e:
            logger.error(f"{self.agent_id} error: {e}")
            
            # Notify Team Lead of failure
            self.mailbox.send(
                from_agent=self.agent_id,
                to_agent="team_lead",
                message={
                    "type": "error",
                    "error": str(e),
                    "task_id": task.get('task_id') if 'task' in locals() else None
                }
            )
        
        finally:
            logger.info(f"{self.agent_id} finished")
            self.finished = True
```

---

## CONTEXT COMPACTION

```python
async def compact_context_if_needed(self):
    """
    Prevent context overflow
    """
    
    token_count = self.count_tokens(self.conversation_history)
    
    if token_count > self.context_limit * 0.8:
        logger.warning(f"{self.agent_id} context near limit, compacting...")
        
        # Summarize old messages
        summary = await self.client.call_brain(
            f"Summarize: {self.conversation_history[:100]}",
            temperature=0.3
        )
        
        # Keep system prompt + summary + recent messages
        self.conversation_history = [
            self.conversation_history[0],  # System prompt
            {"role": "assistant", "content": f"[Summary: {summary}]"},
            *self.conversation_history[-20:]  # Recent 20 messages
        ]
```

---

## PEER-TO-PEER COMMUNICATION

```python
async def request_help_from_peer(self, peer_id: str, question: str):
    """
    Ask another teammate for help
    """
    
    self.mailbox.send(
        from_agent=self.agent_id,
        to_agent=peer_id,
        message={
            "type": "peer_request",
            "request": question
        }
    )
    
    # Wait for response (with timeout)
    response = await self.wait_for_peer_response(peer_id, timeout=30)
    
    return response

async def respond_to_peer(self, msg: dict):
    """
    Respond to peer teammate request
    """
    
    answer = await self.client.call_brain(
        f"Peer question: {msg['request']}\nContext: {self.additional_context}",
        temperature=0.5
    )
    
    self.mailbox.send(
        from_agent=self.agent_id,
        to_agent=msg['from'],
        message={
            "type": "peer_response",
            "answer": answer
        }
    )
```

---

**VERSION:** 3.1  
**ROLE:** Worker/Executor  
**COORDINATION:** Shared Task List + Mailbox  
**SPECIALIZATIONS:** Recon, Exploit, Validator, Binary Analyst
