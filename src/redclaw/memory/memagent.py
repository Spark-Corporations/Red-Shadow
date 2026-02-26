"""
MemAgent — Progress File Manager + Context Compactor + Crash Recovery

Manages the progress file system for RedClaw V3.1:
  - Reads/writes structured progress files (claude-progress.txt)
  - Context compaction when approaching token limits
  - Session recovery from crashes/interruptions

Progress File Format:
  CURRENT STATUS: <phase>
  COMPLETED TASKS: [list]
  ONGOING: [list]
  PENDING: [list]
  FAILED ATTEMPTS: [list]
  KEY FINDINGS: [list]
  NEXT PLANNED: [list]
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger("redclaw.memory.memagent")


class MemAgent:
    """
    Progress file manager for crash-resilient multi-session operation.

    Usage:
        mem = MemAgent(working_dir="~/.redclaw/engagements/test1")
        mem.initialize("Pentest 10.10.10.5")
        mem.update_task_status("scan_1", "RUNNING", "Started nmap scan")
        mem.update_task_status("scan_1", "COMPLETE", "Found 3 open ports")
        mem.add_finding("CVE-2021-41773 on Apache 2.4.49")

        # On resume:
        state = mem.get_current_state()
        summary = mem.get_context_summary()
    """

    PROGRESS_FILE = "claude-progress.txt"

    def __init__(self, working_dir: Optional[str] = None):
        if working_dir is None:
            working_dir = os.path.expanduser("~/.redclaw/current_engagement")

        self.working_dir = working_dir
        os.makedirs(working_dir, exist_ok=True)
        self.progress_path = os.path.join(working_dir, self.PROGRESS_FILE)

        # In-memory state
        self._state = {
            "current_status": "INITIALIZING",
            "completed_tasks": [],
            "ongoing_tasks": [],
            "pending_tasks": [],
            "failed_attempts": [],
            "key_findings": [],
            "next_planned": [],
            "metadata": {
                "engagement": "",
                "started_at": "",
                "last_updated": "",
            },
        }

        # Load existing state if available
        if os.path.exists(self.progress_path):
            self._load_state()
            logger.info(f"MemAgent loaded state from {self.progress_path}")
        else:
            logger.info(f"MemAgent initialized fresh at {self.progress_path}")

    # ── Initialization ────────────────────────────────────────────────────

    def initialize(self, engagement_description: str):
        """Initialize a new engagement progress file."""
        self._state["metadata"]["engagement"] = engagement_description
        self._state["metadata"]["started_at"] = datetime.now().isoformat()
        self._state["current_status"] = "PLANNING"
        self._save_state()
        logger.info(f"Engagement initialized: {engagement_description}")

    # ── Task Management ───────────────────────────────────────────────────

    def update_task_status(self, task_id: str, status: str, details: str = ""):
        """Update the status of a task in the progress file."""
        entry = {
            "task_id": task_id,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat(),
        }

        if status == "RUNNING":
            self._remove_from_list("pending_tasks", task_id)
            self._add_to_list("ongoing_tasks", entry)

        elif status == "COMPLETE":
            self._remove_from_list("pending_tasks", task_id)
            self._remove_from_list("ongoing_tasks", task_id)
            self._add_to_list("completed_tasks", entry)

        elif status == "FAILED":
            self._remove_from_list("pending_tasks", task_id)
            self._remove_from_list("ongoing_tasks", task_id)
            self._add_to_list("failed_attempts", entry)

        elif status == "PENDING":
            self._add_to_list("pending_tasks", entry)

        self._save_state()
        logger.debug(f"Task {task_id} -> {status}")

    def add_pending_tasks(self, tasks: list[dict[str, str]]):
        """Add multiple pending tasks at once."""
        for task in tasks:
            self._add_to_list("pending_tasks", {
                "task_id": task.get("id", ""),
                "details": task.get("description", ""),
                "timestamp": datetime.now().isoformat(),
            })
        self._save_state()

    # ── Findings ──────────────────────────────────────────────────────────

    def add_finding(self, finding: str, severity: str = "info"):
        """Add a key finding."""
        self._state["key_findings"].append({
            "finding": finding,
            "severity": severity,
            "timestamp": datetime.now().isoformat(),
        })
        self._save_state()
        logger.info(f"Finding added: [{severity}] {finding}")

    # ── Status Management ─────────────────────────────────────────────────

    def set_status(self, status: str):
        """Update the current engagement status."""
        self._state["current_status"] = status
        self._save_state()

    def set_next_planned(self, tasks: list[str]):
        """Set the next planned actions."""
        self._state["next_planned"] = tasks
        self._save_state()

    # ── State Queries ─────────────────────────────────────────────────────

    def get_current_state(self) -> dict[str, Any]:
        """Get full current state. Used for crash recovery."""
        return dict(self._state)

    def get_context_summary(self) -> dict[str, Any]:
        """
        Get a compact summary for LLM context injection.

        Returns only the essential info to minimize token usage.
        """
        return {
            "status": self._state["current_status"],
            "completed_tasks": [
                f"{t['task_id']}: {t['details']}"
                for t in self._state["completed_tasks"][-10:]  # Last 10
            ],
            "ongoing_tasks": [
                f"{t['task_id']}: {t['details']}"
                for t in self._state["ongoing_tasks"]
            ],
            "key_findings": [
                f"[{f['severity']}] {f['finding']}"
                for f in self._state["key_findings"][-10:]  # Last 10
            ],
            "next_planned": self._state["next_planned"],
        }

    def get_timeline(self) -> list[dict[str, Any]]:
        """Get ordered timeline of all task changes."""
        all_events = []
        for category in ["completed_tasks", "ongoing_tasks", "pending_tasks", "failed_attempts"]:
            for item in self._state[category]:
                all_events.append({
                    "task_id": item.get("task_id", ""),
                    "status": item.get("status", category),
                    "details": item.get("details", ""),
                    "timestamp": item.get("timestamp", ""),
                })
        all_events.sort(key=lambda x: x["timestamp"])
        return all_events

    # ── Context Compaction ────────────────────────────────────────────────

    def compact_context(self, max_items: int = 20):
        """
        Compact the progress state to stay within token limits.

        Keeps recent items and summarizes older ones.
        """
        # Keep only last N completed tasks
        if len(self._state["completed_tasks"]) > max_items:
            older = self._state["completed_tasks"][:-max_items]
            summary = f"[Compacted] {len(older)} earlier tasks completed"
            self._state["completed_tasks"] = [
                {"task_id": "compacted", "details": summary, "timestamp": datetime.now().isoformat()}
            ] + self._state["completed_tasks"][-max_items:]

        # Keep only last N findings
        if len(self._state["key_findings"]) > max_items:
            self._state["key_findings"] = self._state["key_findings"][-max_items:]

        # Clear resolved failed attempts
        self._state["failed_attempts"] = self._state["failed_attempts"][-5:]

        self._save_state()
        logger.info("Context compacted")

    # ── Crash Recovery ────────────────────────────────────────────────────

    def recover_from_crash(self) -> dict[str, Any]:
        """
        Recover state after crash/interruption.

        Moves any RUNNING tasks back to PENDING.
        Returns the recovered state.
        """
        recovered_tasks = []
        for task in list(self._state["ongoing_tasks"]):
            self._state["pending_tasks"].append({
                **task,
                "status": "PENDING",
                "details": f"[RECOVERED] Was running: {task['details']}",
            })
            recovered_tasks.append(task["task_id"])

        self._state["ongoing_tasks"] = []
        self._state["current_status"] = "RECOVERED"
        self._save_state()

        logger.warning(f"Crash recovery: {len(recovered_tasks)} tasks moved back to pending")
        return {
            "recovered_tasks": recovered_tasks,
            "state": self.get_context_summary(),
        }

    # ── Archival ──────────────────────────────────────────────────────────

    def archive(self):
        """Archive the current progress file with timestamp."""
        if os.path.exists(self.progress_path):
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_path = os.path.join(self.working_dir, f"progress_archive_{ts}.json")
            with open(archive_path, "w") as f:
                json.dump(self._state, f, indent=2)
            logger.info(f"Progress archived to {archive_path}")

    # ── Internal Helpers ──────────────────────────────────────────────────

    def _add_to_list(self, list_name: str, entry: dict):
        """Add an entry to a state list, avoiding duplicates by task_id."""
        self._remove_from_list(list_name, entry.get("task_id", ""))
        self._state[list_name].append(entry)

    def _remove_from_list(self, list_name: str, task_id: str):
        """Remove entries with matching task_id from a state list."""
        self._state[list_name] = [
            item for item in self._state[list_name]
            if item.get("task_id") != task_id
        ]

    def _save_state(self):
        """Save state to progress file."""
        self._state["metadata"]["last_updated"] = datetime.now().isoformat()

        # Save as JSON for machine readability
        json_path = self.progress_path + ".json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2)

        # Also save human-readable format
        with open(self.progress_path, "w", encoding="utf-8") as f:
            f.write(self._format_human_readable())

    def _load_state(self):
        """Load state from progress file."""
        json_path = self.progress_path + ".json"
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                self._state = json.load(f)
        else:
            # Try to parse human-readable format (fallback)
            self._state["current_status"] = "RECOVERED"

    def _format_human_readable(self) -> str:
        """Format state as human-readable text file (ASCII-safe for Windows)."""
        lines = []
        lines.append("=" * 60)
        lines.append("REDCLAW PROGRESS FILE")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"ENGAGEMENT: {self._state['metadata'].get('engagement', 'Unknown')}")
        lines.append(f"STARTED: {self._state['metadata'].get('started_at', 'Unknown')}")
        lines.append(f"UPDATED: {self._state['metadata'].get('last_updated', 'Unknown')}")
        lines.append("")
        lines.append(f"CURRENT STATUS: {self._state['current_status']}")
        lines.append("")

        lines.append("-" * 40)
        lines.append("COMPLETED TASKS:")
        for t in self._state["completed_tasks"]:
            lines.append(f"  [+] {t.get('task_id', '?')}: {t.get('details', '')}")

        lines.append("")
        lines.append("-" * 40)
        lines.append("ONGOING:")
        for t in self._state["ongoing_tasks"]:
            lines.append(f"  [>] {t.get('task_id', '?')}: {t.get('details', '')}")

        lines.append("")
        lines.append("-" * 40)
        lines.append("PENDING:")
        for t in self._state["pending_tasks"]:
            lines.append(f"  [ ] {t.get('task_id', '?')}: {t.get('details', '')}")

        if self._state["failed_attempts"]:
            lines.append("")
            lines.append("-" * 40)
            lines.append("FAILED ATTEMPTS:")
            for t in self._state["failed_attempts"]:
                lines.append(f"  [X] {t.get('task_id', '?')}: {t.get('details', '')}")

        lines.append("")
        lines.append("-" * 40)
        lines.append("KEY FINDINGS:")
        for f in self._state["key_findings"]:
            lines.append(f"  [{f.get('severity', 'info')}] {f.get('finding', '')}")

        lines.append("")
        lines.append("-" * 40)
        lines.append("NEXT PLANNED:")
        for t in self._state["next_planned"]:
            lines.append(f"  -> {t}")

        lines.append("")
        return "\n".join(lines)
