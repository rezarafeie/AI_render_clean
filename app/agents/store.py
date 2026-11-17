"""Small user preferences and audited executions in the existing Studio database.

The no-database development fallback uses Studio's existing atomic local store.
No graph binaries, credentials or media are stored in these records.
"""
import copy
import uuid
from datetime import timedelta
from sqlalchemy import select, text, or_
from app import studio_store as s
from app.models import StudioAgentPreference, StudioAgentRun
from app.models import StudioConversation

MODES = {"lite", "medium", "pro"}


def _admit(rows, cid):
    pending = {"queued", "running", "waiting_job", "waiting_approval"}
    if any(r["conversation_id"] == cid and r["status"] in pending for r in rows):
        raise ValueError("Medium در همین گفتگو اجرای ناتمام دارد؛ ابتدا آن را ادامه دهید یا لغو کنید.")
    if sum(r["status"] in pending for r in rows) >= 4:
        raise ValueError("حداکثر چهار اجرای هم‌زمان Medium مجاز است؛ ابتدا یکی از اجراهای قبلی را تمام یا لغو کنید.")
    cutoff = s.now() - timedelta(minutes=1)
    if sum(str(r["data"].get("created_at", r["updated_at"])) > cutoff.isoformat() for r in rows) >= 12:
        raise ValueError("درخواست‌های Medium بیش از حد سریع ارسال شده‌اند؛ کمی بعد دوباره تلاش کنید.")


def validate_mode(mode):
    if mode not in MODES:
        raise ValueError("Unsupported agent mode")
    return mode


def public(row):
    return {"id": row.id, "conversation_id": row.conversation_id, "user_key": row.user_key,
            "message_id": row.message_id, "agent_mode": row.agent_mode, "status": row.status,
            "data": copy.deepcopy(row.data or {}), "updated_at": s.iso(row.updated_at)}


async def preference(user, mode=None):
    if mode is not None: validate_mode(mode)
    if s.DB_AVAILABLE:
        async with s.AsyncSessionLocal() as db:
            row = await db.get(StudioAgentPreference, user)
            if mode is not None:
                if row: row.default_mode = mode
                else: db.add(StudioAgentPreference(user_key=user, default_mode=mode))
                await db.commit()
            return mode or (row.default_mode if row else "lite")
    with s._lock:
        data = s._read(); prefs = data.setdefault("agent_preferences", {})
        if mode is not None:
            prefs[user] = mode; s._write(data)
        return prefs.get(user, "lite")


async def create_run(cid, user, message_id, mode, request):
    validate_mode(mode)
    await s.repo.get_conversation(cid, user)
    value = {"id": uuid.uuid4().hex, "conversation_id": cid, "user_key": user,
             "message_id": str(message_id), "agent_mode": mode, "status": "queued",
             "data": {"request": request, "created_at": s.iso(s.now())}, "updated_at": s.iso(s.now())}
    if s.DB_AVAILABLE:
        async with s.AsyncSessionLocal() as db:
            if mode == "medium":
                # Serialize admission per authenticated user across API processes.
                if db.bind.dialect.name == "postgresql":
                    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": "medium:" + user})
                await db.execute(select(StudioConversation).where(StudioConversation.id == cid).with_for_update())
                rows = (await db.execute(select(StudioAgentRun).where(StudioAgentRun.user_key == user,
                    StudioAgentRun.agent_mode == "medium", or_(StudioAgentRun.status.in_(
                        ["queued", "running", "waiting_job", "waiting_approval"]),
                        StudioAgentRun.updated_at >= s.now() - timedelta(minutes=1))))).scalars()
                _admit([public(row) for row in rows], cid)
            db.add(StudioAgentRun(**{**value, "updated_at": s.now()})); await db.commit()
    else:
        with s._lock:
            data = s._read(); rows = data.setdefault("agent_runs", {})
            if mode == "medium": _admit([r for r in rows.values() if r["user_key"] == user and r["agent_mode"] == mode], cid)
            rows[value["id"]] = value; s._write(data)
    return value


async def get_run(rid, user):
    if s.DB_AVAILABLE:
        async with s.AsyncSessionLocal() as db:
            row = await db.get(StudioAgentRun, rid)
            if not row or row.user_key != user: raise KeyError(rid)
            return public(row)
    with s._lock:
        value = s._read().get("agent_runs", {}).get(rid)
        if not value or value["user_key"] != user: raise KeyError(rid)
        return copy.deepcopy(value)


async def runs(cid, user):
    await s.repo.get_conversation(cid, user)
    if s.DB_AVAILABLE:
        async with s.AsyncSessionLocal() as db:
            rows = (await db.execute(select(StudioAgentRun).where(StudioAgentRun.conversation_id == cid,
                    StudioAgentRun.user_key == user).order_by(StudioAgentRun.updated_at))).scalars()
            return [public(row) for row in rows]
    with s._lock:
        return [copy.deepcopy(r) for r in s._read().get("agent_runs", {}).values()
                if r["conversation_id"] == cid and r["user_key"] == user]


async def update(rid, user, *, status=None, patch=None, claim=None):
    """Compare-and-set claim prevents duplicate deliveries/approvals from executing twice."""
    def change(value):
        if claim is not None and value["status"] not in claim: return None
        if status: value["status"] = status
        value["data"] = {**value["data"], **(patch or {})}
        value["updated_at"] = s.iso(s.now())
        return value
    if s.DB_AVAILABLE:
        async with s.AsyncSessionLocal() as db:
            row = (await db.execute(select(StudioAgentRun).where(StudioAgentRun.id == rid,
                    StudioAgentRun.user_key == user).with_for_update())).scalar_one_or_none()
            if not row: raise KeyError(rid)
            value = change(public(row))
            if value is None: return None
            row.status, row.data, row.updated_at = value["status"], value["data"], s.now()
            await db.commit(); return value
    with s._lock:
        data = s._read(); row = data.get("agent_runs", {}).get(rid)
        if not row or row["user_key"] != user: raise KeyError(rid)
        value = change(row)
        if value is not None: s._write(data)
        return copy.deepcopy(value)


async def claim_pro():
    """The oldest queued Pro run, moved to `running` in the same transaction (one agent worker never gets a run another one took)."""
    if not s.DB_AVAILABLE:
        with s._lock:
            data = s._read(); rows = data.setdefault("agent_runs", {})
            for value in sorted(rows.values(), key=lambda r: r["updated_at"]):
                if value["agent_mode"] == "pro" and value["status"] == "queued":
                    value["status"] = "running"; value["updated_at"] = s.iso(s.now()); s._write(data)
                    return copy.deepcopy(value)
        return None
    async with s.AsyncSessionLocal() as db:
        query = select(StudioAgentRun).where(StudioAgentRun.agent_mode == "pro", StudioAgentRun.status == "queued").order_by(StudioAgentRun.updated_at).limit(1)
        if db.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        row = (await db.execute(query)).scalar_one_or_none()
        if row is None:
            return None
        row.status, row.updated_at = "running", s.now()
        await db.commit()
        return public(row)
