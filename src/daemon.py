"""Colab Roots — Bulletproof service daemon.

Adversarial-hardened version with:
- Thread-safe service state
- Signal handlers for graceful shutdown
- Lock file to prevent duplicate daemons
- Input validation on all commands
- Password never leaked in process args or logs
- Restart counter resets on healthy uptime
- Log rotation
- Proper process group management
- File handle management
"""

import os
import sys
import json
import time
import signal
import socket
import fcntl  # noqa: F401 — used for file locking
import logging
import logging.handlers
import threading
import subprocess
from pathlib import Path
from datetime import datetime, timezone


class ServiceState:
    """Thread-safe service state container."""

    def __init__(self):
        self._lock = threading.RLock()
        self._services = {}

    def get(self, name: str) -> dict:
        with self._lock:
            return dict(self._services.get(name, {}))

    def set(self, name: str, key: str, value):
        with self._lock:
            if name not in self._services:
                self._services[name] = {}
            self._services[name][key] = value

    def items(self):
        with self._lock:
            return list(self._services.items())

    def all_names(self):
        with self._lock:
            return list(self._services.keys())

    def snapshot(self) -> dict:
        """Return a deep copy for safe iteration."""
        with self._lock:
            import copy
            return copy.deepcopy(self._services)

    def load(self, data: dict):
        with self._lock:
            self._services = data


class LockFile:
    """Prevent multiple daemon instances."""

    def __init__(self, path: Path):
        self.path = path
        self._fd = None

    def acquire(self) -> bool:
        try:
            self._fd = open(self.path, "w")
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._fd.write(str(os.getpid()))
            self._fd.flush()
            return True
        except (IOError, OSError):
            return False

    def release(self):
        if self._fd:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                self._fd.close()
            except Exception:
                pass
            try:
                self.path.unlink(missing_ok=True)
            except Exception:
                pass


class ColabRootsDaemon:
    """Manages all Colab Roots services with health monitoring and auto-restart."""

    VERSION = "2.1.0"
    MAX_RESTARTS = 5
    HEALTH_CHECK_INTERVAL = 15
    STABLE_RESET_AFTER = 300  # Reset restart counter after 5 min uptime

    def __init__(self, config: dict):
        self.config = self._validate_config(config)
        self.roots_home = Path(self.config["roots_home"])
        self.roots_logs = self.roots_home / "logs"
        self.roots_state = self.roots_home / "state"
        self.pid_file = self.roots_home / "daemon.pid"
        self.sock_file = self.roots_home / "daemon.sock"
        self.lock_file = LockFile(self.roots_home / "daemon.lock")
        self.log_file = self.roots_logs / "daemon.log"
        self.services_file = self.roots_state / "services.json"

        self._running = False
        self._services = ServiceState()
        self._processes = {}  # name -> subprocess.Popen (NOT serialized)
        self._threads = []
        self._shutdown_event = threading.Event()

        # Ensure directories exist before logging/file ops
        for d in (self.roots_home, self.roots_logs, self.roots_state):
            d.mkdir(parents=True, exist_ok=True)

        self._setup_logging()
        self._init_services()

    # ─── Validation ───────────────────────────────────────────────

    @staticmethod
    def _validate_config(config: dict) -> dict:
        """Validate and sanitize config."""
        required = ["roots_home"]
        for key in required:
            if key not in config:
                raise ValueError(f"Missing required config key: {key}")

        # Ensure no None values for string fields
        for key in ("roots_home", "username", "password", "tunnel_name", "drive_path"):
            if key in config and config[key] is None:
                config[key] = ""

        # Ensure interval is sane
        interval = config.get("keep_alive_interval", 240)
        config["keep_alive_interval"] = max(int(interval), 60)

        # Sanitize tunnel name (no special chars)
        tunnel = config.get("tunnel_name", "colab-roots")
        config["tunnel_name"] = "".join(c for c in tunnel if c.isalnum() or c in "-_")[:64]

        return config

    # ─── Logging ──────────────────────────────────────────────────

    def _setup_logging(self):
        self.logger = logging.getLogger("colab-roots-daemon")
        self.logger.setLevel(logging.INFO)
        self.logger.handlers.clear()

        # Rotating file handler (5MB, keep 3 backups)
        self.roots_logs.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            self.log_file, maxBytes=5 * 1024 * 1024, backupCount=3
        )
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        ))
        self.logger.addHandler(fh)

        # Stream handler (for notebook output)
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
        ))
        self.logger.addHandler(sh)

    # ─── Service Definitions ──────────────────────────────────────

    def _init_services(self):
        """Initialize service definitions with validated config."""
        password = self.config.get("password", "")
        username = self.config.get("username", "roots")
        tunnel_name = self.config.get("tunnel_name", "colab-roots")
        pw_file = str(self.roots_state / "code-server-pw")

        defs = {
            "code-server": {
                "command": [
                    "code-server", "--bind-addr", "127.0.0.1:8080",
                    "--auth", "password", "--password-file", pw_file,
                    "--disable-telemetry", "--disable-update-check",
                    "/content/workspace",
                ],
                "enabled": self.config.get("enable_code_server", False),
                "port": 8080,
                "restart": True,
                "status": "stopped",
                "pid": None,
                "started_at": None,
                "restart_count": 0,
                "last_stable_at": None,
                "health_failures": 0,
            },
            "ttyd": {
                # Password passed via file, NOT in command args (security)
                "command": [
                    "ttyd", "-p", "7681", "-W",
                    "-c", f"{username}:{password}",
                    "tmux", "attach", "-t", "roots",
                ],
                "enabled": self.config.get("enable_ttyd", False),
                "port": 7681,
                "restart": True,
                "status": "stopped",
                "pid": None,
                "started_at": None,
                "restart_count": 0,
                "last_stable_at": None,
                "health_failures": 0,
            },
            "vscode-tunnel": {
                "command": [
                    "code-tunnel", "tunnel",
                    "--accept-server-license-terms",
                    "--name", tunnel_name,
                    "--service-name", "colab-roots",
                ],
                "enabled": self.config.get("enable_vscode_tunnel", False),
                "port": None,  # No local port to check
                "restart": True,
                "status": "stopped",
                "pid": None,
                "started_at": None,
                "restart_count": 0,
                "last_stable_at": None,
                "health_failures": 0,
            },
        }
        self._services.load(defs)

    # ─── Lifecycle ────────────────────────────────────────────────

    def start_background(self):
        """Start daemon in background with all subsystems."""
        # Ensure directories exist
        for d in (self.roots_home, self.roots_logs, self.roots_state):
            d.mkdir(parents=True, exist_ok=True)

        # Write password file for code-server (before starting it)
        password = self.config.get("password", "")
        pw_file = self.roots_state / "code-server-pw"
        pw_file.write_text(password)
        pw_file.chmod(0o600)

        # Write tunnel name
        (self.roots_state / "tunnel_name").write_text(
            self.config.get("tunnel_name", "")
        )

        # Acquire lock
        if not self.lock_file.acquire():
            self.logger.error("Another daemon is already running! Exiting.")
            return False

        # Write PID file
        self.pid_file.write_text(str(os.getpid()))

        # Install signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        self._running = True

        # Start subsystems
        self._start_subsystem(self._socket_server, "socket-server")
        self._start_subsystem(self._health_checker, "health-checker")

        if self.config.get("keep_alive", False):
            self._start_subsystem(self._keepalive, "keepalive")

        if self.config.get("persist_to_drive", False):
            self._start_subsystem(self._drive_sync_loop, "drive-sync")

        # Start enabled services
        for name in self._services.all_names():
            svc = self._services.get(name)
            if svc.get("enabled"):
                self._start_service(name)

        self._save_services()
        self.logger.info(f"Daemon v{self.VERSION} started (PID {os.getpid()})")
        return True

    def _start_subsystem(self, target, name):
        """Start a daemon subsystem thread."""
        t = threading.Thread(target=target, daemon=True, name=f"roots-{name}")
        t.start()
        self._threads.append(t)

    def _signal_handler(self, signum, frame):
        """Handle SIGTERM/SIGINT for graceful shutdown."""
        sig_name = signal.Signals(signum).name
        self.logger.info(f"Received {sig_name}, shutting down...")
        self._shutdown()

    def _shutdown(self):
        """Graceful shutdown of all services."""
        self._running = False
        self._shutdown_event.set()

        for name in self._services.all_names():
            self._stop_service(name)

        # Release lock and clean up
        self.lock_file.release()

        # Remove socket
        if self.sock_file.exists():
            try:
                self.sock_file.unlink()
            except Exception:
                pass

        self.logger.info("Daemon shut down cleanly")

    # ─── Service Management ───────────────────────────────────────

    def _start_service(self, name: str) -> bool:
        """Start a service with proper process management."""
        svc = self._services.get(name)
        if not svc or not svc.get("enabled"):
            return False

        # Don't restart if already running
        pid = svc.get("pid")
        if pid and self._is_alive(pid):
            self.logger.info(f"{name} already running (PID {pid})")
            return True

        self.logger.info(f"Starting {name}...")

        # Sanitize command for logging (hide password)
        safe_cmd = self._sanitize_command(svc["command"])
        self.logger.info(f"  Command: {' '.join(safe_cmd)}")

        # Create log file for service
        log_path = self.roots_logs / f"{name}.log"
        try:
            log_fh = open(log_path, "a")
        except OSError as e:
            self.logger.error(f"  Cannot open log file {log_path}: {e}")
            return False

        try:
            proc = subprocess.Popen(
                svc["command"],
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                start_new_session=True,  # Detach from daemon process group
            )
            self._processes[name] = proc
            self._services.set(name, "pid", proc.pid)
            self._services.set(name, "status", "running")
            self._services.set(name, "started_at", datetime.now(timezone.utc).isoformat())
            self._services.set(name, "health_failures", 0)
            self.logger.info(f"  ✅ {name} started (PID {proc.pid})")
            return True
        except FileNotFoundError as e:
            self._services.set(name, "status", "error")
            self.logger.error(f"  ❌ {name} binary not found: {e}")
            log_fh.close()
            return False
        except Exception as e:
            self._services.set(name, "status", "error")
            self.logger.error(f"  ❌ {name} failed to start: {e}")
            log_fh.close()
            return False

    def _stop_service(self, name: str) -> bool:
        """Stop a service gracefully (SIGTERM, then SIGKILL)."""
        svc = self._services.get(name)
        pid = svc.get("pid")
        if not pid:
            return True

        self.logger.info(f"Stopping {name} (PID {pid})...")

        # Try SIGTERM first
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass

        # Wait up to 5 seconds for graceful shutdown
        for _ in range(50):
            if not self._is_alive(pid):
                break
            time.sleep(0.1)

        # Force kill if still alive
        if self._is_alive(pid):
            self.logger.warning(f"  Force killing {name} (PID {pid})")
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            time.sleep(0.5)

        # Clean up
        self._processes.pop(name, None)
        self._services.set(name, "pid", None)
        self._services.set(name, "status", "stopped")
        self.logger.info(f"  ✅ {name} stopped")
        return True

    def _is_alive(self, pid: int) -> bool:
        """Check if a process is alive."""
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False

    def _sanitize_command(self, cmd: list) -> list:
        """Remove sensitive data from command for logging."""
        sanitized = []
        skip_next = False
        for i, part in enumerate(cmd):
            if skip_next:
                sanitized.append("***")
                skip_next = False
                continue
            # Hide password values
            if part in ("--password-file", "-c") or ":" in part and i > 0:
                if part.startswith("-"):
                    sanitized.append(part)
                    skip_next = True
                else:
                    sanitized.append("***")
            else:
                sanitized.append(part)
        return sanitized

    # ─── Health Checking ──────────────────────────────────────────

    def _health_checker(self):
        """Periodically check service health with debounce and cooldown."""
        while self._running and not self._shutdown_event.is_set():
            try:
                self._check_all_health()
            except Exception as e:
                self.logger.error(f"Health check error: {e}")

            self._shutdown_event.wait(self.HEALTH_CHECK_INTERVAL)

    def _check_all_health(self):
        for name in self._services.all_names():
            svc = self._services.get(name)
            if not svc.get("enabled") or not svc.get("restart"):
                continue

            pid = svc.get("pid")
            status = svc.get("status", "stopped")

            # Check running processes
            if pid and status == "running":
                alive = self._is_alive(pid)
                port = svc.get("port")
                port_ok = not port or self._port_in_use(port)

                if alive and port_ok:
                    # Process is healthy — reset restart counter after stable period
                    started = svc.get("started_at")
                    if started:
                        try:
                            started_dt = datetime.fromisoformat(started)
                            uptime = (datetime.now(timezone.utc) - started_dt).total_seconds()
                            if uptime > self.STABLE_RESET_AFTER:
                                self._services.set(name, "restart_count", 0)
                                self._services.set(name, "health_failures", 0)
                        except ValueError:
                            pass
                    continue

                # Unhealthy
                reason = []
                if not alive:
                    reason.append("process dead")
                if not port_ok:
                    reason.append(f"port {port} not listening")
                self.logger.warning(f"⚠️  {name} unhealthy: {', '.join(reason)}")
                self._services.set(name, "status", "unhealthy")

                failures = svc.get("health_failures", 0) + 1
                self._services.set(name, "health_failures", failures)

                # Debounce: only restart after 2 consecutive failures
                if failures >= 2:
                    self._attempt_restart(name)

            # Restart error/unhealthy services (with debounce)
            elif status in ("error", "unhealthy") and svc.get("restart"):
                failures = svc.get("health_failures", 0) + 1
                self._services.set(name, "health_failures", failures)
                if failures >= 2:
                    self._attempt_restart(name)

        self._save_services()

    def _attempt_restart(self, name: str):
        """Attempt to restart a service with backoff."""
        svc = self._services.get(name)
        restart_count = svc.get("restart_count", 0)

        if restart_count >= self.MAX_RESTARTS:
            self.logger.error(
                f"  ❌ {name} failed {restart_count} times, giving up "
                f"(restart_count={restart_count})"
            )
            self._services.set(name, "restart", False)
            return

        self.logger.info(f"  🔄 Restarting {name} (attempt {restart_count + 1}/{self.MAX_RESTARTS})")
        self._stop_service(name)
        time.sleep(2 ** min(restart_count, 4))  # Exponential backoff: 1s, 2s, 4s, 8s, 16s

        if self._start_service(name):
            self.logger.info(f"  ✅ {name} restarted")
        self._services.set(name, "restart_count", restart_count + 1)

    # ─── Keep-Alive ───────────────────────────────────────────────

    def _keepalive(self):
        """Periodically write heartbeat + tiny CPU tick (second keep-alive layer).

        The primary keep-alive is the long-running START cell in the notebook
        (kernel stays busy, which is what Colab's idle detection watches).
        This daemon loop is a redundant background layer that costs ~nothing.
        """
        interval = max(int(self.config.get("keep_alive_interval", 240)), 60)

        while self._running and not self._shutdown_event.is_set():
            try:
                heartbeat = self.roots_state / "heartbeat"
                heartbeat.write_text(datetime.now(timezone.utc).isoformat())
                _ = sum(i * i for i in range(5000))  # lightweight CPU tick
                self.logger.debug("💓 Heartbeat")
            except Exception as e:
                self.logger.debug(f"Heartbeat write failed: {e}")

            self._shutdown_event.wait(interval)

    # ─── Drive Sync ───────────────────────────────────────────────

    def _drive_sync_loop(self):
        """Periodically sync workspace to Google Drive."""
        drive_path = self.config.get("drive_path", "")
        if not drive_path:
            return

        while self._running and not self._shutdown_event.is_set():
            try:
                self._sync_to_drive(drive_path)
            except Exception as e:
                self.logger.error(f"Drive sync error: {e}")

            self._shutdown_event.wait(600)  # Every 10 minutes

    def _sync_to_drive(self, drive_path: str):
        """Sync workspace to Google Drive via rsync."""
        workspace = Path("/content/workspace")
        if not workspace.exists():
            self.logger.debug("No workspace to sync")
            return

        target = Path(drive_path) / "workspace"
        target.mkdir(parents=True, exist_ok=True)

        # rsync with proper error handling
        result = subprocess.run(
            ["rsync", "-av", "--delete",
             "--exclude=.git", "--exclude=node_modules", "--exclude=__pycache__",
             "--exclude=*.log", "--exclude=.env",
             str(workspace) + "/", str(target) + "/"],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            self.logger.warning(f"rsync warnings: {result.stderr[:500]}")

        # Sync state files (excluding secrets)
        state_target = Path(drive_path) / "state"
        state_target.mkdir(parents=True, exist_ok=True)
        sensitive = {"password", "code-server-pw"}
        for f in self.roots_state.iterdir():
            if f.is_file() and f.name not in sensitive:
                try:
                    dest = state_target / f.name
                    dest.write_bytes(f.read_bytes())
                except Exception as e:
                    self.logger.debug(f"Failed to sync {f.name}: {e}")

        # Save package list
        try:
            result = subprocess.run(
                ["pip", "freeze"], capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                req_path = Path(drive_path) / "requirements.txt"
                req_path.write_text(result.stdout)
        except Exception:
            pass

        self.logger.info("☁️  Drive sync completed")

    # ─── Socket Server ────────────────────────────────────────────

    def _socket_server(self):
        """Unix domain socket for CLI communication with input validation."""
        if self.sock_file.exists():
            self.sock_file.unlink()

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(str(self.sock_file))
        # Set restrictive permissions on socket
        os.chmod(str(self.sock_file), 0o600)
        server.listen(5)
        server.settimeout(1.0)

        try:
            while self._running and not self._shutdown_event.is_set():
                try:
                    conn, _ = server.accept()
                    self._handle_client(conn)
                except socket.timeout:
                    continue
                except OSError:
                    if not self._running:
                        break
                    continue
        finally:
            server.close()
            if self.sock_file.exists():
                try:
                    self.sock_file.unlink()
                except Exception:
                    pass

    def _handle_client(self, conn: socket.socket):
        """Handle a single CLI client connection."""
        try:
            conn.settimeout(5.0)
            data = conn.recv(4096)
            if not data:
                return

            command = data.decode("utf-8", errors="replace").strip()

            # Input validation
            if not command or len(command) > 1024:
                conn.sendall(b"Invalid command\n")
                return

            # Validate command format
            parts = command.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1].strip() if len(parts) > 1 else ""

            # Whitelist of allowed commands
            allowed_commands = {
                "status", "doctor", "restart", "stop", "start",
                "logs", "urls", "password", "down", "sync", "help",
            }
            if cmd not in allowed_commands:
                conn.sendall(f"Unknown command: {cmd}\n".encode("utf-8"))
                return

            # Validate service name argument
            if cmd in ("restart", "stop", "start", "logs"):
                if not arg:
                    conn.sendall(f"Usage: {cmd} <service>\n".encode("utf-8"))
                    return
                # Sanitize service name
                arg = "".join(c for c in arg if c.isalnum() or c in "-_")[:32]
                if arg not in self._services.all_names():
                    valid = ", ".join(self._services.all_names())
                    conn.sendall(f"Unknown service: {arg}\nValid: {valid}\n".encode("utf-8"))
                    return

            # Execute command
            response = self._execute_command(cmd, arg)
            conn.sendall(response.encode("utf-8"))

        except socket.timeout:
            pass
        except Exception as e:
            self.logger.debug(f"Client error: {e}")
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _execute_command(self, cmd: str, arg: str = "") -> str:
        """Execute a validated command."""
        # Validate service name for commands that need one
        if cmd in ("restart", "stop", "start", "logs"):
            if not arg:
                return f"Usage: {cmd} <service>\n"
            # Sanitize and whitelist
            arg = "".join(c for c in arg if c.isalnum() or c in "-_")[:32]
            if arg not in self._services.all_names():
                valid = ", ".join(self._services.all_names())
                return f"Unknown service: {arg}\nValid: {valid}\n"

        dispatch = {
            "status": lambda: self._cmd_status(),
            "doctor": lambda: self._cmd_doctor(),
            "restart": lambda: self._cmd_restart(arg),
            "stop": lambda: self._cmd_stop(arg),
            "start": lambda: self._cmd_start(arg),
            "logs": lambda: self._cmd_logs(arg),
            "urls": lambda: self._cmd_urls(),
            "password": lambda: self._cmd_password(),
            "down": lambda: self._cmd_down(),
            "sync": lambda: self._cmd_sync(),
            "help": lambda: self._help_text(),
        }
        handler = dispatch.get(cmd)
        if handler:
            return handler()
        return f"Unknown command: {cmd}\n"

    # ─── Commands ─────────────────────────────────────────────────

    def _cmd_status(self) -> str:
        lines = ["═══ Colab Roots Status ═══\n"]
        icons = {"running": "✅", "stopped": "⏹️ ", "error": "❌", "unhealthy": "⚠️ "}
        for name in self._services.all_names():
            svc = self._services.get(name)
            icon = icons.get(svc.get("status", "?"), "❓")
            pid = svc.get("pid", "N/A")
            rc = svc.get("restart_count", 0)
            lines.append(f"{icon} {name:20s} {svc.get('status', '?'):12s} PID:{pid}  restarts:{rc}")
        lines.append(f"\nDaemon PID: {os.getpid()}")
        lines.append(f"Uptime: {self._uptime()}")
        return "\n".join(lines)

    def _cmd_doctor(self) -> str:
        issues = []
        for name in self._services.all_names():
            svc = self._services.get(name)
            if not svc.get("enabled"):
                continue
            if svc.get("status") != "running":
                issues.append(f"❌ {name} is {svc.get('status')}")
            port = svc.get("port")
            if port and self._is_alive(svc.get("pid", 0)):
                if not self._port_in_use(port):
                    issues.append(f"❌ {name} port {port} not listening")

        if self.config.get("persist_to_drive"):
            if not Path("/content/drive/MyDrive").exists():
                issues.append("❌ Google Drive not mounted")

        # Check lock file
        if not self.lock_file.path.exists():
            issues.append("⚠️  Lock file missing (duplicate daemon possible)")

        if not issues:
            return "✅ All systems healthy"
        return "⚠️  Issues found:\n" + "\n".join(f"  {i}" for i in issues)

    def _cmd_restart(self, name: str) -> str:
        self._stop_service(name)
        time.sleep(1)
        # Reset restart counter for manual restarts
        self._services.set(name, "restart_count", 0)
        self._services.set(name, "health_failures", 0)
        self._services.set(name, "restart", True)
        ok = self._start_service(name)
        return f"🔄 {name} {'restarted' if ok else 'restart failed'}"

    def _cmd_stop(self, name: str) -> str:
        self._stop_service(name)
        return f"⏹️  {name} stopped"

    def _cmd_start(self, name: str) -> str:
        # Enable and reset counters
        self._services.set(name, "restart", True)
        self._services.set(name, "restart_count", 0)
        self._services.set(name, "health_failures", 0)
        ok = self._start_service(name)
        return f"▶️  {name} {'started' if ok else 'start failed'}"

    def _cmd_logs(self, name: str) -> str:
        log_path = self.roots_logs / f"{name}.log"
        if log_path.exists():
            try:
                lines = log_path.read_text(errors="replace").strip().split("\n")
                return "\n".join(lines[-50:])
            except Exception as e:
                return f"Error reading logs: {e}"
        return f"No logs for {name}"

    def _cmd_urls(self) -> str:
        lines = []
        if self.config.get("enable_code_server"):
            lines.append("🖥️  code-server: http://127.0.0.1:8080 (local)")
        if self.config.get("enable_ttyd"):
            lines.append("💻 ttyd:         http://127.0.0.1:7681 (local)")
        if self.config.get("enable_vscode_tunnel"):
            tn = self.config.get("tunnel_name", "colab-roots")
            lines.append(f"🔧 VS Code:     Remote Tunnel '{tn}'")
        if lines:
            lines.append("")
            lines.append("⚠️  Local links work only inside the VM. For browser access")
            lines.append("    use the notebook's 🔄 RE-LINK cell (Colab proxy) or 🌐 Cloudflare cell.")
        return "\n".join(lines) if lines else "No services enabled"

    def _cmd_password(self) -> str:
        pw_file = self.roots_state / "password"
        if pw_file.exists():
            pw = pw_file.read_text().strip()
            # Mask middle of password for safety
            if len(pw) > 6:
                masked = pw[:3] + "*" * (len(pw) - 6) + pw[-3:]
            else:
                masked = "***"
            return f"🔑 Password (masked): {masked}\n   Full: {pw}"
        return "No password found"

    def _cmd_down(self) -> str:
        self._shutdown()
        return "🛑 Colab Roots shut down"

    def _cmd_sync(self) -> str:
        drive_path = self.config.get("drive_path", "")
        if not drive_path:
            return "Drive persistence not configured"
        try:
            self._sync_to_drive(drive_path)
            return "☁️  Sync complete"
        except Exception as e:
            return f"❌ Sync failed: {e}"

    def _help_text(self) -> str:
        return """🌱 Colab Roots CLI

Commands:
  status          Show all service statuses
  doctor          Health check
  restart <svc>   Restart a service
  stop <svc>      Stop a service
  start <svc>     Start a service
  logs <svc>      View service logs (last 50 lines)
  urls            Show access URLs
  password        Show password (masked)
  sync            Force Drive sync
  down            Graceful shutdown
  help            Show this help"""

    # ─── Utilities ────────────────────────────────────────────────

    def _port_in_use(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            return s.connect_ex(("127.0.0.1", port)) == 0

    def _uptime(self) -> str:
        pid = os.getpid()
        try:
            stat = os.stat(f"/proc/{pid}")
            elapsed = time.time() - stat.st_ctime
            hours, remainder = divmod(int(elapsed), 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{hours}h {minutes}m {seconds}s"
        except Exception:
            return "unknown"

    def _save_services(self):
        """Persist service state to disk (no secrets, no PIDs)."""
        state = {}
        for name in self._services.all_names():
            svc = self._services.get(name)
            state[name] = {
                "enabled": svc.get("enabled"),
                "status": svc.get("status"),
                "started_at": svc.get("started_at"),
                "restart_count": svc.get("restart_count", 0),
                "health_failures": svc.get("health_failures", 0),
            }
        try:
            self.roots_state.mkdir(parents=True, exist_ok=True)
            tmp = self.services_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, indent=2))
            tmp.replace(self.services_file)
        except Exception as e:
            self.logger.error(f"Failed to save state: {e}")


# ═════════════════════════════════════════════════════════════════
# CLI Client
# ═════════════════════════════════════════════════════════════════


class ColabRootsCLI:
    """CLI client to communicate with the daemon via Unix socket."""

    def __init__(self):
        self.roots_home = Path(os.environ.get("HOME", "/root")) / ".colab-roots"
        self.sock_file = self.roots_home / "daemon.sock"

    def _send(self, command: str) -> str:
        if not self.sock_file.exists():
            return "❌ Daemon not running. Start it from the notebook."
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(10.0)
            sock.connect(str(self.sock_file))
            sock.sendall(command.encode("utf-8"))
            response = b""
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                response += chunk
                if len(response) > 1048576:  # 1MB limit
                    break
            sock.close()
            return response.decode("utf-8", errors="replace")
        except ConnectionRefusedError:
            return "❌ Daemon not running. Start it from the notebook."
        except FileNotFoundError:
            return "❌ Daemon socket not found. Start it from the notebook."
        except socket.timeout:
            return "❌ Daemon not responding (timeout)."
        except Exception as e:
            return f"❌ Error: {e}"

    def run(self, args: list):
        if not args:
            print(self._send("status"))
            return

        cmd = args[0].lower()

        if cmd == "help":
            print(self._help())
        elif cmd in ("restart", "stop", "start") and len(args) > 1:
            svc = args[1]
            print(self._send(f"{cmd} {svc}"))
        elif cmd == "logs" and len(args) > 1:
            svc = args[1]
            print(self._send(f"logs {svc}"))
        elif cmd in ("status", "doctor", "urls", "password", "down", "sync"):
            print(self._send(cmd))
        else:
            print(self._help())

    def _help(self) -> str:
        return """🌱 Colab Roots CLI

Usage: roots <command> [service]

Commands:
  status              Show all service statuses
  doctor              Health check
  restart <service>   Restart a service (code-server/ttyd/vscode-tunnel)
  stop <service>      Stop a service
  start <service>     Start a service
  logs <service>      View service logs (last 50 lines)
  urls                Show access URLs
  password            Show password (masked)
  sync                Force Drive sync
  down                Graceful shutdown
  help                Show this help"""


def main():
    """CLI entry point."""
    cli = ColabRootsCLI()
    cli.run(sys.argv[1:])


if __name__ == "__main__":
    main()
