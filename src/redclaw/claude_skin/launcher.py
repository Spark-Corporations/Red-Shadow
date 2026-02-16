"""
ClaudeCodeLauncher — Orchestrates launching Claude Code with RedClaw injected.

Architecture (Layer 4: Presentation):
  ┌─────────────────────────────────────────────────────┐
  │  Claude Code CLI (TUI)                              │
  │    --system-prompt  → RedClaw pentesting identity   │
  │    --hooks          → GuardianRails + state mgmt    │
  │    --mcp-config     → 10 pentesting tool servers    │
  │    skills/          → /scan, /exploit, /report ...  │
  │                                                     │
  │  ┌─ Reverse Proxy (localhost:8080) ──────────────┐  │
  │  │  Anthropic API ←→ OpenAI API translation      │  │
  │  │  Routes to Kaggle Phi-4 via ngrok             │  │
  │  └───────────────────────────────────────────────-┘  │
  └─────────────────────────────────────────────────────┘

Usage:
    # From CLI
    redclaw skin

    # From Python
    launcher = ClaudeCodeLauncher()
    launcher.launch()
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

from .hooks import HookGenerator
from .mcp_config import MCPConfigGenerator
from .system_prompt import SystemPromptBuilder

logger = logging.getLogger("redclaw.claude_skin.launcher")


class ClaudeCodeLauncher:
    """
    Launch Claude Code CLI with RedClaw's pentesting skin injected.

    Steps:
      1. Check if `claude` CLI is installed
      2. Generate temporary config files (hooks, MCP, system prompt)
      3. Optionally start the reverse proxy (Anthropic→OpenAI)
      4. Launch `claude` with all injected flags
      5. Cleanup temp files on exit
    """

    # ── Configuration ─────────────────────────────────────────────────────

    CLAUDE_BINARY = "claude"  # Must be on PATH
    SKILLS_DIR = Path(__file__).parent.parent / "skills" / "claude_skills"

    def __init__(
        self,
        targets: Optional[list[str]] = None,
        scope: Optional[list[str]] = None,
        engagement_name: str = "RedClaw Engagement",
        proxy_port: int = 8080,
        enable_proxy: bool = True,
        enable_guardian: bool = True,
    ):
        self.targets = targets or []
        self.scope = scope or []
        self.engagement_name = engagement_name
        self.proxy_port = proxy_port
        self.enable_proxy = enable_proxy
        self.enable_guardian = enable_guardian

        # Temp directory for generated configs
        self._temp_dir: Optional[Path] = None
        self._proxy_process: Optional[subprocess.Popen] = None

    # ── Pre-flight Checks ─────────────────────────────────────────────────

    def check_claude_installed(self) -> bool:
        """Check if Claude Code CLI is available on PATH."""
        return shutil.which(self.CLAUDE_BINARY) is not None

    def check_proxy_needed(self) -> bool:
        """Check if the reverse proxy is needed (no Anthropic key set)."""
        return not os.environ.get("ANTHROPIC_API_KEY")

    # ── Config Generation ─────────────────────────────────────────────────

    def _create_temp_dir(self) -> Path:
        """Create temporary directory for generated configs."""
        self._temp_dir = Path(tempfile.mkdtemp(prefix="redclaw_skin_"))
        logger.info(f"Temp config dir: {self._temp_dir}")
        return self._temp_dir

    def _generate_system_prompt(self) -> str:
        """Generate the RedClaw system prompt."""
        builder = SystemPromptBuilder(
            targets=self.targets,
            scope=self.scope,
            engagement_name=self.engagement_name,
        )
        prompt = builder.build()

        # Also write to file for debugging
        if self._temp_dir:
            prompt_file = self._temp_dir / "system_prompt.md"
            prompt_file.write_text(prompt, encoding="utf-8")
            logger.info(f"System prompt written to {prompt_file}")

        return prompt

    def _generate_hooks_config(self) -> Path:
        """Generate hooks JSON config and return path."""
        generator = HookGenerator(
            guardian_enabled=self.enable_guardian,
            auto_checkpoint=True,
            health_check_on_start=True,
        )
        hooks_file = self._temp_dir / "hooks.json"
        generator.write_to_file(hooks_file)
        logger.info(f"Hooks config: {hooks_file}")
        return hooks_file

    def _generate_mcp_config(self) -> Path:
        """Generate MCP server config and return path."""
        generator = MCPConfigGenerator(
            env_vars={
                "REDCLAW_LOG_LEVEL": os.environ.get("REDCLAW_LOG_LEVEL", "INFO"),
            },
        )
        mcp_file = self._temp_dir / "mcp_config.json"
        generator.write_to_file(mcp_file)
        logger.info(f"MCP config: {mcp_file}")
        return mcp_file

    # ── Proxy ─────────────────────────────────────────────────────────────

    def _start_proxy(self) -> bool:
        """Start the reverse proxy in a background process."""
        try:
            backend_url = os.environ.get(
                "REDCLAW_LLM_URL",
                "https://0b2f-34-29-72-116.ngrok-free.app"
            )
            self._proxy_process = subprocess.Popen(
                [
                    sys.executable, "-m", "redclaw.proxy.server",
                    "--backend", backend_url,
                    "--port", str(self.proxy_port),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            logger.info(
                f"Reverse proxy started (PID {self._proxy_process.pid}) "
                f"→ {backend_url} on port {self.proxy_port}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to start proxy: {e}")
            return False

    def _stop_proxy(self) -> None:
        """Stop the background reverse proxy."""
        if self._proxy_process:
            self._proxy_process.terminate()
            try:
                self._proxy_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proxy_process.kill()
            logger.info("Reverse proxy stopped")
            self._proxy_process = None

    # ── Launch ────────────────────────────────────────────────────────────

    def launch(self) -> int:
        """
        Launch Claude Code with RedClaw skin.

        Returns:
            Exit code (0 = success)
        """
        # Auto-install Claude Code if missing (enterprise zero-touch)
        if not self.check_claude_installed():
            print("📦 Claude Code CLI not found — installing automatically...")
            try:
                from ..core.bootstrap import _install_claude_code
                if not _install_claude_code():
                    print(
                        "\n⚠️  Claude Code CLI could not be installed automatically.\n"
                        "   Falling back to RedClaw standalone mode.\n"
                        "   Run:  redclaw   (without 'skin')\n"
                    )
                    return 1
            except Exception as e:
                print(f"\n⚠️  Auto-install failed: {e}")
                print("   Use standalone mode:  redclaw\n")
                return 1

        # Create temp directory
        self._create_temp_dir()

        try:
            # Generate configs
            system_prompt = self._generate_system_prompt()
            hooks_file = self._generate_hooks_config()
            mcp_file = self._generate_mcp_config()

            # Start proxy if needed
            env = os.environ.copy()

            # Load saved ngrok URL if not set via environment
            if "REDCLAW_LLM_URL" not in env:
                link_file = Path.home() / ".redclaw" / "link.txt"
                if link_file.exists():
                    saved_url = link_file.read_text().strip()
                    if saved_url:
                        env["REDCLAW_LLM_URL"] = saved_url
                        logger.info(f"Loaded saved LLM URL: {saved_url}")

            if self.enable_proxy and self.check_proxy_needed():
                if self._start_proxy():
                    env["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{self.proxy_port}"
                    # Set dummy API key so Claude Code skips the login screen
                    # (the proxy translates requests — no real Anthropic key needed)
                    env["ANTHROPIC_API_KEY"] = "sk-redclaw-proxy-bypass"
                    print(
                        f"🔄 Reverse proxy active on port {self.proxy_port}\n"
                        f"   Routing Claude Code → {env.get('REDCLAW_LLM_URL', 'backend')}\n"
                        f"   🔑 Login bypass: dummy API key injected\n"
                    )
                else:
                    print("⚠️  Proxy failed to start. Claude Code will use Anthropic API directly.")

            # Build claude command — detect root and adjust permission mode
            # Claude Code blocks bypassPermissions when running as root/sudo
            is_root = os.geteuid() == 0 if hasattr(os, "geteuid") else False
            permission_mode = "plan" if is_root else "bypassPermissions"

            if is_root:
                logger.info("Running as root — using 'plan' permission mode (bypassPermissions blocked for root)")

            cmd = [
                self.CLAUDE_BINARY,
                "--system-prompt", system_prompt,
                "--mcp-config", str(mcp_file),
                "--permission-mode", permission_mode,
            ]

            # Pass hooks via environment variable (--hooks is not a valid CLI flag)
            env["CLAUDE_CODE_HOOKS_FILE"] = str(hooks_file)

            # Print launch info
            print("🔴 Launching Claude Code with RedClaw skin...")
            print(f"   System Prompt: {len(system_prompt)} chars")
            print(f"   Hooks: {hooks_file}")
            print(f"   MCP Servers: 10 pentesting tools")
            if self.targets:
                print(f"   Targets: {', '.join(self.targets)}")
            print()

            # Launch Claude Code
            result = subprocess.run(cmd, env=env)
            return result.returncode

        except KeyboardInterrupt:
            print("\n🔴 RedClaw skin session interrupted")
            return 130

        finally:
            # Cleanup
            self._stop_proxy()
            self._cleanup_temp()

    def _cleanup_temp(self) -> None:
        """Remove temporary config directory."""
        if self._temp_dir and self._temp_dir.exists():
            try:
                shutil.rmtree(self._temp_dir)
                logger.info(f"Cleaned up temp dir: {self._temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to cleanup temp dir: {e}")

    # ── Info ──────────────────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        """Get launcher status."""
        return {
            "claude_installed": self.check_claude_installed(),
            "proxy_needed": self.check_proxy_needed(),
            "proxy_running": self._proxy_process is not None,
            "proxy_port": self.proxy_port,
            "guardian_enabled": self.enable_guardian,
            "targets": self.targets,
            "skills_dir": str(self.SKILLS_DIR),
            "skills_available": self.SKILLS_DIR.exists(),
        }
