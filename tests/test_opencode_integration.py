#!/usr/bin/env python3
"""Regression coverage for OpenCode Web integration in Colab Roots."""

import importlib.util
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BUILDER = (ROOT / "scripts" / "build_notebook.py").read_text(encoding="utf-8")

spec = importlib.util.spec_from_file_location("roots_daemon", ROOT / "src" / "daemon.py")
daemon_mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(daemon_mod)
ColabRootsDaemon = daemon_mod.ColabRootsDaemon


def make_daemon(tmp: str):
    return ColabRootsDaemon({
        "roots_home": tmp,
        "enable_code_server": False,
        "enable_ttyd": False,
        "enable_vscode_tunnel": False,
        "enable_opencode": True,
        "password": "secret-pass",
        "username": "roots",
        "opencode_username": "opencode",
        "persist_to_drive": False,
    })


def test_notebook_enables_opencode_by_default():
    assert "ENABLE_OPENCODE       = True" in BUILDER
    assert '"ROOTS_ENABLE_OPENCODE": str(ENABLE_OPENCODE)' in BUILDER


def test_notebook_installs_current_opencode_v2():
    assert "https://opencode.ai/v2/install" in BUILDER
    assert 'OPENCODE_BIN_DIR = Path.home() / ".opencode" / "bin"' in BUILDER
    assert 'os.environ["PATH"] = f"{OPENCODE_BIN_DIR}' in BUILDER


def test_daemon_defines_opencode_web_service_on_4096():
    with tempfile.TemporaryDirectory() as tmp:
        daemon = make_daemon(tmp)
        svc = daemon._services.get("opencode")
        assert svc["enabled"] is True
        assert svc["port"] == 4096
        assert svc["command"][-5:] == [
            "serve", "--hostname", "127.0.0.1", "--port", "4096"
        ]
        assert svc["cwd"] == "/content/workspace"
        assert svc["env"]["OPENCODE_SERVER_USERNAME"] == "opencode"
        assert svc["env"]["OPENCODE_SERVER_PASSWORD"] == "secret-pass"


def test_daemon_passes_service_env_and_cwd_to_process():
    class FakeProc:
        pid = 424242

    with tempfile.TemporaryDirectory() as tmp:
        daemon = make_daemon(tmp)
        captured = {}

        def fake_popen(command, **kwargs):
            captured["command"] = command
            captured.update(kwargs)
            return FakeProc()

        with patch.object(daemon_mod.subprocess, "Popen", side_effect=fake_popen):
            assert daemon._start_service("opencode") is True

        assert captured["cwd"] == "/content/workspace"
        assert captured["env"]["OPENCODE_SERVER_USERNAME"] == "opencode"
        assert captured["env"]["OPENCODE_SERVER_PASSWORD"] == "secret-pass"
        assert captured["env"]["PATH"].startswith(str(Path.home() / ".opencode" / "bin"))


def test_fallback_starts_opencode_with_password_out_of_argv():
    assert 'OPENCODE_SERVER_PASSWORD' in BUILDER
    assert 'OPENCODE_SERVER_USERNAME' in BUILDER
    assert 'opencode serve --hostname 127.0.0.1 --port 4096' in BUILDER
    # Password must be injected through env, never interpolated into the command.
    assert 'OPENCODE_SERVER_PASSWORD=' not in BUILDER


def test_access_layer_uses_project_route_and_sse_capable_tunnel():
    assert "OPENCODE_PROJECT_SLUG" in BUILDER
    assert "base64.urlsafe_b64encode(str(ROOTS_WORKSPACE).encode())" in BUILDER
    assert 'OPENCODE_PROJECT_URL = f"{OPENCODE_BASE_URL}/{OPENCODE_PROJECT_SLUG}"' in BUILDER
    assert "start_opencode_tunnel" in BUILDER
    assert "nokey@localhost.run" in BUILDER
    assert 'start_quick_tunnel(4096, "opencode")' not in BUILDER
    assert "🤖 OpenCode" in BUILDER
    assert 'OPENCODE_USERNAME = os.environ.get("ROOTS_OPENCODE_USERNAME", "opencode")' in BUILDER
    assert "usuário: {OPENCODE_USERNAME}" in BUILDER


def test_opencode_probe_covers_project_scoped_api_and_sse():
    assert '"x-opencode-directory": str(ROOTS_WORKSPACE)' in BUILDER
    assert '"/api/location"' in BUILDER
    assert 'location.get("directory") != str(ROOTS_WORKSPACE)' in BUILDER
    assert '("/api/agent", True)' in BUILDER
    assert '("/api/provider", False)' in BUILDER
    assert '("/api/model", False)' in BUILDER
    assert '("/api/session", False)' in BUILDER
    assert "/api/event" in BUILDER
    assert "text/event-stream" in BUILDER


def test_manual_cloudflare_cell_does_not_expose_opencode():
    assert 'for name, port in (("IDE", 8080), ("Terminal", 7681)):' in BUILDER


def test_failed_install_does_not_start_missing_opencode():
    assert "OPENCODE_READY" in BUILDER
    assert "if ENABLE_OPENCODE and OPENCODE_READY and not listening(4096):" in BUILDER


if __name__ == "__main__":
    tests = [
        test_notebook_enables_opencode_by_default,
        test_notebook_installs_current_opencode_v2,
        test_daemon_defines_opencode_web_service_on_4096,
        test_daemon_passes_service_env_and_cwd_to_process,
        test_fallback_starts_opencode_with_password_out_of_argv,
        test_access_layer_uses_project_route_and_sse_capable_tunnel,
        test_opencode_probe_covers_project_scoped_api_and_sse,
        test_manual_cloudflare_cell_does_not_expose_opencode,
        test_failed_install_does_not_start_missing_opencode,
    ]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as exc:
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
    if failures:
        raise SystemExit(f"{failures} OpenCode integration test(s) failed")
    print(f"ALL {len(tests)} OPENCODE INTEGRATION TESTS PASSED")
