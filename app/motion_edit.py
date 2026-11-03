"""Structured edits of a motion graphic: what can be changed (read from the project itself) and applying a change to only what it touches.

`editable()` describes every field the current project really has: each scene's text, narration, entrance and idea, the colours, the voice, the
music and the mix, with their current values and the options the server accepts. The Edit tab renders exactly that list, and `apply()` validates
a change against the same list, so the tab never offers something the project cannot do and nothing is decided in the browser.

A change rebuilds only what it touches: a scene's text is patched into its saved design, a colour is swapped inside the saved designs, a changed
narration line is voiced again alone (and only that scene is redesigned for its new length), a voice or mix setting redoes the audio. The result
is a new version; the old one stays.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
COLOURS = {"bg": "Background", "surface": "Panels", "ink": "Text", "accent": "Accent", "accent2": "Second accent"}
RHYTHMS = {"speech_first": "Speech first", "balanced": "Balanced", "music_first": "Music first", "cinematic": "Cinematic"}
MUSIC_MODES = {"off": "No music", "library": "From the library"}


class EditError(ValueError):
    pass


def _plan(directory: Path) -> tuple[dict, str]:
    saved = json.loads((directory / "plan.json").read_text())
    return saved["plan"], saved.get("fp", "")


def _field(key: str, group: str, label: str, kind: str, value: Any, impact: str, **extra: Any) -> dict:
    return {"key": key, "group": group, "label": label, "type": kind, "value": value, "impact": impact, **extra}


def editable(directory: Path, record: dict) -> dict:
    """The groups and fields of this project's Edit tab, with current values, accepted options and what each change costs."""
    from brain import localize
    from creative import motion_graphic as mg
    from creative.audio import loudness
    plan, _ = _plan(directory)
    fields: list[dict] = []
    for n, scene in enumerate(plan.get("scenes", []), 1):
        spoken = bool((scene.get("narration") or "").strip())
        fields += [
            _field(f"scene.{n}.headline", "scenes", f"Scene {n} · on-screen text", "text", scene.get("headline", ""), "text", maxlength=90, scene=n),
            _field(f"scene.{n}.narration", "scenes", f"Scene {n} · narration", "textarea", scene.get("narration", ""), "voice", maxlength=400, scene=n, disabled=not spoken,
                   help="Only this line is voiced again; the scene is redesigned for its new length." if spoken else "This scene has no narration."),
            _field(f"scene.{n}.transition", "scenes", f"Scene {n} · how it enters", "select", scene.get("transition") or "", "assemble", scene=n,
                   options=[{"value": "", "label": "Chosen by the film's style"}, *[{"value": key, "label": f"{key} — {meaning[1]}"} for key, meaning in mg.ENTRANCE_LIBRARY.items()]]) if n > 1 else None,
            _field(f"scene.{n}.idea", "scenes", f"Scene {n} · what happens (redesigns this scene)", "textarea", scene.get("idea", ""), "scene", maxlength=600, scene=n),
        ]
    fields = [f for f in fields if f]
    colours = plan.get("palette") or {}
    fields += [_field(f"palette.{key}", "colours", label, "color", colours.get(key, "#000000"), "colours") for key, label in COLOURS.items()]
    fields += [
        _field("voice.narrator", "voice", "Narrator", "select", record.get("voice_id", "") or "", "audio",
               options=[{"value": vid, "label": f"{name} — {about}"} for vid, name, about in localize.NARRATORS]),
        _field("voice.style", "voice", "Delivery", "select", record.get("voice_style", "") or "", "audio",
               options=[{"value": key, "label": label} for key, (label, _tags) in localize.VOICE_STYLES.items()]),
        _field("voice.pronunciations", "voice", "Pronunciations (one per line: Written = Spoken)", "textarea",
               "\n".join(f"{a} = {b}" for a, b in (record.get("pronunciations") or {}).items()), "audio", maxlength=2000),
    ]
    music = record.get("music") or {}
    fields += [
        _field("music.mode", "audio", "Background music", "select", "off" if music.get("mode") in (None, "off") else "library" if music.get("mode") == "library" else "attached", "audio",
               options=[{"value": key, "label": label} for key, label in MUSIC_MODES.items()] + ([{"value": "attached", "label": "Your attached track"}] if music.get("mode") == "attached" else [])),
        _field("music.words", "audio", "Music mood (words searched in the library)", "text", music.get("words", ""), "audio", maxlength=120),
        _field("music.level_db", "audio", "Music level when nobody speaks (dB)", "number", record.get("music_gain_db") if record.get("music_gain_db") is not None else -10.0, "audio", min=-40, max=0, step=1),
        _field("music.ducking_db", "audio", "How far music drops under the voice (dB, 0 = off)", "number", record.get("ducking_db") if record.get("ducking_db") is not None else 12.0, "audio", min=0, max=30, step=1),
        _field("mix.loudness", "audio", "Delivery loudness", "select", record.get("loudness") or "social_video", "audio",
               options=[{"value": key, "label": f"{key.replace('_', ' ')} · {lufs:g} LUFS"} for key, (lufs, _tp, _lra) in loudness.PRESETS.items()] + [{"value": "off", "label": "No loudness processing"}]),
        _field("mix.rhythm", "audio", "Scene timing follows", "select", record.get("rhythm") or "speech_first", "audio", options=[{"value": key, "label": label} for key, label in RHYTHMS.items()]),
    ]
    titles = {"scenes": "Scenes", "colours": "Colours", "voice": "Voice", "audio": "Music & sound"}
    return {"groups": [{"id": gid, "title": titles[gid], "fields": [f for f in fields if f["group"] == gid]} for gid in ("scenes", "colours", "voice", "audio")],
            "busy": record.get("status") in ("queued", "writing", "checking", "rendering"), "version": record.get("current")}


def _clean(field: dict, value: Any) -> Any:
    kind = field["type"]
    if kind in ("text", "textarea"):
        text = str(value if value is not None else "").strip()
        if len(text) > field.get("maxlength", 1000):
            raise EditError(f"{field['label']}: at most {field['maxlength']} characters")
        if field["key"].endswith(".headline") and not text:
            raise EditError(f"{field['label']} cannot be empty")
        if field.get("disabled"):
            raise EditError(f"{field['label']}: {field.get('help', 'not editable')}")
        return text
    if kind == "select":
        if str(value) not in {o["value"] for o in field["options"]}:
            raise EditError(f"{field['label']}: not an available option")
        return str(value)
    if kind == "color":
        if not isinstance(value, str) or not HEX.match(value):
            raise EditError(f"{field['label']}: a colour like #1A2B3C")
        return value.upper()
    if kind == "number":
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise EditError(f"{field['label']}: a number")
        if not field["min"] <= number <= field["max"]:
            raise EditError(f"{field['label']}: between {field['min']} and {field['max']}")
        return round(number, 1)
    raise EditError("unknown field type")


def _patch_text(draft: dict, old: str, new: str) -> bool:
    """Swap a scene's on-screen text inside its saved design. False when the old text is not found whole (then the scene is redesigned instead)."""
    found = False
    for name in ("html", "build_js"):
        text = draft.get(name) or ""
        for variant_old, variant_new in ((html.escape(old, quote=False), html.escape(new, quote=False)), (old, new)):
            if variant_old and variant_old in text:
                text = text.replace(variant_old, variant_new); found = True
        draft[name] = text
    return found


def _swap_colour(draft: dict, old: str, new: str) -> None:
    pattern = re.compile(re.escape(old), re.I)
    for name in ("html", "css", "build_js", "update_js"):
        if draft.get(name):
            draft[name] = pattern.sub(new, draft[name])


def apply(directory: Path, record: dict, changes: dict[str, Any]) -> dict:
    """Validate `changes` against `editable()`, change the plan, the saved designs and the record, and say what will be redone. The caller starts the run."""
    catalog = {f["key"]: f for g in editable(directory, record)["groups"] for f in g["fields"]}
    clean: dict[str, Any] = {}
    for key, value in changes.items():
        if key not in catalog:
            raise EditError(f"'{key}' is not something this project can change")
        value = _clean(catalog[key], value)
        if value != catalog[key]["value"] and not (key == "voice.pronunciations" and value == catalog[key]["value"]):
            clean[key] = value
    if not clean:
        raise EditError("nothing changed")
    plan, fp = _plan(directory)
    scenes = plan["scenes"]
    redo = {"scenes": set(), "voice_lines": set(), "audio": False, "reassemble": False}
    scenes_dir = directory / "scenes"

    def draft_file(n: int) -> Path:
        return scenes_dir / f"s{n}.json"

    def load_draft(n: int) -> dict | None:
        try:
            return json.loads(draft_file(n).read_text())
        except (OSError, ValueError):
            return None

    palette_changes: dict[str, tuple[str, str]] = {}
    for key, value in clean.items():
        group, _, rest = key.partition(".")
        if group == "scene":
            n, _, attr = rest.partition(".")
            scene = scenes[int(n) - 1]
            previous = scene.get(attr) or ""
            scene[attr] = value
            if attr == "headline":
                cached = load_draft(int(n))
                if cached and _patch_text(cached["draft"], previous, value):
                    draft_file(int(n)).write_text(json.dumps(cached, ensure_ascii=False))
                else:
                    draft_file(int(n)).unlink(missing_ok=True); redo["scenes"].add(int(n))
            elif attr == "narration":
                redo["voice_lines"].add(int(n)); redo["scenes"].add(int(n))
            elif attr == "idea":
                draft_file(int(n)).unlink(missing_ok=True); redo["scenes"].add(int(n))
            elif attr == "transition":
                redo["reassemble"] = True
        elif group == "palette":
            old = (plan.get("palette") or {}).get(rest, "")
            plan.setdefault("palette", {})[rest] = value
            if old:
                palette_changes[rest] = (old, value)
            redo["reassemble"] = True
        else:
            redo["audio"] = True
    for n in range(1, len(scenes) + 1):                                        # colours are inside the saved designs: swap them there
        if palette_changes and (cached := load_draft(n)):
            for old, new in palette_changes.values():
                _swap_colour(cached["draft"], old, new)
            draft_file(n).write_text(json.dumps(cached, ensure_ascii=False))
    (directory / "plan.json").write_text(json.dumps({"fp": fp, "plan": plan}, ensure_ascii=False))

    if "voice.narrator" in clean: record["voice_id"] = clean["voice.narrator"]
    if "voice.style" in clean: record["voice_style"] = clean["voice.style"]
    if "voice.pronunciations" in clean:
        from creative.audio.persian import parse_dictionary
        record["pronunciations"] = parse_dictionary([l for l in clean["voice.pronunciations"].splitlines()])
    music = dict(record.get("music") or {})
    if "music.mode" in clean:
        music["mode"] = None if clean["music.mode"] == "off" else clean["music.mode"]
        if music["mode"] is None:
            music = {}
    if "music.words" in clean and clean.get("music.mode") != "off":
        music["words"] = clean["music.words"]
        music.setdefault("mode", "library")
    record["music"] = music or None
    if "music.level_db" in clean: record["music_gain_db"] = clean["music.level_db"]
    if "music.ducking_db" in clean: record["ducking_db"] = clean["music.ducking_db"]
    if "mix.loudness" in clean: record["loudness"] = clean["mix.loudness"]
    if "mix.rhythm" in clean: record["rhythm"] = clean["mix.rhythm"]

    parts = []
    if redo["voice_lines"]: parts.append("narration of scene " + ", ".join(map(str, sorted(redo["voice_lines"]))))
    if redo["scenes"]: parts.append("design of scene " + ", ".join(map(str, sorted(redo["scenes"]))))
    if palette_changes: parts.append("colours")
    if redo["reassemble"] and not palette_changes: parts.append("scene entrances")
    if redo["audio"]: parts.append("voice and sound settings")
    record["edit_pending"] = {"label": "Edit · " + "; ".join(parts), "fields": sorted(clean)}
    return {"changed": sorted(clean), "redo": {"scenes": sorted(redo["scenes"]), "voice_lines": sorted(redo["voice_lines"]), "audio": redo["audio"], "reassemble": redo["reassemble"]},
            "summary": parts}
