"""
RedClaw CLI — Claude Code-style enterprise pentesting terminal.

Visually mirrors Claude Code's interface:
  - Welcome panel with mascot + version info (left) and tips (right)
  - Streaming agent output with live task panels
  - Bottom status bar with keyboard shortcuts
  - All slash commands for pentest operations + LLM reliability monitoring
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from rich.columns import Columns
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .mascot import get_mascot, get_model_badge, get_version_badge
from .theme import PROMPT_STYLE, REDCLAW_THEME

logger = logging.getLogger("redclaw.cli")


# ── Slash Commands ────────────────────────────────────────────────────────────

SLASH_COMMANDS = {
    "/help": "Show available commands",
    "/pentest": "Full autonomous pentest (scan → exploit → zero-day → report)",
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
    "/link": "View/update LLM backend endpoint URL",
    "/apikey": "Set or view API key for LLM provider",
    "/ip_m": "Update model IP when GCP restarts",
    "/model": "Switch active model: /model gemini | openai | groq",
    "/monitor": "LLM reliability dashboard (retry stats, costs, health)",
    "/providers": "Show provider failover chain status",
    "/budget": "Show LLM cost tracking and budget",
    "/clear": "Clear the terminal",
    "/quit": "Exit RedClaw",
}


class RedClawCLI:
    """
    Enterprise CLI for autonomous pentesting — Claude Code visual design.

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
        llm_client=None,
    ):
        self._console = Console(theme=REDCLAW_THEME)
        self._config = config_manager
        self._state = state_manager
        self._runtime = runtime
        self._orchestrator = orchestrator
        self._guardian = guardian
        self._llm_client = llm_client
        self._running = False
        self._history_file = Path.home() / ".redclaw_history"

        # Command completer
        self._completer = WordCompleter(
            list(SLASH_COMMANDS.keys()) + ["nmap", "masscan", "nuclei", "metasploit"],
            ignore_case=True,
        )
        logger.info("RedClaw CLI initialized")

    # ── Welcome Screen (Claude Code Layout) ──────────────────────────────

    def _show_welcome(self) -> None:
        """Show Claude Code-style welcome screen with mascot and tips."""
        width = self._console.width or 100

        # ── Left Panel: Mascot + Version ──
        mascot = get_mascot(width)
        version_badge = get_version_badge()

        # Get active model info
        model_file = Path.home() / ".redclaw" / "active_model.txt"
        active_model = "gemini"
        if model_file.exists():
            active_model = model_file.read_text().strip().lower()

        model_display = {
            "gemini": "Gemini 2.5 Flash",
            "openai": "GPT-4o-mini",
            "groq": "Llama 3.3 70B",
            "openrouter": "Qwen 2.5 Coder",
            "gpt-oss": "GPT-OSS 120B (Free)",
            "dolphin": "Dolphin Mistral 24B",
            "nemotron": "Nemotron 3 Nano 30B",
            "qwen": "Qwen (self-hosted)",
            "phi": "Phi-4 (self-hosted)",
        }.get(active_model, active_model)

        model_badge = get_model_badge(model_display, "API Usage")

        left_content = (
            f"[bold #ff4444]Welcome![/]\n\n"
            f"{mascot}\n"
            f"  {model_badge}\n"
            f"  {version_badge}"
        )

        # ── Right Panel: Tips + Recent Activity ──
        right_content = (
            "[bold #ffaa00]Tips for getting started[/]\n"
            "  Run [bold]/pentest <target_ip>[/] to start autonomous pentesting\n"
            "  Run [bold]/model[/] to switch LLM provider\n"
            "  Run [bold]/doctor[/] to check tool dependencies\n"
            "  Run [bold]/monitor[/] to view LLM reliability dashboard\n\n"
            "[bold #ffaa00]Recent activity[/]\n"
        )

        # Check for recent engagements
        engagement_dir = Path.home() / ".redclaw" / "engagements"
        if engagement_dir.exists():
            engagements = sorted(engagement_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:3]
            if engagements:
                for eng in engagements:
                    right_content += f"  [dim]{eng.name}[/]\n"
            else:
                right_content += "  [dim]No recent activity[/]\n"
        else:
            right_content += "  [dim]No recent activity[/]\n"

        # ── Combine in Claude Code layout ──
        if width >= 90:
            left_panel = Panel(
                left_content,
                border_style="#ff4444",
                width=width // 2 - 2,
                padding=(1, 2),
            )
            right_panel = Panel(
                right_content,
                border_style="dim",
                width=width // 2 - 2,
                padding=(1, 2),
            )
            self._console.print(Columns([left_panel, right_panel], padding=1))
        else:
            self._console.print(Panel(left_content + "\n\n" + right_content, border_style="#ff4444"))

        # ── Model switch hint ──
        self._console.print(
            f"\n  [dim]/model to switch providers  ·  /help for all commands[/]\n"
        )

    # ── Main REPL ────────────────────────────────────────────────────────

    def run(self) -> None:
        """Start the interactive CLI REPL."""
        self._show_welcome()
        self._running = True

        session: PromptSession = PromptSession(
            history=FileHistory(str(self._history_file)),
            auto_suggest=AutoSuggestFromHistory(),
            completer=self._completer,
            style=PROMPT_STYLE,
        )

        # Bottom bar hint
        self._console.print(
            "[bar.key]> [/][dim]Type a command or natural language instruction[/]\n"
        )

        while self._running:
            try:
                user_input = session.prompt(
                    [("class:prompt", "> ")],
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
            "/pentest": self._cmd_pentest,
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
            "/apikey": self._cmd_apikey,
            "/ip_m": self._cmd_ip_m,
            "/model": self._cmd_model,
            "/monitor": self._cmd_monitor,
            "/providers": self._cmd_providers,
            "/budget": self._cmd_budget,
            "/clear": self._cmd_clear,
            "/quit": self._cmd_quit,
        }

        handler = handlers.get(cmd)
        if handler:
            handler(args)
        else:
            self._console.print(f"[error]Unknown command: {cmd}. Type /help for options.[/]")

    # ── Command Handlers ─────────────────────────────────────────────────

    def _cmd_help(self, args: list[str]) -> None:
        table = Table(title="RedClaw Commands", style="red", border_style="dim")
        table.add_column("Command", style="bold")
        table.add_column("Description")
        for cmd, desc in SLASH_COMMANDS.items():
            table.add_row(cmd, desc)
        self._console.print(table)

    def _cmd_pentest(self, args: list[str]) -> None:
        """Run full autonomous pentest pipeline."""
        target = args[0] if args else None
        if not target:
            self._console.print(
                Panel(
                    "[warning]Usage:[/] /pentest <target_ip>\n\n"
                    "[dim]Example: /pentest 192.168.1.83[/]\n\n"
                    "Runs the full 10-phase autonomous pentest pipeline:\n"
                    "  1. Brain Planning\n"
                    "  2. Port Scan (nmap or Python scanner)\n"
                    "  3. KnowledgeGraph\n"
                    "  4. Brain CVE Analysis\n"
                    "  5. Hands Exploit Code Generation\n"
                    "  6. Exploitation (FTP, HTTP, VNC, MySQL, etc.)\n"
                    "  7. Zero-Day Hunting (fuzzing, protocol abuse)\n"
                    "  8. Post-Exploitation\n"
                    "  9. Brain Executive Summary\n"
                    "  10. CausalChain Report\n",
                    title="[bold red]Full Autonomous Pentest[/]",
                    border_style="red",
                )
            )
            return

        self._console.print(
            Panel(
                f"[warning]TARGET:[/] [bold]{target}[/]\n\n"
                "This will run the full autonomous pentest pipeline\n"
                "including exploitation and zero-day hunting.\n\n"
                "Type 'yes' to proceed.",
                title="[bold red]Autonomous Pentest Confirmation[/]",
                border_style="red",
            )
        )
        try:
            answer = input("Proceed? [yes/no] > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "no"

        if answer != "yes":
            self._console.print("[dim]Pentest cancelled.[/]")
            return

        api_key = os.environ.get(
            "OPENROUTER_API_KEY",
            os.environ.get("REDCLAW_LLM_KEY", "")
        )

        self._console.print(f"\n[tool]Starting full pentest[/] on [bold]{target}[/]...")
        self._console.print("[dim]All 10 phases will run autonomously.[/]\n")

        async def _run_pentest():
            from ..pentest import RedClawPentest
            pentest = RedClawPentest(target=target, api_key=api_key)
            await pentest.run()

        try:
            asyncio.run(_run_pentest())
            self._console.print("\n[success]Pentest completed. Check ~/.redclaw/engagements/ for reports.[/]")
        except Exception as e:
            self._console.print(f"[error]Pentest failed: {e}[/]")

    def _cmd_status(self, args: list[str]) -> None:
        panel_content = []
        if self._state:
            state = self._state.state
            phase_status = self._state.get_phase_status(self._state.current_phase)
            panel_content.append(f"[phase]Phase[/]: {state.current_phase}")
            panel_content.append(f"[info]Status[/]: {phase_status}")
            panel_content.append(f"[info]Findings[/]: {len(state.global_findings)}")
        else:
            panel_content.append("[dim]No active engagement[/]")

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
            providers = status.get('health_providers', {})
            if providers:
                for name, info in providers.items():
                    reachable = info.get('reachable', False)
                    icon = '✅' if reachable else '❌'
                    panel_content.append(f"  {icon} {name}: {'reachable' if reachable else 'unreachable'}")
            panel_content.append(f"[tool]Tools[/]: {status.get('tool_bridge', 'none')}")

        # LLM Client health
        if self._llm_client:
            report = self._llm_client.get_health_report()
            health = report.get("health", {})
            panel_content.append(f"\n[agent]LLM Client[/]:")
            panel_content.append(f"  Success Rate: {health.get('success_rate', 'N/A')}")
            panel_content.append(f"  Avg Latency: {health.get('avg_latency', 'N/A')}")
            panel_content.append(f"  Total Calls: {health.get('total_calls', 0)}")

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
            "critical": "finding.critical", "high": "finding.high",
            "medium": "finding.medium", "low": "finding.low", "info": "finding.info",
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
        table = Table(title="MCP Tool Servers", border_style="dim")
        table.add_column("Tool", style="tool")
        table.add_column("Description")
        table.add_column("Status", justify="center")
        installed = 0
        for name, desc, binary in tools_meta:
            if binary is None:
                table.add_row(name, desc, "🟢 Ready")
                installed += 1
            elif shutil.which(binary):
                table.add_row(name, desc, "🟢 Ready")
                installed += 1
            else:
                table.add_row(name, desc, "🔴 Not installed")
        self._console.print(table)
        total = len(tools_meta)
        self._console.print(f"[dim]{installed}/{total} tools available. Use /setup-tools to install missing.[/]")

    def _cmd_sessions(self, args: list[str]) -> None:
        self._console.print(Panel(
            "[info]Local Session[/]: 🟢 Active\n"
            "[info]Remote Session[/]: 🔴 Not connected\n"
            "[dim]Use 'connect <host> <user> <pass>' to establish SSH session[/]",
            title="Sessions", border_style="dim",
        ))

    def _cmd_guardian(self, args: list[str]) -> None:
        if self._guardian:
            stats = self._guardian.get_stats()
            self._console.print(Panel(
                f"Total commands: {stats['total_commands']}\n"
                f"Blocked: {stats['blocked']}\n"
                f"Allowed: {stats['allowed']}\n"
                f"Block rate: {stats['block_rate']}",
                title="GuardianRails Statistics", border_style="yellow",
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
        backend = args[0] if args else os.environ.get("REDCLAW_LLM_URL", "https://0b2f-34-29-72-116.ngrok-free.app")
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
        if pstats := status.get('provider_stats'):
            panel_lines.append(f"\n[agent]Provider[/]: {pstats.get('active_provider', 'N/A')}")
            panel_lines.append(f"[info]Requests[/]: {pstats.get('total_requests', 0)}")
            panel_lines.append(f"[info]Tokens[/]: {pstats.get('total_tokens', 0)}")
        if self._runtime.provider:
            health = self._runtime.provider.health_check()
            panel_lines.append("\n[phase]Health Check[/]:")
            for name, info in health.items():
                icon = '🟢' if info.get('reachable') else '🔴'
                panel_lines.append(f"  {icon} {name}")
        self._console.print(Panel("\n".join(panel_lines), title="[bold]Agent Loop Status[/]", border_style="cyan"))

    def _cmd_skin(self, args: list[str]) -> None:
        """Launch Claude Code with RedClaw pentesting skin."""
        from ..claude_skin.launcher import ClaudeCodeLauncher
        targets = args if args else []
        launcher = ClaudeCodeLauncher(targets=targets, enable_guardian=self._guardian is not None)
        if not launcher.check_claude_installed():
            self._console.print(
                "[error]Claude Code CLI not found.[/]\n"
                "Install: [tool]npm install -g @anthropic-ai/claude-code[/]\n"
                "Or use RedClaw standalone mode (current)."
            )
            return
        self._console.print("[agent]Launching Claude Code with RedClaw skin...[/]")
        self._running = False
        exit_code = launcher.launch()
        if exit_code != 0:
            self._console.print(f"[warning]Claude Code exited with code {exit_code}[/]")

    def _cmd_doctor(self, args: list[str]) -> None:
        try:
            from ..tooling.doctor import DoctorReport
            doctor = DoctorReport()
            doctor.run()
        except ImportError:
            self._console.print("[error]Tooling module not available.[/]")
        except Exception as e:
            self._console.print(f"[error]Doctor failed: {e}[/]")

    def _cmd_setup_tools(self, args: list[str]) -> None:
        mode = args[0] if args else "interactive"
        try:
            from ..tooling.installer import ToolInstaller
            installer = ToolInstaller()
            dry_run = mode == "dry-run"
            auto = mode == "auto"
            installer.install_all(console=self._console, dry_run=dry_run, auto_approve=auto)
        except ImportError:
            self._console.print("[error]Tooling module not available.[/]")
        except Exception as e:
            self._console.print(f"[error]Setup failed: {e}[/]")

    def _cmd_link(self, args: list[str]) -> None:
        link_file = Path.home() / ".redclaw" / "link.txt"
        if not args:
            current = os.environ.get("REDCLAW_LLM_URL", None)
            saved = link_file.read_text().strip() if link_file.exists() else None
            runtime_url = None
            if self._runtime:
                status = self._runtime.get_status()
                runtime_url = status.get("llm_endpoint")
            self._console.print(Panel(
                f"[info]Active URL[/]:  {runtime_url or current or '[dim]not set[/]'}\n"
                f"[info]Saved URL[/]:   {saved or '[dim]none[/]'}\n\n"
                "[dim]Usage: /link <ngrok_url>[/]",
                title="[bold]LLM Backend Link[/]", border_style="red",
            ))
            return
        new_url = args[0].strip()
        if not new_url.startswith("http"):
            new_url = f"https://{new_url}"
        os.environ["REDCLAW_LLM_URL"] = new_url
        link_file.parent.mkdir(parents=True, exist_ok=True)
        link_file.write_text(new_url)
        if self._runtime:
            self._runtime._config.llm_endpoint = new_url
            try:
                health = asyncio.run(self._runtime.initialize())
                if health.get("status") == "ready":
                    self._console.print(f"[success]✅ URL updated & connected:[/]\n   [info]{new_url}[/]")
                else:
                    self._console.print(f"[warning]⚠️  URL updated but unreachable:[/]\n   [info]{new_url}[/]")
            except Exception:
                self._console.print(f"[success]✅ URL updated:[/]\n   [info]{new_url}[/]")
        else:
            self._console.print(f"[success]✅ URL updated:[/]\n   [info]{new_url}[/]")

    def _cmd_apikey(self, args: list[str]) -> None:
        key_file = Path.home() / ".redclaw" / "api_key.txt"
        if not args:
            env_key = os.environ.get("REDCLAW_LLM_KEY")
            file_key = key_file.read_text().strip() if key_file.exists() else None
            active_key = env_key or file_key
            if active_key:
                masked = active_key[:4] + "..." + active_key[-4:] if len(active_key) > 12 else active_key[:4] + "..."
                source = "env REDCLAW_LLM_KEY" if env_key else f"{key_file}"
                self._console.print(Panel(
                    f"[info]API Key[/]:    {masked}\n[info]Source[/]:     {source}",
                    title="[bold]API Key[/]", border_style="red",
                ))
            else:
                self._console.print(Panel(
                    "[warning]No API key configured.[/]\n\n"
                    "[dim]Usage: /apikey <your-api-key>[/]\n"
                    "[dim]Get a Gemini key: https://aistudio.google.com/apikey[/]",
                    title="[bold]API Key[/]", border_style="red",
                ))
            return
        new_key = args[0].strip()
        if new_key.lower() == "clear":
            if key_file.exists():
                key_file.unlink()
            if "REDCLAW_LLM_KEY" in os.environ:
                del os.environ["REDCLAW_LLM_KEY"]
            self._console.print("[success]✅ API key cleared.[/]")
            return
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text(new_key)
        os.environ["REDCLAW_LLM_KEY"] = new_key
        masked = new_key[:4] + "..." + new_key[-4:] if len(new_key) > 12 else new_key[:4] + "..."
        self._console.print(f"[success]✅ API key saved:[/]\n   [info]Key: {masked}[/]")

    def _cmd_ip_m(self, args: list[str]) -> None:
        ip_file = Path.home() / ".redclaw" / "model_ip.txt"
        default_port = "8002"
        if not args:
            current_endpoint = None
            if self._runtime:
                status = self._runtime.get_status()
                current_endpoint = status.get("llm_endpoint")
            saved_ip = ip_file.read_text().strip() if ip_file.exists() else None
            self._console.print(Panel(
                f"[info]Active Endpoint[/]:  {current_endpoint or '[dim]not set[/]'}\n"
                f"[info]Saved Model IP[/]:   {saved_ip or '[dim]none[/]'}\n\n"
                "[dim]Usage: /ip_m <ip>[/]",
                title="[bold]Model IP[/]", border_style="red",
            ))
            return
        raw_input = args[0].strip()
        for prefix in ("http://", "https://"):
            if raw_input.startswith(prefix):
                raw_input = raw_input[len(prefix):]
        if ":" in raw_input:
            ip_part, port_part = raw_input.rsplit(":", 1)
        else:
            ip_part, port_part = raw_input, default_port
        new_url = f"http://{ip_part}:{port_part}"
        ip_file.parent.mkdir(parents=True, exist_ok=True)
        ip_file.write_text(f"{ip_part}:{port_part}")
        os.environ["REDCLAW_LLM_URL"] = new_url
        link_file = Path.home() / ".redclaw" / "link.txt"
        link_file.write_text(new_url)
        self._console.print(f"[success]✅ Model IP updated:[/]\n   [info]{new_url}[/]")

    def _cmd_model(self, args: list[str]) -> None:
        """Switch between model backends."""
        model_file = Path.home() / ".redclaw" / "active_model.txt"
        ip_file = Path.home() / ".redclaw" / "model_ip.txt"
        link_file = Path.home() / ".redclaw" / "link.txt"

        profiles = {
            "gemini": {"display": "Gemini 2.5 Flash", "model_name": "gemini-2.5-flash", "endpoint": "https://generativelanguage.googleapis.com/v1beta/openai", "source": "Google AI API", "icon": "🔵", "needs_key": True},
            "openai": {"display": "GPT-4o-mini", "model_name": "gpt-4o-mini", "endpoint": "https://api.openai.com/v1", "source": "OpenAI API", "icon": "🟢", "needs_key": True},
            "groq": {"display": "Llama 3.3 70B", "model_name": "llama-3.3-70b-versatile", "endpoint": "https://api.groq.com/openai/v1", "source": "Groq API", "icon": "🟠", "needs_key": True},
            "openrouter": {"display": "Qwen 2.5 Coder 32B", "model_name": "qwen/qwen-2.5-coder-32b-instruct", "endpoint": "https://openrouter.ai/api/v1", "source": "OpenRouter API", "icon": "🟣", "needs_key": True},
            "gpt-oss": {"display": "GPT-OSS 120B (FREE)", "model_name": "openai/gpt-oss-120b:free", "endpoint": "https://openrouter.ai/api/v1", "source": "OpenRouter (Free)", "icon": "🟢", "needs_key": True},
            "dolphin": {"display": "Dolphin Mistral 24B (FREE)", "model_name": "cognitivecomputations/dolphin-mistral-24b-venice-edition:free", "endpoint": "https://openrouter.ai/api/v1", "source": "OpenRouter (Free)", "icon": "🐬", "needs_key": True},
            "nemotron": {"display": "Nemotron 3 Nano 30B (FREE)", "model_name": "nvidia/nemotron-3-nano-30b-a3b:free", "endpoint": "https://openrouter.ai/api/v1", "source": "OpenRouter (Free)", "icon": "🟩", "needs_key": True},
            "qwen": {"display": "Qwen2.5-Coder-32B (self-hosted)", "model_name": "qwen-coder", "source": "GCP", "icon": "⚪", "needs_key": False},
            "phi": {"display": "Phi-4 (self-hosted)", "model_name": "phi-4", "source": "Kaggle", "icon": "⚪", "needs_key": False},
        }

        if not args:
            active = "gemini"
            if model_file.exists():
                active = model_file.read_text().strip().lower()
            profile = profiles.get(active, profiles["gemini"])
            key_file = Path.home() / ".redclaw" / "api_key.txt"
            has_key = key_file.exists() and key_file.read_text().strip()
            lines = [
                f"[info]Active Model[/]:   {profile['icon']} {profile['display']}",
                f"[info]Model Name[/]:     {profile['model_name']}",
                f"[info]Source[/]:          {profile['source']}",
                f"[info]API Key[/]:         {'✅ Set' if has_key else '❌ Not set — use /apikey <key>'}",
                "",
                "[dim]API Providers:[/]   gemini | openai | groq | openrouter",
                "[dim]Free Models:[/]    gpt-oss | dolphin | nemotron",
                "[dim]Self-hosted:[/]     qwen | phi",
                "",
                "[dim]Switch: /model <name>[/]",
            ]
            self._console.print(Panel("\n".join(lines), title="[bold]Model Configuration[/]", border_style="red"))
            return

        choice = args[0].strip().lower()
        if choice not in profiles:
            self._console.print(f"[error]Unknown model: '{choice}'. Available: {', '.join(profiles.keys())}[/]")
            return

        profile = profiles[choice]
        if "endpoint" in profile:
            new_url = profile["endpoint"]
        elif choice == "qwen":
            new_url = f"http://{ip_file.read_text().strip()}" if ip_file.exists() else "http://35.223.143.247:8002"
        else:
            new_url = link_file.read_text().strip() if link_file.exists() else "https://placeholder.ngrok-free.app"

        model_file.parent.mkdir(parents=True, exist_ok=True)
        model_file.write_text(choice)
        os.environ["REDCLAW_LLM_URL"] = new_url
        os.environ["REDCLAW_LLM_MODEL"] = profile["model_name"]

        if self._runtime:
            self._runtime._config.llm_endpoint = new_url
            self._runtime._config.llm_model = profile["model_name"]

        self._console.print(f"[success]✅ Switched to {profile['icon']} {profile['display']}[/]\n   [info]Endpoint: {new_url}[/]")

    # ── NEW: LLM Reliability Monitoring Commands ─────────────────────────

    def _cmd_monitor(self, args: list[str]) -> None:
        """LLM reliability dashboard."""
        if not self._llm_client:
            self._console.print("[warning]LLM Client not initialized. No monitoring data.[/]")
            return
        report = self._llm_client.get_health_report()
        health = report.get("health", {})
        cost = report.get("cost", {})

        table = Table(title="LLM Reliability Dashboard", border_style="red")
        table.add_column("Metric", style="bold")
        table.add_column("Value")
        table.add_row("Success Rate", str(health.get("success_rate", "N/A")))
        table.add_row("Avg Latency", str(health.get("avg_latency", "N/A")))
        table.add_row("Total Calls", str(health.get("total_calls", 0)))
        table.add_row("Total Errors", str(health.get("total_errors", 0)))
        table.add_row("Total Cost", str(cost.get("total_cost", "$0.0000")))
        table.add_row("Budget Remaining", str(cost.get("budget_remaining", "unlimited")))
        self._console.print(table)

        last = report.get("last_call", {})
        if last:
            self._console.print(f"  [dim]Last call: {last.get('model', '?')} ({last.get('latency', '?')}) — {'✅' if last.get('success') else '❌'}[/]")

    def _cmd_providers(self, args: list[str]) -> None:
        """Show provider failover chain."""
        if not self._llm_client:
            self._console.print("[warning]LLM Client not initialized.[/]")
            return
        report = self._llm_client.get_health_report()
        providers = report.get("providers", [])
        table = Table(title="Provider Failover Chain", border_style="cyan")
        table.add_column("#", style="dim")
        table.add_column("Model", style="bold")
        table.add_column("Description")
        table.add_column("Priority")
        table.add_column("RPM Limit")
        for i, p in enumerate(providers, 1):
            table.add_row(str(i), p["model"], p.get("description", ""), str(p["priority"]), str(p.get("rpm_limit", "?")))
        self._console.print(table)

    def _cmd_budget(self, args: list[str]) -> None:
        """Show cost tracking."""
        if not self._llm_client:
            self._console.print("[warning]LLM Client not initialized.[/]")
            return
        summary = self._llm_client.cost_tracker.get_summary()
        table = Table(title="LLM Cost Tracking", border_style="yellow")
        table.add_column("Metric", style="bold")
        table.add_column("Value")
        table.add_row("Total Cost", str(summary["total_cost"]))
        table.add_row("Total Requests", str(summary["total_requests"]))
        table.add_row("Input Tokens", str(summary["total_input_tokens"]))
        table.add_row("Output Tokens", str(summary["total_output_tokens"]))
        table.add_row("Budget Remaining", str(summary["budget_remaining"]))
        self._console.print(table)
        by_model = summary.get("by_model", {})
        if by_model:
            self._console.print("\n[dim]Cost by model:[/]")
            for model, cost in by_model.items():
                self._console.print(f"  {model}: {cost}")

    def _cmd_clear(self, args: list[str]) -> None:
        self._console.clear()
        self._show_welcome()

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
            except Exception:
                pass

        async def _run():
            async for msg in self._runtime.run_task(text, context=context):
                if msg.role == "system":
                    content = msg.content
                    if "All LLM providers failed" in content or "LLM error" in content:
                        is_rate_limit = "Rate limited" in content or "429" in content
                        if is_rate_limit:
                            self._console.print(
                                "\n[warning]⚠️  Rate limited by provider.[/]\n"
                                "[dim]  Wait a moment or switch: /model gemini[/]"
                            )
                        else:
                            self._console.print(
                                "\n[error]❌ Cannot reach LLM backend.[/]\n"
                                "[dim]  Check: /apikey, /model, /agent[/]"
                            )
                    else:
                        self._console.print(f"  [phase]{content}[/]")
                elif msg.role == "thinking":
                    self._console.print(f"  [tool]{msg.content}[/]")
                elif msg.role == "tool":
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
                        self._console.print(f"  [agent]◆[/] {msg.content[:500]}")

        try:
            asyncio.run(_run())
        except Exception as e:
            err_str = str(e)
            if "Rate limited" in err_str or "429" in err_str:
                self._console.print(
                    "\n[warning]⚠️  Rate limited by provider.[/]\n"
                    "[dim]  Wait a moment or switch: /model gemini[/]"
                )
            elif "LLM" in err_str or "provider" in err_str.lower():
                self._console.print(
                    "\n[error]❌ Cannot reach LLM backend.[/]\n"
                    "[dim]  Check: /apikey, /model, /agent[/]"
                )
            else:
                self._console.print(f"[error]Agent error: {err_str[:200]}[/]")


# ══════════════════════════════════════════════════════════════════════════════
# Runtime Builder + Entry Point (preserved from original)
# ══════════════════════════════════════════════════════════════════════════════


def _build_runtime():
    """Build the full runtime stack with ToolBridge wired to all MCP servers."""
    from ..openclaw_bridge.runtime import OpenClawRuntime, RuntimeConfig
    from ..openclaw_bridge.tool_bridge import ToolBridge
    from ..core.guardian import GuardianRails
    from ..mcp_servers.nmap_server import NmapServer
    from ..mcp_servers.masscan_server import MasscanServer
    from ..mcp_servers.nuclei_server import NucleiServer
    from ..mcp_servers.metasploit_server import MetasploitServer
    from ..mcp_servers.sqlmap_server import SQLMapServer
    from ..mcp_servers.hydra_server import HydraServer
    from ..mcp_servers.bloodhound_server import BloodHoundServer
    from ..mcp_servers.peas_servers import LinPEASServer, WinPEASServer
    from ..mcp_servers.custom_exploit_server import CustomExploitServer
    from ..mcp_servers.terminal_server import TerminalServer
    from ..mcp_servers.agent_control_server import AgentControlServer
    from ..mcp_servers.file_server import FileServer

    model_file = Path.home() / ".redclaw" / "active_model.txt"
    active_model = "gemini"
    if model_file.exists():
        active_model = model_file.read_text().strip().lower()

    provider_table = {
        "gemini":     ("gemini-2.5-flash", "https://generativelanguage.googleapis.com/v1beta/openai"),
        "openai":     ("gpt-4o-mini", "https://api.openai.com/v1"),
        "groq":       ("llama-3.3-70b-versatile", "https://api.groq.com/openai/v1"),
        "openrouter": ("qwen/qwen-2.5-coder-32b-instruct", "https://openrouter.ai/api/v1"),
        "gpt-oss":    ("openai/gpt-oss-120b:free", "https://openrouter.ai/api/v1"),
        "dolphin":    ("cognitivecomputations/dolphin-mistral-24b-venice-edition:free", "https://openrouter.ai/api/v1"),
        "nemotron":   ("nvidia/nemotron-3-nano-30b-a3b:free", "https://openrouter.ai/api/v1"),
    }

    if active_model in provider_table:
        model_name, default_url = provider_table[active_model]
    elif active_model == "phi":
        model_name = "phi-4"
        link_file = Path.home() / ".redclaw" / "link.txt"
        default_url = link_file.read_text().strip() if link_file.exists() else "https://placeholder.ngrok-free.app"
    else:
        model_name = "qwen-coder"
        ip_file = Path.home() / ".redclaw" / "model_ip.txt"
        link_file = Path.home() / ".redclaw" / "link.txt"
        default_url = "http://35.223.143.247:8002"
        if link_file.exists() and link_file.read_text().strip():
            default_url = link_file.read_text().strip()
        if ip_file.exists() and ip_file.read_text().strip():
            saved_ip = ip_file.read_text().strip()
            default_url = f"http://{saved_ip}" if not saved_ip.startswith("http") else saved_ip

    os.environ.setdefault("REDCLAW_LLM_URL", default_url)
    os.environ.setdefault("REDCLAW_LLM_MODEL", model_name)

    config = RuntimeConfig(
        llm_endpoint=os.environ.get("REDCLAW_LLM_URL", default_url),
        llm_model=os.environ.get("REDCLAW_LLM_MODEL", model_name),
    )

    guardian = GuardianRails()
    runtime = OpenClawRuntime(config)

    bridge = ToolBridge(guardian=guardian)
    bridge.register_servers({
        "nmap": NmapServer(), "masscan": MasscanServer(), "nuclei": NucleiServer(),
        "metasploit": MetasploitServer(), "sqlmap": SQLMapServer(),
        "hydra": HydraServer(), "custom_exploit": CustomExploitServer(),
        "bloodhound": BloodHoundServer(), "linpeas": LinPEASServer(), "winpeas": WinPEASServer(),
        "terminal": TerminalServer(), "agent_control": AgentControlServer(), "file_ops": FileServer(),
    })
    runtime.register_tool_bridge(bridge)

    try:
        asyncio.run(runtime.initialize())
    except Exception:
        pass

    # Build LLM Client with provider failover
    from ..router.llm_client import LLMClient
    llm_client = LLMClient()
    llm_client.add_providers_from_env()

    return runtime, guardian, config, llm_client


def main() -> None:
    """Entry point for the CLI."""
    log_dir = Path.home() / ".redclaw" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "redclaw.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    logging.getLogger().addHandler(file_handler)

    # Bootstrap
    try:
        from ..core.bootstrap import ensure_ready
        bootstrap_status = ensure_ready(quiet=False)
        logger.info(f"Bootstrap: {bootstrap_status}")
    except Exception as e:
        logger.warning(f"Bootstrap skipped: {e}")

    # Handle subcommands
    if len(sys.argv) > 1:
        subcmd = sys.argv[1].lower()

        if subcmd == "proxy":
            from ..proxy.server import start_proxy
            backend = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("REDCLAW_LLM_URL", "https://0b2f-34-29-72-116.ngrok-free.app")
            port = int(sys.argv[3]) if len(sys.argv) > 3 else 8080
            start_proxy(backend_url=backend, port=port)
            return

        if subcmd == "agent":
            task = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "Run a health check"
            runtime, guardian, _, llm_client = _build_runtime()
            async def _run():
                await runtime.initialize()
                async for msg in runtime.run_task(task):
                    role = msg.role
                    if role == "system":
                        print(f"[SYS] {msg.content}")
                    elif role == "thinking":
                        print(f"  tool {msg.content}")
                    elif role == "tool":
                        icon = "+" if msg.metadata.get('success') else "x"
                        print(f"  {icon} {msg.metadata.get('tool', '?')}: {msg.content[:200]}")
                    elif role == "assistant":
                        if msg.is_final:
                            print(f"\n{'='*60}")
                            print(msg.content)
                            print(f"{'='*60}")
                        else:
                            print(f"  > {msg.content[:300]}")
            asyncio.run(_run())
            return

        if subcmd == "pentest":
            target = sys.argv[2] if len(sys.argv) > 2 else None
            if not target:
                print("Usage: redclaw pentest <TARGET_IP>")
                sys.exit(1)
            api_key = os.environ.get("OPENROUTER_API_KEY", os.environ.get("REDCLAW_LLM_KEY", ""))
            async def _run_pentest():
                from ..pentest import RedClawPentest
                pentest = RedClawPentest(target=target, api_key=api_key)
                await pentest.run()
            asyncio.run(_run_pentest())
            return

        if subcmd == "skin":
            from ..claude_skin.launcher import ClaudeCodeLauncher
            targets = sys.argv[2:] if len(sys.argv) > 2 else []
            launcher = ClaudeCodeLauncher(targets=targets)
            sys.exit(launcher.launch())

        if subcmd == "doctor":
            from rich.console import Console as RichConsole
            console = RichConsole(theme=REDCLAW_THEME)
            try:
                from ..tooling.doctor import DoctorReport
                doctor = DoctorReport()
                doctor.run()
            except Exception as e:
                console.print(f"[error]Doctor failed: {e}[/]")
            return

        if subcmd in ("setup-tools", "setup_tools"):
            from rich.console import Console as RichConsole
            console = RichConsole(theme=REDCLAW_THEME)
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

    runtime, guardian, _, llm_client = _build_runtime()

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
        llm_client=llm_client,
    )
    cli.run()


if __name__ == "__main__":
    main()
