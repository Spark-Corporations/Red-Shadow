"""
RedClaw Tooling — Doctor Report

Generates a Rich table showing the health status of all pentesting tool
dependencies: installed, version, path, and categorized summary.
"""
from __future__ import annotations

from typing import Optional

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

from redclaw.tooling.detector import ToolDetector, ToolStatus


class DoctorReport:
    """
    Generate and display a health check report.

    Usage:
        report = DoctorReport()
        report.run()       # Print Rich table
        report.to_dict()   # Get structured data
    """

    def __init__(self):
        self.detector = ToolDetector()
        self._results: Optional[list[ToolStatus]] = None

    @property
    def results(self) -> list[ToolStatus]:
        if self._results is None:
            self._results = self.detector.check_all()
        return self._results

    def run(self):
        """Print the Doctor report to console."""
        if HAS_RICH:
            self._print_rich()
        else:
            self._print_plain()

    def _print_rich(self):
        """Rich table output."""
        console = Console()

        # Header
        console.print()
        console.print(Panel(
            "[bold red]RedClaw[/bold red] — Tool Health Check",
            subtitle=f"OS: {self.detector.detect_os()} | Pkg: {self.detector.detect_package_manager() or 'none'}",
            style="red",
        ))

        # Build table
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Status", width=3, justify="center")
        table.add_column("Tool", min_width=20)
        table.add_column("Version", min_width=10)
        table.add_column("Category", min_width=12)
        table.add_column("Path", min_width=20)
        table.add_column("Req", width=3, justify="center")

        for status in self.results:
            if status.installed:
                icon = "✅"
                version = status.version or "—"
                path = status.path or "—"
                style = None
                if not status.meets_minimum:
                    icon = "⚠️"
                    style = "yellow"
            else:
                icon = "❌" if status.tool.required else "⚠️"
                version = "—"
                path = status.error or "NOT FOUND"
                style = "red" if status.tool.required else "yellow"

            req = "★" if status.tool.required else "·"

            table.add_row(
                icon,
                status.tool.name,
                version,
                status.tool.category.value,
                path,
                req,
                style=style,
            )

        console.print(table)

        # Summary
        summary = self.detector.summary()
        installed = summary["installed"]
        total = summary["total"]
        missing = summary["missing"]
        req_missing = summary["required_missing"]

        console.print()
        if summary["ready"]:
            console.print(
                f"  [green]✅ {installed}/{total} tools installed — system READY[/green]"
            )
        else:
            console.print(
                f"  [red]❌ {installed}/{total} tools installed — "
                f"{req_missing} REQUIRED tool(s) missing[/red]"
            )

        if missing > 0:
            console.print(
                f"  [dim]💡 Run: [bold]redclaw setup-tools[/bold] to auto-install missing tools[/dim]"
            )
        console.print()

    def _print_plain(self):
        """Fallback plain-text output (no Rich)."""
        print()
        print("═══ RedClaw — Tool Health Check ═══")
        print(f"OS: {self.detector.detect_os()} | Pkg: {self.detector.detect_package_manager() or 'none'}")
        print()

        for status in self.results:
            if status.installed:
                icon = "[OK]"
                info = f"v{status.version or '?'} → {status.path}"
            else:
                icon = "[!!]" if status.tool.required else "[--]"
                info = "NOT FOUND"

            req = "*" if status.tool.required else " "
            print(f"  {icon} {status.tool.name:<22} {info}  {req}")

        summary = self.detector.summary()
        print()
        print(f"  {summary['installed']}/{summary['total']} tools installed")
        if not summary["ready"]:
            print(f"  ❌ {summary['required_missing']} required tool(s) missing")
            print("  💡 Run: redclaw setup-tools")
        print()

    def to_dict(self) -> dict:
        """Return report as structured dict for programmatic use."""
        summary = self.detector.summary()
        tools = []
        for status in self.results:
            tools.append({
                "name": status.tool.name,
                "binary": status.tool.binary,
                "installed": status.installed,
                "version": status.version,
                "path": status.path,
                "required": status.tool.required,
                "category": status.tool.category.value,
                "meets_minimum": status.meets_minimum,
            })
        return {**summary, "tools": tools}

    def is_ready(self) -> bool:
        """Quick check: are all required tools installed?"""
        return self.detector.summary()["ready"]
