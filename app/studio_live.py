"""Words that are still being written reach the open chat at once, not through the database.

A streamed answer used to be saved as an event for every few words: each save took a third of a second or more on a busy server, so the words queued up
behind the writes and arrived in bursts. The text is cumulative and the finished message is saved anyway, so the running text is only passed on in memory to
the chats that are open (one server process). The started/completed events are still saved.
"""
from __future__ import annotations

import asyncio
import collections
import itertools
import threading
import time
from typing import Any

_LOCK = threading.Lock()
_COUNTER = itertools.count(1)
_RECENT: dict[str, "collections.deque[dict]"] = {}
_WAITERS: dict[str, list[tuple[asyncio.AbstractEventLoop, asyncio.Event]]] = {}
KEEP = 64
MAX_AGE = 120.0


def publish(conversation_id: str, event_type: str, data: dict[str, Any]) -> int:
    """Hand a running piece of text to every open stream of the chat (callable from any thread). Returns its live number."""
    number = next(_COUNTER)
    entry = {"live": number, "type": event_type, "data": data, "at": time.monotonic()}
    with _LOCK:
        queue = _RECENT.setdefault(conversation_id, collections.deque(maxlen=KEEP))
        queue.append(entry)
        waiting = list(_WAITERS.get(conversation_id, []))
    for loop, flag in waiting:
        try:
            loop.call_soon_threadsafe(flag.set)
        except RuntimeError:
            pass                                                  # that stream's loop has gone
    return number


def since(conversation_id: str, number: int) -> list[dict]:
    """The live pieces newer than `number`, oldest first, only the newest piece of each running text (the text is cumulative)."""
    cutoff = time.monotonic() - MAX_AGE
    with _LOCK:
        fresh = [item for item in _RECENT.get(conversation_id, ()) if item["live"] > number and item["at"] >= cutoff]
    latest: dict[Any, dict] = {}
    for item in fresh:
        latest[item["data"].get("response_id")] = item
    return sorted(latest.values(), key=lambda item: item["live"])


def newest(conversation_id: str) -> int:
    with _LOCK:
        queue = _RECENT.get(conversation_id)
        return queue[-1]["live"] if queue else 0


class Subscription:
    """An open stream's way of being woken when something is published for its chat."""

    def __init__(self, conversation_id: str):
        self.conversation_id = conversation_id
        self.flag = asyncio.Event()
        self._entry = (asyncio.get_running_loop(), self.flag)
        with _LOCK:
            _WAITERS.setdefault(conversation_id, []).append(self._entry)

    async def wait(self, timeout: float) -> None:
        try:
            await asyncio.wait_for(self.flag.wait(), timeout)
        except asyncio.TimeoutError:
            pass
        self.flag.clear()

    def close(self) -> None:
        with _LOCK:
            waiting = _WAITERS.get(self.conversation_id, [])
            if self._entry in waiting:
                waiting.remove(self._entry)
            if not waiting:
                _WAITERS.pop(self.conversation_id, None)
