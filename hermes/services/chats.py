"""The agent's conversations: one stored chat per row (like the Studio's chat history), listed in the sidebar, each with its own page.

A chat keeps its messages (the person's, the agent's reply with what it consulted and its suggested next questions). Replies come from
``agent.chat`` (the router task hermes_chat), which also sees the account notes and the text of the page the person was on."""
from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException

from hermes.config import settings_row_id
from hermes.database import delete_row, get_row, list_rows, save_row
from hermes.security import utcnow
from hermes.services import agent

PREFIX = "chat:"
MAX_CHATS = 60
MAX_MESSAGES = 120


def _row_id(user_id: str, cid: str) -> str:
    return settings_row_id(user_id, PREFIX + cid)


def _public(row: dict, with_messages: bool = False) -> dict:
    data = row.get("encrypted_credentials") or {}
    out = {"id": data.get("id"), "title": data.get("title") or "گفتگوی جدید", "created_at": data.get("created_at"), "updated_at": data.get("updated_at")}
    if with_messages:
        out["messages"] = data.get("messages") or []
    return out


async def _save(user_id: str, cid: str, data: dict) -> None:
    existing = await get_row("settings", _row_id(user_id, cid))
    now = utcnow()
    await save_row("settings", {"id": _row_id(user_id, cid), "user_id": int(user_id) if str(user_id).isdigit() else user_id, "provider": PREFIX + cid,
                                "encrypted_credentials": data, "created_at": existing["created_at"] if existing else now, "updated_at": now})


async def list_chats(user_id: str) -> list[dict]:
    rows = [r for r in await list_rows("settings") if str(r.get("user_id")) == str(user_id) and str(r.get("provider", "")).startswith(PREFIX)]
    items = [_public(r) for r in rows]
    return sorted(items, key=lambda c: c.get("updated_at") or "", reverse=True)[:MAX_CHATS]


async def create(user_id: str, title: str = "") -> dict:
    cid = uuid4().hex[:12]
    now = utcnow()
    data = {"id": cid, "title": title[:80], "created_at": now, "updated_at": now, "messages": []}
    await _save(user_id, cid, data)
    return _public({"encrypted_credentials": data}, True)


async def get(user_id: str, cid: str) -> dict:
    row = await get_row("settings", _row_id(user_id, cid))
    if not row or str(row.get("user_id")) != str(user_id):
        raise HTTPException(404, detail={"code": "CHAT_NOT_FOUND"})
    return _public(row, True)


async def remove(user_id: str, cid: str) -> None:
    await get(user_id, cid)
    await delete_row("settings", _row_id(user_id, cid))


async def send(user_id: str, cid: str, message: str, page: dict | None) -> dict:
    chat = await get(user_id, cid)
    history = [{"role": "user" if m["role"] == "user" else "agent", "text": m["text"]} for m in chat["messages"][-8:]]
    reply = await agent.chat(user_id, message, page, history)
    now = utcnow()
    messages = (chat["messages"] + [{"role": "user", "text": message[:4000], "at": now},
                                    {"role": "assistant", "text": reply["reply"], "at": now, "activity": reply.get("activity"), "suggestions": reply.get("suggestions"),
                                     "action": reply.get("action")}])[-MAX_MESSAGES:]
    title = chat["title"] if chat["title"] != "گفتگوی جدید" else message.strip().replace("\n", " ")[:48]
    await _save(user_id, cid, {"id": cid, "title": title, "created_at": chat["created_at"], "updated_at": now, "messages": messages})
    return {"chat": {"id": cid, "title": title, "updated_at": now}, "reply": messages[-1]}
