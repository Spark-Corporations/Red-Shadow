"""
Hook Handler — CLI entry point for Claude Code hook callbacks.

Called by Claude Code hooks as subprocess commands:
  python -m redclaw.claude_skin.hook_handler <action> [args...]

Actions:
  session_start    — Display RedClaw banner
  health_check     — Quick tool health check
  status           — Full system status with REAL LLM connectivity
  link [url]       — View/update LLM backend URL + verify connectivity
  findings         — List vulnerability findings from state
  pre_tool_use     — GuardianRails validation
  post_tool_use    — Log tool result to state
  log_tool_call    — Audit log for tool invocation
  extract_findings — Parse output for vulnerability findings
  checkpoint       — Save current state
  session_end      — Generate session summary
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.request
import urllib.error
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
        results = detector.check_all()
        total = len(results)
        installed = sum(1 for r in results if r.installed)
        print(f"🩺 Tool Health: {installed}/{total} tools available")
        for r in results:
            icon = "✅" if r.installed else "❌"
            ver = r.version if r.version else "—"
            print(f"   {icon} {r.tool.name:<15} {ver}")
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


# ── REAL Command Handlers ───────────────────────────────────────────────────────

def _test_url_reachable(url: str, timeout: int = 5) -> bool:
    """Actually test if a URL is reachable via HTTP. No faking."""
    try:
        # Ensure URL has /v1 for the LLM endpoint check
        test_url = url.rstrip("/")
        if not test_url.endswith("/v1"):
            test_url += "/v1"
        test_url += "/models"

        req = urllib.request.Request(test_url, method="GET")
        req.add_header("User-Agent", "RedClaw/2.0 HealthCheck")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        # Also try the base URL
        try:
            req = urllib.request.Request(url.rstrip("/"), method="GET")
            req.add_header("User-Agent", "RedClaw/2.0 HealthCheck")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return 200 <= resp.status < 500
        except Exception:
            return False


def handle_link(url: str = "") -> None:
    """View or update LLM backend URL — REAL: saves to disk + tests connectivity."""
    link_file = Path.home() / ".redclaw" / "link.txt"

    if not url or not url.strip():
        # Show current URL
        env_url = os.environ.get("REDCLAW_LLM_URL", None)
        saved_url = None
        if link_file.exists():
            saved_url = link_file.read_text().strip()

        active = env_url or saved_url
        print("🔗 LLM Backend Link")
        print(f"   Active URL:  {active or 'not set'}")
        print(f"   Saved URL:   {saved_url or 'none'}")
        print(f"   Env URL:     {env_url or 'not set'}")

        if active:
            print(f"\n   Testing connectivity to {active}...")
            reachable = _test_url_reachable(active)
            if reachable:
                print("   ✅ 🟢 LLM endpoint is REACHABLE")
            else:
                print("   ❌ 🟡 LLM endpoint is UNREACHABLE")
                print("   → Check if Kaggle notebook is running and ngrok tunnel is active")
        else:
            print("\n   ⚠️  No URL configured. Use: /link <ngrok_url>")
        return

    # Update URL
    new_url = url.strip()
    if not new_url.startswith("http"):
        new_url = f"https://{new_url}"

    # Save to disk
    link_file.parent.mkdir(parents=True, exist_ok=True)
    link_file.write_text(new_url)

    # Update env
    os.environ["REDCLAW_LLM_URL"] = new_url

    print(f"🔗 LLM backend URL updated: {new_url}")
    print(f"   Saved to: {link_file}")

    # REAL connectivity test
    print(f"   Testing connectivity...")
    reachable = _test_url_reachable(new_url)
    if reachable:
        print("   ✅ 🟢 LLM endpoint is REACHABLE")
    else:
        print("   ⚠️  🟡 LLM endpoint is UNREACHABLE")
        print("   → URL saved, but the endpoint is not responding.")
        print("   → Check if Kaggle notebook is running and ngrok tunnel is active.")


def handle_status() -> None:
    """Show REAL system status — tests actual LLM connectivity, not fake."""
    print("🔴 RedClaw v2.0 System Status")
    print(f"   Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 1. LLM Backend — test REAL connectivity
    link_file = Path.home() / ".redclaw" / "link.txt"
    llm_url = os.environ.get("REDCLAW_LLM_URL")
    if not llm_url and link_file.exists():
        llm_url = link_file.read_text().strip()

    print("── LLM Backend ────────────────────────────────────")
    if llm_url:
        print(f"   Endpoint: {llm_url}")
        reachable = _test_url_reachable(llm_url)
        if reachable:
            print("   Status:   🟢 REACHABLE")
        else:
            print("   Status:   🟡 UNREACHABLE")
    else:
        print("   Endpoint: NOT CONFIGURED")
        print("   Status:   🔴 No URL set — use /link <ngrok_url>")

    # 2. Tool health — delegate to real health_check
    print()
    print("── Tool Health ────────────────────────────────────")
    handle_health_check()

    # 3. State — show real engagement info
    print()
    print("── Engagement State ──────────────────────────────")
    state_file = Path.home() / ".redclaw" / "state" / "pipeline_state.json"
    if state_file.exists():
        try:
            state_data = json.loads(state_file.read_text())
            phase = state_data.get("current_phase", "unknown")
            findings = state_data.get("global_findings", [])
            print(f"   Phase:    {phase}")
            print(f"   Findings: {len(findings)}")
        except Exception as e:
            print(f"   ⚠️  Could not read state: {e}")
    else:
        print("   No active engagement")

    # 4. GuardianRails
    print()
    print("── GuardianRails ─────────────────────────────────")
    audit_file = Path.home() / ".redclaw" / "logs" / "tool_audit.jsonl"
    if audit_file.exists():
        try:
            lines = audit_file.read_text().strip().split("\n")
            print(f"   Commands audited: {len(lines)}")
        except Exception:
            print("   ⚠️  Could not read audit log")
    else:
        print("   Active (no commands processed yet)")


def handle_findings_list() -> None:
    """List findings from REAL state file on disk."""
    state_file = Path.home() / ".redclaw" / "state" / "pipeline_state.json"

    if not state_file.exists():
        print("No active engagement state found.")
        print("Start a scan first, or load an engagement config.")
        return

    try:
        state_data = json.loads(state_file.read_text())
    except Exception as e:
        print(f"⚠️  Could not read state file: {e}")
        return

    findings = state_data.get("global_findings", [])
    if not findings:
        print("No findings recorded yet.")
        return

    print(f"🔍 Total findings: {len(findings)}")
    print()
    for i, f in enumerate(findings, 1):
        sev = f.get("severity", "info").upper()
        title = f.get("title", "Untitled")
        target = f.get("target", "N/A")
        phase = f.get("phase", "?")
        print(f"  {i}. [{sev}] {title} — {target} (phase: {phase})")


# ── CLI Entry Point ───────────────────────────────────────────────────────────

ACTIONS = {
    "session_start": (handle_session_start, 0),
    "health_check": (handle_health_check, 0),
    "status": (handle_status, 0),
    "link": (handle_link, 1),
    "findings": (handle_findings_list, 0),
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
