"""A title for a new chat, made from its first message.

The Lite path titled chats while it classified the request; chats run by the Medium agent never went through that code and all stayed
"New media edit". This runs beside the agent, never delays it, never replaces a title the person set, and always ends with some title.
"""
from __future__ import annotations

import logging
import re
import threading

log = logging.getLogger(__name__)

AUTOMATIC = {"گفتگوی جدید", "New media edit", "New edit", ""}
_URL = re.compile(r"https?://\S+")
_MARKER = re.compile(r"^\s*\[موتور:\s*[^\]]*\]")
_SYSTEM = ('Write a concise, specific conversation title of 3 to 7 words for a video-editor chat, from the person\'s first message. '
           'Use the language of the message (Persian if it is written in Persian, English if it is English). Describe the subject and the goal. '
           'No quotes, no URLs, no generic words like "New edit", nothing invented. Return only JSON {"title": "..."}.')


def fallback_title(text: str) -> str:
    """The first meaningful words of the message: directive lines, links and routing tags are not part of a title."""
    from creative import directives
    body = _URL.sub(" ", _MARKER.sub("", text or ""))
    body = directives.parse(body)[0]
    for line in body.splitlines():
        words = re.sub(r"\s+", " ", re.sub(r"[*`]+", "", re.sub(r"^[#>\-–—*\s]+", "", line))).strip().split()
        if len(words) >= 2:
            return " ".join(words[:8])[:100]
    return "ساخت ویدیو"


def make_title(text: str) -> str:
    try:
        from brain.lm_gateway import configured
        if configured():
            from brain.llm import gateway_json
            result, _ = gateway_json(_SYSTEM, (text or "")[:1500], "intent_classification", 300)
            title = _URL.sub(" ", str(result.get("title") or "")).replace("\n", " ").strip(' "«»\'')[:100]
            if len(title.split()) >= 2:
                return title
    except Exception as exc:
        log.info("chat title from the model failed (%s); using the message itself", type(exc).__name__)
    return fallback_title(text)


def title_chat(conversation_id: str, user: str, text: str) -> bool:
    """Title the chat when this is its first message and the title is still automatic. True when a title was set."""
    from app.studio_store import repo, run
    try:
        conversation = run(repo.get_conversation(conversation_id, user))
        current = conversation.get("title", "")
        users = [m for m in conversation.get("messages", []) if m["role"] == "user"]
        clean = _MARKER.sub("", text or "").strip()
        if len(users) != 1 or not (current in AUTOMATIC or current == clean[:70] or current == (text or "")[:70]):
            return False
        title = make_title(clean)
        latest = run(repo.get_conversation(conversation_id, user))
        if latest.get("title", "") != current:                      # renamed while the model was answering
            return False
        run(repo.set_conversation(conversation_id, user, title=title))
        from app.studio_orchestrator import _emit
        _emit(conversation_id, "conversation.updated", title=title)
        return True
    except Exception:
        log.warning("chat title not set", exc_info=True)
        return False


def title_in_background(conversation_id: str, user: str, text: str) -> None:
    threading.Thread(target=title_chat, args=(conversation_id, user, text), daemon=True, name="chat-title").start()
