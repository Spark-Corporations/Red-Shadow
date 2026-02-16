"""
RedClaw Tooling — Tool Detector

Detects installed pentesting tools on the system: presence, path, version,
and readiness for use. Supports Linux, macOS, and Windows.
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional

from redclaw.tooling.registry import TOOL_REGISTRY, ToolDef


@dataclass
class ToolStatus:
    """Result of probing a single tool."""
    tool: ToolDef
    installed: bool
    path: Optional[str] = None
    version: Optional[str] = None
    meets_minimum: bool = True
    error: Optional[str] = None


class ToolDetector:
    """
    Detect pentesting tools on the local system.

    Usage:
        detector = ToolDetector()
        results = detector.check_all()
        for status in results:
            print(f"{status.tool.name}: {'✅' if status.installed else '❌'}")
    """

    VERSION_PATTERN = re.compile(r"(\d+\.\d+(?:\.\d+)?)")

    @staticmethod
    def detect_os() -> str:
        """Return simplified OS identifier."""
        system = platform.system().lower()
        if system == "linux":
            # Check for Kali specifically
            try:
                with open("/etc/os-release") as f:
                    content = f.read()
                    if "kali" in content.lower():
                        return "kali"
            except FileNotFoundError:
                pass
            return "linux"
        elif system == "darwin":
            return "macos"
        elif system == "windows":
            return "windows"
        return system

    @staticmethod
    def detect_package_manager() -> Optional[str]:
        """Detect available package manager."""
        for mgr in ("apt-get", "brew", "dnf", "pacman", "choco"):
            if shutil.which(mgr):
                return mgr.replace("-get", "")  # apt-get → apt
        return None

    def check_tool(self, tool: ToolDef) -> ToolStatus:
        """Check if a specific tool is available."""
        binary_path = shutil.which(tool.binary)

        if not binary_path:
            return ToolStatus(
                tool=tool,
                installed=False,
                error=f"{tool.binary} not found on PATH",
            )

        # Try to extract version
        version = None
        try:
            result = subprocess.run(
                tool.version_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = result.stdout + result.stderr
            match = self.VERSION_PATTERN.search(output)
            if match:
                version = match.group(1)
        except (subprocess.TimeoutExpired, OSError) as e:
            pass  # Version extraction failed but tool exists

        # Check minimum version
        meets_minimum = True
        if version and tool.min_version:
            meets_minimum = self._compare_versions(version, tool.min_version)

        return ToolStatus(
            tool=tool,
            installed=True,
            path=binary_path,
            version=version,
            meets_minimum=meets_minimum,
        )

    def check_all(self) -> list[ToolStatus]:
        """Check all tools in the registry."""
        return [self.check_tool(t) for t in TOOL_REGISTRY]

    def check_required(self) -> list[ToolStatus]:
        """Check only required tools."""
        return [self.check_tool(t) for t in TOOL_REGISTRY if t.required]

    def get_missing(self) -> list[ToolDef]:
        """Return list of tools that are not installed."""
        return [
            status.tool
            for status in self.check_all()
            if not status.installed
        ]

    def get_installed(self) -> list[ToolDef]:
        """Return list of tools that are installed."""
        return [
            status.tool
            for status in self.check_all()
            if status.installed
        ]

    @staticmethod
    def _compare_versions(current: str, minimum: str) -> bool:
        """
        Compare two version strings (e.g. '7.93' >= '7.80').
        Returns True if current >= minimum.
        """
        def parts(v: str) -> list[int]:
            return [int(x) for x in v.split(".")]

        try:
            return parts(current) >= parts(minimum)
        except (ValueError, IndexError):
            return True  # Can't parse, assume OK

    def summary(self) -> dict:
        """Return a summary dict: {total, installed, missing, required_missing}."""
        results = self.check_all()
        installed = [r for r in results if r.installed]
        missing = [r for r in results if not r.installed]
        required_missing = [r for r in missing if r.tool.required]

        return {
            "os": self.detect_os(),
            "package_manager": self.detect_package_manager(),
            "total": len(results),
            "installed": len(installed),
            "missing": len(missing),
            "required_missing": len(required_missing),
            "ready": len(required_missing) == 0,
        }
