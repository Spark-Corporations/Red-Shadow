# 🔴 RedClaw V3.1 — Autonomous Penetration Testing Platform

> **Codename: Red Shadow**
> Enterprise-grade AI-driven autonomous pentesting with multi-agent architecture

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-red.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20Docker-lightgrey.svg)]()

---

## 📋 Table of Contents

- [What is RedClaw?](#-what-is-redclaw)
- [Features](#-features)
- [Architecture](#-architecture)
- [Quick Start](#-quick-start)
- [Installation](#-installation)
- [Usage](#-usage)
- [Docker](#-docker-deployment)
- [API Key Setup](#-api-key-setup)
- [CLI Reference](#-cli-reference)
- [Output & Reports](#-output--reports)
- [Project Structure](#-project-structure)

---

## 🔍 What is RedClaw?

RedClaw is an **autonomous penetration testing platform** powered by LLMs (Large Language Models) via OpenRouter API. It performs end-to-end security assessments — from reconnaissance to exploitation to post-exploitation — with **one single command**.

**RedClaw does NOT require Metasploit, Nmap, or any external tools.** It uses pure Python for all operations, making it truly cross-platform. When Nmap is available (e.g., Docker/Linux), it uses it for enhanced scanning.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| **10-Phase Autonomous Pentest** | Scan → Exploit → Zero-Day Hunt → Post-Exploit → Report |
| **Zero-Day Hunter** | Protocol fuzzing, boundary testing, anomaly detection |
| **Brain + Hands Architecture** | Brain (GPT) plans strategy, Hands (Qwen) writes exploits |
| **Cross-Platform** | Windows (cmd/PowerShell) + Linux + Docker |
| **No External Tools Required** | Pure Python scanner, exploiter, and reporter |
| **Interactive CLI** | Rich terminal UI with slash commands |
| **Knowledge Graph** | NetworkX-based attack graph |
| **CausalChain Reports** | Text + JSON with findings, evidence, and remediation |

---

## 🏗 Architecture

**10-Phase Pipeline (one command runs ALL):**

```
Phase 1:  Brain Planning        → AI creates pentest strategy
Phase 2:  Recon (Port Scan)     → Nmap or Python TCP scanner
Phase 3:  KnowledgeGraph        → Build attack graph
Phase 4:  Brain Analysis        → CVE identification + severity
Phase 5:  Hands Exploit Gen     → AI writes exploit code
Phase 6:  Exploitation          → FTP, HTTP, VNC, MySQL, SSH, etc.
Phase 7:  Zero-Day Hunting      → Protocol fuzzing + anomaly detection
Phase 8:  Post-Exploitation     → System info, file enum, loot
Phase 9:  Brain Summary         → Executive summary
Phase 10: Report Generation     → CausalChain text + JSON report
```

---

## 🚀 Quick Start

```bash
# 1. Clone
git clone https://github.com/Spark-Corporations/Red-Shadow.git
cd Red-Shadow

# 2. Install
pip install aiohttp networkx

# 3. Set API key (optional — works without it too)
# Windows PowerShell:
$env:OPENROUTER_API_KEY="sk-or-v1-your-key-here"
# Linux:
export OPENROUTER_API_KEY="sk-or-v1-your-key-here"

# 4. Run pentest (non-interactive mode)
python -m redclaw pentest 192.168.1.83
```

**Or use the interactive CLI:**

```bash
python -m redclaw

# Inside the CLI:
redclaw ❯ /pentest 192.168.1.83
```

---

## 📦 Installation

### Prerequisites

- **Python 3.10+**
- **OpenRouter API Key** (free tier available at [openrouter.ai](https://openrouter.ai))

### Steps

```bash
# Clone
git clone https://github.com/Spark-Corporations/Red-Shadow.git
cd Red-Shadow

# Install dependencies
pip install aiohttp networkx

# (Optional) Install CLI extras for interactive mode
pip install rich prompt_toolkit
```

### Set API Key

```bash
# Windows PowerShell
$env:OPENROUTER_API_KEY="sk-or-v1-your-key-here"

# Linux/macOS
export OPENROUTER_API_KEY="sk-or-v1-your-key-here"

# Or save to config file
mkdir -p ~/.redclaw
echo "sk-or-v1-your-key-here" > ~/.redclaw/api_key.txt
```

---

## 🎯 Usage

### Method 1: Interactive CLI (Recommended)

```bash
python -m redclaw
```

This opens the RedClaw terminal with slash commands:

```
redclaw ❯ /pentest 192.168.1.83    ← Full 10-phase autonomous pentest
redclaw ❯ /scan 192.168.1.83       ← Quick port scan only
redclaw ❯ /exploit 192.168.1.83    ← Exploitation only (needs prior scan)
redclaw ❯ /findings                ← Show all findings
redclaw ❯ /report                  ← Generate report
redclaw ❯ /status                  ← Show pipeline status
redclaw ❯ /help                    ← All commands
```

### Method 2: Non-Interactive (one-shot)

```bash
# Full pentest
python -m redclaw pentest 192.168.1.83

# Or directly
python src/redclaw/pentest.py 192.168.1.83
```

### Method 3: Docker

```bash
docker build -t redclaw:3.1 .
docker run --rm --network host \
  -e OPENROUTER_API_KEY="sk-or-v1-..." \
  redclaw:3.1 192.168.1.83
```

### What `/pentest` Does

When you run `/pentest <target>`, it executes **all 10 phases** autonomously:

1. **Brain Planning** — AI creates strategy based on target
2. **Port Scan** — Discovers all open ports + services
3. **KnowledgeGraph** — Maps relationships between services
4. **CVE Analysis** — Identifies vulnerabilities for each service
5. **Exploit Generation** — AI writes custom exploit code
6. **Exploitation** — Tests exploits against:
   - FTP (anonymous login, banner grab)
   - HTTP (path traversal, hidden dirs)
   - MySQL (auth bypass, banner)
   - VNC (no-auth check)
   - SSH (banner, version analysis)
   - Telnet (default creds)
   - PostgreSQL (no-auth test)
7. **Zero-Day Hunting** — Deep protocol fuzzing:
   - FTP: command injection, SITE abuse, vsFTPd backdoor
   - HTTP: verb tampering, header overflow, hidden files (.git, .env, phpinfo)
   - MySQL: auth bypass race (CVE-2012-2122), buffer overflow
   - SSH: oversized banner, protocol fuzzing
   - VNC: null password, auth type analysis
   - Telnet: default cred brute force
8. **Post-Exploitation** — System enumeration if access gained
9. **Executive Summary** — AI-generated engagement summary
10. **Report** — CausalChain report (text + JSON)

---

## 🐳 Docker Deployment

```bash
# Build
docker build -t redclaw:3.1 .

# Run
docker run --rm --network host \
  -e OPENROUTER_API_KEY="sk-or-v1-..." \
  -v ./engagements:/root/.redclaw/engagements \
  redclaw:3.1 192.168.1.83

# Docker Compose
docker compose up
```

The Docker image (Kali Linux) includes: Nmap, Nuclei, Metasploit, SQLMap, Hydra, Nikto, LinPEAS, BloodHound.

---

## 🔑 API Key Setup

RedClaw uses **OpenRouter** for LLM access. Free models available.

1. Go to [openrouter.ai](https://openrouter.ai) → Sign up → Keys → Create Key
2. Set it: `export OPENROUTER_API_KEY="sk-or-v1-..."`

| Role | Model | Purpose |
|------|-------|---------|
| **Brain** | `openai/gpt-oss-120b:free` | Strategy, CVE analysis |
| **Hands** | `arcee-ai/trinity-large-preview:free` | Exploit code generation |

**Without API key:** Port scanning, exploitation, zero-day hunting, and reports still work. Only AI analysis/planning phases are skipped.

---

## 💻 CLI Reference

| Command | Description |
|---------|-------------|
| `/pentest <ip>` | **Full 10-phase autonomous pentest** |
| `/scan <ip>` | Port scan only |
| `/exploit <ip>` | Exploitation only (requires approval) |
| `/findings` | Show all findings |
| `/report` | Generate report |
| `/status` | Pipeline + agent status |
| `/config` | Engagement configuration |
| `/tools` | List tool availability |
| `/apikey` | Set/view API key |
| `/model` | Switch LLM (gemini/openai/groq/openrouter) |
| `/doctor` | Health-check dependencies |
| `/setup-tools` | Auto-install missing tools |
| `/agent` | LLM provider health |
| `/help` | All commands |
| `/quit` | Exit |

---

## 📊 Output & Reports

All results saved to `~/.redclaw/engagements/<target>_<timestamp>/`:

```
~/.redclaw/engagements/192.168.1.83_20260226/
├── claude-progress.txt    # Real-time progress
├── nmap_scan.txt          # Scan results
├── reports/
│   ├── report.txt         # Human-readable CausalChain report
│   └── report.json        # Machine-readable JSON
└── exploits/              # Generated exploit code
```

---

## 📁 Project Structure

```
Red-Shadow/
├── src/redclaw/
│   ├── __init__.py           # v3.1.0
│   ├── __main__.py           # Entry: python -m redclaw
│   ├── pentest.py            # 10-phase autonomous pentest runner
│   ├── zeroday_hunter.py     # Zero-day hunting module
│   ├── cli/app.py            # Interactive CLI (Rich + prompt_toolkit)
│   ├── agents/               # Multi-agent system
│   ├── router/               # LLM routing (OpenRouter)
│   ├── memory/               # Task + finding tracker (MemAgent)
│   ├── core/                 # KnowledgeGraph, GuardianRails
│   ├── reporting/            # CausalChain report builder
│   ├── orchestrator/         # Workflow activities
│   └── tooling/              # External tool wrappers
├── Dockerfile                # Kali Linux + tools
├── docker-compose.yml        # Easy deployment
└── README.md                 # This file
```

---

## ⚠️ Legal Disclaimer

RedClaw is for **authorized security testing only**. Always obtain written permission. The developers are not responsible for misuse.

---

## 🛠 Troubleshooting

| Problem | Solution |
|---------|----------|
| `No module named 'aiohttp'` | `pip install aiohttp` |
| `No module named 'redclaw'` | Set `PYTHONPATH=src` |
| API returns 401 | Regenerate key at openrouter.ai/keys |
| Docker API issues on Windows | Use Python directly instead of Docker |
| Connection timeout | Verify target is reachable: `ping <target>` |

---

<p align="center">
  <b>RedClaw V3.1</b> — Built by <a href="https://github.com/Spark-Corporations">SparkStack Systems</a><br>
  <i>"Every system has a weakness. RedClaw finds it."</i>
</p>
