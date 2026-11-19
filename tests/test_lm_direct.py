"""Direct provider fallbacks: policy, secrecy, wire formats and the gateway hook."""
import json
import os
import stat

import httpx
import pytest

from brain import lm_direct as direct
from brain import lm_gateway as gateway
from brain.lm_gateway import GatewayError


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    direct._REJECTED.clear()
    monkeypatch.setattr(direct.settings, "JOBS_DIR", str(tmp_path))
    for name in list(os.environ):
        if name.startswith("DIRECT_"):
            monkeypatch.delenv(name)
    for legacy in ("OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setattr(direct.settings, legacy, "")
    return tmp_path


def ok(text="hi"):
    return {"model": "m", "choices": [{"message": {"role": "assistant", "content": text}}], "usage": {"prompt_tokens": 3, "completion_tokens": 2}}


def test_base_url_policy():
    assert direct.validate_base_url("https://api.jarvis.you/v1/") == "https://api.jarvis.you/v1"
    for bad in ("http://api.jarvis.you/v1", "https://user:pw@x.com/v1", "https://x.com/v1?key=1", "https://localhost/v1", "https://127.0.0.1/v1", "https://10.0.0.5/v1", "ftp://x.com"):
        with pytest.raises(ValueError):
            direct.validate_base_url(bad)


def test_keys_are_write_only_and_stored_privately(isolated):
    direct.set_secret("jarvis", "sk-live-1234567890abcd")
    path = isolated / "ai_gateway" / "direct_keys.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    status = direct.status()
    jarvis = next(p for p in status["providers"] if p["id"] == "jarvis")
    assert jarvis["configured"] and jarvis["key_hint"] == "…abcd" and jarvis["key_source"] == "saved"
    assert "sk-live-1234567890abcd" not in json.dumps(status)           # never returned
    direct.set_secret("jarvis", "")                                      # empty deletes
    assert not next(p for p in direct.status()["providers"] if p["id"] == "jarvis")["configured"]
    with pytest.raises(ValueError):
        direct.set_secret("nope", "x")
    with pytest.raises(ValueError):
        direct.set_secret("jarvis", "line\nbreak")


def test_legacy_env_keys_are_reused_so_nothing_is_entered_twice(monkeypatch):
    monkeypatch.setattr(direct.settings, "OPENAI_API_KEY", "openai-legacy-key-9999")
    openai = next(p for p in direct.status()["providers"] if p["id"] == "openai")
    assert openai["configured"] and openai["key_source"] == "environment"


def test_config_defaults_order_and_validation():
    cfg = direct.config()
    assert cfg["enabled"] is True and [p["id"] for p in cfg["providers"]] == ["jarvis", "sarovi", "arvan", "openai", "gemini", "anthropic", "elevenlabs"]
    saved = direct.save_config(False, [{"id": "gemini", "enabled": True, "base_url": "https://relay.example.vercel.app/v1beta", "model": "gemini-3.5-flash", "format": "gemini"},
                                       {"id": "jarvis", "enabled": False, "base_url": "https://api.jarvis.you/v1", "model": "X"}])
    assert saved["enabled"] is False and [p["id"] for p in saved["providers"]][:2] == ["gemini", "jarvis"]   # order kept, rest appended
    with pytest.raises(ValueError):
        direct.save_config(True, [{"id": "evil", "base_url": "https://x.com"}])
    with pytest.raises(ValueError):
        direct.save_config(True, [{"id": "jarvis", "base_url": "http://insecure.example"}])


def test_auth_schemes_and_paths(monkeypatch):
    seen = []

    def fake_post(url, headers, body, timeout):
        seen.append((url, headers, body))
        return httpx.Response(200, json=ok())

    monkeypatch.setattr(direct, "_post", fake_post)
    direct.set_secret("arvan", "arvan-key-0000"); direct.set_secret("jarvis", "jarvis-key-0000")
    cfg = {p["id"]: p for p in direct.config()["providers"]}
    direct.call(cfg["arvan"], [{"role": "user", "content": "x"}], model="GPT-5.6-Sol", tokens=50)
    direct.call(cfg["jarvis"], [{"role": "user", "content": "x"}], model="CLAUDE_SONNET_5_5", tokens=50)
    assert seen[0][0] == "https://aiapi.rafiei.co/v1/chat/completions" and seen[0][1]["Authorization"] == "apikey arvan-key-0000"
    assert seen[1][1]["Authorization"] == "Bearer jarvis-key-0000" and seen[1][2]["model"] == "CLAUDE_SONNET_5_5"


def test_gemini_native_format_round_trip(monkeypatch):
    captured = {}

    def fake_post(url, headers, body, timeout):
        captured.update(url=url, headers=headers, body=body)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "سلام"}]}}], "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 2}})

    monkeypatch.setattr(direct, "_post", fake_post)
    direct.save_config(True, [{"id": "gemini", "base_url": "https://relay.example.vercel.app/v1beta", "model": "gemini-3.5-flash", "format": "gemini", "extra_header_name": "x-relay-secret"}])
    direct.set_secret("gemini", "g-key-12345678"); direct.set_secret("gemini:header", "relay-secret")
    provider = next(p for p in direct.config()["providers"] if p["id"] == "gemini")
    data = direct.call(provider, [{"role": "system", "content": "be brief"}, {"role": "user", "content": "hi"}], model="gemini-3.5-flash", tokens=100, temperature=0.3)
    assert captured["url"] == "https://relay.example.vercel.app/v1beta/models/gemini-3.5-flash:generateContent"
    assert captured["headers"]["x-goog-api-key"] == "g-key-12345678" and captured["headers"]["x-relay-secret"] == "relay-secret"
    assert captured["body"]["systemInstruction"]["parts"][0]["text"] == "be brief" and captured["body"]["contents"][0]["role"] == "user"
    assert data["choices"][0]["message"]["content"] == "سلام" and data["usage"]["prompt_tokens"] == 5


def test_model_selection_prefers_the_routes_own_model_for_that_provider():
    cfg = {p["id"]: p for p in direct.config()["providers"]}
    candidates = ["google:gemini-3.5-flash", "custom:DeepSeek-V4-Flash#arvancloud-all-models", "custom:CLAUDE_OPUS_5_5#jarvis-all-models"]
    assert direct.model_for(cfg["jarvis"], candidates) == "CLAUDE_OPUS_5_5"
    assert direct.model_for(cfg["arvan"], candidates) == "DeepSeek-V4-Flash"
    assert direct.model_for(cfg["gemini"], candidates) == "google/gemini-3.5-flash"      # Vercel gateway naming
    assert direct.model_for(cfg["openai"], candidates) == "gpt-4.1-mini"                  # provider default


def test_fallback_walks_providers_in_order_and_skips_failures(monkeypatch):
    calls = []

    def fake_post(url, headers, body, timeout):
        calls.append(url)
        if "jarvis" in url:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, json=ok("from sarovi"))

    monkeypatch.setattr(direct, "_post", fake_post)
    direct.set_secret("sarovi", "s-key-00000000"); direct.set_secret("jarvis", "j-key-00000000")
    attempts = []
    found = direct.try_fallback([{"role": "user", "content": "x"}], candidates=[], tokens=100, temperature=None, timeout=30, extra=None, attempts=attempts)
    assert found and found[1] == "sarovi" and len(calls) == 2          # Jarvis is asked first, then Sarovi
    assert [a["http_status"] for a in attempts] == [503, 200] and attempts[0]["model"].startswith("direct:jarvis")


def test_gemini_models_ask_google_first(monkeypatch):
    calls = []
    monkeypatch.setattr(direct, "_post", lambda url, headers, body, timeout: (calls.append(url), httpx.Response(200, json=ok("g")))[1])
    for name in ("jarvis", "gemini"):
        direct.set_secret(name, name + "-key-0000000")
    found = direct.try_fallback([{"role": "user", "content": "x"}], candidates=["google:gemini-3.5-flash"], tokens=10, temperature=None, timeout=30, extra=None, attempts=[])
    assert found[1] == "gemini" and "ai-gateway" in calls[0]
    calls.clear()
    found = direct.try_fallback([{"role": "user", "content": "x"}], candidates=["custom:CLAUDE_OPUS_5_5#jarvis-all-models"], tokens=10, temperature=None, timeout=30, extra=None, attempts=[])
    assert found[1] == "jarvis"


def test_master_switch_and_missing_keys_disable_fallback(monkeypatch):
    monkeypatch.setattr(direct, "_post", lambda *a, **k: pytest.fail("must not be called"))
    assert direct.try_fallback([], candidates=[], tokens=1, temperature=None, timeout=1, extra=None, attempts=[]) is None   # no keys
    direct.set_secret("jarvis", "j-key-00000000")
    direct.save_config(False, [{"id": "jarvis", "base_url": "https://api.jarvis.you/v1", "model": "X"}])
    assert direct.try_fallback([], candidates=[], tokens=1, temperature=None, timeout=1, extra=None, attempts=[]) is None   # master off


def test_error_text_never_contains_the_key(monkeypatch):
    monkeypatch.setattr(direct, "_post", lambda *a, **k: httpx.Response(401, text="invalid key j-key-00000000 for account"))
    direct.set_secret("jarvis", "j-key-00000000")
    with pytest.raises(direct.DirectError) as err:
        direct.call(next(p for p in direct.config()["providers"] if p["id"] == "jarvis"), [], model="m", tokens=1)
    assert "j-key-00000000" not in str(err.value) and "[REDACTED]" in str(err.value)


def test_gateway_uses_direct_fallback_only_after_lm_api_fails(monkeypatch):
    """complete(): LM API 503 → direct provider answers, and the audit record says so."""
    cfg = {"enabled": True, "endpoint": "chat", "models": ["custom:CLAUDE_SONNET_5_5#jarvis-all-models"], "automatic_fallback": True,
           "max_retries": 0, "timeout": 30, "temperature": None, "max_tokens": 1000, "streaming": False}
    monkeypatch.setattr(gateway, "defaults", lambda: {"editing_agent": cfg})
    monkeypatch.setattr(gateway, "gateway_settings", lambda: {"enabled": True, "capture_messages": False, "log_char_limit": 100})
    real_records = gateway.store.records
    models = {"custom:CLAUDE_SONNET_5_5#jarvis-all-models": {"enabled": True, "available": True, "verified": ["chat"], "declared": []}}
    monkeypatch.setattr(gateway.store, "records", lambda table: models if table == "models" else real_records(table))
    audits = []
    monkeypatch.setattr(gateway, "_audit", audits.append)

    def lm_down(*args, **kwargs):
        raise GatewayError("LM API HTTP 503: exhausted", 503, True)

    monkeypatch.setattr(gateway, "_wire", lm_down)
    monkeypatch.setattr(gateway.time, "sleep", lambda s: None)
    monkeypatch.setattr(direct, "_post", lambda *a, **k: httpx.Response(200, json=ok("direct answer")))
    direct.set_secret("jarvis", "j-key-00000000")
    response, record = gateway.complete("editing_agent", [{"role": "user", "content": "hi"}])
    assert response["choices"][0]["message"]["content"] == "direct answer"
    assert record["routed_via"] == "direct:jarvis" and record["provider"] == "jarvis" and record["actual_model"] == "CLAUDE_SONNET_5_5"
    assert record["status"] == "success" and audits and any(a["model"].startswith("direct:") for a in record["fallback_history"])

    # master switch off → the original LM API error is raised, nothing is sent to providers
    direct.save_config(False, [{"id": "jarvis", "base_url": "https://api.jarvis.you/v1", "model": "X"}])
    with pytest.raises(GatewayError):
        gateway.complete("editing_agent", [{"role": "user", "content": "hi"}])


def test_structured_callers_use_direct_providers_but_only_valid_answers_count(monkeypatch):
    import json
    from brain import lm_gateway as gateway
    calls = []

    def fake_post(url, headers, body, timeout):
        calls.append(url)
        # The first provider answers with prose, the second with real JSON.
        return httpx.Response(200, json=ok("sorry, no json" if "jarvis" in url else '{"a": 1}'))

    monkeypatch.setattr(direct, "_post", fake_post)
    direct.set_secret("jarvis", "j-key-00000000"); direct.set_secret("sarovi", "s-key-00000000")
    attempts = []
    found = direct.try_fallback([{"role": "user", "content": "x"}], candidates=[], tokens=50, temperature=None, timeout=30, extra=None, attempts=attempts, validate=json.loads)
    assert found and found[1] == "sarovi" and len(calls) == 2
    assert [a.get("error") for a in attempts] == ["invalid structured output", None]


def _stream_route(monkeypatch, *, streaming, models):
    cfg = {"enabled": True, "endpoint": "chat", "models": models, "automatic_fallback": True, "max_retries": 0, "timeout": 30,
           "temperature": None, "max_tokens": 1000, "streaming": streaming}
    monkeypatch.setattr(gateway, "defaults", lambda: {"conversation_response": cfg})
    monkeypatch.setattr(gateway, "gateway_settings", lambda: {"enabled": True, "capture_messages": False, "log_char_limit": 100})
    monkeypatch.setattr(gateway, "_audit", lambda record: None)


def _sse(*pieces):
    lines = [f'data: {json.dumps({"choices": [{"delta": {"content": p}}]})}' for p in pieces]
    lines.append('data: {"choices":[{"delta":{},"finish_reason":"stop"}]}')
    lines.append("data: [DONE]")
    return "\n".join(lines) + "\n"


class _FakeStream:
    def __init__(self, status, body):
        self.status_code, self.is_success, self._body = status, 200 <= status < 300, body
        self.text = body

    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return None
    def iter_lines(self): return iter(self._body.splitlines())


def test_the_first_reply_streams_for_real_from_direct_providers_when_the_route_cannot_stream(monkeypatch):
    _stream_route(monkeypatch, streaming=False, models=["custom:CLAUDE_SONNET_5_5#jarvis-all-models"])
    seen = []

    class Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False

        def stream(self, method, url, headers=None, json=None):
            seen.append((url, json.get("stream")))
            return _FakeStream(200, _sse("سلام", " دنیا"))

    monkeypatch.setattr(direct.httpx, "Client", Client)
    direct.set_secret("jarvis", "j-key-00000000")
    pieces = list(gateway.stream_chat("conversation_response", [{"role": "user", "content": "x"}], tokens=50, timeout_seconds=10))
    assert pieces == ["سلام", " دنیا"] and seen == [("https://api.jarvis.you/v1/chat/completions", True)]


def test_a_failed_provider_is_skipped_before_any_text_but_never_mixed_into_an_answer(monkeypatch):
    _stream_route(monkeypatch, streaming=False, models=["x"])
    answers = {"jarvis": _FakeStream(503, "busy"), "sarovi": _FakeStream(200, _sse("از", " ساروی"))}

    class Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def stream(self, method, url, headers=None, json=None):
            return answers["jarvis" if "jarvis" in url else "sarovi"]

    monkeypatch.setattr(direct.httpx, "Client", Client)
    direct.set_secret("jarvis", "j-key-00000000"); direct.set_secret("sarovi", "s-key-00000000")
    assert "".join(gateway.stream_chat("conversation_response", [{"role": "user", "content": "x"}])) == "از ساروی"


def test_without_any_direct_provider_the_original_reason_is_reported(monkeypatch):
    _stream_route(monkeypatch, streaming=False, models=["x"])
    with pytest.raises(GatewayError, match="Streaming disabled"):
        list(gateway.stream_chat("conversation_response", [{"role": "user", "content": "x"}]))


def test_a_provider_that_rejected_its_key_is_left_alone_for_a_while(monkeypatch):
    calls = []

    def post(url, headers, body, timeout):
        calls.append(url)
        return httpx.Response(401, text="bad key") if "jarvis" in url else httpx.Response(200, json=ok("fine"))

    monkeypatch.setattr(direct, "_post", post)
    direct.set_secret("jarvis", "j-key-00000000"); direct.set_secret("sarovi", "s-key-00000000")
    args = dict(candidates=[], tokens=10, temperature=None, timeout=5, extra=None)
    assert direct.try_fallback([{"role": "user", "content": "x"}], attempts=[], **args)[1] == "sarovi"
    calls.clear()
    assert direct.try_fallback([{"role": "user", "content": "x"}], attempts=[], **args)[1] == "sarovi"
    assert all("jarvis" not in c for c in calls)


def test_a_slow_first_attempt_is_overtaken_by_the_next_one_without_mixing_answers(monkeypatch):
    import time as _time
    direct.set_secret("jarvis", "j-key-00000000"); direct.set_secret("sarovi", "s-key-00000000")

    def fake_stream(provider, messages, *, model, tokens, temperature=None, timeout=60):
        if provider["id"] == "jarvis":
            _time.sleep(0.6)                      # a model that is slow to its first token
            yield "از جارویس"
        else:
            yield "از"; yield " ساروی"

    monkeypatch.setattr(direct, "stream_call", fake_stream)
    out = "".join(direct.stream_fallback([{"role": "user", "content": "x"}], candidates=[], tokens=50, hedge_after=0.15))
    assert out == "از ساروی"                    # the faster attempt won, and nothing from the slow one was added


def test_every_attempt_failing_raises_the_last_reason(monkeypatch):
    direct.set_secret("jarvis", "j-key-00000000")

    def broken(provider, messages, **kw):
        raise direct.DirectError("HTTP 503: busy", 503)
        yield

    monkeypatch.setattr(direct, "stream_call", broken)
    with pytest.raises(direct.DirectError, match="503"):
        list(direct.stream_fallback([{"role": "user", "content": "x"}], candidates=[], tokens=50, hedge_after=0.05))


def test_route_models_are_attempted_in_the_routes_own_order(monkeypatch):
    direct.set_secret("arvan", "a-key-00000000"); direct.set_secret("sarovi", "s-key-00000000")
    pairs = direct._stream_attempts(["custom:DeepSeek-V4-Flash#arvancloud-all-models", "custom:GLM-5.3-Flash#arvancloud-all-models"])
    assert [(p["id"], m) for p, m in pairs][:2] == [("arvan", "DeepSeek-V4-Flash"), ("arvan", "GLM-5.3-Flash")]
    assert ("sarovi", direct.PROVIDERS["sarovi"]["model"]) in [(p["id"], m) for p, m in pairs]        # then each provider's default
def test_google_relay_uses_relay_auth_and_exact_endpoint(monkeypatch):
    from brain import lm_direct as direct
    monkeypatch.setattr(direct, 'key_for', lambda _: 'not-the-google-key')
    monkeypatch.setattr(direct.settings, 'GEMINI_RELAY_SECRET', 'test-relay-secret')
    p={'id':'gemini','format':'gemini','base_url':'https://rafiei-telegram-api-relay.vercel.app/api/gemini'}
    _,url,headers,body=direct._prepare(p,[{'role':'user','content':'hello'}],model='gemini-3.5-flash',tokens=20,temperature=None,extra=None,stream=False)
    assert url==p['base_url']
    assert headers['x-relay-secret']=='test-relay-secret'
    assert headers['x-gemini-model']=='gemini-3.5-flash'
    assert 'x-goog-api-key' not in headers and 'Authorization' not in headers
    assert body['contents']



def test_structured_callers_get_json_mode_from_openai_direct(monkeypatch):
    from brain import lm_direct as d
    seen = {}
    provider = {"id": "openai", "format": "openai", "model": "gpt-x", "enabled": True, "base_url": "https://api.openai.com/v1"}
    monkeypatch.setattr(d, "usable", lambda google_first=False: [provider])
    monkeypatch.setattr(d, "model_for", lambda p, c: "gpt-x")
    def fake_call(p, messages, *, model, tokens, temperature, timeout, extra):
        seen["extra"] = extra
        return {"choices": [{"message": {"content": "{\"ok\": true}"}}]}
    monkeypatch.setattr(d, "call", fake_call)
    out = d.try_fallback([{"role": "user", "content": "json please"}], candidates=[], tokens=50, temperature=0, timeout=30, extra=None, attempts=[], validate=lambda text: __import__("json").loads(text))
    assert out and seen["extra"] == {"response_format": {"type": "json_object"}}
    d.try_fallback([{"role": "user", "content": "plain"}], candidates=[], tokens=50, temperature=0, timeout=30, extra=None, attempts=[], validate=None)
    assert seen["extra"] is None


def test_openai_reasoning_models_get_their_own_parameters(monkeypatch):
    from brain import lm_direct as d
    provider = {"id": "openai", "format": "openai", "base_url": "https://api.openai.com/v1", "model": "gpt-5.4", "enabled": True}
    monkeypatch.setattr(d, "key_for", lambda provider_id: "sk-test-not-real")
    for model, reasoning in (("gpt-5.4", True), ("o3", True), ("gpt-4.1", False)):
        _, _, _, body = d._prepare(provider, [{"role": "user", "content": "hi"}], model=model, tokens=800, temperature=0.3, extra=None, stream=False)
        assert ("max_completion_tokens" in body) is reasoning and ("max_tokens" in body) is not reasoning
        assert ("temperature" in body) is not reasoning
        assert body.get("reasoning_effort") == ("low" if reasoning else None)
