# 🔀 REDCLAW V3.1 — ORCHESTRATION + ROUTER

## Team Lead Orchestration + Model Alloy Routing

---

## TEAM LEAD ORCHESTRATION

```python
class TeamLead:
    model = "gpt-oss-120B"
    
    async def orchestrate(self, user_request):
        # 1. Task decomposition
        tasks = await self.decompose(user_request)
        
        # 2. Spawn teammates
        teammates = []
        for task in tasks:
            teammate = await self.spawn_teammate(task)
            teammates.append(teammate)
        
        # 3. Monitor progress
        while not all_complete(teammates):
            messages = mailbox.check()
            self.process_messages(messages)
            await asyncio.sleep(5)
        
        # 4. Synthesize results
        return self.synthesize_results(teammates)
    
    async def spawn_teammate(self, task):
        teammate = Teammate(
            agent_id=f"teammate_{task.id}",
            model=self.select_model(task),
            tools=self.select_tools(task),
            task_list=shared_task_list,
            mailbox=mailbox
        )
        asyncio.create_task(teammate.run())
        return teammate
```

---

## MODEL ALLOY ROUTER

```python
class ModelAlloyRouter:
    """
    XBOW-inspired strategic switching
    Target: 60% gpt-oss + 40% qwen3
    """
    
    def __init__(self):
        self.gpt_count = 0
        self.qwen_count = 0
    
    def route(self, task):
        # Classification
        if "analyze" in task or "plan" in task:
            self.gpt_count += 1
            return "gpt-oss-120B"
        
        elif "code" in task or "script" in task:
            self.qwen_count += 1
            return "qwen3-coder:free"
        
        # Complex: alternate
        else:
            ratio = self.gpt_count / max(self.gpt_count + self.qwen_count, 1)
            if ratio < 0.6:
                self.gpt_count += 1
                return "gpt-oss-120B"
            else:
                self.qwen_count += 1
                return "qwen3-coder:free"
```

---

## SHARED TASK LIST (SQLite)

```sql
CREATE TABLE tasks (
    task_id INTEGER PRIMARY KEY,
    description TEXT,
    status TEXT CHECK(status IN ('PENDING','RUNNING','COMPLETE','FAILED')),
    assigned_to TEXT,
    dependencies TEXT, -- JSON array
    results TEXT,
    lock_file TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## MAILBOX (SQLite)

```sql
CREATE TABLE messages (
    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_agent TEXT NOT NULL,
    to_agent TEXT NOT NULL,
    message TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    read_status BOOLEAN DEFAULT 0
);
```

---

**VERSION:** 3.1  
**COMPONENTS:** Team Lead + Model Alloy + Coordination Layer
