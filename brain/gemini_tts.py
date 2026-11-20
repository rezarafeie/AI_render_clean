"""Narration with Gemini text-to-speech, through the approved Gemini relay (the relay owns the Google key; the server sends only the relay secret).

A narrator id "gemini:<Voice>" (one of VOICES) selects it everywhere a narrator is picked: the motion / vox / intro / Pro takes (creative.audio.narrate via
claude_motion._tts), the localize and motion-graphic narration (brain.localize), the studio's gateway narration (brain.tts) and the voice test.

Gemini returns raw audio without timestamps. The engines time the film on character timestamps, so the text is read one sentence per request (in parallel)
and the timestamps are built from the audio itself: each sentence's voiced span is measured, and its characters are spread over that span. Sentence and line
edges are therefore exact; a word inside a sentence is placed by its share of the sentence's letters.
"""
from __future__ import annotations

import array
import base64
import concurrent.futures
import logging
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

PREFIX = "gemini:"
RELAY = "https://rafiei-telegram-api-relay.vercel.app/api/gemini"
RATE = 24000                    # Gemini TTS: 16-bit mono PCM at 24 kHz
GAP_S = 0.28                    # silence placed between two sentences of one take
MAX_PIECE = 900                 # characters per request; longer sentences are cut at a comma or a space

# (voice, Persian name shown in the pickers, what it sounds like). Gemini voices are multilingual and read Persian.
VOICES = (
    ("Charon", "Gemini · شارون", "مرد، آگاه و روشن"),
    ("Orus", "Gemini · اوروس", "مرد، محکم و جدی"),
    ("Iapetus", "Gemini · یاپتوس", "مرد، شفاف و آرام"),
    ("Algieba", "Gemini · الجیبا", "مرد، نرم و گرم"),
    ("Rasalgethi", "Gemini · راس‌الجاثی", "مرد، مستندگو"),
    ("Puck", "Gemini · پاک", "مرد، پرانرژی و شاد"),
    ("Fenrir", "Gemini · فنریر", "مرد، هیجان‌زده"),
    ("Achird", "Gemini · اخیرد", "مرد، صمیمی"),
    ("Kore", "Gemini · کوره", "زن، محکم و روشن"),
    ("Sulafat", "Gemini · سولافات", "زن، گرم"),
    ("Despina", "Gemini · دسپینا", "زن، نرم و روان"),
    ("Aoede", "Gemini · آئوده", "زن، سبک و دلنشین"),
    ("Leda", "Gemini · لدا", "زن، جوان"),
    ("Vindemiatrix", "Gemini · ویندمیاتریکس", "زن، ملایم و مهربان"),
    ("Gacrux", "Gemini · گاکروکس", "زن، پخته و باوقار"),
    ("Zephyr", "Gemini · زفیر", "زن، روشن و سرزنده"),
)
NAMES = {name for name, _, _ in VOICES}

# The studio's delivery tags (brain.localize.VOICE_STYLES, written for ElevenLabs) said to Gemini in words.
_TAG_WORDS = {
    "thoughtful": "thoughtful", "emotional": "emotional and moving", "calm": "calm", "softly": "soft and intimate", "excited": "excited",
    "energetic": "energetic", "happy": "happy", "cheerful": "cheerful", "serious": "serious", "confident": "confident", "warm": "warm",
    "whispers": "whispered", "sad": "sad", "dramatic": "dramatic", "curious": "curious", "friendly": "friendly", "professional": "professional",
}
_TAG = re.compile(r"\[([^\]]{1,40})\]\s*")
_SENTENCE = re.compile(r"(?<=[.!?؟…])\s+|\n+")


def is_gemini(voice: str | None) -> bool:
    return str(voice or "").startswith(PREFIX)


def model() -> str:
    return os.environ.get("GEMINI_TTS_MODEL", "").strip() or "gemini-3.1-flash-tts-preview"


def narrators() -> list[tuple[str, str, str]]:
    """The narrator rows the pickers list: (id, name, note)."""
    return [(PREFIX + name, label, note) for name, label, note in VOICES]


def voice_name(voice: str) -> str:
    name = str(voice or "")[len(PREFIX):] if is_gemini(voice) else str(voice or "")
    if name not in NAMES:
        raise ValueError(f"unknown Gemini voice: {name or '(empty)'}")
    return name


def _direction(tags: list[str]) -> str:
    words = [_TAG_WORDS.get(t.strip().lower(), t.strip().lower()) for t in tags if t.strip()]
    tone = ", ".join(dict.fromkeys(w for w in words if re.fullmatch(r"[a-z \-]{2,40}", w)))
    return f"Read aloud as a natural narrator, in a {tone} tone" if tone else "Read aloud as a natural, clear narrator"


def _request(text: str, voice: str, direction: str) -> bytes:
    """One synthesis: 16-bit PCM. A refused request (rate limit, a busy model) is not billed, so it is tried again a few times."""
    from app.config import settings
    secret = settings.GEMINI_RELAY_SECRET
    if not secret:
        raise RuntimeError("Gemini relay secret is not configured")
    prompt = f"{direction}. Read only the text after the colon, word for word:\n{text}"
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_name(voice)}}}}}
    headers = {"Content-Type": "application/json", "x-relay-secret": secret, "x-gemini-model": model()}
    last = ""
    for attempt, wait in enumerate((0, 4, 10, 20)):
        if wait:
            time.sleep(wait)
        try:
            response = httpx.post(RELAY, json=body, headers=headers, timeout=httpx.Timeout(120.0, connect=20.0))
        except httpx.HTTPError as exc:
            last = f"{type(exc).__name__}: {exc}"
            continue
        if response.status_code in (429, 500, 502, 503, 504):
            last = f"HTTP {response.status_code}: {response.text[:160]}"
            continue
        if response.status_code >= 400:
            raise RuntimeError(f"Gemini TTS refused the request (HTTP {response.status_code}): {response.text[:200]}")
        try:
            parts = response.json()["candidates"][0]["content"]["parts"]
            data = next(p["inlineData"]["data"] for p in parts if p.get("inlineData", {}).get("data"))
        except (KeyError, IndexError, StopIteration, ValueError):
            last = f"no audio in the answer: {response.text[:160]}"
            continue
        pcm = base64.b64decode(data)
        if len(pcm) < RATE // 5:
            last = "the answer's audio is shorter than 0.1 s"
            continue
        return pcm
    raise RuntimeError(f"Gemini TTS gave no audio after retries ({last})")


def _voiced(pcm: bytes) -> tuple[int, int]:
    """First and last loud sample (start inclusive, end exclusive), with a little air kept at both ends."""
    samples = array.array("h", pcm[: len(pcm) // 2 * 2])
    if not samples:
        return 0, 0
    loud = 600
    window = RATE // 100
    first = next((i for i in range(0, len(samples), window) if max(abs(x) for x in samples[i:i + window]) > loud), 0)
    last = next((i + window for i in range(len(samples) - window, -1, -window) if max(abs(x) for x in samples[max(0, i):i + window]) > loud), len(samples))
    return max(0, first - int(RATE * 0.04)), min(len(samples), last + int(RATE * 0.08))


def _pieces(text: str) -> list[tuple[int, int]]:
    """(start, end) of each sentence in ``text`` (whitespace around them excluded); a very long sentence is cut at a comma or a space."""
    out: list[tuple[int, int]] = []
    pos = 0
    for found in list(_SENTENCE.finditer(text)) + [None]:
        end = found.start() if found else len(text)
        a, b = pos, end
        while a < b and text[a].isspace():
            a += 1
        while b > a and text[b - 1].isspace():
            b -= 1
        while b - a > MAX_PIECE:
            cut = max(text.rfind("،", a, a + MAX_PIECE), text.rfind(",", a, a + MAX_PIECE))
            cut = cut + 1 if cut > a else (text.rfind(" ", a, a + MAX_PIECE) if text.rfind(" ", a, a + MAX_PIECE) > a else a + MAX_PIECE)
            out.append((a, cut))
            a = cut
            while a < b and text[a].isspace():
                a += 1
        if b > a and _TAG.sub("", text[a:b]).strip():
            out.append((a, b))
        if found:
            pos = found.end()
    return out


def _weight(ch: str) -> float:
    if ch.isspace():
        return 0.6
    if ch in "،,؛;:":
        return 2.5
    if ch in ".!?؟…":
        return 3.0
    return 1.0


def synthesize(text: str, voice: str) -> tuple[bytes, dict]:
    """The whole text read sentence by sentence. Returns (16-bit PCM at 24 kHz, ElevenLabs-shaped alignment over every character of ``text``)."""
    voice_name(voice)
    pieces = _pieces(text)
    if not pieces:
        raise RuntimeError("there is no text to read")
    tags_before: list[list[str]] = []
    spoken: list[str] = []
    active: list[str] = []
    for a, b in pieces:
        found = _TAG.findall(text[a:b])
        if found:
            active = found                                  # a tag sets the tone until the next one, as in one ElevenLabs take
        tags_before.append(list(active))
        spoken.append(" ".join(_TAG.sub("", text[a:b]).split()))
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(pieces))) as pool:
        audios = list(pool.map(lambda k: _request(spoken[k], voice, _direction(tags_before[k])), range(len(pieces))))
    tag = [False] * len(text)
    for found in _TAG.finditer(text):
        for i in range(found.start(), found.end()):
            tag[i] = True
    gap = b"\x00\x00" * int(RATE * GAP_S)
    out = bytearray()
    starts = [0.0] * len(text)
    ends = [0.0] * len(text)
    for k, ((a, b), pcm) in enumerate(zip(pieces, audios)):
        if k:
            out += gap
        v0, v1 = _voiced(pcm)
        offset = len(out) / 2 / RATE
        out += pcm[v0 * 2:v1 * 2]
        lead = int(RATE * 0.04) if v0 else 0
        t0 = offset + lead / RATE
        t1 = offset + (v1 - v0) / RATE - (0.08 if v1 < len(pcm) // 2 else 0.0)
        chars = {i for i in range(a, b) if not tag[i]}
        total = sum(_weight(text[i]) for i in chars) or 1.0
        clock = t0
        for i in range(a, b):
            if i in chars:
                step = (t1 - t0) * _weight(text[i]) / total
                starts[i], ends[i] = clock, clock + step
                clock += step
            else:
                starts[i] = ends[i] = clock
    # characters between pieces (spaces, newlines) sit at the edge of the piece before them
    last = 0.0
    for i in range(len(text)):
        if ends[i] == 0.0 and starts[i] == 0.0 and i:
            starts[i] = ends[i] = last
        last = ends[i]
    return bytes(out), {"characters": list(text), "character_start_times_seconds": [round(x, 3) for x in starts],
                        "character_end_times_seconds": [round(x, 3) for x in ends]}


def encode(pcm: bytes, target: Path) -> Path:
    """PCM to a file whose format is its extension (.mp3 / .wav)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".pcm", delete=False) as raw:
        raw.write(pcm)
    try:
        codec = ["-c:a", "libmp3lame", "-b:a", "128k", "-ar", "44100"] if target.suffix.lower() == ".mp3" else ["-ar", "48000"]
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(RATE), "-ac", "1", "-i", raw.name, *codec, str(target)], check=True, capture_output=True)
    finally:
        os.unlink(raw.name)
    return target


def speak_with_timestamps(text: str, voice: str) -> tuple[bytes, dict]:
    """(mp3 bytes, alignment): the drop-in for ElevenLabs' text-to-speech/with-timestamps."""
    pcm, alignment = synthesize(text, voice)
    with tempfile.TemporaryDirectory() as folder:
        mp3 = encode(pcm, Path(folder) / "take.mp3")
        return mp3.read_bytes(), alignment


def speak(text: str, voice: str, target: Path) -> Path:
    """The text read into ``target`` (.mp3 or .wav)."""
    pcm, _ = synthesize(text, voice)
    return encode(pcm, Path(target))
