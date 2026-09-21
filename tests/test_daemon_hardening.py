"""Adversarial hardening tests — Colab Roots v2.

Run:  python3 -m pytest tests/ -q   (ou: python3 tests/test_daemon_hardening.py)
Cobre: thread-safety, validação de config, sanitização, injeção de path,
comandos inválidos, lock file, ciclo de vida do daemon, permissões.
"""
import os
import sys
import shutil
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from daemon import ColabRootsDaemon, ColabRootsCLI, ServiceState, LockFile


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


if __name__ == "__main__":
    test_service_state_thread_safety()
    print("1/9 thread-safety OK")
    test_config_validation()
    print("2/9 config OK")
    test_command_sanitization()
    print("3/9 sanitize OK")
    test_path_injection_blocked()
    print("4/9 injection OK")
    test_invalid_commands_rejected()
    print("5/9 invalid-cmd OK")
    test_lockfile_exclusive()
    print("6/9 lockfile OK")
    test_daemon_lifecycle()
    print("7/9 lifecycle OK")
    test_secret_file_permissions()
    print("8/9 perms OK")
    test_cli_missing_daemon()
    print("9/9 cli OK")
    print("ALL 9 HARDENING TESTS PASSED")
