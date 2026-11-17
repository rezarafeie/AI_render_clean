"""EditorGPT Pro on the app side (docs/PRO_AGENT_PLAN.md).

    POST /internal/anthropic/v1/messages    the Anthropic Messages API for the Claude Code CLI inside the agent container: run token → model allow-list →
                                             the jarvis provider's own /messages (the key is added here) → streamed back unbuffered → usage audited and
                                             charged like every model call (brain.lm_gateway._audit) → 402 when the run budget or the person's credit is spent
    POST /internal/pro/claim                 the agent worker takes the next queued Pro run (worker secret)
    GET  /internal/pro/status                stop requested? (run token)
    POST /internal/pro/tool                  the editorgpt MCP tools, executed here with the person's ownership checks (run token)
    POST /internal/pro/finish                the run ended (run token)

Only the agent network reaches these paths: a request that came through the public proxy (X-Forwarded-For) is refused, and every one needs a token.
"""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import shutil
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.agents import pro, store
from app.studio_store import repo

log = logging.getLogger(__name__)
router = APIRouter(include_in_schema=False)


def _internal(request: Request) -> None:
    if request.headers.get("x-forwarded-for") or request.headers.get("x-real-ip"):
        raise HTTPException(404, "not found")


def _claims(request: Request) -> dict:
    _internal(request)
    value = request.headers.get("x-api-key") or request.headers.get("x-pro-token") or ""
    auth = request.headers.get("authorization", "")
    if not value and auth.startswith("Bearer "):
        value = auth[7:]
    try:
        return pro.verify(value)
    except (ValueError, RuntimeError):
        raise HTTPException(401, "invalid run token")


def _anthropic_error(status: int, kind: str, message: str) -> JSONResponse:
    return JSONResponse({"type": "error", "error": {"type": kind, "message": message}}, status_code=status)


async def _run_of(claims: dict) -> dict:
    try:
        return await store.get_run(claims["run"], claims["user"])
    except KeyError:
        raise HTTPException(404, "run not found")


def _spent(record: dict) -> int:
    return int(((record["data"].get("pro") or {}).get("spent_credits")) or 0)


# ── the model proxy ─────────────────────────────────────────────────────────

def _provider() -> tuple[str, str]:
    from brain import lm_direct
    provider = next((p for p in lm_direct.usable() if p["id"] == "jarvis"), None)
    key = lm_direct.key_for("jarvis") if provider else ""
    if not provider or not key:
        raise HTTPException(503, "the model provider is not configured")
    return provider["base_url"].rstrip("/"), key


def _audit(claims: dict, model: str, usage: dict, started: float, status: str = "success", error: str | None = None) -> int:
    """One audited, charged model call (the same record and credit path as every other call). Returns the credits taken."""
    from brain import lm_gateway as gw
    tokens = [gw.user_context.set(str(claims["user"])), gw.conversation_context.set(claims["cid"]), gw.job_context.set(claims["run"]),
              gw.work_context.set(("pro", claims["run"]))]
    try:
        record = gw._record("pro_agent", "messages", model, started, [], response={"model": model, "usage": usage}, error=error)
        record["status"] = status
        gw._audit(record)
        return int(record.get("credits") or 0)
    finally:
        for var, token in zip((gw.user_context, gw.conversation_context, gw.job_context, gw.work_context), tokens):
            var.reset(token)


async def _add_spent(claims: dict, credits: int, usage: dict) -> None:
    if credits <= 0:
        return
    record = await _run_of(claims)
    state = dict(record["data"].get("pro") or {})
    state["spent_credits"] = _spent(record) + credits
    state["calls"] = int(state.get("calls") or 0) + 1
    state["input_tokens"] = int(state.get("input_tokens") or 0) + int(usage.get("input_tokens") or 0)
    state["output_tokens"] = int(state.get("output_tokens") or 0) + int(usage.get("output_tokens") or 0)
    state["cache_read_tokens"] = int(state.get("cache_read_tokens") or 0) + int(usage.get("cache_read_input_tokens") or 0)
    await store.update(claims["run"], claims["user"], patch={"pro": state})
    await repo.emit(claims["cid"], "pro.cost", {"run_id": claims["run"], "spent_credits": state["spent_credits"], "budget_credits": pro.BUDGET_CREDITS})


def _lift_tool_images(data: dict) -> bool:
    """Jarvis drops images that sit INSIDE a tool_result (the model then sees nothing and reads the file again and again: a 2026-11-17 run read one
    still 13 times). Each such image is moved right after its tool_result in the same user message, where it reaches the model; the result keeps a note."""
    changed = False
    for message in data.get("messages") or []:
        if message.get("role") != "user" or not isinstance(message.get("content"), list):
            continue
        out, lifted = [], []
        for block in message["content"]:
            if isinstance(block, dict) and block.get("type") == "tool_result" and isinstance(block.get("content"), list):
                images = [item for item in block["content"] if isinstance(item, dict) and item.get("type") == "image"]
                if images:
                    rest = [item for item in block["content"] if not (isinstance(item, dict) and item.get("type") == "image")]
                    block = {**block, "content": rest + [{"type": "text", "text": f"[{len(images)} image(s) of this result attached right after the tool results]"}]}
                    lifted += images
                    changed = True
            out.append(block)
        if lifted:
            first_other = next((i for i, b in enumerate(out) if not (isinstance(b, dict) and b.get("type") == "tool_result")), len(out))
            message["content"] = out[:first_other] + lifted + out[first_other:]
    return changed


@router.post("/internal/anthropic/v1/messages")
async def messages(request: Request):
    claims = _claims(request)
    record = await _run_of(claims)
    if record["status"] not in {"running"}:
        return _anthropic_error(403, "permission_error", "this run is not running")
    if _spent(record) >= pro.BUDGET_CREDITS:
        return _anthropic_error(402, "billing_error", "بودجهٔ این اجرا تمام شد.")
    from app import credits
    try:
        await credits.require(claims["user"])
    except Exception:
        return _anthropic_error(402, "billing_error", "اعتبار حساب تمام شده است.")
    body = await request.body()
    try:
        data = json.loads(body)
    except ValueError:
        return _anthropic_error(400, "invalid_request_error", "invalid JSON")
    if _lift_tool_images(data):
        body = json.dumps(data, ensure_ascii=False).encode()
    model = str(data.get("model") or "")
    if not model.startswith(pro.ALLOWED_MODELS):
        return _anthropic_error(400, "invalid_request_error", f"model {model!r} is not allowed for EditorGPT Pro")
    base, key = await asyncio.to_thread(_provider)          # lm_direct reads its settings with asyncio.run: never on the event loop
    headers = {"x-api-key": key, "anthropic-version": request.headers.get("anthropic-version", "2023-06-01"), "content-type": "application/json"}
    if request.headers.get("anthropic-beta"):
        headers["anthropic-beta"] = request.headers["anthropic-beta"]
    url = base + "/messages" + (("?" + request.url.query) if request.url.query else "")
    started = time.monotonic()
    from brain.http_ssl import ssl_context
    client = httpx.AsyncClient(timeout=httpx.Timeout(900, connect=20), verify=ssl_context())
    upstream = await client.send(client.build_request("POST", url, headers=headers, content=body), stream=True)
    if upstream.status_code != 200 or not data.get("stream"):
        raw = await upstream.aread()
        await upstream.aclose(); await client.aclose()
        if upstream.status_code == 200:
            try:
                usage = json.loads(raw).get("usage") or {}
            except ValueError:
                usage = {}
            credits_taken = await asyncio.to_thread(_audit, claims, model, usage, started)
            await _add_spent(claims, credits_taken, usage)
        else:
            log.warning("pro proxy: upstream %s for run %s", upstream.status_code, claims["run"])
        return Response(raw.replace(key.encode(), b"[REDACTED]"), status_code=upstream.status_code,
                        media_type=upstream.headers.get("content-type", "application/json"))

    usage: dict = {}

    async def relay():
        buffer = b""
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line.startswith(b"data:"):
                        continue
                    try:
                        event = json.loads(line[5:])
                    except ValueError:
                        continue
                    if event.get("type") == "message_start":
                        usage.update((event.get("message") or {}).get("usage") or {})
                    elif event.get("type") == "message_delta":
                        usage.update({k: v for k, v in (event.get("usage") or {}).items() if v is not None})
        finally:
            await upstream.aclose(); await client.aclose()
            try:
                credits_taken = await asyncio.to_thread(_audit, claims, model, usage, started)
                await _add_spent(claims, credits_taken, usage)
            except Exception:
                log.exception("pro proxy: usage could not be recorded for run %s", claims["run"])

    return StreamingResponse(relay(), status_code=200, media_type="text/event-stream",
                             headers={"cache-control": "no-cache", "x-accel-buffering": "no"})


# ── the agent worker ────────────────────────────────────────────────────────

@router.post("/internal/pro/claim")
async def claim(request: Request):
    _internal(request)
    secret = os.environ.get("PRO_WORKER_SECRET", "")
    if len(secret) < 32 or not hmac.compare_digest(request.headers.get("x-pro-worker", ""), secret):
        raise HTTPException(401, "invalid worker secret")
    record = await store.claim_pro()
    if record is None:
        return {"run": None}
    cid, user, rid = record["conversation_id"], record["user_key"], record["id"]
    work = pro.workdir(cid)                                # one folder per chat: a later message continues the same project and session
    for sub in ("in", "out"):
        (work / sub).mkdir(parents=True, exist_ok=True)
    for folder in (pro.RUNS / cid, work, work / "in", work / "out"):
        os.chmod(folder, 0o777)
    request_data = record["data"].get("request") or {}
    resume = None
    for other in await store.runs(cid, user):              # the previous Pro run of this chat: its session is resumed (same cwd, same config dir)
        if other["agent_mode"] == "pro" and other["id"] != rid and (other["data"].get("pro") or {}).get("session_id"):
            resume = other["data"]["pro"]["session_id"]
    await store.update(rid, user, patch={"pro": {"model": pro.MODEL, "budget_credits": pro.BUDGET_CREDITS, "spent_credits": 0, "phase": "start"}})
    await repo.emit(cid, "pro.started", {"run_id": rid, "model": pro.MODEL, "budget_credits": pro.BUDGET_CREDITS})
    await repo.emit(cid, "tool.started", {"tool": "pro_agent", "stage": "thinking", "message": "EditorGPT Pro کار را شروع کرد.", "agent_mode": "pro", "run_id": rid})
    from app.studio_flags import generation
    return {"run": rid, "user": user, "cid": cid, "token": pro.token(rid, user, cid), "model": pro.MODEL,
            "text": request_data.get("text", ""), "attachment_ids": request_data.get("attachment_ids") or [], "resume": resume,
            "stop_generation": record["data"].get("stop_generation", generation(user, cid))}


@router.get("/internal/pro/status")
async def status(request: Request):
    claims = _claims(request)
    record = await _run_of(claims)
    from app.studio_flags import generation
    stopped = record["status"] in {"cancelled", "stopped", "failed"} or \
        generation(claims["user"], claims["cid"]) != record["data"].get("stop_generation", generation(claims["user"], claims["cid"]))
    return {"stop": stopped, "spent_credits": _spent(record), "budget_credits": pro.BUDGET_CREDITS}


@router.post("/internal/pro/finish")
async def finish(request: Request):
    claims = _claims(request)
    body = await request.json()
    state = dict((await _run_of(claims))["data"].get("pro") or {})
    state.update({k: body.get(k) for k in ("session_id", "turns", "cli_cost_usd", "stop_reason") if body.get(k) is not None})
    final = body.get("status") if body.get("status") in {"completed", "failed", "stopped"} else "failed"
    await store.update(claims["run"], claims["user"], status=final, patch={"pro": state, **({"error": str(body.get("error"))[:500]} if body.get("error") else {})})
    message = {"completed": "EditorGPT Pro کار را تمام کرد.", "stopped": "EditorGPT Pro متوقف شد؛ پیام بعدی از همین‌جا ادامه می‌دهد.",
               "failed": "اجرای EditorGPT Pro کامل نشد."}[final]
    await repo.emit(claims["cid"], "tool.completed", {"tool": "pro_agent", "message": message, "agent_mode": "pro", "run_id": claims["run"]})
    await repo.emit(claims["cid"], "pro.finished" if final == "completed" else "pro.failed" if final == "failed" else "pro.stopped",
                    {"run_id": claims["run"], "spent_credits": state.get("spent_credits", 0)})
    if final == "failed" and body.get("error"):
        await repo.add_message(claims["cid"], claims["user"], "assistant", message + " " + str(body["error"])[:300], agent_mode="pro")
    await repo.emit(claims["cid"], "work.state", {"busy": False, "agent_mode": "pro", "run_id": claims["run"]})
    return {"ok": True}


# ── the editorgpt tools ─────────────────────────────────────────────────────

KIND_BY_SUFFIX = {".mp4": "video", ".mov": "video", ".webm": "video", ".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image",
                  ".mp3": "audio", ".wav": "audio", ".m4a": "audio"}
MIME = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4"}


async def _attach(claims: dict, path: Path) -> dict:
    """A file of the chat's folder becomes an attachment of the chat (the person sees and downloads it). What the agent MADE (stills, thumbnails, the
    delivered video) is not an upload: it does not go through the upload quota (a full quota made every thumbnail and delivery fail, 2026-11-17)."""
    from app.studio_ingest import attachment_folder
    suffix = path.suffix.lower()
    kind = KIND_BY_SUFFIX.get(suffix)
    if not kind:
        raise ValueError(f"unsupported file type {suffix}")
    folder = attachment_folder(claims["user"], claims["cid"])
    temporary = folder / f".pro-{claims['run']}-{int(time.time() * 1000)}{suffix}"
    await asyncio.to_thread(shutil.copy2, path, temporary)
    row = await repo.create_attachment(claims["cid"], claims["user"], kind=kind, filename=path.name[:255], path=str(temporary),
                                       mime_type=MIME[suffix], size_bytes=temporary.stat().st_size, metadata={"source": "pro", "run_id": claims["run"]})
    target = folder / f"{row['id']}{suffix}"
    temporary.replace(target)
    from app.studio_store import AsyncSessionLocal, DB_AVAILABLE
    if DB_AVAILABLE:
        from app.models import StudioAttachment
        async with AsyncSessionLocal() as db:
            item = await db.get(StudioAttachment, row["id"]); item.path = str(target); await db.commit()
    row["path"] = str(target)
    return row


async def _tool(claims: dict, name: str, args: dict):
    cid, user, rid = claims["cid"], claims["user"], claims["run"]
    if name == "say":
        text = str(args.get("text") or "").strip()[:4000]
        if not text:
            raise ValueError("text is empty")
        await repo.add_message(cid, user, "assistant", text, agent_mode="pro")
        return {"ok": True}
    if name == "step":
        state = args.get("state", "running")
        kind = {"running": "tool.started", "done": "tool.completed", "failed": "tool.failed"}.get(state, "tool.progress")
        await repo.emit(cid, kind, {"tool": "pro_step", "stage": "pro", "message": str(args.get("label") or "")[:200], "agent_mode": "pro", "run_id": rid,
                                    "activity_id": "pro-" + str(args.get("label") or "")[:60]})
        return {"ok": True}
    if name == "assets_list":
        conversation = await repo.get_conversation(cid, user)
        ids = []
        for message in conversation.get("messages") or []:
            ids += [a for a in (message.get("attachments") or []) if a not in ids]
        rows = await repo.get_attachments(ids, cid, user)
        return {"assets": [{"id": r["id"], "name": r["filename"], "kind": r["kind"], "size_bytes": r["size_bytes"],
                            **{k: v for k, v in (r.get("metadata") or {}).items() if k in {"duration", "width", "height", "fps"}}} for r in rows]}
    if name == "assets_fetch":
        rows = await repo.get_attachments([str(args.get("asset_id") or "")], cid, user)
        if not rows:
            raise ValueError("no such asset in this chat")
        row = rows[0]
        source = Path(row["path"])
        target = pro.inside(cid, f"in/{Path(row['filename']).name}")
        await asyncio.to_thread(shutil.copy2, source, target)
        os.chmod(target, 0o666)
        return {"path": str(target.relative_to(pro.workdir(cid))), "kind": row["kind"], "size_bytes": row["size_bytes"]}
    if name in {"show_stills", "deliver"}:
        paths = [args["path"]] if name == "deliver" else list(args.get("paths") or [])[:12]
        if not paths:
            raise ValueError("no files given")
        attached = []
        for value in paths:
            path = pro.inside(cid, str(value))
            if not path.is_file():
                raise ValueError(f"file not found: {value}")
            attached.append(await _attach(claims, path))
        text = str(args.get("caption") or args.get("notes") or args.get("title") or "").strip()[:2000] or ("استیل‌ها" if name == "show_stills" else "خروجی آماده است.")
        await repo.add_message(cid, user, "assistant", text, [a["id"] for a in attached], agent_mode="pro")
        if name == "deliver":
            await repo.emit(cid, "pro.output", {"run_id": rid, "attachment_id": attached[0]["id"], "title": str(args.get("title") or "")[:200]})
            record = await _run_of(claims)
            state = dict(record["data"].get("pro") or {})
            state["outputs"] = list(state.get("outputs") or []) + [{"attachment_id": attached[0]["id"], "title": str(args.get("title") or "")[:200]}]
            await store.update(rid, user, patch={"pro": state})
        return {"ok": True, "attachments": [a["id"] for a in attached]}
    if name == "render_cloud":
        return await _render_cloud(claims, str(args.get("project_dir") or "project"), str(args.get("output") or "out/video.mp4"))
    if name == "render_status":
        return _render_state(cid, str(args.get("job_id") or ""))
    raise ValueError(f"unknown tool {name}")


# ── renders on the render cloud (RunPod), not in the agent container ─────────

def _render_file(cid: str, job: str) -> Path:
    if not job.isalnum():
        raise ValueError("bad job id")
    folder = pro.RUNS / cid / ".renders"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{job}.json"


def _render_state(cid: str, job: str) -> dict:
    path = _render_file(cid, job)
    if not path.is_file():
        raise ValueError("no such render job")
    return json.loads(path.read_text())


async def _render_cloud(claims: dict, project_dir: str, output: str) -> dict:
    """A Remotion project of the chat's folder rendered on the render cloud (the same verified claude_motion worker the studio's films use: vertical
    1080x1920, 30 fps, muted video). Returns at once with a job id; render_status follows it. The project needs src/timing.json
    {"total": seconds, "width": 1080, "height": 1920, "fps": 30} and a composition with id Main."""
    import threading
    import uuid
    cid, user = claims["cid"], claims["user"]
    project = pro.inside(cid, project_dir)
    target = pro.inside(cid, output)
    try:
        timing = json.loads((project / "src" / "timing.json").read_text())
        size = (int(timing["width"]), int(timing["height"]), int(timing["fps"]))
        float(timing["total"])
    except (OSError, ValueError, KeyError) as exc:
        raise ValueError("the project needs src/timing.json with total, width, height and fps") from exc
    if size != (1080, 1920, 30):
        raise ValueError("the render cloud takes vertical 1080x1920 at 30 fps; render other formats in the container (node render.mjs video ...)")
    job = uuid.uuid4().hex[:12]
    state_file = _render_file(cid, job)

    def save(**values):
        current = json.loads(state_file.read_text()) if state_file.is_file() else {}
        current.update(values)
        state_file.write_text(json.dumps(current, ensure_ascii=False))

    save(job_id=job, state="queued", progress=0, output=output)

    def work():
        from app.render_cloud import hooks
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            done = hooks.claude_motion(project, target, timeout=3600, user=str(user), project_id="pro" + claims["run"], owned_roots=(pro.workdir(cid),),
                                       on_progress=lambda p: save(state="rendering", progress=int(p)),
                                       on_stage=lambda stage: save(stage=str(stage)), on_detail=lambda text: save(detail=str(text)[:200]))
            if done and target.is_file() and target.stat().st_size > 1000:
                save(state="done", progress=100, size_bytes=target.stat().st_size)
            else:
                save(state="failed", error="the render cloud did not take this project (no matching profile or the cloud is off); render it in the container")
        except Exception as exc:
            log.warning("pro cloud render %s failed", job, exc_info=True)
            save(state="failed", error=f"{type(exc).__name__}: {str(exc)[:300]}")
    threading.Thread(target=work, daemon=True, name=f"pro-render-{job}").start()
    await repo.emit(cid, "tool.progress", {"tool": "pro_render", "stage": "pro", "message": "رندر روی سرور ابری شروع شد", "agent_mode": "pro", "run_id": claims["run"]})
    return {"job_id": job, "state": "queued", "note": "poll render_status every 20-30 s (sleep with Bash between polls)"}


@router.post("/internal/pro/tool")
async def tool(request: Request):
    claims = _claims(request)
    record = await _run_of(claims)
    if record["status"] != "running":
        raise HTTPException(409, "this run is not running")
    body = await request.json()
    try:
        return {"ok": True, "result": await _tool(claims, str(body.get("name") or ""), dict(body.get("args") or {}))}
    except (ValueError, KeyError) as exc:
        return {"ok": False, "error": str(exc)[:500]}


# ── what the agent is doing, live in the chat ────────────────────────────────

@router.post("/internal/pro/event")
async def event(request: Request):
    """The runner reports the agent's own reply text (streamed: started → live deltas → completed and saved) and each tool step (started/done with a
    Persian label), so the chat shows the work as it happens, like a Claude Code session."""
    claims = _claims(request)
    body = await request.json()
    cid, user, rid = claims["cid"], claims["user"], claims["run"]
    kind = str(body.get("kind") or "")
    response_id = str(body.get("response_id") or "")[:80]
    if kind == "text_start":
        await repo.emit(cid, "assistant.response.started", {"response_id": response_id, "agent_mode": "pro", "run_id": rid})
    elif kind == "text_delta":
        from app import studio_live
        studio_live.publish(cid, "assistant.response.delta", {"response_id": response_id, "text": str(body.get("text") or "")[:20000]})
    elif kind == "text_done":
        text = str(body.get("text") or "").strip()[:20000]
        if text:
            saved = await repo.add_message(cid, user, "assistant", text, agent_mode="pro")
            await repo.emit(cid, "assistant.response.completed", {"response_id": response_id, "text": text, "message_id": saved["id"], "agent_mode": "pro"})
        else:
            await repo.emit(cid, "assistant.response.failed", {"response_id": response_id, "agent_mode": "pro"})
    elif kind in {"tool_start", "tool_done", "tool_failed"}:
        etype = {"tool_start": "tool.started", "tool_done": "tool.completed", "tool_failed": "tool.failed"}[kind]
        data = {"tool": "pro_" + str(body.get("tool") or "work")[:40], "activity_id": str(body.get("id") or "")[:80], "stage": "pro",
                "message": str(body.get("label") or "")[:200], "agent_mode": "pro", "run_id": rid}
        if body.get("detail"):
            data["request" if kind == "tool_start" else "response"] = str(body["detail"])[:1500]
        if body.get("image") and kind != "tool_start":            # the picture the agent looked at: a small thumbnail on its row, larger on click
            try:
                path = pro.inside(cid, str(body["image"]))
                if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} and path.stat().st_size < 15_000_000:
                    data["image"] = (await _attach(claims, path))["id"]
            except Exception:
                log.warning("pro: thumbnail for %s failed", body.get("image"), exc_info=True)
        await repo.emit(cid, etype, data)
    else:
        raise HTTPException(400, "unknown event")
    return {"ok": True}
