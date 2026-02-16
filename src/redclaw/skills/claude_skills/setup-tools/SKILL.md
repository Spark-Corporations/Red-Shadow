---
name: setup-tools
description: Auto-detect and install missing pentesting tool dependencies
invocation: user
arguments:
  - name: mode
    description: "Install mode: auto|interactive|dry-run (default: interactive)"
    required: false
tools:
  - Bash
---

# Setup Tools Skill — RedClaw v2.0

## Overview
Automatically detect and install all missing pentesting tool dependencies
on the current system.

## Workflow

1. **Detection** — Scan PATH for all 10 required tool binaries
2. **OS Detection** — Identify platform and available package managers
3. **Install Plan** — Generate ordered install commands
4. **Execution** — Run installs (with user confirmation unless `auto` mode)

## Supported Platforms

| Platform | Package Manager | Tools Available |
|----------|----------------|-----------------|
| Kali Linux | apt | All 10 (pre-installed) |
| Debian/Ubuntu | apt | Most via apt |
| Fedora/RHEL | dnf | Most via dnf |
| Arch Linux | pacman | Most via pacman |
| macOS | brew | Most via Homebrew |
| Windows | choco/winget | Limited (use Docker) |

## Install Methods

| Tool | Primary | Fallback |
|------|---------|----------|
| Nmap | apt/brew/choco | — |
| Masscan | apt/brew | Build from source |
| Nuclei | go install | Binary download |
| Metasploit | Official installer | Docker |
| SQLMap | pip | apt/brew |
| Hydra | apt/brew | Build from source |
| LinPEAS | curl download | — |
| BloodHound | pip | — |

## Example Usage
```
/setup-tools
/setup-tools dry-run
/setup-tools auto
```
