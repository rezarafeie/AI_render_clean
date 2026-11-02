"""Musical rhythm from the audio itself: tempo, beats, onsets, energy peaks and section changes.

numpy only (no librosa, no new dependency): ffmpeg decodes, a spectral-flux onset envelope feeds an autocorrelation tempo
estimate, and the beat grid takes the phase that best matches the onsets. Tempo has a confidence value, downbeats are
returned only when they are distinguishable from the other beats, and everything is in integer milliseconds.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np

from .contracts import AudioTimingEvent, ms

SR, N_FFT, HOP = 22050, 1024, 512
FRAME_S = HOP / SR


def decode(path: Path, max_seconds: int = 600) -> np.ndarray:
    done = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-t", str(max_seconds), "-ac", "1", "-ar", str(SR), "-f", "f32le", "pipe:1"],
                          capture_output=True, timeout=300)
    if done.returncode != 0 or not done.stdout:
        raise ValueError("the audio could not be decoded")
    return np.frombuffer(done.stdout, dtype=np.float32)


def _spectrogram(samples: np.ndarray) -> np.ndarray:
    if len(samples) < N_FFT * 4:
        raise ValueError("the audio is too short to analyse")
    count = 1 + (len(samples) - N_FFT) // HOP
    index = np.arange(N_FFT)[None, :] + HOP * np.arange(count)[:, None]
    return np.abs(np.fft.rfft(samples[index] * np.hanning(N_FFT), axis=1))


def _onset_envelope(spec: np.ndarray) -> np.ndarray:
    logmag = np.log1p(spec * 10)
    flux = np.maximum(0.0, np.diff(logmag, axis=0)).sum(axis=1)
    flux = np.concatenate([[0.0], flux])
    window = max(3, int(0.5 / FRAME_S))
    local = np.convolve(flux, np.ones(window) / window, mode="same")
    env = np.maximum(flux - local, 0.0)
    top = env.max()
    return env / top if top > 0 else env


def _peaks(values: np.ndarray, threshold: float, min_gap: int) -> list[int]:
    found: list[int] = []
    for i in range(1, len(values) - 1):
        if values[i] >= threshold and values[i] >= values[i - 1] and values[i] > values[i + 1]:
            if found and i - found[-1] < min_gap:
                if values[i] > values[found[-1]]:
                    found[-1] = i
            else:
                found.append(i)
    return found


def _tempo(env: np.ndarray) -> tuple[float, float]:
    centred = env - env.mean()
    if not np.any(centred):
        return 0.0, 0.0
    size = 1 << (2 * len(centred) - 1).bit_length()
    spectrum = np.fft.rfft(centred, size)
    ac = np.fft.irfft(spectrum * np.conj(spectrum))[:len(centred)]
    ac = ac / ac[0]
    best, best_score = 0.0, -1.0
    for bpm in np.arange(60.0, 180.5, 0.5):
        lag = 60.0 / bpm / FRAME_S
        low, high = int(np.floor(lag)), int(np.ceil(lag))
        if high >= len(ac):
            continue
        value = ac[low] + (ac[high] - ac[low]) * (lag - low)
        weight = np.exp(-0.5 * (np.log2(bpm / 110.0) / 0.9) ** 2)        # people favour tempos near 110
        if value * weight > best_score:
            best, best_score = float(bpm), float(value * weight)
    def at(bpm: float) -> float:
        position = 60.0 / bpm / FRAME_S
        return float(ac[int(round(position))]) if int(round(position)) < len(ac) else 0.0
    # Tempo is ambiguous by a factor of two; a slow pick whose double is almost as strong in the signal is the double
    if best and best < 85 and best * 2 <= 180 and at(best * 2) >= 0.75 * at(best):
        best = best * 2
    lag = 60.0 / best / FRAME_S if best else 0
    centre = int(round(lag))
    confidence = float(np.clip(ac[centre], 0.0, 1.0)) if best and centre < len(ac) else 0.0
    if best and 1 < centre < len(ac) - 1:
        # the lag grid is one frame (~23 ms) wide: a parabola through the peak gives a sub-frame period
        left, mid, right = ac[centre - 1], ac[centre], ac[centre + 1]
        denominator = left - 2 * mid + right
        shift = 0.5 * (left - right) / denominator if denominator else 0.0
        refined = 60.0 / ((centre + float(np.clip(shift, -1, 1))) * FRAME_S)
        if 60.0 <= refined <= 180.0:
            best = refined
    return best, confidence


def _beat_frames(env: np.ndarray, bpm: float) -> list[int]:
    period = 60.0 / bpm / FRAME_S
    best_offset, best_score = 0, -1.0
    for offset in range(int(period)):
        positions = np.round(offset + period * np.arange(int((len(env) - offset) / period))).astype(int)
        positions = positions[positions < len(env)]
        score = env[positions].sum()
        if score > best_score:
            best_offset, best_score = offset, score
    positions = np.round(best_offset + period * np.arange(int((len(env) - best_offset) / period))).astype(int)
    refined = []
    for p in positions[positions < len(env)]:
        window = env[max(0, p - 2):p + 3]
        refined.append(int(max(0, p - 2) + int(np.argmax(window))))
    return refined


def _downbeats(spec: np.ndarray, beat_frames: list[int]) -> tuple[list[int], bool]:
    """Assume 4/4 and keep the beat phase with the most low-frequency weight, only when it clearly stands out."""
    if len(beat_frames) < 12:
        return [], False
    bass = spec[:, 1:10].sum(axis=1)
    weights = np.array([bass[min(f, len(bass) - 1)] for f in beat_frames])
    phases = [weights[p::4].mean() for p in range(4)]
    order = np.argsort(phases)[::-1]
    if phases[order[0]] < 1.15 * phases[order[1]]:
        return [], False
    return beat_frames[int(order[0])::4], True


def _energy(samples: np.ndarray) -> np.ndarray:
    size = SR  # one value per second
    count = len(samples) // size
    if count == 0:
        return np.array([float(np.sqrt(np.mean(samples ** 2)))])
    rms = np.sqrt(np.mean(samples[:count * size].reshape(count, size) ** 2, axis=1))
    return rms / rms.max() if rms.max() > 0 else rms


def analyse(path: Path, cache_dir: Path | None = None) -> dict:
    path = Path(path)
    key = hashlib.sha1(f"{path.name}|{path.stat().st_size}|{int(path.stat().st_mtime)}|v1".encode()).hexdigest()[:16]
    if cache_dir:
        cached = Path(cache_dir) / f"rhythm-{key}.json"
        try:
            return json.loads(cached.read_text())
        except (OSError, ValueError):
            pass
    samples = decode(path)
    spec = _spectrogram(samples)
    env = _onset_envelope(spec)
    onsets = _peaks(env, float(env.mean() + 0.7 * env.std()), max(2, int(0.1 / FRAME_S)))
    bpm, confidence = _tempo(env)
    beats = _beat_frames(env, bpm) if bpm else []
    downbeats, reliable = _downbeats(spec, beats)
    energy = _energy(samples)
    smooth = np.convolve(energy, np.ones(3) / 3, mode="same") if len(energy) >= 3 else energy
    peaks = _peaks(smooth, float(np.percentile(smooth, 80)), 2) if len(smooth) > 4 else []
    jumps = [int(i) for i in range(2, len(smooth) - 2) if abs(smooth[i:i + 2].mean() - smooth[i - 2:i].mean()) > max(0.2, float(np.std(smooth)))]
    result = {"duration_ms": ms(len(samples) / SR), "bpm": round(bpm, 1), "bpm_confidence": round(confidence, 3),
              "beats_ms": [ms(f * FRAME_S) for f in beats], "downbeats_ms": [ms(f * FRAME_S) for f in downbeats], "downbeats_reliable": reliable,
              "onsets_ms": [ms(f * FRAME_S) for f in onsets], "transitions_ms": [ms(float(i)) for i in jumps], "energy": [round(float(v), 3) for v in energy]}
    result["energy_peaks_ms"] = [ms(i + 0.5) for i in peaks]
    if cache_dir:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        (Path(cache_dir) / f"rhythm-{key}.json").write_text(json.dumps(result))
    return result


def events(analysis: dict, source_asset_id: str | None = None) -> list[AudioTimingEvent]:
    """The analysis as timing events on the shared timeline."""
    rows = []
    for kind, field in (("beat", "beats_ms"), ("downbeat", "downbeats_ms"), ("onset", "onsets_ms"), ("energy_peak", "energy_peaks_ms"), ("music_transition", "transitions_ms")):
        for number, time_ms in enumerate(analysis.get(field, [])):
            rows.append(AudioTimingEvent(id=f"{kind}-{number}", type=kind, time_ms=time_ms, source_asset_id=source_asset_id,
                                         confidence=analysis.get("bpm_confidence") if kind == "beat" else None))
    return sorted(rows, key=lambda e: e.time_ms)


def snap_starts(starts: list[float], total_s: float, beats_ms: list[int], tolerance_s: float, max_total_s: float) -> tuple[list[float], float, list[int]]:
    """Delay each scene start (after the first) to the next beat when the wait is short; never move a start earlier,
    which would cut speech. A delay pushes every later scene by the same amount, so speech keeps its order and length.

    Returns (new starts, new total length, indexes of scenes now on a beat). Nothing moves if the film would pass `max_total_s`.
    """
    if not beats_ms or len(starts) < 2:
        return list(starts), total_s, []
    beats = np.array(beats_ms) / 1000.0
    shifted, offset, on_beat = [starts[0]], 0.0, []
    for index in range(1, len(starts)):
        moved = starts[index] + offset
        later = beats[beats >= moved - 1e-6]
        if len(later) and later[0] - moved <= tolerance_s:
            offset += float(later[0] - moved)
            moved = float(later[0])
            on_beat.append(index)
        shifted.append(round(moved, 3))
    if total_s + offset > max_total_s:
        return list(starts), total_s, []
    return shifted, round(total_s + offset, 3), on_beat
