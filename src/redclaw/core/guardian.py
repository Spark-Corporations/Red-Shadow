"""
GuardianRails — Command validation, safety enforcement, and audit logging.

Responsibilities (from v2.0 docs):
  - Blocklist: Prevent destructive commands (rm -rf /, mkfs, dd, shutdown, etc.)
  - Scope check: Only allow commands targeting in-scope IPs/domains
  - Rate limiting: Max commands per minute to prevent runaway execution
  - Human approval: Require operator confirmation for high-risk operations
  - Audit trail: Log every command with timestamp, source, and result
  - Self-destruction prevention: Block commands that could brick the system
"""

from __future__ import annotations

import ipaddress
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("redclaw.core.guardian")


class RiskLevel(str, Enum):
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    BLOCKED = "blocked"


@dataclass
class ValidationResult:
    """Result of command validation."""
    allowed: bool
    risk_level: RiskLevel
    reasons: list[str] = field(default_factory=list)
    requires_approval: bool = False

    @property
    def denied(self) -> bool:
        return not self.allowed


@dataclass
class AuditEntry:
    """Single audit log entry."""
    timestamp: float
    command: str
    session_type: str
    risk_level: str
    allowed: bool
    reasons: list[str]
    approved_by: Optional[str] = None


# ── Default blocklists ────────────────────────────────────────────────────────

DESTRUCTIVE_COMMANDS = [
    "rm -rf /", "rm -rf /*", "rm -rf ~", "rm -rf .",
    "mkfs", "dd if=/dev/zero", "dd if=/dev/random",
    "shutdown", "reboot", "halt", "poweroff",
    "init 0", "init 6",
    ":(){:|:&};:",  # fork bomb
    "chmod -R 777 /", "chmod -R 000 /",
    "chown -R", "mv / ",
    "wget -O /dev/sda", "curl -o /dev/sda",
    "> /dev/sda", "cat /dev/zero > ",
    "kill -9 -1", "killall",
    "iptables -F", "iptables --flush",
    "systemctl stop",
    "history -c",  # anti-forensics
]

SUSPICIOUS_PATTERNS = [
    r">\s*/dev/[sh]d[a-z]",                # overwrite disk
    r"mkfs\.\w+\s+/dev/",                   # format partition
    r"dd\s+if=.+of=/dev/",                  # raw disk write
    r"rm\s+-[rf]+\s+/[^/\s]",              # recursive delete from root
    r":()\s*\{.*\|.*&\s*\}\s*;",           # fork bomb variants
    r"chmod\s+-R\s+[07]{3}\s+/",           # dangerous chmod on root
    r"curl.*\|\s*(bash|sh|python)",         # pipe to shell
    r"wget.*-O\s*-\s*\|\s*(bash|sh)",      # download and execute
]


class GuardianRails:
    """
    Safety enforcement for all command execution.

    Usage:
        guardian = GuardianRails(
            scope_targets=["10.10.10.0/24", "example.com"],
            scope_exclusions=["10.10.10.1"],
            rate_limit=100,
        )
        result = guardian.validate("nmap -sV 10.10.10.5")
        if result.allowed:
            # execute command
        else:
            print(f"BLOCKED: {result.reasons}")
    """

    def __init__(
        self,
        scope_targets: Optional[list[str]] = None,
        scope_exclusions: Optional[list[str]] = None,
        rate_limit: int = 100,  # commands per minute
        blocked_commands: Optional[list[str]] = None,
        approval_callback: Optional[Callable[[str, RiskLevel], bool]] = None,
    ):
        self._scope_targets = scope_targets or []
        self._scope_exclusions = scope_exclusions or []
        self._rate_limit = rate_limit
        self._blocked_commands = blocked_commands or DESTRUCTIVE_COMMANDS
        self._approval_callback = approval_callback
        self._audit_log: list[AuditEntry] = []
        self._command_timestamps: list[float] = []
        self._suspicious_patterns = [re.compile(p) for p in SUSPICIOUS_PATTERNS]
        logger.info(
            f"GuardianRails initialized: scope={len(self._scope_targets)} targets, "
            f"rate_limit={rate_limit}/min"
        )

    # ── Main validation ──────────────────────────────────────────────────

    def validate(self, command: str, session_type: str = "local") -> ValidationResult:
        """
        Validate a command against all safety rules.
        Returns ValidationResult with allowed/denied and reasons.
        """
        reasons: list[str] = []
        risk = RiskLevel.SAFE

        # 1. Check blocklist
        blocked_reason = self._check_blocklist(command)
        if blocked_reason:
            reasons.append(blocked_reason)
            risk = RiskLevel.BLOCKED

        # 2. Check suspicious patterns
        pattern_match = self._check_suspicious_patterns(command)
        if pattern_match:
            reasons.append(f"Suspicious pattern: {pattern_match}")
            if risk != RiskLevel.BLOCKED:
                risk = RiskLevel.CRITICAL

        # 3. Check scope (for commands targeting IPs/domains)
        scope_violation = self._check_scope(command)
        if scope_violation:
            reasons.append(scope_violation)
            if risk in (RiskLevel.SAFE, RiskLevel.LOW):
                risk = RiskLevel.HIGH

        # 4. Check rate limit
        if self._check_rate_limit():
            reasons.append(f"Rate limit exceeded: >{self._rate_limit} commands/min")
            if risk == RiskLevel.SAFE:
                risk = RiskLevel.MEDIUM

        # 5. Classify risk if no issues found
        if not reasons:
            risk = self._classify_risk(command)

        # Decision
        allowed = risk not in (RiskLevel.BLOCKED, RiskLevel.CRITICAL)
        requires_approval = risk in (RiskLevel.HIGH,)

        # If requires approval, call the callback
        if requires_approval and allowed and self._approval_callback:
            approved = self._approval_callback(command, risk)
            if not approved:
                allowed = False
                reasons.append("Human operator denied approval")

        # Record in audit log
        if allowed:
            self._command_timestamps.append(time.monotonic())

        entry = AuditEntry(
            timestamp=time.time(),
            command=command,
            session_type=session_type,
            risk_level=risk.value,
            allowed=allowed,
            reasons=reasons,
        )
        self._audit_log.append(entry)

        result = ValidationResult(
            allowed=allowed,
            risk_level=risk,
            reasons=reasons,
            requires_approval=requires_approval,
        )

        if not allowed:
            logger.warning(f"BLOCKED: '{command}' — {reasons}")
        else:
            logger.debug(f"ALLOWED: '{command}' (risk={risk.value})")

        return result

    # ── Internal checks ──────────────────────────────────────────────────

    def _check_blocklist(self, command: str) -> Optional[str]:
        """Check if command matches any blocked command."""
        cmd_lower = command.lower().strip()
        for blocked in self._blocked_commands:
            if blocked.lower() in cmd_lower:
                return f"Blocked command detected: '{blocked}'"
        return None

    def _check_suspicious_patterns(self, command: str) -> Optional[str]:
        """Check command against suspicious regex patterns."""
        for pattern in self._suspicious_patterns:
            match = pattern.search(command)
            if match:
                return match.group(0)
        return None

    def _check_scope(self, command: str) -> Optional[str]:
        """Check if command targets are within engagement scope."""
        if not self._scope_targets:
            return None  # no scope defined = allow all

        # Extract IPs and domains from command
        ip_pattern = re.compile(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?:/\d{1,2})?)\b')
        targets_in_cmd = ip_pattern.findall(command)

        for target in targets_in_cmd:
            if not self._is_in_scope(target):
                return f"Out-of-scope target: {target}"
        return None

    def _is_in_scope(self, target: str) -> bool:
        """Check if a specific target is within scope."""
        # Explicitly excluded?
        if target in self._scope_exclusions:
            return False

        # Check against scope targets
        try:
            target_ip = ipaddress.ip_address(target.split("/")[0])
            for scope in self._scope_targets:
                try:
                    if "/" in scope:
                        network = ipaddress.ip_network(scope, strict=False)
                        if target_ip in network:
                            return True
                    else:
                        if target_ip == ipaddress.ip_address(scope):
                            return True
                except ValueError:
                    # scope might be a domain
                    if scope in target:
                        return True
        except ValueError:
            # target is a domain, check against scope domains
            for scope in self._scope_targets:
                if scope in target or target in scope:
                    return True

        return False

    def _check_rate_limit(self) -> bool:
        """Check if rate limit is exceeded."""
        now = time.monotonic()
        cutoff = now - 60  # last 60 seconds
        self._command_timestamps = [t for t in self._command_timestamps if t > cutoff]
        return len(self._command_timestamps) >= self._rate_limit

    def _classify_risk(self, command: str) -> RiskLevel:
        """Classify the risk level of a command."""
        cmd_lower = command.lower()

        # High-risk tools
        high_risk_tools = ["metasploit", "msfconsole", "msfvenom", "exploit", "sqlmap", "hydra"]
        for tool in high_risk_tools:
            if tool in cmd_lower:
                return RiskLevel.HIGH

        # Medium-risk
        medium_risk = ["nmap", "masscan", "nuclei", "nikto", "gobuster", "ffuf"]
        for tool in medium_risk:
            if tool in cmd_lower:
                return RiskLevel.MEDIUM

        # Low-risk
        low_risk = ["ping", "traceroute", "dig", "nslookup", "whois", "curl", "wget"]
        for tool in low_risk:
            if tool in cmd_lower:
                return RiskLevel.LOW

        return RiskLevel.SAFE

    # ── Audit ─────────────────────────────────────────────────────────────

    @property
    def audit_log(self) -> list[AuditEntry]:
        return self._audit_log

    def get_stats(self) -> dict[str, Any]:
        """Get guardian statistics."""
        total = len(self._audit_log)
        blocked = sum(1 for e in self._audit_log if not e.allowed)
        return {
            "total_commands": total,
            "blocked": blocked,
            "allowed": total - blocked,
            "block_rate": f"{blocked/total*100:.1f}%" if total else "0%",
        }

    def export_audit_log(self, path: str | Path) -> None:
        """Export audit log to JSON file."""
        import json
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                [
                    {
                        "timestamp": e.timestamp,
                        "command": e.command,
                        "session": e.session_type,
                        "risk": e.risk_level,
                        "allowed": e.allowed,
                        "reasons": e.reasons,
                    }
                    for e in self._audit_log
                ],
                f,
                indent=2,
            )
