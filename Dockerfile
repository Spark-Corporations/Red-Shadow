# ============================================================
# RedClaw V3.1 -- Dockerfile
# Base: Kali Linux (all pentesting tools pre-installed)
# Purpose: Containerized autonomous pentest environment
#
# Build:  docker build -t redclaw .
# Run:    docker run --rm -it -e OPENROUTER_API_KEY=sk-or-v1-... redclaw 192.168.1.83
# Test:   docker run --rm -it redclaw --test
# Shell:  docker run --rm -it --entrypoint bash redclaw
# ============================================================

FROM kalilinux/kali-rolling:latest

LABEL maintainer="SparkStack Systems"
LABEL description="RedClaw V3.1 -- Autonomous Penetration Testing Agent"
LABEL version="3.1.0"

# ── System Setup ──────────────────────────────────────────────────────────
ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# Update and install base packages
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        python3-dev \
        git \
        curl \
        wget \
        jq \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── Install Pentesting Tools (10 MCP servers) ────────────────────────────

# 1. Nmap — Port scanning & service detection
RUN apt-get update && apt-get install -y nmap && rm -rf /var/lib/apt/lists/*

# 2. Masscan — Ultra-fast port scanner
RUN apt-get update && apt-get install -y masscan && rm -rf /var/lib/apt/lists/*

# 3. Nuclei — Template-based vulnerability scanner
RUN curl -sSL https://github.com/projectdiscovery/nuclei/releases/latest/download/nuclei_linux_amd64.zip \
    -o /tmp/nuclei.zip && \
    unzip /tmp/nuclei.zip -d /usr/local/bin/ && \
    chmod +x /usr/local/bin/nuclei && \
    rm /tmp/nuclei.zip && \
    nuclei -update-templates 2>/dev/null || true

# 4. Metasploit Framework
RUN apt-get update && apt-get install -y metasploit-framework && rm -rf /var/lib/apt/lists/*

# 5. SQLMap — SQL injection tool
RUN apt-get update && apt-get install -y sqlmap && rm -rf /var/lib/apt/lists/*

# 6. Hydra — Network login cracker
RUN apt-get update && apt-get install -y hydra && rm -rf /var/lib/apt/lists/*

# 7 & 8. LinPEAS / WinPEAS — Privilege escalation scripts
RUN mkdir -p /opt/peas && \
    curl -sSL https://github.com/peass-ng/PEASS-ng/releases/latest/download/linpeas.sh \
        -o /opt/peas/linpeas.sh && \
    curl -sSL https://github.com/peass-ng/PEASS-ng/releases/latest/download/winPEASany_ofs.exe \
        -o /opt/peas/winpeas.exe && \
    chmod +x /opt/peas/linpeas.sh

# 9. BloodHound — AD attack path analysis (Python collector)
RUN pip3 install --no-cache-dir --break-system-packages bloodhound 2>/dev/null || true

# 10. Custom exploit support (Python dev tools)
RUN pip3 install --no-cache-dir --break-system-packages requests pwntools 2>/dev/null || true

# -- Install RedClaw V3.1 -------------------------------------------------

WORKDIR /opt/redclaw

# Build dependencies for aiohttp C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip python3-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Core Python dependencies (MUST succeed)
RUN pip3 install --no-cache-dir --break-system-packages aiohttp networkx

# Optional: requirements.txt
COPY requirements.txt* ./
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt 2>/dev/null || true

# Copy full project
COPY . .

# Install RedClaw package
RUN pip3 install --no-cache-dir --break-system-packages -e . 2>/dev/null || \
    pip3 install --no-cache-dir --break-system-packages . 2>/dev/null || true

# -- Environment -----------------------------------------------------------

ENV PYTHONPATH=/opt/redclaw/src
ENV PYTHONIOENCODING=utf-8
ENV REDCLAW_LOG_LEVEL="INFO"
ENV PEAS_DIR="/opt/peas"
# OPENROUTER_API_KEY must be provided at runtime via -e or .env

# Working directory for engagements
RUN mkdir -p /root/.redclaw/engagements

# -- Entrypoint ------------------------------------------------------------

# Autonomous pentest: docker run redclaw <TARGET_IP>
# Tests:              docker run redclaw --test
# Interactive CLI:    docker run --entrypoint python3 redclaw -m redclaw.cli.app
ENTRYPOINT ["python3", "src/redclaw/pentest.py"]
CMD []
