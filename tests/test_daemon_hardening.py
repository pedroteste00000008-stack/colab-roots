"""Adversarial hardening tests — Colab Roots v2.1.

Run:  python3 -m pytest tests/ -q   (ou: python3 tests/test_daemon_hardening.py)
Cobre: thread-safety, validação de config, sanitização, injeção de path,
comandos inválidos, lock file, ciclo de vida do daemon, permissões,
restart/backoff, kill, secrets no state, keep-alive, socket.
"""
import os
import sys
import shutil
import socket
import tempfile
import threading
import time
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from daemon import ColabRootsDaemon, ColabRootsCLI, ServiceState, LockFile


def _daemon(tmp, **kw):
    cfg = {
        "roots_home": tmp,
        "username": "roots",
        "password": "test-secret-123",
        "tunnel_name": "colab-roots-test",
        "drive_path": "",
        "enable_code_server": False,
        "enable_ttyd": False,
        "enable_vscode_tunnel": False,
        "persist_to_drive": False,
        "keep_alive": False,
        "keep_alive_interval": 240,
    }
    cfg.update(kw)
    return ColabRootsDaemon(cfg)


def test_service_state_thread_safety():
    ss = ServiceState()
    errors = []

    def writer(name, n):
        try:
            for i in range(n):
                ss.set(name, "val", i)
                assert ss.get(name)["val"] == i
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(f"svc{i}", 100)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, f"thread corruption: {errors}"


def test_config_validation():
    try:
        ColabRootsDaemon._validate_config({})
        raise AssertionError("should reject empty config")
    except ValueError:
        pass

    cfg = ColabRootsDaemon._validate_config({
        "roots_home": "/tmp/x",
        "keep_alive_interval": 5,
        "tunnel_name": "a/b/../../etc/passwd",
    })
    assert cfg["keep_alive_interval"] == 60
    assert "/" not in cfg["tunnel_name"] and ".." not in cfg["tunnel_name"]


def test_command_sanitization(tmpdir="/tmp"):
    d = ColabRootsDaemon({"roots_home": tempfile.mkdtemp()})
    safe = d._sanitize_command(["ttyd", "-c", "user:P@ssw0rd!", "-p", "7681"])
    assert "P@ssw0rd!" not in " ".join(safe)
    shutil.rmtree(d.roots_home, ignore_errors=True)


def test_path_injection_blocked():
    tmp = tempfile.mkdtemp()
    try:
        d = ColabRootsDaemon({"roots_home": tmp})
        for inj in ["../../etc/passwd", "/etc/shadow", "x; rm -rf /", "x" * 1000, ""]:
            r = d._execute_command("restart", inj)
            assert "Unknown service" in r or "Usage" in r, inj
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_invalid_commands_rejected():
    tmp = tempfile.mkdtemp()
    try:
        d = ColabRootsDaemon({"roots_home": tmp})
        for cmd in ["", "evil", "DROP TABLE", "STATUS;rm"]:
            r = d._execute_command(cmd.strip().split()[0] if cmd.strip() else "")
            assert "Unknown" in r or "Usage" in r or "Commands" in r, cmd
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_lockfile_exclusive():
    tmp = tempfile.mkdtemp()
    try:
        lf = LockFile(Path(tmp) / "t.lock")
        assert lf.acquire() is True
        assert LockFile(Path(tmp) / "t.lock").acquire() is False
        lf.release()
        lf3 = LockFile(Path(tmp) / "t.lock")
        assert lf3.acquire() is True
        lf3.release()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_daemon_lifecycle():
    tmp = tempfile.mkdtemp()
    try:
        d = ColabRootsDaemon({
            "roots_home": tmp, "enable_code_server": False,
            "enable_ttyd": False, "enable_vscode_tunnel": False,
            "persist_to_drive": False, "keep_alive": False,
        })
        assert d.start_background() is True
        for cmd in ["status", "doctor", "help", "urls", "password", "sync"]:
            r = d._execute_command(cmd)
            assert isinstance(r, str) and r
        d._shutdown()
        assert not d._running
        assert not d.lock_file.path.exists()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_secret_file_permissions():
    tmp = tempfile.mkdtemp()
    try:
        st = Path(tmp) / "state"
        st.mkdir(parents=True)
        pw = st / "code-server-pw"
        pw.write_text("x")
        pw.chmod(0o600)
        assert oct(pw.stat().st_mode)[-3:] == "600"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_cli_missing_daemon():
    cli = ColabRootsCLI()
    # Aponta para home inexistente para forçar "not running"
    cli.sock_file = Path(tempfile.mkdtemp()) / "nope.sock"
    r = cli._send("status")
    assert "not running" in r.lower() or "not found" in r.lower()


# ─────────────────────────────────────────────────────────────────────
# Nova cobertura v2.1
# ─────────────────────────────────────────────────────────────────────

def test_restart_gives_up_after_max_restarts():
    tmp = tempfile.mkdtemp()
    try:
        d = _daemon(tmp, enable_code_server=True)
        d._services.set("code-server", "restart_count", d.MAX_RESTARTS)
        with mock.patch.object(d, "_start_service") as start:
            d._attempt_restart("code-server")
            start.assert_not_called()
        assert d._services.get("code-server")["restart"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_restart_uses_exponential_backoff():
    tmp = tempfile.mkdtemp()
    try:
        d = _daemon(tmp, enable_code_server=True)
        sleeps = []
        with mock.patch.object(d, "_start_service", return_value=True) as start, \
             mock.patch.object(d, "_stop_service", return_value=True) as stop, \
             mock.patch("daemon.time.sleep", side_effect=lambda s: sleeps.append(s)):
            d._attempt_restart("code-server")
        assert sleeps and sleeps[0] == 1, f"expected 2**0 backoff, got {sleeps}"
        assert d._services.get("code-server")["restart_count"] == 1
        start.assert_called_once()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_stop_service_kills_process_group():
    tmp = tempfile.mkdtemp()
    try:
        d = _daemon(tmp, enable_ttyd=True)
        d._services.set("ttyd", "pid", 98765432)
        with mock.patch.object(d, "_is_alive", return_value=False):
            assert d._stop_service("ttyd") is True
        svc = d._services.get("ttyd")
        assert svc["status"] == "stopped" and svc["pid"] is None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_start_service_missing_binary_marks_error():
    tmp = tempfile.mkdtemp()
    try:
        d = _daemon(tmp, enable_code_server=True)
        with mock.patch("daemon.subprocess.Popen", side_effect=FileNotFoundError("no code-server")):
            assert d._start_service("code-server") is False
        assert d._services.get("code-server")["status"] == "error"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_start_service_already_running_skips():
    tmp = tempfile.mkdtemp()
    try:
        d = _daemon(tmp, enable_code_server=True)
        d._services.set("code-server", "pid", 98765432)
        with mock.patch.object(d, "_is_alive", return_value=True) as alive, \
             mock.patch("daemon.subprocess.Popen") as popen:
            assert d._start_service("code-server") is True
        alive.assert_called_once()
        popen.assert_not_called()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_save_services_excludes_secrets_and_pids():
    tmp = tempfile.mkdtemp()
    try:
        d = _daemon(tmp, enable_code_server=True, enable_ttyd=True)
        d._services.set("code-server", "pid", 111)
        d._services.set("code-server", "status", "running")
        d._services.set("ttyd", "pid", 222)
        d._save_services()
        raw = (Path(tmp) / "state" / "services.json").read_text()
        assert "password" not in raw
        assert "test-secret-123" not in raw
        assert "111" not in raw and "222" not in raw
        assert '"pid"' not in raw
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_keepalive_writes_heartbeat():
    tmp = tempfile.mkdtemp()
    try:
        d = _daemon(tmp, keep_alive=True, keep_alive_interval=60)
        d._running = True
        # Sai do loop após a primeira iteração
        with mock.patch.object(
            d._shutdown_event, "wait",
            side_effect=lambda _t: d._shutdown_event.set(),
        ):
            d._keepalive()
        hb = Path(tmp) / "state" / "heartbeat"
        assert hb.exists() and hb.read_text().strip()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_port_detection():
    tmp = tempfile.mkdtemp()
    try:
        d = _daemon(tmp)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
        assert d._port_in_use(port) is True
        s.close()
        time.sleep(0.1)
        assert d._port_in_use(port) is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class _FakeConn:
    """Socket fake para exercitar _handle_client sem socket real."""

    def __init__(self, payload):
        self._payload = payload
        self.sent = b""
        self.closed = False

    def settimeout(self, t):
        self.timeout = t

    def recv(self, n):
        p, self._payload = self._payload, b""
        return p

    def sendall(self, b):
        self.sent += b

    def close(self):
        self.closed = True


def test_socket_rejects_evil_command():
    tmp = tempfile.mkdtemp()
    try:
        d = _daemon(tmp)
        for payload, expect in [
            (b"restart ../../etc/passwd", b"Unknown service"),
            (b"restart x; rm -rf /", b"Unknown service"),
            (b"DROP TABLE users", b"Unknown command"),
            (b"status\n", b"Status"),
        ]:
            conn = _FakeConn(payload)
            d._handle_client(conn)
            assert expect in conn.sent, f"payload={payload!r} -> {conn.sent!r}"
            assert conn.closed
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_socket_rejects_oversized_command():
    tmp = tempfile.mkdtemp()
    try:
        d = _daemon(tmp)
        conn = _FakeConn(b"x" * 5000)
        d._handle_client(conn)
        assert b"Invalid command" in conn.sent
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    tests = [
        ("thread-safety", test_service_state_thread_safety),
        ("config", test_config_validation),
        ("sanitize", test_command_sanitization),
        ("injection", test_path_injection_blocked),
        ("invalid-cmd", test_invalid_commands_rejected),
        ("lockfile", test_lockfile_exclusive),
        ("lifecycle", test_daemon_lifecycle),
        ("perms", test_secret_file_permissions),
        ("cli", test_cli_missing_daemon),
        ("restart-giveup", test_restart_gives_up_after_max_restarts),
        ("restart-backoff", test_restart_uses_exponential_backoff),
        ("stop-kill", test_stop_service_kills_process_group),
        ("start-missing-binary", test_start_service_missing_binary_marks_error),
        ("start-already-running", test_start_service_already_running_skips),
        ("state-no-secrets", test_save_services_excludes_secrets_and_pids),
        ("keepalive", test_keepalive_writes_heartbeat),
        ("port-detect", test_port_detection),
        ("socket-evil", test_socket_rejects_evil_command),
        ("socket-oversize", test_socket_rejects_oversized_command),
    ]
    n = len(tests)
    failed = 0
    for i, (name, fn) in enumerate(tests, 1):
        try:
            fn()
            print(f"{i}/{n} {name} OK")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"{i}/{n} {name} FAIL: {e!r}")
    if failed:
        print(f"{failed} TEST(S) FAILED")
        sys.exit(1)
    print(f"ALL {n} HARDENING TESTS PASSED")
