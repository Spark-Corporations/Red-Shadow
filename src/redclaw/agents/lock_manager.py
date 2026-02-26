"""
LockManager — File-based resource locking for Agent Teams.

Prevents concurrent access to shared resources (e.g., two agents trying
to run nmap on the same target simultaneously).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

logger = logging.getLogger("redclaw.agents.lock_manager")


class LockManager:
    """
    Simple file-based lock manager for resource coordination.

    Usage:
        lock_mgr = LockManager()

        if lock_mgr.acquire("nmap_10.10.10.5", "recon_agent_1"):
            # Run nmap...
            lock_mgr.release("nmap_10.10.10.5", "recon_agent_1")
        else:
            # Resource busy, skip or wait
            pass
    """

    def __init__(self, lock_dir: Optional[str] = None):
        if lock_dir is None:
            lock_dir = os.path.join(os.path.expanduser("~/.redclaw"), "locks")

        self.lock_dir = lock_dir
        os.makedirs(lock_dir, exist_ok=True)
        logger.info(f"LockManager initialized at {lock_dir}")

    def _lock_path(self, resource_id: str) -> str:
        """Get the file path for a resource lock."""
        safe_name = resource_id.replace("/", "_").replace(":", "_").replace(" ", "_")
        return os.path.join(self.lock_dir, f"{safe_name}.lock")

    def acquire(self, resource_id: str, agent_id: str, timeout: float = 0) -> bool:
        """
        Try to acquire a lock on a resource.

        Args:
            resource_id: Resource identifier (e.g., "nmap_10.10.10.5")
            agent_id: Agent requesting the lock
            timeout: Seconds to wait for lock (0 = no wait)

        Returns:
            True if lock acquired, False otherwise
        """
        lock_path = self._lock_path(resource_id)
        deadline = time.monotonic() + timeout

        while True:
            if not os.path.exists(lock_path):
                # Create lock file
                try:
                    with open(lock_path, "x") as f:  # Atomic create
                        f.write(f"{agent_id}\n{time.time()}")
                    logger.debug(f"Lock acquired: {resource_id} by {agent_id}")
                    return True
                except FileExistsError:
                    pass  # Race condition — another agent grabbed it

            # Check if lock is stale (older than 10 minutes)
            try:
                with open(lock_path, "r") as f:
                    lines = f.read().strip().split("\n")
                    if len(lines) >= 2:
                        lock_time = float(lines[1])
                        if time.time() - lock_time > 600:
                            # Stale lock — clean it up
                            os.remove(lock_path)
                            logger.warning(f"Removed stale lock: {resource_id}")
                            continue
            except (OSError, ValueError):
                pass

            if time.monotonic() >= deadline:
                return False

            time.sleep(0.5)

    def release(self, resource_id: str, agent_id: str) -> bool:
        """
        Release a lock on a resource.

        Args:
            resource_id: Resource identifier
            agent_id: Agent releasing the lock

        Returns:
            True if lock released, False if not held by agent
        """
        lock_path = self._lock_path(resource_id)

        if not os.path.exists(lock_path):
            return False

        try:
            with open(lock_path, "r") as f:
                owner = f.read().strip().split("\n")[0]

            if owner == agent_id:
                os.remove(lock_path)
                logger.debug(f"Lock released: {resource_id} by {agent_id}")
                return True
            else:
                logger.warning(f"Cannot release lock {resource_id}: owned by {owner}, not {agent_id}")
                return False
        except OSError:
            return False

    def is_locked(self, resource_id: str) -> bool:
        """Check if a resource is locked."""
        return os.path.exists(self._lock_path(resource_id))

    def get_lock_owner(self, resource_id: str) -> Optional[str]:
        """Get the agent that holds a lock."""
        lock_path = self._lock_path(resource_id)
        if os.path.exists(lock_path):
            try:
                with open(lock_path, "r") as f:
                    return f.read().strip().split("\n")[0]
            except OSError:
                pass
        return None

    def cleanup(self):
        """Remove all lock files."""
        for f in os.listdir(self.lock_dir):
            if f.endswith(".lock"):
                os.remove(os.path.join(self.lock_dir, f))
        logger.info("All locks cleaned up")
