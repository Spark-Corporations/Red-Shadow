"""
Claude Code CLI Skin — Layer 4: Presentation.

Transforms Claude Code's TUI into a RedClaw pentesting terminal by injecting:
  - System prompt (pentesting identity + tool catalog)
  - Hooks (SessionStart, PreToolUse, PostToolUse, Stop)
  - MCP server config (10 pentesting tool servers)
  - Skills (8 slash commands: /scan, /exploit, /report, /recon, /status, /tools, /doctor, /setup-tools)

Architecture:
  Claude Code CLI ──API──▶ Reverse Proxy ──▶ Kaggle Phi-4 (Layer 1)
       │                                            │
       └── hooks/skills/mcp ──▶ RedClaw backend ◀───┘
"""

from .launcher import ClaudeCodeLauncher
from .hooks import HookGenerator
from .system_prompt import SystemPromptBuilder
from .mcp_config import MCPConfigGenerator

__all__ = [
    "ClaudeCodeLauncher",
    "HookGenerator",
    "SystemPromptBuilder",
    "MCPConfigGenerator",
]
