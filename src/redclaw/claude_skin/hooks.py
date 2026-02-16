"""
HookGenerator — Creates Claude Code hook configurations for RedClaw interception.

Claude Code hooks intercept events in the CLI lifecycle:
  - SessionStart: Display RedClaw banner, run health check
  - PreToolUse:   Route tool calls through GuardianRails validation
  - PostToolUse:  Log tool results to StateManager, update findings
  - Stop:         Auto-checkpoint, generate session summary

Each hook calls a RedClaw subprocess via `python -m redclaw.claude_skin.hook_handler`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional


class HookGenerator:
    """
    Generate Claude Code hook configuration JSON.

    The hooks integrate Claude Code's lifecycle events with RedClaw's backend:
      - GuardianRails validation on every tool call
      - Automatic state persistence on session end
      - Banner display and health checks on session start
    """

    # Python interpreter path (portable)
    PYTHON = sys.executable

    # Hook handler module path
    HANDLER_MODULE = "redclaw.claude_skin.hook_handler"

    def __init__(
        self,
        guardian_enabled: bool = True,
        auto_checkpoint: bool = True,
        health_check_on_start: bool = True,
    ):
        self.guardian_enabled = guardian_enabled
        self.auto_checkpoint = auto_checkpoint
        self.health_check_on_start = health_check_on_start

    def generate(self) -> dict[str, Any]:
        """Generate the complete hooks configuration dict."""
        hooks: dict[str, list[dict[str, Any]]] = {
            "SessionStart": self._session_start_hooks(),
            "PreToolUse": self._pre_tool_use_hooks(),
            "PostToolUse": self._post_tool_use_hooks(),
            "Stop": self._stop_hooks(),
        }
        return {"hooks": hooks}

    def generate_json(self, indent: int = 2) -> str:
        """Generate hooks as a formatted JSON string."""
        return json.dumps(self.generate(), indent=indent)

    def write_to_file(self, path: Path) -> Path:
        """Write hooks config to a JSON file and return the path."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.generate_json(), encoding="utf-8")
        return path

    # ── Hook builders ─────────────────────────────────────────────────────

    def _session_start_hooks(self) -> list[dict[str, Any]]:
        """Hooks for when Claude Code session starts."""
        hooks = [
            # Display RedClaw banner
            {
                "type": "command",
                "command": f"{self.PYTHON} -m {self.HANDLER_MODULE} session_start",
            },
        ]

        if self.health_check_on_start:
            hooks.append({
                "type": "command",
                "command": f"{self.PYTHON} -m {self.HANDLER_MODULE} health_check",
            })

        return hooks

    def _pre_tool_use_hooks(self) -> list[dict[str, Any]]:
        """Hooks that run BEFORE any tool is executed."""
        hooks = []

        if self.guardian_enabled:
            # GuardianRails validation — blocks dangerous commands
            hooks.append({
                "type": "command",
                "command": (
                    f"{self.PYTHON} -m {self.HANDLER_MODULE} "
                    "pre_tool_use $TOOL_NAME $TOOL_INPUT"
                ),
                "matcher": {"tool_name": "*"},  # Match ALL tools
            })

        # Logging hook — records tool invocation
        hooks.append({
            "type": "command",
            "command": (
                f"{self.PYTHON} -m {self.HANDLER_MODULE} "
                "log_tool_call $TOOL_NAME $TOOL_INPUT"
            ),
            "matcher": {"tool_name": "*"},
        })

        return hooks

    def _post_tool_use_hooks(self) -> list[dict[str, Any]]:
        """Hooks that run AFTER a tool completes execution."""
        return [
            # Update state with tool result
            {
                "type": "command",
                "command": (
                    f"{self.PYTHON} -m {self.HANDLER_MODULE} "
                    "post_tool_use $TOOL_NAME $TOOL_OUTPUT"
                ),
                "matcher": {"tool_name": "*"},
            },
            # Finding extraction — parse output for vulnerabilities
            {
                "type": "command",
                "command": (
                    f"{self.PYTHON} -m {self.HANDLER_MODULE} "
                    "extract_findings $TOOL_NAME $TOOL_OUTPUT"
                ),
                "matcher": {
                    "tool_name": [
                        "redclaw-nmap", "redclaw-nuclei", "redclaw-msf",
                        "redclaw-sqlmap", "redclaw-linpeas", "redclaw-winpeas",
                    ],
                },
            },
        ]

    def _stop_hooks(self) -> list[dict[str, Any]]:
        """Hooks for when the Claude Code session ends."""
        hooks = []

        if self.auto_checkpoint:
            hooks.append({
                "type": "command",
                "command": f"{self.PYTHON} -m {self.HANDLER_MODULE} checkpoint",
            })

        # Always generate session summary
        hooks.append({
            "type": "command",
            "command": f"{self.PYTHON} -m {self.HANDLER_MODULE} session_end",
        })

        return hooks


def get_hooks_config(
    guardian: bool = True,
    checkpoint: bool = True,
    health_check: bool = True,
) -> dict[str, Any]:
    """Convenience function to generate hooks config."""
    return HookGenerator(
        guardian_enabled=guardian,
        auto_checkpoint=checkpoint,
        health_check_on_start=health_check,
    ).generate()
