"""A page the relay cannot reach (an Iranian shop that refuses foreign addresses) is asked directly once more, with the full timeout."""
import time

import pytest

from app import studio_url


def _args(**extra):
    return dict(max_bytes=1000, accept="text/html", headers=None, timeout=20, allow_http_error=False, with_status=False, **extra)


def test_relay_failure_falls_back_to_a_direct_fetch_and_clears_the_failed_mark(monkeypatch):
    url = "https://shop.example.ir/product/1"
    studio_url._DIRECT_FAILED["shop.example.ir"] = time.monotonic() + 300
    seen = {}
    monkeypatch.setattr(studio_url, "_relay_fetch", lambda *a, **k: (_ for _ in ()).throw(ValueError("The relay could not fetch the page (HTTP 403)")))
    def direct(url, **kwargs):
        seen.update(kwargs)
        return (b"<html>ok</html>", url, "text/html")
    monkeypatch.setattr(studio_url, "_fetch_direct", direct)
    assert studio_url._relay_or_direct(url, **_args())[0] == b"<html>ok</html>"
    assert seen["timeout"] == 20                                     # the whole timeout, not the few seconds of the first attempt
    assert "shop.example.ir" not in studio_url._DIRECT_FAILED


def test_when_both_fail_the_relays_error_is_reported(monkeypatch):
    monkeypatch.setattr(studio_url, "_relay_fetch", lambda *a, **k: (_ for _ in ()).throw(ValueError("The relay could not fetch the page (HTTP 502)")))
    monkeypatch.setattr(studio_url, "_fetch_direct", lambda *a, **k: (_ for _ in ()).throw(OSError("timed out")))
    with pytest.raises(ValueError, match="relay could not fetch"):
        studio_url._relay_or_direct("https://shop.example.ir/x", **_args())


def test_fetch_uses_the_direct_fallback_when_the_host_was_marked_failed(monkeypatch):
    monkeypatch.setattr(studio_url, "_relay_configured", lambda: True)
    monkeypatch.setattr(studio_url, "_relay_public_url", lambda value: value)
    studio_url._DIRECT_FAILED["shop2.example.ir"] = time.monotonic() + 300
    monkeypatch.setattr(studio_url, "_relay_fetch", lambda *a, **k: (_ for _ in ()).throw(ValueError("The relay could not fetch the page (HTTP 403)")))
    monkeypatch.setattr(studio_url, "_fetch_direct", lambda url, **k: (b"direct", url, "text/html"))
    assert studio_url._fetch("https://shop2.example.ir/p", max_bytes=1000, accept="text/html")[0] == b"direct"
