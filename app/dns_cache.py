"""A small DNS cache for the few hosts this app depends on.

The containers' resolver (Docker -> the host's upstream) intermittently fails or takes seconds for these names, and every
failed lookup used to end a narration, a model call or a sync. Successful answers are kept for a few minutes, a failed
lookup is retried once, and when it still fails the last good answer is used instead of an error. Other hosts are untouched.
"""
from __future__ import annotations

import socket
import threading
import time

_original = socket.getaddrinfo
_installed = False
_lock = threading.Lock()
_entries: dict[tuple, tuple[float, list]] = {}


def install(hosts: set[str], ttl: float = 300.0) -> None:
    global _installed
    wanted = {h.strip().lower() for h in hosts if h.strip()}
    if _installed or not wanted:
        return

    def cached(host, port, family=0, type=0, proto=0, flags=0):
        name = host.decode() if isinstance(host, bytes) else host
        if not isinstance(name, str) or name.lower() not in wanted:
            return _original(host, port, family, type, proto, flags)
        key = (name.lower(), port, family, type, proto, flags)
        now = time.monotonic()
        with _lock:
            entry = _entries.get(key)
        if entry and entry[0] > now:
            return list(entry[1])
        try:
            result = _original(host, port, family, type, proto, flags)
        except socket.gaierror:
            time.sleep(0.2)
            try:
                result = _original(host, port, family, type, proto, flags)
            except socket.gaierror:
                if entry:
                    return list(entry[1])            # the last good answer beats a failed lookup
                raise
        with _lock:
            _entries[key] = (now + ttl, list(result))
        return result

    socket.getaddrinfo = cached
    _installed = True


def reset_for_tests() -> None:
    global _installed
    socket.getaddrinfo = _original
    _installed = False
    _entries.clear()
