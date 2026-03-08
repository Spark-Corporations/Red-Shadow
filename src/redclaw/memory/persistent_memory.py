"""
Persistent Memory Layer — cross-session learning for pentest engagements.

Enterprise-grade 2-layer memory:
  Layer 1: Episodic Memory (per-session)
    - Every hypothesis attempt recorded in SQLite
    - Full evidence chain: service, version, CVE, result, confidence_delta
    - Queryable per target fingerprint

  Layer 2: Semantic Memory (cross-session)
    - Fingerprint-based similarity matching (service+version combos)
    - Past failures lower confidence, past successes boost it
    - System improves with every engagement

Storage: ~/.redclaw/memory.db (SQLite — zero dependencies)

Usage:
    memory = PersistentMemory()    # auto creates ~/.redclaw/memory.db
    
    # Start of session: recall past intelligence
    recall = memory.recall(target="10.10.10.5", services=[...])
    # → {"exact": [...], "similar": [...], "stats": {...}}

    # End of session: commit all hypotheses
    memory.commit_session(target, hypotheses, session_id)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("redclaw.memory")

# Default database location
DEFAULT_DB_PATH = os.path.join(os.path.expanduser("~/.redclaw"), "memory.db")


# ── Data Types ────────────────────────────────────────────────────────────────


@dataclass
class AttemptRecord:
    """A single exploit attempt record from past sessions."""
    service: str
    version: str
    port: int
    cve: str
    attack_vector: str
    result: str            # success / failed / partial
    confidence_delta: float
    evidence: str
    session_id: str
    target: str
    timestamp: str
    attempt_count: int = 1

    @property
    def is_success(self) -> bool:
        return self.result == "success"

    @property
    def is_failure(self) -> bool:
        return self.result == "failed"


@dataclass
class RecallResult:
    """Result from memory recall — past intelligence for this target."""
    exact_matches: List[AttemptRecord]     # Same target IP
    similar_matches: List[AttemptRecord]   # Same service+version combo
    stats: Dict[str, Any]

    @property
    def has_history(self) -> bool:
        return bool(self.exact_matches or self.similar_matches)

    def get_failed_cves(self) -> List[str]:
        """Get CVEs that have consistently failed."""
        failed = {}
        for r in self.exact_matches + self.similar_matches:
            if r.is_failure:
                failed[r.cve] = failed.get(r.cve, 0) + 1
        return [cve for cve, count in failed.items() if count >= 2]

    def get_successful_vectors(self) -> List[str]:
        """Get attack vectors that have succeeded in similar contexts."""
        return list({r.attack_vector for r in self.similar_matches if r.is_success})

    def get_confidence_adjustment(self, cve: str, service: str, version: str) -> float:
        """Calculate confidence adjustment based on past attempts.

        Returns:
            Float adjustment: negative for repeated failures, positive for similar successes
        """
        adjustment = 0.0

        # Exact target matches (highest weight)
        for r in self.exact_matches:
            if r.cve == cve:
                if r.is_failure:
                    adjustment -= 0.15 * r.attempt_count  # More attempts = more penalty
                elif r.is_success:
                    adjustment += 0.20

        # Similar service+version matches (lower weight)
        for r in self.similar_matches:
            if r.service == service and r.version == version:
                if r.cve == cve:
                    if r.is_failure:
                        adjustment -= 0.08
                    elif r.is_success:
                        adjustment += 0.15

        return max(-0.8, min(0.5, adjustment))  # Clamp


# ── Fingerprinting ────────────────────────────────────────────────────────────


def compute_fingerprint(services: List[Dict]) -> str:
    """Compute a deterministic fingerprint from service list.

    Same services+versions on different IPs → same fingerprint.
    This enables cross-target learning.
    """
    # Sort for determinism
    normalized = sorted(
        [f"{s.get('name', '')}:{s.get('version', '')}:{s.get('port', 0)}"
         for s in services]
    )
    raw = "|".join(normalized)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ── Persistent Memory ─────────────────────────────────────────────────────────


class PersistentMemory:
    """SQLite-backed persistent memory for cross-session learning.

    Features:
      - Records every hypothesis attempt with full context
      - Exact recall: same target IP → same service history
      - Semantic recall: same fingerprint → similar targets' history
      - Confidence adjustments based on past success/failure rates
      - Session tracking for audit trail
      - Auto-creates database on first use
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path

        # Ensure directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        # Initialize database
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

        logger.info(f"Persistent memory initialized: {db_path}")

    def _create_tables(self):
        """Create database schema if not exists."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                target TEXT NOT NULL,
                fingerprint TEXT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                total_hypotheses INTEGER DEFAULT 0,
                successful INTEGER DEFAULT 0,
                failed INTEGER DEFAULT 0,
                notes TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                target TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                service TEXT NOT NULL,
                version TEXT DEFAULT '',
                port INTEGER DEFAULT 0,
                cve TEXT NOT NULL,
                attack_vector TEXT NOT NULL,
                result TEXT NOT NULL,
                confidence_delta REAL DEFAULT 0.0,
                evidence TEXT DEFAULT '',
                timestamp TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            CREATE INDEX IF NOT EXISTS idx_attempts_target
                ON attempts(target);
            CREATE INDEX IF NOT EXISTS idx_attempts_fingerprint
                ON attempts(fingerprint);
            CREATE INDEX IF NOT EXISTS idx_attempts_cve
                ON attempts(cve);
            CREATE INDEX IF NOT EXISTS idx_attempts_service_version
                ON attempts(service, version);
        """)
        self.conn.commit()

    # ── Session Management ────────────────────────────────────────────────────

    def start_session(self, target: str, services: List[Dict],
                      session_id: Optional[str] = None) -> str:
        """Register a new pentest session."""
        if not session_id:
            session_id = f"session:{datetime.now().strftime('%Y%m%d_%H%M%S')}:{target}"

        fingerprint = compute_fingerprint(services)

        self.conn.execute(
            "INSERT OR REPLACE INTO sessions (id, target, fingerprint, started_at) "
            "VALUES (?, ?, ?, ?)",
            (session_id, target, fingerprint, datetime.now().isoformat()),
        )
        self.conn.commit()

        logger.info(f"Session started: {session_id} (fingerprint: {fingerprint})")
        return session_id

    def end_session(self, session_id: str, notes: str = ""):
        """Mark session as completed with stats."""
        row = self.conn.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN result='success' THEN 1 ELSE 0 END) as success, "
            "SUM(CASE WHEN result='failed' THEN 1 ELSE 0 END) as failed "
            "FROM attempts WHERE session_id = ?",
            (session_id,),
        ).fetchone()

        self.conn.execute(
            "UPDATE sessions SET ended_at=?, total_hypotheses=?, successful=?, failed=?, notes=? "
            "WHERE id=?",
            (datetime.now().isoformat(), row["total"], row["success"], row["failed"],
             notes, session_id),
        )
        self.conn.commit()
        logger.info(f"Session ended: {session_id} — {row['success']}/{row['total']} successful")

    # ── Write: Commit Results ─────────────────────────────────────────────────

    def commit_attempt(
        self,
        session_id: str,
        target: str,
        fingerprint: str,
        service: str,
        version: str,
        port: int,
        cve: str,
        attack_vector: str,
        result: str,
        confidence_delta: float = 0.0,
        evidence: str = "",
    ):
        """Record a single exploit attempt."""
        self.conn.execute(
            "INSERT INTO attempts "
            "(session_id, target, fingerprint, service, version, port, "
            "cve, attack_vector, result, confidence_delta, evidence, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, target, fingerprint, service, version, port,
             cve, attack_vector, result, confidence_delta, evidence[:500],
             datetime.now().isoformat()),
        )
        self.conn.commit()

    def commit_session(self, target: str, hypotheses: List[Any],
                       session_id: str, services: List[Dict]):
        """Commit all hypothesis results from a completed session.

        Args:
            target: Target IP
            hypotheses: List of Hypothesis objects with status set
            session_id: Session identifier
            services: Service list for fingerprint computation
        """
        fingerprint = compute_fingerprint(services)

        for h in hypotheses:
            # Skip pending hypotheses (never tested)
            status_str = h.status.value if hasattr(h.status, 'value') else str(h.status)
            if status_str == "pending":
                continue

            self.commit_attempt(
                session_id=session_id,
                target=target,
                fingerprint=fingerprint,
                service=h.target_service,
                version=h.version,
                port=h.port,
                cve=h.cve,
                attack_vector=h.attack_vector,
                result=status_str,
                confidence_delta=h.confidence_delta,
                evidence=h.evidence,
            )

        self.end_session(session_id)
        logger.info(f"Session committed: {len(hypotheses)} hypotheses for {target}")

    # ── Read: Recall Past Intelligence ────────────────────────────────────────

    def recall(self, target: str, services: Optional[List[Dict]] = None) -> RecallResult:
        """Recall past intelligence for a target.

        Layer 1 (Exact): Same target IP — highest priority
        Layer 2 (Similar): Same service+version fingerprint — cross-target learning

        Returns:
            RecallResult with exact_matches, similar_matches, and stats
        """
        # ── Layer 1: Exact target match ──
        exact_rows = self.conn.execute(
            "SELECT service, version, port, cve, attack_vector, result, "
            "confidence_delta, evidence, session_id, target, timestamp, "
            "COUNT(*) as attempt_count "
            "FROM attempts WHERE target = ? "
            "GROUP BY cve, attack_vector "
            "ORDER BY timestamp DESC",
            (target,),
        ).fetchall()

        exact_matches = [
            AttemptRecord(
                service=r["service"],
                version=r["version"],
                port=r["port"],
                cve=r["cve"],
                attack_vector=r["attack_vector"],
                result=r["result"],
                confidence_delta=r["confidence_delta"],
                evidence=r["evidence"],
                session_id=r["session_id"],
                target=r["target"],
                timestamp=r["timestamp"],
                attempt_count=r["attempt_count"],
            )
            for r in exact_rows
        ]

        # ── Layer 2: Similar fingerprint match (different targets) ──
        similar_matches = []
        if services:
            fingerprint = compute_fingerprint(services)
            similar_rows = self.conn.execute(
                "SELECT service, version, port, cve, attack_vector, result, "
                "confidence_delta, evidence, session_id, target, timestamp, "
                "COUNT(*) as attempt_count "
                "FROM attempts "
                "WHERE fingerprint = ? AND target != ? "
                "GROUP BY cve, attack_vector "
                "ORDER BY timestamp DESC "
                "LIMIT 50",
                (fingerprint, target),
            ).fetchall()

            similar_matches = [
                AttemptRecord(
                    service=r["service"],
                    version=r["version"],
                    port=r["port"],
                    cve=r["cve"],
                    attack_vector=r["attack_vector"],
                    result=r["result"],
                    confidence_delta=r["confidence_delta"],
                    evidence=r["evidence"],
                    session_id=r["session_id"],
                    target=r["target"],
                    timestamp=r["timestamp"],
                    attempt_count=r["attempt_count"],
                )
                for r in similar_rows
            ]

        # ── Stats ──
        total_sessions = self.conn.execute(
            "SELECT COUNT(DISTINCT session_id) FROM attempts WHERE target = ?",
            (target,),
        ).fetchone()[0]

        total_attempts = len(exact_matches)
        success_rate = (
            sum(1 for r in exact_matches if r.is_success) / total_attempts
            if total_attempts > 0 else 0.0
        )

        stats = {
            "past_sessions": total_sessions,
            "total_attempts": total_attempts,
            "success_rate": success_rate,
            "similar_targets": len(similar_matches),
            "failed_cves": [r.cve for r in exact_matches if r.is_failure],
        }

        return RecallResult(
            exact_matches=exact_matches,
            similar_matches=similar_matches,
            stats=stats,
        )

    # ── Query Helpers ─────────────────────────────────────────────────────────

    def get_session_history(self, target: Optional[str] = None,
                            limit: int = 20) -> List[Dict]:
        """Get past session summaries."""
        if target:
            rows = self.conn.execute(
                "SELECT * FROM sessions WHERE target = ? ORDER BY started_at DESC LIMIT ?",
                (target, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_global_stats(self) -> Dict[str, Any]:
        """Get global memory statistics."""
        row = self.conn.execute(
            "SELECT COUNT(DISTINCT target) as targets, "
            "COUNT(DISTINCT session_id) as sessions, "
            "COUNT(*) as total_attempts, "
            "SUM(CASE WHEN result='success' THEN 1 ELSE 0 END) as successes, "
            "SUM(CASE WHEN result='failed' THEN 1 ELSE 0 END) as failures "
            "FROM attempts"
        ).fetchone()

        return {
            "unique_targets": row["targets"],
            "total_sessions": row["sessions"],
            "total_attempts": row["total_attempts"],
            "successes": row["successes"],
            "failures": row["failures"],
            "overall_success_rate": (
                row["successes"] / row["total_attempts"]
                if row["total_attempts"] > 0 else 0.0
            ),
        }

    def get_display_summary(self, target: str) -> str:
        """Human-readable summary for a target's memory."""
        recall = self.recall(target)
        if not recall.has_history:
            return f"No prior intelligence on {target}"

        lines = [f"Persistent Memory for {target}:"]
        lines.append(f"  Past sessions: {recall.stats['past_sessions']}")
        lines.append(f"  Total attempts: {recall.stats['total_attempts']}")
        lines.append(f"  Success rate: {recall.stats['success_rate']:.0%}")

        failed_cves = recall.get_failed_cves()
        if failed_cves:
            lines.append(f"  Known failed CVEs: {', '.join(failed_cves)}")

        successful_vectors = recall.get_successful_vectors()
        if successful_vectors:
            lines.append(f"  Successful vectors: {', '.join(successful_vectors)}")

        if recall.similar_matches:
            lines.append(f"  Similar targets with intel: {recall.stats['similar_targets']}")

        return "\n".join(lines)

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
