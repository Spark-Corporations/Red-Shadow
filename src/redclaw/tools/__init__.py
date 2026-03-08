"""
RedClaw v3.1 Tools — Minimal wrappers + Output Cleaner for core pentesting tools.

Components:
  - OutputCleaner: Parse and structure raw tool output before sending to LLM
  - NmapWrapper: nmap scan execution + structured output parsing
  - NucleiWrapper: nuclei vulnerability scanning
  - SqlmapWrapper: SQL injection testing
  - GobusterWrapper: directory/DNS bruteforcing
  - FfufWrapper: web fuzzing
  - BashWrapper: generic command execution fallback
"""

from .output_cleaner import OutputCleaner
from .nmap_wrapper import NmapWrapper
from .nuclei_wrapper import NucleiWrapper
from .sqlmap_wrapper import SqlmapWrapper
from .gobuster_wrapper import GobusterWrapper
from .ffuf_wrapper import FfufWrapper
from .bash_wrapper import BashWrapper

__all__ = [
    "OutputCleaner",
    "NmapWrapper",
    "NucleiWrapper",
    "SqlmapWrapper",
    "GobusterWrapper",
    "FfufWrapper",
    "BashWrapper",
]
