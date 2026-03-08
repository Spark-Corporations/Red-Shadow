<p align="center">
  <h1 align="center">🩸 RedClaw v3.1 — Autonomous Penetration Testing Framework</h1>
  <p align="center">
    <em>Hypothesis-driven exploitation with Knowledge Graph state management,<br>
    MITRE ATT&CK post-exploitation, and event-driven phase orchestration.</em>
  </p>
</p>

---

## Table of Contents

- [Quick Start](#quick-start)
- [Developer Onboarding](#developer-onboarding)
- [Contributing — How to Extend](#contributing)
- [Architecture Overview](#architecture-overview)
- [Core Pipeline — 10 Phase Execution](#core-pipeline)
- [Knowledge Graph (KG)](#knowledge-graph)
- [Hypothesis Engine](#hypothesis-engine)
- [PhaseAgent Architecture](#phaseagent-architecture)
  - [PhaseAgentBase (ABC)](#phaseagentbase)
  - [ReconPhaseAgent](#reconphaseagent)
  - [ExploitPhaseAgent](#exploitphaseagent)
  - [PostExploitPhaseAgent + ShellBridge](#postexploitphaseagent--shellbridge)
- [PentestOrchestrator](#pentestorchestrator)
- [Tool Execution Layer](#tool-execution-layer)
  - [BashWrapper](#bashwrapper)
  - [ToolScheduler (TDG)](#toolscheduler)
- [Memory Architecture](#memory-architecture)
  - [MemAgent (Session)](#memagent)
  - [PersistentMemory (Cross-Session)](#persistentmemory)
- [Adaptive Payload Mutation](#adaptive-payload-mutation)
- [Zero-Day Hunter](#zero-day-hunter)
- [Reporting — Causal Chain](#reporting)
- [Data Flow Diagrams](#data-flow-diagrams)

---

## Quick Start

### Prerequisites

- **Python 3.10+** (async/await + `match-case` syntax)
- **Git**
- **nmap** (optional — Python fallback scanner activates if missing)
- **API key**: OpenRouter, OpenAI, or any OpenAI-compatible LLM endpoint

### Installation

```bash
# 1. Clone
git clone https://github.com/Spark-Corporations/Red-Shadow.git
cd Red-Shadow

# 2. Install (triggers post-install bootstrap → creates ~/.redclaw/)
pip install -e .

# Or manual dependency install:
pip install -r requirements.txt
```

**Dependencies** (from `requirements.txt`):
```
paramiko>=3.4.0        # SSH connections (ShellBridge SSHTransport)
aiohttp>=3.9.3         # Async HTTP (LLM API calls)
rich>=13.7.0           # CLI rendering (panels, tables, progress)
prompt-toolkit>=3.0.43 # Interactive CLI input
networkx               # Knowledge Graph (auto-installed via setup.py)
litellm>=1.50.0        # LLM reliability layer (retry, failover)
pydantic>=2.6.0        # Config validation
```

### API Key Setup

```bash
# Option 1: File-based (persists across sessions)
mkdir -p ~/.redclaw
echo "sk-or-v1-your-api-key" > ~/.redclaw/api_key.txt

# Option 2: Environment variable
export REDCLAW_LLM_MODEL="openai/gpt-4.1-mini"    # default
export REDCLAW_LLM_URL="https://openrouter.ai/api/v1"  # default

# Option 3: CLI command (interactive)
python -m redclaw
> /apikey sk-or-v1-your-api-key
```

### First Scan

```bash
# Interactive mode (Claude Code-style CLI)
python -m redclaw
> /pentest 10.10.10.5

# Direct mode (one-shot)
python src/redclaw/pentest.py 10.10.10.5
```

### What Happens

```
/pentest 10.10.10.5
  │
  ├─ Planning: LLM decides which phases to run/skip
  ├─ Recon: nmap or Python scanner → open ports + banners
  ├─ Ingest: Results → Knowledge Graph nodes
  ├─ Analysis: LLM extracts CVEs from service versions
  ├─ Exploit Gen: HypothesisEngine scores attack vectors
  ├─ Exploit Exec: Socket tests + LLM sandbox → real connections
  ├─ Zero-Day Hunt: Protocol fuzzing (stdlib, no tools needed)
  ├─ Post-Exploit: Real shell via ShellBridge → credential harvesting
  ├─ Summary: LLM executive synthesis
  └─ Report: Causal Chain (WHY-WHAT-HOW-PROOF-FIX)

Output: ~/.redclaw/engagements/10.10.10.5_YYYYMMDD_HHMMSS/
  ├─ reports/report.txt
  ├─ reports/report.json
  └─ knowledge_graph.json
```

### Key CLI Commands

| Command | Action |
|---|---|
| `/pentest <target>` | Full autonomous pentest |
| `/scan <target>` | Recon only (nmap + banner grab) |
| `/exploit <target>` | Exploitation only (requires prior scan) |
| `/findings` | Show discovered vulnerabilities |
| `/report` | Generate Causal Chain report |
| `/tools` | List available tools + availability |
| `/status` | Pipeline and agent status |
| `/apikey <key>` | Set LLM API key |
| `/model <name>` | Switch LLM model (gemini, openai, groq) |
| `/doctor` | System health check |

---

## Developer Onboarding

### İlk Gün — Bu dosyaları bu sırayla oku

```
Day 1: Mimariyi Anla
  1. README.md (bu dosya) — Architecture Overview section
  2. knowledge_graph.py (411 satır) — 8 node type, graph traversal
     → HER ŞEY buraya yazılıyor, buradan okunuyor
  3. pentest.py:55-75 — __init__: target, api_key, work_dir, llm_model
  4. pentest.py:1274-1449 — run(): 10-phase sequential chain

Day 2: Yeni Mimariyi Anla
  5. phase_agent.py — PhaseAgentBase ABC → run() → validate() → write_to_kg()
  6. orchestrator.py — Event queue, TRANSITION_MAP, summary_gate
  7. hypothesis_engine.py — CVE scoring, SERVICE_ATTACK_MAP

Day 3: Katman Derinliği
  8. exploit_phase_agent.py — 9 socket tests, LLM sandbox
  9. shell_bridge.py — 5 transport, from_kg() factory
  10. post_exploit_planner.py — MITRE ATT&CK tree
  11. tool_scheduler.py — TDG pre/post conditions
```

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `REDCLAW_LLM_MODEL` | `openai/gpt-4.1-mini` | LLM model identifier (OpenRouter format) |
| `REDCLAW_LLM_URL` | `https://openrouter.ai/api/v1` | LLM API endpoint |
| API key | `~/.redclaw/api_key.txt` | One line, plain text |

### Key Directories

```
~/.redclaw/
  ├─ api_key.txt          # LLM API key
  ├─ memory.db            # PersistentMemory (SQLite, cross-session)
  ├─ .initialized         # Post-install bootstrap marker
  └─ engagements/
      └─ {target}_{timestamp}/
          ├─ state.json    # MemAgent session state
          ├─ reports/      # Causal Chain output
          └─ *.json        # Phase outputs
```

### Design Decisions — NEDEN böyle yapıldı

| Karar | Neden | Alternatif ve Neden Reddedildi |
|---|---|---|
| **NetworkX** (KG backend) | In-memory, sıfır config, DiGraph traversal native | Neo4j → aşırı infra, pentest sırasında gereksiz |
| **SQLite** (PersistentMemory) | Tek dosya, cross-platform, concurrent read | PostgreSQL → harici servis lazım, dağıtım zorlaşır |
| **Event Queue** (Orchestrator) | Paralel fazlar, exploit_success → hemen post_exploit | Sequential chain → 176 satır if/await, paralel YOK |
| **LLM = code writer only** | Deterministic strategy, reproducible results | LLM decides strategy → her seferinde farklı sonuç |
| **ShellBridge abstraction** | Aynı API ile FTP/SSH/PG/Web bağlanabilir | Doğrudan ftplib/paramiko → her transport'a ayrı kod |
| **Socket tests önce** | 5ms, LLM call'dan 1000x hızlı, deterministik | Hep LLM sandbox → yavaş, token waste, non-deterministic |
| **MITRE ATT&CK tree** | Standardize, tekrarlanabilir, audit-ready | LLM "ne yapayım" diye soruyor → her seferinde farklı |
| **Capability flags** (TDG) | Tool X bitti → tool Y otomatik unlock | Manuel sıralama → bir tool ekleyince tüm chain kırılır |

### Known Limitations

- **ShellBridge SSH**: `asyncssh` import'u var ama `requirements.txt`'de yok — `paramiko` fallback aktif
- **Windows**: `BashLocalTransport` `cmd.exe` kullanır, bazı Unix komutları (`uname`, `cat /etc/passwd`) çalışmaz
- **ZeroDayHunter**: sadece stdlib — gerçek fuzzer performansı değil, anomaly detection seviyesinde
- **LLM sandbox**: `subprocess.run(python {temp}, timeout=30)` — container isolation YOK
- **Rate limiting**: OpenRouter 429'lar için exponential backoff var, ama concurrent request limiti yok

---

## Contributing

### Yeni PhaseAgent Nasıl Eklenir

```python
# 1. Dosya oluştur: openclaw_bridge/my_phase_agent.py

from .phase_agent import PhaseAgentBase, PhaseResult, PhaseStatus

class MyPhaseAgent(PhaseAgentBase):
    PHASE_NAME = "my_phase"
    REQUIRED_OUTPUT_FIELDS = ["results", "findings"]

    async def execute(self) -> dict:
        # KG'den oku
        services = self.kg.get_services_for_host(self.target)

        # İşini yap
        results = await self._do_work(services)

        # KG'ye yaz
        for finding in results:
            self.kg.add_vulnerability(...)

        return {"results": results, "findings": [...]}

    async def _do_work(self, services):
        # Tool çalıştır (BashWrapper)
        output = await self.run_command("nmap -sV {target}")

        # Veya LLM'e sor (sadece kod üretimi için)
        code = await self.ask_llm("Write a scanner for this service")

        return [...]
```

```python
# 2. Orchestrator'a kayıt et: orchestrator.py

# _build_agent() → agent_map'e ekle:
agent_map = {
    "recon":        lambda: ReconPhaseAgent(**base_args),
    "exploit_exec": lambda: ExploitPhaseAgent(**base_args),
    "post_exploit": lambda: PostExploitPhaseAgent(**base_args),
    "my_phase":     lambda: MyPhaseAgent(**base_args),  # ← EKLE
}

# TRANSITION_MAP'e ekle:
TRANSITION_MAP = {
    ...
    "analysis":  ["my_phase"],    # my_phase analysis'ten sonra çalışsın
    "my_phase":  ["exploit_gen"], # sonra exploit_gen tetiklensin
}

# AGENT_PHASES'e ekle:
AGENT_PHASES = {"recon", "exploit_exec", "post_exploit", "my_phase"}
```

```python
# 3. Test yaz
async def test_my_phase():
    agent = MyPhaseAgent(target="10.10.10.5", kg=kg, ...)
    result = await agent.run()
    assert result.status == PhaseStatus.COMPLETE
    assert "results" in result.data
```

### Yeni ShellBridge Transport Nasıl Eklenir

```python
# 1. shell_bridge.py'de transport class'ı ekle:

class MyDBTransport(ShellTransport):
    """MongoDB shell transport."""

    async def connect(self) -> bool:
        import pymongo
        self.client = pymongo.MongoClient(self.context.host, self.context.port)
        self.db = self.client[self.context.db_name or "admin"]
        return True

    async def execute(self, command: str) -> str:
        # Shell komutunu DB sorgusuna çevir
        if "whoami" in command:
            return str(self.db.command("connectionStatus"))
        elif command.startswith("ls"):
            return str(self.db.list_collection_names())
        return f"Unsupported: {command}"

    async def close(self):
        self.client.close()
```

```python
# 2. METHOD_TO_SHELL map'ine ekle:
METHOD_TO_SHELL = {
    ...
    "mongodb_noauth": ShellType.DB_MONGO,  # ← EKLE
}

# 3. ShellType enum'a ekle:
class ShellType(Enum):
    ...
    DB_MONGO = "db_mongo"
```

### Yeni TDG Tool Nasıl Eklenir

```python
# tool_scheduler.py → TOOL_DEPENDENCY_GRAPH'a ekle:

"nikto_scan": {
    "pre": ["http_confirmed"],           # Hangi capability'ler lazım
    "post": ["web_vulns", "headers"],    # Ne üretiyor
    "cmd": "nikto -h http://{target}:{http_port} -Format json",
    "binary": "nikto",                   # shutil.which() ile kontrol
    "timeout": 180,
    "description": "Web vulnerability scanner",
},
```

Kural: `pre` listesindeki tüm capability'ler KG'de `set_capability()` ile set edilmiş olmalı. Yoksa tool auto-skip olur.

### Test Yazma Kuralı

Her yeni modül için minimum test listesi:

```
1. Syntax check (py_compile)
2. Import check (from module import Class)
3. Instantiation (Class(mock_args))
4. KG read check (verilen input → doğru KG query)
5. KG write check (output → doğru node/edge oluştu)
6. Edge case (boş input, hatalı data, timeout)
7. Full flow (end-to-end with mocks)
```

---

## Architecture Overview

RedClaw is a **fully autonomous** penetration testing framework. An LLM (via OpenRouter API) handles natural language planning, analysis, and code generation — but **never makes strategic decisions**. Strategy is deterministic: the Knowledge Graph holds state, the HypothesisEngine scores attack priorities, and the ToolScheduler executes tools when pre-conditions are met.

```
┌────────────────────────────────────────────────────────────┐
│                    PentestOrchestrator                       │
│  Event Queue ← PentestEvent(type, phase, data)              │
│  Transition Map: planning → recon → ingest → analysis →     │
│    exploit_gen → exploit_exec ─┬→ zeroday ──────┐           │
│                                └→ post_exploit ─┤ (parallel)│
│                                                  → summary  │
│                                                  → report   │
├────────────────────────────────────────────────────────────┤
│  PhaseAgents (new)           │  Legacy Phases               │
│  ┌──────────────────┐       │  ┌──────────────────┐       │
│  │ ReconPhaseAgent   │       │  │ phase_planning()  │       │
│  │ ExploitPhaseAgent │       │  │ phase_ingest()    │       │
│  │ PostExploitAgent  │       │  │ phase_analyze()   │       │
│  └──────┬───────────┘       │  │ phase_exploit()   │       │
│         │                    │  │ phase_zeroday()   │       │
│         ▼                    │  │ phase_summary()   │       │
│  ┌──────────────┐           │  │ phase_report()    │       │
│  │ ShellBridge   │           │  └──────────────────┘       │
│  │ 5 Transports  │           │                              │
│  └──────────────┘           │                              │
├────────────────────────────────────────────────────────────┤
│                     Shared Infrastructure                    │
│  ┌───────────┐ ┌──────────────┐ ┌────────────────────────┐│
│  │ Knowledge  │ │  Hypothesis   │ │  PersistentMemory       ││
│  │ Graph (NX) │ │  Engine       │ │  (SQLite)               ││
│  └───────────┘ └──────────────┘ └────────────────────────┘│
│  ┌───────────┐ ┌──────────────┐ ┌────────────────────────┐│
│  │ BashWrapper│ │ ToolScheduler │ │ AdaptiveMutation       ││
│  │ (subproc) │ │ (TDG)        │ │ (14 strategies)        ││
│  └───────────┘ └──────────────┘ └────────────────────────┘│
└────────────────────────────────────────────────────────────┘
```

**Key design principle**: LLM writes code, system decides what to attack. Every phase reads from KG and writes back to KG. Phases never pass data directly — KG is the single source of truth.

---

## Core Pipeline

RedClaw executes a 10-phase autonomous pentest. Each phase reads from KG and writes results back:

| # | Phase | Input (KG Read) | Output (KG Write) | Executor |
|---|---|---|---|---|
| 1 | **Planning** | Target IP | `phases_to_run`, `phases_to_skip` | LLM |
| 2 | **Recon** | — | `host`, `port`, `service` nodes | `ReconPhaseAgent` |
| 3 | **Ingest** | Scan results | KG nodes + `capability` flags | Deterministic |
| 4 | **Analysis** | KG services | `vulnerability` nodes (CVE + severity) | LLM |
| 5 | **Exploit Gen** | KG vulns | `Hypothesis` objects (scored, ranked) | `HypothesisEngine` |
| 6 | **Exploit Exec** | Hypotheses | `exploit` nodes + `EXPLOITABLE_VIA` edges | `ExploitPhaseAgent` |
| 7 | **Zero-Day** | KG services | Protocol anomalies | `ZeroDayHunter` |
| 8 | **Post-Exploit** | `EXPLOITABLE_VIA` edges | `credential`, internal hosts | `PostExploitPhaseAgent` |
| 9 | **Summary** | Full KG | Executive summary text | LLM |
| 10 | **Report** | Full KG | Causal Chain PDF/JSON | `CausalChainReport` |

---

## Knowledge Graph

**File**: `redclaw/memory/knowledge_graph.py` (411 lines)  
**Backend**: NetworkX `DiGraph` (directed graph)

The KG is the central state store. Every phase reads from and writes to it. No inter-phase data is passed through variables — KG is the single source of truth.

### Node Types

```python
class NodeType(Enum):
    HOST          = "host"           # IP address
    PORT          = "port"           # ip:port (e.g. "10.10.10.5:80")
    SERVICE       = "service"        # ip:port:name (e.g. "10.10.10.5:80:http")
    VERSION       = "version"        # Service version string
    VULNERABILITY = "vulnerability"  # vuln:CVE-XXXX-XXXXX
    EXPLOIT       = "exploit"        # exploit:CVE:name
    CREDENTIAL    = "credential"     # cred:ip:username
    FILE          = "file"           # file:ip:path
```

### Edge Types (Relationships)

```python
class EdgeType(Enum):
    HAS_PORT        = "HAS_PORT"         # host → port
    RUNS_SERVICE    = "RUNS_SERVICE"      # port → service
    HAS_VERSION     = "HAS_VERSION"      # service → version
    HAS_VULN        = "HAS_VULN"         # service → vulnerability
    EXPLOITABLE_VIA = "EXPLOITABLE_VIA"  # vulnerability → exploit
    USES_CREDENTIAL = "USES_CREDENTIAL"  # host → credential
    CONTAINS_FILE   = "CONTAINS_FILE"    # host → file
    CONNECTS_TO     = "CONNECTS_TO"      # host → host (lateral movement)
```

### Graph Traversal Chain

```
Host(10.10.10.5)
  ├─ HAS_PORT → Port(10.10.10.5:80)
  │    └─ RUNS_SERVICE → Service(10.10.10.5:80:http)
  │         ├─ version: "nginx 1.24.0"
  │         └─ HAS_VULN → Vulnerability(vuln:CVE-2021-41773)
  │              ├─ severity: "critical", cvss: 9.8
  │              └─ EXPLOITABLE_VIA → Exploit(exploit:CVE-2021-41773:path_traversal)
  │                   ├─ tested: true, result: "success"
  │                   └─ evidence: "root:x:0:0:..."
  ├─ HAS_PORT → Port(10.10.10.5:22)
  │    └─ RUNS_SERVICE → Service(10.10.10.5:22:ssh)
  └─ USES_CREDENTIAL → Credential(cred:10.10.10.5:root)
       └─ source: "post_exploit:credential_harvesting:/etc/shadow"
```

### Capability Tracking

The KG also stores capability flags used by the `ToolScheduler` to determine which tools can run:

```python
kg.set_capability("open_ports", True)      # nmap ran successfully
kg.set_capability("http_confirmed", True)   # port 80/443 found
kg.set_capability("ssh_confirmed", True)    # port 22 found
kg.set_capability("cve_matches", True)      # nuclei found CVEs
```

### Natural Language Queries

```python
kg.query_natural_language("Find all vulnerabilities on 10.10.10.5")
kg.query_natural_language("Show exploits for CVE-2021-41773")
kg.query_natural_language("List all services on 10.10.10.5")
```

Uses regex IP/CVE extraction + keyword matching to route to typed query methods (`get_vulnerabilities_for_host`, `get_exploits_for_cve`, `get_services_for_host`, `get_credentials_for_host`, `get_attack_path`).

---

## Hypothesis Engine

**File**: `redclaw/openclaw_bridge/hypothesis_engine.py` (364 lines)

The HypothesisEngine replaces ad-hoc exploit selection with a **scored, ranked hypothesis system**. The system decides WHAT to attack; the LLM only decides HOW.

### Hypothesis Generation

Two sources, priority-ordered:

1. **CVE-backed** (from KG vulnerabilities): Confidence = `cvss / 10.0` (e.g., CVSS 9.8 → 98%)
2. **Service-based** (no CVE needed): Confidence starts at 35%, uses `SERVICE_ATTACK_MAP`

```python
SERVICE_ATTACK_MAP = {
    "ftp":        {"vectors": ["anonymous_login", "default_creds", "bounce_attack"]},
    "ssh":        {"vectors": ["default_creds", "key_bruteforce", "cve_exploit"]},
    "http":       {"vectors": ["path_traversal", "sqli", "default_admin", "header_injection"]},
    "mysql":      {"vectors": ["default_creds", "no_auth", "sqli"]},
    "postgresql":  {"vectors": ["default_creds", "no_auth", "trust_auth"]},
    "smb":        {"vectors": ["null_session", "eternal_blue", "default_share"]},
    "redis":      {"vectors": ["no_auth", "config_write", "module_load"]},
    "mongodb":    {"vectors": ["no_auth", "default_creds"]},
    "telnet":     {"vectors": ["default_creds", "no_auth"]},
}
```

### Confidence Adjustment

```python
engine.record_result(hypothesis, "success", confidence_delta=+0.3)
engine.record_result(hypothesis, "failed",  confidence_delta=-0.2)
```

`record_result()` also writes to KG:
```python
kg.add_exploit(cve=hypothesis.cve, exploit_name=f"{vector} ({result})", tested=True)
# → creates EXPLOITABLE_VIA edge in KG graph
```

### Cross-Session Learning

If `PersistentMemory` is available:
```python
recall = memory.recall(target)
adj = recall.get_confidence_adjustment(cve=h.cve, service=h.target_service)
h.confidence += adj  # Negative for repeated failures, positive for similar successes
```

---

## PhaseAgent Architecture

**File**: `redclaw/openclaw_bridge/phase_agent.py` (223 lines)

The PhaseAgent system replaces monolithic `phase_*()` methods with isolated, validated, KG-integrated agents.

### PhaseAgentBase

Abstract base class enforcing:

| Feature | How |
|---|---|
| **Isolated context** | Each agent has its own conversation history (`_messages`) |
| **KG read** | `_load_context_from_kg()` — each agent reads only what it needs |
| **KG write** | `_write_to_kg(result)` — each agent writes its outputs |
| **External validation** | `_validate(result)` against `REQUIRED_OUTPUT_FIELDS` |
| **Retry loop** | Up to 3 iterations if validation fails |
| **Tool execution** | `run_tool()` / `run_command()` via BashWrapper |

```python
class PhaseAgentBase(ABC):
    PHASE_NAME: str
    REQUIRED_OUTPUT_FIELDS: List[str]

    async def run(self) -> PhaseResult:
        # 1. Load KG context
        # 2. Call execute() — subclass implements
        # 3. Validate output
        # 4. Write to KG
        # 5. Return PhaseResult

    @abstractmethod
    async def execute(self) -> dict: ...
```

### ReconPhaseAgent

**File**: `redclaw/openclaw_bridge/recon_phase_agent.py` (400 lines)

Network reconnaissance — **100% deterministic, no LLM involvement**.

**Primary**: `nmap -sV -sC -O {target}` via `BashWrapper` (real subprocess).  
**Fallback**: Python async socket scanner with banner grabbing.

```
nmap available? ──YES──→ nmap -sV -sC → XML parse (ElementTree)
       │                                    ↓
       NO                              KG: add_host, add_port, add_service
       ↓
Python TCP Scanner (asyncio.open_connection)
  ├─ Port scan: top 100 ports, 50 concurrent
  ├─ Banner grab: 1024 bytes, 3s timeout
  └─ Service ID: regex signatures for SSH, FTP, HTTP, MySQL, PG, Redis
       ↓
  KG: add_host, add_port, add_service
  KG: set_capability("open_ports", "http_confirmed", ...)
```

Banner signature matching (deterministic, not LLM):
```python
BANNER_SIGNATURES = {
    r"SSH-\d": "ssh",
    r"220.*FTP|vsftpd|ProFTPD": "ftp",
    r"HTTP/1\.[01]|nginx|Apache": "http",
    r"\x00\x00\x00.*mysql|MariaDB": "mysql",
    ...
}
```

### ExploitPhaseAgent

**Files**:
- `redclaw/openclaw_bridge/exploit_phase_agent.py` (700 lines)
- `redclaw/openclaw_bridge/parallel_exploit.py` (280 lines) — **NEW**

**Parallel execution** — all hypotheses run concurrently, not sequentially:

```
HypothesisEngine → 9 hypotheses (CVSS-ranked)
        ↓
PriorityHypothesisQueue (heapq max-heap by confidence)
        ↓
ParallelExploitOrchestrator (asyncio.Semaphore, max_concurrent=4)
        ↓
    [ftp:21 anon]     [mysql:3306 CVE-B]    [http:80 CVE-A]    [ssh:22 default]
         ↓                   ↓                    ↓                  ↓
    port_lock(21)       port_lock(3306)      port_lock(80)      port_lock(22)
         ↓                   ↓                    ↓                  ↓
    _test_single:       _test_single:        _test_single:      _test_single:
    socket → OK         socket → SUCCESS ✅  socket → WAF       socket → banner
    sandbox → skip      success_event.set()  sandbox exec...    sandbox → fail
         ↓                   ↓                    ↓                  ↓
    _record_result      _record_result       SKIPPED (early)    SKIPPED (early)
```

**3 safety layers** inside `ParallelExploitOrchestrator`:

| Layer | Class | Purpose |
|---|---|---|
| **Concurrency** | `asyncio.Semaphore(4)` | Max 4 hypotheses simultaneously |
| **Port safety** | `PortLockManager` | Same-port hypotheses serialize; different ports always parallel |
| **Early stop** | `asyncio.Event` | First `access_gained=True` → remaining hypotheses skip |

**Per-hypothesis dual strategy** (via `_test_single_hypothesis()`):

1. **Direct socket test** (5ms, deterministic) — FTP anon, SSH banner, HTTP path traversal, MySQL/PG no-auth, SMB probe, Redis PING, VNC auth check, Telnet banner
2. **LLM sandbox** (if socket inconclusive) — LLM generates Python code → temp file → `subprocess` (30s timeout) → parse `EXPLOIT_RESULT:` JSON marker → delete temp file

**Performance**: Sequential = N × avg_time. Parallel = max(concurrent_times). With 4-way concurrency, 7 hypotheses complete in ~2x single-test time instead of 7x.

### PostExploitPhaseAgent + ShellBridge

**Files**: 
- `redclaw/openclaw_bridge/shell_bridge.py` (500 lines)
- `redclaw/openclaw_bridge/post_exploit_phase_agent.py` (250 lines)

**Critical change**: Replaces LLM shell simulation with **real transport connections**.

#### ShellBridge

Transport abstraction that maps exploit types to protocol handlers:

```python
METHOD_TO_SHELL = {
    "ftp_anonymous":     ShellType.FTP,       → FTPTransport (ftplib)
    "default_creds":     ShellType.SSH,        → SSHTransport (asyncssh/paramiko)
    "postgres_noauth":   ShellType.DB_POSTGRES,→ PostgresTransport (asyncpg/psycopg2)
    "path_traversal":    ShellType.WEB,        → WebShellTransport (HTTP GET)
    "rce":               ShellType.WEB,        → WebShellTransport (HTTP GET)
    ...
    fallback:            ShellType.BASH_LOCAL  → BashLocalTransport (subprocess)
}
```

Factory method reads KG:
```python
bridge = ShellBridge.from_kg(kg, target)
# 1. Query KG for exploit nodes (EXPLOITABLE_VIA edges)
# 2. Select best exploit (access_gained > tested > any)
# 3. Map attack_vector → ShellType → Transport class
# 4. Get credentials from KG
# 5. Create ShellContext + Transport instance
```

Each transport implements `connect() → bool`, `execute(command) → str`, `close()`.

**PostgresTransport** special behavior: Converts shell commands to SQL equivalents:
```python
"cat /etc/passwd" → "SELECT pg_read_file('/etc/passwd', 0, 10000)"
"whoami"          → "SELECT current_user, session_user"
"ls /"            → "SELECT * FROM pg_ls_dir('/') LIMIT 50"
```

#### PostExploitPhaseAgent + PostExploitChain

**Files**:
- `redclaw/openclaw_bridge/post_exploit_phase_agent.py` (310 lines)
- `redclaw/openclaw_bridge/post_exploit_chain.py` (500 lines) — **NEW**

Execution flow: fingerprint → **6-stage chain** → MITRE planner → executor:

```
1. ShellBridge.from_kg(kg, target) → Select transport
2. bridge.connect() → Real TCP/FTP/SSH/PG connection
3. _fingerprint() → uname, whoami, id, hostname, ifconfig

4. ⭐ PostExploitChain.run() → 6 stages:
   ┌────────────────────────────────────────────────────────────────────┐
   │ Stage 1: LOCAL ENUMERATION (20+ commands)                │
   │   os_info, sudo_rights, SUID, cron, env, SSH keys, net   │
   ├────────────────────────────────────────────────────────────────────┤
   │ Stage 2: PRIVILEGE ESCALATION (5 vectors)                │
   │   SUID exploit map (14 binaries: nmap→!sh, vim→:!bash)  │
   │   Sudo misconfig (11 rules: ALL→bash, python→system)    │
   │   Writable /etc/passwd, Kernel CVE map, Cron hijack      │
   ├────────────────────────────────────────────────────────────────────┤
   │ Stage 3: CREDENTIAL HARVESTING (15+ categories)          │
   │   WP, Laravel, Django, Rails, MySQL, PG, Redis, Mongo    │
   │   SSH keys, AWS/GCP/Azure, Docker, K8s, Browser          │
   ├────────────────────────────────────────────────────────────────────┤
   │ Stage 4: LATERAL MOVEMENT                                │
   │   SSH key reuse, credential spray, internal port scan    │
   │   (skips if no creds AND no SSH keys found)              │
   ├────────────────────────────────────────────────────────────────────┤
   │ Stage 5: PERSISTENCE (risk_threshold)                    │
   │   cron backdoor, SSH authorized_keys, .bashrc, systemd   │
   │   new user (filterable: low/medium/high risk)            │
   ├────────────────────────────────────────────────────────────────────┤
   │ Stage 6: DATA EXFILTRATION (evidence)                    │
   │   /etc/shadow, DB dump (mysqldump, pg_dumpall)           │
   │   .env files, web configs, SSH keys                      │
   └────────────────────────────────────────────────────────────────────┘
5. PostExploitPlanner.plan() → MITRE ATT&CK tree (7 objectives)
6. PostExploitExecutor.execute(plan, shell_fn=bridge.execute)
7. Write all discoveries → KG (credentials, hosts, capabilities)
```

**Kernel CVE mapping** (from Stage 2):

| Kernel | CVE | Exploit |
|---|---|---|
| 3.x | CVE-2016-5195 | DirtyCow |
| 4.x | CVE-2021-4034 | PwnKit (pkexec) |
| 5.x | CVE-2022-0847 | DirtyPipe |
| 6.x | CVE-2024-1086 | nf_tables UAF |

---

## PentestOrchestrator

**File**: `redclaw/openclaw_bridge/orchestrator.py` (400 lines)

Replaces the old 176-line sequential `run()` method with an **event-driven** phase execution system.

### Event Types

```python
class EventType(Enum):
    PHASE_COMPLETE   = "phase_complete"
    PHASE_INCOMPLETE = "phase_incomplete"
    PHASE_FAILED     = "phase_failed"
    EXPLOIT_SUCCESS  = "exploit_success"    # Triggers post_exploit immediately
    ALL_COMPLETE     = "all_complete"
    CRITICAL_FAIL    = "critical_fail"
```

### Transition Map

```python
TRANSITION_MAP = {
    "planning":     ["recon"],
    "recon":        ["ingest"],
    "ingest":       ["analysis"],
    "analysis":     ["exploit_gen"],
    "exploit_gen":  ["exploit_exec"],
    "exploit_exec": ["zeroday"],          # post_exploit via EXPLOIT_SUCCESS
    "zeroday":      [],                    # → summary gate
    "post_exploit": [],                    # → summary gate
    "summary":      ["report"],
    "report":       [],
}
```

### Key Mechanisms

**Exploit Success Event**: When `exploit_exec` completes with `successes > 0`, it emits an `EXPLOIT_SUCCESS` event. The dispatcher immediately starts `post_exploit` — no waiting for `zeroday` to finish.

**Summary Gate**: Summary cannot start until ALL gate phases (`zeroday` + `post_exploit`) are complete or skipped. This prevents the summary from running before post-exploitation harvests credentials.

**Parallel Execution**: `zeroday` and `post_exploit` run simultaneously as `asyncio.Task` objects.

**LLM Adapter**: The orchestrator bridges `pentest.call_llm(prompt, system_prompt)` (old API) to PhaseAgent's `messages` list format.

---

## Tool Execution Layer

### BashWrapper

**File**: `redclaw/tools/bash_wrapper.py` (238 lines)

Generic command executor using `asyncio.create_subprocess_shell`. All tool output passes through `OutputCleaner` which strips ANSI codes, normalizes whitespace, and extracts structured data.

4 tool operations:
- `exec_command(command)` → subprocess + OutputCleaner
- `read_file(path)` → local file read
- `write_file(path, content)` → local file write  
- `save_finding(title, severity, description)` → finding record

### ToolScheduler

**File**: `redclaw/openclaw_bridge/tool_scheduler.py` (450 lines)

**Tool Dependency Graph (TDG)**: Each tool declares:
- `pre`: KG capabilities required (e.g., `["open_ports"]`)
- `post`: KG capabilities produced (e.g., `["cve_matches", "nuclei_results"]`)
- `cmd`: Command template with `{target}` substitution
- `binary`: System binary checked via `shutil.which()`

```python
TOOL_DEPENDENCY_GRAPH = {
    "nmap_scan":     pre=[],                  post=["open_ports", "services"]
    "nuclei_scan":   pre=["open_ports"],      post=["cve_matches"]
    "gobuster_scan": pre=["http_confirmed"],  post=["directories"]
    "ffuf_scan":     pre=["http_confirmed"],  post=["fuzz_results"]
    "sqlmap_scan":   pre=["http_confirmed", "directories"], post=["sqli_results"]
    "hydra_ssh":     pre=["ssh_confirmed"],   post=["ssh_creds"]
    "hydra_ftp":     pre=["ftp_confirmed"],   post=["ftp_creds"]
}
```

Execution algorithm:
1. Check binary availability (`shutil.which`)
2. Find tools with all pre-conditions met in KG
3. Run ready tools in parallel batches (up to `max_parallel=3`)
4. Each completed tool sets its post-condition capabilities in KG
5. Re-check readiness — newly unlocked tools enter next batch
6. Auto-skip tools whose pre-conditions can never be met

---

## Memory Architecture

### MemAgent (Session Memory)

**File**: `redclaw/memory/memagent.py` (14KB)

In-session state management: current phase, completed tasks, key findings, conversation history. Uses a local JSON file for persistence within a single engagement.

### PersistentMemory (Cross-Session)

**File**: `redclaw/memory/persistent_memory.py` (490 lines)  
**Backend**: SQLite (`~/.redclaw/memory.db`)

2-layer episodic memory:

**Layer 1 — Exact Recall**: Same target IP → direct history lookup
```sql
SELECT * FROM attempts WHERE target = ? ORDER BY timestamp DESC
```

**Layer 2 — Similar Recall**: Same service+version fingerprint → cross-target learning
```python
fingerprint = hashlib.sha256(
    "|".join(sorted(f"{svc['name']}:{svc['version']}" for svc in services))
).hexdigest()[:16]
```
```sql
SELECT * FROM attempts WHERE fingerprint = ? AND target != ?
```

**Confidence adjustment formula**:
```python
exact_fails = count(exact_matches where result == "failed" and cve matches)
similar_successes = count(similar_matches where result == "success" and service matches)
adjustment = (similar_successes * 0.1) - (exact_fails * 0.15)
# Clamped to [-0.3, +0.2]
```

Schema:
```sql
CREATE TABLE sessions (id, target, fingerprint, services_json, start_time, end_time, status)
CREATE TABLE attempts (id, session_id, target, fingerprint, service, version, port, 
                       cve, attack_vector, result, confidence_delta, evidence, timestamp)
```

---

## Adaptive Payload Mutation

**File**: `redclaw/openclaw_bridge/adaptive_mutation.py` (768 lines)

3-layer response adaptation:

**Layer 1 — ResponseClassifier**: Categorizes tool/HTTP responses into 10 classes:
```
WAF_DETECTED, AUTH_REQUIRED, RATE_LIMITED, VULNERABLE,
NOT_FOUND, SERVER_ERROR, TIMEOUT, CONNECTION_REFUSED,
SUCCESS_NO_VULN, UNKNOWN
```
Detection via HTTP status codes (403→WAF, 401→AUTH, 429→RATE), body patterns (`"CloudFlare"`, `"ModSecurity"`, `"Access Denied"`), header analysis.

**Layer 2 — MutationStrategy**: 14 deterministic strategies:
```
CASE_VARIATION, COMMENT_INJECTION, UNICODE_NORMALIZATION,
DOUBLE_URL_ENCODE, NULL_BYTE_INJECTION, CHUNKED_ENCODING,
PATH_NORMALIZATION, DEFAULT_CREDENTIALS, HEADER_MANIPULATION,
METHOD_OVERRIDE, BASELINE_RETRY, ENCODING_SWITCH, DELAY_RETRY
```

**Layer 3 — Strategy Selection**: Response class → ordered strategy list:
```python
WAF_DETECTED → [CASE_VARIATION, COMMENT_INJECTION, UNICODE_NORMALIZATION, DOUBLE_URL_ENCODE]
AUTH_REQUIRED → [DEFAULT_CREDENTIALS, HEADER_MANIPULATION, METHOD_OVERRIDE]
RATE_LIMITED → [DELAY_RETRY, ENCODING_SWITCH, NULL_BYTE_INJECTION]
```

Cross-session learning via `PersistentMemory` — strategies that worked against similar services are prioritized.

---

## Zero-Day Hunter

**File**: `redclaw/zeroday_hunter.py` (664 lines)

Autonomous protocol fuzzing using **only Python stdlib** — no external tools required.

6 protocol fuzzers:

| Fuzzer | Technique | Targets |
|---|---|---|
| `fuzz_ftp` | ALLO overflow, USER/PASS format strings, SITE abuse, path traversal | vsftpd, ProFTPD |
| `fuzz_http` | Header injection, verb abuse, chunked encoding, path traversal, Host header manipulation | nginx, Apache |
| `fuzz_mysql` | Auth bypass sequences, greeting analysis, capability fingerprinting | MySQL, MariaDB |
| `fuzz_ssh` | Banner analysis, large key exchange, algorithm mismatch | OpenSSH |
| `fuzz_vnc` | Auth type enumeration, no-auth probe, version fingerprinting | RealVNC, TightVNC |
| `fuzz_telnet` | IAC option overflow, login brute, NULL byte injection | Various |

Findings recorded with severity levels: `ANOMALY`, `POTENTIAL`, `CONFIRMED`, `CRASH`.

---

## Reporting

**File**: `redclaw/reporting/causal_chain.py` (246 lines)

Every finding follows the **Causal Chain** format:

```
WHY:   Root cause — what configuration, code, or design flaw led to this
WHAT:  CVE ID, CVSS score, affected service, version, impact classification
HOW:   Step-by-step exploitation path (numbered sequence)
PROOF: Command output, response snippets, evidence
FIX:   Specific remediation steps with priority
```

Output formats: Plain text (`report.txt`) and JSON (`report.json`). Report includes executive summary, findings section, attack path visualization (from KG `get_attack_path()`), and prioritized remediation plan.

---

## Data Flow Diagrams

### Exploit → KG → Post-Exploit Flow

```
ExploitPhaseAgent.execute()
    │
    ├─ Direct Socket Test (FTP anonymous login)
    │   └─ SUCCESS
    │        └─ HypothesisEngine.record_result(h, "success")
    │             ├─ h.status = SUCCESS
    │             ├─ h.confidence_delta = +0.3
    │             └─ kg.add_exploit("CVE-XXX", "anonymous_login (success)", tested=True)
    │                  └─ KG Edge: vuln:CVE-XXX → EXPLOITABLE_VIA → exploit:CVE-XXX:anonymous_login
    │
    ▼
PentestOrchestrator
    └─ EXPLOIT_SUCCESS event (successes > 0)
         └─ _maybe_start_phase("post_exploit")
              │
              ▼
PostExploitPhaseAgent.execute()
    │
    ├─ ShellBridge.from_kg(kg, target)
    │   └─ Read exploit nodes → METHOD_TO_SHELL["anonymous_login"] → FTP
    │        └─ FTPTransport(host, port=21, username="anonymous")
    │
    ├─ bridge.connect() → ftplib.FTP.connect() + .login()
    │
    ├─ _fingerprint(bridge)
    │   ├─ bridge.execute("uname -a") → "Linux 5.15.0 x86_64"
    │   └─ detect_os() → LINUX, detect_privilege() → USER
    │
    ├─ PostExploitPlanner.plan(context)
    │   └─ MITRE ATT&CK tree → 6 objectives (sort by priority)
    │
    └─ PostExploitExecutor.execute(plan, shell_fn=bridge.execute)
        ├─ situational_awareness: cat /etc/passwd, id, ifconfig
        ├─ credential_harvesting: cat /etc/shadow, find .ssh/
        │   └─ extract_credentials(output) → kg.add_credential()
        ├─ internal_discovery: arp -a, cat /etc/hosts
        │   └─ detect_internal_hosts(output) → kg.add_host()
        └─ lateral_movement: _inject_lateral_hypotheses()
             └─ New hypotheses for discovered internal hosts
```

### Orchestrator Event Flow

```
planning_complete
    │
    ▼ (TRANSITION_MAP)
recon_complete ── agent phase (ReconPhaseAgent)
    │
    ▼
ingest_complete ── legacy (phase_ingest → KG population)
    │
    ▼
analysis_complete ── legacy (phase_analyze → CVE extraction → KG vulns)
    │
    ▼
exploit_gen_complete ── legacy (phase_exploit → HypothesisEngine.generate())
    │
    ▼
exploit_exec_complete ── agent phase (ExploitPhaseAgent)
    │
    ├─ TRANSITION_MAP → zeroday (asyncio.Task #1)
    │
    └─ EXPLOIT_SUCCESS → post_exploit (asyncio.Task #2)  ← PARALLEL
    │
    ▼ (both complete → summary_gate opens)
summary_complete ── legacy (phase_brain_summary)
    │
    ▼
report_complete ── legacy (phase_report → CausalChainReport)
    │
    ▼
ALL_COMPLETE → orchestrator.run() returns
```

---

## Phase Validation System

**File**: `redclaw/openclaw_bridge/phase_validation.py` (326 lines)

3-layer termination control — the system, not the LLM, decides when a phase is complete:

**Layer 1 — Structured Output**: Phase must return JSON with required fields:
```python
REQUIRED_FIELDS = {
    "recon":        {"scan_results": dict},
    "ingest":       {"services": list},
    "analysis":     {"findings": list, "raw_text": str},
    "exploit_exec": {"tests_run": list},
}
```

**Layer 2 — External State**: KG is checked independently:
```python
def is_recon_complete(kg, target):
    return kg.get_services_for_host(target)["count"] > 0

def is_analysis_complete(kg, target):
    return kg.get_vulnerabilities_for_host(target)["count"] > 0
```

**Layer 3 — PhaseRunner with Retry**: If either Layer 1 or 2 fails, the phase re-executes (up to `max_retries` times) with feedback about what's missing.

---

## Project Structure

```
src/redclaw/
├── pentest.py                          # Main pentest runner (RedClawPentest class)
├── zeroday_hunter.py                   # Protocol fuzzing (Python stdlib)
│
├── openclaw_bridge/
│   ├── orchestrator.py                 # Event-driven phase orchestrator (NEW)
│   ├── phase_agent.py                  # PhaseAgentBase ABC (NEW)
│   ├── recon_phase_agent.py            # Recon via nmap/Python socket (NEW)
│   ├── exploit_phase_agent.py          # Dual exploit: socket + LLM sandbox (NEW)
│   ├── post_exploit_phase_agent.py     # Real shell post-exploit (NEW)
│   ├── shell_bridge.py                 # 5 transport types (NEW)
│   ├── parallel_exploit.py            # Parallel hypothesis execution (NEW)
│   ├── post_exploit_chain.py          # 6-stage post-exploit pipeline (NEW)
│   ├── hypothesis_engine.py            # Scored hypothesis generation
│   ├── post_exploit_planner.py         # MITRE ATT&CK objective tree
│   ├── tool_scheduler.py              # TDG-based tool execution
│   ├── phase_validation.py             # 3-layer phase completion checking
│   ├── adaptive_mutation.py            # Response-driven payload mutation
│   ├── runtime.py                      # OpenClaw runtime + agent loop
│   └── tool_bridge.py                  # LLM tool call routing
│
├── memory/
│   ├── knowledge_graph.py              # NetworkX DiGraph (8 node types, NL queries)
│   ├── memagent.py                     # Session-level state management
│   └── persistent_memory.py            # SQLite cross-session learning
│
├── tools/
│   ├── bash_wrapper.py                 # Generic subprocess executor
│   ├── output_cleaner.py               # Tool output normalization
│   ├── nmap_wrapper.py                 # nmap-specific parser
│   ├── nuclei_wrapper.py               # nuclei scanner wrapper
│   ├── gobuster_wrapper.py             # Directory brute-force wrapper
│   ├── ffuf_wrapper.py                 # Web fuzzer wrapper
│   └── sqlmap_wrapper.py               # SQL injection wrapper
│
├── reporting/
│   └── causal_chain.py                 # WHY-WHAT-HOW-PROOF-FIX reports
│
├── cli/                                # Command-line interface
├── core/                               # Core abstractions
├── skills/                             # LLM-callable skill definitions
└── router/                             # API routing
```

---

## Test Results

All modules verified with automated test suites:

| Module | Tests | Status |
|---|---|---|
| PhaseAgentBase | 7/7 | ✅ |
| ReconPhaseAgent | 7/7 | ✅ |
| ExploitPhaseAgent | 9/9 | ✅ |
| ShellBridge | 9/9 | ✅ |
| PostExploitPhaseAgent | 9/9 | ✅ |
| PentestOrchestrator | 8/8 | ✅ |
| ParallelExploitOrchestrator | 24/24 | ✅ |
| PostExploitChain | 54/54 | ✅ |
| **Total** | **127/127** | ✅ |
