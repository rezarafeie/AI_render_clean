"""Words that are still being written reach the open chat at once, not through the database.

A streamed answer used to be saved as an event for every few words: each save took a third of a second or more on a busy server, so the words queued up
behind the writes and arrived in bursts. The text is cumulative and the finished message is saved anyway, so the running text is only passed on in memory to
the chats that are open (one server process). The started/completed events are still saved.
"""
from __future__ import annotations

import asyncio
import collections
import itertools
import json
import os
import threading
import time
import uuid
from typing import Any

_LOCK = threading.Lock()
_COUNTER = itertools.count(1)
_RECENT: dict[str, "collections.deque[dict]"] = {}
_WAITERS: dict[str, list[tuple[asyncio.AbstractEventLoop, asyncio.Event]]] = {}
KEEP = 64
MAX_AGE = 120.0


_ORIGIN = uuid.uuid4().hex                      # this process; a message that came back from Redis with this origin is already local
_CHANNEL = "editorgpt:studio-live"
_client = None
_listener_started = False


def _redis():
    """The Redis client shared by the processes of the studio (None when there is no Redis: then streaming works inside one process only)."""
    global _client
    if _client is None:
        url = os.environ.get("REDIS_URL", "").strip()
        if not url:
            return None
        import redis
        _client = redis.Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2)
    return _client


def _relay(conversation_id: str, event_type: str, data: dict[str, Any]) -> None:
    """The studio's work often runs in the worker process while the open chats are served by the app process: the running text goes through Redis so both see it."""
    try:
        client = _redis()
        if client is not None:
            client.publish(_CHANNEL, json.dumps({"o": _ORIGIN, "c": conversation_id, "t": event_type, "d": data}, ensure_ascii=False))
    except Exception:
        pass                                                      # streaming is a courtesy: the finished message is saved anyway


def _listen() -> None:
    while True:
        try:
            client = _redis()
            if client is None:
                return
            pubsub = client.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(_CHANNEL)
            for message in pubsub.listen():
                try:
                    item = json.loads(message["data"])
                    if item.get("o") != _ORIGIN:
                        publish(item["c"], item["t"], item["d"], relay=False)
                except Exception:
                    continue
        except Exception:
            time.sleep(2)                                         # Redis restarted: subscribe again


def start_listener() -> None:
    """Called by the process that serves the chats' streams: it hears what other processes (the worker) publish."""
    global _listener_started
    with _LOCK:
        if _listener_started or not os.environ.get("REDIS_URL", "").strip():
            return
        _listener_started = True
    threading.Thread(target=_listen, name="studio-live-listener", daemon=True).start()


def publish(conversation_id: str, event_type: str, data: dict[str, Any], relay: bool = True) -> int:
    """Hand a running piece of text to every open stream of the chat (callable from any thread). Returns its live number."""
    if relay:
        _relay(conversation_id, event_type, data)
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
        start_listener()
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
