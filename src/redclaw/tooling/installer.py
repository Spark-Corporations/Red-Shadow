"""
RedClaw Tooling — Auto-Installer

Installs missing pentesting tools based on detected OS and package manager.
Supports dry-run mode, individual tool installation, and Kali meta-packages.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

from redclaw.tooling.detector import ToolDetector
from redclaw.tooling.registry import TOOL_REGISTRY, ToolDef, InstallMethod

logger = logging.getLogger("redclaw.tooling.installer")


@dataclass
class InstallResult:
    """Outcome of an installation attempt."""
    tool: ToolDef
    success: bool
    method_used: str
    output: str = ""
    error: Optional[str] = None


class ToolInstaller:
    """
    OS-aware auto-installer for pentesting tool dependencies.

    Usage:
        installer = ToolInstaller()
        results = installer.install_missing()
        for r in results:
            print(f"{r.tool.name}: {'✅' if r.success else '❌'}")
    """

    # Package manager priority order
    MANAGER_ORDER = ["apt", "brew", "dnf", "pacman", "pip", "go", "manual"]

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.detector = ToolDetector()
        self.os_name = self.detector.detect_os()
        self.pkg_mgr = self.detector.detect_package_manager()

    def install_tool(self, tool: ToolDef) -> InstallResult:
        """Install a single tool using the best available method, with fallback."""
        install = tool.install

        # Get ALL viable install commands in priority order
        candidates = self._get_all_install_cmds(install)

        if not candidates:
            return InstallResult(
                tool=tool,
                success=False,
                method_used="none",
                error=f"No installation method available for {self.os_name}/{self.pkg_mgr}",
            )

        last_error = ""
        for method_name, command in candidates:
            logger.info(f"Installing {tool.name} via {method_name}: {command}")

            if self.dry_run:
                return InstallResult(
                    tool=tool,
                    success=True,
                    method_used=method_name,
                    output=f"[DRY RUN] Would execute: {command}",
                )

            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 min timeout
                )

                if result.returncode == 0:
                    return InstallResult(
                        tool=tool,
                        success=True,
                        method_used=method_name,
                        output=result.stdout[:500],
                    )
                else:
                    last_error = result.stderr[:300]
                    logger.warning(f"  ❌ {tool.name} failed via {method_name}, trying next...")
            except subprocess.TimeoutExpired:
                last_error = "Installation timed out (>5 min)"
                logger.warning(f"  ⏳ {tool.name} timed out via {method_name}, trying next...")
            except OSError as e:
                last_error = str(e)
                logger.warning(f"  ❌ {tool.name} OS error via {method_name}: {e}")

        # All methods failed
        return InstallResult(
            tool=tool,
            success=False,
            method_used=candidates[-1][0],
            error=last_error,
        )

    def install_missing(self) -> list[InstallResult]:
        """Install all missing tools."""
        missing = self.detector.get_missing()
        if not missing:
            logger.info("All tools are already installed!")
            return []

        logger.info(f"Installing {len(missing)} missing tools...")

        # On Kali, try meta-packages first
        if self.os_name == "kali" and not self.dry_run:
            self._install_kali_metapackages()

        results = []
        for tool in missing:
            result = self.install_tool(tool)
            results.append(result)
            if result.success:
                logger.info(f"  ✅ {tool.name} installed via {result.method_used}")
            else:
                logger.warning(f"  ❌ {tool.name} failed: {result.error}")

        return results

    def install_by_name(self, name: str) -> Optional[InstallResult]:
        """Install a specific tool by name."""
        from redclaw.tooling.registry import get_tool_by_name
        tool = get_tool_by_name(name)
        if not tool:
            logger.error(f"Tool '{name}' not found in registry")
            return None
        return self.install_tool(tool)

    def _get_all_install_cmds(self, install: InstallMethod) -> list[tuple[str, str]]:
        """
        Get ALL viable install commands in priority order.
        Returns list of (method_name, command) tuples.
        Skips methods whose prerequisite binary is missing (e.g. 'go').
        """
        # Binaries required for each method
        _method_binary = {"go": "go", "pip": "pip3", "brew": "brew", "npm": "npm"}

        priority = []

        # Prefer the detected package manager
        if self.pkg_mgr:
            cmd = getattr(install, self.pkg_mgr, None)
            if cmd:
                priority.append((self.pkg_mgr, cmd))

        # Fall through to other managers
        for method in self.MANAGER_ORDER:
            if method == self.pkg_mgr:
                continue
            cmd = getattr(install, method, None)
            if not cmd:
                continue

            # Skip methods whose prerequisite binary is missing
            required_bin = _method_binary.get(method)
            if required_bin and not shutil.which(required_bin):
                logger.debug(f"Skipping {method} for install — {required_bin} not on PATH")
                continue

            priority.append((method, cmd))

        return priority

    def _install_kali_metapackages(self):
        """On Kali Linux, install kali-tools meta-packages for broad coverage."""
        logger.info("🐉 Kali detected — installing meta-packages...")
        packages = [
            "kali-tools-top10",
            "kali-tools-vulnerability",
            "kali-tools-exploitation",
        ]
        cmd = f"sudo apt-get update && sudo apt-get install -y {' '.join(packages)}"
        try:
            subprocess.run(cmd, shell=True, timeout=600, check=False)
        except (subprocess.TimeoutExpired, OSError):
            logger.warning("Kali meta-package installation timed out")
