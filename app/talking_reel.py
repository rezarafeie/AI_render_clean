"""Talking-head reels for a job: transcribe, let the LLM edit, render (see ``engine.talking_reel``).

State lives in ``<job dir>/talking_reel.json``; renders go to the job's
``exports/talking_reel_v<N>.mp4``. Work runs in a background thread and
clients poll the state. User edits (hook, highlighted words, name, title,
music) are kept across renders; "regenerate" asks the LLM again.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from creative.review import QualityReviewRequired

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MUSIC = "assets/music/motivational_piano_beat.mp3"
DEFAULTS = {
    "status": "idle", "stage": "", "message": "", "progress": 0,
    "hook": "", "hook_highlight": [], "name": "", "title": "",
    "music": DEFAULT_MUSIC, "cta": "", "style": "talking_1", "suggested_style": None,
    "suggested_style_reason": "", "analysis_ready": False, "output": None, "decisions": None,
    "render_settings": {
        "grade": {"brightness": 0, "contrast": 100, "saturation": 100, "temperature": 0, "vignette": 50},
        "zoom": {"enabled": True, "amount": 100, "base_scale": 100, "close_scale": 140},
        "key_moments_enabled": True,
        "first_key_moment_enabled": True,
        "first_key_moment_sentence": None,
        "key_moment_effect": "grayscale_title",
        "title_color": "#F5B800",
        "outro_logo": {"enabled": True, "motion": "pop"},
        "disabled_moments": [],
        "dropped_sentences": [], "bottom_shade": 0, "source_cuts": [], "effects": [],
    },
}
EDITABLE = {"hook", "hook2", "hook_highlight", "name", "title", "music", "music_chosen", "cta", "style", "captions", "storyboard", "render_settings",
            "timeline_edits", "broll_edits", "key_moments"}
_lock = threading.Lock()
_running: set[str] = set()
_cancel_events: dict[str, threading.Event] = {}
_pause_events: dict[str, threading.Event] = {}

class TaskCanceled(Exception):
    pass

def _checkpoint(job_dir: Path) -> None:
    key = str(job_dir)
    while True:
        with _lock:
            cancel_event, pause_event = _cancel_events.get(key), _pause_events.get(key)
        if cancel_event and cancel_event.is_set():
            raise TaskCanceled()
        if not pause_event or not pause_event.is_set():
            return
        time.sleep(0.2)


def _path(job_dir: Path) -> Path:
    return job_dir / "talking_reel.json"


def load(job_dir: Path) -> dict:
    path = _path(job_dir)
    state = dict(DEFAULTS)
    if path.is_file():
        state.update(json.loads(path.read_text()))
    state["render_settings"] = _clean_render_settings(state.get("render_settings"))
    return state


def save(job_dir: Path, state: dict) -> dict:
    state["updated_at"] = time.time()
    tmp = _path(job_dir).with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    tmp.replace(_path(job_dir))
    return state


def recover_interrupted(jobs_root: Path) -> int:
    """Fail in-memory talking tasks left behind by a backend restart.

    Talking renders run in daemon threads and cannot survive their owning
    process.  Leaving the persisted state as ``running`` makes the editor look
    permanently stuck even though no FFmpeg process exists.
    """
    if not jobs_root.is_dir():
        return 0
    recovered = 0
    for path in jobs_root.glob("*/talking_reel.json"):
        try:
            state = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if state.get("status") not in {"running", "paused"}:
            continue
        state.update(
            status="error",
            stage="",
            message="Interrupted by a server restart. Start the render again.",
            updated_at=time.time(),
        )
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1))
        tmp.replace(path)
        recovered += 1
    return recovered


def public(state: dict) -> dict:
    result = {k: v for k, v in state.items() if not k.startswith("decisions")}
    key = _decisions_key(str(state.get("style") or "talking_1"))
    decisions = state.get(key) or {}
    captions = decisions.get("captions") or {}
    result["captions"] = [
        {"i": int(index), "text": str(text)}
        for index, text in sorted(captions.items(), key=lambda item: int(item[0]))
    ]
    result["storyboard"] = decisions.get("storyboard") or []
    result["key_moments"] = key_moments_of(decisions)
    result["timeline"] = _timeline(decisions, str(state.get("style") or "talking_1"))
    return result


def key_moments_of(decisions: dict) -> list[dict]:
    """The black-and-white key moments of the plan: [{"i": sentence, "text": takeaway shown over it ("" when none)}], in sentence order."""
    notes = {}
    for item in decisions.get("notes") or []:
        try:
            notes[int(item.get("i"))] = str(item.get("text") or "").strip()
        except (AttributeError, TypeError, ValueError):
            continue
    indexes = set(notes)
    for value in decisions.get("bw") or []:
        try:
            indexes.add(int(value))
        except (TypeError, ValueError):
            continue
    return [{"i": i, "text": notes.get(i, "")} for i in sorted(indexes)]


def clean_key_moments(value, sentence_count: int) -> list[dict]:
    """Shape-check the key moments a person chose: real sentences only, a short Persian takeaway (optional), at most 8."""
    import re as _re
    seen: dict[int, str] = {}
    for item in value or []:
        try:
            index = int(item.get("i"))
        except (AttributeError, TypeError, ValueError):
            continue
        if not 0 <= index < sentence_count:
            continue
        text = " ".join(str(item.get("text") or "").split())
        if text and (len(text.split()) > 5 or _re.search(r"[A-Za-z]", text)):
            raise ValueError("متن لحظهٔ کلیدی باید حداکثر ۵ کلمهٔ فارسی باشد.")
        seen[index] = text[:60]
    if len(seen) > 8:
        raise ValueError("حداکثر ۸ لحظهٔ کلیدی ممکن است.")
    return [{"i": i, "text": seen[i]} for i in sorted(seen)]


def _timeline(decisions: dict, style: str) -> list[dict]:
    """Editable pre-render events, using transcript sentence indices as stable ids."""
    rows = []
    for source in ("notes", "titles", "storyboard", "broll"):
        for index, item in enumerate(decisions.get(source) or []):
            try:
                sentence = int(item.get("i", index))
            except (TypeError, ValueError):
                sentence = index
            rows.append({
                "id": f"{style}-{source}-{sentence}-{index}", "sentence": sentence,
                "title": str(item.get("text") or item.get("title") or item.get("label") or f"لحظه کلیدی {len(rows) + 1}"),
                "kind": "key_moment", "order": len(rows),
            })
    return rows


def _clean_render_settings(value: object) -> dict:
    current = json.loads(json.dumps(DEFAULTS["render_settings"]))
    if not isinstance(value, dict):
        return current
    if value.get('caption_font') in {'default', 'Vazirmatn'}:
        current['caption_font'] = value['caption_font']
    grade = value.get("grade") if isinstance(value.get("grade"), dict) else {}
    limits = {"brightness": (-30, 30), "contrast": (50, 160), "saturation": (0, 180),
              "temperature": (-50, 50), "vignette": (0, 100)}
    for key, (low, high) in limits.items():
        try:
            current["grade"][key] = max(low, min(high, int(grade.get(key, current["grade"][key]))))
        except (TypeError, ValueError):
            pass
    zoom = value.get("zoom") if isinstance(value.get("zoom"), dict) else {}
    current["zoom"]["enabled"] = bool(zoom.get("enabled", current["zoom"]["enabled"]))
    try:
        current["zoom"]["amount"] = max(0, min(200, int(zoom.get("amount", 100))))
    except (TypeError, ValueError):
        pass
    for key, default, low, high in (
        ("base_scale", 100, 100, 180), ("close_scale", 140, 100, 220),
    ):
        try:
            current["zoom"][key] = max(low, min(high, int(zoom.get(key, default))))
        except (TypeError, ValueError):
            pass
    current["zoom"]["close_scale"] = max(
        current["zoom"]["base_scale"], current["zoom"]["close_scale"]
    )
    for key in ("key_moments_enabled", "first_key_moment_enabled"):
        current[key] = bool(value.get(key, current[key]))
    try:
        selected = value.get("first_key_moment_sentence")
        current["first_key_moment_sentence"] = None if selected in (None, "") else max(0, int(selected))
    except (TypeError, ValueError):
        pass
    if value.get("key_moment_effect") in {"grayscale_title", "title_only", "grayscale", "none"}:
        current["key_moment_effect"] = value["key_moment_effect"]
    import re
    colour = str(value.get("title_color") or "").upper()
    if re.fullmatch(r"#[0-9A-F]{6}", colour):
        current["title_color"] = colour
    outro = value.get("outro_logo") if isinstance(value.get("outro_logo"), dict) else {}
    current["outro_logo"]["enabled"] = bool(outro.get("enabled", True))
    if outro.get("motion") in {"pop", "fade", "slide", "none"}:
        current["outro_logo"]["motion"] = outro["motion"]
    from engine import music_mix
    try:
        mix = music_mix.clean(value.get("music_mix"))
    except ValueError:
        mix = {}
    if mix:
        current["music_mix"] = mix
    current["disabled_moments"] = [str(v)[:80] for v in (value.get("disabled_moments") or [])][:30]
    drops = value.get('dropped_sentences') or []
    current['dropped_sentences'] = sorted({v for v in drops if type(v) is int and 0 <= v < 10000})[:500] if isinstance(drops, list) else []
    try: current['bottom_shade'] = max(0, min(60, int(value.get('bottom_shade', 0))))
    except (TypeError, ValueError): pass
    from engine import face_effects as _effects
    try: current['effects'] = _effects.clean_plan(value.get('effects'))
    except _effects.EffectsError: current['effects'] = [dict(item) for item in (current.get('effects') or [])]
    cuts=value.get('source_cuts') or []
    current['source_cuts']=[]
    if isinstance(cuts,list):
        for cut in cuts[:100]:
            try:
                a,b=float(cut['start']),float(cut['end'])
                if 0<=a<b<=86400: current['source_cuts'].append({'start':a,'end':b})
            except (TypeError,ValueError,KeyError): pass
    return current


def _decisions_key(style: str) -> str:
    return "decisions" if style == "talking_1" else f"decisions_{style.rsplit('_', 1)[-1]}"


def update(job_dir: Path, changes: dict) -> dict:
    with _lock:
        if str(job_dir) in _running:
            raise ValueError("talking reel is busy")
        state = load(job_dir)
        for key in EDITABLE & set(changes):
            value = changes[key]
            if key == "render_settings":
                state[key] = _clean_render_settings(value)
                continue
            if key == "timeline_edits":
                from app import timeline_edits
                state[key] = timeline_edits.clean(value)
                continue
            if key == "broll_edits":
                from app import broll_edits
                state[key] = broll_edits.clean(value)
                continue
            if key == "key_moments":
                decisions_key = _decisions_key(str(state.get("style") or "talking_1"))
                decisions = dict(state.get(decisions_key) or {})
                moments = clean_key_moments(value, len(decisions.get("captions") or {}) + len(decisions.get("drop") or []) or 10**6)
                decisions["bw"] = [m["i"] for m in moments]
                decisions["notes"] = [{"i": m["i"], "text": m["text"]} for m in moments if m["text"]]
                state[decisions_key] = decisions
                continue
            if key in {"captions", "storyboard"}:
                decisions_key = _decisions_key(str(state.get("style") or "talking_1"))
                decisions = dict(state.get(decisions_key) or {})
                if key == "storyboard":
                    allowed = {"concept", "stat", "comparison", "steps", "ui_showcase", "media_collage",
                               "chat", "map_route", "spec_callout", "kinetic_type", "before_after"}
                    board = []
                    for item in value or []:
                        if not isinstance(item, dict) or not str(item.get("title") or "").strip():
                            continue
                        clean = dict(item)
                        clean["title"] = str(clean["title"]).strip()[:80]
                        if clean.get("visual_type") not in allowed:
                            clean["visual_type"] = "concept"
                        board.append(clean)
                    decisions["storyboard"] = board[:9]
                    state[decisions_key] = decisions
                    continue
                current = dict(decisions.get("captions") or {})
                for item in value or []:
                    try:
                        index = int(item.get("i"))
                    except (AttributeError, TypeError, ValueError):
                        continue
                    text = str(item.get("text") or "").strip()
                    if text and (index in current or str(index) in current):
                        current[index] = text
                        current.pop(str(index), None)
                decisions["captions"] = current
                state[decisions_key] = decisions
                continue
            if key == "hook_highlight":
                value = [str(v).strip() for v in (value or []) if str(v).strip()]
            elif key == "style":
                from engine.talking_reel import STYLES
                if value not in STYLES:
                    raise ValueError(f"unknown style {value!r}")
            elif key == "music_chosen":
                value = bool(value)
            elif key == "music":
                value = value or None
                if value and resolve_music(value) is None:
                    raise ValueError("music file not found in the library")
            else:
                value = str(value or "").strip()
            state[key] = value
        return save(job_dir, state)


def music_library() -> list[dict]:
    """The bundled music beds a project can use: [{"path": "assets/music/x.mp3", "label": "x"}]."""
    folder = PROJECT_ROOT / "assets" / "music"
    return [{"path": f"assets/music/{p.name}", "label": p.stem.replace("_", " ")}
            for p in sorted(folder.glob("*")) if p.suffix.lower() in {".mp3", ".wav", ".m4a"} and p.is_file()]


def resolve_music(music: Optional[str]) -> Optional[Path]:
    if not music:
        return None
    path = (PROJECT_ROOT / music).resolve()
    if not path.is_relative_to((PROJECT_ROOT / "assets").resolve()) or not path.is_file():
        return None
    return path


def analyze(job_dir: Path, raw_video: Path, *, style: Optional[str] = None, request: str = "",
            concept: Optional[dict] = None) -> dict:
    """Transcribe and prepare editable AI decisions without starting a render.

    ``concept`` is a concept the user picked from the plan: the director is skipped and only the
    style's own decision step runs with that concept as guidance."""
    key = str(job_dir)
    with _lock:
        if key in _running:
            raise ValueError("talking reel is busy")
        state = load(job_dir)
        state.update(status="running", stage="transcribing", message="", progress=5, analysis_ready=False)
        save(job_dir, state)
        _running.add(key)
        _cancel_events[key], _pause_events[key] = threading.Event(), threading.Event()

    def run() -> None:
        try:
            _analyze(job_dir, raw_video, style=style, request=request, concept=concept)
        except TaskCanceled:
            current = load(job_dir); current.update(status="canceled", stage="", message="Canceled by user"); save(job_dir, current)
        except QualityReviewRequired as exc:
            current = load(job_dir)
            current.update(status="awaiting_confirmation", stage="quality review", message=str(exc)[:800], progress=100)
            save(job_dir, current)
        except Exception as exc:
            log.exception("talking reel analysis failed for %s", job_dir.name)
            current = load(job_dir)
            current.update(status="error", stage="", message=str(exc)[:500], analysis_ready=False)
            save(job_dir, current)
        finally:
            with _lock:
                _running.discard(key)
                _cancel_events.pop(key, None); _pause_events.pop(key, None)

    threading.Thread(target=run, daemon=True).start()
    return state


def _concept_plan(previous: Optional[dict], concept: dict, style: Optional[str]) -> dict:
    """The stored creative plan with the user's chosen concept promoted; the old winner becomes an alternative."""
    previous = dict(previous or {})
    old = previous.get("chosen") or {}
    others = [c for c in previous.get("alternatives") or [] if c.get("id") != concept.get("id")]
    if old and old.get("id") != concept.get("id"):
        others.insert(0, {k: old.get(k) for k in ("id", "name", "angle", "hook", "style_hint", "visual_language",
                                                  "pacing", "why_it_works")})
    previous.update(chosen={**concept, "beats": concept.get("beats") or []}, alternatives=others,
                    style=style, verdict="ایدهٔ انتخاب‌شده توسط شما.")
    return previous


def _concept_notes(concept: dict) -> str:
    parts = [f"Chosen concept: {concept.get('name', '')}. {concept.get('angle', '')}",
             f"Hook (first seconds): {concept.get('hook', '')}"]
    for key in ("visual_language", "pacing"):
        if concept.get(key):
            parts.append(f"{key.replace('_', ' ').title()}: {concept[key]}")
    return "\n".join(parts)


def _analyze(job_dir: Path, video: Path, *, style: Optional[str], request: str = "",
             concept: Optional[dict] = None) -> None:
    from dotenv import load_dotenv
    from importlib import import_module
    from brain import talking_reel as base_brain
    import creative

    load_dotenv(PROJECT_ROOT / ".env")
    transcript = transcript_for(job_dir, video)

    # Creative direction first: understand the talk, explore concepts, critique, then let the
    # existing engines execute the chosen one. This stage can only improve a result: if the
    # gateway is slow or limited, the standard analysis below runs exactly as before.
    plan = None
    guidance = ""
    creative_error = ""
    picked = None
    if concept:
        picked = _concept_plan(load(job_dir).get("creative_plan"), concept, style)
        guidance = _concept_notes(concept)
    elif creative.enabled():
        _stage(job_dir, "directing the edit", progress=12)
        try:
            plan = creative.direct_talk(transcript["sentences"], request, style=style)
            guidance = plan.director_notes
        except creative.CreativeUnavailable as exc:
            creative_error = str(exc)[:240]
            log.warning("creative direction unavailable for %s: %s", job_dir.name, creative_error)

    selected = style or (plan.style if plan else None)
    reason = ""
    if plan and not style and plan.style:
        reason = plan.critique.verdict
    if not selected:
        _stage(job_dir, "choosing style", progress=15)
        try:
            selected, reason = base_brain.recommend_style(transcript["sentences"])
        except Exception as exc:  # a slow selector must not kill the job; the selector's own rule is "calm when unsure"
            log.warning("style selector failed for %s: %s", job_dir.name, type(exc).__name__)
            selected, reason = "talking_4", "انتخاب خودکار سبک در دسترس نبود؛ سبک امن و ساده انتخاب شد."
    from engine.talking_reel import STYLES
    if selected not in STYLES:
        raise ValueError(f"unknown style {selected!r}")

    _stage(job_dir, "editing text", progress=30)
    state = load(job_dir)
    if selected == "talking_1":
        decisions = base_brain.decide(transcript["sentences"], guidance)
        state["decisions"] = decisions
        state["hook"] = decisions["hook"]
        state["hook_highlight"] = decisions["hook_highlight"]
    else:
        brain_name, decisions_key, _music = SPLIT_STYLES[selected]
        decisions = import_module(brain_name).decide(
            transcript["sentences"], [p.name for p in user_media(job_dir)], guidance=guidance
        )
        state[decisions_key] = decisions
        state["hook2"] = decisions["hook"]
        if plan and int(plan.schema_version) >= 2 and selected in {'talking_2','talking_3'}:
            from creative.production import bind_talking
            decisions = bind_talking(plan,decisions,transcript['sentences'])
            state[decisions_key] = decisions
    state["creative_plan"] = picked if picked is not None else (plan.public() if plan else None)
    state["creative_error"] = creative_error
    state.update(
        status="ready", stage="", message="", progress=100, style=selected,
        suggested_style=selected if style is None else state.get("suggested_style"),
        suggested_style_reason=reason if style is None else state.get("suggested_style_reason", ""),
        analysis_ready=True,
    )
    save(job_dir, state)


def start(job_dir: Path, raw_video: Path, *, regenerate: bool = False, cached_only: bool = False) -> dict:
    key = str(job_dir)
    with _lock:
        if key in _running:
            raise ValueError("talking reel is busy")
        state = load(job_dir)
        if not state.get("analysis_ready"):
            raise ValueError("analyze and review the talking reel before rendering")
        if cached_only:
            if not (job_dir / 'transcript.json').is_file():
                raise ValueError('متن ذخیره‌شده موجود نیست؛ ادامهٔ رندر بدون تولید مجدد ممکن نیست.')
            decision_key = SPLIT_STYLES[state['style']][1] if state['style'] in SPLIT_STYLES else 'decisions'
            if not state.get(decision_key): raise ValueError('برنامهٔ تدوین ذخیره‌شده موجود نیست.')
        state["published_outputs"] = published_outputs(state)
        state["candidate_output"] = None
        state["output"] = None
        state["creative_review"] = None
        state["technical_qc"] = None
        state['cached_render_only'] = cached_only
        state.update(status="running", stage="queued", message="", progress=0)
        save(job_dir, state)
        _running.add(key)
        _cancel_events[key], _pause_events[key] = threading.Event(), threading.Event()

    def run() -> None:
        try:
            started = time.time()
            _run(job_dir, raw_video, regenerate=regenerate)
            _record_render_time(job_dir, raw_video, time.time() - started)
        except TaskCanceled:
            current = load(job_dir); current.update(status="canceled", stage="", message="Canceled by user"); save(job_dir, current)
        except Exception as exc:
            log.exception("talking reel export held for %s", job_dir.name)
            current = load(job_dir)
            current.update(status="needs_review", stage="quality review", message=str(exc)[:800],
                           technical_qc={**(current.get("technical_qc") or {}), "hold_reason": str(exc)[:800]})
            save(job_dir, current)
        finally:
            with _lock:
                _running.discard(key)
                _cancel_events.pop(key, None); _pause_events.pop(key, None)

    threading.Thread(target=run, daemon=True).start()
    return state


def _record_render_time(job_dir: Path, raw_video: Path, seconds: float) -> None:
    """Feed the plan's time estimate with a real measurement; never affects the render."""
    try:
        from app import render_stats
        from engine.probe import probe
        state = load(job_dir)
        if state.get("status") != "done" or state.get("cached_render_only"):
            return
        duration = float(probe(raw_video).get("format", {}).get("duration") or 0)
        render_stats.record(f"talking:{state.get('style')}", duration, seconds)
    except Exception as exc:
        log.warning("render timing not recorded: %s", type(exc).__name__)


def _stage(job_dir: Path, stage: str, **extra) -> None:
    _checkpoint(job_dir)
    state = load(job_dir)
    if state.get("stage") != stage and "message" not in extra:
        state["message"] = ""
    state.update(stage=stage, **extra)
    save(job_dir, state)


def _render_reporter(job_dir: Path, ceiling: int = 55):
    """Keep the engine's current substage when percentage callbacks arrive."""
    current = {"stage": "rendering", "message": "", "pct": 0}
    def report():
        _stage(job_dir, current["stage"], message=current["message"],
               progress=45 + int(current["pct"] * ceiling / 100))
    def progress(pct):
        current["pct"] = max(current["pct"], min(100, max(0, pct)))
        report()
    def stage(code, detail):
        current.update(stage=code, message=detail)
        report()
    return progress, stage

def pause(job_dir: Path) -> dict:
    key = str(job_dir)
    with _lock:
        event = _pause_events.get(key)
        if event is None: raise ValueError("talking reel is not running")
        event.set()
    state = load(job_dir); state.update(status="paused", message="Paused by user"); return save(job_dir, state)

def resume(job_dir: Path) -> dict:
    key = str(job_dir)
    with _lock:
        event = _pause_events.get(key)
        if event is None: raise ValueError("talking reel is not running")
        event.clear()
    state = load(job_dir); state.update(status="running", message=""); return save(job_dir, state)

def cancel(job_dir: Path) -> dict:
    key = str(job_dir)
    with _lock:
        event, pause_event = _cancel_events.get(key), _pause_events.get(key)
        if event is None: raise ValueError("talking reel is not running")
        event.set()
        if pause_event: pause_event.clear()
    state = load(job_dir); state.update(status="canceled", message="Canceling…"); return save(job_dir, state)


def transcript_for(job_dir: Path, video: Path) -> dict:
    """ElevenLabs Scribe transcript with real word timings (cached per file).

    Estimated timings or a garbled fallback transcript make wrong cuts and
    wrong captions, so a failure stops here with a clear message.
    """
    from brain.transcribe import transcribe
    if load(job_dir).get('cached_render_only'):
        transcript = json.loads((job_dir / 'transcript.json').read_text())
        if not transcript.get('words'): raise ValueError('متن ذخیره‌شده معتبر نیست.')
        return transcript
    transcript = transcribe(video, job_dir, language="fa", engine="elevenlabs")
    if not transcript.get("words"):
        raise RuntimeError("no speech found in the video")
    return transcript


def _run(job_dir: Path, video: Path, *, regenerate: bool) -> None:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
    style = load(job_dir).get("style") or "talking_1"
    if style in SPLIT_STYLES:
        _run_split(job_dir, video, style, regenerate=regenerate)
    else:
        _run_talking_1(job_dir, video, regenerate=regenerate)


def _faces(job_dir: Path, video: Path, media) -> list:
    faces_path = job_dir / "talking_reel_faces.json"
    if faces_path.is_file():
        return [tuple(f) for f in json.loads(faces_path.read_text())]
    faces = media.track_faces(video)
    faces_path.write_text(json.dumps(faces))
    return faces


def _next_output(job_dir: Path) -> Path:
    exports = job_dir / "exports"
    exports.mkdir(exist_ok=True)
    version = len(list(exports.glob("talking_reel_v*.mp4"))) + 1
    return exports / f"talking_reel_v{version}.mp4"


def _run_talking_1(job_dir: Path, video: Path, *, regenerate: bool) -> None:
    from brain import talking_reel as brain
    from engine.talking_reel import get_style

    media = get_style("talking_1")
    _stage(job_dir, "loading transcript" if (job_dir / "transcript.json").is_file() else "transcribing", progress=5)
    transcript = transcript_for(job_dir, video)

    state = load(job_dir)
    decisions = state.get("decisions")
    if regenerate or not decisions:
        _stage(job_dir, "editing text", progress=20)
        decisions = brain.decide(transcript["sentences"])
        state = load(job_dir)
        state["decisions"] = decisions
        if regenerate or not state.get("hook"):
            state["hook"] = decisions["hook"]
            state["hook_highlight"] = decisions["hook_highlight"]
        save(job_dir, state)
    _stage(job_dir, "planning render", progress=35)
    planned = plan_render(job_dir, video)
    settings, plan = planned.settings, planned.plan
    _stage(job_dir, "rendering", progress=45)
    exports = job_dir / "exports"
    exports.mkdir(exist_ok=True)
    version = len(list(exports.glob("talking_reel_v*.mp4"))) + 1
    out = exports / f"talking_reel_v{version}.mp4"
    state = load(job_dir)

    progress, render_stage = _render_reporter(job_dir)

    media.render(video, plan, out, hook=state["hook"], highlight=state.get("hook_highlight") or [],
                 name=state.get("name") or "", title=state.get("title") or "",
                 work_dir=job_dir / "talking_reel_work", music=resolve_music(state.get("music")),
                 cta=state.get("cta") or "",
                 render_settings=settings,
                 logo_path=custom_logo(job_dir),
                 on_progress=progress, on_stage=render_stage)
    _apply_effects(job_dir, out, settings)
    _review_creative_output(job_dir,out)
    state = load(job_dir)
    state.update(status="done", stage="", message="", progress=100, output=f"exports/{out.name}",
                 published_outputs=[*published_outputs(state), f"exports/{out.name}"],
                 duration=round(plan.duration, 2), shots=len(plan.shots))
    save(job_dir, state)


MEDIA_DIR = "talking_media"            # the creator's own pictures for "صحبتی ۲"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def _apply_effects(job_dir: Path, output: Path, settings: dict) -> None:
    """The effects the person chose (orbit, spotlight, ...) are laid over the finished video. A failure keeps the plain video and says why."""
    plan = (settings or {}).get("effects") or []
    if not plan:
        return
    from engine import face_effects as effects
    _stage(job_dir, "rendering effects", progress=90, message="در حال افزودن افکت‌ها روی ویدیو")
    key = str(job_dir)
    temporary = output.with_name(output.stem + "_fx.mp4")

    def cancelled() -> bool:
        with _lock:
            event = _cancel_events.get(key)
        return bool(event and event.is_set())

    def progress(value: float, stage: str) -> None:
        try: _stage(job_dir, "rendering effects", progress=90 + int(value * 8), message="در حال افزودن افکت‌ها روی ویدیو")
        except TaskCanceled: raise
        except Exception: pass
    try:
        effects.apply(output, temporary, plan, work=job_dir / "talking_reel_work" / "effects", on_progress=progress, should_cancel=cancelled)
        os.replace(temporary, output)
        state = load(job_dir); state.pop("effects_error", None); save(job_dir, state)
    except effects.EffectsError as exc:
        temporary.unlink(missing_ok=True)
        _checkpoint(job_dir)
        state = load(job_dir); state["effects_error"] = str(exc)[:300]; save(job_dir, state)
        log.warning("effects were not applied for %s: %s", job_dir.name, exc)


def _review_creative_output(job_dir: Path, output: Path, moments: list[float] | None = None) -> None:
    from creative.review import required, review_export, enforce
    state=load(job_dir)
    direction=state.get('creative_plan')
    from creative.capabilities import TALKING_STYLES
    direction={**(direction or {}),'render_contract': {
        'style':state.get('style'),
        'style_description':TALKING_STYLES.get(state.get('style'),''),
        'hook':state.get('hook'),
        'pinned_hook_is_intentional':state.get('style')=='talking_1',
    }}
    from engine.probe import probe
    from engine.technical_qc import inspect_talking_export
    _stage(job_dir, 'checking export', candidate_output=f'exports/{output.name}')
    duration=float(probe(output)['format']['duration'])
    _stage(job_dir,'reviewing creative output',progress=99)
    technical=inspect_talking_export(output,duration=duration)
    _stage(job_dir, 'checking export', technical_qc=technical)
    if not required(direction):
        return
    report=review_export(output,direction,job_dir/'talking_reel_work/creative_review',
        duration=duration,moments=moments)
    _stage(job_dir,'reviewing creative output',progress=99,creative_review=report,
        technical_qc=technical,candidate_output=f'exports/{output.name}')
    enforce(report)



def published_outputs(state: dict) -> list[str]:
    """Only exports that crossed the publish gate belong in version history."""
    if 'published_outputs' in state:
        return list(dict.fromkeys(state['published_outputs']))
    output = state.get('output')
    report = state.get('creative_review') or {}
    approved = state.get('quality_accepted_by_user') or (
        report.get('status') in {None, 'passed'} and (state.get('visual_qc') or {}).get('passed', True))
    return [output] if output and state.get('status') == 'done' and approved else []

def user_media(job_dir: Path) -> list[Path]:
    folder = job_dir / MEDIA_DIR
    return sorted(p for p in folder.glob("*") if p.suffix.lower() in IMAGE_EXTENSIONS) if folder.is_dir() else []


def custom_logo(job_dir: Path) -> Optional[Path]:
    path = job_dir / "talking_reel_logo.png"
    return path if path.is_file() else None


def _library_pictures() -> list[dict]:
    index = PROJECT_ROOT / "assets" / "library_index.json"
    try:
        assets = json.loads(index.read_text()).get("assets") or []
    except (OSError, ValueError):
        return []
    return [a for a in assets if Path(str(a.get("path") or "")).suffix.lower() in IMAGE_EXTENSIONS
            and (PROJECT_ROOT / a["path"]).is_file()]


def resolve_pictures(job_dir: Path, decisions: dict, style: str, *,
                     generate_missing: bool = True) -> tuple[dict[int, str], list[dict]]:
    """Picture per B-roll slot: the creator's upload, then a library image, then an AI image.

    Returns ({sentence index: path}, slots for the settings card). Slots
    with no picture are drawn as text cards. AI images are cached by prompt.
    With ``generate_missing`` False nothing is generated: AI slots without a cached
    image stay in the result with source "ai_planned" and their future cache path.
    """
    import hashlib
    from concurrent.futures import ThreadPoolExecutor

    chip_slots = {c["i"] for c in decisions.get("chips", [])}
    uploads = {p.name: p for p in user_media(job_dir)}
    library = _library_pictures()
    pictures: dict[int, str] = {}
    slots: list[dict] = []
    wanted_ai = []
    for slot in decisions.get("broll", []):
        if slot["i"] in chip_slots:
            continue
        entry = {"i": slot["i"], "label": slot.get("label") or "", "source": "card", "file": None}
        if slot.get("media") in uploads:
            entry.update(source="upload", file=str(uploads[slot["media"]]))
        elif slot.get("library") and (PROJECT_ROOT / slot["library"]).is_file():
            entry.update(source="library", file=str(PROJECT_ROOT / slot["library"]))
        else:
            words = set((slot.get("label") or "").split()) | set(slot.get("visual", "").lower().split())
            match = next((a for a in library if words & {str(t).lower() for t in a.get("tags") or []}), None)
            if match:
                entry.update(source="library", file=str(PROJECT_ROOT / match["path"]))
            elif slot.get("visual"):
                provider_name = _talking_image_provider()
                # Include the renderer/prompt revision in the cache key so an
                # improved visual direction never silently reuses the old,
                # low-quality AI pictures.
                cache_material = f"minimal-v3|{style}|{provider_name}|{slot['visual']}"
                key = hashlib.sha256(cache_material.encode()).hexdigest()[:16]
                entry.update(source="ai", file=str(job_dir / "talking2_broll" / f"ai_{key}.png"))
                wanted_ai.append((_visual_prompt(slot["visual"], style), Path(entry["file"]), provider_name))
        slots.append(entry)

    def generate(item: tuple[str, Path, str]) -> None:
        prompt, dst, provider_name = item
        if dst.is_file():
            return
        if load(job_dir).get('cached_render_only'):
            raise ValueError('تصویر ذخیره‌شده موجود نیست؛ تولید مجدد نیازمند تأیید جداگانه است.')
        from brain.media_provider import get_provider

        dst.parent.mkdir(parents=True, exist_ok=True)
        result = get_provider(provider_name).generate_image(prompt, "1:1", dst.parent)
        Path(result.file_path).replace(dst)

    if not generate_missing:
        for entry in slots:
            if entry["file"] and Path(entry["file"]).is_file():
                pictures[entry["i"]] = entry["file"]
            elif entry["source"] == "ai":
                entry["source"] = "ai_planned"
                pictures[entry["i"]] = entry["file"]
        return pictures, slots
    with ThreadPoolExecutor(max_workers=4) as pool:
        for item, outcome in zip(wanted_ai, pool.map(lambda i: _try(generate, i), wanted_ai)):
            if outcome:
                log.warning("AI picture failed for %s: %s", item[1].name, outcome)
    for entry in slots:
        if entry["file"] and Path(entry["file"]).is_file():
            pictures[entry["i"]] = entry["file"]
        else:
            entry.update(source="card", file=None)
    return pictures, slots


def _talking_image_provider() -> str:
    """Best configured provider for talking-reel visuals.

    The premium Google model is preferred. Deployments can override this with
    TALKING_IMAGE_PROVIDER without changing the general content-creator model.
    """
    import os
    from brain.media_provider import get_provider

    return "arvan_image"


def _visual_prompt(subject: str, style: str) -> str:
    shared = (
        "Create one premium, restrained visual for a vertical educational reel. "
        "One clear focal subject, simple composition, generous negative space, crisp edges, "
        "subtle natural texture, tasteful studio art direction. No people, faces, hands, crowds, "
        "screens, charts, text, letters, logos, watermarks, surreal anatomy, glossy stock-art look, "
        "or generic AI aesthetics. Compose safely for a near-square editorial panel. "
    )
    if style == "talking_3":
        direction = (
            "Use a believable minimalist still-life photograph on charcoal or warm ivory, soft "
            "directional light, muted colors, premium editorial magazine mood. "
        )
    else:
        direction = (
            "Use a Swiss-style flat editorial illustration built from two to four recognizable "
            "everyday objects, off-white background, charcoal linework, and one muted teal or amber "
            "accent. Communicate the idea immediately; avoid meaningless abstract geometry. No gradients or 3D. "
        )
    return shared + direction + "Concept to communicate: " + subject.strip()


def _try(fn, item) -> Optional[str]:
    try:
        fn(item)
        return None
    except Exception as exc:  # one failed picture becomes a text card, not a failed render
        return str(exc)[:200]


SPLIT_STYLES = {   # style -> (brain module, decisions key, default music)
    "talking_2": ("brain.talking_reel_2", "decisions_2", "assets/music/motivational_piano_beat.mp3"),
    "talking_3": ("brain.talking_reel_3", "decisions_3", "assets/music/cinematic_pulse.mp3"),
    "talking_4": ("brain.talking_reel_4", "decisions_4", "assets/music/soft_lofi_loop.mp3"),
}


def _apply_timeline_choices(decisions: dict, style: str, settings: dict) -> dict:
    """Apply review choices to AI decisions before a render plan is built."""
    result = dict(decisions)
    result['source_cuts'] = settings.get('source_cuts') or []
    dropped = set(result.get('drop') or []) | set(settings.get('dropped_sentences') or [])
    result['drop'] = sorted(dropped)
    result['notes'] = [n for n in result.get('notes', []) if n.get('i') not in dropped]
    result['bw'] = [i for i in result.get('bw', []) if i not in dropped]
    if (result.get('cold_open') or {}).get('i') in dropped: result['cold_open'] = None
    if not settings.get("first_key_moment_enabled", True):
        result["cold_open"] = None
    elif settings.get("first_key_moment_sentence") is not None:
        cold = dict(result.get("cold_open") or {})
        cold["i"] = int(settings["first_key_moment_sentence"])
        result["cold_open"] = cold
    effect = settings.get("key_moment_effect", "grayscale_title")
    if not settings.get("key_moments_enabled", True) or effect == "none":
        for key in ("notes", "titles", "storyboard"):
            result[key] = []
        result["bw"] = []
    elif effect == "title_only":
        result["bw"] = []
    elif effect == "grayscale":
        result["notes"] = []
        result["titles"] = []
    disabled = set(settings.get("disabled_moments") or [])
    for key in ("notes", "titles", "storyboard", "broll"):
        kept = []
        for index, item in enumerate(result.get(key) or []):
            moment_id = f"{style}-{key}-{int(item.get('i', index))}-{index}"
            if moment_id not in disabled:
                kept.append(item)
        result[key] = kept
    return result


@dataclass
class PlannedReel:
    """Everything a render is built from. The render and the project timeline both use this, so the
    timeline always shows exactly what the renderer will produce."""
    style: str
    media: object
    transcript: dict
    decisions: dict
    settings: dict
    plan: object
    visual_plan: object = None
    pictures: dict = field(default_factory=dict)
    slots: list = field(default_factory=list)
    hyperframes: bool = False


def plan_render(job_dir: Path, video: Path, *, prepare_media: bool = True, apply_edits: bool = True) -> PlannedReel:
    """The render plan for the job's current decisions.

    ``prepare_media`` False is for reading only: no picture is generated, no face tracking runs and no
    transcription is requested; AI pictures that do not exist yet appear as "ai_planned" slots.
    ``apply_edits`` False returns the plan as the AI made it, without the user's timeline edits."""
    state = load(job_dir)
    style = str(state.get("style") or "talking_1")
    planned = (_plan_split(job_dir, video, style, prepare_media=prepare_media,
                           broll_edits=state.get("broll_edits") if apply_edits else None) if style in SPLIT_STYLES
               else _plan_talking_1(job_dir, video, prepare_media=prepare_media))
    if apply_edits and state.get("timeline_edits"):
        from app import timeline_edits
        for plan in {id(p): p for p in (planned.plan, planned.visual_plan) if p is not None}.values():
            timeline_edits.apply(plan, planned.transcript["sentences"], state["timeline_edits"])
    return planned


def _planning_transcript(job_dir: Path, video: Path, prepare_media: bool) -> dict:
    if prepare_media:
        return transcript_for(job_dir, video)
    path = job_dir / "transcript.json"
    if not path.is_file():
        raise ValueError("analyze the video before reading its timeline")
    return json.loads(path.read_text())


def _cached_faces(job_dir: Path) -> list:
    path = job_dir / "talking_reel_faces.json"
    return [tuple(f) for f in json.loads(path.read_text())] if path.is_file() else []


def _plan_talking_1(job_dir: Path, video: Path, *, prepare_media: bool) -> PlannedReel:
    from engine.talking_reel import get_style
    media = get_style("talking_1")
    transcript = _planning_transcript(job_dir, video, prepare_media)
    state = load(job_dir)
    if not state.get("decisions"):
        raise ValueError("analyze the video before planning the render")
    decisions = {**state["decisions"], "captions": {int(k): v for k, v in state["decisions"]["captions"].items()}}
    settings = state.get("render_settings") or DEFAULTS["render_settings"]
    decisions = _apply_timeline_choices(decisions, "talking_1", settings)
    from engine.revision_timing import prepare_transcript
    transcript, decisions = prepare_transcript(transcript, decisions)
    if prepare_media:
        _stage(job_dir, "tracking the face", progress=35)
    faces = _faces(job_dir, video, media) if prepare_media else _cached_faces(job_dir)
    plan = media.plan_reel(transcript, decisions, faces, float(transcript.get("duration") or 0)
                           or media.probe_video(video)[2])
    return PlannedReel("talking_1", media, transcript, decisions, settings, plan)


def _plan_split(job_dir: Path, video: Path, style: str, *, prepare_media: bool, broll_edits: dict | None = None) -> PlannedReel:
    from app.config import settings
    from engine.talking_reel import get_style
    _brain_name, decisions_key, _music = SPLIT_STYLES[style]
    media = get_style(style)
    transcript = _planning_transcript(job_dir, video, prepare_media)
    state = load(job_dir)
    decisions = state.get(decisions_key)
    if not decisions:
        raise ValueError("analyze the video before planning the render")
    decisions = {**decisions, "captions": {int(k): v for k, v in decisions["captions"].items()},
                 "hook": load(job_dir).get("hook2") or decisions["hook"]}
    render_settings = state.get("render_settings") or DEFAULTS["render_settings"]
    decisions = _apply_timeline_choices(decisions, style, render_settings)
    if broll_edits:
        from app import broll_edits as broll_layer
        decisions = broll_layer.apply(decisions, broll_edits)
    motion_panels={}
    panel_manifest=job_dir/'generated'/'motion_so'/'talking_panels.json'
    if style=='talking_2' and panel_manifest.is_file():
        for row in json.loads(panel_manifest.read_text()).get('panels',[]):
            key=str(row.get('clip',''))
            if not re.fullmatch('[a-f0-9]{24}',key):continue
            clip=panel_manifest.parent/(key+'.mp4')
            index=int(row['sentence'])
            if clip.is_file() and 0<=index<len(transcript['sentences']):motion_panels[index]=str(clip)
    hyperframes = style == "talking_2" and settings.TALKING_HYPERFRAMES_ENABLED
    if motion_panels:
        # Explicitly chosen Motion panels use the native split renderer. They do
        # not trigger HyperFrames, image generation, or media regeneration.
        hyperframes=False
        decisions={**decisions,'broll':[{'i':i,'label':'Motion'} for i in sorted(motion_panels)],
                   'chips':[c for c in decisions.get('chips',[]) if int(c['i']) not in motion_panels]}
    if prepare_media:
        _stage(job_dir, "planning visual beats" if hyperframes else "finding pictures", progress=25)
    if motion_panels:
        pictures=motion_panels
        slots=[{'i':i,'source':'motion_so','status':'ready'} for i in sorted(motion_panels)]
    elif hyperframes:
        # A neutral placeholder makes the proven style-2 renderer place the
        # speaker in the lower half. HyperFrames paints over the upper card,
        # so motion graphics never cover the speaker's face.
        from PIL import Image

        placeholder = job_dir / "talking_reel_work" / "motion_placeholder.png"
        placeholder.parent.mkdir(parents=True, exist_ok=True)
        if not placeholder.is_file():
            Image.new("RGB", (1080, 1080), "#F3F0E8").save(placeholder)
        pictures = {int(item["i"]): str(placeholder) for item in decisions.get("broll") or []}
        slots = [{"i": item["i"], "source": "motion", "status": "planned"}
                 for item in decisions.get("broll") or []]
    else:
        pictures, slots = resolve_pictures(job_dir, decisions, style, generate_missing=prepare_media)
    if prepare_media and not hyperframes and style in {"talking_2", "talking_3"} and decisions.get("broll"):
        required = min(2, len(decisions["broll"]))
        if len(pictures) < required:
            raise RuntimeError("Enough AI visuals were not generated. Check the image provider, then analyze and render again.")
        # A failed image slot should return to the real speaker, never become
        # an unattractive text-card substitute.
        decisions = {
            **decisions,
            "broll": [item for item in decisions["broll"] if item["i"] in pictures],
        }
    if prepare_media:
        _stage(job_dir, "tracking the face", progress=35, slots=slots)
    faces = _faces(job_dir, video, media) if prepare_media else _cached_faces(job_dir)
    source_duration = float(transcript.get("duration") or 0) or media.probe_video(video)[2]
    visual_plan = media.plan_reel(transcript, decisions, faces, source_duration, pictures)
    # The rough cut stays clean: HyperFrames owns the visual beats, while the
    # proven FFmpeg renderer keeps cuts, audio, face framing and Ray captions.
    clean_decisions = {**decisions, "chips": [], "broll": []} if hyperframes else decisions
    plan = media.plan_reel(transcript, clean_decisions, faces, source_duration,
                           {} if hyperframes else pictures)
    return PlannedReel(style, media, transcript, decisions, render_settings, plan, visual_plan,
                       pictures, slots, hyperframes)


def _run_split(job_dir: Path, video: Path, style: str, *, regenerate: bool) -> None:
    """The split-screen styles ("صحبتی ۲", "صحبتی ۳"): pictures on top, the speaker below."""
    from importlib import import_module

    from app.config import settings
    from engine.talking_reel import get_style

    brain_name, decisions_key, default_music = SPLIT_STYLES[style]
    brain = import_module(brain_name)
    media = get_style(style)
    _stage(job_dir, "loading transcript" if (job_dir / "transcript.json").is_file() else "transcribing", progress=5)
    transcript = transcript_for(job_dir, video)
    state = load(job_dir)
    decisions = state.get(decisions_key)
    if regenerate or not decisions:
        _stage(job_dir, "editing text", progress=15)
        decisions = brain.decide(transcript["sentences"], [p.name for p in user_media(job_dir)])
        state = load(job_dir)
        state[decisions_key] = decisions
        if regenerate or not state.get("hook2"):
            state["hook2"] = decisions["hook"]
        save(job_dir, state)
    _stage(job_dir, "planning render", progress=35)
    planned = plan_render(job_dir, video)
    decisions, transcript, hyperframes = planned.decisions, planned.transcript, planned.hyperframes
    render_settings, visual_plan, plan = planned.settings, planned.visual_plan, planned.plan
    _stage(job_dir, "rendering", progress=45)
    out = _next_output(job_dir)
    state = load(job_dir)

    progress, render_stage = _render_reporter(job_dir, 30 if hyperframes else 55)

    # The talking_1 default bed does not suit every style; an explicit choice wins.
    music = state.get("music")
    if music in (None, DEFAULT_MUSIC) and state.get("music") is not None and not state.get("music_chosen"):
        music = default_music
    rough = job_dir / "talking_reel_work" / "hyperframes_base.mp4" if hyperframes else out
    render_options=dict(work_dir=job_dir / "talking_reel_work",music=resolve_music(music),
        cta=state.get("cta") or "",render_settings=render_settings,logo_path=custom_logo(job_dir),on_progress=progress,on_stage=render_stage)
    if hyperframes:
        from engine.native_checkpoint import render_cached
        reused=render_cached(media.render,video,plan,rough,options=render_options,
            implementations=[Path(media.__file__),Path(media.base.__file__)])
        if reused:
            _stage(job_dir,'reusing prepared cut',progress=75)
    else:
        media.render(video,plan,rough,**render_options)
    if hyperframes:
        from engine.hyperframes import build_project, build_visual_beats, render_project

        beats = build_visual_beats(visual_plan, decisions, transcript)
        if not beats:
            raise RuntimeError("The visual planner produced no usable motion beats")
        _stage(job_dir, "building motion graphics", progress=78,
               renderer="hyperframes", visual_beats=[beat.model_dump() for beat in beats])
        project = job_dir / "talking_reel_work" / "hyperframes"
        from engine.probe import probe
        render_duration=float(probe(rough)['format']['duration'])
        build_project(project, rough, beats, duration=render_duration)
        _stage(job_dir, "rendering motion graphics", progress=82)
        _stage(job_dir, "rendering motion graphics", candidate_output=f"exports/{out.name}")
        render_project(
            project, out,
            on_progress=lambda pct: _stage(job_dir, "rendering motion graphics", progress=pct),
        )
        from engine.hyperframes.quality import review_render
        review = review_render(out, beats, job_dir / "talking_reel_work")
        _stage(job_dir, "reviewing motion graphics", progress=99, visual_qc=review,
               candidate_output=f"exports/{out.name}")
        if not review["passed"]:
            # A hard-coded rotation of templates is not a creative repair.
            # Keep the candidate and request a targeted, approved correction.
            raise QualityReviewRequired('بازبینی موشن نیازمند اصلاح است؛ رندر تکراری خودکار انجام نشد: '+
                '; '.join(review['problems']))
    _stage(job_dir, "checking export", candidate_output=f"exports/{out.name}")
    _apply_effects(job_dir, out, render_settings)
    _review_creative_output(job_dir,out,
        [(b.start+b.end)/2 for b in beats] if hyperframes else None)
    state = load(job_dir)
    state.update(status="done", stage="", message="", progress=100, output=f"exports/{out.name}",
                 published_outputs=[*published_outputs(state), f"exports/{out.name}"],
                 duration=round(plan.duration, 2), shots=len(plan.shots))
    save(job_dir, state)
