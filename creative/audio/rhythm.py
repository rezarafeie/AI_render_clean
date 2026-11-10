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


BANDS = ((1, 10, 1.0), (10, 94, 0.6), (94, 400, 0.25))      # FFT bins at 22.05 kHz / 1024: up to ~200 Hz (kick, bass), ~200 Hz-2 kHz, above (hats, air); weights favour the pulse


def _onset_envelope(spec: np.ndarray) -> np.ndarray:
    """Spectral flux per band, each normalised, then summed with weights that favour the low bands: a hat or a shaker on the off-beat has a much bigger broadband flux than a kick,
    and an unweighted sum would put the whole beat grid on the off-beats."""
    logmag = np.log1p(spec * 10)
    window = max(3, int(0.5 / FRAME_S))
    total = np.zeros(len(logmag))
    for low, high, weight in BANDS:
        flux = np.maximum(0.0, np.diff(logmag[:, low:high], axis=0)).sum(axis=1)
        flux = np.concatenate([[0.0], flux])
        local = np.convolve(flux, np.ones(window) / window, mode="same")
        env = np.maximum(flux - local, 0.0)
        live = env[env > 0]
        top = float(np.percentile(live, 95)) if len(live) >= 20 else float(env.max())      # not the maximum: one huge event (a bass note entering) would make every kick look weak
        if top > 0:
            total += weight * np.minimum(env / top, 1.5)
    top = total.max()
    return total / top if top > 0 else total


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

    def lagged(lag: float) -> float:
        low, high = int(np.floor(lag)), int(np.ceil(lag))
        if high >= len(ac):
            return 0.0
        return float(ac[low] + (ac[high] - ac[low]) * (lag - low))

    for bpm in np.arange(60.0, 180.5, 0.5):
        lag = 60.0 / bpm / FRAME_S
        if int(np.ceil(lag)) >= len(ac):
            continue
        # a true tempo repeats at 2, 3 and 4 beats too: the mean of the first four multiples separates 120 from 80 (1.5 beats), which a single lag cannot
        value = sum(lagged(k * lag) for k in (1, 2, 3, 4)) / 4
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
    """Beat positions: the tempo's grid with its PHASE chosen per 8-second stretch, the stretches joined by dynamic programming.

    A single phase for the whole track is dominated by whatever is loudest and most regular for longest: a 14 s snare roll before a drop, whose off-beat hits are as strong as its
    on-beat ones, can pull the grid half a beat away from the kicks that follow. Per stretch the phase follows the strongest onsets there; a stretch that is ambiguous (two equally good
    phases) follows its neighbours, because changing phase costs; so the kicks decide where they exist and the roll just continues the grid. The tempo itself also drifts a few
    milliseconds per beat in a real track, which a per-stretch phase absorbs."""
    period = 60.0 / bpm / FRAME_S
    size = int(6.0 / FRAME_S)
    count = max(1, len(env) // size)
    edges = [round(i * len(env) / count) for i in range(count + 1)]
    candidates = max(2, int(period))
    scores = np.zeros((count, candidates))
    for c in range(count):
        lo, hi = edges[c], edges[c + 1]
        for phase in range(candidates):
            first = int(np.ceil((lo - phase) / period))
            positions = np.round(phase + period * np.arange(first, int((hi - phase) / period) + 1)).astype(int)
            positions = positions[(positions >= lo) & (positions < min(hi, len(env)))]
            scores[c, phase] = env[positions].sum() if len(positions) else 0.0
        spread = scores[c].max() - scores[c].min()
        if spread > 0:
            scores[c] = ((scores[c] - scores[c].min()) / spread) ** 2          # a decisive stretch has one clear peak; an ambiguous one is flat and so has no say
    penalty = 0.5                                                     # changing phase by half a beat costs half of a stretch's best score
    best = scores[0].copy()
    back = np.zeros((count, candidates), dtype=int)
    steps = np.arange(candidates)
    distance = np.minimum(np.abs(steps[:, None] - steps[None, :]), candidates - np.abs(steps[:, None] - steps[None, :])) / (candidates / 2)
    for c in range(1, count):
        total = best[:, None] - penalty * distance                    # from phase i (rows) to phase j (columns)
        back[c] = total.argmax(axis=0)
        best = total.max(axis=0) + scores[c]
    chain = [int(best.argmax())]
    for c in range(count - 1, 0, -1):
        chain.append(int(back[c][chain[-1]]))
    chain.reverse()
    refined: list[int] = []
    for c in range(count):
        lo, hi = edges[c], edges[c + 1]
        phase = chain[c]
        first = int(np.ceil((lo - phase) / period))
        for k in range(first, int((hi - phase) / period) + 1):
            p = int(round(phase + period * k))
            if lo <= p < min(hi, len(env)):
                window = env[max(0, p - 2):p + 3]
                refined.append(int(max(0, p - 2) + int(np.argmax(window))))
    return sorted(set(refined))


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


def content_key(path: Path) -> str:
    """The same audio is analysed once whatever it is called or wherever it is copied: the key is the file's content (size + first/last 4 MiB), not its name."""
    path = Path(path)
    digest = hashlib.sha1(f"{path.stat().st_size}|v2".encode())
    with path.open("rb") as handle:
        digest.update(handle.read(4 << 20))
        if path.stat().st_size > (8 << 20):
            handle.seek(-(4 << 20), 2)
            digest.update(handle.read())
    return digest.hexdigest()[:16]


def analyse(path: Path, cache_dir: Path | None = None) -> dict:
    path = Path(path)
    key = content_key(path)
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
    result.update(structure(samples, env, beats, downbeats, reliable, confidence))
    if cache_dir:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        (Path(cache_dir) / f"rhythm-{key}.json").write_text(json.dumps(result))
    return result


FINE = 0.25            # seconds per value of the fine loudness curve (structure detection)


def _fine_energy(samples: np.ndarray) -> np.ndarray:
    size = int(SR * FINE)
    count = len(samples) // size
    if count == 0:
        return np.array([0.0])
    rms = np.sqrt(np.mean(samples[:count * size].reshape(count, size) ** 2, axis=1))
    return rms / rms.max() if rms.max() > 0 else rms


def _nearest(values: list[int], target: int, within: int) -> int | None:
    if not values:
        return None
    best = min(values, key=lambda v: abs(v - target))
    return best if abs(best - target) <= within else None


def structure(samples: np.ndarray, env: np.ndarray, beat_frames: list[int], downbeat_frames: list[int], reliable: bool, tempo_confidence: float) -> dict:
    """Beat strength, bars, quiet passages, sections, build-ups and drops, all measured from the audio (a 0.25 s loudness curve and the onset envelope).

    A drop is a clear rise in loudness that follows a calmer passage; a build-up is a steady rise towards one; both are snapped to the nearest bar line
    when one is within half a second, so a cut placed on them also lands on the music's own grid. Nothing is invented: a track without such moments
    returns empty lists, and `beat_confidence` says how much of the beat grid sits on real onsets."""
    beats_ms = [ms(f * FRAME_S) for f in beat_frames]
    strength = [round(float(env[min(f, len(env) - 1)]), 3) for f in beat_frames]
    on_onset = float(np.mean([v >= max(0.05, float(env.mean())) for v in strength])) if strength else 0.0
    beat_confidence = round(float(np.clip(0.5 * tempo_confidence + 0.5 * on_onset, 0.0, 1.0)), 3) if beats_ms else 0.0
    if strength:
        cut = float(np.percentile(strength, 65))
        strong = [t for t, v in zip(beats_ms, strength) if v >= cut]
    else:
        strong = []
    if reliable and downbeat_frames:
        bars = [ms(f * FRAME_S) for f in downbeat_frames]
    else:                                  # 4/4 assumed from the strongest beat phase; flagged by bars_reliable
        phases = [np.mean(strength[p::4]) if len(strength[p::4]) else 0.0 for p in range(4)] if len(strength) >= 8 else []
        offset = int(np.argmax(phases)) if phases else 0
        bars = beats_ms[offset::4]
    fine = _fine_energy(samples)
    smooth = np.convolve(fine, np.ones(3) / 3, mode="same") if len(fine) >= 3 else fine
    step_ms = int(FINE * 1000)
    quiet, start = [], None
    for index, value in enumerate(smooth):
        if value < 0.12 and start is None:
            start = index
        elif value >= 0.12 and start is not None:
            if (index - start) * FINE >= 1.0:
                quiet.append([start * step_ms, index * step_ms])
            start = None
    if start is not None and (len(smooth) - start) * FINE >= 1.0:
        quiet.append([start * step_ms, len(smooth) * step_ms])
    lead, lag = int(2.0 / FINE), int(1.5 / FINE)          # compare the 2 s before a moment with the 1.5 s after it
    delta = np.zeros(len(smooth))
    level_after = np.zeros(len(smooth))
    level_before = np.zeros(len(smooth))
    for index in range(lead, len(smooth) - lag):
        level_before[index], level_after[index] = float(smooth[index - lead:index].mean()), float(smooth[index:index + lag].mean())
        delta[index] = level_after[index] - level_before[index]
    window = int(1.5 / FINE)
    drops, builds = [], []
    for index in range(lead, len(smooth) - lag):           # a drop is the PEAK of that contrast (the first crossing would sit inside the build-up)
        neighbourhood = delta[max(0, index - window):index + window + 1]
        if delta[index] >= 0.3 and delta[index] >= neighbourhood.max() and level_after[index] >= 0.5 and level_before[index] <= 0.6 * level_after[index]:
            time_ms = index * step_ms
            if drops and time_ms - drops[-1] < 4000:
                continue
            drops.append(time_ms)
    snapped = []
    for time_ms in drops:
        near = _nearest(bars, time_ms, 500) if bars else None
        snapped.append(near if near is not None else time_ms)
    drops = sorted(set(snapped))
    slow = np.convolve(fine, np.ones(4) / 4, mode="same") if len(fine) >= 4 else fine        # one-second loudness: the roll of a build-up is lumpy at 0.25 s
    for drop in drops:
        end = drop // step_ms
        begin = max(0, end - int(6.0 / FINE))
        segment = slow[begin:end]
        if len(segment) < int(2.0 / FINE) or np.ptp(segment) < 1e-6:
            continue
        rise = float(segment[-4:].mean() - segment[:4].mean())
        trend = float(np.corrcoef(np.arange(len(segment)), segment)[0, 1])
        if rise >= 0.10 and trend >= 0.75:                       # a steady climb into the drop, not a loud passage that merely precedes it
            builds.append([begin * step_ms, drop])
    # sections: the peaks of the loudness change that last (at least 6 s apart), snapped to bars, each labelled by its own loudness
    bounds = [0]
    change = np.abs(delta)
    for index in range(lead, len(smooth) - lag):
        if change[index] >= 0.22 and change[index] >= change[max(0, index - window):index + window + 1].max():
            time_ms = index * step_ms
            near = _nearest(bars, time_ms, 700) if bars else None
            time_ms = near if near is not None else time_ms
            if time_ms - bounds[-1] >= 6000:
                bounds.append(time_ms)
    total_ms = len(samples) * 1000 // SR
    edges = bounds + [total_ms]
    sections = []
    for left, right in zip(edges, edges[1:]):
        part = smooth[left // step_ms:max(left // step_ms + 1, right // step_ms)]
        level = float(part.mean()) if len(part) else 0.0
        sections.append({"start_ms": left, "end_ms": right, "energy": round(level, 3), "label": "low" if level < 0.35 else "high" if level > 0.65 else "mid"})
    return {"beat_strength": strength, "strong_beats_ms": strong, "bars_ms": bars, "bars_reliable": bool(reliable), "beat_confidence": beat_confidence,
            "quiet_ms": quiet, "drops_ms": drops, "buildups_ms": builds, "sections": sections}


def events(analysis: dict, source_asset_id: str | None = None) -> list[AudioTimingEvent]:
    """The analysis as timing events on the shared timeline."""
    rows = []
    for kind, field in (("beat", "beats_ms"), ("downbeat", "downbeats_ms"), ("onset", "onsets_ms"), ("energy_peak", "energy_peaks_ms"), ("music_transition", "transitions_ms"), ("drop", "drops_ms")):
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
