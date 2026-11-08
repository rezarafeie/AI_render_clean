"""Central, bounded Rafiei LM gateway used by the existing editor adapters."""
from __future__ import annotations
import contextvars
import functools
import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, unquote
import httpx
from app.config import settings
from app import lm_store as store
from . import lm_adapters as adapters

log = logging.getLogger(__name__)
user_context = contextvars.ContextVar("ai_user", default=None)
job_context = contextvars.ContextVar("ai_job", default=None)
route_context = contextvars.ContextVar("ai_route", default=None)
conversation_context = contextvars.ContextVar("ai_conversation", default=None)
_slots = threading.BoundedSemaphore(4)
ROUTES = {
    "general_chat": ("General Chat", "chat"), "editing_agent": ("Video Editing Agent", "chat"),
    "video_understanding": ("Video Understanding", "vision"), "transcription": ("Transcription", "transcription"),
    "subtitles": ("Subtitle Processing", "chat"), "script": ("Script Generation", "chat"),
    "image": ("Image Generation", "image"), "audio": ("Audio Generation", "speech"),
    "video": ("Video Generation", "video"), "embeddings": ("Embeddings", "embeddings"),
}


class GatewayError(RuntimeError):
    def __init__(self, message, status=502, retryable=False):
        super().__init__(message); self.status = status; self.retryable = retryable


def secret():
    if settings.LMAPI_API_KEY: return settings.LMAPI_API_KEY.strip()
    path = Path(settings.LMAPI_API_KEY_FILE)
    if not path.is_absolute(): path = Path(__file__).parents[1] / path
    return path.read_text().strip() if path.is_file() else ""


def configured():
    return bool(secret())


def safe(value, limit=6000):
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    for key in (secret(), settings.ELEVENLABS_API_KEY):
        if key: text = text.replace(key, "[REDACTED]")
    text = re.sub(r'data:[^;\s]+;base64,[A-Za-z0-9+/=]+', '[media omitted]', text)
    text = re.sub(r'("b64_json"\s*:\s*")[^"]*', r'\1[media omitted]', text)
    text = re.sub(r'(?i)(bearer\s+|(?:api[_-]?key|token|secret)[=:]\s*)[^\s"&]+', r'\1[REDACTED]', text)
    text = re.sub(r'\b(?:sk-|freellmapi-)[A-Za-z0-9_.-]+', '[REDACTED]', text)
    return text[:limit]


def gateway_settings():
    value = store.records("settings").get("global", {})
    return {"enabled": True, "capture_messages": True, "log_char_limit": 6000, **value}


def _client(timeout):
    from .http_ssl import ssl_context
    return httpx.Client(timeout=httpx.Timeout(timeout, connect=min(timeout, 10)), verify=ssl_context(), follow_redirects=False)


def _url(path):
    base = settings.LMAPI_BASE_URL.rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "https" or parsed.hostname != "lmapi.rafiei.co" or parsed.username or parsed.query:
        raise GatewayError("LM API must use the approved HTTPS host", 422)
    return base + "/" + path


def headers():
    key = secret()
    if not key: raise GatewayError("LM API is not configured", 503)
    return {"Authorization": "Bearer " + key, "Content-Type": "application/json", "X-FreeLLM-Cache": "off"}


def defaults():
    existing = store.records("routes")
    new = {}
    for key, (title, capability) in ROUTES.items():
        if key not in existing:
            specialized = capability in {"image", "speech", "transcription", "video"}
            new[key] = {"id": key, "title": title, "capability": capability, "enabled": not specialized,
                "models": ["auto"], "endpoint": "embeddings" if key == "embeddings" else "chat",
                "timeout": 120, "max_retries": 1, "temperature": None, "max_tokens": 16000,
                "streaming": False, "automatic_fallback": True, "specialized_fallback": specialized}
    from .lm_tasks import TASKS, prioritize
    pending = [key for key in TASKS if key not in existing and key not in new]
    if pending:
        register_task_models()          # preferred models must exist in the catalog before a route can list them
    catalog = store.records("models") if pending else {}
    for key, spec in TASKS.items():
        if key not in existing and key not in new:
            parent = {**existing, **new}[spec["parent"]]
            # Operator priority (Jarvis, Sarovi, Arvan; Google first for Gemini) ahead of whatever the parent route uses.
            # A preferred model that has not passed its capability test is skipped at execution time, so this is safe.
            preferred = prioritize([p["id"] for p in spec["preferences"] if p["id"] in catalog])
            models = (preferred + [m for m in parent["models"] if m not in preferred])[:8]
            new[key] = {**parent, "id":key, "title":spec["title"], "capability":spec["capability"],
                        "models":models, "task_id":key}
    if new: store.save("routes", new)
    return {**existing, **new}


def sync_models():
    with _client(30) as client:
        response = client.get(_url("models"), headers=headers()); response.raise_for_status()
        catalog = response.json()
        spec_response = client.get(_url("openapi.json"), headers=headers())
        paths = list(spec_response.json().get("paths", {})) if spec_response.is_success else []
    rows = catalog.get("data")
    if not isinstance(rows, list) or len(rows) > 20000: raise GatewayError("Invalid model catalog")
    previous = store.records("models"); updated = {}
    for item in rows:
        mid = item.get("id")
        if not isinstance(mid, str) or not mid or len(mid) > 512: continue
        old = previous.get(mid, {})
        # Only explicit catalog metadata is evidence; IDs/names never imply capability.
        declared = []
        metadata_caps = item.get("capabilities", {})
        if isinstance(metadata_caps, dict): declared = [k for k,v in metadata_caps.items() if v is True]
        elif isinstance(metadata_caps, list): declared = [v for v in metadata_caps if isinstance(v, str)]
        parameters = item.get("supported_parameters") or []
        for parameter, capability in (("reasoning_effort","reasoning"),("tools","tools"),("response_format","structured"),("stream","streaming")):
            if parameter in parameters and capability not in declared: declared.append(capability)
        updated[mid] = {**old, "id": mid, "name": item.get("name") or item.get("display_name") or mid,
            "provider": item.get("owned_by") or item.get("provider") or None,
            "available": item.get("available", True), "enabled": old.get("enabled", True),
            "declared": declared, "verified": old.get("verified", []),
            "status": old.get("status", "Untested"), "metadata": item, "synced_at": datetime.now(timezone.utc).isoformat()}
    for mid, old in previous.items():
        if mid not in updated:
            # Scoped execution IDs come from registered endpoint models, not the
            # normalized public catalog. A sync must not discard their probe evidence.
            updated[mid] = old if old.get("scope_registered") else {**old, "available": False}
    store.save("models", updated)
    store.save("settings", {"discovery": {"paths": paths, "synced_at": datetime.now(timezone.utc).isoformat(), "models": len(rows)}})
    defaults()
    return {"models": len(rows), "paths": paths}


def capabilities(model):
    if model.get("scope_registered"): return set(model.get("verified", []))
    return set(model.get("verified", [])) | set(model.get("declared", []))


def register_task_models():
    """Register observed execution pairs as Untested; never infer capability."""
    from .lm_tasks import TASKS
    previous=store.records("models"); rows={}
    for task in TASKS.values():
        for pair in task["preferences"]:
            mid=pair["id"]
            if mid not in previous:
                rows[mid]={"id":mid,"name":pair["model_id"],"provider":pair["provider"],
                    "enabled":True,"available":True,"verified":[],"declared":[],"status":"Untested",
                    "scope_registered":True,"metadata":{"registration_source":"authenticated Gateway Keys UI"}}
    if rows: store.save("models",rows)
    return {"registered":len(rows)}


def model_allowed(mid):
    # User explicitly disabled this provider. Also guard saved legacy selections.
    return not (mid.endswith("#vercel-all-models") or mid.startswith("vercel:"))


def _wire(endpoint, data, timeout):
    try:
        with _client(timeout) as client:
            request_headers = headers()
            if endpoint in {'image','speech','video'}:
                from .media_policy import response_timeout,request_headers as media_headers,require_gateway_safety
                timeout=response_timeout(endpoint,timeout,data)
                client.timeout=httpx.Timeout(timeout,connect=min(timeout,10))
                request_headers.update(media_headers(endpoint,timeout))
                require_gateway_safety(client,_url('editor-media-policy'),headers())
            if endpoint == "messages": request_headers["anthropic-version"] = "2023-06-01"
            response = client.post(_url(adapters.PATHS[endpoint]), headers=request_headers, json=data)
            if not response.is_success:
                raise GatewayError(f"LM API HTTP {response.status_code}: {safe(response.text, 350)}",
                    response.status_code, response.status_code in {408, 429, 500, 502, 503, 504})
            return response.json(), dict(response.headers), response.status_code
    except httpx.TransportError as exc:
        raise GatewayError(f"LM API {type(exc).__name__}", 504, True) from exc


def _audit(record):
    try: store.log(record)
    except Exception: log.exception("AI audit persistence failed request=%s", record["id"])


def _wire_chat_stream(endpoint, data, timeout):
    """Collect real SSE for structured callers; validation stays in complete()."""
    if endpoint != "chat": raise GatewayError("Structured streaming requires chat", 422)
    chunks = []; result = {}; completed = False
    started = time.monotonic()
    try:
        with _client(timeout) as client:
            with client.stream("POST", _url("chat/completions"), headers=headers(),
                               json={**data, "stream": True}) as response:
                hdr = dict(response.headers)
                if not response.is_success:
                    raise GatewayError(f"LM stream HTTP {response.status_code}", response.status_code,
                                       response.status_code in {408, 429, 500, 502, 503, 504})
                for line in response.iter_lines():
                    if time.monotonic() - started > timeout: raise GatewayError("Stream deadline exceeded", 504, True)
                    if not line.startswith("data:"): continue
                    value = line[5:].strip()
                    if value == "[DONE]": completed = True; break
                    try: chunk = json.loads(value)
                    except ValueError: raise GatewayError("Invalid SSE document", 502, True) from None
                    if chunk.get("error"): raise GatewayError("LM stream reported an error", 502, True)
                    if chunk.get("model"): result["model"] = chunk["model"]
                    if chunk.get("usage"): result["usage"] = chunk["usage"]
                    choices = chunk.get("choices") or []
                    if choices:
                        choice = choices[0]
                        if choice.get("finish_reason"): completed = True; result["finish_reason"] = choice["finish_reason"]
                        delta = choice.get("delta", {}).get("content")
                        if isinstance(delta, str): chunks.append(delta)
                if not completed: raise GatewayError("LM stream ended before completion", 502, True)
                result["choices"] = [{"message": {"role": "assistant", "content": "".join(chunks)},
                                      "finish_reason": result.get("finish_reason")}]
                return result, hdr, response.status_code
    except httpx.TransportError as exc:
        raise GatewayError(f"LM API {type(exc).__name__}", 504, True) from exc


def _record(route, endpoint, requested, started, attempts, response=None, hdr=None, error=None, request=None):
    cfg = gateway_settings(); response = response or {}; hdr = hdr or {}
    usage = adapters.usage(response)
    routed = unquote(hdr.get("x-routed-via", ""))
    actual = response.get("model")
    if not actual or actual in {"auto","fusion"} or str(actual).startswith("auto:"):
        actual = routed.partition("/")[2] or None
    media=[]
    if endpoint=='image' and not error:
        try:
            from .media_archive import images
            media=images(response)
        except Exception: log.exception('Could not archive media response')
    return {"id": str(uuid.uuid4()), "media":media, "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user_context.get(), "job_id": job_context.get(), "route": route,
        "conversation_id": conversation_context.get(), "task_id":route,
        "endpoint": adapters.PATHS[endpoint], "requested_model": requested, "actual_model": actual,
        "provider": unquote(hdr.get("x-provider", "")) or routed.partition("/")[0] or None,
        "routed_via": routed or None,
        "status": "failed" if error else "success", "latency_ms": round((time.monotonic()-started)*1000),
        **usage, "http_status": attempts[-1].get("http_status") if attempts else None,
        "retry_count": len(attempts)-len({a["model"] for a in attempts}), "fallback_history": attempts,
        "fallback_count": max(0,len({a["model"] for a in attempts})-1),
        "gateway_fallback_attempts": hdr.get("x-fallback-attempts"),
        "gateway_fallback_history": safe(hdr.get("x-fallback-trail", ""), 1000) or None,
        "error": safe(str(error), 500) if error else None,
        "correlation_id": __import__("request_context").current_request_id(),
        "request_message": safe(request, cfg["log_char_limit"]) if cfg["capture_messages"] else None,
        "response_message": safe(response, cfg["log_char_limit"]) if cfg["capture_messages"] else None}


def _direct_fallback(route, endpoint, messages, cfg, candidates, tokens, extra, started, attempts, probe, validate=None):
    """LM API failed: answer from a directly configured provider (see brain/lm_direct.py). Chat only."""
    if probe or endpoint != "chat":
        return None
    from . import lm_direct
    try:
        found = lm_direct.try_fallback(messages, candidates=list(candidates), tokens=min(tokens or cfg["max_tokens"], cfg["max_tokens"]),
                                       temperature=cfg["temperature"], timeout=cfg["timeout"], extra=extra, attempts=attempts, validate=validate)
    except Exception:
        log.exception("direct fallback crashed")
        return None
    if not found:
        return None
    response, provider_id, model = found
    record = _record(route, endpoint, candidates[0] if candidates else "", started, attempts, response, {}, request=messages)
    record.update(provider=provider_id, routed_via=f"direct:{provider_id}", actual_model=model)
    _audit(record)
    return response, record


from app.studio_activity import observe_request


@observe_request
def complete(route, messages, *, required=None, tokens=None, extra=None, endpoint=None, model_override=None, probe=False, validate_response=None, stream=False):
    cfg = defaults().get(route)
    if not cfg or not gateway_settings()["enabled"] or (not cfg["enabled"] and not probe):
        raise GatewayError("This AI route is disabled", 503)
    endpoint = endpoint or cfg["endpoint"]
    required = set(required or {endpoint})
    if stream: required.add("streaming")
    if extra and extra.get("tools"): required.add("tools")
    if extra and extra.get("response_format"): required.add("structured")
    models = store.records("models")
    candidates = [model_override] if model_override else cfg["models"]
    is_media=endpoint in {'image','speech','video'}
    if is_media or not cfg["automatic_fallback"] or endpoint == "embeddings": candidates = candidates[:1]
    started = time.monotonic(); attempts = []; error = None; response = hdr = None
    # One bounded retry owner. The upstream gateway's own fallback is observed, never recursively replayed.
    if not _slots.acquire(timeout=2): raise GatewayError("AI request queue is busy", 429)
    try:
        for mid in candidates[:8]:
            if not model_allowed(mid): continue
            item = models.get(mid)
            if not item or not item.get("enabled") or not item.get("available", True): continue
            if not probe and not required.issubset(capabilities(item)): continue
            retries = 0 if is_media or probe or mid.startswith("auto") or mid == "fusion" else cfg["max_retries"]
            for attempt in range(retries+1):
                if time.monotonic()-started > min(300, cfg["timeout"]*2): break
                request_extra = dict(extra or {})
                if validate_response is not None and "structured" in capabilities(item):
                    request_extra.setdefault("response_format", {"type": "json_object"})
                body = adapters.payload(endpoint, mid, messages, tokens=min(tokens or cfg["max_tokens"], cfg["max_tokens"]),
                    temperature=cfg["temperature"], extra=request_extra)
                tick = time.monotonic()
                try:
                    remaining = min(300, cfg["timeout"]*2) - (time.monotonic()-started)
                    wire = _wire_chat_stream if stream else _wire
                    response, hdr, status = wire(endpoint, body, max(1, min(cfg["timeout"], remaining)))
                    if validate_response is not None:
                        try:
                            validate_response(adapters.text(endpoint, response))
                        except (ValueError, TypeError):
                            # HTTP 200 is not a usable editing plan. Skip this
                            # model once; never repeat the same invalid answer.
                            raise GatewayError('Model returned invalid structured output', 502, True) from None
                    if mid.startswith("google:"):
                        routed=unquote(hdr.get("x-routed-via", ""))
                        if routed != "google/" + mid.partition(":")[2]:
                            raise GatewayError("Google provider pin was not honored",502,True)
                    attempts.append({"model": mid, "http_status": status, "latency_ms": round((time.monotonic()-tick)*1000)})
                    record = _record(route, endpoint, candidates[0], started, attempts, response, hdr, request=body)
                    _audit(record)
                    return response, record
                except GatewayError as exc:
                    if is_media:
                        # An ambiguous media failure may already have been billed.
                        # Do not submit another image automatically after timeout/5xx.
                        exc.retryable = False
                    # A model the upstream catalog does not (or no longer) list is skipped, not fatal: the next candidate and the direct fallbacks still run.
                    if not is_media and exc.status == 404 and "model_not_found" in str(exc):
                        # Disabled Google model: skip, without quota preflight or retry.
                        exc.retryable = True
                    error = exc
                    attempts.append({"model": mid, "http_status": exc.status, "error": safe(str(exc), 300), "latency_ms": round((time.monotonic()-tick)*1000)})
                    if not exc.retryable: raise
                    if str(exc) == 'Model returned invalid structured output': break
                    if exc.status in {404,429}: break
                    # Long Retry-After/quota cooldowns are not slept inside editor workers.
                    if attempt < retries: time.sleep(min(2**attempt, 2))
            if error and not error.retryable: break
        # Structured (JSON) callers get the direct providers too, but only answers that pass their own validator count.
        direct = _direct_fallback(route, endpoint, messages, cfg, candidates, tokens, extra, started, attempts, probe, validate_response)
        if direct:
            return direct
        if error and str(error) == 'Model returned invalid structured output':
            error.retryable = False
        failed_direct = [a for a in attempts if str(a.get("model", "")).startswith("direct:") and a.get("http_status") != 200]
        if error and failed_direct:
            # Say what the direct fallback answered too: "LM API rate limited" alone hides that the backup key had no credit.
            last = failed_direct[-1]
            error = GatewayError(f"{error} | direct fallback {last['model']} also failed: {str(last.get('error', ''))[:160]}", error.status, error.retryable)
        raise error or GatewayError("No enabled, capability-verified model for this route; configure AI Models & Logs", 422)
    except Exception as exc:
        _audit(_record(route, endpoint, candidates[0] if candidates else "", started, attempts,
                       response=response, hdr=hdr, error=exc, request=messages))
        raise
    finally:
        _slots.release()


def stream_chat(route, messages, model_override=None, probe=False, *, tokens=None, timeout_seconds=None):
    """Stream a chat answer. LM API first (when the route has verified streaming); when that is off, or fails before the first token,
    the direct providers stream it for real (priority Jarvis, Sarovi, Arvan, ...; Google first for Gemini models)."""
    cfg = defaults()[route]
    if not cfg["enabled"] or not gateway_settings()["enabled"]: raise GatewayError("Route disabled", 503)
    candidates = [model_override] if model_override else cfg["models"]
    emitted = False; error = None
    if cfg["streaming"] or probe:
        try:
            for piece in _lm_stream(route, messages, model_override, probe, tokens=tokens, timeout_seconds=timeout_seconds):
                emitted = True
                yield piece
            return
        except Exception as exc:
            if emitted or probe: raise
            error = exc
    else:
        error = GatewayError("Streaming disabled on route", 422)
    from . import lm_direct
    started = time.monotonic(); text = []
    try:
        budget = min(300, max(1, timeout_seconds)) if timeout_seconds is not None else 120
        for piece in lm_direct.stream_fallback(messages, candidates=list(candidates), tokens=min(max((tokens or 0) * 3, 1500), cfg["max_tokens"]),
                                               temperature=cfg["temperature"], timeout=budget):
            text.append(piece)
            yield piece
    except lm_direct.DirectError:
        if text: raise
        # Some upstreams accept chat but disconnect SSE before its first token.
        # Ask the SAME configured route for a real bounded response; never fake
        # incremental tokens or replay after any content has reached the user.
        if probe: raise error
        try:
            response, _ = complete(route, messages, required={"chat"}, tokens=tokens,
                                   model_override=model_override)
            answer = adapters.text("chat", response)
            if answer:
                yield answer
                return
        except Exception:
            pass
        raise error
    record = _record(route, "chat", candidates[0] if candidates else "", started, [{"model": "direct:stream", "http_status": 200}],
                     {"output_text": "".join(text)}, {}, request=messages)
    record.update(routed_via="direct:stream")
    _audit(record)


def _lm_stream(route, messages, model_override=None, probe=False, *, tokens=None, timeout_seconds=None):
    cfg = defaults()[route]; models = store.records("models")
    candidates = [model_override] if model_override else cfg["models"]
    if not cfg["enabled"] or not gateway_settings()["enabled"]: raise GatewayError("Route disabled", 503)
    started = time.monotonic(); attempts = []; emitted = False; last = None
    budget = min(300, max(1, timeout_seconds)) if timeout_seconds is not None else 300
    if not _slots.acquire(timeout=2): raise GatewayError("AI request queue is busy", 429)
    try:
        for mid in candidates[:8] if cfg["automatic_fallback"] else candidates[:1]:
            if time.monotonic()-started >= budget: break
            if not model_allowed(mid): continue
            model = models.get(mid, {})
            if not model.get("enabled") or not model.get("available",True) or (not probe and not {"chat","streaming"}.issubset(capabilities(model))): continue
            body = adapters.payload("chat", mid, messages, tokens=min(256 if probe else (tokens or cfg["max_tokens"]), cfg["max_tokens"], 16000), stream=True)
            result = {}; hdr = {}; chunks = []
            try:
                with _client(min(cfg["timeout"],max(1,budget-(time.monotonic()-started)))) as client:
                    with client.stream("POST", _url("chat/completions"), headers=headers(), json=body) as response:
                        hdr = dict(response.headers)
                        if not response.is_success:
                            raise GatewayError(f"LM stream HTTP {response.status_code}", response.status_code, response.status_code in {429,500,502,503,504})
                        completed = False
                        for line in response.iter_lines():
                            if time.monotonic()-started > budget: raise GatewayError("Stream deadline exceeded", 504)
                            if not line.startswith("data:"): continue
                            value = line[5:].strip()
                            if value == "[DONE]": completed = True; break
                            chunk = json.loads(value)
                            if chunk.get("error"): raise GatewayError("LM stream reported an error")
                            if chunk.get("model"): result["model"] = chunk["model"]
                            if chunk.get("usage"): result["usage"] = chunk["usage"]
                            choices = chunk.get("choices") or []
                            if choices and choices[0].get("finish_reason"): completed = True
                            delta = choices[0].get("delta", {}).get("content") if choices else None
                            if delta:
                                emitted = True; chunks.append(delta); yield delta
                        if not completed: raise GatewayError("LM stream ended before completion", 502, True)
                attempts.append({"model": mid, "http_status": 200})
                result["output_text"] = "".join(chunks)
                _audit(_record(route, "chat", candidates[0], started, attempts, result, hdr, request=body))
                return
            except (GatewayError, httpx.TransportError) as exc:
                last = exc; attempts.append({"model": mid, "http_status": getattr(exc, "status", 504), "error": safe(str(exc), 300)})
                if emitted: raise
                if not getattr(exc, "retryable", isinstance(exc, httpx.TransportError)): break
        raise last or GatewayError("No streaming-verified model available", 422)
    except BaseException as exc:
        _audit(_record(route, "chat", candidates[0], started, attempts, error=exc, request=messages))
        raise
    finally:
        _slots.release()


def probe_model(mid, capability="chat"):
    models = store.records("models")
    if mid not in models: raise GatewayError("Unknown catalog model", 404)
    allowed = {"chat", "responses", "messages", "embeddings", "vision", "structured", "tools", "streaming"}
    if capability not in allowed: raise GatewayError("Unsupported probe; costly media tests are not enabled", 422)
    messages = [{"role": "user", "content": 'Return only {"ok":true}.'}]
    endpoint = capability if capability in {"responses", "messages", "embeddings"} else "chat"
    extra = None
    if capability == "vision":
        import base64, io
        from PIL import Image
        buffer = io.BytesIO(); Image.new("RGB", (32,32), "blue").save(buffer, format="PNG")
        messages = [{"role":"user","content":[{"type":"text","text":"What is the dominant color? Answer one word."},
                    {"type":"image_url","image_url":{"url":"data:image/png;base64,"+base64.b64encode(buffer.getvalue()).decode()}}]}]
    if capability == "structured": extra = {"response_format":{"type":"json_object"}}
    if capability == "tools":
        extra = {"tools":[{"type":"function","function":{"name":"ping","description":"Connectivity test","parameters":{"type":"object","properties":{}}}}],"tool_choice":"required"}
    started = time.monotonic()
    probe_record = None
    try:
        if capability == "streaming":
            output = "".join(stream_chat("general_chat", messages, mid, probe=True))
            if not output: raise GatewayError("Empty streamed response")
        else:
            data, probe_record = complete("embeddings" if endpoint == "embeddings" else "general_chat",
                "probe" if endpoint == "embeddings" else messages, tokens=120, extra=extra,
                endpoint=endpoint, model_override=mid, probe=True)
            output = adapters.text(endpoint, data)
            if capability == "embeddings":
                vectors = data.get("data") or []
                if not vectors or not isinstance(vectors[0].get("embedding"), list) or not vectors[0]["embedding"]:
                    raise GatewayError("No embedding vector returned")
            elif capability == "tools":
                if not (data.get("choices") or [{}])[0].get("message", {}).get("tool_calls"): raise GatewayError("Tool call not returned")
            elif capability == "vision":
                if "blue" not in output.lower(): raise GatewayError("Vision test failed semantic check")
            elif capability == "structured": json.loads(output)
            elif not output: raise GatewayError("Empty model response")
        row = {"verified": [capability],
               "status":"Healthy", "last_test":datetime.now(timezone.utc).isoformat(), "test_latency_ms":round((time.monotonic()-started)*1000), "last_error":None}
    except Exception as exc:
        if probe_record:
            probe_record.update(status="failed",error=safe(str(exc),500),probe_capability=capability)
            _audit(probe_record)
        store.patch("models",mid,{"status":"Degraded" if models[mid].get("verified") else "Failed", "last_test":datetime.now(timezone.utc).isoformat(), "last_error":safe(str(exc),500)})
        raise
    if probe_record:
        probe_record["probe_capability"] = capability; _audit(probe_record)
    return store.patch("models",mid,row,union=("verified",))


@observe_request
def transcription(audio, language=None, *, provider=None):
    """One verified multipart STT submission; never retries paid transcription."""
    cfg=defaults().get('transcription',{})
    if not cfg.get('enabled') or not gateway_settings()['enabled']:
        raise GatewayError('Transcription routing is disabled',503)
    candidates=cfg.get('models',[])
    if provider:
        group={'jarvis':'jarvis-all-models','sarovi':'sarovi-all-models'}.get(provider)
        if not group:raise GatewayError('Unsupported STT provider',422)
        candidates=[m for m in candidates if m.endswith('#'+group) and ('scribe' in m.lower() or 'eleven' in m.lower())]
    candidates=candidates[:1]
    model=candidates[0] if candidates else ''
    item=store.records('models').get(model,{})
    if not model_allowed(model) or not item.get('enabled') or 'transcription' not in capabilities(item):
        raise GatewayError('No verified gateway STT model; local Whisper fallback is available',422)
    from .media_policy import response_timeout,request_headers,require_gateway_safety
    body={'model':model,'response_format':'verbose_json','timestamp_granularities[]':'word'}
    if language:body['language']=language
    timeout=response_timeout('speech',max(200,cfg.get('timeout',200)),body)
    started=time.monotonic();attempts=[]
    try:
        with _client(timeout) as client:
            require_gateway_safety(client,_url('editor-media-policy'),headers())
            auth=headers();auth.pop('Content-Type',None)
            with Path(audio).open('rb') as file:
                response=client.post(_url(adapters.PATHS['transcription']),headers={**auth,**request_headers('speech',timeout)},data=body,files={'file':(Path(audio).name,file,'audio/mpeg')})
        attempts.append({'model':model,'http_status':response.status_code})
        if not response.is_success:raise GatewayError(f'Gateway STT HTTP {response.status_code}',response.status_code)
        result=response.json()
        if not isinstance(result,dict) or not isinstance(result.get('words'),list):raise GatewayError('STT word timestamp contract not satisfied')
        _audit(_record('transcription','transcription',model,started,attempts,result,dict(response.headers),request={'model':model,'language':language}))
        return {**result,'model':model}
    except Exception as exc:
        _audit(_record('transcription','transcription',model,started,attempts,error=exc,request={'model':model,'language':language}))
        raise


@observe_request
def speech(route, text, voice, *, language="", context=""):
    """Verified binary media contract; exactly one submission, including on 429."""
    cfg = defaults().get(route)
    if not cfg or not cfg.get('enabled') or not gateway_settings()['enabled']:
        raise GatewayError('Speech routing is disabled',503)
    catalog=store.records('models'); started=time.monotonic(); attempts=[]
    from .speech_policy import gateway_choice
    try:
        mid, body = gateway_choice(cfg, catalog, text, voice, context, language)
    except ValueError as exc:
        _audit(_record(route,'speech',next(iter(cfg.get('models', [])), ''),started,attempts,
                       error=exc,request={'input':text,'language':language,'casting':'rejected-before-submission'}))
        raise
    candidates=[mid]
    for mid in candidates:
        item=catalog.get(mid,{})
        if not model_allowed(mid) or not item.get('enabled') or not item.get('available',True) or 'speech' not in capabilities(item):
            continue
        try:
            from .media_policy import response_timeout,request_headers as media_headers,require_gateway_safety
            timeout=response_timeout('speech',cfg['timeout'],body)
            with _client(timeout) as client:
                require_gateway_safety(client,_url('editor-media-policy'),headers())
                response=client.post(_url(adapters.PATHS['speech']),headers={**headers(),**media_headers('speech',timeout)},json=body)
            attempts.append({'model':mid,'http_status':response.status_code})
            if not response.is_success:
                raise GatewayError(f'LM speech HTTP {response.status_code}: {safe(response.text,200)}',response.status_code)
            if not response.headers.get('content-type','').startswith('audio/') or not 100 < len(response.content) < 30*1024*1024:
                raise GatewayError('Gateway returned invalid audio content')
            record=_record(route,'speech',candidates[0],started,attempts,
                {'content_type':response.headers.get('content-type'),'size_bytes':len(response.content)},dict(response.headers),request=body)
            try:
                from .media_archive import save
                artifact=save(response.content,response.headers.get('content-type','').split(';')[0])
                if artifact:record['media']=[artifact]
            except Exception:log.exception('Could not archive audio response; original result retained')
            _audit(record)
            return response.content
        except Exception as exc:
            _audit(_record(route,'speech',candidates[0],started,attempts,error=exc,request={'model':mid,'input':text}))
            raise
    raise GatewayError('No verified speech model is available',503)


def job_scope(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        obj = args[0] if args else kwargs.get("job_id")
        token = job_context.set(str(getattr(obj, "id", obj)) if obj is not None else job_context.get())
        owner = getattr(obj,"user_id",None)
        if owner is None and isinstance(obj,str):
            from app.jobs import get
            job = get(obj)
            owner = getattr(job,"user_id",None) if job else None
        user = user_context.set(str(owner) if owner is not None else user_context.get())
        try: return function(*args, **kwargs)
        finally: job_context.reset(token); user_context.reset(user)
    return wrapped


def conversation_scope(function):
    @functools.wraps(function)
    def wrapped(conversation_id, user_key, *args, **kwargs):
        user=user_context.set(str(user_key)); conversation=conversation_context.set(conversation_id)
        try:return function(conversation_id,user_key,*args,**kwargs)
        finally:user_context.reset(user);conversation_context.reset(conversation)
    return wrapped


def observe_specialized(route, provider, endpoint=None):
    """Audit preserved specialist calls without pretending they passed through LM API."""
    def decorate(function):
        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            if not configured(): return function(*args,**kwargs)
            if route == 'audio':
                return function(*args,**kwargs)  # The central speech transport owns its audit.
            started=time.monotonic(); error=None
            is_audio=route=="audio"
            from .localize import tts_model
            model=(kwargs.get("model_id") or (args[3] if len(args)>3 else "") or tts_model()) if is_audio else (kwargs.get("model") or "")
            prompt=args[0] if is_audio else (args[1] if len(args)>1 else kwargs.get("prompt",""))
            try:return function(*args,**kwargs)
            except Exception as exc:error=exc;raise
            finally:
                try: cfg=gateway_settings()
                except Exception: cfg={"capture_messages":False,"log_char_limit":256}
                _audit({"id":str(uuid.uuid4()),"timestamp":datetime.now(timezone.utc).isoformat(),
                    "user_id":user_context.get(),"job_id":job_context.get(),"conversation_id":conversation_context.get(),
                    "route":route,"endpoint":endpoint or ("v1/text-to-speech" if is_audio else "chat/completions"),
                    "requested_model":model,"actual_model":None,"provider":provider,"transport":"preserved-specialist",
                    "status":"failed" if error else "success","latency_ms":round((time.monotonic()-started)*1000),
                    "input_tokens":None,"output_tokens":None,"cost":None,"http_status":None,
                    "retry_count":0,"fallback_history":[],"error":safe(str(error),500) if error else None,
                    "request_message":safe(prompt,cfg["log_char_limit"]) if cfg["capture_messages"] else None,
                    "response_message":"Binary media omitted" if not error else None})
        return wrapped
    return decorate
