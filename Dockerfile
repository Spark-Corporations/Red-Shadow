# ────────────────────────────────────────────────────────────────────────────
# RedClaw v2.0 — Dockerfile
# Base: Kali Linux (all pentesting tools pre-installed)
# Purpose: Containerized pentesting environment with all 10 tools bundled
# ────────────────────────────────────────────────────────────────────────────

FROM kalilinux/kali-rolling:latest

LABEL maintainer="SparkStack Systems"
LABEL description="RedClaw v2.0 — Autonomous Penetration Testing Agent"
LABEL version="2.0.0"

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
RUN pip3 install --no-cache-dir bloodhound 2>/dev/null || true

# 10. Custom exploit support (Python dev tools)
RUN pip3 install --no-cache-dir requests pwntools 2>/dev/null || true

# ── Install RedClaw ──────────────────────────────────────────────────────

WORKDIR /opt/redclaw

# Copy project files
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .

# Install RedClaw package in development mode
RUN pip3 install --no-cache-dir -e . 2>/dev/null || pip3 install --no-cache-dir .

# ── Environment ──────────────────────────────────────────────────────────

# Default LLM endpoint (override with docker-compose or -e)
ENV REDCLAW_LLM_URL="https://0b2f-34-29-72-116.ngrok-free.app"
ENV REDCLAW_LLM_MODEL="phi-4"
ENV REDCLAW_LOG_LEVEL="INFO"
ENV PEAS_DIR="/opt/peas"

# Working directory for engagements
RUN mkdir -p /engagements
WORKDIR /engagements

# Expose proxy port
EXPOSE 8080

# ── Entrypoint ───────────────────────────────────────────────────────────

# Default: launch interactive CLI
ENTRYPOINT ["python3", "-m", "redclaw.cli.app"]

# Allow subcommands: `docker run redclaw doctor`, `docker run redclaw skin`
CMD []
