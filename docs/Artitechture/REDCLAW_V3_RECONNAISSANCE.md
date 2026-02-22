# 🔍 REDCLAW V3.0 - RECONNAISSANCE PHASE

## Parallel Recon with Temporal + Knowledge Graph Integration

> **v2.0 → v3.0:**  
> Sequential scans → Parallel Temporal workflows  
> Raw output to LLM → Knowledge Graph ingestion  
> Static tools → Live OSINT research

---

## 🎯 RECONNAISSANCE OBJECTIVES

**Primary Goal:** Gather maximum information about target(s) with minimum noise

**v3.0 Innovations:**
- ✅ Parallel execution (nmap + nuclei + dirb simultaneously)
- ✅ Knowledge Graph storage (query on-demand, not dump to LLM)
- ✅ Live OSINT (search internet for subdomains, leaks, etc.)
- ✅ Specialized Recon Agent (focused prompt)

---

## 🏗️ RECON ARCHITECTURE

```
┌────────────────────────────────────────────────────────┐
│            ORCHESTRATOR AGENT                          │
│     "Need reconnaissance on 10.10.10.5"                │
└──────────────────────┬─────────────────────────────────┘
                       │
                       ↓
┌────────────────────────────────────────────────────────┐
│         HANDOFF TO RECON AGENT                         │
│  (Specialized agent with recon-only tools)             │
└──────────────────────┬─────────────────────────────────┘
                       │
                       ▼
┌────────────────────────────────────────────────────────┐
│      TEMPORAL RECON WORKFLOW                           │
│                                                        │
│  @workflow.defn ReconWorkflow:                         │
│    # PARALLEL execution                                │
│    results = await asyncio.gather(                     │
│      run_nmap(target),      # 30 min                   │
│      run_nuclei(target),    # 20 min                   │
│      run_dirb(target),      # 15 min                   │
│      osint_search(target)   # 5 min                    │
│    )                                                   │
└──────────────────────┬─────────────────────────────────┘
                       │
                       ▼
┌────────────────────────────────────────────────────────┐
│        KNOWLEDGE GRAPH INGESTION                       │
│                                                        │
│  Nmap results → Graph                                  │
│  [Host] → [Port] → [Service] → [Version]              │
│                                                        │
│  Nuclei results → Graph                                │
│  [Service] → [Vuln:CVE]                                │
│                                                        │
│  OSINT results → Graph                                 │
│  [Domain] → [Subdomain] → [IP]                         │
└────────────────────────────────────────────────────────┘
```

---

## 🔧 PARALLEL RECON WORKFLOW

```python
from temporalio import workflow, activity
from datetime import timedelta
import asyncio

@workflow.defn
class ReconWorkflow:
    @workflow.run
    async def run(self, target: str) -> dict:
        """
        Parallel reconnaissance workflow
        
        All tools run simultaneously!
        """
        
        # Phase 1: Parallel active recon
        active_recon = [
            workflow.execute_activity(
                run_nmap_activity,
                target,
                start_to_close_timeout=timedelta(minutes=30)
            ),
            workflow.execute_activity(
                run_nuclei_activity,
                target,
                start_to_close_timeout=timedelta(minutes=20)
            ),
            workflow.execute_activity(
                run_dirb_activity,
                f"http://{target}",
                start_to_close_timeout=timedelta(minutes=15)
            )
        ]
        
        # Phase 2: Parallel passive recon (OSINT)
        passive_recon = [
            workflow.execute_activity(
                osint_subdomain_enum_activity,
                target,
                start_to_close_timeout=timedelta(minutes=10)
            ),
            workflow.execute_activity(
                shodan_search_activity,
                target,
                start_to_close_timeout=timedelta(minutes=5)
            )
        ]
        
        # Execute ALL in parallel
        all_results = await asyncio.gather(
            asyncio.gather(*active_recon),
            asyncio.gather(*passive_recon)
        )
        
        active_results, passive_results = all_results
        
        # Ingest to Knowledge Graph
        await workflow.execute_activity(
            ingest_recon_to_graph_activity,
            {
                "active": active_results,
                "passive": passive_results
            }
        )
        
        # Return summary (NOT full data!)
        return {
            "phase": "reconnaissance_complete",
            "summary": {
                "ports_found": len(active_results[0]["open_ports"]),
                "vulns_found": len(active_results[1]["vulnerabilities"]),
                "subdomains_found": len(passive_results[0]["subdomains"])
            }
        }
```

---

## 🛠️ RECON TOOLS

### 1. Nmap (Port Scanning)

```python
@activity.defn
async def run_nmap_activity(target: str) -> dict:
    """Full port scan with service detection"""
    
    cmd = [
        "nmap",
        "-sV",  # Service version
        "-sC",  # Default scripts
        "-p-",  # All ports
        "--min-rate=1000",  # Fast
        target,
        "-oX", "/tmp/nmap.xml"
    ]
    
    # Execute
    result = await asyncio.create_subprocess_exec(*cmd)
    await result.wait()
    
    # Parse XML → structured data
    parsed = parse_nmap_xml("/tmp/nmap.xml")
    
    return parsed
```

---

### 2. Nuclei (Vulnerability Scanning)

```python
@activity.defn
async def run_nuclei_activity(target: str) -> dict:
    """Automated vulnerability scanning"""
    
    cmd = [
        "nuclei",
        "-u", target,
        "-json",
        "-severity", "high,critical"
    ]
    
    result = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE
    )
    
    stdout, _ = await result.communicate()
    
    # Parse JSON lines
    vulns = []
    for line in stdout.decode().split('\n'):
        if line.strip():
            vulns.append(json.loads(line))
    
    return {"vulnerabilities": vulns}
```

---

### 3. Dirb (Web Directory Enumeration)

```python
@activity.defn
async def run_dirb_activity(url: str) -> dict:
    """Web directory brute-force"""
    
    cmd = [
        "dirb",
        url,
        "/usr/share/wordlists/dirb/common.txt",
        "-o", "/tmp/dirb.txt"
    ]
    
    result = await asyncio.create_subprocess_exec(*cmd)
    await result.wait()
    
    # Parse output
    with open("/tmp/dirb.txt") as f:
        content = f.read()
    
    # Extract found paths
    paths = re.findall(r'\+ (http[^\s]+)', content)
    
    return {"paths": paths}
```

---

### 4. OSINT Subdomain Enumeration (NEW v3.0)

```python
@activity.defn
async def osint_subdomain_enum_activity(domain: str) -> dict:
    """
    Passive subdomain enumeration using multiple sources
    
    Uses:
    - crt.sh (certificate transparency)
    - VirusTotal
    - SecurityTrails
    - DNS brute-force
    """
    
    subdomains = set()
    
    # crt.sh
    crtsh_url = f"https://crt.sh/?q=%.{domain}&output=json"
    async with aiohttp.ClientSession() as session:
        async with session.get(crtsh_url) as resp:
            data = await resp.json()
            for entry in data:
                subdomains.add(entry["name_value"])
    
    # DNS brute-force (parallel)
    wordlist = load_subdomain_wordlist()
    dns_tasks = [
        resolve_subdomain(f"{word}.{domain}")
        for word in wordlist[:1000]  # Top 1000
    ]
    
    resolved = await asyncio.gather(*dns_tasks)
    subdomains.update([s for s in resolved if s])
    
    return {"subdomains": list(subdomains)}
```

---

### 5. Shodan Search (NEW v3.0)

```python
@activity.defn
async def shodan_search_activity(target: str) -> dict:
    """
    Search Shodan for target information
    
    Requires: SHODAN_API_KEY
    """
    
    import shodan
    
    api = shodan.Shodan(os.getenv("SHODAN_API_KEY"))
    
    try:
        results = api.host(target)
        
        return {
            "ip": results["ip_str"],
            "org": results.get("org", "Unknown"),
            "os": results.get("os", "Unknown"),
            "ports": results.get("ports", []),
            "vulns": results.get("vulns", [])
        }
    except shodan.APIError:
        return {"error": "Not found in Shodan"}
```

---

## 🕸️ KNOWLEDGE GRAPH INGESTION

```python
@activity.defn
async def ingest_recon_to_graph_activity(results: dict) -> dict:
    """
    Ingest all recon results into Knowledge Graph
    
    This is where the magic happens:
    - Raw tool output → Structured graph
    - LLM queries graph on-demand
    - Token savings: 50K lines → 500 tokens
    """
    
    graph = get_knowledge_graph()
    
    # Nmap results
    nmap_data = results["active"][0]
    graph.add_host(nmap_data["target"], os=nmap_data.get("os"))
    
    for port in nmap_data["open_ports"]:
        graph.add_port(nmap_data["target"], port, "open")
    
    for svc in nmap_data["services"]:
        graph.add_service(
            nmap_data["target"],
            svc["port"],
            svc["name"],
            svc["version"]
        )
    
    # Nuclei results
    nuclei_data = results["active"][1]
    for vuln in nuclei_data["vulnerabilities"]:
        graph.add_vulnerability(
            f"{nmap_data['target']}:{vuln.get('port', 80)}",
            vuln["template"],
            vuln["severity"]
        )
    
    # Dirb results
    dirb_data = results["active"][2]
    for path in dirb_data["paths"]:
        graph.add_web_path(nmap_data["target"], path)
    
    # OSINT results
    osint_data = results["passive"][0]
    for subdomain in osint_data["subdomains"]:
        graph.add_subdomain(nmap_data["target"], subdomain)
    
    return {
        "nodes_added": graph.node_count_delta(),
        "edges_added": graph.edge_count_delta()
    }
```

---

## 🤖 RECON AGENT

```python
RECON_AGENT_PROMPT = """
You are RedClaw Recon Agent.

Your ONLY job: Gather information about targets.

Available Tools:
- run_nmap(target): Port scan
- run_nuclei(target): Vulnerability scan
- run_dirb(url): Web directory enum
- osint_subdomain_enum(domain): Find subdomains
- shodan_search(ip): Passive intel
- query_knowledge_graph(query): Check what we know

You CANNOT:
- Exploit vulnerabilities
- Test web apps (SQLi, XSS)
- Do post-exploitation

Workflow:
1. Start parallel recon (all tools at once)
2. Wait for results
3. Query graph for summary
4. Report findings to Orchestrator
5. Recommend next phase

Remember: You coordinate recon, Temporal executes it.
"""
```

---

## 📊 RECON WORKFLOW EXAMPLE

```
T=0s    User: "Recon 10.10.10.5"

T=1s    Orchestrator → Recon Agent

T=2s    Recon Agent: Start ReconWorkflow
        Temporal spawns 5 parallel activities:
          - nmap (30 min)
          - nuclei (20 min)
          - dirb (15 min)
          - subdomain enum (10 min)
          - shodan (5 min)

T=5m    Shodan completes first
        Result → Graph
        Graph nodes: +1 Host, +5 Ports

T=10m   Subdomain enum completes
        Result → Graph
        Graph nodes: +12 Subdomains

T=15m   Dirb completes
        Result → Graph
        Graph nodes: +8 Web paths

T=20m   Nuclei completes
        Result → Graph
        Graph nodes: +3 Vulns

T=30m   Nmap completes
        Result → Graph
        Graph nodes: +15 Services

T=31m   Recon Agent queries graph:
        query_knowledge_graph("Summary for 10.10.10.5")
        
        Graph returns:
        {
          "host": "10.10.10.5",
          "open_ports": [22, 80, 443, 3306],
          "services": ["SSH 8.0", "Apache 2.4.49", "MySQL 8.0"],
          "vulnerabilities": [
            "CVE-2021-41773 (Apache)",
            "CVE-2021-XXXXX (MySQL)"
          ],
          "web_paths": ["/admin", "/upload", "/api"],
          "subdomains": ["www", "mail", "ftp", ...]
        }

T=32m   Recon Agent → Orchestrator:
        "Recon complete. Found 2 critical CVEs. 
         Recommend: Handoff to Web Agent for /admin path."

TOTAL: 32 minutes (vs 95 minutes sequential!)
SAVINGS: 66% time reduction
```

---

## 🎯 SUCCESS CRITERIA

**Recon phase succeeds if:**

✅ All tools execute in parallel  
✅ Results ingested to Knowledge Graph  
✅ LLM queries graph (not raw output)  
✅ OSINT finds additional subdomains  
✅ Shodan provides passive intel  
✅ Recon Agent reports findings correctly  
✅ Time savings: 50%+ vs sequential

---

**VERSION:** 3.0  
**STATUS:** ✅ COMPLETE  
**NEXT:** Web Agent + Exploitation phases
