"""Sound of the intro engines: the beat grid of a music bed, and the mix (effects on the picture's events, music, narration with ducking, -14 LUFS).

The picture and the sound share one source of time: the events list an engine's `plan()` returns is what the template shows and what is mixed here.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)
HERE = Path(__file__).resolve().parent
SFX = HERE / "kit" / "sfx"
MUSIC = HERE / "kit" / "music"
SR = 48000


def decode(path: Path | str, rate: int = SR, channels: int = 2) -> np.ndarray:
    """Any audio file as float32 samples (frames, channels)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ar", str(rate), "-ac", str(channels), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, channels).copy()


def beat_grid(music: Path | str | np.ndarray, rate: int = 22050) -> dict:
    """The beat grid of a track: {"period": seconds per beat, "first": the first strong low hit, "bpm"}; B(n) = first + period * (n - 1).

    Spectral flux of a 1024/256 STFT -> autocorrelation between 0.3 and 1.0 s gives the period; the first beat is the first clear rise of the
    eight lowest bins that the rest of the low hits agree with (the kick)."""
    x = decode(music, rate, 1)[:, 0] if not isinstance(music, np.ndarray) else np.asarray(music, dtype=np.float32)
    win, hop = 1024, 256
    if len(x) < win * 8:
        raise ValueError("the track is too short for a beat grid")
    frames = 1 + (len(x) - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(frames)[:, None]
    spec = np.abs(np.fft.rfft(x[idx] * np.hanning(win)[None, :], axis=1))
    flux = np.maximum(np.diff(spec, axis=0), 0).sum(axis=1)
    flux = flux - flux.mean()
    step = hop / rate
    lo, hi = int(round(0.3 / step)), int(round(1.0 / step))
    n = len(flux)
    size = 1 << int(np.ceil(np.log2(2 * n)))
    power = np.abs(np.fft.rfft(flux, size)) ** 2
    ac = np.fft.irfft(power)[:hi + 2]
    lag = lo + int(np.argmax(ac[lo:hi + 1]))
    if 0 < lag < len(ac) - 1:                                   # parabolic refinement of the peak
        a, b, c = ac[lag - 1], ac[lag], ac[lag + 1]
        denom = a - 2 * b + c
        frac = 0.5 * (a - c) / denom if abs(denom) > 1e-12 else 0.0
    else:
        frac = 0.0
    period = (lag + frac) * step
    # the kick: rises of the low bins
    low = np.maximum(np.diff(spec[:, :8].sum(axis=1)), 0)
    if low.max() <= 0:
        first = 0.0
    else:
        strong = np.where(low > 0.35 * low.max())[0]
        # the phase that most of the strong low hits share
        phases = (strong * step) % period
        hist, edges = np.histogram(phases, bins=24, range=(0, period))
        centre = (edges[int(np.argmax(hist))] + edges[int(np.argmax(hist)) + 1]) / 2
        near = [i for i in strong if min(abs((i * step) % period - centre), period - abs((i * step) % period - centre)) < period * 0.12]
        onset = float((near[0] if near else strong[0]) + 1) * step + 0.012                         # the frame that first holds the hit starts just before it
        first = onset % period
        while first < 0.3:                                       # B(1) is the first grid point with a short lead-in before it
            first += period
    return {"period": round(float(period), 4), "first": round(float(first), 3), "bpm": round(float(60.0 / period), 1)}


def _norm(a: np.ndarray, peak: float = 0.9) -> np.ndarray:
    return a / (np.abs(a).max() + 1e-9) * peak


def mix(out: Path, *, total: float, events: list[dict], music: Path | None, music_gain: float, fade: float, voice: list[dict] | None = None,
        music_offset: float = 0.0) -> dict:
    """events: [{"t", "k", "g"}] (k = a file of kit/sfx); voice: [{"path", "start"}]; music at `music_gain`, ducked under the voice (60 % down, attack 60 ms,
    release 450 ms); fade-in 0.15 s and `fade` s out; two-pass loudnorm to -14 LUFS, true peak -1.5, then a limiter. Returns the measured input loudness."""
    out.parent.mkdir(parents=True, exist_ok=True)
    n = int(total * SR)
    buf = np.zeros((n + SR * 4, 2), np.float32)
    cache: dict[str, np.ndarray] = {}

    def add(target: np.ndarray, clip: np.ndarray, t: float, gain: float = 1.0) -> None:
        i = int(max(0.0, t) * SR)
        if i >= len(target):
            return
        clip = clip[:len(target) - i] * gain
        target[i:i + len(clip)] += clip

    for e in events:
        key = str(e.get("k", ""))
        path = SFX / f"{key}.mp3"
        if not path.is_file():
            continue
        if key not in cache:
            cache[key] = _norm(decode(path))
        add(buf, cache[key], float(e["t"]), float(e.get("g", 0.6)) * 0.7)
    spoken = np.zeros_like(buf)
    for v in voice or []:
        add(spoken, decode(v["path"]), float(v["start"]))
    has_voice = bool(voice) and float(np.abs(spoken).max()) > 0
    if has_voice:
        spoken = _norm(spoken, 0.85)
    bed = np.zeros_like(buf)
    if music and Path(music).is_file():
        track = decode(music)[int(music_offset * SR):]
        track = np.pad(track, ((0, max(0, len(buf) - len(track))), (0, 0)))[:len(buf)]
        bed = _norm(track, 0.9)
        tt = np.arange(len(buf)) / SR
        bed *= (np.clip(tt / 0.15, 0, 1) * np.clip((total - tt) / max(fade, 0.05), 0, 1))[:, None]
    gain = np.ones(len(buf), np.float32)
    if has_voice:
        env = np.abs(spoken).mean(axis=1)
        w = int(0.05 * SR)
        env = np.convolve(env, np.ones(w) / w, "same")
        on = (env > 0.01).astype(np.float32)[::48]
        a1, r1 = np.exp(-48 / (0.06 * SR)), np.exp(-48 / (0.45 * SR))
        x, steps = 0.0, np.empty(len(on), np.float32)
        for i, target in enumerate(on):
            x = target + (x - target) * (a1 if target > x else r1)
            steps[i] = 1 - 0.6 * x
        gain = np.repeat(steps, 48)[:len(buf)]
        if len(gain) < len(buf):
            gain = np.pad(gain, (0, len(buf) - len(gain)), constant_values=1.0)
    mixed = (spoken + buf * 0.6 + bed * music_gain * gain[:, None])[:n]
    raw = out.with_name(out.stem + "_raw.f32")
    raw.write_bytes(mixed.astype(np.float32).tobytes())
    source = ["-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", str(raw)]
    try:
        log_text = subprocess.run(["ffmpeg", "-hide_banner", *source, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                                  capture_output=True, text=True, check=True).stderr
        measured = json.loads(log_text[log_text.rindex("{"):])
        chain = (f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:measured_LRA={measured['input_lra']}:"
                 f"measured_thresh={measured['input_thresh']}:offset={measured['target_offset']}:linear=true,alimiter=limit=0.84:level=false")
        subprocess.run(["ffmpeg", "-v", "error", "-y", *source, "-af", chain, "-ar", "48000", str(out)], check=True)
    finally:
        raw.unlink(missing_ok=True)
    return {"input_lufs": measured.get("input_i"), "events": len(events), "voice": has_voice}
