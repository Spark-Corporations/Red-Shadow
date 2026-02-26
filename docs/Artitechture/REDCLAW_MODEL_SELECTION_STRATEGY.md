# 🧠 REDCLAW MODEL SELECTION STRATEGY

## Advanced Model Routing for Optimal Performance

---

## STRATEGY OVERVIEW

**Goal:** Use the right model for each task to maximize success rate while minimizing cost.

**Models:**
- **gpt-oss-120B** - Strategic reasoning (free, rate-limited)
- **qwen3-coder:free** - Code generation (free, rate-limited)

**Target Distribution:** 60% gpt-oss + 40% qwen3 (XBOW-inspired)

---

## DECISION MATRIX

### Task Categories

| Category | Indicators | Model | Reason |
|----------|-----------|-------|---------|
| **Strategic Analysis** | analyze, assess, evaluate, plan, decide | gpt-oss-120B | Better reasoning |
| **Code Generation** | write, code, script, generate, implement | qwen3-coder | Code-specialized |
| **Vulnerability Research** | CVE, research, find, discover | gpt-oss-120B | Complex queries |
| **Tool Automation** | automate, bash, command, execute | qwen3-coder | Script generation |
| **Exploit Development** | exploit, payload, shellcode | **BOTH** (alternating) | Needs both reasoning + code |
| **Report Writing** | report, document, summarize | gpt-oss-120B | Natural language |

---

## CLASSIFICATION ALGORITHM

```python
class ModelSelector:
    def __init__(self):
        self.reasoning_keywords = [
            'analyze', 'assess', 'evaluate', 'plan', 'decide', 
            'strategy', 'why', 'how', 'should', 'recommend'
        ]
        
        self.coding_keywords = [
            'write', 'code', 'script', 'generate', 'implement',
            'function', 'class', 'def', 'import', 'compile'
        ]
        
        self.both_keywords = [
            'exploit', 'vulnerability', 'attack', 'pentest'
        ]
    
    def classify_task(self, task_description: str) -> str:
        """
        Classify task and select model
        """
        
        desc_lower = task_description.lower()
        
        # Check for "both" indicators first
        if any(kw in desc_lower for kw in self.both_keywords):
            return "BOTH"
        
        # Count keyword matches
        reasoning_score = sum(
            1 for kw in self.reasoning_keywords
            if kw in desc_lower
        )
        
        coding_score = sum(
            1 for kw in self.coding_keywords
            if kw in desc_lower
        )
        
        # Decision
        if reasoning_score > coding_score:
            return "gpt-oss-120B"
        elif coding_score > reasoning_score:
            return "qwen3-coder:free"
        else:
            # Tie or no clear match - use context
            return self.use_context_hint(task_description)
    
    def use_context_hint(self, description: str) -> str:
        """
        Use additional context when keywords don't help
        """
        
        # Check for code-like patterns
        if re.search(r'[{}\[\]();]', description):
            return "qwen3-coder:free"
        
        # Check for question marks (reasoning)
        if '?' in description:
            return "gpt-oss-120B"
        
        # Default to gpt-oss (better at ambiguous tasks)
        return "gpt-oss-120B"
```

---

## BALANCE ENFORCEMENT

```python
class BalancedRouter:
    """
    Enforce 60/40 distribution
    """
    
    def __init__(self, target_gpt_ratio=0.6):
        self.target_ratio = target_gpt_ratio
        self.gpt_count = 0
        self.qwen_count = 0
        self.selector = ModelSelector()
    
    def route(self, task: dict) -> str:
        """
        Route task while maintaining balance
        """
        
        # Get natural classification
        natural_choice = self.selector.classify_task(task['description'])
        
        # Calculate current ratio
        total = self.gpt_count + self.qwen_count
        current_ratio = self.gpt_count / max(total, 1)
        
        # Check if we're off balance
        if current_ratio < self.target_ratio - 0.05:
            # Too few gpt calls, prefer gpt
            if natural_choice in ["gpt-oss-120B", "BOTH"]:
                choice = "gpt-oss-120B"
            else:
                # Force gpt if severely off balance
                if current_ratio < self.target_ratio - 0.15:
                    choice = "gpt-oss-120B"
                else:
                    choice = natural_choice
        
        elif current_ratio > self.target_ratio + 0.05:
            # Too many gpt calls, prefer qwen
            if natural_choice in ["qwen3-coder:free", "BOTH"]:
                choice = "qwen3-coder:free"
            else:
                # Force qwen if severely off balance
                if current_ratio > self.target_ratio + 0.15:
                    choice = "qwen3-coder:free"
                else:
                    choice = natural_choice
        
        else:
            # Balanced, use natural choice
            choice = natural_choice
        
        # Update counters
        if choice == "gpt-oss-120B":
            self.gpt_count += 1
        elif choice == "qwen3-coder:free":
            self.qwen_count += 1
        
        return choice
    
    def get_stats(self):
        total = self.gpt_count + self.qwen_count
        return {
            "gpt_count": self.gpt_count,
            "qwen_count": self.qwen_count,
            "gpt_ratio": self.gpt_count / max(total, 1),
            "qwen_ratio": self.qwen_count / max(total, 1),
            "target_ratio": self.target_ratio,
            "balanced": abs(self.gpt_count / max(total, 1) - self.target_ratio) < 0.05
        }
```

---

## ALTERNATING STRATEGY (Complex Tasks)

```python
async def handle_complex_task(task, router):
    """
    For tasks requiring both reasoning and code
    """
    
    # Phase 1: gpt-oss plans
    plan = await openrouter_client.call_brain(
        prompt=f"Plan: {task['description']}",
        model="gpt-oss-120B",
        temperature=0.6
    )
    
    # Phase 2: qwen3 implements
    code = await openrouter_client.call_hands(
        task=f"Implement: {plan}",
        model="qwen3-coder:free",
        temperature=0.2
    )
    
    # Phase 3: gpt-oss reviews (optional)
    if task.get('review_required', False):
        review = await openrouter_client.call_brain(
            prompt=f"Review code: {code}",
            model="gpt-oss-120B",
            temperature=0.4
        )
        
        return {"plan": plan, "code": code, "review": review}
    
    return {"plan": plan, "code": code}
```

---

## PERFORMANCE TRACKING

```python
class ModelPerformanceTracker:
    """
    Track success rate per model
    """
    
    def __init__(self):
        self.results = {
            "gpt-oss-120B": {"success": 0, "failure": 0},
            "qwen3-coder:free": {"success": 0, "failure": 0}
        }
    
    def record(self, model: str, success: bool):
        """
        Record task outcome
        """
        if success:
            self.results[model]["success"] += 1
        else:
            self.results[model]["failure"] += 1
    
    def get_success_rate(self, model: str) -> float:
        """
        Calculate success rate
        """
        total = self.results[model]["success"] + self.results[model]["failure"]
        return self.results[model]["success"] / max(total, 1)
    
    def get_report(self):
        """
        Generate performance report
        """
        return {
            "gpt-oss-120B": {
                "success_rate": self.get_success_rate("gpt-oss-120B"),
                "total_tasks": sum(self.results["gpt-oss-120B"].values())
            },
            "qwen3-coder:free": {
                "success_rate": self.get_success_rate("qwen3-coder:free"),
                "total_tasks": sum(self.results["qwen3-coder:free"].values())
            }
        }
    
    def recommend_adjustment(self):
        """
        Suggest routing adjustments based on performance
        """
        gpt_rate = self.get_success_rate("gpt-oss-120B")
        qwen_rate = self.get_success_rate("qwen3-coder:free")
        
        if gpt_rate > qwen_rate + 0.1:
            return "Consider increasing gpt-oss usage"
        elif qwen_rate > gpt_rate + 0.1:
            return "Consider increasing qwen3 usage"
        else:
            return "Current balance is optimal"
```

---

## INTEGRATION WITH TEAM LEAD

```python
class TeamLead:
    def __init__(self, openrouter_client):
        self.client = openrouter_client
        self.router = BalancedRouter(target_gpt_ratio=0.6)
        self.tracker = ModelPerformanceTracker()
    
    async def spawn_teammate(self, task: dict):
        """
        Spawn teammate with optimal model
        """
        
        # Select model
        model = self.router.route(task)
        
        logger.info(f"Selected {model} for task {task['id']}")
        
        # Create teammate
        teammate = Teammate(
            agent_id=f"teammate_{task['id']}",
            model=model,
            task=task
        )
        
        # Start and track
        result = await teammate.run()
        
        # Record performance
        self.tracker.record(model, result['success'])
        
        # Log stats periodically
        if (self.router.gpt_count + self.router.qwen_count) % 10 == 0:
            stats = self.router.get_stats()
            logger.info(f"Model distribution: {stats}")
            
            perf = self.tracker.get_report()
            logger.info(f"Performance: {perf}")
```

---

## EXAMPLES

```python
# Example 1: Clear reasoning task
task1 = {"description": "Analyze nmap results and plan attack strategy"}
model1 = router.route(task1)
# Result: "gpt-oss-120B" ✓

# Example 2: Clear coding task
task2 = {"description": "Write Python script to automate SQLMap"}
model2 = router.route(task2)
# Result: "qwen3-coder:free" ✓

# Example 3: Complex exploit task
task3 = {"description": "Exploit CVE-2021-41773 on Apache"}
model3 = router.route(task3)
# Result: "BOTH" → alternating gpt-oss → qwen3 ✓

# Example 4: Ambiguous task (balanced)
task4 = {"description": "Complete pentest on target"}
model4 = router.route(task4)
# Result: Depends on current balance (enforces 60/40)
```

---

**VERSION:** 3.1  
**TARGET:** 60% gpt-oss + 40% qwen3  
**MONITORING:** Real-time performance tracking  
**ADAPTIVE:** Self-adjusting based on success rates
