"""
RedClaw CLI — Claude Code-style interactive pentesting terminal.

Features:
  - Rich terminal output with panels, tables, progress bars
  - Interactive REPL with auto-completion
  - Slash commands (/scan, /exploit, /report, /status, /config, /quit)
  - Streaming agent output with live updates
  - Phase progress visualization
  - Finding severity color coding
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

logger = logging.getLogger("redclaw.cli")

# ── Theme ─────────────────────────────────────────────────────────────────────

REDCLAW_THEME = Theme({
    "info": "dim cyan",
    "warning": "yellow",
    "error": "bold red",
    "critical": "bold white on red",
    "success": "bold green",
    "phase": "bold magenta",
    "finding.critical": "bold white on red",
    "finding.high": "bold red",
    "finding.medium": "yellow",
    "finding.low": "cyan",
    "finding.info": "dim white",
    "tool": "bold blue",
    "agent": "bold cyan",
})

PROMPT_STYLE = Style.from_dict({
    "prompt": "#ff4444 bold",
    "input": "#ffffff",
})

# ── Banner ────────────────────────────────────────────────────────────────────

BANNER = r"""
[bold red]
  ██████╗ ███████╗██████╗  ██████╗██╗      █████╗ ██╗    ██╗
  ██╔══██╗██╔════╝██╔══██╗██╔════╝██║     ██╔══██╗██║    ██║
  ██████╔╝█████╗  ██║  ██║██║     ██║     ███████║██║ █╗ ██║
  ██╔══██╗██╔══╝  ██║  ██║██║     ██║     ██╔══██║██║███╗██║
  ██║  ██║███████╗██████╔╝╚██████╗███████╗██║  ██║╚███╔███╔╝
  ╚═╝  ╚═╝╚══════╝╚═════╝  ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝[/]
[dim white]  v2.0.0 "Red Shadow" — Autonomous Penetration Testing Agent
  Powered by OpenClaw Runtime + Kaggle Phi-4[/]
"""

# ── Slash Commands ────────────────────────────────────────────────────────────

SLASH_COMMANDS = {
    "/help": "Show available commands",
    "/status": "Show pipeline and agent status",
    "/config": "Show current engagement configuration",
    "/scan": "Start a scan on configured targets",
    "/exploit": "Begin exploitation phase (requires approval)",
    "/report": "Generate engagement report",
    "/findings": "Show all findings",
    "/tools": "List available MCP tool servers",
    "/sessions": "Show active sessions",
    "/guardian": "Show GuardianRails statistics",
    "/checkpoint": "Save current state to disk",
    "/resume": "Resume from last checkpoint",
    "/proxy": "Start the Anthropic→OpenAI reverse proxy",
    "/agent": "Show agent loop stats and LLM provider health",
    "/skin": "Launch Claude Code with RedClaw pentesting skin",
    "/doctor": "Health-check all tool dependencies",
    "/setup-tools": "Auto-install missing pentesting tools",
    "/link": "View/update ngrok LLM backend URL",
    "/ip_m": "Update model IP when GCP restarts (e.g. /ip_m 35.223.143.247)",
    "/model": "Switch active model: /model qwen | /model phi",
    "/clear": "Clear the terminal",
    "/quit": "Exit RedClaw",
}


class RedClawCLI:
    """
    Claude Code-style interactive CLI for pentesting operations.

    Usage:
        cli = RedClawCLI()
        cli.run()
    """

    def __init__(
        self,
        config_manager=None,
        state_manager=None,
        runtime=None,
        orchestrator=None,
        guardian=None,
    ):
        self._console = Console(theme=REDCLAW_THEME)
        self._config = config_manager
        self._state = state_manager
        self._runtime = runtime
        self._orchestrator = orchestrator
        self._guardian = guardian
        self._running = False
        self._history_file = Path.home() / ".redclaw_history"

        # Command completer
        self._completer = WordCompleter(
            list(SLASH_COMMANDS.keys()) + ["nmap", "masscan", "nuclei", "metasploit"],
            ignore_case=True,
        )

        logger.info("RedClaw CLI initialized")

    def run(self) -> None:
        """Start the interactive CLI REPL."""
        self._console.print(BANNER)
        self._show_system_status()
        self._running = True

        session: PromptSession = PromptSession(
            history=FileHistory(str(self._history_file)),
            auto_suggest=AutoSuggestFromHistory(),
            completer=self._completer,
            style=PROMPT_STYLE,
        )

        self._console.print(
            "\n[dim]Type a command or natural language instruction. "
            "Use /help for available commands.[/]\n"
        )

        while self._running:
            try:
                user_input = session.prompt(
                    [("class:prompt", "redclaw ❯ ")],
                ).strip()

                if not user_input:
                    continue

                if user_input.startswith("/"):
                    self._handle_slash_command(user_input)
                else:
                    self._handle_natural_language(user_input)

            except KeyboardInterrupt:
                self._console.print("\n[warning]Use /quit to exit.[/]")
            except EOFError:
                self._running = False

        self._console.print("[dim]RedClaw session ended.[/]")

    # ── Slash command dispatch ────────────────────────────────────────────

    def _handle_slash_command(self, command: str) -> None:
        """Route slash commands to handlers."""
        cmd = command.split()[0].lower()
        args = command.split()[1:]

        handlers = {
            "/help": self._cmd_help,
            "/status": self._cmd_status,
            "/config": self._cmd_config,
            "/scan": self._cmd_scan,
            "/exploit": self._cmd_exploit,
            "/report": self._cmd_report,
            "/findings": self._cmd_findings,
            "/tools": self._cmd_tools,
            "/sessions": self._cmd_sessions,
            "/guardian": self._cmd_guardian,
            "/checkpoint": self._cmd_checkpoint,
            "/proxy": self._cmd_proxy,
            "/agent": self._cmd_agent,
            "/skin": self._cmd_skin,
            "/doctor": self._cmd_doctor,
            "/setup-tools": self._cmd_setup_tools,
            "/link": self._cmd_link,
            "/ip_m": self._cmd_ip_m,
            "/model": self._cmd_model,
            "/clear": self._cmd_clear,
            "/quit": self._cmd_quit,
        }

        handler = handlers.get(cmd)
        if handler:
            handler(args)
        else:
            self._console.print(f"[error]Unknown command: {cmd}. Type /help for options.[/]")

    # ── Command handlers ──────────────────────────────────────────────────

    def _cmd_help(self, args: list[str]) -> None:
        table = Table(title="RedClaw Commands", style="red", border_style="dim")
        table.add_column("Command", style="bold")
        table.add_column("Description")
        for cmd, desc in SLASH_COMMANDS.items():
            table.add_row(cmd, desc)
        self._console.print(table)

    def _cmd_status(self, args: list[str]) -> None:
        panel_content = []

        # Pipeline status
        if self._state:
            state = self._state.state
            phase_status = self._state.get_phase_status(self._state.current_phase)
            panel_content.append(f"[phase]Phase[/]: {state.current_phase}")
            panel_content.append(f"[info]Status[/]: {phase_status}")
            panel_content.append(f"[info]Findings[/]: {len(state.global_findings)}")
        else:
            panel_content.append("[dim]No active engagement[/]")

        # Runtime status — REAL health, not fake
        if self._runtime:
            status = self._runtime.get_status()
            health = status.get('health', 'not_initialized')

            if health == 'ready':
                panel_content.append(f"\n[agent]OpenClaw[/]: 🟢 Ready (LLM reachable)")
            elif health == 'degraded':
                panel_content.append(f"\n[agent]OpenClaw[/]: 🟡 Degraded (LLM unreachable)")
            else:
                panel_content.append(f"\n[agent]OpenClaw[/]: 🔴 Not initialized")

            panel_content.append(f"[tool]LLM[/]: {status.get('llm_model', 'N/A')}")
            panel_content.append(f"[tool]Endpoint[/]: {status.get('llm_endpoint', 'N/A')}")

            # Per-provider health
            providers = status.get('health_providers', {})
            if providers:
                for name, info in providers.items():
                    reachable = info.get('reachable', False)
                    icon = '✅' if reachable else '❌'
                    panel_content.append(f"  {icon} {name}: {'reachable' if reachable else 'unreachable'}")

            panel_content.append(f"[tool]Tools[/]: {status.get('tool_bridge', 'none')}")

        self._console.print(Panel(
            "\n".join(panel_content),
            title="[bold]Pipeline Status[/]",
            border_style="red",
        ))

    def _cmd_config(self, args: list[str]) -> None:
        if self._config:
            table = Table(title="Engagement Config", border_style="dim")
            table.add_column("Key", style="bold")
            table.add_column("Value")
            cfg = self._config._config
            table.add_row("Name", cfg.name)
            table.add_row("Targets", ", ".join(cfg.targets.include))
            enabled_phases = [p for p, pc in cfg.phases.items() if pc.enabled]
            table.add_row("Phases", ", ".join(enabled_phases) if enabled_phases else "none")
            table.add_row("LLM Model", cfg.llm.model)
            table.add_row("LLM Provider", cfg.llm.provider)
            self._console.print(table)
        else:
            self._console.print("[warning]No configuration loaded. Provide an engagement YAML.[/]")

    def _cmd_scan(self, args: list[str]) -> None:
        """Start a REAL scan through the OpenClaw runtime ReAct loop."""
        target = args[0] if args else None
        if not target:
            self._console.print("[warning]Usage: /scan <target>[/]")
            self._console.print("[dim]Example: /scan 10.10.10.5[/]")
            return

        if not self._runtime:
            self._console.print("[error]OpenClaw runtime not available. Cannot scan.[/]")
            return

        # Delegate to the REAL agent loop — this calls LLM which uses MCP tools
        task_prompt = (
            f"Perform a comprehensive network scan on target: {target}\n"
            "1. Use masscan or nmap for fast port discovery\n"
            "2. Run detailed service/version detection on open ports\n"
            "3. Identify potential vulnerabilities\n"
            "4. Summarize all findings with severity ratings"
        )
        self._console.print(f"[tool]Starting scan[/] on [bold]{target}[/] via OpenClaw agent...")
        self._handle_natural_language(task_prompt)

    def _cmd_exploit(self, args: list[str]) -> None:
        """Exploitation phase — requires explicit human approval."""
        target = args[0] if args else None
        self._console.print(
            Panel(
                "[warning]⚠️  EXPLOITATION PHASE[/]\n\n"
                "This will attempt to exploit discovered vulnerabilities.\n"
                "Each exploit will require your explicit approval.\n"
                "Type 'yes' to proceed or 'no' to cancel.",
                title="[bold red]Human Approval Required[/]",
                border_style="red",
            )
        )
        # Get user's confirmation
        try:
            answer = input("Proceed? [yes/no] > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "no"

        if answer != "yes":
            self._console.print("[dim]Exploitation cancelled.[/]")
            return

        if not self._runtime:
            self._console.print("[error]OpenClaw runtime not available.[/]")
            return

        # Delegate to REAL agent loop
        task_prompt = (
            f"Exploitation phase for target: {target or 'engagement targets'}\n"
            "1. Review all findings from the scanning phase\n"
            "2. Identify exploitable vulnerabilities\n"
            "3. Attempt exploitation using available tools (metasploit, sqlmap, etc.)\n"
            "4. Document evidence for each successful exploit\n"
            "Human has approved this exploitation attempt."
        )
        self._handle_natural_language(task_prompt)

    def _cmd_report(self, args: list[str]) -> None:
        output = args[0] if args else "./output/report.md"
        self._console.print(f"[info]Generating report: {output}[/]")
        try:
            from ..reporting.generator import ReportGenerator
            gen = ReportGenerator(self._state, self._config)
            gen.generate_markdown(output)
            gen.generate_html(Path(output).with_suffix(".html"))
            self._console.print(f"[success]Report generated: {output}[/]")
        except Exception as e:
            self._console.print(f"[error]Report generation failed: {e}[/]")

    def _cmd_findings(self, args: list[str]) -> None:
        if not self._state:
            self._console.print("[dim]No findings yet.[/]")
            return

        findings = self._state.state.global_findings
        if not findings:
            self._console.print("[dim]No findings recorded.[/]")
            return

        table = Table(title=f"Findings ({len(findings)})", border_style="dim")
        table.add_column("#", style="dim")
        table.add_column("Severity", justify="center")
        table.add_column("Title")
        table.add_column("Phase")

        sev_styles = {
            "critical": "finding.critical",
            "high": "finding.high",
            "medium": "finding.medium",
            "low": "finding.low",
            "info": "finding.info",
        }

        for i, f in enumerate(findings, 1):
            sev = f.severity
            style = sev_styles.get(sev, "dim")
            table.add_row(str(i), Text(sev.upper(), style=style), f.title, f.phase)

        self._console.print(table)

    def _cmd_tools(self, args: list[str]) -> None:
        """List tool servers with REAL availability detection."""
        tools_meta = [
            ("nmap", "Port scanning & service detection", "nmap"),
            ("masscan", "Ultra-fast port discovery", "masscan"),
            ("nuclei", "Template-based vuln scanning", "nuclei"),
            ("metasploit", "Exploitation framework", "msfconsole"),
            ("sqlmap", "SQL injection", "sqlmap"),
            ("hydra", "Credential brute-force", "hydra"),
            ("linpeas", "Linux privesc enumeration", "linpeas.sh"),
            ("winpeas", "Windows privesc enumeration", "winpeas.exe"),
            ("bloodhound", "AD domain analysis", "bloodhound-python"),
            ("custom_exploit", "Python/Bash exploit scripts", None),
        ]

        import shutil
        table = Table(title="MCP Tool Servers", border_style="dim")
        table.add_column("Tool", style="tool")
        table.add_column("Description")
        table.add_column("Status", justify="center")

        installed = 0
        for name, desc, binary in tools_meta:
            if binary is None:
                # Custom exploit — always available (it's our own code)
                table.add_row(name, desc, "🟢 Ready")
                installed += 1
            elif shutil.which(binary):
                table.add_row(name, desc, "🟢 Ready")
                installed += 1
            else:
                table.add_row(name, desc, "🔴 Not installed")

        self._console.print(table)
        total = len(tools_meta)
        self._console.print(
            f"[dim]{installed}/{total} tools available. "
            f"Use /setup-tools to install missing tools.[/]"
        )

    def _cmd_sessions(self, args: list[str]) -> None:
        self._console.print(Panel(
            "[info]Local Session[/]: 🟢 Active\n"
            "[info]Remote Session[/]: 🔴 Not connected\n"
            "[dim]Use 'connect <host> <user> <pass>' to establish SSH session[/]",
            title="Sessions",
            border_style="dim",
        ))

    def _cmd_guardian(self, args: list[str]) -> None:
        if self._guardian:
            stats = self._guardian.get_stats()
            self._console.print(Panel(
                f"Total commands: {stats['total_commands']}\n"
                f"Blocked: {stats['blocked']}\n"
                f"Allowed: {stats['allowed']}\n"
                f"Block rate: {stats['block_rate']}",
                title="GuardianRails Statistics",
                border_style="yellow",
            ))
        else:
            self._console.print("[dim]GuardianRails not initialized.[/]")

    def _cmd_checkpoint(self, args: list[str]) -> None:
        if self._state:
            self._state.checkpoint()
            self._console.print("[success]State checkpointed to disk.[/]")
        else:
            self._console.print("[warning]No active state to checkpoint.[/]")

    def _cmd_proxy(self, args: list[str]) -> None:
        """Start the Anthropic→OpenAI reverse proxy."""
        from ..proxy.server import start_proxy
        import os
        backend = args[0] if args else os.environ.get(
            "REDCLAW_LLM_URL",
            "https://0b2f-34-29-72-116.ngrok-free.app"
        )
        port = int(args[1]) if len(args) > 1 else 8080
        self._console.print(
            f"[tool]Starting reverse proxy[/]\n"
            f"  Backend: {backend}\n"
            f"  Listen: http://127.0.0.1:{port}\n\n"
            f"  [dim]Set ANTHROPIC_BASE_URL=http://127.0.0.1:{port} for Claude Code[/]"
        )
        start_proxy(backend_url=backend, port=port)

    def _cmd_agent(self, args: list[str]) -> None:
        """Show agent loop stats and LLM provider health."""
        if not self._runtime:
            self._console.print("[warning]Runtime not initialized.[/]")
            return

        status = self._runtime.get_status()
        panel_lines = [
            f"[agent]Initialized[/]: {'🟢 Yes' if status['initialized'] else '🔴 No'}",
            f"[tool]LLM Endpoint[/]: {status.get('llm_endpoint', 'N/A')}",
            f"[tool]LLM Model[/]: {status.get('llm_model', 'N/A')}",
            f"[info]Total Tasks[/]: {status.get('total_tasks', 0)}",
            f"[info]Last Iterations[/]: {status.get('last_iterations', 0)}",
            f"[info]Tool Bridge[/]: {status.get('tool_bridge', 'N/A')}",
        ]

        # Provider stats
        if pstats := status.get('provider_stats'):
            panel_lines.append(f"\n[agent]Provider[/]: {pstats.get('active_provider', 'N/A')}")
            panel_lines.append(f"[info]Requests[/]: {pstats.get('total_requests', 0)}")
            panel_lines.append(f"[info]Tokens[/]: {pstats.get('total_tokens', 0)}")

        # Health check
        if self._runtime.provider:
            health = self._runtime.provider.health_check()
            panel_lines.append("\n[phase]Health Check[/]:")
            for name, info in health.items():
                icon = '🟢' if info.get('reachable') else '🔴'
                panel_lines.append(f"  {icon} {name}")

        self._console.print(Panel(
            "\n".join(panel_lines),
            title="[bold]Agent Loop Status[/]",
            border_style="cyan",
        ))

    def _cmd_skin(self, args: list[str]) -> None:
        """Launch Claude Code with RedClaw pentesting skin."""
        from ..claude_skin.launcher import ClaudeCodeLauncher

        targets = args if args else []
        launcher = ClaudeCodeLauncher(
            targets=targets,
            enable_guardian=self._guardian is not None,
        )

        if not launcher.check_claude_installed():
            self._console.print(
                "[error]Claude Code CLI not found.[/]\n"
                "Install: [tool]npm install -g @anthropic-ai/claude-code[/]\n"
                "Or use RedClaw standalone mode (current)."
            )
            return

        self._console.print("[agent]Launching Claude Code with RedClaw skin...[/]")
        status = launcher.get_status()
        self._console.print(f"  Proxy needed: {status['proxy_needed']}")
        self._console.print(f"  Skills: {status['skills_available']}")

        # Transfer control to Claude Code
        self._running = False  # Exit current REPL
        exit_code = launcher.launch()
        if exit_code != 0:
            self._console.print(f"[warning]Claude Code exited with code {exit_code}[/]")

    def _cmd_doctor(self, args: list[str]) -> None:
        """Run health-check on all tool dependencies."""
        try:
            from ..tooling.doctor import DoctorReport
            doctor = DoctorReport()
            doctor.run()
        except ImportError:
            self._console.print("[error]Tooling module not available.[/]")
        except Exception as e:
            self._console.print(f"[error]Doctor failed: {e}[/]")

    def _cmd_setup_tools(self, args: list[str]) -> None:
        """Auto-install missing pentesting tool dependencies."""
        mode = args[0] if args else "interactive"
        try:
            from ..tooling.installer import ToolInstaller
            installer = ToolInstaller()
            dry_run = mode == "dry-run"
            auto = mode == "auto"
            installer.install_all(
                console=self._console,
                dry_run=dry_run,
                auto_approve=auto,
            )
        except ImportError:
            self._console.print("[error]Tooling module not available.[/]")
        except Exception as e:
            self._console.print(f"[error]Setup failed: {e}[/]")

    def _cmd_link(self, args: list[str]) -> None:
        """View or update the ngrok LLM backend URL (REDCLAW_LLM_URL)."""
        link_file = Path.home() / ".redclaw" / "link.txt"

        if not args:
            # Show current URL
            current = os.environ.get("REDCLAW_LLM_URL", None)
            saved = None
            if link_file.exists():
                saved = link_file.read_text().strip()

            # Also show runtime endpoint if different
            runtime_url = None
            if self._runtime:
                status = self._runtime.get_status()
                runtime_url = status.get("llm_endpoint")

            self._console.print(Panel(
                f"[info]Active URL[/]:  {runtime_url or current or '[dim]not set[/]'}\n"
                f"[info]Saved URL[/]:   {saved or '[dim]none[/]'}\n\n"
                "[dim]Usage: /link <ngrok_url>[/]",
                title="[bold]LLM Backend Link[/]",
                border_style="red",
            ))
            return

        new_url = args[0].strip()
        if not new_url.startswith("http"):
            new_url = f"https://{new_url}"

        # Update env at runtime
        os.environ["REDCLAW_LLM_URL"] = new_url

        # Persist for next session
        link_file.parent.mkdir(parents=True, exist_ok=True)
        link_file.write_text(new_url)

        # ── Hot-reload: rebuild the LLM provider with the new URL ──────────
        if self._runtime:
            self._runtime._config.llm_endpoint = new_url
            try:
                import asyncio
                health = asyncio.run(self._runtime.initialize())
                reachable = health.get("status") == "ready"
                if reachable:
                    self._console.print(
                        f"[success]✅ LLM backend URL updated and connected:[/]\n"
                        f"   [info]{new_url}[/]\n"
                        f"   [success]🟢 LLM reachable![/]"
                    )
                else:
                    self._console.print(
                        f"[warning]⚠️  LLM backend URL updated but unreachable:[/]\n"
                        f"   [info]{new_url}[/]\n"
                        f"   [warning]🟡 Will retry when you send a command[/]"
                    )
            except Exception:
                self._console.print(
                    f"[success]✅ LLM backend URL updated:[/]\n"
                    f"   [info]{new_url}[/]\n"
                    f"   [dim]Saved to {link_file}[/]"
                )
        else:
            self._console.print(
                f"[success]✅ LLM backend URL updated:[/]\n"
                f"   [info]{new_url}[/]\n"
                f"   [dim]Saved to {link_file}[/]"
            )

    def _cmd_ip_m(self, args: list[str]) -> None:
        """Update the model's IP address when GCP instance restarts.

        Usage:
            /ip_m                    → show current model IP
            /ip_m 35.223.143.247     → update to new IP (keeps port 8002)
            /ip_m 35.223.143.247:8003 → update IP and port
        """
        ip_file = Path.home() / ".redclaw" / "model_ip.txt"
        default_port = "8002"

        if not args:
            # Show current model IP
            current_endpoint = None
            if self._runtime:
                status = self._runtime.get_status()
                current_endpoint = status.get("llm_endpoint")

            saved_ip = None
            if ip_file.exists():
                saved_ip = ip_file.read_text().strip()

            self._console.print(Panel(
                f"[info]Active Endpoint[/]:  {current_endpoint or '[dim]not set[/]'}\n"
                f"[info]Saved Model IP[/]:   {saved_ip or '[dim]none[/]'}\n\n"
                "[dim]Usage: /ip_m <new_ip>[/]\n"
                "[dim]Example: /ip_m 35.223.143.247[/]\n"
                "[dim]Example: /ip_m 35.223.143.247:8003[/]",
                title="[bold]Model IP Configuration[/]",
                border_style="red",
            ))
            return

        # Parse IP input
        raw_input = args[0].strip()

        # Strip protocol prefix if user accidentally adds it
        for prefix in ("http://", "https://"):
            if raw_input.startswith(prefix):
                raw_input = raw_input[len(prefix):]

        # Split IP and port
        if ":" in raw_input:
            ip_part, port_part = raw_input.rsplit(":", 1)
        else:
            ip_part = raw_input
            port_part = default_port

        # Build the full endpoint URL
        new_url = f"http://{ip_part}:{port_part}"

        # Persist the IP for next session
        ip_file.parent.mkdir(parents=True, exist_ok=True)
        ip_file.write_text(f"{ip_part}:{port_part}")

        # Update environment
        os.environ["REDCLAW_LLM_URL"] = new_url

        # Also update the link.txt so /link stays in sync
        link_file = Path.home() / ".redclaw" / "link.txt"
        link_file.write_text(new_url)

        # Hot-reload runtime
        if self._runtime:
            self._runtime._config.llm_endpoint = new_url
            try:
                import asyncio
                health = asyncio.run(self._runtime.initialize())
                reachable = health.get("status") == "ready"
                if reachable:
                    self._console.print(
                        f"[success]✅ Model IP updated and connected:[/]\n"
                        f"   [info]IP: {ip_part}[/]\n"
                        f"   [info]Port: {port_part}[/]\n"
                        f"   [info]Endpoint: {new_url}[/]\n"
                        f"   [success]🟢 Model reachable![/]"
                    )
                else:
                    self._console.print(
                        f"[warning]⚠️  Model IP updated but unreachable:[/]\n"
                        f"   [info]{new_url}[/]\n"
                        f"   [warning]🟡 Is the model running? Check GCP VM.[/]"
                    )
            except Exception:
                self._console.print(
                    f"[success]✅ Model IP updated:[/]\n"
                    f"   [info]{new_url}[/]\n"
                    f"   [dim]Saved to {ip_file}[/]"
                )
        else:
            self._console.print(
                f"[success]✅ Model IP updated:[/]\n"
                f"   [info]{new_url}[/]\n"
                f"   [dim]Saved to {ip_file}[/]"
            )

    def _cmd_model(self, args: list[str]) -> None:
        """Switch between model backends: qwen (GCP IP) or phi (ngrok tunnel).

        Usage:
            /model          → show current active model
            /model qwen     → switch to Qwen2.5-Coder-32B (uses /ip_m address)
            /model phi      → switch to Phi-4 (uses /link ngrok URL)
        """
        model_file = Path.home() / ".redclaw" / "active_model.txt"
        ip_file = Path.home() / ".redclaw" / "model_ip.txt"
        link_file = Path.home() / ".redclaw" / "link.txt"

        # ── Model profiles ──
        profiles = {
            "qwen": {
                "display": "Qwen2.5-Coder-32B",
                "model_name": "qwen-coder",
                "source": "GCP Compute Engine (IP)",
                "icon": "🟢",
            },
            "phi": {
                "display": "Phi-4",
                "model_name": "phi-4",
                "source": "Kaggle (ngrok tunnel)",
                "icon": "🔵",
            },
        }

        if not args:
            # Show current model
            active = "qwen"  # default
            if model_file.exists():
                active = model_file.read_text().strip().lower()

            profile = profiles.get(active, profiles["qwen"])

            # Show saved endpoints
            saved_ip = ip_file.read_text().strip() if ip_file.exists() else None
            saved_link = link_file.read_text().strip() if link_file.exists() else None
            current_endpoint = None
            if self._runtime:
                status = self._runtime.get_status()
                current_endpoint = status.get("llm_endpoint")

            lines = [
                f"[info]Active Model[/]:   {profile['icon']} {profile['display']}",
                f"[info]Model Name[/]:     {profile['model_name']}",
                f"[info]Source[/]:          {profile['source']}",
                f"[info]Endpoint[/]:        {current_endpoint or '[dim]not set[/]'}",
                "",
                f"[dim]Qwen IP[/]:    {saved_ip or '[dim]not set — use /ip_m[/]'}",
                f"[dim]Phi URL[/]:    {saved_link or '[dim]not set — use /link[/]'}",
                "",
                "[dim]Switch: /model qwen | /model phi[/]",
            ]

            self._console.print(Panel(
                "\n".join(lines),
                title="[bold]Model Configuration[/]",
                border_style="red",
            ))
            return

        # ── Switch model ──
        choice = args[0].strip().lower()

        if choice not in profiles:
            self._console.print(
                f"[error]Unknown model: '{choice}'. Available: qwen, phi[/]"
            )
            return

        profile = profiles[choice]

        # Determine endpoint based on model choice
        if choice == "qwen":
            # Use saved IP or default
            if ip_file.exists():
                saved_ip = ip_file.read_text().strip()
                new_url = f"http://{saved_ip}" if not saved_ip.startswith("http") else saved_ip
            else:
                new_url = "http://35.223.143.247:8002"
                self._console.print(
                    "[dim]No saved IP. Using default. Set with /ip_m <ip>[/]"
                )
        else:  # phi
            if link_file.exists():
                new_url = link_file.read_text().strip()
            else:
                new_url = "https://placeholder.ngrok-free.app"
                self._console.print(
                    "[warning]⚠️ No ngrok URL saved. Set with /link <url>[/]"
                )

        model_name = profile["model_name"]

        # Save active model choice
        model_file.parent.mkdir(parents=True, exist_ok=True)
        model_file.write_text(choice)

        # Update environment
        os.environ["REDCLAW_LLM_URL"] = new_url
        os.environ["REDCLAW_LLM_MODEL"] = model_name

        # Hot-reload runtime
        if self._runtime:
            self._runtime._config.llm_endpoint = new_url
            self._runtime._config.llm_model = model_name
            try:
                import asyncio
                health = asyncio.run(self._runtime.initialize())
                reachable = health.get("status") == "ready"
                if reachable:
                    self._console.print(
                        f"[success]✅ Switched to {profile['icon']} {profile['display']}:[/]\n"
                        f"   [info]Model: {model_name}[/]\n"
                        f"   [info]Endpoint: {new_url}[/]\n"
                        f"   [success]🟢 Connected![/]"
                    )
                else:
                    self._console.print(
                        f"[warning]⚠️  Switched to {profile['display']} but unreachable:[/]\n"
                        f"   [info]{new_url}[/]\n"
                        f"   [warning]🟡 Check {'GCP VM' if choice == 'qwen' else 'ngrok tunnel'}[/]"
                    )
            except Exception:
                self._console.print(
                    f"[success]✅ Switched to {profile['display']}:[/]\n"
                    f"   [info]Endpoint: {new_url}[/]"
                )
        else:
            self._console.print(
                f"[success]✅ Model set to {profile['display']}:[/]\n"
                f"   [info]{new_url}[/]\n"
                f"   [dim]Will take effect on next task[/]"
            )

    def _cmd_clear(self, args: list[str]) -> None:
        self._console.clear()
        self._console.print(BANNER)

    def _cmd_quit(self, args: list[str]) -> None:
        self._console.print("[dim]Shutting down RedClaw...[/]")
        if self._state:
            self._state.checkpoint()
        if self._runtime:
            self._runtime.shutdown()
        self._running = False

    # ── Natural language processing ───────────────────────────────────────

    def _handle_natural_language(self, text: str) -> None:
        """Process natural language input through the ReAct agent loop."""
        self._console.print(f"\n[agent]◆ Processing[/]: {text}\n")

        if not self._runtime:
            self._console.print(
                "[warning]OpenClaw runtime not initialized. "
                "Agent processing unavailable.[/]"
            )
            return

        # Build context from current state
        context = {}
        if self._state:
            state = self._state.state
            context["findings"] = [
                {"title": f.title, "severity": f.severity}
                for f in state.global_findings
            ]
        if self._config:
            try:
                cfg = self._config._config
                context["targets"] = list(cfg.targets.include)
                context["scope"] = list(cfg.targets.include)
            except Exception:
                pass

        async def _run():
            async for msg in self._runtime.run_task(text, context=context):
                if msg.role == "system":
                    content = msg.content
                    # Clean up error messages for user display
                    if "LLM error" in content or "All LLM providers failed" in content:
                        self._console.print(
                            "\n[error]❌ Cannot reach LLM backend.[/]\n"
                            "[warning]  Possible causes:[/]\n"
                            "  • Kaggle notebook not running or ngrok tunnel expired\n"
                            "  • Wrong ngrok URL — use [bold]/link <new-url>[/] to update\n"
                            "  • No local Ollama fallback available\n"
                            "[dim]  Run /agent for detailed provider health.[/]"
                        )
                    else:
                        self._console.print(f"  [phase]{content}[/]")
                elif msg.role == "thinking":
                    self._console.print(f"  [tool]{msg.content}[/]")
                elif msg.role == "tool":
                    # Show tool result summary
                    tool_name = msg.metadata.get("tool", "?")
                    success = msg.metadata.get("success", False)
                    icon = "✓" if success else "✗"
                    style = "success" if success else "error"
                    self._console.print(
                        f"  [{style}]{icon} {tool_name}[/]: "
                        f"{msg.content[:300]}{'...' if len(msg.content) > 300 else ''}"
                    )
                elif msg.role == "assistant":
                    if msg.is_final:
                        # Final answer — render as rich markdown
                        self._console.print()
                        self._console.print(Panel(
                            Markdown(msg.content),
                            title="[bold]Agent Response[/]",
                            border_style="green",
                        ))
                        if meta := msg.metadata:
                            self._console.print(
                                f"  [dim]({meta.get('iteration', '?')} iterations, "
                                f"{meta.get('total_time', '?')})[/]"
                            )
                    else:
                        # Intermediate thinking
                        self._console.print(f"  [agent]◆[/] {msg.content[:500]}")

        try:
            asyncio.run(_run())
        except Exception as e:
            err_str = str(e)
            if "All LLM providers failed" in err_str or "LLM" in err_str:
                self._console.print(
                    "\n[error]❌ Cannot reach LLM backend.[/]\n"
                    "[dim]  Use /link <url> to set a new ngrok URL, "
                    "or /agent for health details.[/]"
                )
            else:
                self._console.print(f"[error]Agent error: {err_str[:200]}[/]")

    # ── System status ─────────────────────────────────────────────────────

    def _show_system_status(self) -> None:
        """Show system status on startup — reflects REAL health."""
        items = [
            ("State Manager", self._state is not None),
            ("Config Manager", self._config is not None),
            ("GuardianRails", self._guardian is not None),
        ]

        table = Table(show_header=False, border_style="dim", pad_edge=False)
        table.add_column("Component")
        table.add_column("Status", justify="center")

        for name, ready in items:
            status = "[success]✓[/]" if ready else "[warning]○[/]"
            table.add_row(name, status)

        # OpenClaw Runtime — show REAL health
        if self._runtime:
            rt_status = self._runtime.get_status()
            health = rt_status.get('health', 'not_initialized')
            if health == 'ready':
                table.add_row("OpenClaw Runtime", "[success]✓ Ready[/]")
            elif health == 'degraded':
                table.add_row("OpenClaw Runtime", "[warning]⚠ Degraded (LLM unreachable)[/]")
            else:
                table.add_row("OpenClaw Runtime", "[error]✗ Not initialized[/]")

            # Show endpoint being used
            table.add_row("LLM Endpoint", f"[dim]{rt_status.get('llm_endpoint', '?')}[/]")
        else:
            table.add_row("OpenClaw Runtime", "[error]✗ Missing[/]")

        self._console.print(Panel(table, title="System Status", border_style="red"))


def _build_runtime():
    """Build the full runtime stack with ToolBridge wired to all MCP servers."""
    import os
    from ..openclaw_bridge.runtime import OpenClawRuntime, RuntimeConfig
    from ..openclaw_bridge.tool_bridge import ToolBridge
    from ..core.guardian import GuardianRails
    # Original 10 MCP servers
    from ..mcp_servers.nmap_server import NmapServer
    from ..mcp_servers.masscan_server import MasscanServer
    from ..mcp_servers.nuclei_server import NucleiServer
    from ..mcp_servers.metasploit_server import MetasploitServer
    from ..mcp_servers.sqlmap_server import SQLMapServer
    from ..mcp_servers.hydra_server import HydraServer
    from ..mcp_servers.bloodhound_server import BloodHoundServer
    from ..mcp_servers.peas_servers import LinPEASServer, WinPEASServer
    from ..mcp_servers.custom_exploit_server import CustomExploitServer
    # New agentic core tools (3 servers, 6 tools)
    from ..mcp_servers.terminal_server import TerminalServer
    from ..mcp_servers.agent_control_server import AgentControlServer
    from ..mcp_servers.file_server import FileServer

    # ── Load active model profile from ~/.redclaw/active_model.txt ──────────
    # /model command saves "qwen" or "phi" here
    model_file = Path.home() / ".redclaw" / "active_model.txt"
    active_model = "qwen"  # default
    if model_file.exists():
        active_model = model_file.read_text().strip().lower()

    # ── Resolve endpoint based on active model ────────────────────────────
    link_file = Path.home() / ".redclaw" / "link.txt"
    ip_file = Path.home() / ".redclaw" / "model_ip.txt"

    if active_model == "phi":
        # Phi-4 mode: use ngrok URL from link.txt
        model_name = "phi-4"
        default_url = "https://placeholder.ngrok-free.app"
        if link_file.exists():
            saved = link_file.read_text().strip()
            if saved:
                default_url = saved
        os.environ.setdefault("REDCLAW_LLM_URL", default_url)
        os.environ.setdefault("REDCLAW_LLM_MODEL", model_name)
    else:
        # Qwen mode (default): use GCP IP from model_ip.txt
        model_name = "qwen-coder"
        default_url = "http://35.223.143.247:8002"
        # First try link.txt as base
        if link_file.exists():
            saved = link_file.read_text().strip()
            if saved:
                default_url = saved
        # model_ip.txt takes priority over link.txt for qwen
        if ip_file.exists():
            saved_ip = ip_file.read_text().strip()
            if saved_ip:
                default_url = f"http://{saved_ip}" if not saved_ip.startswith("http") else saved_ip
        os.environ.setdefault("REDCLAW_LLM_URL", default_url)
        os.environ.setdefault("REDCLAW_LLM_MODEL", model_name)

    # Config from environment or defaults
    config = RuntimeConfig(
        llm_endpoint=os.environ.get("REDCLAW_LLM_URL", default_url),
        llm_model=os.environ.get("REDCLAW_LLM_MODEL", model_name),
        llm_api_key=os.environ.get("REDCLAW_LLM_KEY"),
    )

    # Create guardian
    guardian = GuardianRails()

    # Create runtime
    runtime = OpenClawRuntime(config)

    # Create and wire ToolBridge with all MCP servers (13 total)
    bridge = ToolBridge(guardian=guardian)
    bridge.register_servers({
        # ── Scanning & Recon ──
        "nmap": NmapServer(),
        "masscan": MasscanServer(),
        "nuclei": NucleiServer(),
        # ── Exploitation ──
        "metasploit": MetasploitServer(),
        "sqlmap": SQLMapServer(),
        "hydra": HydraServer(),
        "custom_exploit": CustomExploitServer(),
        # ── Post-Exploitation ──
        "bloodhound": BloodHoundServer(),
        "linpeas": LinPEASServer(),
        "winpeas": WinPEASServer(),
        # ── Agentic Core (NEW) ──
        "terminal": TerminalServer(),
        "agent_control": AgentControlServer(),
        "file_ops": FileServer(),
    })
    runtime.register_tool_bridge(bridge)

    # ── Eagerly initialize OpenClaw so /status shows Ready ─────────────────
    import asyncio
    try:
        asyncio.run(runtime.initialize())
    except Exception:
        # If initialize fails, that's OK — runtime will retry on first task
        pass

    return runtime, guardian, config


def main() -> None:
    """Entry point for the CLI."""
    # ── Logging: console + file during TESTING phase ──────────────────────
    # TODO: When testing is complete, switch to file-only logging to hide
    # internal logs from end users. For now, keep console output so errors
    # are visible during development/debugging.
    log_dir = Path.home() / ".redclaw" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "redclaw.log"

    # Console handler (visible to user — needed during testing)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    # Also log to file for persistent debugging
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    ))
    logging.getLogger().addHandler(file_handler)

    # ── Zero-touch bootstrap: auto-setup on first run ─────────────────────
    # Runs doctor + installs missing tools + installs Claude Code CLI.
    # Subsequent launches fast-path via marker file (~/.redclaw/.initialized).
    try:
        from ..core.bootstrap import ensure_ready
        bootstrap_status = ensure_ready(quiet=False)
        logger.info(f"Bootstrap: {bootstrap_status}")
    except Exception as e:
        logger.warning(f"Bootstrap skipped: {e}")

    # Handle subcommands
    if len(sys.argv) > 1:
        subcmd = sys.argv[1].lower()

        # `redclaw proxy` — start the reverse proxy
        if subcmd == "proxy":
            from ..proxy.server import start_proxy
            import os
            backend = (
                sys.argv[2] if len(sys.argv) > 2
                else os.environ.get(
                    "REDCLAW_LLM_URL",
                    "https://0b2f-34-29-72-116.ngrok-free.app"
                )
            )
            port = int(sys.argv[3]) if len(sys.argv) > 3 else 8080
            start_proxy(backend_url=backend, port=port)
            return

        # `redclaw agent <task>` — one-shot agent task
        if subcmd == "agent":
            task = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "Run a health check"
            runtime, guardian, _ = _build_runtime()

            async def _run():
                await runtime.initialize()
                async for msg in runtime.run_task(task):
                    role = msg.role
                    if role == "system":
                        print(f"[SYS] {msg.content}")
                    elif role == "thinking":
                        print(f"  🔧 {msg.content}")
                    elif role == "tool":
                        icon = "✓" if msg.metadata.get('success') else "✗"
                        print(f"  {icon} {msg.metadata.get('tool', '?')}: {msg.content[:200]}")
                    elif role == "assistant":
                        if msg.is_final:
                            print(f"\n{'='*60}")
                            print(msg.content)
                            print(f"{'='*60}")
                        else:
                            print(f"  ◆ {msg.content[:300]}")

            asyncio.run(_run())
            return

        # `redclaw skin` — launch Claude Code with RedClaw skin
        if subcmd == "skin":
            from ..claude_skin.launcher import ClaudeCodeLauncher
            targets = sys.argv[2:] if len(sys.argv) > 2 else []
            launcher = ClaudeCodeLauncher(targets=targets)
            exit_code = launcher.launch()
            sys.exit(exit_code)

        # `redclaw doctor` — health-check all tools
        if subcmd == "doctor":
            from rich.console import Console as RichConsole
            console = RichConsole(theme=REDCLAW_THEME)
            console.print(BANNER)
            try:
                from ..tooling.doctor import DoctorReport
                doctor = DoctorReport()
                doctor.run()
            except Exception as e:
                console.print(f"[error]Doctor failed: {e}[/]")
            return

        # `redclaw setup-tools` — auto-install missing tools
        if subcmd in ("setup-tools", "setup_tools"):
            from rich.console import Console as RichConsole
            console = RichConsole(theme=REDCLAW_THEME)
            console.print(BANNER)
            mode = sys.argv[2] if len(sys.argv) > 2 else "interactive"
            try:
                from ..tooling.installer import ToolInstaller
                dry = (mode == "dry-run")
                installer = ToolInstaller(dry_run=dry)
                results = installer.install_missing()
                for r in results:
                    if r.success:
                        console.print(f"  [success]✅ {r.tool.name} — installed via {r.method_used}[/]")
                    else:
                        console.print(f"  [warning]⚠️  {r.tool.name} — {r.error or 'failed'}[/]")
                if not results:
                    console.print("  [success]✅ All tools already installed![/]")
            except Exception as e:
                console.print(f"[error]Setup failed: {e}[/]")
            return

    # Default: interactive CLI
    from ..core.config import ConfigManager
    from ..core.state import StateManager

    runtime, guardian, _ = _build_runtime()

    # Attempt to load engagement config
    config = None
    config_candidates = ["engagement.yaml", "engagement.yml", "redclaw.yaml"]
    for candidate in config_candidates:
        if Path(candidate).exists():
            try:
                config = ConfigManager.from_file(candidate)
                break
            except Exception:
                pass

    state = StateManager()

    cli = RedClawCLI(
        config_manager=config,
        state_manager=state,
        runtime=runtime,
        guardian=guardian,
    )
    cli.run()


if __name__ == "__main__":
    main()
