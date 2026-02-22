# 🔧 REDCLAW V3.0 - TOOL INTEGRATION GUIDE

## Complete Guide: Temporal Activities + MCP Servers + Knowledge Graph

> **v2.0 → v3.0 Evolution:**  
> Shell Wrappers → Temporal Activities  
> Direct LLM Output → Knowledge Graph Ingestion  
> Static Tools → Dynamic Web Research  

---

## 🎯 DOCUMENT PURPOSE

**Version:** 3.0  
**Scope:** Complete tool integration architecture

This guide explains:
- How tools integrate with Temporal workflows
- MCP server architecture
- Knowledge Graph data ingestion
- Live RAG research tools
- Tool schema definitions for LLMs

**Audience:** Developers implementing RedClaw v3.0

---

## 🏗️ v3.0 TOOL ARCHITECTURE

```
┌────────────────────────────────────────────────────────────┐
│                    LLM (Brain/Hands)                       │
│              Calls tools via schemas                       │
└──────────────────────┬─────────────────────────────────────┘
                       │
                       ▼
┌────────────────────────────────────────────────────────────┐
│              TEMPORAL ACTIVITY LAYER                       │
│                                                            │
│  @activity.defn run_nmap_activity(target)                 │
│  @activity.defn run_nuclei_activity(target)               │
│  @activity.defn run_sqlmap_activity(url)                  │
│                                                            │
│  Benefits:                                                 │
│  - Async execution (parallel)                              │
│  - Auto-retry on failure                                   │
│  - State persistence (crash recovery)                      │
│  - Timeout protection                                      │
└──────────────────────┬─────────────────────────────────────┘
                       │
                       ▼
┌────────────────────────────────────────────────────────────┐
│                MCP SERVER LAYER                            │
│                                                            │
│  MCP Servers (Tool Providers):                             │
│  ├─ nmap_mcp: Port scanning                               │
│  ├─ nuclei_mcp: Vulnerability scanning                    │
│  ├─ sqlmap_mcp: SQL injection testing                     │
│  ├─ metasploit_mcp: Exploitation                          │
│  └─ custom_tools_mcp: Research, privesc, etc.             │
│                                                            │
│  Each MCP server:                                          │
│  - Executes tool                                           │
│  - Parses output                                           │
│  - Returns structured JSON                                 │
└──────────────────────┬─────────────────────────────────────┘
                       │
                       ▼
┌────────────────────────────────────────────────────────────┐
│            KNOWLEDGE GRAPH INGESTION                       │
│                                                            │
│  Raw tool output → Parser → Graph nodes/edges              │
│                                                            │
│  Example:                                                  │
│  Nmap XML → {host, port, service} → Graph                 │
│  LLM queries graph, not raw 50K lines!                    │
└────────────────────────────────────────────────────────────┘
```

---

## 🔧 CORE TOOLS INTEGRATION

### 1. NMAP (Port Scanner)

**Temporal Activity:**

```python
from temporalio import activity
import subprocess
import xml.etree.ElementTree as ET

@activity.defn
async def run_nmap_activity(
    target: str,
    ports: str = "1-65535",
    scan_type: str = "SYN"
) -> dict:
    """
    Run nmap scan as Temporal activity
    
    Args:
        target: IP or hostname
        ports: Port range (default: all)
        scan_type: SYN, TCP, UDP
    
    Returns:
        Structured scan results
    """
    
    # Build nmap command
    cmd = [
        "nmap",
        "-sV",  # Version detection
        "-sC",  # Default scripts
        "-p", ports,
        target,
        "-oX", "/tmp/nmap_scan.xml"  # XML output
    ]
    
    # Execute (with timeout)
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, stderr = await asyncio.wait_for(
        process.communicate(),
        timeout=1800  # 30 min max
    )
    
    # Parse XML
    tree = ET.parse("/tmp/nmap_scan.xml")
    root = tree.getroot()
    
    # Extract data
    results = {
        "target": target,
        "open_ports": [],
        "services": []
    }
    
    for host in root.findall("host"):
        for port in host.findall(".//port"):
            if port.find("state").get("state") == "open":
                port_num = int(port.get("portid"))
                results["open_ports"].append(port_num)
                
                service = port.find("service")
                if service is not None:
                    results["services"].append({
                        "port": port_num,
                        "name": service.get("name"),
                        "version": service.get("version", "unknown")
                    })
    
    # Ingest to Knowledge Graph
    await ingest_nmap_results(results)
    
    # Return summary (NOT full output!)
    return {
        "summary": f"Found {len(results['open_ports'])} open ports",
        "open_ports": results["open_ports"][:10],  # First 10 only
        "services": results["services"][:10]
    }
```

---

**MCP Server (nmap_mcp):**

```python
# src/tools/mcp_servers/nmap_server.py

from mcp.server import Server
from mcp.types import Tool, TextContent

server = Server("nmap-mcp")

@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="run_nmap",
            description="Execute nmap port scan",
            inputSchema={
                "type": "object",
                "properties": {
                    "target": {"type": "string"},
                    "ports": {"type": "string", "default": "1-65535"}
                },
                "required": ["target"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "run_nmap":
        result = await run_nmap_activity(
            target=arguments["target"],
            ports=arguments.get("ports", "1-65535")
        )
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
```

---

**Knowledge Graph Ingestion:**

```python
async def ingest_nmap_results(results: dict):
    """Ingest nmap results into Knowledge Graph"""
    
    graph = get_knowledge_graph()
    
    # Add host
    graph.add_host(results["target"])
    
    # Add ports
    for port in results["open_ports"]:
        graph.add_port(
            ip=results["target"],
            port=port,
            state="open"
        )
    
    # Add services
    for svc in results["services"]:
        graph.add_service(
            ip=results["target"],
            port=svc["port"],
            name=svc["name"],
            version=svc["version"]
        )
    
    logger.info(f"Ingested {len(results['services'])} services to graph")
```

---

**Tool Schema for LLM:**

```python
NMAP_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_nmap",
        "description": "Execute nmap port scan. Use for initial reconnaissance.",
        "parameters": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "IP address or hostname"
                },
                "ports": {
                    "type": "string",
                    "description": "Port range (e.g., '1-1000', '80,443,8080')",
                    "default": "1-65535"
                },
                "scan_type": {
                    "type": "string",
                    "enum": ["SYN", "TCP", "UDP"],
                    "default": "SYN"
                }
            },
            "required": ["target"]
        }
    }
}
```

---

### 2. NUCLEI (Vulnerability Scanner)

**Temporal Activity:**

```python
@activity.defn
async def run_nuclei_activity(target: str) -> dict:
    """
    Run Nuclei vulnerability scanner
    
    Returns:
        Found vulnerabilities
    """
    
    cmd = [
        "nuclei",
        "-u", target,
        "-json",  # JSON output
        "-severity", "high,critical"  # Only high/critical
    ]
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE
    )
    
    stdout, _ = await asyncio.wait_for(
        process.communicate(),
        timeout=1200  # 20 min
    )
    
    # Parse JSON output
    vulns = []
    for line in stdout.decode().split('\n'):
        if line.strip():
            vuln = json.loads(line)
            vulns.append({
                "template": vuln["template-id"],
                "severity": vuln["info"]["severity"],
                "name": vuln["info"]["name"],
                "url": vuln["matched-at"]
            })
    
    # Ingest to graph
    await ingest_nuclei_results(target, vulns)
    
    return {
        "summary": f"Found {len(vulns)} vulnerabilities",
        "vulnerabilities": vulns
    }
```

---

### 3. SQLMAP (SQL Injection)

**Temporal Activity:**

```python
@activity.defn
async def run_sqlmap_activity(url: str, data: str = None) -> dict:
    """
    Run SQLMap for SQL injection testing
    
    Args:
        url: Target URL
        data: POST data (if applicable)
    
    Returns:
        SQL injection results
    """
    
    cmd = [
        "sqlmap",
        "-u", url,
        "--batch",  # Non-interactive
        "--risk=3",
        "--level=5",
        "--threads=10",
        "--output-dir=/tmp/sqlmap"
    ]
    
    if data:
        cmd.extend(["--data", data])
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE
    )
    
    stdout, _ = await asyncio.wait_for(
        process.communicate(),
        timeout=600  # 10 min
    )
    
    # Parse output
    output = stdout.decode()
    
    vulnerable = "Parameter:" in output and "is vulnerable" in output
    
    if vulnerable:
        # Extract database info
        db_info = extract_db_info(output)
        
        # Ingest to graph
        await ingest_sqli_vuln(url, db_info)
        
        return {
            "vulnerable": True,
            "database": db_info
        }
    
    return {"vulnerable": False}
```

---

### 4. METASPLOIT (Exploitation Framework)

**Temporal Activity:**

```python
@activity.defn
async def run_metasploit_exploit_activity(
    exploit: str,
    target: str,
    options: dict
) -> dict:
    """
    Run Metasploit exploit
    
    Args:
        exploit: Module name (e.g., 'exploit/multi/http/apache_rce')
        target: Target IP
        options: Exploit options (RHOST, RPORT, etc.)
    
    Returns:
        Exploitation results
    """
    
    # Build msf command
    msf_script = f"""
use {exploit}
set RHOST {target}
"""
    
    for key, value in options.items():
        msf_script += f"set {key} {value}\n"
    
    msf_script += "exploit\n"
    
    # Write to temp file
    with open("/tmp/msf_script.rc", "w") as f:
        f.write(msf_script)
    
    # Execute via msfconsole
    cmd = [
        "msfconsole",
        "-q",  # Quiet
        "-r", "/tmp/msf_script.rc"
    ]
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE
    )
    
    stdout, _ = await asyncio.wait_for(
        process.communicate(),
        timeout=300  # 5 min
    )
    
    output = stdout.decode()
    
    # Check for session
    session_obtained = "session opened" in output.lower()
    
    if session_obtained:
        # Extract session info
        session_id = extract_session_id(output)
        
        return {
            "success": True,
            "session_id": session_id,
            "shell_type": "meterpreter"
        }
    
    return {"success": False}
```

---

## 🌐 NEW v3.0 TOOLS: LIVE RAG

### 5. WEB SEARCH (SearxNG)

**Temporal Activity:**

```python
@activity.defn
async def search_web_activity(query: str) -> list:
    """
    Search web for exploits, PoCs, documentation
    
    Args:
        query: Search query
    
    Returns:
        List of search results
    """
    
    # SearxNG API (self-hosted or public instance)
    searxng_url = "https://searx.example.com/search"
    
    params = {
        "q": query,
        "format": "json",
        "engines": "google,github,duckduckgo"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(searxng_url, params=params) as resp:
            data = await resp.json()
    
    results = []
    for item in data["results"][:5]:  # Top 5
        results.append({
            "title": item["title"],
            "url": item["url"],
            "snippet": item["content"]
        })
    
    return results
```

---

**Tool Schema:**

```python
SEARCH_WEB_TOOL = {
    "type": "function",
    "function": {
        "name": "search_web",
        "description": "Search internet for exploits, PoCs, CVE information",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (e.g., 'CVE-2021-41773 Apache RCE exploit')"
                }
            },
            "required": ["query"]
        }
    }
}
```

---

### 6. WEBPAGE READER (Jina)

**Temporal Activity:**

```python
@activity.defn
async def read_webpage_activity(url: str) -> str:
    """
    Read webpage and return clean markdown
    
    Uses Jina Reader API to remove HTML fluff
    
    Args:
        url: URL to read
    
    Returns:
        Clean markdown content
    """
    
    # Jina Reader API
    jina_url = f"https://r.jina.ai/{url}"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(jina_url) as resp:
            markdown = await resp.text()
    
    return markdown
```

---

### 7. POC DOWNLOADER (GitHub)

**Temporal Activity:**

```python
@activity.defn
async def download_poc_activity(github_url: str) -> dict:
    """
    Download exploit PoC from GitHub
    
    Args:
        github_url: GitHub file URL
    
    Returns:
        Downloaded code
    """
    
    # Convert to raw URL
    if "github.com" in github_url:
        raw_url = github_url.replace(
            "github.com", "raw.githubusercontent.com"
        ).replace("/blob/", "/")
    else:
        raw_url = github_url
    
    async with aiohttp.ClientSession() as session:
        async with session.get(raw_url) as resp:
            code = await resp.text()
    
    # Detect language
    language = detect_language_from_url(github_url)
    
    return {
        "url": github_url,
        "code": code,
        "language": language
    }
```

---

### 8. EXPLOIT COMPILER & TESTER

**Temporal Activity:**

```python
@activity.defn
async def compile_and_test_exploit_activity(
    code: str,
    language: str,
    target_arch: str = "x64"
) -> dict:
    """
    Compile and test exploit in sandbox
    
    Args:
        code: Source code
        language: python, c, rust, etc.
        target_arch: x86, x64, arm
    
    Returns:
        Compilation result + test result
    """
    
    # Create sandbox (Docker container)
    sandbox = await create_sandbox(arch=target_arch)
    
    # Copy code to sandbox
    await sandbox.write_file("/tmp/exploit", code)
    
    # Compile based on language
    if language == "c":
        compile_cmd = f"gcc -o /tmp/exploit.bin /tmp/exploit.c"
    elif language == "python":
        compile_cmd = None  # No compilation needed
    elif language == "rust":
        compile_cmd = "rustc /tmp/exploit.rs -o /tmp/exploit.bin"
    
    if compile_cmd:
        compile_result = await sandbox.exec(compile_cmd)
        
        if compile_result.returncode != 0:
            return {
                "success": False,
                "error": "Compilation failed",
                "details": compile_result.stderr
            }
    
    # Test in sandbox (safe target)
    test_result = await sandbox.exec("/tmp/exploit.bin 127.0.0.1")
    
    return {
        "success": test_result.returncode == 0,
        "compiled": True,
        "binary_path": "/tmp/exploit.bin" if compile_cmd else None
    }
```

---

## 🕸️ KNOWLEDGE GRAPH TOOLS

### 9. QUERY KNOWLEDGE GRAPH

**Tool Schema:**

```python
QUERY_GRAPH_TOOL = {
    "type": "function",
    "function": {
        "name": "query_knowledge_graph",
        "description": "Query the pentest knowledge graph for relationships and data",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query (e.g., 'What vulnerabilities exist on 10.10.10.5?')"
                }
            },
            "required": ["query"]
        }
    }
}
```

---

**Implementation:**

```python
@tool
async def query_knowledge_graph(query: str) -> dict:
    """
    Query the pentest knowledge graph
    
    Examples:
    - "What services run on 10.10.10.5?"
    - "Show all CVEs for Apache services"
    - "Find path to domain admin"
    """
    
    graph = get_knowledge_graph()
    
    # Parse natural language query → graph traversal
    results = await graph.query_natural_language(query)
    
    return {
        "query": query,
        "results": results,
        "node_count": len(results.get("nodes", [])),
        "edge_count": len(results.get("edges", []))
    }
```

---

## 🌳 MCTS TOOLS

### 10. CREATE ATTACK BRANCH

**Tool Schema:**

```python
CREATE_BRANCH_TOOL = {
    "type": "function",
    "function": {
        "name": "create_attack_branch",
        "description": "Create new attack branch (saves checkpoint). Call BEFORE attempting risky exploit.",
        "parameters": {
            "type": "object",
            "properties": {
                "branch_name": {
                    "type": "string",
                    "description": "Descriptive name (e.g., 'SMB Relay Attack')"
                },
                "rationale": {
                    "type": "string",
                    "description": "Why trying this approach"
                }
            },
            "required": ["branch_name"]
        }
    }
}
```

---

### 11. ABANDON BRANCH (Rollback)

**Tool Schema:**

```python
ABANDON_BRANCH_TOOL = {
    "type": "function",
    "function": {
        "name": "abandon_branch",
        "description": "This attack path failed, rollback to checkpoint (clean context). Call AFTER exploit fails.",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Why this branch failed"
                }
            },
            "required": ["reason"]
        }
    }
}
```

---

## 📋 COMPLETE TOOL MANIFEST

### tools_manifest_v3.yaml

```yaml
version: "3.0"

tools:
  # Reconnaissance
  - name: run_nmap
    category: recon
    activity: run_nmap_activity
    mcp_server: nmap_mcp
    timeout: 1800
    retries: 3
  
  - name: run_nuclei
    category: recon
    activity: run_nuclei_activity
    mcp_server: nuclei_mcp
    timeout: 1200
    retries: 2
  
  - name: run_dirb
    category: recon
    activity: run_dirb_activity
    mcp_server: web_mcp
    timeout: 900
    retries: 2
  
  # Web Testing
  - name: run_sqlmap
    category: web
    activity: run_sqlmap_activity
    mcp_server: web_mcp
    timeout: 600
    retries: 1
  
  - name: run_nikto
    category: web
    activity: run_nikto_activity
    mcp_server: web_mcp
    timeout: 600
  
  # Exploitation
  - name: run_metasploit_exploit
    category: exploit
    activity: run_metasploit_exploit_activity
    mcp_server: metasploit_mcp
    timeout: 300
    requires_approval: true
  
  # Live RAG (NEW in v3.0)
  - name: search_web
    category: research
    activity: search_web_activity
    timeout: 30
  
  - name: read_webpage
    category: research
    activity: read_webpage_activity
    timeout: 30
  
  - name: download_poc
    category: research
    activity: download_poc_activity
    timeout: 60
  
  - name: compile_and_test_exploit
    category: research
    activity: compile_and_test_exploit_activity
    timeout: 300
  
  # Knowledge Graph (NEW in v3.0)
  - name: query_knowledge_graph
    category: memory
    activity: query_knowledge_graph_activity
    timeout: 5
  
  # MCTS (NEW in v3.0)
  - name: create_attack_branch
    category: decision
    activity: create_attack_branch_activity
    timeout: 1
  
  - name: abandon_branch
    category: decision
    activity: abandon_branch_activity
    timeout: 1
```

---

## 🚀 USAGE EXAMPLE

### Complete Workflow with All Tools

```python
# User command
await redclaw.pentest("10.10.10.5")

# Step 1: Parallel recon (Temporal)
recon_results = await asyncio.gather(
    workflow.execute_activity(run_nmap_activity, "10.10.10.5"),
    workflow.execute_activity(run_nuclei_activity, "10.10.10.5"),
    workflow.execute_activity(run_dirb_activity, "http://10.10.10.5")
)

# Step 2: Ingest to Knowledge Graph
for result in recon_results:
    await ingest_to_graph(result)

# Step 3: Brain queries graph
brain_prompt = "Analyze 10.10.10.5"
brain_response = await brain.chat(
    messages=[{"role": "user", "content": brain_prompt}],
    tools=[QUERY_GRAPH_TOOL, SEARCH_WEB_TOOL, CREATE_BRANCH_TOOL]
)

# Brain calls: query_knowledge_graph
graph_data = await query_knowledge_graph("Show vulnerabilities on 10.10.10.5")

# Step 4: Brain decides to exploit Apache
brain_response = await brain.chat(
    messages=[{"role": "user", "content": f"Found: {graph_data}"}],
    tools=[CREATE_BRANCH_TOOL, SEARCH_WEB_TOOL]
)

# Brain calls: create_attack_branch
await create_attack_branch("Apache CVE-2021-41773 RCE")

# Brain calls: search_web
search_results = await search_web("CVE-2021-41773 Apache RCE exploit GitHub")

# Step 5: Hands downloads PoC
poc = await download_poc(search_results[0]["url"])

# Step 6: Hands compiles & tests
compiled = await compile_and_test_exploit(poc["code"], "python", "x64")

# Step 7: Execute (with approval)
if compiled["success"]:
    approval = await request_approval("Execute Apache RCE")
    
    if approval:
        result = await execute_exploit(compiled["binary_path"])
        
        if result["shell"]:
            print("Shell obtained!")
        else:
            # Failed - rollback
            await abandon_branch("Exploit failed to get shell")
```

---

## 🎯 SUCCESS CRITERIA

**v3.0 tool integration works if:**

✅ All tools execute as Temporal activities  
✅ MCP servers provide structured output  
✅ Knowledge Graph ingests data correctly  
✅ Live RAG tools find exploits on internet  
✅ MCTS tools manage context cleanly  
✅ Parallel execution works (3+ tools simultaneously)  
✅ Error handling prevents crashes  
✅ Timeout protection prevents hangs

---

**VERSION:** 3.0  
**STATUS:** ✅ COMPLETE  
**TOOLS:** 11 core + unlimited via MCP  
**NEXT:** Implement MCP servers + Graph ingestion
