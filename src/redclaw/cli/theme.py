"""
RedClaw CLI Theme — Color palette, styled widgets, and Rich theme definitions.

Based on Claude Code's visual style, adapted with RedClaw's red/dark theme.
"""

from __future__ import annotations

from rich.theme import Theme
from prompt_toolkit.styles import Style as PTStyle


# ── Rich Theme ────────────────────────────────────────────────────────────────

REDCLAW_THEME = Theme({
    # Base
    "info": "dim cyan",
    "warning": "yellow",
    "error": "bold red",
    "critical": "bold white on red",
    "success": "bold green",
    "muted": "dim white",
    "accent": "bold #ff4444",

    # RedClaw branding
    "brand": "bold #ff4444",
    "brand.dim": "#cc3333",
    "brand.border": "#ff4444",
    "version": "#ff8888",
    "codename": "#cc6666",

    # Phase indicators
    "phase": "bold magenta",
    "phase.recon": "bold blue",
    "phase.scan": "bold cyan",
    "phase.vuln": "bold yellow",
    "phase.exploit": "bold red",
    "phase.post": "bold magenta",
    "phase.report": "bold green",

    # Finding severities
    "finding.critical": "bold white on red",
    "finding.high": "bold red",
    "finding.medium": "yellow",
    "finding.low": "cyan",
    "finding.info": "dim white",

    # Components
    "tool": "bold blue",
    "agent": "bold cyan",
    "model": "bold #ff8888",
    "provider": "bold #88ff88",
    "cost": "bold #ffaa00",

    # Status bar
    "bar.tip": "bold #ffaa00",
    "bar.key": "bold white",
    "bar.text": "dim white",
    "bar.back": "on #1a1a2e",

    # Welcome panel
    "welcome.border": "#ff4444",
    "welcome.title": "bold #ff4444",
    "welcome.section": "bold #ffaa00",
    "welcome.text": "#cccccc",
    "welcome.link": "bold cyan underline",
})


# ── Prompt Toolkit Style ─────────────────────────────────────────────────────

PROMPT_STYLE = PTStyle.from_dict({
    "prompt": "#ff4444 bold",
    "prompt.arrow": "#ff6666",
    "input": "#ffffff",
    "completion-menu.completion": "bg:#2a2a3a #ffffff",
    "completion-menu.completion.current": "bg:#ff4444 #ffffff",
    "scrollbar.background": "bg:#1a1a2e",
    "scrollbar.button": "bg:#ff4444",
})


# ── Color Constants ──────────────────────────────────────────────────────────

class Colors:
    """RedClaw color constants."""
    RED = "#ff4444"
    RED_DIM = "#cc3333"
    RED_LIGHT = "#ff8888"
    DARK_BG = "#0c0c1d"
    DARK_SURFACE = "#1a1a2e"
    WHITE = "#ffffff"
    GRAY = "#cccccc"
    YELLOW = "#ffaa00"
    GREEN = "#44ff44"
    CYAN = "#44ffff"
    BLUE = "#4488ff"
