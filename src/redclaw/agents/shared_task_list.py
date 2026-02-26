"""
SharedTaskList — SQLite-backed task queue for Agent Teams coordination.

Agents claim tasks from this shared queue, execute them, and report results.
Supports task dependencies so dependent tasks only become available after
their prerequisites complete.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger("redclaw.agents.shared_task_list")


class TaskStatus(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class SharedTaskList:
    """
    Thread-safe, SQLite-backed task queue for Agent Teams.

    Usage:
        task_list = SharedTaskList()
        task_list.add_task("scan_1", "Nmap scan 10.10.10.5", dependencies=[])
        task_list.add_task("exploit_1", "Exploit Apache RCE", dependencies=["scan_1"])

        task = task_list.claim_task("recon_agent_1")
        # ... execute task ...
        task_list.complete_task("scan_1", '{"ports": [22, 80]}')
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            work_dir = os.path.expanduser("~/.redclaw")
            os.makedirs(work_dir, exist_ok=True)
            db_path = os.path.join(work_dir, "shared_tasks.db")

        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()
        logger.info(f"SharedTaskList initialized at {db_path}")

    def _init_db(self):
        """Create the tasks table if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    assigned_to TEXT,
                    dependencies TEXT NOT NULL DEFAULT '[]',
                    result TEXT,
                    priority INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    error TEXT
                )
            """)
            conn.commit()

    def add_task(
        self,
        task_id: str,
        description: str,
        dependencies: Optional[list[str]] = None,
        priority: int = 0,
    ):
        """Add a task to the queue."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO tasks
                       (task_id, description, status, dependencies, priority, created_at)
                       VALUES (?, ?, 'PENDING', ?, ?, ?)""",
                    (
                        task_id,
                        description,
                        json.dumps(dependencies or []),
                        priority,
                        datetime.now().isoformat(),
                    ),
                )
                conn.commit()
        logger.debug(f"Added task: {task_id} (deps: {dependencies})")

    def claim_task(self, agent_id: str) -> Optional[dict[str, Any]]:
        """
        Claim the next available task for an agent.

        A task is available when:
          1. Status is PENDING
          2. All dependencies are COMPLETE
        """
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row

                # Get all pending tasks ordered by priority
                cursor = conn.execute(
                    """SELECT * FROM tasks
                       WHERE status = 'PENDING'
                       ORDER BY priority DESC, created_at ASC"""
                )

                for row in cursor.fetchall():
                    deps = json.loads(row["dependencies"])

                    # Check if all dependencies are complete
                    if deps:
                        dep_check = conn.execute(
                            f"""SELECT COUNT(*) FROM tasks
                                WHERE task_id IN ({','.join('?' * len(deps))})
                                AND status = 'COMPLETE'""",
                            deps,
                        ).fetchone()[0]

                        if dep_check < len(deps):
                            continue  # Dependencies not met

                    # Claim this task
                    conn.execute(
                        """UPDATE tasks SET status = 'RUNNING',
                           assigned_to = ?, started_at = ?
                           WHERE task_id = ?""",
                        (agent_id, datetime.now().isoformat(), row["task_id"]),
                    )
                    conn.commit()

                    task = dict(row)
                    task["dependencies"] = deps
                    logger.info(f"Agent {agent_id} claimed task {row['task_id']}")
                    return task

        return None  # No available tasks

    def complete_task(self, task_id: str, result: str):
        """Mark a task as complete with its result."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """UPDATE tasks SET status = 'COMPLETE',
                       result = ?, completed_at = ?
                       WHERE task_id = ?""",
                    (result, datetime.now().isoformat(), task_id),
                )
                conn.commit()
        logger.info(f"Task {task_id} completed")

    def fail_task(self, task_id: str, error: str):
        """Mark a task as failed."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """UPDATE tasks SET status = 'FAILED',
                       error = ?, completed_at = ?
                       WHERE task_id = ?""",
                    (error, datetime.now().isoformat(), task_id),
                )
                conn.commit()
        logger.warning(f"Task {task_id} failed: {error}")

    def all_tasks_complete(self) -> bool:
        """Check if all tasks are done (COMPLETE or FAILED)."""
        with sqlite3.connect(self.db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE status IN ('PENDING', 'RUNNING')"
            ).fetchone()[0]
        return count == 0

    def get_task(self, task_id: str) -> Optional[dict[str, Any]]:
        """Get a specific task by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if row:
                task = dict(row)
                task["dependencies"] = json.loads(task["dependencies"])
                return task
        return None

    def get_completed_tasks(self) -> list[dict[str, Any]]:
        """Get all completed tasks with their results."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = 'COMPLETE'"
            ).fetchall()
            tasks = []
            for row in rows:
                task = dict(row)
                task["dependencies"] = json.loads(task["dependencies"])
                if task.get("result"):
                    try:
                        task["result_parsed"] = json.loads(task["result"])
                    except (json.JSONDecodeError, TypeError):
                        task["result_parsed"] = task["result"]
                tasks.append(task)
        return tasks

    def get_status_summary(self) -> dict[str, int]:
        """Get count of tasks per status."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status"
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def reset(self):
        """Clear all tasks (for testing or new engagement)."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM tasks")
                conn.commit()
        logger.info("SharedTaskList cleared")

    def close(self):
        """Clean up resources."""
        logger.info("SharedTaskList closed")
