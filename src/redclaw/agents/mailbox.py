"""
Mailbox — SQLite-backed inter-agent messaging system for Agent Teams.

Agents communicate via typed messages:
  - task_complete: Task finished notification
  - validation_request: Request Validator Agent
  - intervention: Team Lead guidance
  - broadcast: Message to all agents
  - peer_request / peer_response: Teammate-to-teammate
  - terminate: Shutdown signal
  - error: Error notification
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger("redclaw.agents.mailbox")


class Mailbox:
    """
    Thread-safe, SQLite-backed inter-agent messaging.

    Usage:
        mailbox = Mailbox()

        # Send message
        mailbox.send("exploit_agent_1", "team_lead", {
            "type": "task_complete",
            "task_id": "scan_1",
            "summary": "Found 3 open ports"
        })

        # Receive messages
        messages = mailbox.get_messages("team_lead")
        for msg in messages:
            print(msg)

        # Broadcast to all
        mailbox.broadcast("team_lead", {"type": "broadcast", "message": "New CVE found!"})
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            work_dir = os.path.expanduser("~/.redclaw")
            os.makedirs(work_dir, exist_ok=True)
            db_path = os.path.join(work_dir, "mailbox.db")

        self.db_path = db_path
        self._lock = threading.Lock()
        self._registered_agents: set[str] = set()
        self._init_db()
        logger.info(f"Mailbox initialized at {db_path}")

    def _init_db(self):
        """Create the messages table if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_agent TEXT NOT NULL,
                    to_agent TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    read_status INTEGER DEFAULT 0
                )
            """)
            conn.commit()

    def register_agent(self, agent_id: str):
        """Register an agent for broadcast messages."""
        self._registered_agents.add(agent_id)

    def unregister_agent(self, agent_id: str):
        """Unregister an agent."""
        self._registered_agents.discard(agent_id)

    def send(
        self,
        from_agent: str,
        to_agent: str,
        message: dict[str, Any],
    ):
        """Send a message to a specific agent."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """INSERT INTO messages (from_agent, to_agent, message, timestamp)
                       VALUES (?, ?, ?, ?)""",
                    (
                        from_agent,
                        to_agent,
                        json.dumps(message),
                        datetime.now().isoformat(),
                    ),
                )
                conn.commit()
        logger.debug(f"Message sent: {from_agent} -> {to_agent} ({message.get('type', 'unknown')})")

    def broadcast(self, from_agent: str, message: dict[str, Any]):
        """Send a message to all registered agents (except sender)."""
        for agent_id in self._registered_agents:
            if agent_id != from_agent:
                self.send(from_agent, agent_id, message)

    def get_messages(self, agent_id: str, mark_read: bool = True) -> list[dict[str, Any]]:
        """
        Get all unread messages for an agent.

        Args:
            agent_id: The recipient agent ID
            mark_read: Whether to mark messages as read

        Returns:
            List of message dicts with "from", "message", "timestamp"
        """
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row

                rows = conn.execute(
                    """SELECT * FROM messages
                       WHERE to_agent = ? AND read_status = 0
                       ORDER BY timestamp ASC""",
                    (agent_id,),
                ).fetchall()

                messages = []
                for row in rows:
                    msg = {
                        "message_id": row["message_id"],
                        "from": row["from_agent"],
                        "to": row["to_agent"],
                        "timestamp": row["timestamp"],
                    }
                    try:
                        msg.update(json.loads(row["message"]))
                    except (json.JSONDecodeError, TypeError):
                        msg["message"] = row["message"]
                    messages.append(msg)

                # Mark as read
                if mark_read and rows:
                    ids = [row["message_id"] for row in rows]
                    conn.execute(
                        f"""UPDATE messages SET read_status = 1
                            WHERE message_id IN ({','.join('?' * len(ids))})""",
                        ids,
                    )
                    conn.commit()

        return messages

    def has_messages(self, agent_id: str) -> bool:
        """Check if an agent has unread messages."""
        with sqlite3.connect(self.db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE to_agent = ? AND read_status = 0",
                (agent_id,),
            ).fetchone()[0]
        return count > 0

    def get_message_count(self, agent_id: str) -> int:
        """Get count of unread messages for an agent."""
        with sqlite3.connect(self.db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE to_agent = ? AND read_status = 0",
                (agent_id,),
            ).fetchone()[0]
        return count

    def reset(self):
        """Clear all messages."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM messages")
                conn.commit()
        logger.info("Mailbox cleared")

    def close(self):
        """Clean up resources."""
        self._registered_agents.clear()
        logger.info("Mailbox closed")
