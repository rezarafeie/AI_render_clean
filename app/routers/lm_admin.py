"""Server-enforced administration for AI models, routes and audit logs."""
from __future__ import annotations
import csv
import io
import json
import threading
import time
from collections import Counter, defaultdict
from typing import Literal
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse, FileResponse
from pydantic import BaseModel, Field, ConfigDict
from app.config import settings
from app.job_access import is_local_auth_bypass
from app import lm_store as store
from brain import lm_gateway as gateway


def allowed(request):
    user = getattr(request.state, "user", None)
    if not user: return False
    if settings.APP_ENV != "production" and is_local_auth_bypass(request) and str(user.id) == "local_dev": return True
    ids = {x.strip() for x in settings.AI_ADMIN_USER_IDS.split(",") if x.strip()}
    emails = {x.strip().lower() for x in settings.AI_ADMIN_EMAILS.split(",") if x.strip()}
    return str(user.id) in ids or str(user.email).lower() in emails


def admin(request: Request):
    if not allowed(request): raise HTTPException(403, "Administrator access required")


access_router = APIRouter(prefix="/admin/ai", tags=["AI administration"])
router = APIRouter(prefix="/admin/ai", tags=["AI administration"], dependencies=[Depends(admin)])


@access_router.get("/access")
def access(request: Request):
    return {"allowed": allowed(request)}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelUpdate(Strict):
    id: str = Field(min_length=1, max_length=512)
    enabled: bool


class Probe(Strict):
    id: str = Field(min_length=1, max_length=512)
    capability: str = Field(pattern="^(chat|responses|messages|embeddings|vision|structured|tools|streaming)$")


class RouteUpdate(Strict):
    models: list[str] = Field(min_length=1, max_length=8)
    endpoint: str = Field(pattern="^(chat|responses|messages|embeddings|image|speech|video|transcription|music)$")
    enabled: bool = True
    timeout: int = Field(default=90, ge=5, le=3600)
    max_retries: int = Field(default=0, ge=0, le=2)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int = Field(default=16000, ge=32, le=32000)
    streaming: bool = False
    automatic_fallback: bool = True


class SettingsUpdate(Strict):
    enabled: bool
    capture_messages: bool
    log_char_limit: int = Field(ge=256, le=12000)
    direct_mode: bool = False


class SpeechVoice(Strict):
    voice_id: str = Field(min_length=1, max_length=160)
    provider: Literal["elevenlabs", "google"]
    languages: list[str] = Field(min_length=1, max_length=150)
    labels: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class SpeechModel(Strict):
    speech_provider: Literal["elevenlabs", "google"]
    supported_languages: list[str] = Field(min_length=1, max_length=150)
    voices: list[SpeechVoice] = Field(default_factory=list, max_length=200)


class SpeechCasting(Strict):
    voices: list[SpeechVoice] = Field(default_factory=list, max_length=200)
    models: dict[str, SpeechModel] = Field(default_factory=dict)


@router.get("/speech-casting")
def speech_casting():
    return store.records("settings").get("speech_casting", {"voices": [], "models": {}})


@router.put("/speech-casting")
def save_speech_casting(body: SpeechCasting):
    catalog = store.records("models")
    for mid, profile in body.models.items():
        row = catalog.get(mid, {})
        if "speech" not in row.get("verified", []):
            raise HTTPException(422, "Register and verify the speech model before configuring its voices")
        if any(v.provider != profile.speech_provider for v in profile.voices):
            raise HTTPException(422, "Voice provider must match the speech model")
    # Only public voice metadata; credentials never belong in a profile.
    value = body.model_dump()
    store.save("settings", {"speech_casting": value})
    return value


def public_model(value):
    return {k:v for k,v in value.items() if k != "metadata"}


@router.get("/models")
def models(q: str = Query("", max_length=200), provider: str = "", capability: str = "", page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200)):
    rows = [r for r in store.records("models").values() if gateway.model_allowed(r["id"])]
    providers = sorted({r["provider"] for r in rows if r.get("provider")})
    if q: rows = [r for r in rows if q.lower() in (r["id"]+" "+r["name"]).lower()]
    if provider: rows = [r for r in rows if r.get("provider") == provider]
    if capability: rows = [r for r in rows if capability in gateway.capabilities(r)]
    rows.sort(key=lambda r:r["id"])
    return {"items":[public_model(r) for r in rows[(page-1)*size:page*size]], "total":len(rows), "providers":providers}


@router.post("/models/sync")
def sync():
    try: return gateway.sync_models()
    except Exception as exc: raise HTTPException(502, gateway.safe(str(exc), 500)) from exc


@router.patch("/models")
def update_model(body: ModelUpdate):
    row = store.records("models").get(body.id)
    if row is None: raise HTTPException(404, "Model not found")
    return public_model(store.patch("models",body.id,{"enabled":body.enabled}))


_probes = defaultdict(list)
_lock = threading.Lock()


@router.post("/models/test")
def probe(body: Probe, request: Request):
    with _lock:
        uid = str(request.state.user.id); now = time.monotonic()
        _probes[uid] = [v for v in _probes[uid] if now-v < 60]
        if len(_probes[uid]) >= 8: raise HTTPException(429, "At most eight bounded probes per minute")
        _probes[uid].append(now)
    try: return public_model(gateway.probe_model(body.id, body.capability))
    except Exception as exc: raise HTTPException(422, gateway.safe(str(exc),500)) from exc


@router.get("/routes")
def routes(): return list(gateway.defaults().values())


@router.post("/routes/prioritize")
def prioritize_routes():
    """Apply the operator priority to every chat/vision route: Jarvis, Sarovi, Arvan, then the rest; Gemini/Google models via Google first.
    Only the order changes: no model is added, removed or enabled, and media routes are left alone. Direct fallbacks follow the same order."""
    from brain.lm_tasks import prioritize
    from brain import lm_direct
    changed = {}
    for route_id, row in gateway.defaults().items():
        if row.get("capability") not in {"chat", "vision"}:
            continue
        ordered = prioritize(list(row["models"]))
        if ordered != row["models"]:
            row["models"] = ordered
            changed[route_id] = row
    if changed:
        store.save("routes", changed)
    direct = lm_direct.apply_priority()
    return {"routes_changed": sorted(changed), "direct_order": [p["id"] for p in direct["providers"]]}


@router.put("/routes/{route_id}")
def update_route(route_id: str, body: RouteUpdate):
    row = gateway.defaults().get(route_id)
    if row is None: raise HTTPException(404, "Unknown route")
    if row['capability'] in {'image','speech','video','music','transcription'} and (body.max_retries or body.automatic_fallback):
        raise HTTPException(422,'Media retries and fallback require explicit user confirmation for every attempt')
    catalog = store.records("models")
    if len(set(body.models)) != len(body.models) or any(mid not in catalog for mid in body.models):
        raise HTTPException(422, "Choose unique IDs from the actual model catalog")
    if any(not gateway.model_allowed(mid) for mid in body.models):
        raise HTTPException(422, "Vercel is disabled by installation policy")
    if row["capability"] in {"video", "transcription", "music"} and body.enabled:
        raise HTTPException(422, "Specialized LM media execution is not verified; the existing editor provider remains active")
    if body.enabled and row['capability'] in {'image','speech'} and body.endpoint != row['capability']:
        raise HTTPException(422,'Choose the verified media endpoint, not the text endpoint')
    if route_id == 'image_editing' and body.enabled:
        raise HTTPException(422,'Image editing requires a separately verified editing contract; generation is not editing')
    if route_id == "embeddings" and (body.endpoint != "embeddings" or len(body.models) != 1):
        raise HTTPException(422, "Embeddings require one pinned model family to preserve vector compatibility")
    if route_id == "video_understanding" and body.endpoint != "chat":
        raise HTTPException(422, "Vision currently requires the verified chat image-input adapter")
    if body.streaming and body.endpoint != "chat": raise HTTPException(422, "Only verified chat streaming is exposed")
    required = row["capability"] if row["capability"] == "vision" else body.endpoint
    if body.enabled:
        for mid in body.models:
            caps = gateway.capabilities(catalog[mid])
            if required not in caps or (body.streaming and "streaming" not in caps):
                raise HTTPException(422, f"Test the required capability first: {mid}")
            if body.temperature is not None and "temperature" not in catalog[mid].get("metadata",{}).get("supported_parameters",[]):
                raise HTTPException(422, f"Temperature support is not declared for {mid}; leave it blank")
    row.update(body.model_dump()); store.save("routes", {route_id:row}); return row


@router.get("/settings")
def get_settings():
    from brain import lm_direct
    return {**gateway.gateway_settings(), "configured":gateway.configured(), "base_url":settings.LMAPI_BASE_URL,
            "direct_ready":bool(lm_direct.usable()),
            "discovery":store.records("settings").get("discovery"), "concurrency_per_worker":4}


@router.put("/settings")
def put_settings(body: SettingsUpdate):
    from brain import lm_direct
    if body.direct_mode and not lm_direct.usable():
        raise HTTPException(409, "Direct mode needs at least one direct provider with an API key (Direct fallbacks tab); with none the router would have nothing to call")
    store.save("settings", {"global":body.model_dump()}); return get_settings()


def filters(model="", status="", user_id="", route="", id="", since=None, until=None):
    return {"model":model,"status":status,"user_id":user_id,"route":route,"id":id,
            "since":since.isoformat() if since else None,"until":until.isoformat() if until else None}


@router.get("/logs")
def logs(model: str="", status: str="", user_id: str="", route: str="", id: str="",
         since: datetime|None=None, until: datetime|None=None,
         page: int=Query(1,ge=1), size: int=Query(50,ge=1,le=200)):
    return store.logs(filters(model,status,user_id,route,id,since,until),page,size)


@router.get('/media/{media_id}')
def audit_media(media_id: str):
    from brain.media_archive import resolve
    try:path=resolve(media_id)
    except (ValueError,FileNotFoundError):raise HTTPException(404,'Media not found')
    return FileResponse(path,headers={'Cache-Control':'private, no-store'})


@router.get("/logs.csv")
def export_logs(model: str="", status: str="", user_id: str="", route: str="", id: str="",
                since: datetime|None=None, until: datetime|None=None):
    query = filters(model,status,user_id,route,id,since,until)
    if store.logs(query,size=1)["total"] > 10000: raise HTTPException(422,"Narrow the export date range to 10,000 requests or fewer")
    result = store.logs(query,size=10000)
    fields = ["timestamp","id","job_id","user_id","route","requested_model","actual_model","provider","status","latency_ms","input_tokens","output_tokens","cache_read_tokens","cache_write_tokens","credits","conversation_id","project_kind","project_id","cost"]
    output=io.StringIO(); writer=csv.DictWriter(output,fieldnames=fields,extrasaction="ignore"); writer.writeheader()
    for row in result["items"]:
        # CSV formula injection protection for model/user-controlled values.
        writer.writerow({k:("'"+v if isinstance(v,str) and v[:1] in "=+-@\t\r" else v) for k,v in row.items()})
    return Response(output.getvalue(),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=ai-requests.csv","Cache-Control":"no-store"})


@router.get("/analytics")
def analytics(since: datetime|None=None, until: datetime|None=None):
    result = store.logs(filters(since=since,until=until),size=50000)
    rows=result["items"]; count=len(rows)
    groups=defaultdict(list); days=defaultdict(Counter)
    for row in rows:
        groups[row["requested_model"]].append(row)
        day=days[row["timestamp"][:10]]; day["requests"]+=1; day["failed"]+=row["status"]!="success"
    def summary(items):
        known_cost=[r["cost"] for r in items if isinstance(r.get("cost"),(int,float))]
        known_tokens=[r for r in items if r.get("input_tokens") is not None or r.get("output_tokens") is not None]
        return {"requests":len(items),"successful":sum(r["status"]=="success" for r in items),
            "failed":sum(r["status"]!="success" for r in items),
            "average_latency_ms":round(sum(r["latency_ms"] for r in items)/len(items)) if items else None,
            "tokens":sum((r.get("input_tokens") or 0)+(r.get("output_tokens") or 0) for r in known_tokens) if known_tokens else None,
            "cost":sum(known_cost) if known_cost else None,"cost_reported_requests":len(known_cost)}
    return {**summary(rows),"total_matching":result["total"],"truncated":result["total"]>count,
            "models":[{"id":mid,**summary(items)} for mid,items in groups.items()],
            "daily":[{"date":day,**counts} for day,counts in sorted(days.items())]}


class StreamProbe(Strict):
    route: str = "general_chat"


@router.post("/stream-check")
def stream_check(body: StreamProbe):
    if body.route not in gateway.ROUTES: raise HTTPException(422,"Unknown route")
    def events():
        try:
            for delta in gateway.stream_chat(body.route,[{"role":"user","content":"Say hello briefly."}]):
                yield "data: "+json.dumps({"delta":delta})+"\n\n"
            yield "event: done\ndata: {}\n\n"
        except Exception as exc:
            yield "event: error\ndata: "+json.dumps({"error":gateway.safe(str(exc),300)})+"\n\n"
    return StreamingResponse(events(),media_type="text/event-stream",headers={"Cache-Control":"no-store","X-Accel-Buffering":"no"})


# ── Direct provider fallbacks (brain/lm_direct.py) ──────────────────────────────
from brain import lm_direct  # noqa: E402


class DirectProvider(Strict):
    prefer_stream: bool | None = None
    id: str = Field(pattern="^[a-z]{3,12}$")
    enabled: bool = True
    base_url: str = Field(max_length=300)
    model: str = Field(min_length=1, max_length=200)
    format: str = Field(default="openai", pattern="^(openai|gemini)$")
    extra_header_name: str = Field(default="", max_length=60)


class LocalSTTFallback(Strict):
    enabled: bool = True
    model: str = Field(default="small", pattern="^(base|small|medium|large-v3)$")
    improve_low_quality: bool = True


class DirectUpdate(Strict):
    enabled: bool
    providers: list[DirectProvider] = Field(max_length=8)
    stt: LocalSTTFallback | None = None


class SecretUpdate(Strict):
    value: str | None = Field(default=None, max_length=4000)


@router.get("/direct")
def direct_status():
    """Master switch, ordered providers, and whether each has a key. Keys are never returned."""
    return lm_direct.status()


@router.put("/direct")
def direct_update(body: DirectUpdate):
    try:
        return lm_direct.save_config(body.enabled, [item.model_dump() for item in body.providers], body.stt.model_dump() if body.stt else None)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.put("/direct/{provider}/key")
def direct_key(provider: str, body: SecretUpdate):
    """Write-only. An empty value deletes the saved key."""
    try:
        lm_direct.set_secret(provider, body.value)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return lm_direct.status()


@router.put("/direct/{provider}/header")
def direct_header(provider: str, body: SecretUpdate):
    """Write-only value for the optional extra header (for example a proxy relay secret)."""
    try:
        lm_direct.set_secret(f"{provider}:header", body.value)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return lm_direct.status()


@router.post("/direct/{provider}/test")
def direct_test(provider: str, request: Request):
    with _lock:
        uid = str(request.state.user.id); now = time.monotonic()
        _probes[uid] = [v for v in _probes[uid] if now - v < 60]
        if len(_probes[uid]) >= 8: raise HTTPException(429, "At most eight bounded probes per minute")
        _probes[uid].append(now)
    try:
        return lm_direct.probe(provider)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


# ── credits (token credit system): balances, the weights table, packages and orders ──────────────────

class CreditAdjust(Strict):
    amount: int = Field(ge=-10**12, le=10**12)
    note: str = Field(default="", max_length=300)


class CreditUnlimited(Strict):
    unlimited: bool


class CreditWeight(Strict):
    model_config = ConfigDict(extra="forbid")
    in_: float = Field(alias="in", ge=0, le=10000)
    out: float = Field(ge=0, le=10000)
    cache: float = Field(ge=0, le=10000)
    write: float = Field(ge=0, le=10000)


class CreditSettings(Strict):
    initial_grant: int = Field(ge=0, le=10**12)
    enforce: bool = True
    weights: dict[str, CreditWeight] = Field(max_length=200)
    default: CreditWeight
    per_call: dict[str, int] = Field(max_length=30)


class CreditPackageBody(Strict):
    id: str = Field(min_length=1, max_length=32, pattern="^[A-Za-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=120)
    credits: int = Field(gt=0, le=10**12)
    price: int = Field(default=0, ge=0, le=10**12)
    currency: str = Field(default="IRT", max_length=8)
    active: bool = True
    sort: int = Field(default=0, ge=0, le=1000)


def _weights_dump(value):
    return {k: {"in": v.in_, "out": v.out, "cache": v.cache, "write": v.write} for k, v in value.items()}


@router.get("/credits/users")
async def credit_users(query: str = Query("", max_length=100)):
    from app import credits
    return {"items": await credits.users_overview(query), "initial_grant": credits.settings()["initial_grant"]}


@router.get("/credits/users/{user_id}")
async def credit_user(user_id: str, page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200)):
    from app import credits
    return {"account": await credits.account(user_id), "chats": await credits.chat_usage(user_id),
            "projects": await credits.usage_by(user_id, "project_id"), **await credits.ledger(user_id, page, size)}


@router.post("/credits/users/{user_id}/adjust")
async def credit_adjust(request: Request, user_id: str, body: CreditAdjust):
    """Add (positive) or take away (negative) credits by hand; the change is a ledger row with the administrator's id."""
    from app import credits
    if body.amount == 0: raise HTTPException(422, "The amount cannot be zero")
    await credits.account(user_id)
    await credits.apply(user_id, body.amount, "admin", fields={"note": body.note or None, "actor": str(request.state.user.id)})
    return await credits.account(user_id)


@router.put("/credits/users/{user_id}/unlimited")
async def credit_unlimited(user_id: str, body: CreditUnlimited):
    from app import credits
    return await credits.set_unlimited(user_id, body.unlimited)


@router.get("/credits/settings")
def credit_settings():
    from app import credits
    return credits.settings(fresh=True)


@router.put("/credits/settings")
def credit_settings_save(body: CreditSettings):
    from app import credits
    return credits.save_settings({"initial_grant": body.initial_grant, "enforce": body.enforce, "weights": _weights_dump(body.weights),
                                  "default": {"in": body.default.in_, "out": body.default.out, "cache": body.default.cache, "write": body.default.write},
                                  "per_call": body.per_call})


@router.get("/credits/packages")
async def credit_packages():
    from app import credits
    return {"items": await credits.packages(active_only=False)}


@router.put("/credits/packages")
async def credit_package_save(body: CreditPackageBody):
    from app import credits
    return await credits.save_package(body.model_dump())


@router.get("/credits/orders")
async def credit_orders(user_id: str | None = Query(None, max_length=64)):
    from app import credits
    return {"items": await credits.orders(user_id, limit=200)}


@router.post("/credits/orders/{order_id}/paid")
async def credit_order_paid(request: Request, order_id: str):
    """The administrator confirms an order was paid: its credits are added once (a second confirmation changes nothing)."""
    from app import credits
    try:
        return await credits.mark_paid(order_id, gateway="manual", actor=str(request.state.user.id))
    except KeyError:
        raise HTTPException(404, "Order not found")
