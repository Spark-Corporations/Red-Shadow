---
name: recon
description: Perform passive and active reconnaissance on a target
invocation: user
arguments:
  - name: target
    description: Domain, IP, or organization to recon
    required: true
  - name: mode
    description: "Recon mode: passive|active|full (default: full)"
    required: false
tools:
  - Bash
  - redclaw-nmap
---

# Recon Skill — RedClaw v2.0

## Overview
Perform comprehensive reconnaissance to gather intelligence about a target
before scanning and exploitation phases.

## Workflow

### Phase 1: Passive Recon (No target interaction)
- **WHOIS Lookup** — Domain registration, nameservers, contacts
- **DNS Enumeration** — A, AAAA, MX, NS, TXT, CNAME records
- **Subdomain Discovery** — Certificate transparency logs, DNS brute-force
- **OSINT** — Search engines, Shodan, Censys, social media
- **Technology Fingerprinting** — Wappalyzer, BuiltWith detection

### Phase 2: Active Recon (Target interaction)
- **Ping Sweep** — Host discovery in target range
- **DNS Zone Transfer** — Attempt AXFR
- **Banner Grabbing** — Service identification
- **Web Crawling** — Directory structure, robots.txt, sitemap
- **SSL/TLS Analysis** — Certificate details, cipher suites

## Example Usage
```
/recon example.com
/recon 10.10.10.0/24 active
/recon target.htb passive
```
