"""Token credits: every person has a balance of weighted tokens and every model call takes from it.

Unit: one input token of Claude Opus = 1 credit. Each model has a weight for input, output, cached-read and cache-write tokens
(output costs more than input, a cache hit costs less), kept in an editable table (administrator page → «اعتبار»).
Media calls that report no tokens (image, speech, video, transcription) cost a flat number of credits per call.

Rules (decided by the owner):
* a NEW request is refused when the balance is not above zero (`require`), with a clear Persian message and a buy button;
* work that is already running is never cut: `charge` always takes the cost, so a balance may dip below zero;
* every new person (and every existing one, on first use) starts with `initial_grant` credits.

All state is in PostgreSQL (credit_accounts / credit_ledger / ...). A balance changes only through one atomic UPDATE ... RETURNING,
and every change has a ledger row that links to the model call (ai_request_logs.id), the chat and the project/video.
"""
from __future__ import annotations

import asyncio
import copy
import logging
import math
import re
import threading
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.database import AsyncSessionLocal, DB_AVAILABLE
from contextlib import asynccontextmanager

from app.models import Base, CreditAccount, CreditLedger, CreditOrder, CreditPackage

log = logging.getLogger(__name__)

DEFAULT_SETTINGS = {
    "initial_grant": 1_000_000,
    "enforce": True,
    # weights: credits per token. 1.0 = one Opus input token. Keys are matched as a substring of the normalised model name (longest wins).
    "weights": {
        "claude_opus": {"in": 1.0, "out": 5.0, "cache": 0.1, "write": 1.25},
        "claude_sonnet": {"in": 0.75, "out": 3.75, "cache": 0.075, "write": 0.94},
        "claude_haiku": {"in": 0.25, "out": 1.25, "cache": 0.025, "write": 0.31},
        "gpt_5": {"in": 0.4, "out": 3.0, "cache": 0.04, "write": 0.4},
        "gpt_4_1_mini": {"in": 0.1, "out": 0.4, "cache": 0.025, "write": 0.1},
        "gpt_4_1": {"in": 0.5, "out": 2.0, "cache": 0.125, "write": 0.5},
        "gemini_pro": {"in": 0.5, "out": 3.0, "cache": 0.125, "write": 0.5},
        "gemini": {"in": 0.1, "out": 0.75, "cache": 0.025, "write": 0.1},
        "deepseek": {"in": 0.035, "out": 0.07, "cache": 0.01, "write": 0.035},
    },
    "default": {"in": 0.5, "out": 2.5, "cache": 0.05, "write": 0.5},
    "per_call": {"image": 10_000, "speech": 3_000, "video": 50_000, "transcription": 3_000, "embeddings": 50, "default": 1_000},
}
DEFAULT_PACKAGES = [
    {"id": "p1", "title": "بستهٔ شروع", "credits": 5_000_000, "price": 0, "currency": "IRT", "active": True, "sort": 1},
    {"id": "p2", "title": "بستهٔ حرفه‌ای", "credits": 20_000_000, "price": 0, "currency": "IRT", "active": True, "sort": 2},
    {"id": "p3", "title": "بستهٔ تیم", "credits": 100_000_000, "price": 0, "currency": "IRT", "active": True, "sort": 3},
]
MEDIA_ENDPOINTS = {"image", "speech", "video", "transcription", "embeddings", "audio"}
KINDS = {"usage", "initial", "grant", "purchase", "admin", "refund"}

USD_PER_CREDIT = 4 / 1_000_000          # one credit = one Opus input token = $4 per million

EXHAUSTED_MESSAGE = "اعتبار شما تمام شده است. برای ادامه، اعتبار بخرید یا افزایش دهید."


class CreditsExhausted(Exception):
    def __init__(self, balance: int):
        super().__init__(EXHAUSTED_MESSAGE)
        self.balance = balance


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── settings (the weights table) ────────────────────────────────────────────

def _blocking(function):
    """asyncio.run() cannot start inside a running event loop (a FastAPI route): run the blocking store call in a helper thread then."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return function()
    box = {}
    def target():
        try: box["value"] = function()
        except BaseException as exc: box["error"] = exc
    thread = threading.Thread(target=target); thread.start(); thread.join()
    if "error" in box: raise box["error"]
    return box["value"]


_cache = {"at": 0.0, "value": None}
_cache_lock = threading.Lock()


def settings(fresh: bool = False) -> dict:
    """The saved settings over the defaults. Read from the AI gateway settings table, cached for 20 s."""
    with _cache_lock:
        if not fresh and _cache["value"] is not None and time.time() - _cache["at"] < 20:
            return _cache["value"]
    saved = {}
    try:
        from app import lm_store
        saved = _blocking(lambda: lm_store.records("settings")).get("credits", {})
    except Exception:
        log.exception("could not read the credit settings; using defaults")
    value = copy.deepcopy(DEFAULT_SETTINGS)
    for key in ("initial_grant", "enforce"):
        if key in saved: value[key] = saved[key]
    for key in ("weights", "per_call"):
        if isinstance(saved.get(key), dict): value[key] = {**value[key], **saved[key]}
    if isinstance(saved.get("default"), dict): value["default"] = {**value["default"], **saved["default"]}
    with _cache_lock:
        _cache.update(at=time.time(), value=value)
    return value


def save_settings(changes: dict) -> dict:
    from app import lm_store
    current = _blocking(lambda: lm_store.records("settings")).get("credits", {})
    _blocking(lambda: lm_store.save("settings", {"credits": {**current, **changes}}))
    return settings(fresh=True)


def normalise(model) -> str:
    text = str(model or "").lower().split("#", 1)[0]
    text = re.sub(r"^(custom|direct|google|openai|anthropic):", "", text)
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def weight_for(model, table: dict | None = None) -> tuple[str, dict]:
    table = table or settings()
    name = normalise(model)
    best = None
    for key in table["weights"]:
        if normalise(key) and normalise(key) in name and (best is None or len(key) > len(best)):
            best = key
    return (best, table["weights"][best]) if best else ("default", table["default"])


def compute(record: dict, table: dict | None = None) -> dict:
    """The cost of one audited call: {"credits": n, "unit": ..., "breakdown": {...}}. Pure; no I/O except the (cached) settings."""
    table = table or settings()
    model = record.get("actual_model") or record.get("requested_model")
    endpoint = str(record.get("endpoint") or "")
    route = str(record.get("route") or "")
    is_media = route in MEDIA_ENDPOINTS or any(endpoint.startswith(prefix) for prefix in ("v1/text-to-speech", "v1/audio", "v1/images", "v1/video", "images", "audio", "video", "embeddings"))
    tin, tout = record.get("input_tokens"), record.get("output_tokens")
    if tin is None and tout is None:
        if record.get("status") != "success":
            return {"credits": 0, "unit": "none", "breakdown": {}}
        kind = "speech" if route == "audio" or "speech" in endpoint else "image" if "image" in route or "image" in endpoint else \
            "transcription" if "transcri" in route or "transcri" in endpoint else "embeddings" if "embedding" in endpoint else \
            "video" if "video" in route and "understanding" not in route else None
        if kind is None and not is_media:
            return {"credits": 0, "unit": "none", "breakdown": {}}
        flat = int(table["per_call"].get(kind or "default", table["per_call"]["default"]))
        return {"credits": flat, "unit": "call", "breakdown": {"per_call": flat, "kind": kind or "default"}}
    key, w = weight_for(model, table)
    tin, tout = int(tin or 0), int(tout or 0)
    read, write = int(record.get("cache_read_tokens") or 0), int(record.get("cache_write_tokens") or 0)
    fresh = max(0, tin - read - write)
    parts = {"in": fresh * w["in"], "out": tout * w["out"], "cache": read * w["cache"], "write": write * w["write"]}
    total = math.ceil(sum(parts.values()))
    return {"credits": total, "unit": "token", "breakdown": {"weights": key, "fresh_in": fresh, "out": tout, "cache_read": read, "cache_write": write,
                                                          **{k: round(v, 2) for k, v in parts.items()}}}


# ── persistence ──────────────────────────────────────────────────────────────

_TABLES = [CreditAccount.__table__, CreditLedger.__table__, CreditPackage.__table__, CreditOrder.__table__]
_schema_ready = False


@asynccontextmanager
async def _session():
    """A database session; the four credit tables are created on first use (CREATE TABLE IF NOT EXISTS, safe from every process and
    safe to roll the app back: no Alembic revision is recorded, so an older image still starts)."""
    global _schema_ready
    if not _schema_ready:
        async with AsyncSessionLocal() as db:
            try:
                connection = await db.connection()
                await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=_TABLES, checkfirst=True))
                await db.commit()
            except Exception:               # another process created them at the same moment
                await db.rollback()
                async with AsyncSessionLocal() as again:
                    connection = await again.connection()
                    await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=_TABLES, checkfirst=True))
                    await again.commit()
        _schema_ready = True
    async with AsyncSessionLocal() as db:
        yield db


def _run(coro):
    return asyncio.run(coro)


def _usable(user_id) -> bool:
    return bool(DB_AVAILABLE and user_id not in (None, "", "local_dev"))


async def _ensure(db, user_id: str) -> CreditAccount:
    row = await db.get(CreditAccount, user_id)
    if row is not None:
        return row
    grant = int(settings()["initial_grant"])
    stamp = now()
    db.add(CreditAccount(user_id=user_id, balance=grant, granted_total=grant, used_total=0, unlimited=False, created_at=stamp, updated_at=stamp))
    db.add(CreditLedger(created_at=stamp, user_id=user_id, kind="initial", amount=grant, balance_after=grant, note="اعتبار اولیه", actor="system"))
    try:
        await db.commit()
    except IntegrityError:                       # another process created it first
        await db.rollback()
    return await db.get(CreditAccount, user_id)


async def apply(user_id: str, amount: int, kind: str, *, fields: dict | None = None) -> int:
    """Change a balance atomically and write the ledger row. Returns the balance after the change."""
    assert kind in KINDS
    user_id = str(user_id); amount = int(amount)
    async with _session() as db:
        await _ensure(db, user_id)
        values = {"balance": CreditAccount.balance + amount, "updated_at": now()}
        if kind == "usage":
            values["used_total"] = CreditAccount.used_total - amount
        elif amount > 0:
            values["granted_total"] = CreditAccount.granted_total + amount
        balance = (await db.execute(update(CreditAccount).where(CreditAccount.user_id == user_id).values(**values)
                                    .returning(CreditAccount.balance))).scalar_one()
        db.add(CreditLedger(created_at=now(), user_id=user_id, kind=kind, amount=amount, balance_after=balance, **(fields or {})))
        await db.commit()
        return int(balance)


def charge(record: dict) -> None:
    """Called for every audited model call: take its cost from the user's balance and write the result into the record
    (credits, credits_balance_after, credit_breakdown). Never raises; a call without a user is recorded but not billed."""
    try:
        cost = compute(record)
        record["credits"] = cost["credits"]
        record["credit_breakdown"] = cost["breakdown"]
        if record.get("cost") is None and cost["unit"] == "token" and cost["credits"] > 0:
            record["cost"] = round(cost["credits"] * USD_PER_CREDIT, 6)      # the gateway reports no price: an estimate from the weights table
            record["cost_estimated"] = True
        user_id = record.get("user_id")
        if cost["credits"] <= 0 or not _usable(user_id):
            return
        balance = _run(apply(str(user_id), -cost["credits"], "usage", fields={
            "request_id": record.get("id"), "route": record.get("route"),
            "model": (record.get("actual_model") or record.get("requested_model") or "")[:500],
            "conversation_id": record.get("conversation_id"), "project_id": record.get("project_id"),
            "project_kind": record.get("project_kind"), "job_id": record.get("job_id"),
            "input_tokens": record.get("input_tokens"), "output_tokens": record.get("output_tokens"),
            "cache_tokens": (record.get("cache_read_tokens") or 0) + (record.get("cache_write_tokens") or 0) or None}))
        record["credits_balance_after"] = balance
    except Exception:
        log.exception("credit charge failed for request %s", record.get("id"))


async def account(user_id: str) -> dict:
    if not _usable(user_id):
        return {"user_id": str(user_id), "balance": 0, "used_total": 0, "granted_total": 0, "unlimited": True, "tracked": False}
    async with _session() as db:
        row = await _ensure(db, str(user_id))
        return {"user_id": row.user_id, "balance": int(row.balance), "used_total": int(row.used_total), "granted_total": int(row.granted_total),
                "unlimited": bool(row.unlimited), "tracked": True}


async def require(user_id) -> dict:
    """Gate for a NEW request. Raises CreditsExhausted when the balance is not above zero (running work never calls this)."""
    state = await account(str(user_id))
    if state["tracked"] and settings()["enforce"] and not state["unlimited"] and state["balance"] <= 0:
        raise CreditsExhausted(state["balance"])
    return state


def require_sync(user_id) -> dict:
    return _run(require(user_id))


def http_error(exc: CreditsExhausted):
    from fastapi import HTTPException
    return HTTPException(402, {"code": "credits_exhausted", "message": EXHAUSTED_MESSAGE, "balance": exc.balance})


async def gate(user_id) -> None:
    """For FastAPI routes: `await credits.gate(user)` → 402 with the Persian message when the person has no credit left."""
    try:
        await require(user_id)
    except CreditsExhausted as exc:
        raise http_error(exc)


def gate_sync(user_id) -> None:
    """The same gate for a plain `def` route."""
    try:
        require_sync(user_id)
    except CreditsExhausted as exc:
        raise http_error(exc)


# ── packages and orders ─────────────────────────────────────────────────────

def _package(row: CreditPackage) -> dict:
    return {"id": row.id, "title": row.title, "credits": int(row.credits), "price": int(row.price), "currency": row.currency, "active": bool(row.active), "sort": row.sort}


async def packages(active_only: bool = True) -> list[dict]:
    if not DB_AVAILABLE:
        return [p for p in DEFAULT_PACKAGES if p["active"] or not active_only]
    async with _session() as db:
        rows = (await db.execute(select(CreditPackage).order_by(CreditPackage.sort, CreditPackage.id))).scalars().all()
        if not rows:
            db.add_all([CreditPackage(**p) for p in DEFAULT_PACKAGES])
            await db.commit()
            rows = (await db.execute(select(CreditPackage).order_by(CreditPackage.sort, CreditPackage.id))).scalars().all()
        return [_package(r) for r in rows if r.active or not active_only]


async def save_package(item: dict) -> dict:
    async with _session() as db:
        row = await db.get(CreditPackage, item["id"])
        if row is None:
            row = CreditPackage(id=item["id"], title=item["title"], credits=item["credits"])
            db.add(row)
        row.title, row.credits, row.price = item["title"], int(item["credits"]), int(item.get("price") or 0)
        row.currency, row.active, row.sort = item.get("currency") or "IRT", bool(item.get("active", True)), int(item.get("sort") or 0)
        await db.commit()
        return _package(row)


def _order(row: CreditOrder) -> dict:
    return {"id": row.id, "user_id": row.user_id, "package_id": row.package_id, "credits": int(row.credits), "price": int(row.price), "currency": row.currency,
            "status": row.status, "gateway": row.gateway, "gateway_ref": row.gateway_ref, "created_at": row.created_at, "paid_at": row.paid_at}


async def create_order(user_id: str, package_id: str) -> dict:
    """A pending order for a package. No payment gateway is connected yet: an administrator marks it paid (see mark_paid)."""
    async with _session() as db:
        package = await db.get(CreditPackage, package_id)
        if package is None or not package.active:
            raise KeyError(package_id)
        row = CreditOrder(id=str(uuid.uuid4()), user_id=str(user_id), package_id=package.id, credits=package.credits, price=package.price,
                          currency=package.currency, status="pending", created_at=now())
        db.add(row)
        await db.commit()
        return _order(row)


async def mark_paid(order_id: str, *, gateway: str = "manual", gateway_ref: str | None = None, actor: str | None = None) -> dict:
    """Idempotent: the credits of an order are granted once, whatever number of times (or processes) call this."""
    async with _session() as db:
        claimed = (await db.execute(update(CreditOrder).where(CreditOrder.id == order_id, CreditOrder.status == "pending")
                                    .values(status="paid", paid_at=now(), gateway=gateway, gateway_ref=gateway_ref).returning(CreditOrder.id))).scalar_one_or_none()
        await db.commit()
        row = await db.get(CreditOrder, order_id)
        if row is None:
            raise KeyError(order_id)
    if claimed is not None:
        await apply(row.user_id, int(row.credits), "purchase", fields={"note": f"سفارش {row.id[:8]}", "actor": actor or gateway})
    return _order(row)


async def start_payment(order_id: str, user_id: str, return_base: str) -> dict:
    """Send an order of this person to Rafiei Pay. Returns the order plus {"payment_url"} to redirect to."""
    from app import rafieipay
    async with _session() as db:
        row = await db.get(CreditOrder, order_id)
        if row is None or row.user_id != str(user_id) or row.status != "pending":
            raise KeyError(order_id)
        if row.price <= 0:
            raise ValueError("این بسته هنوز قیمت ندارد.")
        price, credits_, currency = int(row.price), int(row.credits), row.currency
    if currency != "IRT":
        raise ValueError("پرداخت آنلاین فقط برای قیمت به تومان فعال است.")
    paid = await rafieipay.request_payment(amount_toman=price, order_id=order_id, description=f"خرید {credits_:,} اعتبار EditorGPT",
                                           callback_url=f"{return_base}/api/webhook/rafieipay/return?order_id={order_id}", metadata={"app": "editorgpt", "credits": credits_})
    async with _session() as db:
        await db.execute(update(CreditOrder).where(CreditOrder.id == order_id, CreditOrder.status == "pending").values(gateway="rafieipay", gateway_ref=paid["payment_id"]))
        await db.commit()
    return {**(await _order_by_id(order_id)), "payment_url": paid["url"]}


async def order_id_for(ident: str) -> str | None:
    """An order id, or the gateway's payment id of an order, to our order id (None when it is neither)."""
    async with _session() as db:
        row = await db.get(CreditOrder, ident)
        if row is None:
            row = (await db.execute(select(CreditOrder).where(CreditOrder.gateway_ref == ident))).scalars().first()
        return row.id if row else None


async def _order_by_id(order_id: str) -> dict:
    async with _session() as db:
        row = await db.get(CreditOrder, order_id)
        if row is None:
            raise KeyError(order_id)
        return _order(row)


async def settle_order(order_id: str) -> dict:
    """Ask Rafiei Pay (server to server) whether the order was paid; if so add its credits exactly once.
    The amount Rafiei Pay reports must equal the order's price: a mismatch is never fulfilled. Safe to call any number of times."""
    from app import rafieipay
    order = await _order_by_id(order_id)
    if order["status"] != "pending" or order["gateway"] != "rafieipay" or not order["gateway_ref"]:
        return order
    try:
        payment = await rafieipay.get_payment(order["gateway_ref"])
    except rafieipay.PayError:
        log.warning("could not check payment of order %s", order_id, exc_info=True)
        return order
    if str(payment.get("status")) == "verified":
        if int(payment.get("amount_toman") or -1) != int(order["price"]):
            log.error("payment amount mismatch for order %s: paid %s, expected %s", order_id, payment.get("amount_toman"), order["price"])
            return order
        return await mark_paid(order_id, gateway="rafieipay", gateway_ref=str(payment.get("ref_id") or order["gateway_ref"]), actor="rafieipay")
    return order


async def orders(user_id: str | None = None, limit: int = 100) -> list[dict]:
    async with _session() as db:
        query = select(CreditOrder).order_by(CreditOrder.created_at.desc()).limit(limit)
        if user_id is not None:
            query = query.where(CreditOrder.user_id == str(user_id))
        return [_order(r) for r in (await db.execute(query)).scalars()]


# ── reading usage ───────────────────────────────────────────────────────────

def _entry(r: CreditLedger) -> dict:
    return {"id": int(r.id), "at": r.created_at, "kind": r.kind, "amount": int(r.amount), "balance_after": int(r.balance_after), "request_id": r.request_id,
            "route": r.route, "model": r.model, "conversation_id": r.conversation_id, "project_id": r.project_id, "project_kind": r.project_kind,
            "input_tokens": r.input_tokens, "output_tokens": r.output_tokens, "cache_tokens": r.cache_tokens, "note": r.note, "actor": r.actor}


async def ledger(user_id: str, page: int = 1, size: int = 50, kind: str | None = None) -> dict:
    async with _session() as db:
        cond = [CreditLedger.user_id == str(user_id)] + ([CreditLedger.kind == kind] if kind else [])
        total = await db.scalar(select(func.count()).select_from(CreditLedger).where(*cond))
        rows = (await db.execute(select(CreditLedger).where(*cond).order_by(CreditLedger.id.desc()).offset((page - 1) * size).limit(size))).scalars()
        return {"items": [_entry(r) for r in rows], "total": int(total or 0)}


async def usage_by(user_id: str, column: str, limit: int = 50) -> list[dict]:
    """Total credits used per chat (`conversation_id`) or per project/video (`project_id`)."""
    col = getattr(CreditLedger, column)
    async with _session() as db:
        rows = (await db.execute(select(col, func.sum(-CreditLedger.amount), func.count(), func.sum(CreditLedger.input_tokens), func.sum(CreditLedger.output_tokens),
                                        func.max(CreditLedger.created_at), func.max(CreditLedger.project_kind))
                                 .where(CreditLedger.user_id == str(user_id), CreditLedger.kind == "usage", col.is_not(None))
                                 .group_by(col).order_by(func.max(CreditLedger.created_at).desc()).limit(limit))).all()
        return [{"id": r[0], "credits": int(r[1] or 0), "calls": int(r[2]), "input_tokens": int(r[3] or 0), "output_tokens": int(r[4] or 0), "last_at": r[5], "kind": r[6]} for r in rows]


async def conversation_for_project(ref: str) -> str | None:
    """The chat a project / film belongs to (studio projects know their conversation; the film's own id is the project's external_ref)."""
    from app.models import StudioProject
    async with _session() as db:
        row = (await db.execute(select(StudioProject).where((StudioProject.id == ref) | (StudioProject.external_ref == ref)))).scalars().first()
        return row.conversation_id if row else None


async def chat_usage(user_id: str, limit: int = 50) -> list[dict]:
    """Credits per chat, including the calls of its films / projects: a film's calls carry its project but not always the chat
    (a render started from a button), so they are attached to the project's chat here."""
    from app.models import StudioProject
    async with _session() as db:
        rows = (await db.execute(select(CreditLedger.conversation_id, CreditLedger.project_id, func.sum(-CreditLedger.amount), func.count(),
                                        func.sum(CreditLedger.input_tokens), func.sum(CreditLedger.output_tokens), func.max(CreditLedger.created_at))
                                 .where(CreditLedger.user_id == str(user_id), CreditLedger.kind == "usage")
                                 .group_by(CreditLedger.conversation_id, CreditLedger.project_id))).all()
        refs = {r[1] for r in rows if r[0] is None and r[1]}
        owner = {}
        if refs:
            for p in (await db.execute(select(StudioProject).where(StudioProject.id.in_(refs) | StudioProject.external_ref.in_(refs)))).scalars():
                owner[p.id] = p.conversation_id
                if p.external_ref: owner[p.external_ref] = p.conversation_id
    groups = {}
    for conv, project, credits_, calls, tin, tout, last in rows:
        conv = conv or owner.get(project)
        if not conv: continue
        g = groups.setdefault(conv, {"id": conv, "credits": 0, "calls": 0, "input_tokens": 0, "output_tokens": 0, "last_at": "", "kind": None})
        g["credits"] += int(credits_ or 0); g["calls"] += int(calls); g["input_tokens"] += int(tin or 0); g["output_tokens"] += int(tout or 0)
        g["last_at"] = max(g["last_at"], last or "")
    return sorted(groups.values(), key=lambda g: g["last_at"], reverse=True)[:limit]


async def project_breakdown(user_id: str, project_id: str) -> dict:
    """What one video cost: per model and per step (route), with the raw tokens."""
    async with _session() as db:
        out = {}
        for name, col in (("by_model", CreditLedger.model), ("by_route", CreditLedger.route)):
            rows = (await db.execute(select(col, func.sum(-CreditLedger.amount), func.count(), func.sum(CreditLedger.input_tokens), func.sum(CreditLedger.output_tokens),
                                            func.sum(CreditLedger.cache_tokens))
                                     .where(CreditLedger.user_id == str(user_id), CreditLedger.kind == "usage", CreditLedger.project_id == project_id)
                                     .group_by(col).order_by(func.sum(-CreditLedger.amount).desc()))).all()
            out[name] = [{"key": r[0], "credits": int(r[1] or 0), "calls": int(r[2]), "input_tokens": int(r[3] or 0), "output_tokens": int(r[4] or 0), "cache_tokens": int(r[5] or 0)} for r in rows]
        out["total"] = sum(x["credits"] for x in out["by_route"])
        return out


async def users_overview(query: str = "", limit: int = 300) -> list[dict]:
    """Administrator: every user with their balance (users without an account yet show the initial grant they will get)."""
    from app.models import UserModel
    async with _session() as db:
        stmt = select(UserModel).order_by(UserModel.id)
        if query.strip():
            like = f"%{query.strip().lower()}%"
            stmt = stmt.where(func.lower(UserModel.email).like(like) | func.lower(UserModel.name).like(like))
        users = (await db.execute(stmt.limit(limit))).scalars().all()
        accounts = {a.user_id: a for a in (await db.execute(select(CreditAccount))).scalars()}
    grant = int(settings()["initial_grant"])
    out = []
    for u in users:
        a = accounts.get(str(u.id))
        out.append({"id": str(u.id), "email": u.email, "name": u.name, "has_account": a is not None,
                    "balance": int(a.balance) if a else grant, "used_total": int(a.used_total) if a else 0,
                    "granted_total": int(a.granted_total) if a else grant, "unlimited": bool(a.unlimited) if a else False})
    return out


async def set_unlimited(user_id: str, value: bool) -> dict:
    async with _session() as db:
        await _ensure(db, str(user_id))
        await db.execute(update(CreditAccount).where(CreditAccount.user_id == str(user_id)).values(unlimited=bool(value), updated_at=now()))
        await db.commit()
    return await account(str(user_id))
