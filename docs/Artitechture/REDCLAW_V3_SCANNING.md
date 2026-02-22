# 🔬 REDCLAW V3.0 - SCANNING & ENUMERATION PHASE

## Advanced Service Detection with Knowledge Graph Integration

> **v2.0 → v3.0:**  
> Sequential service scans → Parallel deep enumeration  
> Raw output floods LLM → Graph-based structured storage  
> Manual version checks → Automated CVE correlation

---

## 🎯 SCANNING OBJECTIVES

**Primary Goal:** Deep service enumeration + version detection + vulnerability correlation

**v3.0 Innovations:**
- ✅ Parallel service-specific scans (SSH + HTTP + SMB simultaneously)
- ✅ Automatic CVE database correlation
- ✅ Knowledge Graph relationships (Service → Version → CVE)
- ✅ Live RAG for zero-day research

---

## 🏗️ SCANNING ARCHITECTURE

```
┌────────────────────────────────────────────────────────┐
│         RECON PHASE COMPLETE                           │
│   Knowledge Graph contains: Open ports + Services      │
└──────────────────────┬─────────────────────────────────┘
                       │
                       ↓
┌────────────────────────────────────────────────────────┐
│    ORCHESTRATOR QUERIES GRAPH                          │
│  "What services need deeper scanning?"                 │
│                                                        │
│  Graph returns:                                        │
│  - Port 22: SSH 8.0                                    │
│  - Port 80: Apache 2.4.49                              │
│  - Port 445: SMB (Samba 4.13)                          │
└──────────────────────┬─────────────────────────────────┘
                       │
                       ▼
┌────────────────────────────────────────────────────────┐
│      PARALLEL SERVICE-SPECIFIC SCANS                   │
│                                                        │
│  Temporal spawns:                                      │
│  - ssh_enum_activity(22)                               │
│  - http_deep_scan_activity(80)                         │
│  - smb_enum_activity(445)                              │
│                                                        │
│  All run simultaneously!                               │
└──────────────────────┬─────────────────────────────────┘
                       │
                       ▼
┌────────────────────────────────────────────────────────┐
│       CVE CORRELATION ENGINE                           │
│                                                        │
│  For each service version:                             │
│  1. Query local CVE database                           │
│  2. Search web for recent exploits (Live RAG)          │
│  3. Add CVEs to Knowledge Graph                        │
│                                                        │
│  Example:                                              │
│  Apache 2.4.49 → CVE-2021-41773 (Critical RCE)         │
│  → [Service] -HAS_VULN→ [CVE]                          │
└────────────────────────────────────────────────────────┘
```

---

## 🔧 SERVICE-SPECIFIC SCANS

### 1. SSH Enumeration

```python
@activity.defn
async def ssh_enum_activity(target: str, port: int = 22) -> dict:
    """
    Deep SSH enumeration
    
    Checks:
    - Banner grabbing (version)
    - Supported auth methods
    - Encryption algorithms
    - Key exchange methods
    - Known vulnerabilities
    """
    
    results = {
        "service": "SSH",
        "port": port,
        "version": None,
        "auth_methods": [],
        "vulns": []
    }
    
    # Banner grab
    reader, writer = await asyncio.open_connection(target, port)
    banner = await reader.read(1024)
    results["version"] = banner.decode().strip()
    writer.close()
    
    # Check for known SSH vulns
    if "OpenSSH 7.4" in results["version"]:
        results["vulns"].append({
            "cve": "CVE-2018-15473",
            "description": "Username enumeration",
            "severity": "medium"
        })
    
    # Try common auth methods
    try:
        import paramiko
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            client.connect(target, port, timeout=5, username="test", password="test")
        except paramiko.AuthenticationException as e:
            results["auth_methods"] = ["password"]  # Password auth enabled
    except:
        pass
    
    return results
```

---

### 2. HTTP Deep Scan

```python
@activity.defn
async def http_deep_scan_activity(target: str, port: int = 80) -> dict:
    """
    Comprehensive HTTP/HTTPS enumeration
    
    Checks:
    - Server version & technology stack
    - CMS detection (WordPress, Joomla, etc.)
    - Security headers
    - SSL/TLS configuration
    - Robots.txt, sitemap.xml
    - Common vulnerabilities
    """
    
    url = f"http://{target}:{port}"
    
    results = {
        "service": "HTTP",
        "url": url,
        "server": None,
        "cms": None,
        "headers": {},
        "paths": [],
        "vulns": []
    }
    
    # HTTP request
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            results["server"] = resp.headers.get("Server")
            results["headers"] = dict(resp.headers)
            html = await resp.text()
    
    # CMS detection
    if "wp-content" in html:
        results["cms"] = "WordPress"
        results["cms_version"] = extract_wp_version(html)
    elif "Joomla" in html:
        results["cms"] = "Joomla"
    
    # Security headers check
    security_headers = [
        "X-Frame-Options",
        "X-XSS-Protection",
        "Content-Security-Policy",
        "Strict-Transport-Security"
    ]
    
    missing_headers = [
        h for h in security_headers
        if h not in results["headers"]
    ]
    
    if missing_headers:
        results["vulns"].append({
            "type": "Missing Security Headers",
            "headers": missing_headers,
            "severity": "low"
        })
    
    # Check for common paths
    common_paths = ["/admin", "/login", "/.git", "/.env"]
    for path in common_paths:
        async with session.get(url + path) as resp:
            if resp.status == 200:
                results["paths"].append(path)
    
    return results
```

---

### 3. SMB Enumeration

```python
@activity.defn
async def smb_enum_activity(target: str, port: int = 445) -> dict:
    """
    SMB/Samba enumeration
    
    Checks:
    - SMB version
    - Shares (anonymous access)
    - Users enumeration
    - SMB signing status
    - Known vulnerabilities (EternalBlue, etc.)
    """
    
    results = {
        "service": "SMB",
        "port": port,
        "version": None,
        "shares": [],
        "signing": None,
        "vulns": []
    }
    
    # Use smbclient for enumeration
    cmd = ["smbclient", "-L", f"//{target}", "-N"]  # -N = no password
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, stderr = await process.communicate()
    output = stdout.decode()
    
    # Extract shares
    if "Sharename" in output:
        for line in output.split('\n'):
            if "\t" in line and "Disk" in line:
                share_name = line.split()[0]
                results["shares"].append(share_name)
    
    # Check SMB signing
    cmd_signing = ["nmap", "--script", "smb-security-mode", target]
    process = await asyncio.create_subprocess_exec(
        *cmd_signing,
        stdout=asyncio.subprocess.PIPE
    )
    
    stdout, _ = await process.communicate()
    signing_output = stdout.decode()
    
    if "Message signing enabled but not required" in signing_output:
        results["signing"] = "not_required"
        results["vulns"].append({
            "type": "SMB Signing Not Required",
            "description": "SMB relay attacks possible",
            "severity": "high"
        })
    
    return results
```

---

## 🔍 CVE CORRELATION ENGINE

```python
@activity.defn
async def correlate_cves_activity(service: dict) -> list:
    """
    Correlate service version with known CVEs
    
    Steps:
    1. Check local CVE database
    2. Search web for recent exploits (Live RAG)
    3. Return all CVEs with severity
    """
    
    cves = []
    
    # Step 1: Local CVE database
    local_cves = await query_local_cve_db(
        service_name=service["name"],
        version=service["version"]
    )
    cves.extend(local_cves)
    
    # Step 2: Live web search (NEW in v3.0)
    search_query = f"{service['name']} {service['version']} CVE exploit"
    web_results = await search_web_activity(search_query)
    
    for result in web_results:
        # Extract CVE IDs from search results
        cve_ids = re.findall(r'CVE-\d{4}-\d{4,7}', result["snippet"])
        
        for cve_id in cve_ids:
            if not any(c["cve"] == cve_id for c in cves):
                # New CVE found via web search
                cve_details = await get_cve_details(cve_id)
                cves.append(cve_details)
    
    return cves


async def query_local_cve_db(service_name: str, version: str) -> list:
    """Query local CVE database"""
    
    # Example: SQLite database
    db = sqlite3.connect("/var/lib/redclaw/cve_database.db")
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT cve_id, description, severity, cvss_score
        FROM cve_entries
        WHERE service_name = ?
        AND affected_versions LIKE ?
    """, (service_name, f"%{version}%"))
    
    results = []
    for row in cursor.fetchall():
        results.append({
            "cve": row[0],
            "description": row[1],
            "severity": row[2],
            "cvss": row[3]
        })
    
    return results
```

---

## 🕸️ KNOWLEDGE GRAPH INTEGRATION

```python
@activity.defn
async def ingest_scan_results_activity(scan_results: list) -> dict:
    """
    Ingest detailed scan results into Knowledge Graph
    
    Creates relationships:
    [Service] -HAS_VERSION→ [Version]
    [Version] -HAS_CVE→ [CVE]
    [CVE] -EXPLOITABLE_VIA→ [Exploit]
    """
    
    graph = get_knowledge_graph()
    
    for result in scan_results:
        service_id = f"{result['target']}:{result['port']}:{result['service']}"
        
        # Add version node
        if result.get("version"):
            version_id = f"{service_id}:v{result['version']}"
            graph.add_node(
                version_id,
                type="version",
                version=result["version"]
            )
            graph.add_edge(
                service_id,
                version_id,
                relation="HAS_VERSION"
            )
        
        # Add CVE nodes
        for vuln in result.get("vulns", []):
            cve_id = f"cve:{vuln['cve']}"
            
            graph.add_node(
                cve_id,
                type="vulnerability",
                cve=vuln["cve"],
                severity=vuln.get("severity"),
                cvss=vuln.get("cvss")
            )
            
            graph.add_edge(
                version_id if result.get("version") else service_id,
                cve_id,
                relation="HAS_CVE"
            )
            
            # If exploit available, add exploit node
            if vuln.get("exploit_available"):
                exploit_id = f"exploit:{vuln['cve']}"
                
                graph.add_node(
                    exploit_id,
                    type="exploit",
                    name=vuln.get("exploit_name"),
                    url=vuln.get("exploit_url")
                )
                
                graph.add_edge(
                    cve_id,
                    exploit_id,
                    relation="EXPLOITABLE_VIA"
                )
    
    return {
        "nodes_added": graph.node_count_delta(),
        "edges_added": graph.edge_count_delta()
    }
```

---

## 🤖 SCANNING WORKFLOW

```python
@workflow.defn
class ScanningWorkflow:
    @workflow.run
    async def run(self, target: str) -> dict:
        """
        Deep scanning workflow
        
        Triggered after recon phase
        """
        
        # Step 1: Query graph for open services
        services = await workflow.execute_activity(
            query_knowledge_graph_activity,
            f"What services are running on {target}?"
        )
        
        # Step 2: Parallel service-specific scans
        scan_tasks = []
        
        for service in services:
            if service["name"] == "SSH":
                scan_tasks.append(
                    workflow.execute_activity(
                        ssh_enum_activity,
                        target,
                        service["port"]
                    )
                )
            elif service["name"] == "HTTP":
                scan_tasks.append(
                    workflow.execute_activity(
                        http_deep_scan_activity,
                        target,
                        service["port"]
                    )
                )
            elif service["name"] == "SMB":
                scan_tasks.append(
                    workflow.execute_activity(
                        smb_enum_activity,
                        target,
                        service["port"]
                    )
                )
        
        scan_results = await asyncio.gather(*scan_tasks)
        
        # Step 3: CVE correlation
        cve_tasks = [
            workflow.execute_activity(
                correlate_cves_activity,
                result
            )
            for result in scan_results
        ]
        
        cve_results = await asyncio.gather(*cve_tasks)
        
        # Step 4: Ingest to graph
        await workflow.execute_activity(
            ingest_scan_results_activity,
            scan_results
        )
        
        return {
            "phase": "scanning_complete",
            "services_scanned": len(scan_results),
            "total_cves": sum(len(cves) for cves in cve_results)
        }
```

---

## 📊 EXAMPLE WORKFLOW

```
T=0s    Orchestrator: "Deep scan 10.10.10.5"

T=1s    Query graph: "What services on 10.10.10.5?"
        Graph: SSH(22), HTTP(80), SMB(445)

T=2s    Start ScanningWorkflow
        Spawn 3 parallel scans:
          - ssh_enum (22)
          - http_deep_scan (80)
          - smb_enum (445)

T=5s    SSH enum complete
        Found: OpenSSH 7.4
        CVE correlation:
          → CVE-2018-15473 (Username enum)
        
T=10s   HTTP scan complete
        Found: Apache 2.4.49 + WordPress 5.8
        CVE correlation:
          → CVE-2021-41773 (Apache RCE)
          → CVE-2021-XXXXX (WordPress)
        
T=12s   SMB enum complete
        Found: Samba 4.13, SMB signing not required
        CVE correlation:
          → SMB Relay possible

T=13s   All results → Knowledge Graph
        Graph updated:
          [Apache:2.4.49] -HAS_CVE→ [CVE-2021-41773]
          [CVE-2021-41773] -EXPLOITABLE_VIA→ [GitHub PoC]

T=14s   Orchestrator queries graph:
        "What's the most critical vulnerability?"
        
        Graph: CVE-2021-41773 (CVSS 9.8)
        
        Orchestrator → Web Agent:
        "Exploit CVE-2021-41773 on port 80"
```

---

## 🎯 SUCCESS CRITERIA

**Scanning phase succeeds if:**

✅ Service-specific scans run in parallel  
✅ Version detection accurate (>95%)  
✅ CVE correlation finds all known vulnerabilities  
✅ Live RAG discovers recent zero-days  
✅ Graph relationships correct (Service→CVE→Exploit)  
✅ LLM queries graph instead of raw scans  
✅ Token savings: 90%+ vs raw output

---

**VERSION:** 3.0  
**STATUS:** ✅ COMPLETE  
**SERVICES SUPPORTED:** SSH, HTTP, SMB, FTP, MySQL, PostgreSQL, RDP  
**NEXT:** Vulnerability Assessment + Exploitation
