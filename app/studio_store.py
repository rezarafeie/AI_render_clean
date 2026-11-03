"""Persistence facade for the chat-first video Studio.

PostgreSQL is canonical in production.  A single atomic JSON document keeps
loopback development usable when DATABASE_URL is intentionally empty.
"""
from __future__ import annotations

import asyncio
import copy
import json
import time
import os
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from app.config import settings
from app.database import AsyncSessionLocal, DB_AVAILABLE
from app.models import (
    StudioAction, StudioAttachment, StudioConversation, StudioEvent,
    StudioMessage, StudioProject, StudioProjectVersion,
)

ROOT = Path(settings.JOBS_DIR).expanduser() / "studio"
FALLBACK = ROOT / "studio.json"
_lock = threading.RLock()


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | str | None) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return value.isoformat()


def new_id() -> str:
    return uuid.uuid4().hex


def _empty() -> dict:
    return {"conversations": {}, "messages": {}, "attachments": {}, "projects": {}, "versions": {}, "actions": {}, "events": {}}


def _read() -> dict:
    ROOT.mkdir(parents=True, exist_ok=True)
    if not FALLBACK.is_file():
        return _empty()
    try:
        text = FALLBACK.read_text()
    except OSError:
        return _empty()
    try:
        data = json.loads(text)
    except ValueError:
        data = _recover(text)
    return data if isinstance(data, dict) else _empty()


def _recover(text: str) -> dict:
    """A damaged store must never read as "empty": the next write would erase everything.

    Two processes writing at once can leave a complete JSON document followed by stray bytes. Keep the damaged
    file for inspection and continue from the intact document at its start; if there is none, stop loudly."""
    try:
        data, _end = json.JSONDecoder().raw_decode(text)
        if not isinstance(data, dict):
            raise ValueError("not an object")
    except ValueError as exc:
        raise RuntimeError(f"The local Studio store {FALLBACK} is damaged and cannot be recovered automatically; "
                           f"restore it from a backup instead of starting empty") from exc
    damaged = FALLBACK.with_name(f"studio.damaged-{int(time.time())}.json")
    damaged.write_text(text)
    logging.getLogger(__name__).warning("Studio store was damaged; recovered its intact start (copy kept at %s)", damaged)
    _write(data)
    return data


def _write(data: dict) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    # One temporary file per writer: concurrent writers can lose an update but can never interleave bytes.
    temporary = FALLBACK.with_name(f"{FALLBACK.stem}.{os.getpid()}.{threading.get_ident()}.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    temporary.replace(FALLBACK)


def _conversation(row: StudioConversation) -> dict:
    return {"id": row.id, "user_key": row.user_key, "title": row.title, "language": row.language,
            "status_voice_enabled": row.status_voice_enabled, "state": row.state or {},
            "created_at": iso(row.created_at), "updated_at": iso(row.updated_at)}


def _project(row: StudioProject) -> dict:
    return {"id": row.id, "conversation_id": row.conversation_id, "engine": row.engine,
            "title": row.title, "status": row.status, "external_ref": row.external_ref,
            "current_version": row.current_version, "state": row.state or {},
            "created_at": iso(row.created_at), "updated_at": iso(row.updated_at)}


class Repository:
    async def claim_manual_checkpoint(self, project_id: str, user_key: str, question_id: str) -> bool:
        """Single-use render approval, locked across API/worker processes."""
        if DB_AVAILABLE:
            async with AsyncSessionLocal() as db:
                row = (await db.execute(select(StudioProject).where(StudioProject.id == project_id,
                    StudioProject.user_key == user_key).with_for_update())).scalar_one_or_none()
                if row is None: raise KeyError(project_id)
                state = copy.deepcopy(row.state or {})
                checkpoint = state.get('manual_checkpoint') or {}
                if checkpoint.get('id') != question_id or checkpoint.get('claimed'): return False
                checkpoint['claimed'] = True
                row.state = {**state, 'manual_checkpoint': checkpoint}
                await db.commit()
                return True
        with _lock:
            data = _read(); row = data['projects'].get(project_id)
            if row is None or row['user_key'] != user_key: raise KeyError(project_id)
            checkpoint = row['state'].get('manual_checkpoint') or {}
            if checkpoint.get('id') != question_id or checkpoint.get('claimed'): return False
            checkpoint['claimed'] = True; _write(data)
            return True

    async def claim_manual_question(self, conversation_id: str, user_key: str, question_id: str) -> bool:
        if DB_AVAILABLE:
            async with AsyncSessionLocal() as db:
                row = (await db.execute(select(StudioConversation).where(StudioConversation.id == conversation_id,
                    StudioConversation.user_key == user_key).with_for_update())).scalar_one_or_none()
                if row is None: raise KeyError(conversation_id)
                state = copy.deepcopy(row.state or {}); session = state.get('manual_session') or {}
                if session.get('question_id') != question_id or session.get('claimed'): return False
                session['claimed'] = True; row.state = {**state, 'manual_session': session}
                await db.commit(); return True
        with _lock:
            data = _read(); row = data['conversations'].get(conversation_id)
            if row is None or row['user_key'] != user_key: raise KeyError(conversation_id)
            session = row['state'].get('manual_session') or {}
            if session.get('question_id') != question_id or session.get('claimed'): return False
            session['claimed'] = True; _write(data); return True

    async def voice_enabled(self, conversation_id: str) -> bool:
        if DB_AVAILABLE:
            assert AsyncSessionLocal is not None
            async with AsyncSessionLocal() as db:
                row = await db.get(StudioConversation, conversation_id)
                return bool(row and row.status_voice_enabled)
        with _lock:
            row = _read()["conversations"].get(conversation_id)
            return bool(row and row.get("status_voice_enabled"))

    async def create_conversation(self, user_key: str, title: str = "گفتگوی جدید") -> dict:
        cid, created = new_id(), now()
        if DB_AVAILABLE:
            assert AsyncSessionLocal is not None
            async with AsyncSessionLocal() as db:
                row = StudioConversation(id=cid, user_key=user_key, title=title[:255], language="fa",
                                         status_voice_enabled=False, state={}, created_at=created, updated_at=created)
                db.add(row); await db.commit()
                return _conversation(row)
        value = {"id": cid, "user_key": user_key, "title": title[:255], "language": "fa",
                 "status_voice_enabled": False, "state": {}, "created_at": iso(created), "updated_at": iso(created)}
        with _lock:
            data = _read(); data["conversations"][cid] = value; _write(data)
        return copy.deepcopy(value)

    async def list_conversations(self, user_key: str) -> list[dict]:
        if DB_AVAILABLE:
            assert AsyncSessionLocal is not None
            async with AsyncSessionLocal() as db:
                rows = (await db.execute(select(StudioConversation).where(
                    StudioConversation.user_key == user_key).order_by(StudioConversation.updated_at.desc()))).scalars()
                return [_conversation(row) for row in rows]
        with _lock:
            rows = [v for v in _read()["conversations"].values() if v["user_key"] == user_key]
        return sorted(copy.deepcopy(rows), key=lambda item: item["updated_at"], reverse=True)

    async def get_conversation(self, conversation_id: str, user_key: str) -> dict:
        if DB_AVAILABLE:
            assert AsyncSessionLocal is not None
            async with AsyncSessionLocal() as db:
                row = await db.get(StudioConversation, conversation_id)
                if row is None or row.user_key != user_key: raise KeyError(conversation_id)
                messages = (await db.execute(select(StudioMessage).where(StudioMessage.conversation_id == conversation_id).order_by(StudioMessage.id))).scalars()
                projects = (await db.execute(select(StudioProject).where(StudioProject.conversation_id == conversation_id).order_by(StudioProject.created_at))).scalars()
                actions = (await db.execute(select(StudioAction).where(StudioAction.conversation_id == conversation_id).order_by(StudioAction.created_at))).scalars()
                value = _conversation(row)
                value["messages"] = [{"id": item.id, "role": item.role, "content": item.content,
                                      "attachments": item.attachments or [], "agent_mode": item.agent_mode,
                                      "created_at": iso(item.created_at)} for item in messages]
                value["projects"] = [_project(item) for item in projects]
                value["actions"] = [{"id": item.id, "project_id": item.project_id, "kind": item.kind,
                                     "status": item.status, "payload": item.payload or {},
                                     "estimated_cost_usd": item.estimated_cost_usd,
                                     "created_at": iso(item.created_at)} for item in actions]
                return value
        with _lock:
            data = _read(); row = data["conversations"].get(conversation_id)
            if row is None or row["user_key"] != user_key: raise KeyError(conversation_id)
            value = copy.deepcopy(row)
            value["messages"] = copy.deepcopy(data["messages"].get(conversation_id, []))
            value["projects"] = [copy.deepcopy(v) for v in data["projects"].values() if v["conversation_id"] == conversation_id]
            value["actions"] = [copy.deepcopy(v) for v in data["actions"].values() if v["conversation_id"] == conversation_id]
            return value

    async def set_conversation(self, conversation_id: str, user_key: str, **changes: Any) -> dict:
        allowed = {"title", "language", "status_voice_enabled", "state"}
        changes = {key: value for key, value in changes.items() if key in allowed}
        if DB_AVAILABLE:
            assert AsyncSessionLocal is not None
            async with AsyncSessionLocal() as db:
                row = await db.get(StudioConversation, conversation_id)
                if row is None or row.user_key != user_key: raise KeyError(conversation_id)
                for key, value in changes.items(): setattr(row, key, value)
                row.updated_at = now(); await db.commit(); return _conversation(row)
        with _lock:
            data = _read(); row = data["conversations"].get(conversation_id)
            if row is None or row["user_key"] != user_key: raise KeyError(conversation_id)
            row.update(changes, updated_at=iso(now())); _write(data); return copy.deepcopy(row)

    async def add_message(self, conversation_id: str, user_key: str, role: str, content: str,
                          attachments: list[str] | None = None, *, agent_mode: str = "lite") -> dict:
        await self.get_conversation(conversation_id, user_key)
        created = now(); attachments = attachments or []
        if DB_AVAILABLE:
            assert AsyncSessionLocal is not None
            async with AsyncSessionLocal() as db:
                row = StudioMessage(conversation_id=conversation_id, role=role, content=content,
                                    attachments=attachments, created_at=created, agent_mode=agent_mode)
                db.add(row)
                conversation = await db.get(StudioConversation, conversation_id)
                if conversation: conversation.updated_at = created
                await db.commit(); await db.refresh(row)
                return {"id": row.id, "role": role, "content": content, "attachments": attachments, "agent_mode": agent_mode, "created_at": iso(created)}
        with _lock:
            data = _read(); items = data["messages"].setdefault(conversation_id, [])
            value = {"id": len(items) + 1, "role": role, "content": content, "attachments": attachments, "agent_mode": agent_mode, "created_at": iso(created)}
            items.append(value); data["conversations"][conversation_id]["updated_at"] = iso(created); _write(data)
            return copy.deepcopy(value)

    async def create_attachment(self, conversation_id: str, user_key: str, **values: Any) -> dict:
        await self.get_conversation(conversation_id, user_key)
        aid, created = new_id(), now()
        value = {"id": aid, "conversation_id": conversation_id, "user_key": user_key,
                 "kind": values["kind"], "filename": values["filename"], "path": values["path"],
                 "mime_type": values["mime_type"], "size_bytes": values["size_bytes"],
                 "metadata": values.get("metadata") or {}, "created_at": iso(created)}
        if DB_AVAILABLE:
            assert AsyncSessionLocal is not None
            async with AsyncSessionLocal() as db:
                db.add(StudioAttachment(id=aid, conversation_id=conversation_id, user_key=user_key,
                    kind=value["kind"], filename=value["filename"], path=value["path"],
                    mime_type=value["mime_type"], size_bytes=value["size_bytes"],
                    metadata_json=value["metadata"], created_at=created))
                await db.commit()
        else:
            with _lock:
                data = _read(); data["attachments"][aid] = value; _write(data)
        return value

    async def get_attachments(self, ids: list[str], conversation_id: str, user_key: str) -> list[dict]:
        if not ids: return []
        if DB_AVAILABLE:
            assert AsyncSessionLocal is not None
            async with AsyncSessionLocal() as db:
                rows = (await db.execute(select(StudioAttachment).where(
                    StudioAttachment.id.in_(ids), StudioAttachment.conversation_id == conversation_id,
                    StudioAttachment.user_key == user_key))).scalars()
                values = [{"id": row.id, "kind": row.kind, "filename": row.filename, "path": row.path,
                           "mime_type": row.mime_type, "size_bytes": row.size_bytes,
                           "metadata": row.metadata_json or {}} for row in rows]
        else:
            with _lock:
                data = _read(); values = [copy.deepcopy(data["attachments"][key]) for key in ids
                    if key in data["attachments"] and data["attachments"][key]["conversation_id"] == conversation_id
                    and data["attachments"][key]["user_key"] == user_key]
        if len(values) != len(set(ids)): raise KeyError("attachment")
        order = {value: index for index, value in enumerate(ids)}
        return sorted(values, key=lambda item: order[item["id"]])

    async def create_project(self, conversation_id: str, user_key: str, engine: str, title: str,
                             state: dict | None = None, external_ref: str | None = None) -> dict:
        conversation = await self.get_conversation(conversation_id, user_key)
        pid, created = new_id(), now(); state = dict(state or {})
        state.setdefault("render_target", conversation.get("state", {}).get("render_target", "server"))
        value = {"id": pid, "conversation_id": conversation_id, "user_key": user_key, "engine": engine, "title": title[:255],
                 "status": "planning", "external_ref": external_ref, "current_version": 1,
                 "state": state, "created_at": iso(created), "updated_at": iso(created)}
        if DB_AVAILABLE:
            assert AsyncSessionLocal is not None
            async with AsyncSessionLocal() as db:
                row = StudioProject(id=pid, conversation_id=conversation_id, user_key=user_key, engine=engine,
                    title=title[:255], status="planning", external_ref=external_ref, current_version=1,
                    state=state, created_at=created, updated_at=created)
                db.add(row); db.add(StudioProjectVersion(project_id=pid, version=1, source="agent", snapshot=state, created_at=created))
                await db.commit()
        else:
            with _lock:
                data = _read(); data["projects"][pid] = value
                data["versions"][pid] = [{"version": 1, "source": "agent", "snapshot": state, "created_at": iso(created)}]
                _write(data)
        conversation = await self.get_conversation(conversation_id, user_key)
        await self.set_conversation(conversation_id, user_key,
                                    state={**conversation.get("state", {}), "current_project_id": pid})
        return value

    async def get_project(self, project_id: str, user_key: str) -> dict:
        if DB_AVAILABLE:
            assert AsyncSessionLocal is not None
            async with AsyncSessionLocal() as db:
                row = await db.get(StudioProject, project_id)
                if row is None or row.user_key != user_key: raise KeyError(project_id)
                return _project(row)
        with _lock:
            row = _read()["projects"].get(project_id)
            if row is None or row.get("user_key", user_key) != user_key: raise KeyError(project_id)
            return copy.deepcopy(row)

    async def attach_plan_frames(self, project_id: str, user_key: str, version_id: str, frames: dict, status: str) -> None:
        """Merge optional thumbnails under the row lock; never overwrite a concurrent approval."""
        def merge(state):
            state = copy.deepcopy(state)
            versions = (state.get("plan") or {}).get("versions") or []
            if not versions or versions[-1]["id"] != version_id: return None
            versions[-1]["content"]["frames"] = frames
            state["plan_preview_status"] = status
            return state
        if DB_AVAILABLE:
            async with AsyncSessionLocal() as db:
                row = await db.scalar(select(StudioProject).where(StudioProject.id == project_id).with_for_update())
                if row is None or row.user_key != user_key: raise KeyError(project_id)
                state = merge(row.state)
                if state is not None:
                    row.state = state
                    await db.commit()
        else:
            with _lock:
                data = _read(); row = data["projects"].get(project_id)
                if row is None or row.get("user_key") != user_key: raise KeyError(project_id)
                state = merge(row["state"])
                if state is not None:
                    row["state"] = state; _write(data)

    async def update_project(self, project_id: str, user_key: str, *, source: str | None = None, **changes: Any) -> dict:
        allowed = {"title", "status", "external_ref", "state"}; changes = {k: v for k, v in changes.items() if k in allowed}
        created = now()
        if DB_AVAILABLE:
            assert AsyncSessionLocal is not None
            async with AsyncSessionLocal() as db:
                row = await db.get(StudioProject, project_id)
                if row is None or row.user_key != user_key: raise KeyError(project_id)
                for key, value in changes.items(): setattr(row, key, value)
                if source:
                    row.current_version += 1
                    db.add(StudioProjectVersion(project_id=project_id, version=row.current_version,
                                                source=source, snapshot=row.state or {}, created_at=created))
                row.updated_at = created; await db.commit(); return _project(row)
        with _lock:
            data = _read(); row = data["projects"].get(project_id)
            if row is None or row.get("user_key", user_key) != user_key: raise KeyError(project_id)
            row.update(changes, updated_at=iso(created))
            if source:
                row["current_version"] += 1
                data["versions"].setdefault(project_id, []).append({"version": row["current_version"], "source": source,
                                                                     "snapshot": row.get("state", {}), "created_at": iso(created)})
            _write(data); return copy.deepcopy(row)

    async def create_action(self, conversation_id: str, project_id: str | None, kind: str,
                            payload: dict, idempotency_key: str, estimated_cost: float | None = None) -> dict:
        aid, created = new_id(), now()
        value = {"id": aid, "conversation_id": conversation_id, "project_id": project_id, "kind": kind,
                 "status": "pending", "payload": payload, "idempotency_key": idempotency_key,
                 "estimated_cost_usd": estimated_cost, "created_at": iso(created), "updated_at": iso(created)}
        if DB_AVAILABLE:
            assert AsyncSessionLocal is not None
            async with AsyncSessionLocal() as db:
                existing = (await db.execute(select(StudioAction).where(StudioAction.idempotency_key == idempotency_key))).scalar_one_or_none()
                if existing: return {"id": existing.id, "status": existing.status, "kind": existing.kind,
                                     "project_id": existing.project_id, "payload": existing.payload or {},
                                     "estimated_cost_usd": existing.estimated_cost_usd}
                db.add(StudioAction(id=aid, conversation_id=conversation_id, project_id=project_id, kind=kind,
                    status="pending", idempotency_key=idempotency_key, payload=payload,
                    estimated_cost_usd=estimated_cost, created_at=created, updated_at=created)); await db.commit()
        else:
            with _lock:
                data = _read()
                existing = next((item for item in data["actions"].values() if item["idempotency_key"] == idempotency_key), None)
                if existing: return copy.deepcopy(existing)
                data["actions"][aid] = value; _write(data)
        return value

    async def get_action(self, action_id: str, user_key: str) -> dict:
        conversation_ids = {item["id"] for item in await self.list_conversations(user_key)}
        if DB_AVAILABLE:
            assert AsyncSessionLocal is not None
            async with AsyncSessionLocal() as db:
                row = await db.get(StudioAction, action_id)
                if row is None or row.conversation_id not in conversation_ids: raise KeyError(action_id)
                return {"id": row.id, "conversation_id": row.conversation_id, "project_id": row.project_id,
                        "kind": row.kind, "status": row.status, "payload": row.payload or {},
                        "estimated_cost_usd": row.estimated_cost_usd}
        with _lock:
            row = _read()["actions"].get(action_id)
            if row is None or row["conversation_id"] not in conversation_ids: raise KeyError(action_id)
            return copy.deepcopy(row)

    async def update_action(self, action_id: str, status: str) -> dict:
        if DB_AVAILABLE:
            assert AsyncSessionLocal is not None
            async with AsyncSessionLocal() as db:
                row = await db.get(StudioAction, action_id)
                if row is None: raise KeyError(action_id)
                row.status, row.updated_at = status, now(); await db.commit()
                return {"id": row.id, "conversation_id": row.conversation_id, "project_id": row.project_id,
                        "kind": row.kind, "status": row.status, "payload": row.payload or {}}
        with _lock:
            data = _read(); row = data["actions"].get(action_id)
            if row is None: raise KeyError(action_id)
            row.update(status=status, updated_at=iso(now())); _write(data); return copy.deepcopy(row)

    async def emit(self, conversation_id: str, event_type: str, data_value: dict, *, source_event_id: str | None = None) -> dict:
        created = now()
        if source_event_id:data_value={**data_value,'source_event_id':source_event_id}
        if DB_AVAILABLE:
            assert AsyncSessionLocal is not None
            async with AsyncSessionLocal() as db:
                if db.bind.dialect.name=='postgresql':
                    from sqlalchemy import text
                    await db.execute(text('SELECT pg_advisory_xact_lock(hashtext(:cid))'),{'cid':conversation_id})
                if source_event_id:
                    old=await db.scalar(select(StudioEvent).where(StudioEvent.conversation_id==conversation_id,
                        StudioEvent.data['source_event_id'].as_string()==source_event_id))
                    if old:return {'id':old.id,'seq':old.seq,'type':old.event_type,'data':old.data,'created_at':iso(old.created_at)}
                seq = int((await db.scalar(select(func.coalesce(func.max(StudioEvent.seq), 0)).where(
                    StudioEvent.conversation_id == conversation_id))) or 0) + 1
                row = StudioEvent(conversation_id=conversation_id, seq=seq, event_type=event_type,
                                  data=data_value, created_at=created)
                db.add(row); await db.commit(); await db.refresh(row)
                return {"id": row.id, "seq": seq, "type": event_type, "data": data_value, "created_at": iso(created)}
        with _lock:
            store = _read(); events = store["events"].setdefault(conversation_id, [])
            if source_event_id:
                old=next((e for e in events if e['data'].get('source_event_id')==source_event_id),None)
                if old:return copy.deepcopy(old)
            value = {"id": len(events) + 1, "seq": len(events) + 1, "type": event_type,
                     "data": data_value, "created_at": iso(created)}
            events.append(value); _write(store); return copy.deepcopy(value)

    async def events(self, conversation_id: str, user_key: str, after: int = 0, limit: int = 200, *, check: bool = True) -> list[dict]:
        if check:
            await self.get_conversation(conversation_id, user_key)
        if DB_AVAILABLE:
            assert AsyncSessionLocal is not None
            async with AsyncSessionLocal() as db:
                rows = (await db.execute(select(StudioEvent).where(
                    StudioEvent.conversation_id == conversation_id, StudioEvent.seq > after
                ).order_by(StudioEvent.seq).limit(limit))).scalars()
                return [{"id": row.id, "seq": row.seq, "type": row.event_type,
                         "data": row.data or {}, "created_at": iso(row.created_at)} for row in rows]
        with _lock:
            return copy.deepcopy([item for item in _read()["events"].get(conversation_id, []) if item["seq"] > after][:limit])


repo = Repository()


def run(coro):
    return asyncio.run(coro)
