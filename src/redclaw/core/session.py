"""
SessionManager — Dual-session multiplexer for local and remote command execution.

Architecture (from v2.0 docs):
  - Local session: subprocess execution for tools on the attacking machine (Kali)
  - Remote session: paramiko SSH for target interaction, reverse shell handler
  - Command routing: automatically determines local vs. remote based on context
  - Session persistence with heartbeat and reconnection
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("redclaw.core.session")


class SessionType(str, Enum):
    LOCAL = "local"
    REMOTE = "remote"


@dataclass
class CommandResult:
    """Result of a command execution."""
    command: str
    stdout: str
    stderr: str
    exit_code: int
    duration: float  # seconds
    session_type: SessionType
    timed_out: bool = False
    truncated: bool = False

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    @property
    def output(self) -> str:
        """Combined stdout, or stderr if stdout is empty."""
        return self.stdout.strip() or self.stderr.strip()


@dataclass
class SSHCredentials:
    """SSH connection details for remote session."""
    hostname: str
    port: int = 22
    username: str = "root"
    password: Optional[str] = None
    key_file: Optional[str] = None
    passphrase: Optional[str] = None


class LocalSession:
    """
    Executes commands on the local attacking machine via subprocess.
    """

    def __init__(self, shell: str = "/bin/bash", working_dir: Optional[str] = None):
        self._shell = shell
        self._working_dir = working_dir
        self._history: list[CommandResult] = []
        logger.info(f"LocalSession initialized: shell={shell}")

    async def execute(
        self, command: str, timeout: int = 300, env: Optional[dict[str, str]] = None
    ) -> CommandResult:
        """Execute a command locally with timeout."""
        start = time.monotonic()
        merged_env = {**os.environ, **(env or {})}
        timed_out = False

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._working_dir,
                env=merged_env,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            exit_code = proc.returncode or 0
        except asyncio.TimeoutError:
            timed_out = True
            proc.kill()
            stdout_bytes, stderr_bytes = b"", b"Command timed out"
            exit_code = -1
        except Exception as e:
            stdout_bytes, stderr_bytes = b"", str(e).encode()
            exit_code = -1

        duration = time.monotonic() - start
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        # Truncate very large outputs (>1MB)
        truncated = False
        if len(stdout) > 1_000_000:
            stdout = stdout[:1_000_000] + "\n... [TRUNCATED]"
            truncated = True

        result = CommandResult(
            command=command,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration=duration,
            session_type=SessionType.LOCAL,
            timed_out=timed_out,
            truncated=truncated,
        )
        self._history.append(result)
        logger.debug(f"Local cmd: '{command}' → exit={exit_code} ({duration:.2f}s)")
        return result

    def execute_sync(
        self, command: str, timeout: int = 300, env: Optional[dict[str, str]] = None
    ) -> CommandResult:
        """Synchronous command execution (for non-async contexts)."""
        start = time.monotonic()
        merged_env = {**os.environ, **(env or {})}
        timed_out = False

        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                timeout=timeout,
                cwd=self._working_dir,
                env=merged_env,
            )
            exit_code = proc.returncode
            stdout = proc.stdout.decode("utf-8", errors="replace")
            stderr = proc.stderr.decode("utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            timed_out = True
            stdout, stderr = "", "Command timed out"
            exit_code = -1
        except Exception as e:
            stdout, stderr = "", str(e)
            exit_code = -1

        duration = time.monotonic() - start
        truncated = False
        if len(stdout) > 1_000_000:
            stdout = stdout[:1_000_000] + "\n... [TRUNCATED]"
            truncated = True

        result = CommandResult(
            command=command,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration=duration,
            session_type=SessionType.LOCAL,
            timed_out=timed_out,
            truncated=truncated,
        )
        self._history.append(result)
        return result

    @property
    def history(self) -> list[CommandResult]:
        return self._history


class RemoteSession:
    """
    Executes commands on a remote target via SSH (paramiko).
    Supports key-based and password auth, heartbeat, and reconnection.
    """

    def __init__(self, credentials: SSHCredentials, timeout: int = 30, retries: int = 3):
        self._creds = credentials
        self._timeout = timeout
        self._retries = retries
        self._client = None
        self._connected = False
        self._history: list[CommandResult] = []
        self._last_heartbeat: float = 0
        logger.info(f"RemoteSession initialized: {credentials.hostname}:{credentials.port}")

    def connect(self) -> None:
        """Establish SSH connection with retry logic."""
        try:
            import paramiko
        except ImportError:
            raise RuntimeError("paramiko is required for remote sessions: pip install paramiko")

        for attempt in range(1, self._retries + 1):
            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                connect_kwargs: dict[str, Any] = {
                    "hostname": self._creds.hostname,
                    "port": self._creds.port,
                    "username": self._creds.username,
                    "timeout": self._timeout,
                }
                if self._creds.key_file:
                    connect_kwargs["key_filename"] = self._creds.key_file
                    if self._creds.passphrase:
                        connect_kwargs["passphrase"] = self._creds.passphrase
                elif self._creds.password:
                    connect_kwargs["password"] = self._creds.password

                client.connect(**connect_kwargs)
                self._client = client
                self._connected = True
                self._last_heartbeat = time.monotonic()
                logger.info(f"SSH connected: {self._creds.hostname} (attempt {attempt})")
                return
            except Exception as e:
                logger.warning(f"SSH connect attempt {attempt}/{self._retries} failed: {e}")
                if attempt == self._retries:
                    raise ConnectionError(
                        f"Failed to connect to {self._creds.hostname} after {self._retries} attempts"
                    )
                time.sleep(2 ** attempt)  # exponential backoff

    def disconnect(self) -> None:
        """Close SSH connection."""
        if self._client:
            self._client.close()
            self._connected = False
            logger.info(f"SSH disconnected: {self._creds.hostname}")

    def heartbeat(self) -> bool:
        """Check if the connection is still alive."""
        if not self._client or not self._connected:
            return False
        try:
            transport = self._client.get_transport()
            if transport and transport.is_active():
                transport.send_ignore()
                self._last_heartbeat = time.monotonic()
                return True
        except Exception:
            pass
        self._connected = False
        return False

    def execute(self, command: str, timeout: int = 300) -> CommandResult:
        """Execute command on the remote target."""
        if not self._connected:
            self.connect()

        start = time.monotonic()
        timed_out = False

        try:
            stdin, stdout_ch, stderr_ch = self._client.exec_command(command, timeout=timeout)
            stdout = stdout_ch.read().decode("utf-8", errors="replace")
            stderr = stderr_ch.read().decode("utf-8", errors="replace")
            exit_code = stdout_ch.channel.recv_exit_status()
        except Exception as e:
            if "timed out" in str(e).lower():
                timed_out = True
            stdout, stderr = "", str(e)
            exit_code = -1

        duration = time.monotonic() - start
        truncated = False
        if len(stdout) > 1_000_000:
            stdout = stdout[:1_000_000] + "\n... [TRUNCATED]"
            truncated = True

        result = CommandResult(
            command=command,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration=duration,
            session_type=SessionType.REMOTE,
            timed_out=timed_out,
            truncated=truncated,
        )
        self._history.append(result)
        logger.debug(f"Remote cmd: '{command}' → exit={exit_code} ({duration:.2f}s)")
        return result

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def history(self) -> list[CommandResult]:
        return self._history


class SessionManager:
    """
    Dual-session multiplexer — routes commands to local or remote sessions.

    Usage:
        sm = SessionManager()
        result = await sm.execute_local("nmap -sV 10.10.10.5")
        sm.connect_remote(SSHCredentials(hostname="10.10.10.5", password="toor"))
        result = sm.execute_remote("id && whoami")
    """

    def __init__(self, shell: str = "/bin/bash", working_dir: Optional[str] = None):
        self._local = LocalSession(shell=shell, working_dir=working_dir)
        self._remote: Optional[RemoteSession] = None
        self._audit_log: list[dict[str, Any]] = []
        logger.info("SessionManager initialized")

    @property
    def local(self) -> LocalSession:
        return self._local

    @property
    def remote(self) -> Optional[RemoteSession]:
        return self._remote

    @property
    def has_remote(self) -> bool:
        return self._remote is not None and self._remote.is_connected

    async def execute_local(self, command: str, timeout: int = 300) -> CommandResult:
        """Execute command on the local attacking machine."""
        self._audit("local", command)
        return await self._local.execute(command, timeout=timeout)

    def execute_local_sync(self, command: str, timeout: int = 300) -> CommandResult:
        """Synchronous local execution."""
        self._audit("local", command)
        return self._local.execute_sync(command, timeout=timeout)

    def connect_remote(self, credentials: SSHCredentials, timeout: int = 30) -> None:
        """Establish SSH connection to a remote target."""
        self._remote = RemoteSession(credentials, timeout=timeout)
        self._remote.connect()
        self._audit("remote_connect", f"{credentials.hostname}:{credentials.port}")

    def execute_remote(self, command: str, timeout: int = 300) -> CommandResult:
        """Execute command on the remote target."""
        if not self._remote:
            raise RuntimeError("No remote session established. Call connect_remote() first.")
        self._audit("remote", command)
        return self._remote.execute(command, timeout=timeout)

    def disconnect_remote(self) -> None:
        """Disconnect the remote session."""
        if self._remote:
            self._remote.disconnect()
            self._audit("remote_disconnect", "")

    def _audit(self, session_type: str, command: str) -> None:
        """Record command in audit log."""
        entry = {
            "timestamp": time.time(),
            "session": session_type,
            "command": command,
        }
        self._audit_log.append(entry)

    @property
    def audit_log(self) -> list[dict[str, Any]]:
        return self._audit_log

    def get_stats(self) -> dict[str, Any]:
        """Get session statistics."""
        return {
            "local_commands": len(self._local.history),
            "remote_commands": len(self._remote.history) if self._remote else 0,
            "remote_connected": self.has_remote,
            "total_audit_entries": len(self._audit_log),
        }
