"""Which speech-to-text a person wants for their videos: chosen automatically, always ElevenLabs (cloud, fast, paid by the hour), or always local Whisper
on the server (free, slower; the model size is theirs to choose). One small file per person next to their Studio data."""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

ENGINES = ("auto", "elevenlabs", "whisper")
WHISPER_MODELS = ("", "base", "small", "medium", "large-v3")          # "" lets the server pick for the length of the video
DEFAULT = {"engine": "auto", "whisper_model": ""}
ELEVENLABS_USD_PER_HOUR = 0.40                                         # the rate used for the cost shown (brain.transcribe_elevenlabs.COST_PER_SECOND)


def _path(user: str) -> Path:
    from app import studio_store
    return studio_store.ROOT / re.sub(r"[^A-Za-z0-9_-]", "_", str(user)) / "transcription.json"


def get(user: str | None) -> dict:
    if not user:
        return dict(DEFAULT)
    try:
        saved = json.loads(_path(user).read_text())
    except (OSError, ValueError):
        return dict(DEFAULT)
    engine = saved.get("engine") if saved.get("engine") in ENGINES else DEFAULT["engine"]
    model = saved.get("whisper_model") if saved.get("whisper_model") in WHISPER_MODELS else DEFAULT["whisper_model"]
    return {"engine": engine, "whisper_model": model}


def put(user: str, engine: str, whisper_model: str = "") -> dict:
    if engine not in ENGINES or whisper_model not in WHISPER_MODELS:
        raise ValueError("unsupported transcription setting")
    path = _path(user)
    path.parent.mkdir(parents=True, exist_ok=True)
    value = {"engine": engine, "whisper_model": whisper_model}
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, suffix=".part") as handle:
        json.dump(value, handle)
    os.replace(handle.name, path)
    return value


def estimate_usd(seconds: float) -> float:
    return round(seconds / 3600 * ELEVENLABS_USD_PER_HOUR, 2)
