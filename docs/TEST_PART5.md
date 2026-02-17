                                                                                                                                                                                                                                           
┌──(venv)─(root㉿linux)-[/home/sherlock/Desktop/Red-Shadow]
└─# redclaw skin                                                  
2026-02-16 18:09:39,072 [redclaw.bootstrap] INFO: Bootstrap: already initialized, tools ready
2026-02-16 18:09:42,350 [redclaw.cli] INFO: Bootstrap: {'ready': True, 'tools_installed': 10, 'tools_total': 10, 'claude_code': True, 'freshly_bootstrapped': False}
2026-02-16 18:09:42,355 [redclaw.claude_skin.launcher] INFO: Temp config dir: /tmp/redclaw_skin_86w1lg0m
2026-02-16 18:09:42,355 [redclaw.claude_skin.launcher] INFO: System prompt written to /tmp/redclaw_skin_86w1lg0m/system_prompt.md
2026-02-16 18:09:42,355 [redclaw.claude_skin.launcher] INFO: Hooks config: /tmp/redclaw_skin_86w1lg0m/hooks.json
2026-02-16 18:09:42,355 [redclaw.claude_skin.launcher] INFO: MCP config: /tmp/redclaw_skin_86w1lg0m/mcp_config.json
2026-02-16 18:09:42,356 [redclaw.claude_skin.launcher] INFO: Reverse proxy started (PID 81446) → https://0b2f-34-29-72-116.ngrok-free.app on port 8080
2026-02-16 18:09:42,356 [redclaw.claude_skin.launcher] INFO: Set hasCompletedOnboarding=true in ~/.claude.json
2026-02-16 18:09:42,358 [redclaw.claude_skin.launcher] INFO: Set apiKeyHelper in /root/.claude/settings.json
🔄 Reverse proxy active on port 8080
   Routing Claude Code → https://0b2f-34-29-72-116.ngrok-free.app
   🔑 Login bypass: API key + onboarding skip configured

2026-02-16 18:09:42,358 [redclaw.claude_skin.launcher] INFO: Running as root — using 'plan' permission mode (bypassPermissions blocked for root)
🔴 Launching Claude Code with RedClaw skin...
   System Prompt: 4053 chars
   Hooks: /tmp/redclaw_skin_86w1lg0m/hooks.json
   MCP Servers: 10 pentesting tools

                                                                                                                                                                                                                                            
╭─── Claude Code v2.1.42 ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│                                       │ Tips for getting started                                                                                                                                                                         │
│             Welcome back!             │ Run /init to create a CLAUDE.md file with instructions for Claude                                                                                                                                │
│                                       │ ─────────────────────────────────────────────────────────────────                                                                                                                                │
│                                       │ Recent activity                                                                                                                                                                                  │
│                ▐▛███▜▌                │ No recent activity                                                                                                                                                                               │
│               ▝▜█████▛▘               │                                                                                                                                                                                                  │
│                 ▘▘ ▝▝                 │                                                                                                                                                                                                  │
│    Sonnet 4.5 · API Usage Billing     │                                                                                                                                                                                                  │
│   /home/sherlock/Desktop/Red-Shadow   │                                                                                                                                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
                                                                                                                                                                                                                                            
  /model to try Opus 4.6                                                                                                                                                                                                                    
                                                                                                                                                                                                                                            
❯ Unknown skill: link                                                                                                                                                                                                                       
                                                  
❯ hello                                                                                                                                                                                                                                     
  ⎿  Interrupted · What should Claude do instead?                                                                                                                                                                                         
u                                                                                                                                                                                                                                           
Resume this session with:                                                                                                                                                                                                                   
claude --resume 89a05803-286f-4cbd-85e8-7e42fa50eb8d                                                                                                                                                                                        
u2026-02-16 18:10:54,256 [redclaw.claude_skin.launcher] INFO: Reverse proxy stopped                                                                                                                                                         
2026-02-16 18:10:54,257 [redclaw.claude_skin.launcher] INFO: Cleaned up temp dir: /tmp/redclaw_skin_86w1lg0m                                                                                                                                
                                                                                                                                                                                                                                            
┌──(venv)─(root㉿linux)-[/home/sherlock/Desktop/Red-Shadow]
└─# redclaw         
2026-02-16 18:11:01,528 [redclaw.bootstrap] INFO: Bootstrap: already initialized, tools ready
2026-02-16 18:11:04,858 [redclaw.cli] INFO: Bootstrap: {'ready': True, 'tools_installed': 10, 'tools_total': 10, 'claude_code': True, 'freshly_bootstrapped': False}
2026-02-16 18:11:04,999 [redclaw.core.guardian] INFO: GuardianRails initialized: scope=0 targets, rate_limit=100/min
2026-02-16 18:11:04,999 [redclaw.openclaw_bridge.runtime] INFO: OpenClawRuntime created: endpoint=https://0b2f-34-29-72-116.ngrok-free.app, model=phi-4
2026-02-16 18:11:04,999 [redclaw.openclaw_bridge.tool_bridge] INFO: ToolBridge initialized
2026-02-16 18:11:04,999 [redclaw.mcp_servers.base] INFO: MCP Server 'nmap' initialized
2026-02-16 18:11:04,999 [redclaw.mcp_servers.base] INFO: MCP Server 'masscan' initialized
2026-02-16 18:11:04,999 [redclaw.mcp_servers.base] INFO: MCP Server 'nuclei' initialized
2026-02-16 18:11:04,999 [redclaw.mcp_servers.base] INFO: MCP Server 'metasploit' initialized
2026-02-16 18:11:04,999 [redclaw.mcp_servers.base] INFO: MCP Server 'sqlmap' initialized
2026-02-16 18:11:04,999 [redclaw.mcp_servers.base] INFO: MCP Server 'hydra' initialized
2026-02-16 18:11:04,999 [redclaw.mcp_servers.base] INFO: MCP Server 'bloodhound' initialized
2026-02-16 18:11:04,999 [redclaw.mcp_servers.base] INFO: MCP Server 'linpeas' initialized
2026-02-16 18:11:04,999 [redclaw.mcp_servers.base] INFO: MCP Server 'winpeas' initialized
2026-02-16 18:11:04,999 [redclaw.mcp_servers.base] INFO: MCP Server 'custom_exploit' initialized
2026-02-16 18:11:04,999 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: nmap
2026-02-16 18:11:04,999 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: masscan
2026-02-16 18:11:04,999 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: nuclei
2026-02-16 18:11:04,999 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: metasploit
2026-02-16 18:11:04,999 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: sqlmap
2026-02-16 18:11:04,999 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: hydra
2026-02-16 18:11:04,999 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: bloodhound
2026-02-16 18:11:04,999 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: linpeas
2026-02-16 18:11:04,999 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: winpeas
2026-02-16 18:11:04,999 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: custom_exploit
2026-02-16 18:11:04,999 [redclaw.openclaw_bridge.runtime] INFO: ToolBridge registered: 10 tools available
2026-02-16 18:11:05,000 [redclaw.core.state] INFO: StateManager initialized: output_dir=output
2026-02-16 18:11:05,000 [redclaw.cli] INFO: RedClaw CLI initialized


  ██████╗ ███████╗██████╗  ██████╗██╗      █████╗ ██╗    ██╗
  ██╔══██╗██╔════╝██╔══██╗██╔════╝██║     ██╔══██╗██║    ██║
  ██████╔╝█████╗  ██║  ██║██║     ██║     ███████║██║ █╗ ██║
  ██╔══██╗██╔══╝  ██║  ██║██║     ██║     ██╔══██║██║███╗██║
  ██║  ██║███████╗██████╔╝╚██████╗███████╗██║  ██║╚███╔███╔╝
  ╚═╝  ╚═╝╚══════╝╚═════╝  ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝
  v2.0.0 "Red Shadow" — Autonomous Penetration Testing Agent
  Powered by OpenClaw Runtime + Kaggle Phi-4

╭───────────────────────────────────────────────────────────────────────────────────────────────────────────── System Status ──────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ ┌─────────────────┬──┐                                                                                                                                                                                                                   │
│ │OpenClaw Runtime │ ✓│                                                                                                                                                                                                                   │
│ │State Manager    │ ✓│                                                                                                                                                                                                                   │
│ │Config Manager   │ ○│                                                                                                                                                                                                                   │
│ │GuardianRails    │ ✓│                                                                                                                                                                                                                   │
│ └─────────────────┴──┘                                                                                                                                                                                                                   │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯

Type a command or natural language instruction. Use /help for available commands.

redclaw ❯ /link https://aa7f-136-112-80-28.ngrok-free.app
✅ LLM backend URL updated:
   https://aa7f-136-112-80-28.ngrok-free.app
   Saved to /root/.redclaw/link.txt
redclaw ❯ hello

◆ Processing: hello

Traceback (most recent call last):
  File "/home/sherlock/Desktop/Red-Shadow/venv/bin/redclaw", line 7, in <module>
    sys.exit(main())
             ~~~~^^
  File "/home/sherlock/Desktop/Red-Shadow/src/redclaw/cli/app.py", line 811, in main
    cli.run()
    ~~~~~~~^^
  File "/home/sherlock/Desktop/Red-Shadow/src/redclaw/cli/app.py", line 167, in run
    self._handle_natural_language(user_input)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^
  File "/home/sherlock/Desktop/Red-Shadow/src/redclaw/cli/app.py", line 559, in _handle_natural_language
    for f in state.findings
             ^^^^^^^^^^^^^^
  File "/home/sherlock/Desktop/Red-Shadow/venv/lib/python3.13/site-packages/pydantic/main.py", line 1026, in __getattr__
    raise AttributeError(f'{type(self).__name__!r} object has no attribute {item!r}')
AttributeError: 'PipelineState' object has no attribute 'findings'
                                                                                                                                                                                                                                            
┌──(venv)─(root㉿linux)-[/home/sherlock/Desktop/Red-Shadow]
└─# redclaw 
2026-02-16 18:11:28,076 [redclaw.bootstrap] INFO: Bootstrap: already initialized, tools ready
2026-02-16 18:11:31,405 [redclaw.cli] INFO: Bootstrap: {'ready': True, 'tools_installed': 10, 'tools_total': 10, 'claude_code': True, 'freshly_bootstrapped': False}
2026-02-16 18:11:31,540 [redclaw.core.guardian] INFO: GuardianRails initialized: scope=0 targets, rate_limit=100/min
2026-02-16 18:11:31,540 [redclaw.openclaw_bridge.runtime] INFO: OpenClawRuntime created: endpoint=https://0b2f-34-29-72-116.ngrok-free.app, model=phi-4
2026-02-16 18:11:31,540 [redclaw.openclaw_bridge.tool_bridge] INFO: ToolBridge initialized
2026-02-16 18:11:31,540 [redclaw.mcp_servers.base] INFO: MCP Server 'nmap' initialized
2026-02-16 18:11:31,540 [redclaw.mcp_servers.base] INFO: MCP Server 'masscan' initialized
2026-02-16 18:11:31,540 [redclaw.mcp_servers.base] INFO: MCP Server 'nuclei' initialized
2026-02-16 18:11:31,540 [redclaw.mcp_servers.base] INFO: MCP Server 'metasploit' initialized
2026-02-16 18:11:31,540 [redclaw.mcp_servers.base] INFO: MCP Server 'sqlmap' initialized
2026-02-16 18:11:31,540 [redclaw.mcp_servers.base] INFO: MCP Server 'hydra' initialized
2026-02-16 18:11:31,540 [redclaw.mcp_servers.base] INFO: MCP Server 'bloodhound' initialized
2026-02-16 18:11:31,540 [redclaw.mcp_servers.base] INFO: MCP Server 'linpeas' initialized
2026-02-16 18:11:31,540 [redclaw.mcp_servers.base] INFO: MCP Server 'winpeas' initialized
2026-02-16 18:11:31,540 [redclaw.mcp_servers.base] INFO: MCP Server 'custom_exploit' initialized
2026-02-16 18:11:31,540 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: nmap
2026-02-16 18:11:31,540 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: masscan
2026-02-16 18:11:31,540 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: nuclei
2026-02-16 18:11:31,540 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: metasploit
2026-02-16 18:11:31,540 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: sqlmap
2026-02-16 18:11:31,540 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: hydra
2026-02-16 18:11:31,540 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: bloodhound
2026-02-16 18:11:31,540 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: linpeas
2026-02-16 18:11:31,540 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: winpeas
2026-02-16 18:11:31,540 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: custom_exploit
2026-02-16 18:11:31,540 [redclaw.openclaw_bridge.runtime] INFO: ToolBridge registered: 10 tools available
2026-02-16 18:11:31,540 [redclaw.core.state] INFO: StateManager initialized: output_dir=output
2026-02-16 18:11:31,541 [redclaw.cli] INFO: RedClaw CLI initialized


  ██████╗ ███████╗██████╗  ██████╗██╗      █████╗ ██╗    ██╗
  ██╔══██╗██╔════╝██╔══██╗██╔════╝██║     ██╔══██╗██║    ██║
  ██████╔╝█████╗  ██║  ██║██║     ██║     ███████║██║ █╗ ██║
  ██╔══██╗██╔══╝  ██║  ██║██║     ██║     ██╔══██║██║███╗██║
  ██║  ██║███████╗██████╔╝╚██████╗███████╗██║  ██║╚███╔███╔╝
  ╚═╝  ╚═╝╚══════╝╚═════╝  ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝
  v2.0.0 "Red Shadow" — Autonomous Penetration Testing Agent
  Powered by OpenClaw Runtime + Kaggle Phi-4

╭───────────────────────────────────────────────────────────────────────────────────────────────────────────── System Status ──────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ ┌─────────────────┬──┐                                                                                                                                                                                                                   │
│ │OpenClaw Runtime │ ✓│                                                                                                                                                                                                                   │
│ │State Manager    │ ✓│                                                                                                                                                                                                                   │
│ │Config Manager   │ ○│                                                                                                                                                                                                                   │
│ │GuardianRails    │ ✓│                                                                                                                                                                                                                   │
│ └─────────────────┴──┘                                                                                                                                                                                                                   │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯

Type a command or natural language instruction. Use /help for available commands.

redclaw ❯ /status
Traceback (most recent call last):
  File "/home/sherlock/Desktop/Red-Shadow/venv/bin/redclaw", line 7, in <module>
    sys.exit(main())
             ~~~~^^
  File "/home/sherlock/Desktop/Red-Shadow/src/redclaw/cli/app.py", line 811, in main
    cli.run()
    ~~~~~~~^^
  File "/home/sherlock/Desktop/Red-Shadow/src/redclaw/cli/app.py", line 165, in run
    self._handle_slash_command(user_input)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^
  File "/home/sherlock/Desktop/Red-Shadow/src/redclaw/cli/app.py", line 207, in _handle_slash_command
    handler(args)
    ~~~~~~~^^^^^^
  File "/home/sherlock/Desktop/Red-Shadow/src/redclaw/cli/app.py", line 228, in _cmd_status
    panel_content.append(f"[info]Status[/]: {state.status}")
                                             ^^^^^^^^^^^^
  File "/home/sherlock/Desktop/Red-Shadow/venv/lib/python3.13/site-packages/pydantic/main.py", line 1026, in __getattr__
    raise AttributeError(f'{type(self).__name__!r} object has no attribute {item!r}')
AttributeError: 'PipelineState' object has no attribute 'status'
                                                                                                                                                                                                                                            
┌──(venv)─(root㉿linux)-[/home/sherlock/Desktop/Red-Shadow]
└─# redclaw 
2026-02-16 18:11:43,175 [redclaw.bootstrap] INFO: Bootstrap: already initialized, tools ready
2026-02-16 18:11:46,350 [redclaw.cli] INFO: Bootstrap: {'ready': True, 'tools_installed': 10, 'tools_total': 10, 'claude_code': True, 'freshly_bootstrapped': False}
2026-02-16 18:11:46,475 [redclaw.core.guardian] INFO: GuardianRails initialized: scope=0 targets, rate_limit=100/min
2026-02-16 18:11:46,475 [redclaw.openclaw_bridge.runtime] INFO: OpenClawRuntime created: endpoint=https://0b2f-34-29-72-116.ngrok-free.app, model=phi-4
2026-02-16 18:11:46,475 [redclaw.openclaw_bridge.tool_bridge] INFO: ToolBridge initialized
2026-02-16 18:11:46,475 [redclaw.mcp_servers.base] INFO: MCP Server 'nmap' initialized
2026-02-16 18:11:46,475 [redclaw.mcp_servers.base] INFO: MCP Server 'masscan' initialized
2026-02-16 18:11:46,476 [redclaw.mcp_servers.base] INFO: MCP Server 'nuclei' initialized
2026-02-16 18:11:46,476 [redclaw.mcp_servers.base] INFO: MCP Server 'metasploit' initialized
2026-02-16 18:11:46,476 [redclaw.mcp_servers.base] INFO: MCP Server 'sqlmap' initialized
2026-02-16 18:11:46,476 [redclaw.mcp_servers.base] INFO: MCP Server 'hydra' initialized
2026-02-16 18:11:46,476 [redclaw.mcp_servers.base] INFO: MCP Server 'bloodhound' initialized
2026-02-16 18:11:46,476 [redclaw.mcp_servers.base] INFO: MCP Server 'linpeas' initialized
2026-02-16 18:11:46,476 [redclaw.mcp_servers.base] INFO: MCP Server 'winpeas' initialized
2026-02-16 18:11:46,476 [redclaw.mcp_servers.base] INFO: MCP Server 'custom_exploit' initialized
2026-02-16 18:11:46,476 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: nmap
2026-02-16 18:11:46,476 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: masscan
2026-02-16 18:11:46,476 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: nuclei
2026-02-16 18:11:46,476 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: metasploit
2026-02-16 18:11:46,476 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: sqlmap
2026-02-16 18:11:46,476 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: hydra
2026-02-16 18:11:46,476 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: bloodhound
2026-02-16 18:11:46,476 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: linpeas
2026-02-16 18:11:46,476 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: winpeas
2026-02-16 18:11:46,476 [redclaw.openclaw_bridge.tool_bridge] INFO: Registered MCP server: custom_exploit
2026-02-16 18:11:46,476 [redclaw.openclaw_bridge.runtime] INFO: ToolBridge registered: 10 tools available
2026-02-16 18:11:46,476 [redclaw.core.state] INFO: StateManager initialized: output_dir=output
2026-02-16 18:11:46,476 [redclaw.cli] INFO: RedClaw CLI initialized


  ██████╗ ███████╗██████╗  ██████╗██╗      █████╗ ██╗    ██╗
  ██╔══██╗██╔════╝██╔══██╗██╔════╝██║     ██╔══██╗██║    ██║
  ██████╔╝█████╗  ██║  ██║██║     ██║     ███████║██║ █╗ ██║
  ██╔══██╗██╔══╝  ██║  ██║██║     ██║     ██╔══██║██║███╗██║
  ██║  ██║███████╗██████╔╝╚██████╗███████╗██║  ██║╚███╔███╔╝
  ╚═╝  ╚═╝╚══════╝╚═════╝  ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝
  v2.0.0 "Red Shadow" — Autonomous Penetration Testing Agent
  Powered by OpenClaw Runtime + Kaggle Phi-4

╭───────────────────────────────────────────────────────────────────────────────────────────────────────────── System Status ──────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ ┌─────────────────┬──┐                                                                                                                                                                                                                   │
│ │OpenClaw Runtime │ ✓│                                                                                                                                                                                                                   │
│ │State Manager    │ ✓│                                                                                                                                                                                                                   │
│ │Config Manager   │ ○│                                                                                                                                                                                                                   │
│ │GuardianRails    │ ✓│                                                                                                                                                                                                                   │
│ └─────────────────┴──┘                                                                                                                                                                                                                   │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯

Type a command or natural language instruction. Use /help for available commands.

redclaw ❯ /help
                         RedClaw Commands                         
┏━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Command      ┃ Description                                     ┃
┡━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ /help        │ Show available commands                         │
│ /status      │ Show pipeline and agent status                  │
│ /config      │ Show current engagement configuration           │
│ /scan        │ Start a scan on configured targets              │
│ /exploit     │ Begin exploitation phase (requires approval)    │
│ /report      │ Generate engagement report                      │
│ /findings    │ Show all findings                               │
│ /tools       │ List available MCP tool servers                 │
│ /sessions    │ Show active sessions                            │
│ /guardian    │ Show GuardianRails statistics                   │
│ /checkpoint  │ Save current state to disk                      │
│ /resume      │ Resume from last checkpoint                     │
│ /proxy       │ Start the Anthropic→OpenAI reverse proxy        │
│ /agent       │ Show agent loop stats and LLM provider health   │
│ /skin        │ Launch Claude Code with RedClaw pentesting skin │
│ /doctor      │ Health-check all tool dependencies              │
│ /setup-tools │ Auto-install missing pentesting tools           │
│ /link        │ View/update ngrok LLM backend URL               │
│ /clear       │ Clear the terminal                              │
│ /quit        │ Exit RedClaw                                    │
└──────────────┴─────────────────────────────────────────────────┘
redclaw ❯ 

