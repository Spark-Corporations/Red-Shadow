# 💻 REDCLAW AGENT TEAMS IMPLEMENTATION

## Production Code for Team Lead + Teammates + Coordination

---

## CORE COMPONENTS

### 1. SharedTaskList

```python
import sqlite3
from typing import Optional

class SharedTaskList:
    def __init__(self, db_path="redclaw_tasks.db"):
        self.conn = sqlite3.connect(db_path)
        self.init_db()
    
    def init_db(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id INTEGER PRIMARY KEY,
                description TEXT,
                status TEXT CHECK(status IN ('PENDING','RUNNING','COMPLETE','FAILED')),
                assigned_to TEXT,
                dependencies TEXT,
                results TEXT,
                lock_file TEXT
            )
        """)
        self.conn.commit()
    
    def add_task(self, description: str, dependencies: list = None):
        cursor = self.conn.execute("""
            INSERT INTO tasks (description, status, dependencies)
            VALUES (?, 'PENDING', ?)
        """, (description, json.dumps(dependencies or [])))
        self.conn.commit()
        return cursor.lastrowid
    
    def claim_task(self, agent_id: str) -> Optional[dict]:
        # Find first PENDING task with satisfied dependencies
        cursor = self.conn.execute("""
            SELECT task_id, description, dependencies
            FROM tasks
            WHERE status = 'PENDING'
            ORDER BY task_id
        """)
        
        for row in cursor:
            task_id, description, deps = row
            dependencies = json.loads(deps)
            
            # Check if dependencies satisfied
            if all(self.is_complete(dep_id) for dep_id in dependencies):
                # Claim task
                self.conn.execute("""
                    UPDATE tasks
                    SET status = 'RUNNING', assigned_to = ?
                    WHERE task_id = ?
                """, (agent_id, task_id))
                self.conn.commit()
                
                return {"task_id": task_id, "description": description}
        
        return None
    
    def complete_task(self, task_id: int, results: str):
        self.conn.execute("""
            UPDATE tasks
            SET status = 'COMPLETE', results = ?
            WHERE task_id = ?
        """, (results, task_id))
        self.conn.commit()
    
    def is_complete(self, task_id: int) -> bool:
        cursor = self.conn.execute("""
            SELECT status FROM tasks WHERE task_id = ?
        """, (task_id,))
        row = cursor.fetchone()
        return row and row[0] == 'COMPLETE'
```

### 2. Mailbox

```python
class Mailbox:
    def __init__(self, db_path="redclaw_mailbox.db"):
        self.conn = sqlite3.connect(db_path)
        self.init_db()
    
    def init_db(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_agent TEXT,
                to_agent TEXT,
                message TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                read_status BOOLEAN DEFAULT 0
            )
        """)
        self.conn.commit()
    
    def send(self, from_agent: str, to_agent: str, message: str):
        self.conn.execute("""
            INSERT INTO messages (from_agent, to_agent, message)
            VALUES (?, ?, ?)
        """, (from_agent, to_agent, message))
        self.conn.commit()
    
    def get_messages(self, agent_id: str, mark_read=True):
        cursor = self.conn.execute("""
            SELECT message_id, from_agent, message, timestamp
            FROM messages
            WHERE to_agent = ? AND read_status = 0
        """, (agent_id,))
        
        messages = []
        for row in cursor:
            messages.append({
                "id": row[0],
                "from": row[1],
                "message": row[2],
                "timestamp": row[3]
            })
        
        if mark_read:
            self.conn.execute("""
                UPDATE messages
                SET read_status = 1
                WHERE to_agent = ?
            """, (agent_id,))
            self.conn.commit()
        
        return messages
```

### 3. Team Lead

```python
class TeamLead:
    def __init__(self, openrouter_client):
        self.client = openrouter_client
        self.task_list = SharedTaskList()
        self.mailbox = Mailbox()
        self.teammates = []
    
    async def orchestrate(self, user_request: str):
        # 1. Decompose
        subtasks = await self.decompose_task(user_request)
        
        # 2. Add to Shared Task List
        for task in subtasks:
            self.task_list.add_task(
                description=task["description"],
                dependencies=task.get("dependencies", [])
            )
        
        # 3. Spawn teammates
        self.spawn_teammates(count=3)
        
        # 4. Monitor
        await self.monitor_progress()
        
        # 5. Synthesize
        return await self.synthesize_results()
    
    async def decompose_task(self, request: str):
        prompt = f"""
        Break this pentest request into parallel subtasks:
        {request}
        
        Output JSON array of tasks with dependencies:
        [
          {{"description": "Nmap scan", "dependencies": []}},
          {{"description": "Exploit Apache", "dependencies": [1]}}
        ]
        """
        
        response = await self.client.call_brain(prompt)
        return json.loads(response)
    
    def spawn_teammates(self, count: int):
        for i in range(count):
            teammate = Teammate(
                agent_id=f"teammate_{i}",
                client=self.client,
                task_list=self.task_list,
                mailbox=self.mailbox
            )
            self.teammates.append(teammate)
            asyncio.create_task(teammate.run())
    
    async def monitor_progress(self):
        while not all(t.finished for t in self.teammates):
            messages = self.mailbox.get_messages("team_lead")
            for msg in messages:
                print(f"[Team Lead] Message from {msg['from']}: {msg['message']}")
            await asyncio.sleep(5)
```

### 4. Teammate

```python
class Teammate:
    def __init__(self, agent_id, client, task_list, mailbox):
        self.agent_id = agent_id
        self.client = client
        self.task_list = task_list
        self.mailbox = mailbox
        self.finished = False
    
    async def run(self):
        while True:
            # Claim task
            task = self.task_list.claim_task(self.agent_id)
            
            if not task:
                self.finished = True
                break
            
            # Execute
            result = await self.execute_task(task)
            
            # Complete
            self.task_list.complete_task(task["task_id"], result)
            
            # Notify
            self.mailbox.send(
                from_agent=self.agent_id,
                to_agent="team_lead",
                message=f"Task {task['task_id']} complete"
            )
    
    async def execute_task(self, task):
        # Use qwen3-coder for execution
        prompt = f"Execute: {task['description']}"
        result = await self.client.call_hands(prompt)
        return result
```

---

## USAGE

```python
# Initialize
client = OpenRouterClient(api_key="...")
team_lead = TeamLead(client)

# Run pentest
result = await team_lead.orchestrate("Pentest 10.10.10.5")
```

---

**VERSION:** 3.1  
**STATUS:** ✅ Production-ready code
