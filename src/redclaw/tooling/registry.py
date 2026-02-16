"""
RedClaw Tooling — Tool Registry

Central registry of all pentesting tool dependencies: binary names, version
commands, installation instructions per OS/package-manager, and metadata.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ToolCategory(str, Enum):
    """Broad category for grouping tools."""
    SCANNING = "scanning"
    EXPLOITATION = "exploitation"
    ENUMERATION = "enumeration"
    POST_EXPLOITATION = "post_exploitation"
    CREDENTIAL = "credential"
    WEB = "web"
    AD = "active_directory"
    CUSTOM = "custom"


@dataclass(frozen=True)
class InstallMethod:
    """Installation commands for a specific package manager."""
    apt: Optional[str] = None
    brew: Optional[str] = None
    dnf: Optional[str] = None
    pacman: Optional[str] = None
    pip: Optional[str] = None
    go: Optional[str] = None
    manual: Optional[str] = None   # fallback: curl/wget script


@dataclass(frozen=True)
class ToolDef:
    """Definition of a single pentesting tool dependency."""
    name: str                          # Human-readable name
    binary: str                        # Binary name on PATH
    version_cmd: str                   # Shell command to get version
    category: ToolCategory
    required: bool                     # Is this tool required for basic operation?
    description: str
    install: InstallMethod
    min_version: Optional[str] = None  # Minimum acceptable version
    kali_package: Optional[str] = None # Kali meta-package that includes it
    website: str = ""
    alternatives: tuple[str, ...] = field(default_factory=tuple)


# ── The 10-Tool Registry ─────────────────────────────────────────────────

TOOL_REGISTRY: list[ToolDef] = [
    # ── Scanning ──────────────────────────────────────────────
    ToolDef(
        name="Nmap",
        binary="nmap",
        version_cmd="nmap --version",
        category=ToolCategory.SCANNING,
        required=True,
        description="Network mapper — port scanning, service detection, OS fingerprinting",
        min_version="7.80",
        kali_package="nmap",
        website="https://nmap.org",
        install=InstallMethod(
            apt="sudo apt-get install -y nmap",
            brew="brew install nmap",
            dnf="sudo dnf install -y nmap",
            pacman="sudo pacman -S --noconfirm nmap",
        ),
    ),
    ToolDef(
        name="Masscan",
        binary="masscan",
        version_cmd="masscan --version",
        category=ToolCategory.SCANNING,
        required=True,
        description="Ultra-fast internet-wide port scanner",
        min_version="1.3.0",
        kali_package="masscan",
        website="https://github.com/robertdavidgraham/masscan",
        install=InstallMethod(
            apt="sudo apt-get install -y masscan",
            brew="brew install masscan",
            dnf="sudo dnf install -y masscan",
            pacman="sudo pacman -S --noconfirm masscan",
        ),
    ),
    ToolDef(
        name="Nuclei",
        binary="nuclei",
        version_cmd="nuclei --version",
        category=ToolCategory.SCANNING,
        required=True,
        description="Template-based vulnerability scanner by ProjectDiscovery",
        min_version="3.0.0",
        website="https://github.com/projectdiscovery/nuclei",
        install=InstallMethod(
            apt="sudo apt-get install -y nuclei",
            go="go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest",
            manual="curl -sL https://raw.githubusercontent.com/projectdiscovery/nuclei/main/scripts/install.sh | sudo bash",
        ),
    ),

    # ── Exploitation ──────────────────────────────────────────
    ToolDef(
        name="Metasploit Framework",
        binary="msfconsole",
        version_cmd="msfconsole --version",
        category=ToolCategory.EXPLOITATION,
        required=False,
        description="Full-featured exploitation framework",
        kali_package="metasploit-framework",
        website="https://www.metasploit.com",
        install=InstallMethod(
            apt="sudo apt-get install -y metasploit-framework",
            manual="curl https://raw.githubusercontent.com/rapid7/metasploit-omnibus/master/config/templates/metasploit-framework-wrappers/msfupdate.erb > /tmp/msfinstall && chmod 755 /tmp/msfinstall && sudo /tmp/msfinstall",
        ),
    ),

    # ── Web ───────────────────────────────────────────────────
    ToolDef(
        name="SQLMap",
        binary="sqlmap",
        version_cmd="sqlmap --version",
        category=ToolCategory.WEB,
        required=False,
        description="Automatic SQL injection and database takeover tool",
        kali_package="sqlmap",
        website="https://sqlmap.org",
        install=InstallMethod(
            apt="sudo apt-get install -y sqlmap",
            brew="brew install sqlmap",
            pip="pip3 install sqlmap",
        ),
    ),
    ToolDef(
        name="Nikto",
        binary="nikto",
        version_cmd="nikto -Version",
        category=ToolCategory.WEB,
        required=False,
        description="Web server scanner — misconfigurations, dangerous files, outdated versions",
        kali_package="nikto",
        website="https://cirt.net/Nikto2",
        install=InstallMethod(
            apt="sudo apt-get install -y nikto",
            brew="brew install nikto",
        ),
    ),
    ToolDef(
        name="Gobuster",
        binary="gobuster",
        version_cmd="gobuster version",
        category=ToolCategory.WEB,
        required=False,
        description="Directory/file/DNS brute-force tool written in Go",
        website="https://github.com/OJ/gobuster",
        install=InstallMethod(
            apt="sudo apt-get install -y gobuster",
            go="go install github.com/OJ/gobuster/v3@latest",
        ),
    ),

    # ── Credential ────────────────────────────────────────────
    ToolDef(
        name="Hydra",
        binary="hydra",
        version_cmd="hydra -h 2>&1 | head -1",
        category=ToolCategory.CREDENTIAL,
        required=False,
        description="Online password brute-force attack tool",
        kali_package="hydra",
        website="https://github.com/vanhauser-thc/thc-hydra",
        install=InstallMethod(
            apt="sudo apt-get install -y hydra",
            brew="brew install hydra",
            dnf="sudo dnf install -y hydra",
        ),
    ),

    # ── Active Directory ──────────────────────────────────────
    ToolDef(
        name="BloodHound (Python)",
        binary="bloodhound-python",
        version_cmd="bloodhound-python --version",
        category=ToolCategory.AD,
        required=False,
        description="Active Directory relationship collector for BloodHound",
        website="https://github.com/dirkjanm/BloodHound.py",
        install=InstallMethod(
            pip="pip3 install bloodhound",
        ),
    ),

    # ── Post-Exploitation ─────────────────────────────────────
    ToolDef(
        name="LinPEAS",
        binary="linpeas.sh",
        version_cmd="echo installed",
        category=ToolCategory.POST_EXPLOITATION,
        required=False,
        description="Linux privilege escalation enumeration script",
        website="https://github.com/peass-ng/PEASS-ng",
        install=InstallMethod(
            manual="sudo curl -sL https://github.com/peass-ng/PEASS-ng/releases/latest/download/linpeas.sh -o /usr/local/bin/linpeas.sh && sudo chmod +x /usr/local/bin/linpeas.sh",
        ),
    ),
]


def get_tool_by_name(name: str) -> Optional[ToolDef]:
    """Look up a tool definition by name (case-insensitive)."""
    name_lower = name.lower()
    for tool in TOOL_REGISTRY:
        if tool.name.lower() == name_lower or tool.binary.lower() == name_lower:
            return tool
    return None


def get_tools_by_category(category: ToolCategory) -> list[ToolDef]:
    """Get all tools in a given category."""
    return [t for t in TOOL_REGISTRY if t.category == category]


def get_required_tools() -> list[ToolDef]:
    """Get only the required tools."""
    return [t for t in TOOL_REGISTRY if t.required]
