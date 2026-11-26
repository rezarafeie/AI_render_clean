"""Scheduled tasks: a person's standing instruction ("every day at 9, make five motion films about X") that runs on its own.

Each run starts NEW Studio chats through the app's own public API (the same path as a person typing: credit gate, engine choice, dispatcher), so every
engine works unchanged and every output also reaches the person's Telegram when it is linked. Before the chats start, a short planning call turns the
instruction into this run's briefs: distinct topics (never one of the recent runs'), fresh web sources when the task asks for research.

Storage: one JSON file per person under job_data/scheduled_tasks (small, rarely written; the app runs one worker process, which owns the loop).
Time: Iran time (UTC+03:30, no daylight saving since 2022).
"""

import asyncio
import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

IRAN = timezone(timedelta(hours=3, minutes=30))
ROOT = Path(os.environ.get("SCHEDULED_TASKS_DIR") or Path(__file__).resolve().parents[1] / "job_data" / "scheduled_tasks")
MAX_TASKS = 20
MAX_RUNS_KEPT = 60
TICK_SECONDS = 30
MISSED_GRACE = timedelta(hours=6)          # a run missed while the app was down still runs if it is this recent; older ones skip to the next time
BRIEF_GAP_SECONDS = 20                     # chats of one run start this far apart (five films at once would crowd the render queue)
_lock = threading.RLock()
_running: set[str] = set()                 # task ids with a run being started now

router = APIRouter(prefix="/scheduled", tags=["scheduled"])


# ── model ────────────────────────────────────────────────────────────────────

class Schedule(BaseModel):
    kind: Literal["hourly", "daily", "weekdays", "weekly", "once"] = "daily"
    time: str = Field(default="09:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    every_hours: int = Field(default=1, ge=1, le=12)                 # hourly
    weekday: int = Field(default=0, ge=0, le=6)                      # weekly: 0 = Saturday … 6 = Friday
    date: str = Field(default="", pattern=r"^(\d{4}-\d{2}-\d{2})?$")  # once (Gregorian, Iran time)


class Source(BaseModel):
    file_id: str = Field(min_length=3, max_length=200)         # a library file ("att:<attachment id>", an output, …): attached to each run's chat
    name: str = Field(default="", max_length=300)
    kind: str = Field(default="", max_length=20)


class TaskIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    instructions: str = Field(min_length=3, max_length=6000)
    engine: Literal["lite", "medium", "pro"] = "lite"
    per_run: int = Field(default=1, ge=1, le=5)
    research: bool = False
    schedule: Schedule = Field(default_factory=Schedule)
    status: Literal["active", "paused"] = "active"
    sources: list[Source] = Field(default_factory=list, max_length=60)
    source_use: Literal["rotate", "all"] = "rotate"            # rotate: the next unused file(s) each video; all: every file in every video


class TaskPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    instructions: str | None = Field(default=None, min_length=3, max_length=6000)
    engine: Literal["lite", "medium", "pro"] | None = None
    per_run: int | None = Field(default=None, ge=1, le=5)
    research: bool | None = None
    schedule: Schedule | None = None
    status: Literal["active", "paused"] | None = None
    sources: list[Source] | None = Field(default=None, max_length=60)
    source_use: Literal["rotate", "all"] | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value else None


def _parse(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def next_run(schedule: dict, after: datetime) -> datetime | None:
    """The first run time strictly after `after` (UTC in, UTC out); None for a one-off date already past."""
    s = Schedule(**schedule)
    hour, minute = (int(x) for x in s.time.split(":"))
    local = after.astimezone(IRAN)
    if s.kind == "once":
        if not s.date:
            return None
        y, m, d = (int(x) for x in s.date.split("-"))
        at = datetime(y, m, d, hour, minute, tzinfo=IRAN)
        return at.astimezone(timezone.utc) if at > local else None
    if s.kind == "hourly":
        # Every N hours on the given minute, counted from midnight so the times stay the same each day (every 3 h at :15 → 00:15, 03:15, …).
        day = local.replace(hour=0, minute=minute, second=0, microsecond=0)
        for step in range(0, 48 * 60 // max(1, s.every_hours) + 2):
            at = day + timedelta(hours=step * s.every_hours)
            if at > local:
                return at.astimezone(timezone.utc)
        return None
    at = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    for _ in range(15):
        if at > local:
            weekday = (at.weekday() + 2) % 7                  # Python Monday=0 → Iran Saturday=0
            if s.kind == "daily" or (s.kind == "weekdays" and weekday <= 4) or (s.kind == "weekly" and weekday == s.weekday):
                return at.astimezone(timezone.utc)
        at += timedelta(days=1)
    return None


# ── storage ──────────────────────────────────────────────────────────────────

def _file(user: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,120}", user):
        raise HTTPException(400, "bad user")
    return ROOT / f"{user}.json"


def _load(user: str) -> list[dict]:
    path = _file(user)
    with _lock:
        if not path.is_file():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("tasks", [])
        except Exception:
            log.exception("scheduled tasks file unreadable: %s", path)
            return []


def _save(user: str, tasks: list[dict]) -> None:
    path = _file(user)
    with _lock:
        ROOT.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"tasks": tasks}, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)


def _mutate(user: str, task_id: str, change) -> dict:
    """Load, change one task in place (change(task) may return a value), save; returns the task."""
    with _lock:
        tasks = _load(user)
        task = next((t for t in tasks if t["id"] == task_id), None)
        if task is None:
            raise KeyError(task_id)
        change(task)
        task["updated_at"] = _iso(_now())
        _save(user, tasks)
        return task


def _users() -> list[str]:
    if not ROOT.is_dir():
        return []
    return [p.stem for p in ROOT.glob("*.json")]


# ── running ──────────────────────────────────────────────────────────────────

BRIEFS = """You plan one run of a person's scheduled video task for EditorGPT, a Persian AI video studio. The task's instruction says what to make each time.
Return strict JSON: {"briefs": [{"title": "<short Persian chat title, max 60 chars>", "prompt": "<the complete request for the studio, in Persian>"}]}
with exactly N briefs (N is given).
Rules:
- Each prompt is a complete, standalone request the studio can act on with no questions: the video type, the exact topic/angle, key facts and numbers to
  use, the tone and length, aspect ratio, and anything the instruction fixes (brand, call to action, style). Keep every fact, name, number and link the
  person wrote.
- When N > 1, every brief is about a DIFFERENT subject (a different news story, fact, product or idea), not different angles of one subject — unless the instruction itself names a single subject. With FRESH SOURCES, use a different story for each brief. Never repeat a topic from RECENT RUNS.
- When FRESH SOURCES are given, build the briefs on them (today's news or facts), name the facts concretely, and never invent facts or numbers.
- Write the prompt as the person would talk to the studio ("یک موشن‌گرافیک ۴۰ ثانیه‌ای عمودی بساز درباره‌ی ..."). No markdown."""

AUTO_NOTE = ("(این درخواست از یک «کار زمان‌بندی‌شده» می‌آید و کسی منتظر پاسخ نیست: سؤال نپرس، خودت تصمیم بگیر و کار را تا خروجی نهایی کامل بساز.)\n\n")


def _briefs(task: dict, user: str, recent: list[str]) -> list[dict]:
    """This run's briefs (blocking: model calls). Falls back to the instruction itself when planning fails."""
    from brain.lm_gateway import work_scope
    n = int(task.get("per_run") or 1)
    fallback = [{"title": task["name"][:60] + (f" · {i + 1}" if n > 1 else ""),
                 "prompt": task["instructions"] + (f"\n\n(نسخه‌ی {i + 1} از {n}: موضوع یا زاویه‌ای متفاوت از بقیه انتخاب کن.)" if n > 1 else "")}
                for i in range(n)]
    with work_scope("scheduled", task["id"], user=user):
        sources = []
        if task.get("research"):
            try:
                from brain.lm_gateway import search
                sources = search(task["instructions"][:380], count=10)
                if int(task.get("per_run") or 1) > 1:          # one search tends to return one big story: ask once more for other recent ones
                    try:
                        more = search("other recent news and developments, different stories: " + task["instructions"][:330], count=10)
                        seen = {x.get("url") for x in sources}
                        sources += [x for x in more if x.get("url") not in seen]
                    except Exception:
                        pass
            except Exception as exc:
                log.warning("scheduled task %s: web search failed (%s)", task["id"], str(exc)[:160])
        today = _now().astimezone(IRAN).strftime("%Y-%m-%d")
        parts = [f"N = {n}", f"TODAY (Iran): {today}", "INSTRUCTION:\n" + task["instructions"]]
        if task.get("sources"):
            parts.append("Each video gets the person's own source file(s) attached to its chat (" +
                         ("a different file for each video" if task.get("source_use", "rotate") == "rotate" else "the same files every time") +
                         "): write each prompt as a request to make the video FROM the attached file, without inventing its content.")
        if recent:
            parts.append("RECENT RUNS (do not repeat these topics):\n" + "\n".join("- " + t for t in recent[-40:]))
        if sources:
            parts.append("FRESH SOURCES:\n" + "\n\n".join(f"[{i + 1}] {s.get('title', '')}\n{s.get('url', '')}\n{str(s.get('content', ''))[:900]}"
                                                       for i, s in enumerate(sources)))
        try:
            from brain.llm import gateway_json
            out, _ = gateway_json(BRIEFS, "\n\n".join(parts), route="engine_advisor", max_tokens=6000)
            rows = [b for b in (out.get("briefs") or []) if isinstance(b, dict) and str(b.get("prompt", "")).strip()]
            if rows:
                rows = (rows + fallback)[:n]
                return [{"title": str(b.get("title") or task["name"])[:60].strip() or task["name"][:60], "prompt": str(b["prompt"]).strip()[:11000]}
                        for b in rows]
        except Exception as exc:
            log.warning("scheduled task %s: planning failed, using the instruction (%s)", task["id"], str(exc)[:160])
    return fallback


async def _api(user: str, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    """Call the app's own API as the person (a short-lived access token), on this same process."""
    import httpx
    from app import auth
    from app.config import settings
    host = (settings.ALLOWED_HOSTS.split(",")[0].strip() or "localhost")
    token = auth._create_access_token(user, "", "")
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=60) as client:
        response = await client.request(method, path, json=body, headers={"Authorization": f"Bearer {token}", "Host": host})
    try:
        data = response.json()
    except Exception:
        data = {"detail": response.text[:300]}
    return response.status_code, data if isinstance(data, dict) else {"data": data}


def _error_text(status: int, data: dict) -> str:
    detail = data.get("detail")
    if isinstance(detail, dict):
        detail = detail.get("message") or detail.get("detail") or json.dumps(detail, ensure_ascii=False)
    text = str(detail or data)[:300]
    if status == 402:
        return "اعتبار کافی نیست: " + text
    return f"{status}: {text}"


async def run_task(user: str, task_id: str, trigger: str = "schedule") -> dict | None:
    """Start one run: plan the briefs, then open one new chat per brief. Returns the run record (or None when the task is gone / already starting)."""
    key = f"{user}:{task_id}"
    if key in _running:
        return None
    _running.add(key)
    run = {"id": uuid.uuid4().hex[:12], "at": _iso(_now()), "trigger": trigger, "status": "preparing", "items": [], "error": ""}
    try:
        def add(task):
            task.setdefault("runs", []).insert(0, run)
            del task["runs"][MAX_RUNS_KEPT:]
            task["last_run_at"] = run["at"]
        task = _mutate(user, task_id, add)
        recent = [i.get("title", "") for r in task.get("runs", [])[1:] for i in r.get("items", [])]
        sources = list(task.get("sources") or [])
        rotate = task.get("source_use", "rotate") == "rotate" and bool(sources)
        cursor = int(task.get("source_cursor") or 0)
        if rotate and cursor >= len(sources):
            raise RuntimeError("همه‌ی فایل‌های منبع این کار استفاده شده‌اند؛ از صفحه‌ی کار فایل تازه اضافه کنید یا «استفاده‌ی دوباره از اول» را بزنید.")
        if rotate:                                        # never more videos than unused files
            task = dict(task, per_run=min(int(task.get("per_run") or 1), len(sources) - cursor))
        briefs = await asyncio.to_thread(_briefs, task, user, recent)
        items, error = [], ""
        for index, brief in enumerate(briefs):
            if index:
                await asyncio.sleep(BRIEF_GAP_SECONDS)
            item = {"title": brief["title"], "prompt": brief["prompt"][:600], "conversation_id": "", "status": "starting", "error": ""}
            status, data = await _api(user, "POST", "/studio/conversations", {"title": brief["title"]})
            if status >= 300:
                item.update(status="failed", error=_error_text(status, data)); items.append(item); error = item["error"]; break
            item["conversation_id"] = data.get("id", "")
            attachment_ids, used = [], []
            chosen = [sources[cursor]] if rotate else (sources if sources else [])
            for source in chosen:
                code, attached = await _api(user, "POST", f"/studio/conversations/{item['conversation_id']}/attachments/library", {"file_id": source["file_id"]})
                if code < 300 and attached.get("id"):
                    attachment_ids.append(attached["id"]); used.append(source.get("name") or source["file_id"])
            if chosen and not attachment_ids:
                item.update(status="failed", error="فایل منبع پیدا نشد (شاید حذف شده باشد): " + (chosen[0].get("name") or chosen[0]["file_id"]))
                items.append(item); error = item["error"]
                if rotate:
                    cursor += 1
                continue
            if rotate:
                cursor += 1
                def advance_cursor(task, cursor=cursor):
                    task["source_cursor"] = cursor
                _mutate(user, task_id, advance_cursor)
            item["sources"] = used
            status, data = await _api(user, "POST", f"/studio/conversations/{item['conversation_id']}/messages",
                                      {"content": AUTO_NOTE + brief["prompt"], "agent_mode": task.get("engine") or "lite", "attachment_ids": attachment_ids,
                                       "execution_mode": "auto", "render_target": "server"})
            if status >= 300:
                item.update(status="failed", error=_error_text(status, data)); items.append(item); error = item["error"]
                if status in (402, 503):
                    break
                continue
            item["status"] = "running"
            items.append(item)
            def save_items(task, items=list(items)):
                for r in task.get("runs", []):
                    if r["id"] == run["id"]:
                        r.update(items=items, status="running")
            _mutate(user, task_id, save_items)
        def finish(task):
            for r in task.get("runs", []):
                if r["id"] == run["id"]:
                    r.update(items=items, status="failed" if items and all(i["status"] == "failed" for i in items) else "running", error=error)
        task = _mutate(user, task_id, finish)
        return next((r for r in task.get("runs", []) if r["id"] == run["id"]), run)
    except KeyError:
        return None
    except Exception as exc:
        log.exception("scheduled task %s run failed", task_id)
        try:
            def fail(task):
                for r in task.get("runs", []):
                    if r["id"] == run["id"]:
                        r.update(status="failed", error=str(exc)[:300])
            _mutate(user, task_id, fail)
        except KeyError:
            pass
        return run
    finally:
        _running.discard(key)


_FINAL = {"done", "failed"}
# Answers the autopilot gives to the studio's own questions in a scheduled chat, in order of preference: approve, then «without it» / defaults
# (never «use the attached file», there is none).
_PREFERRED = ("approve", "skip", "none", "off", "default", "natural", "original", "minimal", "existing")


async def _autopilot(user: str, item: dict) -> bool:
    """Nobody is there to press the buttons in a scheduled run: answer the studio's questions, confirm its actions, approve its plans and pick the
    recommended look, through the same endpoints the buttons use. Each gate is handled once (remembered in item["auto"]). True if it acted."""
    from app.studio_store import repo
    cid = item["conversation_id"]
    done = set(item.get("auto") or [])
    acted = False
    try:
        conversation = await repo.get_conversation(cid, user, message_limit=1)
    except Exception:
        return False
    state = conversation.get("state") or {}
    session = state.get("manual_session")
    if session and session.get("question_id") and f"q:{session['question_id']}" not in done:
        from app.studio_manual import question
        spec = question(session)
        values = [c["value"] for c in spec.get("choices") or [] if c.get("value") != "attached"]
        pick = next((v for v in _PREFERRED if v in values), values[0] if values else "پیش‌فرض")
        code, _ = await _api(user, "POST", f"/studio/conversations/{cid}/messages",
                             {"content": pick, "manual_question_id": session["question_id"], "execution_mode": "auto", "render_target": "server"})
        done.add(f"q:{session['question_id']}"); acted = code < 300
    for action in conversation.get("actions") or []:
        if action.get("status") == "pending" and f"a:{action['id']}" not in done:
            code, _ = await _api(user, "POST", f"/studio/actions/{action['id']}/confirm")
            done.add(f"a:{action['id']}"); acted = acted or code < 300
    from app import creative_plan
    for project in conversation.get("projects") or []:
        pstate = project.get("state") or {}
        version = creative_plan.current(pstate)
        if pstate.get("workflow") == "awaiting_approval" and version and f"p:{version['id']}" not in done:
            code, _ = await _api(user, "POST", f"/studio/projects/{project['id']}/plan/approve", {"version_id": version["id"]})
            done.add(f"p:{version['id']}"); acted = acted or code < 300
        question_ = pstate.get("design_question")
        if question_ and not pstate.get("design_resolved") and f"d:{project['id']}" not in done:
            code, _ = await _api(user, "POST", f"/studio/projects/{project['id']}/design-choice", {"choice": str(question_.get("recommended") or "")})
            done.add(f"d:{project['id']}"); acted = acted or code < 300
    if acted or done != set(item.get("auto") or []):
        item["auto"] = sorted(done)
    return acted


async def _item_status(user: str, conversation_id: str) -> tuple[str, str | None]:
    """done / failed / needs_you / running for one chat, plus the id of a Medium run waiting for plan approval."""
    from app.studio_store import repo
    from app.agents import store as agent_store
    try:
        conversation = await repo.get_conversation(conversation_id, user)
        runs = await agent_store.runs(conversation_id, user)
    except Exception:
        return "failed", None
    projects = conversation.get("projects") or []
    waiting = next((r["id"] for r in runs if r.get("status") == "waiting_approval"), None)
    states = [str(p.get("status") or "") for p in projects]
    if any(s in {"completed", "done", "ready", "succeeded"} for s in states):
        return "done", None
    active = [r for r in runs if r.get("status") in {"queued", "running", "waiting_job"}]
    if waiting:
        return "needs_you", waiting
    if any(s in {"running", "planning", "rendering", "queued"} for s in states) or active:
        return "running", None
    if any(s in {"awaiting_confirmation", "awaiting_input", "needs_input"} for s in states):
        return "needs_you", None
    if states and all(s in {"failed", "error", "cancelled", "canceled"} for s in states):
        return "failed", None
    if runs and all(r.get("status") in {"completed", "failed", "cancelled"} for r in runs):
        return ("done" if any(r.get("status") == "completed" for r in runs) else "failed"), None
    return "running", None


async def _refresh(user: str, task: dict, *, approve: bool = False) -> bool:
    """Update the status of the recent runs' chats (and approve a waiting Medium plan: nobody is there to press the button). True if anything changed."""
    changed = False
    horizon = _now() - timedelta(days=3)
    for run in task.get("runs", [])[:10]:
        if run.get("status") in _FINAL or (_parse(run.get("at")) or _now()) < horizon:
            continue
        for item in run.get("items", []):
            if item.get("status") in _FINAL or not item.get("conversation_id"):
                continue
            if approve:
                before = list(item.get("auto") or [])
                if await _autopilot(user, item) or list(item.get("auto") or []) != before:
                    changed = True
            status, waiting = await _item_status(user, item["conversation_id"])
            if waiting and approve:
                code, _ = await _api(user, "POST", f"/studio/agent-runs/{waiting}/resume", {"decision": "approve"})
                if code < 300:
                    status = "running"
            if status != item.get("status"):
                item["status"] = status
                changed = True
        states = [i.get("status") for i in run.get("items", [])]
        if states and all(s in _FINAL for s in states) and run.get("status") != "preparing":
            final = "done" if all(s == "done" for s in states) else ("failed" if all(s == "failed" for s in states) else "partial")
            if run.get("status") != final:
                run["status"] = final
                changed = True
    return changed


async def _tick() -> None:
    now = _now()
    for user in _users():
        for task in _load(user):
            try:
                if task.get("status") == "active":
                    due = _parse(task.get("next_run_at"))
                    if due and due <= now:
                        late = now - due
                        following = next_run(task["schedule"], now)
                        def advance(t, following=following):
                            t["next_run_at"] = _iso(following)
                            if following is None and t["schedule"].get("kind") == "once":
                                t["status"] = "paused"
                        _mutate(user, task["id"], advance)
                        if late <= MISSED_GRACE:
                            asyncio.create_task(run_task(user, task["id"], "schedule"))
                        else:
                            log.info("scheduled task %s: skipped a run missed by %s", task["id"], late)
                if any(r.get("status") not in _FINAL for r in task.get("runs", [])[:10]):
                    fresh = next((t for t in _load(user) if t["id"] == task["id"]), None)
                    if fresh and await _refresh(user, fresh, approve=True):
                        def keep_runs(t, runs=fresh.get("runs", [])):
                            by_id = {r["id"]: r for r in runs}
                            t["runs"] = [by_id.get(r["id"], r) for r in t.get("runs", [])]
                        _mutate(user, task["id"], keep_runs)
            except KeyError:
                continue
            except Exception:
                log.exception("scheduled task tick failed for %s", task.get("id"))


async def scheduler_loop() -> None:
    """Started from the app's lifespan (one worker process). Never raises."""
    await asyncio.sleep(20)                    # let the app finish starting
    while True:
        try:
            await _tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("scheduler tick failed")
        await asyncio.sleep(TICK_SECONDS)


# ── credits per chat (for the run history) ───────────────────────────────────

async def _credits_by_chat(user: str, ids: list[str]) -> dict[str, int]:
    ids = [i for i in ids if i]
    if not ids:
        return {}
    try:
        from sqlalchemy import bindparam, text
        from app.credits import _session
        query = text("select conversation_id, sum(-amount) from credit_ledger where kind='usage' and user_id=:u and conversation_id in :ids group by 1") \
            .bindparams(bindparam("ids", expanding=True))
        async with _session() as db:
            rows = (await db.execute(query, {"u": str(user), "ids": ids})).all()
        return {str(c): int(s or 0) for c, s in rows}
    except Exception:
        log.exception("credit lookup for scheduled runs failed")
        return {}


# ── HTTP ─────────────────────────────────────────────────────────────────────

def _owner(request: Request) -> str:
    return str(request.state.user.id)


def _summary(task: dict) -> dict:
    last = (task.get("runs") or [None])[0]
    return {k: task.get(k) for k in ("id", "name", "instructions", "engine", "per_run", "research", "schedule", "status", "created_at", "updated_at",
                                     "next_run_at", "last_run_at", "sources", "source_use")} | {"source_cursor": int(task.get("source_cursor") or 0)} | {"last_run": {"at": last["at"], "status": last["status"]} if last else None,
                                                                      "runs_count": len(task.get("runs") or [])}


@router.get("/tasks")
async def list_tasks(request: Request):
    tasks = _load(_owner(request))
    return {"tasks": [_summary(t) for t in sorted(tasks, key=lambda t: t.get("created_at") or "", reverse=True)]}


@router.post("/tasks", status_code=201)
async def create_task(request: Request, body: TaskIn):
    user = _owner(request)
    with _lock:
        tasks = _load(user)
        if len(tasks) >= MAX_TASKS:
            raise HTTPException(409, f"حداکثر {MAX_TASKS} کار زمان‌بندی‌شده می‌توانید داشته باشید.")
        stamp = _iso(_now())
        task = body.model_dump() | {"id": uuid.uuid4().hex[:12], "created_at": stamp, "updated_at": stamp, "last_run_at": None, "runs": []}
        task["next_run_at"] = _iso(next_run(task["schedule"], _now())) if task["status"] == "active" else None
        if task["schedule"]["kind"] == "once" and not task["next_run_at"] and task["status"] == "active":
            raise HTTPException(422, "زمان این اجرای یک‌باره گذشته است.")
        tasks.append(task)
        _save(user, tasks)
    return _summary(task)


@router.get("/tasks/{task_id}")
async def get_task(request: Request, task_id: str):
    user = _owner(request)
    task = next((t for t in _load(user) if t["id"] == task_id), None)
    if task is None:
        raise HTTPException(404, "not found")
    if await _refresh(user, task):
        try:
            _mutate(user, task_id, lambda t: t.update(runs=task.get("runs", [])))
        except KeyError:
            pass
    credits = await _credits_by_chat(user, [i.get("conversation_id") for r in task.get("runs", [])[:20] for i in r.get("items", [])])
    runs = []
    for run in task.get("runs", []):
        items = [i | {"credits": credits.get(i.get("conversation_id") or "", 0)} for i in run.get("items", [])]
        runs.append(run | {"items": items, "credits": sum(i["credits"] for i in items)})
    return _summary(task) | {"runs": runs, "running_now": f"{user}:{task_id}" in _running}


@router.patch("/tasks/{task_id}")
async def update_task(request: Request, task_id: str, body: TaskPatch):
    user = _owner(request)
    patch = body.model_dump(exclude_none=True)
    reset = request.query_params.get("reset_sources") == "1"
    def change(task):
        if "sources" in patch and [s["file_id"] for s in patch["sources"]] != [s["file_id"] for s in task.get("sources") or []]:
            task["source_cursor"] = 0                    # a changed file list starts again from its first file
        if reset:
            task["source_cursor"] = 0
        task.update(patch)
        task["next_run_at"] = _iso(next_run(task["schedule"], _now())) if task["status"] == "active" else None
    try:
        task = _mutate(user, task_id, change)
    except KeyError:
        raise HTTPException(404, "not found")
    return _summary(task)


@router.delete("/tasks/{task_id}")
async def delete_task(request: Request, task_id: str):
    user = _owner(request)
    with _lock:
        tasks = _load(user)
        left = [t for t in tasks if t["id"] != task_id]
        if len(left) == len(tasks):
            raise HTTPException(404, "not found")
        _save(user, left)
    return {"ok": True}


@router.post("/tasks/{task_id}/run", status_code=202)
async def run_now(request: Request, task_id: str):
    user = _owner(request)
    if not any(t["id"] == task_id for t in _load(user)):
        raise HTTPException(404, "not found")
    from app import credits
    await credits.gate(user)
    if f"{user}:{task_id}" in _running:
        raise HTTPException(409, "این کار همین الان در حال شروع است.")
    asyncio.create_task(run_task(user, task_id, "manual"))
    return {"ok": True}


ASSIST = """You are EditorGPT's assistant, setting up a SCHEDULED TASK with the person in a chat. Talk like a capable colleague in natural, short Persian:
understand what they want, ask only what you really need, suggest good defaults, and never run a rigid questionnaire.

What a scheduled task is: on its schedule (Iran time) it opens new studio chats that each make one finished video from the task's instruction, with no one
there to answer questions; outputs also reach the person's Telegram if linked. Before each run a planner picks distinct topics (and can search the web).

What each kind of video NEEDS — make sure the task will have it, or it cannot run:
- Talking reel / edited reel from the person's own footage (ریلز صحبتی، تدوین ویدیوی خودم): their recorded videos. A scheduled task can only use files it
  is given: ask them to attach the videos here in the chat (the + button), or pick from their earlier files listed below; one video is used per output
  (a pool that is consumed), or the same file every time. Also: the speaker's name/title shown on screen, style, subtitles, music.
- Dubbing / Persian localization (دوبله، فارسی‌سازی) and clips from a long video (کلیپ از ویدیوی بلند): the source videos, same way.
- Product ad (تبلیغ محصول): the product page link(s) or product photos, price/offer, call to action, brand.
- Motion graphic / kinetic typography / Vox-style documentary / story / brand intro: a subject is enough. Ask about the area or topic, the angle, the
  audience, length (default 30-60 s), vertical 9:16 by default, brand name/handle and call to action if they want one, and whether it should use fresh news
  (web research).
Engines: lite = fast and cheap, right for nearly everything above; medium = multi-step work that checks and measures first; pro = strongest and costly,
for custom or research-heavy films. Suggest lite unless the work needs more. Videos per run: 1-5.

Files: the person may attach files in this chat (listed under FILES ATTACHED IN THIS CHAT) or you may offer files from their library (EARLIER FILES).
Put the ones the task should use in draft.sources as {"file_id", "name", "kind"} exactly as listed, and set draft.source_use to "rotate" (a different
file for each video; the task stops when they run out) or "all" (every file in every video, e.g. a logo or intro clip).

Each turn return strict JSON:
{"reply": "<your message: what you understood, a suggestion, and AT MOST one question; plain Persian, no markdown headings>",
 "options": [{"label": "<short quick answer>", "detail": "<one line>"}],
 "draft": null or {"name": "...", "instructions": "<complete Persian instruction for each video: type, subject/angle, facts the person gave, tone,
            length, aspect, brand, call to action, how to use the source file>", "engine": "lite|medium|pro", "per_run": 1-5, "research": true|false,
            "schedule": {"kind": "hourly|daily|weekdays|weekly|once", "time": "HH:MM", "every_hours": 1-12, "weekday": 0-6 (0 = Saturday), "date": "YYYY-MM-DD or empty"},
            "sources": [...], "source_use": "rotate|all"}}
- options: 0-4 quick answers ONLY when the question has natural short answers (never for open questions like a topic or a link). The person can always type.
- Return a draft only when everything the task needs is known (including the source files for footage-based work); the reply then summarizes it in one or
  two sentences and asks for confirmation (the chat shows the create buttons). After a change request, return the updated draft.
- Never invent the person's facts, links, names or files. Never claim the task is already created. Weekdays = Saturday to Wednesday."""


class AssistIn(BaseModel):
    messages: list[dict] = Field(min_length=1, max_length=40)


def _assist_call(user: str, messages: list[dict], context: str = "") -> dict:
    """One turn of the setup assistant (blocking). Returns {reply, options, draft}; the draft validated against TaskIn (sources only from known files)."""
    from brain.llm import gateway_json
    from brain.lm_gateway import work_scope
    lines = [f"{'PERSON' if m.get('role') == 'user' else 'YOU'}: {str(m.get('content', ''))[:3000]}" for m in messages[-40:]]
    today = _now().astimezone(IRAN).strftime("%Y-%m-%d %H:%M (%A)")
    with work_scope("scheduled", "assist", user=user):
        out = gateway_json(ASSIST, f"NOW (Iran): {today}\n{context}\n\nCONVERSATION:\n" + "\n".join(lines), route="engine_advisor", max_tokens=3500)[0]
    draft = out.get("draft") if isinstance(out.get("draft"), dict) else None
    if draft:
        try:
            draft = TaskIn(**{k: v for k, v in draft.items() if k in TaskIn.model_fields}).model_dump()
        except Exception:
            log.warning("setup draft rejected: %s", json.dumps(draft, ensure_ascii=False)[:300])
            draft = None
    options = [{"label": str(o.get("label", ""))[:80], "detail": str(o.get("detail", ""))[:200]}
               for o in (out.get("options") or [])[:4] if isinstance(o, dict) and o.get("label")] if not draft else []
    return {"reply": str(out.get("reply", "")).strip()[:2500], "options": options, "draft": draft}


@router.post("/assist")
async def assist(request: Request, body: AssistIn):
    user = _owner(request)
    from app import credits
    await credits.gate(user)
    try:
        return await asyncio.to_thread(_assist_call, user, body.messages)
    except Exception as exc:
        raise HTTPException(502, "دستیار پاسخ نداد؛ دوباره امتحان کنید. " + str(exc)[:120])


# ── setup inside a Studio chat ("ساخت با هوش مصنوعی") ───────────────────────
# The chat's state carries {"scheduled_setup": {"history", "options", "draft", "files", "busy"}}. While it is there, the chat's messages go to the setup
# assistant instead of the engines (app/routers/studio.py send_message); its quick answers / create buttons show as the chat's option card.

SETUP_SEED = "می‌خواهم یک کار زمان‌بندی‌شده بسازم که خودش طبق برنامه ویدیو بسازد."
CREATE, CREATE_PAUSED = "__create__", "__create_paused__"
ENGINE_FA = {"lite": "Lite", "medium": "Medium", "pro": "Pro"}
DAYS_FA = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]


def _fa(value) -> str:
    return str(value).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def describe(schedule: dict) -> str:
    s = Schedule(**schedule)
    at = f"ساعت {_fa(s.time)}"
    return {"hourly": f"هر {_fa(s.every_hours)} ساعت، دقیقه‌ی {_fa(s.time[3:])}" if s.every_hours > 1 else f"هر ساعت، دقیقه‌ی {_fa(s.time[3:])}",
            "daily": f"هر روز {at}", "weekdays": f"روزهای کاری (شنبه تا چهارشنبه) {at}", "weekly": f"هر {DAYS_FA[s.weekday]} {at}",
            "once": f"یک‌بار، {_fa(s.date)} {at}"}[s.kind]


def setup_question(state: dict) -> dict | None:
    """The chat's option card for the current setup turn (ManualQuestion shape), or None."""
    setup = state.get("scheduled_setup")
    if not isinstance(setup, dict) or setup.get("busy"):
        return None
    turn = len(setup.get("history") or [])
    draft = setup.get("draft")
    if draft:
        files = draft.get("sources") or []
        lines = [f"زمان اجرا: {describe(draft['schedule'])} (به وقت ایران)",
                 f"موتور {ENGINE_FA.get(draft['engine'], draft['engine'])} · {_fa(draft['per_run'])} ویدیو در هر اجرا" + (" · با جست‌وجوی تازه در وب" if draft.get("research") else "")]
        if files:
            lines.append(f"فایل‌های منبع: {_fa(len(files))} فایل" + (" (هر ویدیو یک فایل تازه)" if draft.get("source_use") == "rotate" else " (همه در هر ویدیو)"))
        return {"id": f"sched-{turn}", "key": "scheduled", "title": f"«{draft['name']}»", "input": True,
                "description": "\n".join(lines), "summary": draft["instructions"],
                "choices": [{"value": CREATE, "label": "بساز و فعال کن", "description": "طبق زمان‌بندی خودکار اجرا می‌شود"},
                            {"value": CREATE_PAUSED, "label": "بساز ولی فعلاً متوقف بماند", "description": "بعداً از صفحه‌ی کار فعالش کنید"}]}
    options = setup.get("options") or []
    if not options:
        return None
    return {"id": f"sched-{turn}", "key": "scheduled", "title": "پاسخ سریع", "input": True,
            "choices": [{"value": o["label"] + (f" ({o['detail']})" if o.get("detail") else ""), "label": o["label"], "description": o.get("detail", "")}
                        for o in options]}


async def _say(cid: str, user: str, text: str) -> None:
    from app.studio_store import repo
    response_id = f"response:sched:{uuid.uuid4().hex[:8]}"
    await repo.emit(cid, "assistant.response.started", {"response_id": response_id})
    saved = await repo.add_message(cid, user, "assistant", text)
    await repo.emit(cid, "assistant.response.completed", {"response_id": response_id, "text": text, "message_id": saved["id"]})


async def _set_setup(cid: str, user: str, setup: dict | None) -> None:
    from app.studio_store import repo
    conversation = await repo.get_conversation(cid, user)
    await repo.set_conversation(cid, user, state={**(conversation.get("state") or {}), "scheduled_setup": setup})


def _base_url() -> str:
    from app.config import settings
    return "https://" + (settings.ALLOWED_HOSTS.split(",")[0].strip() or "editor.rafiei.co")


async def _context(user: str, setup: dict) -> str:
    """What the assistant should know besides the chat: files attached here, the person's recent library files, their brand profile."""
    parts = []
    files = setup.get("files") or []
    if files:
        parts.append("FILES ATTACHED IN THIS CHAT:\n" + "\n".join(f"- file_id={f['file_id']} kind={f.get('kind', '')} name={f.get('name', '')}" for f in files))
    try:
        from app import studio_files
        library = (await studio_files.library(user)).get("files") or []
        attached = {f["file_id"] for f in files}
        recent = [f for f in library if f.get("kind") == "video" and f.get("id") not in attached][:15]
        if recent:
            parts.append("EARLIER FILES (the person's library, newest first; offer them only when footage is needed):\n" +
                         "\n".join(f"- file_id={f['id']} kind={f['kind']} name={f.get('name', '')} from_chat={f.get('conversation_title', '')}" for f in recent))
    except Exception:
        log.exception("library for scheduled setup")
    try:
        from app import brand_profile
        profile = await asyncio.to_thread(brand_profile.load, user)
        known = {k: profile.get(k) for k in ("name", "tagline", "cta") if profile.get(k)}
        if known:
            parts.append("BRAND PROFILE (saved by the person; use as defaults, confirm briefly): " + json.dumps(known, ensure_ascii=False)[:600])
    except Exception:
        pass
    return "\n\n".join(parts)


async def _setup_answer(cid: str, user: str) -> None:
    """Background: the assistant's next turn in a setup chat."""
    try:
        from app.studio_store import repo
        conversation = await repo.get_conversation(cid, user)
        setup = dict((conversation.get("state") or {}).get("scheduled_setup") or {})
        try:
            context = await _context(user, setup)
            out = await asyncio.to_thread(_assist_call, user, setup.get("history") or [], context)
        except Exception as exc:
            log.warning("scheduled setup turn failed: %s", str(exc)[:200])
            await _set_setup(cid, user, {**setup, "busy": False})
            await _say(cid, user, "دستیار الان پاسخ نداد؛ لطفاً پیامتان را دوباره بفرستید.")
            return
        known = {f["file_id"] for f in setup.get("files") or []}
        if out["draft"] and out["draft"].get("sources"):
            # Only files the person attached here or that were offered from their library (the validated ids) are kept.
            try:
                from app import studio_files
                library = {f["id"] for f in (await studio_files.library(user)).get("files") or []}
            except Exception:
                library = set()
            out["draft"]["sources"] = [f for f in out["draft"]["sources"] if f["file_id"] in known or f["file_id"] in library]
        text = out["reply"] or ("پیش‌نویس آماده است؛ اگر درست است بسازیدش." if out["draft"] else "…")
        history = list(setup.get("history") or []) + [{"role": "assistant", "content": text + (f"\n[DRAFT {json.dumps(out['draft'], ensure_ascii=False)}]" if out["draft"] else "")}]
        await _set_setup(cid, user, {**setup, "history": history, "options": out["options"], "draft": out["draft"], "busy": False})
        await _say(cid, user, text)
    except Exception:
        log.exception("scheduled setup answer failed")


async def setup_message(conversation: dict, user: str, text: str, attachment_ids: list[str] | None = None) -> dict:
    """A message sent in a setup chat (called by send_message instead of dispatching to an engine)."""
    from app.studio_store import repo
    cid = conversation["id"]
    setup = dict((conversation.get("state") or {}).get("scheduled_setup") or {})
    if setup.get("busy"):
        raise HTTPException(409, "دستیار هنوز در حال پاسخ دادن است؛ چند ثانیه صبر کنید.")
    card = setup_question(conversation.get("state") or {})
    label = next((c["label"] for c in (card or {}).get("choices", []) if c["value"] == text), None)
    attachments = await repo.get_attachments(list(attachment_ids or []), cid, user, restore_media=False) if attachment_ids else []
    message = await repo.add_message(cid, user, "user", label or text, [a["id"] for a in attachments])
    files = list(setup.get("files") or []) + [{"file_id": "att:" + a["id"], "name": a.get("filename", ""), "kind": a.get("kind", "")} for a in attachments]
    if setup.get("draft") and text in (CREATE, CREATE_PAUSED):
        draft = dict(setup["draft"]) | {"status": "paused" if text == CREATE_PAUSED else "active"}
        with _lock:
            tasks = _load(user)
            if len(tasks) >= MAX_TASKS:
                await _say(cid, user, f"حداکثر {_fa(MAX_TASKS)} کار زمان‌بندی‌شده می‌توانید داشته باشید؛ یکی را از صفحه‌ی کارهای زمان‌بندی‌شده حذف کنید.")
                return message
            stamp = _iso(_now())
            task = TaskIn(**draft).model_dump() | {"id": uuid.uuid4().hex[:12], "created_at": stamp, "updated_at": stamp, "last_run_at": None, "runs": [],
                                                   "source_cursor": 0, "setup_chat": cid}
            task["next_run_at"] = _iso(next_run(task["schedule"], _now())) if task["status"] == "active" else None
            tasks.append(task)
            _save(user, tasks)
        await _set_setup(cid, user, None)
        first = _parse(task["next_run_at"])
        when = first.astimezone(IRAN).strftime("%Y-%m-%d %H:%M") if first else ""
        done = f"کار «{task['name']}» ساخته شد" + (f" و اولین اجرایش {_fa(when)} به وقت ایران است." if when else "؛ فعلاً متوقف است.")
        await _say(cid, user, done + f"\nهر اجرا در چت‌های تازه انجام می‌شود و تاریخچه‌اش در صفحه‌ی کار هست:\n{_base_url()}/scheduled/{task['id']}")
        return message
    said = label or text
    if attachments:
        said += "\n[فایل پیوست شد: " + "، ".join(f"{a.get('filename', '')} (file_id=att:{a['id']})" for a in attachments) + "]"
    history = list(setup.get("history") or []) + [{"role": "user", "content": said}]
    await _set_setup(cid, user, {**setup, "history": history, "files": files, "options": [], "busy": True})
    asyncio.create_task(_setup_answer(cid, user))
    return message


@router.post("/setup", status_code=201)
async def start_setup(request: Request):
    """Open a new Studio chat that sets up a scheduled task with the assistant."""
    from app.studio_store import repo
    from app import credits
    user = _owner(request)
    await credits.gate(user)
    conversation = await repo.create_conversation(user, "تنظیم کار زمان‌بندی‌شده")
    cid = conversation["id"]
    await repo.add_message(cid, user, "user", SETUP_SEED)
    await repo.set_conversation(cid, user, state={**(conversation.get("state") or {}), "agent_mode": "lite",
                                                  "scheduled_setup": {"history": [{"role": "user", "content": SETUP_SEED}], "options": [], "draft": None,
                                                                      "files": [], "busy": True}})
    asyncio.create_task(_setup_answer(cid, user))
    return {"id": cid}
