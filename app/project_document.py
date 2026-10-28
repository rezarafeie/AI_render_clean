"""Project Document: the engine-neutral timeline of a Studio project.

One document per project describes everything in the video as tracks of elements with stable ids:
the speaker clips, the upper picture panel, titles, captions, graphics, audio and the outro. Engines
produce it through adapters; the Talking adapter builds it from the exact render plan the renderer uses
(``talking_reel.plan_render``), so the timeline always matches what is (or will be) rendered.

Ids are derived from the source, not from positions, so they survive text edits: a caption is
``caption:s<sentence>:<n>`` (n-th caption of that transcript sentence), a picture is ``picture:s<slot>``.

Each element says how it can be changed today (``edit.via``: "plan", "chat", "timeline"); only captions are
editable on the timeline so far, through the edits layer (``timeline_edits``), and nothing claims an edit the
renderer cannot apply.
"""
from __future__ import annotations

from pathlib import Path

from app import timeline_edits as edits_layer

SCHEMA = 1

TRACKS = {   # id -> (kind, Persian label), in display order
    "video": ("video", "گوینده"),
    "panel": ("broll", "تصویر بالا"),
    "titles": ("title", "هوک و عنوان‌ها"),
    "captions": ("caption", "زیرنویس"),
    "graphics": ("motion", "گرافیک و تأکید"),
    "voice": ("audio", "صدای گوینده"),
    "music": ("music", "موسیقی"),
    "outro": ("video", "پایان (CTA و لوگو)"),
}

PICTURE_SOURCES = {
    "hidden": "بدون تصویر",
    "upload": "فایل شما", "library": "کتابخانه", "ai": "ساخته‌شده با هوش مصنوعی",
    "ai_planned": "با هوش مصنوعی ساخته می‌شود (هنوز ساخته نشده)", "motion_so": "کلیپ موشن هوشمند", "motion": "موشن HyperFrames",
    "card": "کارت متنی",
}


def _r(value: float) -> float:
    return round(float(value), 3)


def _element(id_: str, type_: str, start: float, end: float, label: str, *, text: str = "", source: dict | None = None,
             props: dict | None = None, via: list[str] | None = None, note: str = "") -> dict:
    return {"id": id_, "type": type_, "start": _r(start), "end": _r(max(end, start)), "label": label, "text": text,
            "source": source or {}, "props": props or {}, "edit": {"via": via or [], "note": note}}


def _caption_frames(planned, job_dir: Path, state: dict) -> dict[int, dict]:
    """Where each caption sits on the 1080x1920 frame, read from the ASS the style itself builds (no looks applied).

    Style 4 is drawn by Tscaps (always horizontally centred): its place comes from the role, and is approximate."""
    from engine import caption_looks
    from engine.talking_styles import talking_1 as first
    style, plan = planned.style, planned.plan
    try:
        if style == "talking_5":
            return {i: {"x": 540.0, "y": 0.70 * 1920, "size": 96.0, "box": None, "style": "words", "font": "Ray Bold", "x_locked": True}
                    for i in range(len(plan.captions))}
        if style == "talking_4":
            from engine import tscaps_overlay as tso
            vertical = float(tso.ROLES["caption"]["alignment"]["verticalOffset"])
            return {i: {"x": 540.0, "y": vertical * 1920, "size": 4.8 * 19.2, "box": None, "style": "tscaps", "font": "Ray Bold", "x_locked": True}
                    for i in range(len(plan.captions))}
        fonts = first.fonts_bundle(job_dir / "talking_reel_work")
        if style == "talking_1":
            ass = planned.media.build_ass(plan, state.get("hook") or "", state.get("hook_highlight") or [], state.get("name") or "",
                                          state.get("title") or "", fonts, moments=False)
        else:
            ass = planned.media.build_ass(plan, fonts)
        frames = caption_looks.geometry(ass, plan.captions)
        for frame in frames.values():
            frame["fonts_dir"] = str(fonts)
            if planned.settings.get("caption_font") == "Vazirmatn":      # the render swaps the caption font the same way
                frame["font"] = "Vazirmatn"
        return frames
    except Exception:
        return {}


def _text_width(frame: dict, text: str) -> float:
    """Width of the caption text in frame pixels (measured with the style's own font, estimated if that fails)."""
    if frame.get("box") or not text:
        return 0.0
    try:
        from engine.localize import measure_text_boxes
        return float(measure_text_boxes([(text, int(frame["size"]))], 1080, 1920, frame["font"], Path(frame["fonts_dir"]))[0][0])
    except Exception:
        return min(1000.0, frame["size"] * 0.55 * len(text))


def talking_document(job_dir: Path, video: Path) -> dict:
    from app import talking_reel
    from engine.talking_styles.talking_1 import CTA_SECONDS, LOGO, LOGO_SECONDS

    planned = talking_reel.plan_render(job_dir, video, prepare_media=False, apply_edits=False)
    plan, style, state = planned.plan, planned.style, talking_reel.load(job_dir)
    sentences = planned.transcript["sentences"]
    clock = edits_layer.Clock(plan.shots[1:] if plan.cold_open else plan.shots, sentences)
    tracks: dict[str, list[dict]] = {key: [] for key in TRACKS}
    split_style = style != "talking_1"

    # Speaker clips. Cuts come from the speech (pauses and fillers are removed), not from a hand edit.
    for index, shot in enumerate(plan.shots):
        cold = bool(plan.cold_open) and index == 0
        framing = ("پایین قاب (تصویر بالا)" if getattr(shot, "split", False) else
                   "نمای بسته" if shot.close else "نمای باز")
        if getattr(shot, "bw", False):
            framing += " · سیاه‌وسفید"
        tracks["video"].append(_element(
            f"clip:{int(round(shot.src_in * 1000))}", "clip", shot.out_start, shot.out_start + shot.length,
            ("پیش‌نمایش ابتدایی · " if cold else "") + framing,
            source={"kind": "upload", "label": video.name, "in": _r(shot.src_in), "out": _r(shot.src_out)},
            props={"close": bool(shot.close), "split": bool(getattr(shot, "split", False)),
                   "bw": bool(getattr(shot, "bw", False)), "push": bool(getattr(shot, "push", False)), "cold_open": cold},
            via=["chat"], note="برش‌ها از گفتار ساخته می‌شوند (مکث و کلمه‌های اضافه حذف می‌شوند)؛ برش دستی در مرحلهٔ بعد اضافه می‌شود."))

    # The upper picture panel of the split styles: one element per contiguous run of the same slot, showing the
    # AI's choice with the user's picture edit (broll_edits) laid over it.
    if split_style:
        slots = {int(s["i"]): s for s in planned.slots}
        picture_edits = state.get("broll_edits") or {}
        effective = ({int(s["i"]): s for s in talking_reel.plan_render(job_dir, video, prepare_media=False).slots}
                     if picture_edits else slots)
        ai_choice = {int(item["i"]): item for item in (planned.decisions.get("broll") or [])}
        full = getattr(plan, "full_pictures", set())
        cards = getattr(plan, "card_pictures", set())
        # With HyperFrames on, style 2's upper panel is an authored motion scene painted over a placeholder, so a
        # replacement picture would never appear: the picture editor is offered only where it has an effect.
        motion_scene = bool(planned.hyperframes)
        editable = style in {"talking_2", "talking_3"} and not motion_scene
        run: list = []

        def close_run():
            if not run:
                return
            slot = run[0].slot
            info = slots.get(slot, {})
            edit = picture_edits.get(str(slot))
            hidden = bool(edit and edit.get("source") == "hidden")
            shown = effective.get(slot, {}) if not hidden else {}
            kind = shown.get("source") or info.get("source") or ("motion" if planned.hyperframes else "card")
            picture = run[0].picture
            layout = ("تمام‌قاب" if any(id(s) in full for s in run) else
                      "کارت کج" if picture in cards else "بالای قاب")
            plan_item = ai_choice.get(slot, {})
            file_name = shown.get("file") or info.get("file")
            tracks["panel"].append(_element(
                f"picture:s{slot}", "picture", run[0].out_start, run[-1].out_start + run[-1].length,
                shown.get("label") or info.get("label") or (sentences[slot]["text"][:40] if slot is not None and slot < len(sentences) else "تصویر"),
                source={"kind": "hidden" if hidden else kind, "label": "بدون تصویر" if hidden else PICTURE_SOURCES.get(kind, kind),
                        "file": Path(file_name).name if file_name and not hidden else None},
                props={"layout": layout, "sentence": slot, "edited": bool(edit), "hidden": hidden,
                       "prompt": plan_item.get("visual", ""), "editable": editable,
                       "needs_generation": kind == "ai_planned" and not hidden, "motion_scene": motion_scene,
                       "original": {"source": info.get("source") or "card", "visual": plan_item.get("visual", ""),
                                    "label": info.get("label", "")},
                       "current": picture_edits.get(str(slot))},
                via=(["timeline", "chat"] if editable else ["chat"] if motion_scene else []),
                note=("تصویر این بخش را همین‌جا عوض یا حذف کنید؛ تصویر تازه بعد از تأیید برنامه ساخته می‌شود." if editable else
                      "این بخش یک صحنهٔ موشن طراحی‌شده است، نه تصویر؛ تغییرش را در چت بخواهید." if motion_scene else "")))
            run.clear()

        for shot in plan.shots:
            if getattr(shot, "split", False) and shot.slot is not None and (shot.picture or shot.slot in slots):
                if run and run[-1].slot != shot.slot:
                    close_run()
                run.append(shot)
            else:
                close_run()
        close_run()

    # Hook and titles.
    hook_text = state.get("hook") if style == "talking_1" else (state.get("hook2") or state.get("hook"))
    if style == "talking_1" and hook_text:
        tracks["titles"].append(_element("hook", "title", 0, plan.duration, "هوک ثابت", text=hook_text,
                                         props={"highlight": state.get("hook_highlight") or [], "persistent": True},
                                         via=["plan", "chat"], note="متن و کلمهٔ رنگی هوک را در برنامه یا چت عوض کنید."))
    elif getattr(plan, "hook", None):
        tracks["titles"].append(_element("hook", "title", plan.hook["start"], plan.hook["end"], "هوک", text=plan.hook["text"],
                                         via=["plan", "chat"], note="متن هوک را در برنامه یا چت عوض کنید."))
    for title in getattr(plan, "titles", []) or []:
        sentence = clock.sentence(title["start"])
        tracks["titles"].append(_element(f"title:s{sentence}", "title", title["start"], title["end"], "عنوان فصل",
                                         text=title["text"], via=["chat"]))
    for card in getattr(plan, "cards", []) or []:
        sentence = clock.sentence(card["start"])
        tracks["graphics"].append(_element(f"card:s{sentence}", "card", card["start"], card["end"], "کارت متنی",
                                           text=card["text"], via=["chat"]))

    # Captions, with ids from their transcript sentence and the user's edits laid over the AI's version.
    edits = state.get("timeline_edits") or {}
    caption_ids = edits_layer.caption_ids(plan, sentences)
    frames = _caption_frames(planned, job_dir, state)
    from engine.caption_looks import effective_rect
    for index, (element_id, caption) in enumerate(zip(caption_ids, plan.captions)):
        edit = edits.get(element_id)
        shown = edits_layer.merge_caption(caption, edit) or caption
        teaser = element_id.startswith("caption:cold")
        sentence = None if element_id.split(":")[-2] == "sx" else int(element_id.split(":")[-2][1:])
        original = {"text": edits_layer.caption_text(caption), "start": _r(caption["start"]), "end": _r(caption["end"])}
        frame = frames.get(index)
        look = (shown.get("look") or {}) if shown is not caption else {}
        placed = None
        if frame:
            width = _text_width(frame, edits_layer.caption_text(shown))
            from app.fonts import font_file
            placed = {"font": frame.get("font") or "", "font_file": font_file(frame.get("font") or ""),
                      "x": frame["x"], "y": frame["y"], "size": frame["size"], "boxed": bool(frame["box"]),
                      "x_locked": bool(frame.get("x_locked")),
                      "rect": {k: round(v, 1) for k, v in effective_rect(frame, None, width).items()},
                      "now": {k: round(v, 1) for k, v in effective_rect(frame, look, width).items()}}
        tracks["captions"].append(_element(
            element_id, "caption", shown["start"], shown["end"],
            ("پیش‌نمایش ابتدایی · " if teaser else "") + (f"جملهٔ {sentence + 1}" if sentence is not None else ""),
            text=edits_layer.caption_text(shown),
            props={"sentence": sentence, "key": shown.get("key"), "edited": bool(edit), "deleted": bool(edit and edit.get("deleted")),
                   "original": original, "look": look, "frame": placed},
            via=["timeline", "chat"], note="متن، زمان، جای زیرنویس روی تصویر، اندازه و رنگ آن را همین‌جا عوض کنید یا آن را پنهان کنید."))
    stale = sorted(set(edits) - set(caption_ids))

    # Graphics: chips (lists), key moments (style 1) and authored motion scenes (style 2 with HyperFrames).
    for chip in getattr(plan, "chips", []) or []:
        sentence = clock.sentence(chip["start"])
        tracks["graphics"].append(_element(f"chips:s{sentence}", "chips", chip["start"], chip["end"], "فهرست",
                                           text=" · ".join(chip["items"]), via=["chat"]))
    for note in getattr(plan, "notes", []) or []:
        sentence = clock.sentence(note["start"])
        tracks["graphics"].append(_element(f"moment:s{sentence}", "moment", note["start"], note["end"], "لحظهٔ کلیدی",
                                           text=note.get("text", ""), props={"effect": (planned.settings or {}).get("key_moment_effect")},
                                           via=["plan"], note="لحظه‌های کلیدی را در برنامه روشن یا خاموش کنید."))
    for k, t in enumerate(getattr(plan, "flashes", []) or []):
        tracks["graphics"].append(_element(f"flash:{k}", "flash", max(0.0, t - 0.1), t + 0.28, "فلش نور", via=[]))
    for beat in state.get("visual_beats") or []:
        if "start" in beat and "end" in beat:
            tracks["graphics"].append(_element(f"motion:{beat.get('id') or beat['start']}", "motion", beat["start"], beat["end"],
                                               beat.get("title") or "صحنهٔ موشن",
                                               source={"kind": "motion", "label": "طراحی‌شده" if beat.get("authored") else "قالب"},
                                               via=["chat"]))

    # Audio.
    tracks["voice"].append(_element("voice", "audio", 0, plan.duration, "صدای اصلی",
                                    source={"kind": "upload", "label": video.name},
                                    note="صدا همراه هر برش تصویر بریده می‌شود و بلندی آن یکسان‌سازی می‌شود."))
    music = talking_reel.resolve_music(state.get("music"))
    outro_logo = (planned.settings or {}).get("outro_logo") or {}
    logo_on = bool(outro_logo.get("enabled", True)) and (bool(talking_reel.custom_logo(job_dir)) or LOGO.is_file())
    cta = (state.get("cta") or "").strip()
    outro_seconds = (CTA_SECONDS if cta else 0.0) + (LOGO_SECONDS if logo_on else 0.0)
    total = plan.duration + outro_seconds
    from engine import music_mix
    mix = music_mix.resolve(planned.style, planned.settings)
    mix_props = {"volume_db": mix.volume_db, "fade_in": mix.fade_in, "fade_out": mix.fade_out, "duck": mix.duck,
                 "defaults": music_mix.defaults(planned.style), "edited": bool((planned.settings or {}).get("music_mix")),
                 "library": talking_reel.music_library()}
    if music:
        tracks["music"].append(_element("music", "music", 0, total, music.stem.replace("_", " "),
                                        source={"kind": "library", "label": music.name},
                                        props={**mix_props, "path": state.get("music")}, via=["timeline", "chat"],
                                        note="بلندی، محو شدن و کاهش خودکار موسیقی هنگام صحبت را همین‌جا عوض کنید یا موسیقی دیگری انتخاب کنید."))
    else:
        tracks["music"].append(_element("music", "music", 0, total, "بدون موسیقی",
                                        source={"kind": "library", "label": ""}, props={**mix_props, "path": None},
                                        via=["timeline", "chat"], note="موسیقی‌ای انتخاب نشده؛ از اینجا یکی را انتخاب کنید."))

    # Outro.
    if cta:
        tracks["outro"].append(_element("cta", "cta", plan.duration, plan.duration + CTA_SECONDS, "دعوت به اقدام", text=cta,
                                        via=["plan", "chat"]))
    if logo_on:
        start = plan.duration + (CTA_SECONDS if cta else 0.0)
        tracks["outro"].append(_element("logo", "logo", start, start + LOGO_SECONDS, "لوگوی متحرک",
                                        props={"motion": outro_logo.get("motion", "pop")}, via=["plan"]))

    return {
        "schema": SCHEMA, "engine": "talking", "style": style,
        "canvas": {"width": 1080, "height": 1920, "fps": 30},
        "duration": _r(total), "content_duration": _r(plan.duration),
        "stale_edits": stale, "edit_count": len(edits) - len(stale) + len(state.get("broll_edits") or {}),
        "tracks": [{"id": key, "kind": TRACKS[key][0], "label": TRACKS[key][1], "elements": sorted(items, key=lambda e: e["start"])}
                   for key, items in tracks.items() if items],
    }


# -- Localize -----------------------------------------------------------------------------------

def localize_fingerprint(state: dict) -> str:
    """Hash of everything that changes a Localize render's picture or sound."""
    import hashlib
    import json
    relevant = {
        "lines": [(l.get("i"), l.get("start"), l.get("end"), l.get("fa"), l.get("kind"), len(l.get("covers") or []))
                  for l in state.get("lines") or []],
        "placements": [(p.get("i"), p.get("start"), p.get("end"), p.get("tempo")) for p in state.get("placements") or []],
        **({"caption_looks": state["caption_looks"]} if state.get("caption_looks") else {}),   # absent when unedited: old fingerprints stay valid
        **{k: state.get(k) for k in ("title", "title_layout", "title_emojis", "title_box", "caption_box", "end_card",
                                      "end_card_seconds", "cta_number", "music", "voice_provider", "voice_id", "voice_style")},
    }
    return hashlib.sha256(json.dumps(relevant, sort_keys=True, default=str).encode()).hexdigest()[:16]


_LOCALIZE_FRAMES: dict = {}


def _localize_frames(state: dict, windows: list[tuple], placements: list[dict], w: int, h: int, duration: float,
                     source_duration: float, card_at: float | None) -> dict[int, dict]:
    """Where each Localize caption sits on the frame, read from the overlay the renderer itself lays out (no looks).

    Only for the 1080x1920 frame the on-frame editor draws on; other sizes can still be edited as text."""
    from app import localize as store
    from app.fonts import font_file
    from engine import localize as media
    from engine.caption_looks import effective_rect

    if (w, h) != (1080, 1920):
        return {}
    fonts_dir = store.PROJECT_ROOT / "presets" / "fonts"
    style = store.render_style({**state, "caption_looks": {}}, store.next_version(state["id"]))
    key = (state["id"], localize_fingerprint(style), style["caption_box"], duration, source_duration)
    raw = _LOCALIZE_FRAMES.get(key)
    if raw is None:                       # laying the captions out measures every line with libass: seconds, so remembered
        raw = {}
        try:
            media.plan_overlays(style, placements, w, h, duration, font_file=fonts_dir / "RAY-EXTRABLACK.TTF", fonts_dir=fonts_dir,
                                source_duration=source_duration, end_card_at=card_at, frames=raw)
        except Exception:
            return {}
        if len(_LOCALIZE_FRAMES) >= 8:
            _LOCALIZE_FRAMES.pop(next(iter(_LOCALIZE_FRAMES)))
        _LOCALIZE_FRAMES[key] = raw
    looks = state.get("caption_looks") or {}
    ids = media.caption_ids(windows)
    out = {}
    for index, frame in raw.items():
        geometry = {"x": frame["x"], "y": frame["y"], "size": frame["size"],
                    "box": {"dx": -frame["w"] / 2, "dy": -frame["h"] / 2, "w": frame["w"], "h": frame["h"]}}
        look = looks.get(ids[index]) if index < len(ids) else None
        out[index] = {"font": media.END_CARD_FONT, "font_file": font_file(media.END_CARD_FONT), "x": round(frame["x"], 1),
                      "y": round(frame["y"], 1), "size": frame["size"], "boxed": True, "x_locked": False,
                      "box_color": frame["box_color"], "text_color": frame["text_color"], "covers_english": frame["cover"],
                      "lines": frame.get("lines") or [],
                      "rect": {k: round(v, 1) for k, v in effective_rect(geometry, None).items()},
                      "now": {k: round(v, 1) for k, v in effective_rect(geometry, look).items()}}
    return out


def localize_document(project_id: str) -> dict:
    """Timeline of a Localize project from the same functions the renderer uses (engine.localize)."""
    from app import localize as store
    from engine import localize as media

    state = store.load(project_id)
    if not state.get("lines"):
        raise ValueError("The timeline appears once the video has been analysed")
    root = store._dir(project_id)
    _w, _h, source_duration = media.probe_video(root / state["source"])
    placements = state.get("placements") or []
    end_card = state.get("end_card", True)
    duration, card_at = media.output_timing(state, placements, source_duration)
    end_all = max(0.01, (card_at if end_card else duration) - 0.02)
    tracks: dict[str, list[dict]] = {key: [] for key in LOCALIZE_TRACKS}
    names = {"video": ("video", "ویدیوی اصلی"), "titles": ("title", "عنوان"), "captions": ("caption", "زیرنویس فارسی"),
             "voice": ("audio", "دوبله فارسی"), "audio": ("audio", "صدای اصلی"), "music": ("music", "موسیقی"),
             "outro": ("video", "پایان")}

    tracks["video"].append(_element("source", "clip", 0, card_at, "ویدیوی منبع",
                                    source={"kind": "upload", "label": state.get("name") or "ویدیو", "in": 0.0, "out": _r(card_at)},
                                    via=["advanced"], note="ویدیوی منبع بدون برش پخش می‌شود."))
    if end_card:
        number = str(state.get("cta_number") or "").strip() or "31"
        tracks["outro"].append(_element("end_card", "cta", card_at, duration, "کارت پایانی",
                                        text=media.END_CARD_LINES[0].format(n=number), props={"cta_number": number},
                                        via=["advanced"], note="شمارهٔ کارت پایانی را در ویرایشگر Localize عوض کنید."))
    elif duration > source_duration + 0.05:
        tracks["outro"].append(_element("hold", "clip", source_duration, duration, "ثابت‌ماندن آخرین فریم",
                                        note="تا پایان دوبلهٔ فارسی آخرین فریم نگه داشته می‌شود."))

    title = (state.get("title") or "").strip()
    layout = state.get("title_layout") or {}
    if title:
        tracks["titles"].append(_element("title", "title", layout.get("start", 0.0), layout.get("end", min(duration, 6.0)), "عنوان",
                                         text=title + (" " + state["title_emojis"] if state.get("title_emojis") else ""),
                                         via=["advanced", "chat"]))

    windows = media.caption_windows({**state, "caption_looks": {}}, placements, end_all)   # the AI's captions, before any look
    ids = media.caption_ids(windows)
    looks = state.get("caption_looks") or {}
    frames = _localize_frames(state, windows, placements, *media.output_size(_w, _h), duration, source_duration, card_at if end_card else None)
    for index, (element_id, (line, start, stop, cover)) in enumerate(zip(ids, windows)):
        look = looks.get(element_id) or {}
        frame = frames.get(index)
        tracks["captions"].append(_element(
            element_id, "caption", start, stop, f"خط {line['i'] + 1}", text=line["fa"],
            props={"line": line["i"], "english": line.get("en", ""), "covers_english": cover is not None, "kind": line.get("kind"),
                   "edited": bool(look), "deleted": False, "look": look, "frame": frame},
            via=(["timeline", "advanced", "chat"] if frame else ["advanced", "chat"]),
            note=("جا، اندازه و رنگ زیرنویس را روی تصویر عوض کنید؛ " if frame else "") +
                 "ترجمه را در ویرایشگر Localize یا با چت اصلاح کنید؛ متن انگلیسی منبع: «" + str(line.get("en", ""))[:80] + "»"))
    stale = sorted(set(looks) - set(ids))

    for placed in placements:
        line = next((l for l in state["lines"] if l["i"] == placed["i"]), {})
        tracks["voice"].append(_element(
            f"voice:l{placed['i']}", "audio", placed["start"], placed["end"], f"دوبلهٔ خط {placed['i'] + 1}", text=line.get("fa", ""),
            props={"tempo": placed.get("tempo"), "line": placed["i"]}, via=["advanced"],
            note="صدای هر خط جدا ساخته می‌شود؛ بازسازی یک جمله ممکن است هزینهٔ صدا داشته باشد."))
    if placements:
        cut = media.audio_cut_time(state["lines"], placements)
        if cut > 0.05:
            tracks["audio"].append(_element("original_audio", "audio", 0, cut, "صدای اصلی تا شروع دوبله",
                                            source={"kind": "upload", "label": state.get("name") or "ویدیو"}))
    from app.localize import resolve_music
    music = resolve_music(state.get("music"))
    if music:
        tracks["music"].append(_element("music", "music", 0, duration, music.stem.replace("_", " "),
                                        source={"kind": "library", "label": music.name}, via=["advanced"]))

    output = state.get("output")
    fingerprint = localize_fingerprint(state)
    rendered = state.get("rendered_fingerprint")
    return {
        "schema": SCHEMA, "engine": "localize", "style": None,
        "canvas": {"width": media.output_size(_w, _h)[0], "height": media.output_size(_w, _h)[1], "fps": 30},
        "duration": _r(duration), "content_duration": _r(card_at),
        "notes": ([] if placements else ["صدای دوبله بعد از ساخت صدا به تایم‌لاین اضافه می‌شود."]),
        "stale_edits": stale, "edit_count": len(set(looks) & set(ids)),
        # None = unknown (rendered before this was recorded): the player is not claimed to match.
        "basis": {"plan_version": None, "rendered_version": None, "workflow": state.get("status"),
                  "synced": (rendered == fingerprint) if (output and rendered) else None},
        "tracks": [{"id": key, "kind": names[key][0], "label": names[key][1], "elements": sorted(items, key=lambda e: e["start"])}
                   for key, items in tracks.items() if items],
    }


LOCALIZE_TRACKS = ("video", "titles", "captions", "voice", "audio", "music", "outro")


# -- Motion (generic Edit Plan engine) ----------------------------------------------------------

MOTION_TRACKS = {"video": ("video", "صحنه‌ها"), "panel": ("broll", "B-roll"), "titles": ("title", "هوک و عنوان"),
                 "captions": ("caption", "زیرنویس"), "effects": ("effect", "افکت تصویر"), "graphics": ("motion", "ترنزیشن‌ها"), "voice": ("audio", "نریشن"),
                 "sfx": ("audio", "افکت صوتی"), "music": ("music", "موسیقی")}
CAPTION_STYLE = {"normal": "معمولی", "emphasis": "تأکیدی", "cta": "دعوت به اقدام", "cover": "تیتر ابتدایی"}


def _file_seconds(path: str) -> float:
    try:
        from engine.probe import probe_duration
        return float(probe_duration(Path(path))) if Path(path).is_file() else 0.0
    except Exception:
        return 0.0


def motion_document(job) -> dict:
    """Timeline of a Motion project from its Edit Plan (what the MLT renderer consumes), or, before a render
    plan exists, from the approved storyboard (clearly marked as a plan, not a render)."""
    from app import jobs as jobstore
    from engine.schema import validate_plan

    tracks: dict[str, list[dict]] = {key: [] for key in MOTION_TRACKS}
    storyboard_path = Path(job.dir) / "storyboard.json"
    scenes = []
    if storyboard_path.is_file():
        import json
        scenes = json.loads(storyboard_path.read_text()).get("scenes") or []
    try:
        data = jobstore.load_plan(job)
    except FileNotFoundError:
        data = None
    plan = None
    if data is not None:
        plan, errors = validate_plan(data, base_dir=Path(job.dir), check_media=False)
        if plan is None:
            raise ValueError("The saved plan is not valid: " + "; ".join(errors[:2]))

    if plan is None:
        if not scenes:
            raise ValueError("The timeline appears once the storyboard or plan exists")
        cursor = 0.0
        for index, scene in enumerate(scenes):
            length = float(scene.get("duration_s") or 0)
            tracks["video"].append(_element(
                f"scene:{index}", "clip", cursor, cursor + length, f"صحنه {index + 1}", text=scene.get("text_overlay") or "",
                source={"kind": scene.get("media_method") or "card", "label": scene.get("media_method") or ""},
                props={"description": scene.get("description", ""), "planned": True}, via=["chat"],
                note="این برنامهٔ استوری‌بورد است؛ بعد از تولید دارایی‌ها به برنامهٔ رندر تبدیل می‌شود."))
            if scene.get("narration_text"):
                tracks["voice"].append(_element(f"narration:{index}", "audio", cursor, cursor + length, f"نریشن صحنه {index + 1}",
                                                text=scene["narration_text"], props={"planned": True}, via=["chat"]))
            cursor += length
        duration, fps = cursor, 30
        notes = ["این تایم‌لاین از استوری‌بورد ساخته شده؛ هنوز برنامهٔ رندر وجود ندارد."]
        canvas = {"width": 1080, "height": 1920, "fps": 30}
    else:
        fps = plan.canvas.fps
        placed = plan.segment_frames()
        effects = {e.segment_id: e.type for e in plan.visual_effects}
        from engine.effects_v4 import EFFECT_CATALOG_V4
        for index, (segment, (start, count)) in enumerate(zip(plan.segments, placed)):
            scene = scenes[index] if index < len(scenes) else {}
            tracks["video"].append(_element(
                f"segment:{segment.id}", "clip", start / fps, (start + count) / fps, f"صحنه {index + 1}",
                text=scene.get("text_overlay") or "",
                source={"kind": "upload", "label": Path(plan.source).name, "in": _r(segment.in_), "out": _r(segment.out)},
                props={"effect": effects.get(segment.id), "zoom": [segment.zoom.from_, segment.zoom.to]}, via=["chat"],
                note="جلوهٔ حرکتی و برش این صحنه را در چت عوض کنید."))
            if segment.id in effects:
                effect = effects[segment.id]
                tracks["effects"].append(_element(
                    f"effect:{segment.id}", "effect", start / fps, (start + count) / fps,
                    EFFECT_CATALOG_V4.get(effect, {}).get("label", effect),
                    props={"segment_id": segment.id, "resource_id": "editorgpt:" + effect},
                    via=["plan"], note="این افکت روی کل قطعه اعمال می‌شود؛ در بخش افکت و ترنزیشنِ همین تب تغییرش دهید."))
        for transition in plan.transitions:
            if transition.duration_frames <= 0:
                continue
            index = next(i for i, s in enumerate(plan.segments) if s.id == transition.to_segment_id)
            tracks["graphics"].append(_element(
                f"transition:{transition.from_segment_id}:{transition.to_segment_id}", "transition",
                placed[index][0] / fps, (placed[index][0] + transition.duration_frames) / fps,
                {"crossfade": "محو", "directional": "کشویی", "zoom": "زوم"}.get(transition.type, transition.type),
                props={"type": transition.type, "frames": transition.duration_frames,
                       "from_segment_id": transition.from_segment_id, "to_segment_id": transition.to_segment_id,
                       "direction": transition.direction, "intensity": transition.intensity,
                       "zoom_mode": transition.zoom_mode, "zoom_scale": transition.zoom_scale}, via=["plan"],
                note="این ترنزیشن بین دو قطعه است؛ در بخش افکت و ترنزیشنِ همین تب تغییرش دهید."))
        duration = plan.output_duration
        for number, caption in enumerate(plan.captions):
            tracks["captions"].append(_element(
                f"caption:{number}", "caption", caption.start, caption.end, CAPTION_STYLE.get(caption.style, caption.style),
                text=caption.text, props={"style": caption.style, "position": caption.position,
                                          "highlight": caption.highlighted_word, "locked": caption.locked},
                via=["chat"], note="متن زیرنویس را با چت اصلاح کنید."))
        if plan.poster and plan.poster.show_in_video:
            tracks["titles"].append(_element("poster", "title", 0, duration, "هوک ثابت", text=plan.poster.text,
                                             props={"persistent": True}, via=["chat"]))
        if plan.cover:
            tracks["titles"].append(_element("cover", "title", plan.cover.start, plan.cover.end, "تیتر ابتدایی",
                                             text=plan.cover.text, via=["chat"]))
        for number, clip in enumerate(plan.broll):
            tracks["panel"].append(_element(f"broll:{number}", "picture", clip.at, clip.at + clip.duration, f"B-roll {number + 1}",
                                            source={"kind": "upload", "label": Path(clip.file).name, "file": Path(clip.file).name},
                                            props={"query": clip.query}, via=["chat"]))
        for number, sound in enumerate(plan.sfx):
            name = Path(sound.file).name
            length = _file_seconds(sound.file) if Path(sound.file).is_absolute() else _file_seconds(str(Path(job.dir) / sound.file))
            track = "voice" if name.startswith("narration") else "sfx"
            tracks[track].append(_element(
                f"{track}:{number}", "audio", sound.at, min(duration, sound.at + (length or 0.5)),
                "نریشن" if track == "voice" else name, source={"kind": "generated" if track == "voice" else "library", "label": name},
                props={"volume_db": sound.volume_db}, via=["chat"]))
        if plan.music:
            tracks["music"].append(_element("music", "music", 0, duration, Path(plan.music.file).stem.replace("_", " "),
                                            source={"kind": "library", "label": Path(plan.music.file).name},
                                            props={"volume_db": plan.music.volume_db, "ducked": len(plan.music.duck)}, via=["chat"]))
        notes = []
        canvas = {"width": plan.canvas.width, "height": plan.canvas.height, "fps": fps}

    return {
        "schema": SCHEMA, "engine": "motion", "style": None, "canvas": canvas,
        "duration": _r(duration), "content_duration": _r(duration), "notes": notes, "stale_edits": [], "edit_count": 0,
        # No render fingerprint is stored for this engine yet, so the player is not claimed to match.
        "basis": {"plan_version": None, "rendered_version": None, "workflow": job.render.status, "synced": None},
        "tracks": [{"id": key, "kind": MOTION_TRACKS[key][0], "label": MOTION_TRACKS[key][1],
                    "elements": sorted(items, key=lambda e: e["start"])} for key, items in tracks.items() if items],
    }
