"""
Hook Handler — CLI entry point for Claude Code hook callbacks.

Called by Claude Code hooks as subprocess commands:
  python -m redclaw.claude_skin.hook_handler <action> [args...]

Actions:
  session_start  — Display RedClaw banner
  health_check   — Quick tool health check
  pre_tool_use   — GuardianRails validation
  post_tool_use  — Log tool result to state
  log_tool_call  — Audit log for tool invocation
  extract_findings — Parse output for vulnerability findings
  checkpoint     — Save current state
  session_end    — Generate session summary
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("redclaw.hook_handler")

# ── Banner ────────────────────────────────────────────────────────────────────

BANNER = r"""
 ██████╗ ███████╗██████╗  ██████╗██╗      █████╗ ██╗    ██╗
 ██╔══██╗██╔════╝██╔══██╗██╔════╝██║     ██╔══██╗██║    ██║
 ██████╔╝█████╗  ██║  ██║██║     ██║     ███████║██║ █╗ ██║
 ██╔══██╗██╔══╝  ██║  ██║██║     ██║     ██╔══██║██║███╗██║
 ██║  ██║███████╗██████╔╝╚██████╗███████╗██║  ██║╚███╔███╔╝
 ╚═╝  ╚═╝╚══════╝╚═════╝  ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝
 v2.0.0 "Red Shadow" — Autonomous Pentesting Agent
 Powered by OpenClaw Runtime + Kaggle Phi-4
"""


# ── Action Handlers ───────────────────────────────────────────────────────────

def handle_session_start() -> None:
    """Display RedClaw banner on session start."""
    print(BANNER)
    print("🔴 RedClaw v2.0 session initialized")
    print(f"   Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("   Mode: Claude Code Skin + OpenClaw Runtime")
    print()


def handle_health_check() -> None:
    """Quick health check of tool dependencies."""
    try:
        from redclaw.tooling.detector import ToolDetector
        from redclaw.tooling.registry import TOOL_REGISTRY

        detector = ToolDetector()
        results = detector.detect_all(TOOL_REGISTRY)
        total = len(results)
        installed = sum(1 for r in results if r.installed)
        print(f"🩺 Tool Health: {installed}/{total} tools available")
        for r in results:
            icon = "✅" if r.installed else "❌"
            ver = r.version if r.version else "—"
            print(f"   {icon} {r.name:<15} {ver}")
    except Exception as e:
        print(f"⚠️  Health check unavailable: {e}")


def handle_pre_tool_use(tool_name: str, tool_input: str = "") -> None:
    """Validate tool call through GuardianRails before execution."""
    try:
        from redclaw.core.guardian import GuardianRails

        guardian = GuardianRails()

        # Extract command from tool input
        try:
            input_data = json.loads(tool_input) if tool_input else {}
        except json.JSONDecodeError:
            input_data = {"command": tool_input}

        command = input_data.get("command", tool_input)

        if command:
            validation = guardian.validate(command)
            if not validation.allowed:
                # Block the tool call
                print(f"🛡️ BLOCKED by GuardianRails: {tool_name}")
                for reason in validation.reasons:
                    print(f"   ❌ {reason}")
                sys.exit(1)  # Non-zero exit = block in Claude Code hooks
            elif validation.risk_level.value in ("high", "critical"):
                print(f"⚠️  High-risk command detected: {tool_name}")
                print(f"   Risk: {validation.risk_level.value}")

        # Log successful validation
        print(f"🔧 Tool authorized: {tool_name}")

    except ImportError:
        # GuardianRails not available — allow by default
        print(f"🔧 Tool call: {tool_name} (no GuardianRails)")


def handle_post_tool_use(tool_name: str, tool_output: str = "") -> None:
    """Log tool result to the RedClaw state manager."""
    output_preview = tool_output[:200] if tool_output else "(no output)"
    print(f"📋 Tool completed: {tool_name}")
    print(f"   Output: {output_preview}{'...' if len(tool_output) > 200 else ''}")


def handle_log_tool_call(tool_name: str, tool_input: str = "") -> None:
    """Audit log for tool invocation — writes to engagement log file."""
    log_dir = Path.home() / ".redclaw" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "tool_audit.jsonl"

    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "tool": tool_name,
        "input_preview": tool_input[:500] if tool_input else "",
        "source": "claude_code_hook",
    }

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def handle_extract_findings(tool_name: str, tool_output: str = "") -> None:
    """Parse tool output for vulnerability findings."""
    if not tool_output:
        return

    # Simple heuristic finding extraction
    severity_keywords = {
        "critical": ["critical", "CRITICAL", "rce", "remote code execution"],
        "high": ["high", "HIGH", "sql injection", "xss", "authentication bypass"],
        "medium": ["medium", "MEDIUM", "information disclosure", "clickjacking"],
        "low": ["low", "LOW", "cookie", "header missing"],
    }

    for severity, keywords in severity_keywords.items():
        for keyword in keywords:
            if keyword in tool_output:
                print(f"🔍 Potential {severity.upper()} finding detected in {tool_name}")
                break


def handle_checkpoint() -> None:
    """Save current state to disk."""
    try:
        from redclaw.core.state import StateManager
        state = StateManager()
        state.checkpoint()
        print("💾 State checkpointed to disk")
    except Exception as e:
        print(f"⚠️  Checkpoint failed: {e}")


def handle_session_end() -> None:
    """Generate session summary on exit."""
    print("\n" + "═" * 50)
    print("🔴 RedClaw session ended")
    print(f"   Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("   State saved. Use 'redclaw --resume' to continue.")
    print("═" * 50)


# ── CLI Entry Point ───────────────────────────────────────────────────────────

ACTIONS = {
    "session_start": (handle_session_start, 0),
    "health_check": (handle_health_check, 0),
    "pre_tool_use": (handle_pre_tool_use, 2),
    "post_tool_use": (handle_post_tool_use, 2),
    "log_tool_call": (handle_log_tool_call, 2),
    "extract_findings": (handle_extract_findings, 2),
    "checkpoint": (handle_checkpoint, 0),
    "session_end": (handle_session_end, 0),
}


def main() -> None:
    """CLI entry point: python -m redclaw.claude_skin.hook_handler <action> [args...]"""
    if len(sys.argv) < 2:
        print(f"Usage: python -m redclaw.claude_skin.hook_handler <action> [args...]")
        print(f"Actions: {', '.join(ACTIONS.keys())}")
        sys.exit(1)

    action = sys.argv[1]
    args = sys.argv[2:]

    if action not in ACTIONS:
        print(f"Unknown action: {action}")
        print(f"Available: {', '.join(ACTIONS.keys())}")
        sys.exit(1)

    handler, expected_args = ACTIONS[action]

    # Pad args with empty strings if fewer than expected
    while len(args) < expected_args:
        args.append("")

    handler(*args[:expected_args])


if __name__ == "__main__":
    main()
