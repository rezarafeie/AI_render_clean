"""Heavy background work (renders, discovery, clean-base builds) runs in threads of the same process that answers the API.

Linux applies a nice value to the calling thread only, and every ffmpeg started from that thread inherits it, so wrapping a worker's entry point is enough:
the renders still use all the spare CPU, but the pages and API calls of the people using the app go first when the machine is busy.
"""
from __future__ import annotations

import functools
import os

NICE = int(os.environ.get("BACKGROUND_NICE", "10"))


def wrap(function):
    @functools.wraps(function)
    def run(*args, **kwargs):
        try:
            os.nice(NICE)
        except (AttributeError, OSError):
            pass
        return function(*args, **kwargs)
    return run
