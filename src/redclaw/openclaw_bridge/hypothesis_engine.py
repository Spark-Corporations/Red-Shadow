"""
Hypothesis-Driven Exploitation Engine.

Enterprise-grade exploitation pattern (XBOW-style):
  1. KG → Scored Candidates (deterministic, ranked by CVSS)
  2. Each candidate → Isolated Hypothesis (structured, testable)
  3. LLM = code writer only (no strategy decisions)
  4. Results → KG feedback (confidence_delta adjusts priority)

The system decides WHAT to attack. LLM only decides HOW.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("redclaw.hypothesis")


# ── Data Types ────────────────────────────────────────────────────────────────


class AttackOutcome(str, Enum):
    """Expected or actual outcome of an exploit attempt."""
    RCE = "rce"
    AUTH_BYPASS = "auth_bypass"
    INFO_DISCLOSURE = "info_disclosure"
    DOS = "dos"
    CREDENTIAL_ACCESS = "credential_access"
    FILE_ACCESS = "file_access"
    UNKNOWN = "unknown"


class HypothesisStatus(str, Enum):
    PENDING = "pending"
    TESTING = "testing"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    SKIPPED = "skipped"


@dataclass
class Hypothesis:
    """A single, isolated exploitation hypothesis.

    Each hypothesis targets one service+vulnerability combination.
    LLM receives this as input and writes code specifically for it.
    """
    id: str
    target_service: str
    version: str
    port: int
    cve: str
    attack_vector: str
    confidence: float          # 0.0 - 1.0, derived from CVSS
    expected_outcome: AttackOutcome
    status: HypothesisStatus = HypothesisStatus.PENDING

    # Filled after execution
    actual_result: str = ""
    evidence: str = ""
    confidence_delta: float = 0.0

    @property
    def display(self) -> str:
        icon = {
            HypothesisStatus.SUCCESS: "✅",
            HypothesisStatus.FAILED: "❌",
            HypothesisStatus.PARTIAL: "⚠️",
            HypothesisStatus.PENDING: "⏳",
            HypothesisStatus.TESTING: "🔄",
            HypothesisStatus.SKIPPED: "⏭️",
        }.get(self.status, "?")
        return (f"{icon} [{self.confidence:.0%}] {self.port}/tcp {self.target_service} "
                f"{self.version} → {self.attack_vector} ({self.cve})")

    def to_prompt_block(self) -> str:
        """Generate structured prompt block for LLM code generation."""
        return f"""HYPOTHESIS:
  Target: {{target_ip}}:{self.port}
  Service: {self.target_service} {self.version}
  CVE: {self.cve}
  Attack Vector: {self.attack_vector}
  Expected Outcome: {self.expected_outcome.value}
  Confidence: {self.confidence:.0%}"""


# ── CVSS → Attack vector mapping ─────────────────────────────────────────────

# Maps service names to likely attack vectors when no CVE info is available
SERVICE_ATTACK_MAP: Dict[str, Dict[str, Any]] = {
    "ftp": {
        "vectors": ["anonymous_login", "default_creds", "bounce_attack"],
        "outcome": AttackOutcome.CREDENTIAL_ACCESS,
    },
    "ssh": {
        "vectors": ["default_creds", "key_bruteforce", "cve_exploit"],
        "outcome": AttackOutcome.AUTH_BYPASS,
    },
    "http": {
        "vectors": ["path_traversal", "sqli", "default_admin", "header_injection"],
        "outcome": AttackOutcome.INFO_DISCLOSURE,
    },
    "https": {
        "vectors": ["path_traversal", "sqli", "default_admin", "ssl_misconfig"],
        "outcome": AttackOutcome.INFO_DISCLOSURE,
    },
    "mysql": {
        "vectors": ["default_creds", "no_auth", "sqli"],
        "outcome": AttackOutcome.CREDENTIAL_ACCESS,
    },
    "postgresql": {
        "vectors": ["default_creds", "no_auth", "trust_auth"],
        "outcome": AttackOutcome.CREDENTIAL_ACCESS,
    },
    "smb": {
        "vectors": ["null_session", "eternal_blue", "default_share"],
        "outcome": AttackOutcome.FILE_ACCESS,
    },
    "redis": {
        "vectors": ["no_auth", "config_write", "module_load"],
        "outcome": AttackOutcome.RCE,
    },
    "mongodb": {
        "vectors": ["no_auth", "default_creds"],
        "outcome": AttackOutcome.FILE_ACCESS,
    },
    "telnet": {
        "vectors": ["default_creds", "no_auth"],
        "outcome": AttackOutcome.AUTH_BYPASS,
    },
}

# Severity → base confidence score
SEVERITY_SCORE: Dict[str, float] = {
    "critical": 0.90,
    "high": 0.70,
    "medium": 0.45,
    "low": 0.20,
}


# ── Hypothesis Engine ─────────────────────────────────────────────────────────


class HypothesisEngine:
    """Generates scored hypotheses from KnowledgeGraph data.

    Usage:
        engine = HypothesisEngine(kg=self.kg, target="10.10.10.5")
        hypotheses = engine.generate()
        # → sorted by confidence, ready for LLM code generation

        for h in hypotheses:
            # test it...
            engine.record_result(h, "success", evidence="root shell obtained")

        # Failed hypotheses lose priority in next iteration
    """

    def __init__(self, kg: Any, target: str, memory: Any = None):
        self.kg = kg
        self.target = target
        self.memory = memory  # PersistentMemory instance (optional)
        self.hypotheses: List[Hypothesis] = []
        self._attempt_history: Dict[str, float] = {}  # hypothesis_id → cumulative delta

    def generate(self) -> List[Hypothesis]:
        """Query KG and produce ranked hypotheses.

        Priority order:
          1. CVE-backed vulnerabilities (sorted by CVSS desc)
          2. Service-based guesses (default creds, misconfigs)
          3. Previously failed hypotheses get deprioritized
        """
        self.hypotheses = []

        # ── Source 1: KG vulnerabilities (highest priority) ──
        vulns = self.kg.get_vulnerabilities_for_host(self.target)
        for v in vulns.get("vulnerabilities", []):
            cve = v.get("cve", "N/A")
            severity = v.get("severity", "medium")
            cvss = v.get("cvss")
            service_id = v.get("service", "")

            # Parse service info from service_id  (format: "ip:port:name")
            parts = service_id.split(":") if service_id else []
            port = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
            svc_name = parts[2] if len(parts) >= 3 else "unknown"

            # Get version from KG service node
            version = ""
            svc_data = self.kg.get_services_for_host(self.target)
            for s in svc_data.get("services", []):
                if s.get("port") == port:
                    version = s.get("version", "") or ""
                    break

            # Determine confidence from CVSS or severity
            if cvss and isinstance(cvss, (int, float)):
                confidence = min(cvss / 10.0, 1.0)
            else:
                confidence = SEVERITY_SCORE.get(severity, 0.5)

            # Determine attack vector
            svc_info = SERVICE_ATTACK_MAP.get(svc_name.lower(), {})
            attack_vector = f"exploit_{cve}"
            outcome = svc_info.get("outcome", AttackOutcome.UNKNOWN)

            h = Hypothesis(
                id=f"hyp:{cve}:{port}",
                target_service=svc_name,
                version=version,
                port=port,
                cve=cve,
                attack_vector=attack_vector,
                confidence=confidence,
                expected_outcome=outcome,
            )
            self.hypotheses.append(h)

        # ── Source 2: Service-based hypotheses (no CVE needed) ──
        services = self.kg.get_services_for_host(self.target)
        existing_ports = {h.port for h in self.hypotheses}

        for svc in services.get("services", []):
            port = svc.get("port", 0)
            name = (svc.get("name", "") or "").lower()
            version = svc.get("version", "") or ""

            if name not in SERVICE_ATTACK_MAP:
                continue

            svc_info = SERVICE_ATTACK_MAP[name]
            for vector in svc_info["vectors"][:2]:  # Top 2 vectors per service
                h_id = f"hyp:MISC-{name}:{port}:{vector}"

                # Skip if we already have a CVE-backed hypothesis for this port
                if port in existing_ports and vector == "cve_exploit":
                    continue

                # Service-based hypotheses start at lower confidence
                base_confidence = 0.35

                h = Hypothesis(
                    id=h_id,
                    target_service=name,
                    version=version,
                    port=port,
                    cve=f"MISC-{name}-{vector}",
                    attack_vector=vector,
                    confidence=base_confidence,
                    expected_outcome=svc_info["outcome"],
                )
                self.hypotheses.append(h)

        # ── Apply historical confidence deltas (in-session) ──
        for h in self.hypotheses:
            delta = self._attempt_history.get(h.id, 0.0)
            h.confidence = max(0.0, min(1.0, h.confidence + delta))

        # ── Apply persistent memory (cross-session) ──
        if self.memory:
            try:
                recall = self.memory.recall(self.target)
                if recall.has_history:
                    logger.info(f"Persistent memory: {recall.stats['total_attempts']} past attempts")
                    for h in self.hypotheses:
                        adj = recall.get_confidence_adjustment(
                            cve=h.cve, service=h.target_service, version=h.version
                        )
                        if adj != 0.0:
                            old = h.confidence
                            h.confidence = max(0.0, min(1.0, h.confidence + adj))
                            logger.info(f"  Memory adj: {h.cve} {old:.0%} → {h.confidence:.0%} ({adj:+.2f})")
            except Exception as e:
                logger.warning(f"Persistent memory recall failed: {e}")

        # ── Sort by confidence descending ──
        self.hypotheses.sort(key=lambda h: h.confidence, reverse=True)

        return self.hypotheses

    def record_result(
        self,
        hypothesis: Hypothesis,
        result: str,
        evidence: str = "",
        confidence_delta: float = 0.0,
    ):
        """Record exploitation result and update confidence.

        Args:
            hypothesis: The tested hypothesis
            result: "success" | "failed" | "partial"
            evidence: Raw output / proof (truncated)
            confidence_delta: Score adjustment (+0.3 for success, -0.2 for fail)
        """
        if result == "success":
            hypothesis.status = HypothesisStatus.SUCCESS
            hypothesis.confidence_delta = confidence_delta or +0.3
        elif result == "partial":
            hypothesis.status = HypothesisStatus.PARTIAL
            hypothesis.confidence_delta = confidence_delta or +0.1
        else:
            hypothesis.status = HypothesisStatus.FAILED
            hypothesis.confidence_delta = confidence_delta or -0.2

        hypothesis.actual_result = result
        hypothesis.evidence = evidence[:500]

        # Update cumulative history
        self._attempt_history[hypothesis.id] = (
            self._attempt_history.get(hypothesis.id, 0.0) + hypothesis.confidence_delta
        )

        # Write result to KG
        try:
            self.kg.add_exploit(
                cve=hypothesis.cve,
                exploit_name=f"{hypothesis.attack_vector} ({result})",
                url=f"{self.target}:{hypothesis.port}",
                tested=True,
            )

            # Update KG node with result metadata
            exploit_id = f"exploit:{hypothesis.cve}:{hypothesis.attack_vector} ({result})"
            if exploit_id in self.kg.graph:
                self.kg.graph.nodes[exploit_id]["result"] = result
                self.kg.graph.nodes[exploit_id]["evidence"] = evidence[:200]
                self.kg.graph.nodes[exploit_id]["confidence_delta"] = hypothesis.confidence_delta

        except Exception as e:
            logger.warning(f"Failed to write exploit result to KG: {e}")

    def get_summary(self) -> str:
        """Get a multi-line summary of all hypotheses and their results."""
        if not self.hypotheses:
            return "No hypotheses generated."

        lines = [f"Hypothesis Summary ({len(self.hypotheses)} total):"]
        for h in self.hypotheses:
            lines.append(f"  {h.display}")

        succeeded = sum(1 for h in self.hypotheses if h.status == HypothesisStatus.SUCCESS)
        failed = sum(1 for h in self.hypotheses if h.status == HypothesisStatus.FAILED)
        pending = sum(1 for h in self.hypotheses if h.status == HypothesisStatus.PENDING)

        lines.append(f"  ───")
        lines.append(f"  Success: {succeeded}, Failed: {failed}, Pending: {pending}")

        return "\n".join(lines)

    def get_successful(self) -> List[Hypothesis]:
        """Get hypotheses that succeeded."""
        return [h for h in self.hypotheses if h.status == HypothesisStatus.SUCCESS]

    def get_actionable(self) -> List[Hypothesis]:
        """Get hypotheses worth testing (confidence > threshold)."""
        return [h for h in self.hypotheses if h.confidence >= 0.2 and h.status == HypothesisStatus.PENDING]
