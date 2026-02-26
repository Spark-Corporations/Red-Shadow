# 🆕 REDCLAW AGENT TEAMS ARCHITECTURE

## Complete Multi-Agent System Design

---

## CORE CONCEPTS

### Team Lead vs Teammates

**Team Lead (Orchestrator):**
- Model: gpt-oss-120B
- Role: Strategic coordination
- Responsibilities:
  - Task decomposition
  - Teammate spawning
  - Progress monitoring
  - Result synthesis
  - Model Alloy routing

**Teammates (Workers):**
- Model: qwen3-coder:free (or ALLOY)
- Role: Execution specialists
- Types:
  - Recon Teammate
  - Exploit Teammate (Model Alloy)
  - Validator Teammate
  - Binary Analyst Teammate

---

## SUBAGENTS vs AGENT TEAMS

| Feature | Subagents | Agent Teams |
|---------|-----------|-------------|
| **Context** | Share parent context | Isolated per teammate |
| **Communication** | Hub-and-spoke (via parent) | Mesh (via Mailbox) |
| **Coordination** | Centralized (parent only) | Distributed (Shared Task List) |
| **When to use** | Simple parallel tasks | Complex coordination needed |

---

## SHARED COORDINATION

### Shared Task List (SQLite)
```sql
CREATE TABLE tasks (
    task_id INTEGER PRIMARY KEY,
    description TEXT,
    status TEXT CHECK(status IN ('PENDING','RUNNING','COMPLETE')),
    assigned_to TEXT,
    dependencies TEXT,
    results TEXT,
    lock_file TEXT
);
```

### Mailbox (SQLite)
```sql
CREATE TABLE messages (
    message_id INTEGER PRIMARY KEY,
    from_agent TEXT,
    to_agent TEXT,
    message TEXT,
    timestamp TIMESTAMP,
    read_status BOOLEAN
);
```

### Progress File (TXT)
```
## CURRENT STATUS
Phase: Exploitation
Teammates: 3 active

## COMPLETED
✓ Task 1: Nmap scan

## ONGOING
⏳ Task 2: Exploit attempt
```

---

## WORKFLOW

```
User Request
    ↓
Team Lead decomposes
    ↓
Spawn Teammates (parallel)
    ↓
Teammates claim tasks
    ↓
Execute + update Progress
    ↓
Send Mailbox messages
    ↓
Team Lead synthesizes
    ↓
Report delivered
```

---

**VERSION:** 3.1  
**STATUS:** ✅ Architecture defined
