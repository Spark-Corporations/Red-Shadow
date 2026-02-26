# 🔀 REDCLAW MODEL ALLOY

## XBOW-Inspired Strategic Model Switching

---

## CONCEPT

**Model Alloy:** Use multiple models strategically  
**RedClaw Implementation:** 60% gpt-oss-120B + 40% qwen3-coder:free

**Why?** Different models excel at different tasks.

---

## DECISION MATRIX

| Task Type | Model | Reason |
|-----------|-------|--------|
| Strategic planning | gpt-oss-120B | Better reasoning |
| Code generation | qwen3-coder | Faster, specialized |
| Exploit analysis | gpt-oss-120B | Complex logic |
| Script writing | qwen3-coder | Code-focused |
| Complex exploit | BOTH (alternate) | Combine strengths |

---

## IMPLEMENTATION

```python
class ModelAlloyRouter:
    def __init__(self):
        self.gpt_count = 0
        self.qwen_count = 0
        self.target_ratio = 0.6  # 60% gpt
    
    def select_model(self, task: dict) -> str:
        # Rule-based
        if "analyze" in task or "plan" in task:
            self.gpt_count += 1
            return "gpt-oss-120B"
        
        if "code" in task or "script" in task:
            self.qwen_count += 1
            return "qwen3-coder:free"
        
        # Balance to maintain 60/40
        current_ratio = self.gpt_count / max(self.gpt_count + self.qwen_count, 1)
        
        if current_ratio < self.target_ratio:
            self.gpt_count += 1
            return "gpt-oss-120B"
        else:
            self.qwen_count += 1
            return "qwen3-coder:free"
    
    def get_stats(self):
        total = self.gpt_count + self.qwen_count
        return {
            "gpt_percentage": self.gpt_count / total if total > 0 else 0,
            "qwen_percentage": self.qwen_count / total if total > 0 else 0,
            "total_calls": total
        }
```

---

## ALTERNATING STRATEGY (Complex Tasks)

```python
async def exploit_with_alloy(target):
    # Step 1: gpt-oss plans
    plan = await client.call_brain(
        f"Analyze {target} and plan exploit strategy",
        model="gpt-oss-120B"
    )
    
    # Step 2: qwen3 codes
    code = await client.call_hands(
        f"Implement this plan: {plan}",
        model="qwen3-coder:free"
    )
    
    # Step 3: gpt-oss reviews
    review = await client.call_brain(
        f"Review this exploit code: {code}",
        model="gpt-oss-120B"
    )
    
    return {"plan": plan, "code": code, "review": review}
```

---

## PERFORMANCE TRACKING

```python
class AlloyMetrics:
    def __init__(self):
        self.model_performance = {
            "gpt-oss-120B": {"success": 0, "total": 0},
            "qwen3-coder:free": {"success": 0, "total": 0}
        }
    
    def record_result(self, model: str, success: bool):
        self.model_performance[model]["total"] += 1
        if success:
            self.model_performance[model]["success"] += 1
    
    def get_success_rates(self):
        return {
            model: stats["success"] / stats["total"] if stats["total"] > 0 else 0
            for model, stats in self.model_performance.items()
        }
```

---

**VERSION:** 3.1  
**TARGET RATIO:** 60% gpt-oss + 40% qwen3  
**XBOW ALIGNMENT:** Strategic switching implemented
