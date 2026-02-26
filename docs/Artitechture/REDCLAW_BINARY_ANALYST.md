# 🔬 REDCLAW BINARY ANALYST AGENT

## Ghidra + Radare2 + 0day Detection

---

## PURPOSE

Analyze binary executables for vulnerabilities that static scanners miss.

---

## ARCHITECTURE

```
Binary discovered (e.g., custom daemon)
         ↓
Team Lead spawns Binary Analyst
         ↓
    1. Ghidra decompile
    2. Radare2 disassembly
    3. Pattern matching (0day signatures)
    4. Report findings
```

---

## TOOLS

### Ghidra Integration
```python
async def ghidra_decompile(binary_path: str):
    """
    Decompile binary with Ghidra
    """
    cmd = [
        "analyzeHeadless",
        "/tmp/ghidra_projects",
        "redclaw_analysis",
        "-import", binary_path,
        "-postScript", "DecompileAll.py"
    ]
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE
    )
    
    stdout, _ = await process.communicate()
    
    # Parse decompiled C code
    return parse_ghidra_output(stdout.decode())
```

### Radare2 Integration
```python
async def radare2_analyze(binary_path: str):
    """
    Disassemble with Radare2
    """
    import r2pipe
    
    r2 = r2pipe.open(binary_path)
    r2.cmd("aaa")  # Analyze all
    
    # Get functions
    functions = r2.cmdj("aflj")
    
    # Get strings
    strings = r2.cmdj("izj")
    
    # Find dangerous functions
    dangerous = [
        f for f in functions
        if f['name'] in ['strcpy', 'gets', 'sprintf']
    ]
    
    return {
        "functions": functions,
        "strings": strings,
        "dangerous_calls": dangerous
    }
```

---

## 0DAY DETECTION

```python
class ZeroDayDetector:
    """
    Pattern matching for common vulnerability types
    """
    
    patterns = {
        "buffer_overflow": [
            r"strcpy\([^,]+,\s*[^)]+\)",
            r"gets\([^)]+\)",
            r"sprintf\([^,]+,"
        ],
        "format_string": [
            r"printf\([^,)]+\)",
            r"fprintf\([^,]+,\s*[^,)]+\)"
        ],
        "integer_overflow": [
            r"malloc\([^)]*\+[^)]*\)",
            r"calloc\([^)]*\*[^)]*\)"
        ],
        "use_after_free": [
            r"free\([^)]+\).*\n.*\1",  # Variable used after free
        ]
    }
    
    def scan(self, decompiled_code: str):
        findings = []
        
        for vuln_type, patterns in self.patterns.items():
            for pattern in patterns:
                matches = re.findall(pattern, decompiled_code)
                
                if matches:
                    findings.append({
                        "type": vuln_type,
                        "confidence": "medium",
                        "code_snippet": matches[0],
                        "line_number": self.find_line_number(decompiled_code, matches[0])
                    })
        
        return findings
```

---

## WORKFLOW

```python
@agent
class BinaryAnalystAgent:
    model = "gpt-oss-120B"  # Needs reasoning
    tools = ["ghidra", "radare2", "pattern_matcher"]
    
    async def analyze(self, binary_path: str):
        # 1. Decompile
        decompiled = await ghidra_decompile(binary_path)
        
        # 2. Disassemble
        disasm = await radare2_analyze(binary_path)
        
        # 3. Pattern matching
        detector = ZeroDayDetector()
        potential_vulns = detector.scan(decompiled["code"])
        
        # 4. LLM analysis
        llm_findings = await self.llm_analyze(
            decompiled, disasm, potential_vulns
        )
        
        # 5. Report
        return {
            "binary": binary_path,
            "vulnerabilities": llm_findings,
            "confidence": self.calculate_confidence(llm_findings)
        }
    
    async def llm_analyze(self, decompiled, disasm, patterns):
        prompt = f"""
        Analyze this binary for vulnerabilities.
        
        Decompiled code:
        {decompiled['code'][:2000]}
        
        Dangerous function calls:
        {json.dumps(disasm['dangerous_calls'])}
        
        Pattern matches:
        {json.dumps(patterns)}
        
        Questions:
        1. Are these genuine vulnerabilities?
        2. Can they be exploited?
        3. What's the exploitation path?
        
        Respond in JSON:
        {{
          "vulnerabilities": [
            {{
              "type": "buffer_overflow",
              "function": "process_input",
              "exploitable": true,
              "exploitation_path": "..."
            }}
          ]
        }}
        """
        
        response = await openrouter_client.call_brain(prompt)
        return json.loads(response)
```

---

## INTEGRATION

```python
# Team Lead detects binary
binary_info = {
    "path": "/usr/local/bin/custom_daemon",
    "discovered_by": "recon_teammate_1"
}

# Spawn Binary Analyst
mailbox.send(
    from_agent="team_lead",
    to_agent="binary_analyst_1",
    message={
        "type": "analyze_binary",
        "binary": binary_info
    }
)

# Binary Analyst runs
findings = await binary_analyst.analyze(binary_info["path"])

if findings["vulnerabilities"]:
    # Report potential 0day
    mailbox.send(
        from_agent="binary_analyst_1",
        to_agent="team_lead",
        message={
            "type": "0day_found",
            "findings": findings
        }
    )
```

---

**VERSION:** 3.1  
**TOOLS:** Ghidra + Radare2 + Pattern Matching + LLM Analysis  
**TARGET:** 0day detection in custom binaries
