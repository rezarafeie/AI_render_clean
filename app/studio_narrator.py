"""The studio's voice in the chat: one short, streamed message about what a step just did or found.

The words are written by the model from the REAL facts of the step (the title of the page it read, the number of shots in the reference, the colours it
measured, the idea it chose), so a message is never a canned sentence. If the model is unavailable the caller's plain factual ``fallback`` is posted
instead: something true always appears. Messages are queued per conversation and run in the background, so the pipeline never waits for its own narration
and two messages never interleave.
"""
from __future__ import annotations

import json
import hashlib
import re
import logging
import threading
import time
import uuid
import contextvars
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any

log = logging.getLogger(__name__)
_lock = threading.Lock()
_queues: dict[str, ThreadPoolExecutor] = {}
MAX_CHARS = 320
_recent: dict[tuple, str] = {}

SYSTEM = (
    "You are the voice of a video and motion-graphics studio, talking to the person who asked for the work. Write ONE short chat message "
    "(1 to 2 sentences, at most about 40 words) about what the studio has just done or found. Write in Persian unless facts explicitly specify another language. "
    "first person, natural, in your own words. Use ONLY the facts given: name concrete things (a page title, a number, a colour, a short quoted phrase). "
    "Never invent details, never claim anything the facts do not say, never promise results, never describe internal steps or tools. "
    "If a fact says something could not be determined or read, say so plainly in one clause. No headings, no bullet lists, no emojis, no greeting."
)


def _public_narration(text: str, facts: dict) -> bool:
    if re.search(r"<think>|```|\b(?:analysis|verdict|chain.of.thought)\s*:", text, re.I): return False
    if facts.get("language", "fa") == "fa":
        persian = len(re.findall(r"[\u0600-\u06ff]", text))
        latin = len(re.findall(r"[A-Za-z]", text))
        if persian < 3 or persian < latin * .7: return False
    return True


def _executor(conversation_id: str) -> ThreadPoolExecutor:
    with _lock:
        if conversation_id not in _queues:
            _queues[conversation_id] = ThreadPoolExecutor(max_workers=1, thread_name_prefix="narrator")
        return _queues[conversation_id]


def _trim(text: str) -> str:
    """A narration is short: cut a rambling answer at a sentence end instead of showing a wall of text."""
    text = text.strip()
    if len(text) <= MAX_CHARS:
        return text
    cut = text[:MAX_CHARS]
    end = max(cut.rfind("."), cut.rfind("؟"), cut.rfind("!"), cut.rfind("؛"), cut.rfind("\n"))
    return (cut[:end + 1] if end > MAX_CHARS * 0.4 else cut.rsplit(" ", 1)[0] + "…").strip()


def _post(conversation_id: str, user_key: str, text: str, attachments: list[str] | None) -> None:
    from app.studio_orchestrator import _assistant
    _assistant(conversation_id, user_key, text, attachments or None)


def _stream(conversation_id: str, user_key: str, kind: str, facts: dict, attachments: list[str] | None, fallback: str, generation: int = 0) -> None:
    from app import studio_flags
    from app.studio_orchestrator import _emit, repo, run
    if studio_flags.generation(user_key, conversation_id) != generation:
        return                                           # the person pressed Stop after this was queued: it is no longer news
    from brain.lm_gateway import configured, stream_chat
    text = ""
    if configured():
        response_id = f"narration:{uuid.uuid4().hex[:12]}"
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": json.dumps({"stage": kind, "facts": facts}, ensure_ascii=False)[:6000]}]
        _emit(conversation_id, "assistant.response.started", response_id=response_id, narration=kind)
        flushed, tick = "", 0.0
        try:
            for chunk in stream_chat("conversation_response", messages, tokens=300, timeout_seconds=30):
                text += chunk
                if len(text) > MAX_CHARS * 1.6:
                    break                                        # enough: the message is cut at a sentence end below
                if _public_narration(text, facts) and (not flushed or time.monotonic() - tick > 0.04):
                    _emit(conversation_id, "assistant.response.delta", response_id=response_id, text=text)
                    flushed, tick = text, time.monotonic()
            text = _trim(text)
            if not text or not _public_narration(text, facts):
                raise ValueError("Narration must be public-facing and in the requested language")
            if studio_flags.generation(user_key, conversation_id) != generation:
                _emit(conversation_id, "assistant.response.failed", response_id=response_id, text="", message_id=None, error="")
                return
            mode = facts.get("agent_mode")
            saved = run(repo.add_message(conversation_id, user_key, "assistant", text, attachments or None,
                                        **({"agent_mode": mode} if mode in {"lite", "medium"} else {})))
            _emit(conversation_id, "assistant.response.completed", response_id=response_id, text=text, message_id=saved["id"], attachments=list(attachments or []))
            return
        except Exception as exc:
            log.warning("narration %s fell back to its plain text: %s", kind, type(exc).__name__)
            _emit(conversation_id, "assistant.response.failed", response_id=response_id, text="", message_id=None, error="")
    if fallback.strip():
        _post(conversation_id, user_key, fallback.strip(), attachments)


def narrate(conversation_id: str, user_key: str, kind: str, facts: dict[str, Any], *, attachments: list[str] | None = None,
            fallback: str = "", background: bool = True):
    """Say what ``kind`` of step just happened, from ``facts``. Returns the future (``.result()`` to wait for the message to be posted)."""
    from app import studio_flags
    generation = studio_flags.generation(user_key, conversation_id)
    identity = (user_key, conversation_id, kind, generation)
    digest = hashlib.sha256(json.dumps([facts, attachments, fallback], sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    with _lock:
        if _recent.get(identity) == digest:
            done = Future(); done.set_result(None); return done
        _recent[identity] = digest
        if len(_recent) > 512: _recent.pop(next(iter(_recent)))
    queued_at = time.monotonic()

    def run_narration(generation: int) -> None:
        if not attachments and time.monotonic() - queued_at > 45: return
        with studio_flags.working(user_key, conversation_id):
            _stream(conversation_id, user_key, kind, facts, attachments, fallback, generation)

    # Keep authenticated Gateway accounting/cancellation context in the worker.
    context = contextvars.copy_context()
    job = _executor(conversation_id).submit(context.run, run_narration, generation)
    if not background:
        job.result()
    return job
