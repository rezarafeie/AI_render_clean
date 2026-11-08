from pathlib import Path

import pytest

from app.config import Settings
from brain import llm
from brain import lm_gateway
from brain.ai_provider import LocalFallbackProvider, RouterProvider, get_provider
from brain.elevenlabs_transport import base_url
from brain.media_provider import get_provider as media_provider, list_providers
from brain.tts import _configured_provider, generate_narration


def test_stale_configuration_cannot_override_policy(monkeypatch):
    settings = Settings(_env_file=None, APP_ENV="development", AI_PROVIDER="retired", CONTENT_TTS_PROVIDER="retired")
    assert settings.CONTENT_TTS_PROVIDER == settings.TTS_PROVIDER == "elevenlabs"
    assert _configured_provider("retired") == "elevenlabs"
    monkeypatch.setattr(lm_gateway, "configured", lambda: True)
    assert isinstance(get_provider("retired"), RouterProvider)          # whatever name a saved project holds, the router answers
    monkeypatch.setattr(lm_gateway, "configured", lambda: False)
    assert isinstance(get_provider("retired"), LocalFallbackProvider)   # no router: local templates, never a direct provider


def test_text_and_vision_need_the_router(monkeypatch):
    monkeypatch.setattr(lm_gateway, "configured", lambda: False)
    with pytest.raises(RuntimeError, match="router is not configured"):
        llm.chat_json("system", "user")
    with pytest.raises(RuntimeError, match="router is not configured"):
        llm.chat_vision("system", "user", images=[b"image"])


def test_vision_goes_through_the_router_route(monkeypatch):
    calls = []
    monkeypatch.setattr(lm_gateway, "configured", lambda: True)
    def complete(route, messages, **kwargs):
        calls.append((route, messages, kwargs))
        return {"choices": [{"message": {"content": '{"ok":true}'}}]}, {"requested_model": "m", "latency_ms": 5}
    monkeypatch.setattr(lm_gateway, "complete", complete)
    result, _ = llm.chat_vision("system", "user", images=[b"image"], return_json=True, route="visual_qc")
    assert result == {"ok": True}
    assert calls[0][0] == "visual_qc" and calls[0][2]["required"] == {"chat", "vision"}


def test_relay_is_required(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_PROXY_URL", raising=False)
    with pytest.raises(RuntimeError, match="relay"):
        base_url()
    monkeypatch.setenv("ELEVENLABS_PROXY_URL", "https://relay.vercel.app/api/elevenlabs/")
    assert base_url() == "https://relay.vercel.app/api/elevenlabs"


def test_all_narration_uses_localize_voice(monkeypatch, tmp_path):
    from brain import tts
    from brain.localize import tts_voice, tts_model
    calls = []
    def generate(text, output, **kwargs):
        calls.append(kwargs)
        Path(output).write_bytes(b"audio")
    monkeypatch.setattr(tts, "_generate_elevenlabs", generate)
    monkeypatch.setattr(tts, "_get_audio_duration", lambda path: 1.5)
    result = generate_narration("hello", tmp_path, provider="retired")
    assert result.provider == "elevenlabs"
    assert calls == [{"voice_id": tts_voice(), "model_id": tts_model()}]


def test_media_provider_is_the_router_or_the_local_fixture(monkeypatch):
    monkeypatch.setattr(lm_gateway, "configured", lambda: True)
    assert media_provider("retired_image").name == "lm_gateway"
    assert media_provider("local_fixture").name == "local_fixture"
    assert {item["name"] for item in list_providers()} == {"local_fixture", "lm_gateway"}
    monkeypatch.setattr(lm_gateway, "configured", lambda: False)
    with pytest.raises(RuntimeError, match="router is not configured"):
        media_provider("retired_image")


def test_provider_labels_do_not_introduce_direct_endpoints_outside_central_adapter():
    import re
    root = Path(__file__).parents[1]
    retired = ("sar" + "ovi", "jar" + "vis")
    for directory in ("app", "brain", "web/src"):
        for path in (root / directory).rglob("*"):
            if path.suffix in {".py", ".tsx", ".ts"}:
                if path == root / "brain" / "lm_direct.py":
                    # The one sanctioned place for direct provider endpoints: admin-controlled fallbacks used only
                    # after LM API fails (see docs/CREATIVE_ENGINE_DESIGN.md and the "Direct fallbacks" admin tab).
                    continue
                if path == root / "brain" / "lm_tasks.py":
                    # These providers are now allowed only as centrally scoped
                    # Gateway identities, never as direct network endpoints.
                    assert "https://" not in path.read_text()
                    continue
                # Provider names and Custom Endpoint group IDs are valid
                # gateway metadata, not direct connections. Guard literal
                # network origins instead of banning names in the admin UI.
                origins=re.findall(r'https?://[^\s\x27\x22<>]+',path.read_text().lower())
                assert not any(name in url for name in retired for url in origins), path
