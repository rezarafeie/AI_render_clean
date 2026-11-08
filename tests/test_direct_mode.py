"""The router setting "direct mode": the gateway (lmapi.rafiei.co) is switched off and the app talks to the providers' own APIs."""
import os

import httpx
import pytest
from fastapi import HTTPException

from app import lm_store as store
from app.config import settings
from app.routers import lm_admin
from brain import lm_direct as direct
from brain import lm_gateway as gateway


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    direct._REJECTED.clear()
    monkeypatch.setattr(settings, "JOBS_DIR", str(tmp_path))
    for name in list(os.environ):
        if name.startswith("DIRECT_"):
            monkeypatch.delenv(name)
    for legacy in ("OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setattr(settings, legacy, "")
    monkeypatch.setattr(settings, "LMAPI_API_KEY", "gateway-key-" + "x" * 20)
    # any call that reaches the gateway fails the test
    def gateway_called(*args, **kwargs):
        raise AssertionError("the gateway must not be called in direct mode")
    monkeypatch.setattr(gateway, "_wire", gateway_called)
    monkeypatch.setattr(gateway, "_client", gateway_called)
    return tmp_path


def turn_on(jarvis_key="jarvis-key-1234"):
    if jarvis_key:
        direct.set_secret("jarvis", jarvis_key)
    store.save("settings", {"global": {"enabled": True, "capture_messages": True, "log_char_limit": 6000, "direct_mode": True}})


def enable(route):
    store.save("routes", {route: {**gateway.defaults()[route], "enabled": True}})


def ok(text="hello"):
    return {"model": "CLAUDE_SONNET_5_5", "choices": [{"message": {"role": "assistant", "content": text}}], "usage": {"prompt_tokens": 3, "completion_tokens": 2}}


def test_configured_follows_the_direct_providers_in_direct_mode():
    assert gateway.configured() is True                     # the gateway key
    store.save("settings", {"global": {"direct_mode": True}})
    assert gateway.configured() is False                    # no direct provider has a key: nothing to call
    direct.set_secret("jarvis", "jarvis-key-1234")
    assert gateway.configured() is True


def test_chat_goes_straight_to_the_provider_with_the_model_the_route_names(monkeypatch):
    turn_on()
    seen = {}
    def post(url, headers, body, timeout):
        seen.update(url=url, auth=headers.get("Authorization"), model=body["model"])
        return httpx.Response(200, json=ok("answer"), request=httpx.Request("POST", url))
    monkeypatch.setattr(direct, "_post", post)
    route = gateway.defaults()["creative_motion"]
    response, record = gateway.complete("creative_motion", [{"role": "user", "content": "hi"}])
    assert response["choices"][0]["message"]["content"] == "answer"
    assert seen["url"] == "https://api.jarvis.you/v1/chat/completions" and seen["auth"] == "Bearer jarvis-key-1234"
    assert seen["model"] == route["models"][0].split("#")[0].replace("custom:", "")          # the route decides the model, not the code
    assert record["routed_via"] == "direct:jarvis"


def test_an_image_goes_to_the_providers_images_endpoint(monkeypatch):
    turn_on(); enable("photorealistic_image")
    seen = {}
    def post(url, headers, body, timeout):
        seen.update(url=url, body=body)
        return httpx.Response(200, json={"data": [{"b64_json": "QUJD"}]}, request=httpx.Request("POST", url))
    monkeypatch.setattr(direct, "_post", post)
    response, record = gateway.complete("photorealistic_image", "a blue circle", endpoint="image", extra={"n": 1, "size": "1024x1024"})
    assert response["data"][0]["b64_json"] == "QUJD"
    assert seen["url"] == "https://api.jarvis.you/v1/images/generations"
    assert seen["body"]["prompt"] == "a blue circle" and seen["body"]["model"] == gateway.defaults()["photorealistic_image"]["models"][0].split("#")[0].replace("custom:", "")


def test_speech_returns_audio_from_the_provider(monkeypatch):
    turn_on(); enable("narration")
    seen = {}
    def post(url, headers, body, timeout):
        seen.update(url=url)
        return httpx.Response(200, content=b"\x00" * 4000, headers={"content-type": "audio/mpeg"}, request=httpx.Request("POST", url))
    monkeypatch.setattr(direct, "_post", post)
    monkeypatch.setattr("brain.speech_policy.gateway_choice", lambda cfg, catalog, text, voice, context, language: ("TTS_ELEVEN_V3", {"input": text, "voice": "v"}))
    assert len(gateway.speech("narration", "سلام", "v")) == 4000
    assert seen["url"] == "https://api.jarvis.you/v1/audio/speech"


def test_streaming_comes_from_the_providers(monkeypatch):
    turn_on()
    def stream_call(provider, messages, **kwargs):
        yield "a"; yield "b"
    monkeypatch.setattr(direct, "stream_call", stream_call)
    monkeypatch.setattr(gateway, "_lm_stream", lambda *a, **k: (_ for _ in ()).throw(AssertionError("the gateway stream must not run")))
    assert "".join(gateway.stream_chat("general_chat", [{"role": "user", "content": "x"}])) == "ab"


def test_gateway_only_features_say_so(monkeypatch):
    turn_on()
    for call in (lambda: gateway.sync_models(), lambda: gateway.search("anything"), lambda: gateway.transcription("x.wav", "fa")):
        with pytest.raises(gateway.GatewayError, match="[Dd]irect mode"):
            call()


def test_no_provider_answering_is_a_clear_error(monkeypatch):
    turn_on()
    monkeypatch.setattr(direct, "_post", lambda *a, **k: httpx.Response(500, text="boom", request=httpx.Request("POST", "https://x")))
    with pytest.raises(gateway.GatewayError, match="Direct mode"):
        gateway.complete("creative_motion", [{"role": "user", "content": "hi"}])


def test_the_setting_cannot_be_turned_on_without_a_direct_provider_key():
    base = {"enabled": True, "capture_messages": True, "log_char_limit": 6000}
    with pytest.raises(HTTPException) as caught:
        lm_admin.put_settings(lm_admin.SettingsUpdate(**base, direct_mode=True))
    assert caught.value.status_code == 409
    direct.set_secret("jarvis", "jarvis-key-1234")
    result = lm_admin.put_settings(lm_admin.SettingsUpdate(**base, direct_mode=True))
    assert result["direct_mode"] is True and result["direct_ready"] is True
    assert lm_admin.put_settings(lm_admin.SettingsUpdate(**base, direct_mode=False))["direct_mode"] is False
