"""
RedClaw Tooling — Tool registry, auto-installer, and health checker.

This package provides:
  - registry: Defines all 10 pentesting tool dependencies
  - detector: Detects installed tools, versions, paths
  - installer: Installs missing tools based on OS/package manager
  - doctor: Generates Rich table health check reports
"""

from redclaw.tooling.registry import TOOL_REGISTRY, ToolDef
from redclaw.tooling.detector import ToolDetector
from redclaw.tooling.installer import ToolInstaller
from redclaw.tooling.doctor import DoctorReport

__all__ = [
    "TOOL_REGISTRY",
    "ToolDef",
    "ToolDetector",
    "ToolInstaller",
    "DoctorReport",
]
