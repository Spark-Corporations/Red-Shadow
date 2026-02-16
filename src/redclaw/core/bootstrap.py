"""
RedClaw Bootstrap — Zero-Touch First-Run Setup.

Enterprise-grade auto-setup: when RedClaw starts for the first time,
this module automatically:
  1. Checks all pentesting tool dependencies (doctor)
  2. Installs missing tools (setup-tools)
  3. Ensures Claude Code CLI is available (npm install)
  4. Generates default configs
  5. Creates marker file (~/.redclaw/.initialized)

Subsequent launches skip the bootstrap if marker exists and all tools pass.

Usage (called internally by app.py main):
    from redclaw.core.bootstrap import ensure_ready
    ensure_ready()   # blocks until system is fully ready
"""

from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("redclaw.bootstrap")

# ── Paths ─────────────────────────────────────────────────────────────────────

REDCLAW_HOME = Path.home() / ".redclaw"
MARKER_FILE = REDCLAW_HOME / ".initialized"
CONFIG_DIR = REDCLAW_HOME / "config"
LOGS_DIR = REDCLAW_HOME / "logs"


# ── Rich Console (lazy) ──────────────────────────────────────────────────────

def _get_console():
    """Get a Rich console, or None if Rich is unavailable."""
    try:
        from rich.console import Console
        from rich.theme import Theme
        theme = Theme({
            "info": "dim cyan",
            "success": "bold green",
            "warning": "yellow",
            "error": "bold red",
            "phase": "bold magenta",
            "tool": "bold blue",
        })
        return Console(theme=theme)
    except ImportError:
        return None


def _print(msg: str, console=None, style: str = "") -> None:
    """Print with Rich if available, else plain print."""
    if console:
        console.print(f"[{style}]{msg}[/]" if style else msg)
    else:
        print(msg)


# ── Bootstrap Steps ──────────────────────────────────────────────────────────

def _ensure_dirs() -> None:
    """Create RedClaw home directories."""
    for d in (REDCLAW_HOME, CONFIG_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _check_marker() -> bool:
    """Check if bootstrap has already completed."""
    if not MARKER_FILE.exists():
        return False
    try:
        data = json.loads(MARKER_FILE.read_text(encoding="utf-8"))
        version = data.get("version")
        return version == "2.0.0"
    except (json.JSONDecodeError, KeyError):
        return False


def _write_marker() -> None:
    """Write initialization marker with metadata."""
    data = {
        "version": "2.0.0",
        "initialized_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "platform": platform.system(),
        "python": sys.version.split()[0],
    }
    MARKER_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _install_claude_code(console=None) -> bool:
    """
    Ensure Claude Code CLI is installed.

    Checks for `claude` on PATH. If missing, installs via npm.
    If npm is also missing, installs Node.js first.
    """
    # Already installed?
    if shutil.which("claude"):
        _print("  ✅ Claude Code CLI — installed", console, "success")
        return True

    _print("  📦 Installing Claude Code CLI...", console, "phase")

    # Check for npm
    npm = shutil.which("npm")
    if not npm:
        # Try to install Node.js
        _print("  📦 Node.js not found — installing...", console, "warning")
        if not _install_nodejs(console):
            _print("  ⚠️  Could not install Node.js. Claude Code skin mode unavailable.", console, "warning")
            _print("      Standalone mode will work fine.", console, "info")
            return False
        npm = shutil.which("npm")

    if not npm:
        _print("  ⚠️  npm still not found after Node.js install.", console, "warning")
        return False

    # Install Claude Code
    try:
        result = subprocess.run(
            [npm, "install", "-g", "@anthropic-ai/claude-code"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0 and shutil.which("claude"):
            _print("  ✅ Claude Code CLI — installed successfully", console, "success")
            return True
        else:
            # Try with npx as fallback
            _print("  ⚠️  Global install failed, trying npx...", console, "warning")
            logger.warning(f"npm install failed: {result.stderr[:200]}")
            return False
    except (subprocess.TimeoutExpired, OSError) as e:
        _print(f"  ⚠️  Claude Code install failed: {e}", console, "warning")
        return False


def _install_nodejs(console=None) -> bool:
    """Install Node.js on the current platform."""
    system = platform.system().lower()

    commands = {
        "linux": [
            # Try nvm first, then apt, then snap
            "curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt-get install -y nodejs",
        ],
        "darwin": [
            "brew install node",
        ],
        "windows": [
            # winget is the most reliable on modern Windows
            "winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements",
        ],
    }

    platform_cmds = commands.get(system, [])

    for cmd in platform_cmds:
        try:
            _print(f"    Running: {cmd[:60]}...", console, "info")
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                _print("  ✅ Node.js installed", console, "success")
                return True
        except (subprocess.TimeoutExpired, OSError):
            continue

    return False


def _run_doctor(console=None) -> dict:
    """Run health check and return summary."""
    try:
        from redclaw.tooling.doctor import DoctorReport
        doctor = DoctorReport()
        return doctor.to_dict()
    except Exception as e:
        logger.error(f"Doctor check failed: {e}")
        return {"ready": False, "installed": 0, "total": 10, "missing": 10}


def _run_installer(console=None) -> int:
    """Install all missing tools. Returns number of newly installed tools."""
    try:
        from redclaw.tooling.installer import ToolInstaller
        installer = ToolInstaller(dry_run=False)
        results = installer.install_missing()
        installed_count = sum(1 for r in results if r.success)

        for r in results:
            if r.success:
                _print(f"  ✅ {r.tool.name} — installed via {r.method_used}", console, "success")
            else:
                _print(f"  ⚠️  {r.tool.name} — {r.error or 'failed'}", console, "warning")

        return installed_count
    except Exception as e:
        logger.error(f"Installer failed: {e}")
        _print(f"  ⚠️  Auto-installer error: {e}", console, "warning")
        return 0


# ── Main Bootstrap ────────────────────────────────────────────────────────────

def ensure_ready(force: bool = False, quiet: bool = False) -> dict:
    """
    Ensure RedClaw is fully ready.

    Called automatically on every launch. Fast-paths if already bootstrapped.

    Args:
        force: Run bootstrap even if marker exists
        quiet: Suppress output (background mode)

    Returns:
        Status dict with keys: ready, tools_installed, tools_total,
        claude_code, freshly_bootstrapped
    """
    console = None if quiet else _get_console()

    # Fast path: already initialized
    if not force and _check_marker():
        # Quick verification — just check if tools are still there
        try:
            from redclaw.tooling.doctor import DoctorReport
            doctor = DoctorReport()
            if doctor.is_ready():
                logger.info("Bootstrap: already initialized, tools ready")
                summary = doctor.to_dict()
                return {
                    "ready": True,
                    "tools_installed": summary["installed"],
                    "tools_total": summary["total"],
                    "claude_code": shutil.which("claude") is not None,
                    "freshly_bootstrapped": False,
                }
        except Exception:
            pass
        # If quick check fails, fall through to full bootstrap

    # ── Full bootstrap ────────────────────────────────────────────────────

    _print("\n🔴 RedClaw v2.0 — First Launch Setup\n", console, "phase")
    _print("   Setting up your pentesting environment...\n", console, "info")

    start = time.monotonic()

    # Step 1: Create directories
    _print("  📁 Creating RedClaw home directory...", console, "info")
    _ensure_dirs()

    # Step 2: Health check
    _print("\n  🩺 Checking tool dependencies...\n", console, "phase")
    doctor_result = _run_doctor(console)
    total = doctor_result.get("total", 10)
    installed = doctor_result.get("installed", 0)
    missing = doctor_result.get("missing", 0)

    _print(f"\n  📊 Found {installed}/{total} tools installed", console, "info")

    # Step 3: Install missing tools
    newly_installed = 0
    if missing > 0:
        _print(f"\n  📦 Installing {missing} missing tool(s)...\n", console, "phase")
        newly_installed = _run_installer(console)
        installed += newly_installed

    # Step 4: Install Claude Code CLI
    _print("\n  🔧 Checking Claude Code CLI...", console, "phase")
    has_claude = _install_claude_code(console)

    # Step 5: Write marker
    _write_marker()

    elapsed = time.monotonic() - start

    # Summary
    _print(f"\n{'═' * 50}", console)
    _print(f"  ✅ Bootstrap complete in {elapsed:.1f}s", console, "success")
    _print(f"     Tools: {installed}/{total}", console, "info")
    _print(f"     Claude Code: {'✅' if has_claude else '⚠️  unavailable'}", console, "info")
    _print(f"     Home: {REDCLAW_HOME}", console, "info")
    _print(f"{'═' * 50}\n", console)

    return {
        "ready": True,
        "tools_installed": installed,
        "tools_total": total,
        "claude_code": has_claude,
        "freshly_bootstrapped": True,
    }


def reset_bootstrap() -> None:
    """Reset bootstrap marker (forces re-run on next launch)."""
    if MARKER_FILE.exists():
        MARKER_FILE.unlink()
        logger.info("Bootstrap marker removed — will re-run on next launch")
