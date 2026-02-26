# 🎓 REDCLAW FINE-TUNING PIPELINE

## CoT Dataset + Domain Adaptation

---

## PURPOSE

Fine-tune models for pentest-specific tasks to improve performance beyond base models.

---

## STRATEGY

### Target Models
1. **Qwen3-32B** - Coding tasks
2. **DeepSeek-R1** - Reasoning tasks

### Fine-tuning Method
- **LoRA** (Low-Rank Adaptation) - Parameter efficient
- **QLoRA** - Quantized LoRA for resource efficiency

---

## DATASET COLLECTION

### Chain-of-Thought Format

```json
{
  "instruction": "Analyze this nmap scan and identify attack vectors",
  "input": "PORT   STATE SERVICE VERSION\n22/tcp open  ssh     OpenSSH 7.4\n80/tcp open  http    Apache 2.4.49",
  "output": "<think>\nStep 1: Identify services\n- SSH on port 22 (OpenSSH 7.4)\n- HTTP on port 80 (Apache 2.4.49)\n\nStep 2: Check for known vulnerabilities\n- Apache 2.4.49: CVE-2021-41773 (Critical RCE)\n- OpenSSH 7.4: CVE-2018-15473 (Username enumeration)\n\nStep 3: Prioritize attack vectors\n1. Apache RCE (highest impact)\n2. SSH enumeration (reconnaissance)\n\nStep 4: Recommend exploitation path\nStart with Apache RCE for immediate shell access\n</think>\n\nAttack vectors identified:\n1. CVE-2021-41773 on Apache 2.4.49 (CRITICAL)\n2. CVE-2018-15473 on OpenSSH 7.4 (MEDIUM)"
}
```

### Data Sources

1. **Successful Exploits** (from Memory RAG)
   - Extract CoT from successful penetration tests
   - Include reasoning steps

2. **Failed Attempts** (learning from failures)
   - Document why exploit failed
   - Alternative approaches tried

3. **Manual Annotations**
   - Expert pentester reviews
   - Add reasoning annotations

---

## COLLECTION SCRIPT

```python
class CoTDatasetCollector:
    def __init__(self):
        self.dataset = []
    
    def collect_from_memory_rag(self):
        """
        Extract successful exploits from Memory RAG
        """
        rag = MemoryRAG()
        exploits = rag.exploit_collection.get()
        
        for exploit in exploits:
            # Generate CoT from exploit logs
            cot = self.generate_cot_from_logs(exploit)
            
            self.dataset.append({
                "instruction": f"Exploit {exploit['service']} {exploit['version']}",
                "input": exploit['target_info'],
                "output": cot
            })
    
    def generate_cot_from_logs(self, exploit):
        """
        Convert exploit logs to CoT format
        """
        return f"""
<think>
Step 1: Service identification
{exploit['recon_step']}

Step 2: Vulnerability research
{exploit['vuln_research']}

Step 3: Exploit selection
{exploit['exploit_selection']}

Step 4: Payload adaptation
{exploit['payload_adaptation']}

Step 5: Execution
{exploit['execution_log']}
</think>

{exploit['result_summary']}
"""
    
    def save_dataset(self, output_path="pentest_cot_dataset.jsonl"):
        with open(output_path, 'w') as f:
            for item in self.dataset:
                f.write(json.dumps(item) + '\n')
```

---

## FINE-TUNING PROCESS

### Using Unsloth (Efficient Training)

```python
from unsloth import FastLanguageModel
import torch

# 1. Load base model
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="Qwen/Qwen2.5-Coder-32B-Instruct",
    max_seq_length=8192,
    dtype=torch.float16,
    load_in_4bit=True  # QLoRA
)

# 2. Configure LoRA
model = FastLanguageModel.get_peft_model(
    model,
    r=16,  # LoRA rank
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    lora_alpha=16,
    lora_dropout=0.05,
    bias="none",
    use_gradient_checkpointing=True
)

# 3. Load dataset
from datasets import load_dataset

dataset = load_dataset(
    "json",
    data_files="pentest_cot_dataset.jsonl",
    split="train"
)

# 4. Training arguments
from transformers import TrainingArguments

training_args = TrainingArguments(
    output_dir="./redclaw_qwen_finetuned",
    num_train_epochs=3,
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,
    learning_rate=2e-4,
    fp16=True,
    logging_steps=10,
    save_steps=100
)

# 5. Train
from trl import SFTTrainer

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    args=training_args,
    max_seq_length=8192
)

trainer.train()

# 6. Save
model.save_pretrained("redclaw_qwen_lora")
```

---

## EVALUATION

### Benchmark Tasks

1. **Vulnerability Identification**
   - Input: Service scan
   - Expected: Correct CVE + CVSS

2. **Exploit Code Generation**
   - Input: CVE description
   - Expected: Working exploit code

3. **Attack Path Planning**
   - Input: Network topology
   - Expected: Optimal exploitation sequence

### Metrics

```python
def evaluate_finetuned_model(model, test_dataset):
    metrics = {
        "vuln_identification_accuracy": 0,
        "exploit_success_rate": 0,
        "code_quality_score": 0
    }
    
    for example in test_dataset:
        # Test vulnerability identification
        pred_cve = model.predict(example['input'])
        if pred_cve == example['expected_cve']:
            metrics["vuln_identification_accuracy"] += 1
        
        # Test exploit generation
        exploit_code = model.generate_exploit(example['cve'])
        if test_exploit_in_sandbox(exploit_code):
            metrics["exploit_success_rate"] += 1
    
    # Normalize
    for key in metrics:
        metrics[key] /= len(test_dataset)
    
    return metrics
```

---

## DEPLOYMENT

### LoRA Adapter Loading

```python
# Load fine-tuned adapter at runtime
from peft import PeftModel

base_model = AutoModelForCausalLM.from_pretrained("Qwen/Qwen2.5-Coder-32B")
finetuned_model = PeftModel.from_pretrained(
    base_model,
    "redclaw_qwen_lora"
)

# Use in production
result = finetuned_model.generate(prompt)
```

---

## CONTINUOUS IMPROVEMENT

```python
# After each successful pentest
async def update_training_data(pentest_result):
    """
    Add successful pentest to training dataset
    """
    
    # Extract CoT
    cot = extract_cot_from_pentest(pentest_result)
    
    # Add to dataset
    collector = CoTDatasetCollector()
    collector.dataset.append(cot)
    collector.save_dataset()
    
    # Trigger periodic retraining (e.g., weekly)
    if should_retrain():
        schedule_finetuning_job()
```

---

**VERSION:** 3.1  
**MODELS:** Qwen3-32B + DeepSeek-R1  
**METHOD:** LoRA/QLoRA  
**DATA:** CoT format from successful exploits
