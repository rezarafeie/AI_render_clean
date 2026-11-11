"""The music director's glue for films whose scene timing is already fixed by a recorded voice: the product reel and the style-pack talking reel.

The motion-graphic engine decides its music, fits the track's rhythm to the film, tells each scene where the beats fall, lays sound effects and masters the
loudness (app/motion_graphic.py). This module is the same logic without that engine's record plumbing, so the other engines get the same behaviour:

  choose()         the track: the person's own (attached / chosen) or the director's (library -> catalogues -> generation), decided once and kept in music_choice.json
  lengthen_buildup() a drop earlier than the reveal is reached by a longer build-up (the track, never the narration)
  fit()            the track slid (never stretched) so its drop lands on the accent, else its beat grid on the cuts
  attach_beats()   each scene learns the beats and the accent that fall inside it
  sfx()            synthesised sound effects on the cuts and on the accent
  master()         narration + music at the delivery loudness

Nothing here stops a film: every function returns what it was given when it cannot do its job, with a note saying so.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

Progress = Callable[[str, str], None]


def director_enabled() -> bool:
    """FILM_MUSIC_DIRECTOR=0 keeps the old behaviour (the person's file, or none) in the product and talking reels."""
    import os
    return os.environ.get("FILM_MUSIC_DIRECTOR", "1").strip().lower() not in {"0", "false", "off", "no"}


def choose(directory: Path, request, progress: Progress | None = None):
    """The film's music, decided once. `request` is a music_director.MusicRequest; the result is kept beside the project so a retry never pays again."""
    from creative.audio import music_director as md
    stamp = json.dumps([request.mode, request.words, request.style, request.energy, request.instrumental, request.cost, request.path, request.variant, request.exclude,
                        int(request.duration_s // 10)], ensure_ascii=False, default=str)
    saved = directory / "music_choice.json"
    try:
        cached = json.loads(saved.read_text())
        if cached.get("stamp") == stamp and cached.get("path") and Path(cached["path"]).is_file():
            return md.Result(path=Path(cached["path"]), label=cached["label"], source=cached["source"], notes=cached.get("notes", []), reasons=cached.get("reasons", []),
                             attribution=cached.get("attribution"), cost=cached.get("cost"), style=cached.get("style", ""), arc=cached.get("arc", []), track=cached.get("track"))
    except (OSError, ValueError):
        pass
    chosen = md.resolve(request, progress=progress)
    if chosen.path:
        small = {k: v for k, v in (chosen.track or {}).items() if k in {"id", "source", "provider", "title", "artist", "license", "rights", "cost", "duration_s"}}
        directory.mkdir(parents=True, exist_ok=True)
        saved.write_text(json.dumps({"stamp": stamp, "path": str(chosen.path), "label": chosen.label, "source": chosen.source, "notes": chosen.notes, "reasons": chosen.reasons,
                                     "attribution": chosen.attribution, "cost": chosen.cost, "style": chosen.style, "arc": chosen.arc, "track": small}, ensure_ascii=False))
    return chosen


def lengthen_buildup(directory: Path, choice, analysis: dict, accent_s: float | None, notes: list[str]):
    """A track whose drop comes before the film's reveal gets a longer build-up (music_fit.extend_buildup), so the drop can fall on the reveal. The new file is kept as the film's
    music (music_choice.json), measured again, and used only when its drop really is where it should be; otherwise the original track is kept. Returns (analysis, choice)."""
    from creative.audio import music_director as md, music_fit, music_providers
    try:
        ext = music_fit.extend_buildup(Path(choice.path), analysis, accent_s, music_providers.store_root() / "extended")
        if not ext:
            return analysis, choice
        longer = md.analysis_for(ext["path"])
        if not longer or longer.get("bpm_confidence", 0) < 0.2 or not any(abs(d - ext["drop_ms"]) <= 650 for d in longer.get("drops_ms") or []):
            return analysis, choice                  # the detector must still see a drop near where the repeats put it (it may sit up to a beat early on the lengthened build-up)
        # The repeats put the drop at an exactly known place: the measured one is replaced by it (in the cached analysis too, so every later step reads the same grid).
        added_ms = int(round(ext["added_s"] * 1000))
        original = int(ext["drop_ms"]) - added_ms
        longer["drops_ms"] = [int(ext["drop_ms"])] + [int(d) + added_ms for d in analysis.get("drops_ms") or [] if int(d) > original + 500]
        try:
            from creative.audio import rhythm
            (md.analysis_dir() / f"rhythm-{rhythm.content_key(Path(ext['path']))}.json").write_text(json.dumps(longer))
        except Exception:
            log.info("lengthened build-up analysis not cached")
        saved = directory / "music_choice.json"
        try:
            record = json.loads(saved.read_text())
            record.update({"path": str(ext["path"]), "extended_from": str(choice.path)})
            saved.write_text(json.dumps(record, ensure_ascii=False))
        except (OSError, ValueError):
            pass
        choice.path = ext["path"]
        notes.append(f"بیلدآپ موسیقی {ext['added_s']:.1f} ثانیه (دو میزان، {ext['repeats']} بار تکرار) طولانی‌تر شد تا دراپ به لحظهٔ رونمایی برسد")
        return longer, choice
    except Exception as exc:
        log.info("build-up not lengthened: %s", str(exc)[:160])
        return analysis, choice


def fit(directory: Path, choice, starts: list[float], total: float, accent_s: float | None, notes: list[str]):
    """The track's rhythm against fixed scene starts: nothing in the film moves. Returns (track_path, fit_dict or None, analysis or None).
    The track is slid so its drop lands on `accent_s`, else its beat grid on the most cuts; a track without a reliable beat is returned as it is."""
    from creative.audio import music_director as md, music_fit
    source = Path(choice.path)
    try:
        analysis = md.analysis_for(source)
        if not analysis or analysis.get("bpm_confidence", 0) < 0.2 or len(analysis.get("beats_ms", [])) < 8:
            notes.append(f"ضرب موسیقی «{choice.label}» قابل اتکا تشخیص داده نشد؛ موسیقی بدون هم‌گام‌سازی استفاده شد.")
            return source, None, analysis
        analysis, choice = lengthen_buildup(directory, choice, analysis, accent_s, notes)
        source = Path(choice.path)
        if accent_s is None:                         # no reveal to land a drop on: the beat grid is put on as many cuts as possible
            plan = music_fit.phase_offset(analysis, list(starts), float(total))
        else:
            plan = music_fit.solve(analysis, list(starts), float(total), snap=False, tolerance_s=0.0, max_total_s=float(total) + 0.001)["fit"]
        (directory / "music_fit.json").write_text(json.dumps(plan))
        notes.append(f"موسیقی {analysis['bpm']:.0f} BPM (اطمینان ضرب {analysis.get('beat_confidence', 0):.0%})")
        for n in plan.get("notes", []):
            notes.append("دراپ موسیقی روی لحظهٔ اوج فیلم قرار گرفت" if "lands on the film's accent" in n else
                         f"موسیقی {plan['offset_s']:.2f} ثانیه جابه‌جا شد تا ضرب‌ها روی برش‌ها بنشینند" if "beat grid falls" in n else n)
        if plan.get("offset_s", 0) > 0.001 or plan.get("loop"):
            return music_fit.render(source, directory / "music_fitted.wav", float(total), plan, analysis), plan, analysis
        return source, plan, analysis
    except Exception as exc:
        log.info("music rhythm fit skipped: %s", str(exc)[:160])
        return source, None, None


def save_timing(directory: Path, analysis: dict | None, plan: dict | None, total: float, choice) -> None:
    """The track's rhythm on the film's own clock (offset removed), beside the project with its source and licence: what attach_beats, the sound effects and the editor read."""
    from creative.audio import music_fit
    timing = music_fit.film_timing(analysis, plan, float(total)) if (analysis and plan) else {}
    (directory / "music_timing.json").write_text(json.dumps({"timing": timing, "source": choice.source, "label": choice.label, "style": choice.style, "arc": choice.arc,
                                                             "attribution": choice.attribution,
                                                             "track": choice.track and {k: choice.track.get(k) for k in ("id", "provider", "license", "rights")}}, ensure_ascii=False))


def attach_beats(directory: Path, plan):
    """Each scene gets the beats and the accent that fall inside it (seconds from its own start), so its designer can land the big moves on them. Needs a reliable beat grid."""
    try:
        timing = json.loads((directory / "music_timing.json").read_text())["timing"]
    except (OSError, ValueError, KeyError):
        return plan
    if not timing or float(timing.get("beat_confidence") or 0) < 0.3 or not timing.get("bpm"):
        return plan
    strong_all, bars_all, beats_all = timing.get("strong_beats_ms") or [], timing.get("bars_ms") or [], timing.get("beats_ms") or []
    accents = [d for d in timing.get("drops_ms") or []] + ([timing["anchor"]["film_ms"]] if timing.get("anchor") else [])
    period = round(60.0 / float(timing["bpm"]), 3)
    scenes = []
    for scene in plan.scenes:
        def inside(values):
            return [round(b / 1000 - scene.start, 2) for b in values if scene.start <= b / 1000 < scene.end - 0.1]
        beats = (inside(strong_all) or inside(bars_all) or inside(beats_all)[::2])[:12]
        accent = next((round(a / 1000 - scene.start, 2) for a in accents if scene.start - 1e-6 <= a / 1000 < scene.end), None)
        scenes.append(scene.model_copy(update={"beats": beats, "accent": accent, "beat_s": period if beats else 0.0}))
    return plan.model_copy(update={"scenes": scenes})


def sfx(directory: Path, starts: list[float], total: float, voice_words_s: list[float], accent_s: float | None, level: str = "minimal"):
    """Synthesised sound effects on every cut and on the accent, as dense as `level` allows, snapped to a near beat and kept off the spoken words. Returns (clip or None, notes)."""
    if level in {"", "none"}:
        return None, []
    try:
        from creative.audio import music_director as md, sound_design
        from creative.audio.contracts import AudioTimingEvent
        try:
            timing = json.loads((directory / "music_timing.json").read_text()).get("timing") or {}
        except (OSError, ValueError):
            timing = {}
        speech = [AudioTimingEvent(id=f"w{i}", type="word", time_ms=int(t * 1000), duration_ms=280) for i, t in enumerate(voice_words_s)]
        cues = sound_design.plan(md.sfx_moments([{"start": s} for s in starts], timing, accent_s), level, md.sfx_library(directory / "sfx"),
                                 beats_ms=timing.get("beats_ms") or None, speech=speech, total_ms=int(total * 1000))
        track = md.render_sfx(cues, total, directory / "sfx_track.wav")
        (directory / "sfx_cues.json").write_text(json.dumps(cues, ensure_ascii=False))
        placed = [c for c in cues if c["status"] == "ready"]
        if not track or not placed:
            return None, []
        return {"path": str(track), "start": 0, "duration": round(total, 3), "role": "sfx"}, [f"{len(placed)} افکت صوتی هم‌زمان با برش‌ها و لحظهٔ اوج (سطح {level})"]
    except Exception as exc:
        log.warning("sound effects skipped: %s", str(exc)[:200])
        return None, []


def master(directory: Path, voice: list[dict], music: dict | None, total: float, preset: str = "social_video"):
    """Narration and music in one track at the delivery loudness. Returns (clip or None, notes); on failure None, so the caller keeps the separate tracks."""
    from creative.audio import loudness, mixer
    if preset == "off" or not voice or preset not in loudness.PRESETS:
        return None, []
    try:
        result = mixer.master(voice, music, total, directory / "master.m4a", preset)
    except Exception as exc:
        log.warning("master mix failed: %s", str(exc)[:200])
        return None, ["میکس نهایی انجام نشد؛ صدا بدون نرمال‌سازی استفاده شد: " + str(exc)[:120]]
    (directory / "audio_report.json").write_text(json.dumps({"mix": {"preset": preset, **result}}, ensure_ascii=False))
    before, after, target = result["before"]["integrated_lufs"], result["after"]["integrated_lufs"], result["target"]["lufs"]
    return ({"path": str(directory / "master.m4a"), "start": 0, "duration": round(total, 3), "role": "master"},
            [f"میکس نهایی: لودنس {before:.1f} به {after:.1f} LUFS رسید (هدف {target:g}، true peak {result['after']['true_peak_dbtp']:.1f} dBTP)"])
