#!/usr/bin/env python3
"""Regression checks for Colab access-link generation.

The Colab runtime proxy origin returned by google.colab.kernel.proxyPort()
must not be printed as a reusable external URL. Colab's own window helper is
deprecated for browser-security reasons; external browser links must come from
an actual HTTP tunnel, while the Colab-native proxy may be used only through
its supported iframe helper.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER = (ROOT / "scripts" / "build_notebook.py").read_text(encoding="utf-8")


def test_start_does_not_print_raw_proxyport_url():
    marker = 'output.eval_js("google.colab.kernel.proxyPort('
    assert marker not in BUILDER, (
        "START/RE-LINK still converts proxyPort() into a raw external URL; "
        "those *.prod.colab.dev origins can return 404 outside Colab context"
    )


def test_start_has_supported_colab_iframe_fallback():
    assert "serve_kernel_port_as_iframe" in BUILDER, (
        "Expected Colab-native iframe access as the in-notebook fallback"
    )


def test_start_generates_real_external_tunnel_urls():
    assert "cloudflared" in BUILDER
    assert "trycloudflare.com" in BUILDER
    assert "start_quick_tunnel" in BUILDER


def test_relink_uses_tunnel_state_not_raw_proxy_origin():
    assert "cloudflare-code-server.url" in BUILDER
    assert "cloudflare-ttyd.url" in BUILDER


if __name__ == "__main__":
    tests = [
        test_start_does_not_print_raw_proxyport_url,
        test_start_has_supported_colab_iframe_fallback,
        test_start_generates_real_external_tunnel_urls,
        test_relink_uses_tunnel_state_not_raw_proxy_origin,
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
        raise SystemExit(f"{failures} access-link regression test(s) failed")
    print(f"ALL {len(tests)} ACCESS-LINK TESTS PASSED")
