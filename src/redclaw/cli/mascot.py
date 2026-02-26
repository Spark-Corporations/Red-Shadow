"""
RedClaw CLI Mascot — Red horned demon pixel art ASCII art.

Replaces Claude Code's pig mascot with RedClaw's signature demon.
Displays alongside version info in the welcome panel.
"""

from __future__ import annotations


# ── Red Horned Demon Mascot (pixel art style, like Claude Code's pig) ────────

DEMON_MASCOT = r"""
[bold red]    /\  /\[/]
[bold red]   {  \/  }[/]
[bold red]   {  ◉◉  }[/]
[bold red]    \ [bold yellow]▼▼[/bold yellow] /[/]
[bold red]   .-'--'-.  [/]
[bold red]  / [bold #ff8888]||  ||[/bold #ff8888] \ [/]
[bold red]  \_[bold #ff8888]||__||[/bold #ff8888]_/[/]
"""

# Compact version for narrow terminals
DEMON_MASCOT_SMALL = r"""
[bold red]  /\ /\[/]
[bold red]  {◉◉}[/]
[bold red]  \[bold yellow]▼▼[/bold yellow]/[/]
[bold red]  /||\[/]
"""

# Ultra-compact for very narrow terminals
DEMON_MASCOT_TINY = "[bold red]👹[/]"


def get_mascot(width: int = 80) -> str:
    """Get the appropriate mascot size for terminal width."""
    if width >= 80:
        return DEMON_MASCOT
    elif width >= 40:
        return DEMON_MASCOT_SMALL
    else:
        return DEMON_MASCOT_TINY


def get_version_badge() -> str:
    """Get styled version badge text."""
    try:
        from redclaw import __version__, __codename__
    except ImportError:
        __version__ = "3.1.0"
        __codename__ = "Red Shadow"

    return (
        f"[bold #ff8888]RedClaw v{__version__}[/] · "
        f"[dim #cc6666]{__codename__}[/]"
    )


def get_model_badge(model_name: str = "OpenRouter", billing: str = "API") -> str:
    """Get styled model info badge (like Claude Code's 'Sonnet 4.5 · API Usage Billing')."""
    return f"[bold #ff8888]{model_name}[/] · [dim]{billing}[/]"
