"""Talking-head style 5: a style-pack reel.

Planning is the proven talking_2 cut (speech ranges, pieces of 1.6-3 s, face per shot). What is different is who draws:
the speaker is cropped, punched-in and graded by ffmpeg, every graphic (panels, captions, the hook, key-moment slams) is ONE
transparent HyperFrames page (engine/hyperframes/overlay_reel.py) laid over it, so a new look is a new StylePack
(creative/style_packs.py), never a new renderer.

Hard cuts only (the reference style): the speaker is either full-frame or a rounded card under the panel, and the page knows
which, shot by shot.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

from creative.style_packs import REFERENCE_AI_NEWS, StylePack

from . import talking_2 as base
from .talking_1 import H, W, music_bed

log = logging.getLogger(__name__)

CARD_Y = 888                          # the speaker card starts here (matches overlay_reel.SPLIT_Y)
CARD_H = H - CARD_Y
CARD_RADIUS = 58
LOUDNESS = -14.0
MUSIC_DB = -17.0
GRADES = {
    "warm": "eq=contrast=1.06:saturation=1.10:gamma=0.98,colorbalance=rs=.03:gs=0:bs=-.04:rm=.02:bm=-.02",
    "cool": "eq=contrast=1.06:saturation=1.05,colorbalance=rs=-.03:bs=.04",
    "neutral": "eq=contrast=1.03:saturation=1.0",
}

track_faces = base.track_faces
probe_video = base.probe_video
Shot = base.Shot
ReelPlan = base.ReelPlan


# ── planning ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def cold_open_choice(decisions: dict, sentences: list[dict], key_moments: list[dict], settings: dict) -> dict | None:
    """The teaser line shown before the video starts (the "first key moment"), switched on and off and re-chosen from the edit panel.

    Never the opening line itself unless the creator picked it: it would be heard twice back to back. Default: the strongest line that is
    NOT at the start (the director's pick when it is late enough, else the first key moment that is)."""
    if not settings.get("first_key_moment_enabled", True) or not sentences:
        return None
    manual = settings.get("first_key_moment_sentence")
    if manual is not None and 0 <= int(manual) < len(sentences):
        pick = int(manual)
    else:
        def late(i) -> bool:
            return i is not None and 0 <= int(i) < len(sentences) and int(i) >= 1 and float(sentences[int(i)]["start"]) >= MIN_TEASER_START
        director = (decisions.get("cold_open") or {}).get("i")
        pick = int(director) if late(director) else next((int(m["i"]) for m in key_moments if late(m.get("i"))), None)
    if pick is None:
        return None
    return {"i": pick, "text": str(sentences[pick]["text"])}


def plan_reel(transcript: dict, decisions: dict, faces: list, duration: float, pack: StylePack | None = None,
              beats: list[dict] | None = None, key_moments: list[dict] | None = None, creative_plan: dict | None = None,
              settings: dict | None = None) -> ReelPlan:
    """The talking_2 cut with a layout per shot (full / split) and the script the overlay page needs on plan.script."""
    pack = pack or REFERENCE_AI_NEWS
    sentences = transcript["sentences"]
    cold = cold_open_choice(decisions, sentences, key_moments or [], settings or {})
    plan = base.plan_reel(transcript, {**decisions, "broll": [], "chips": [], "cold_open": cold}, faces, duration, pictures={}, continuous_split=False)
    by_sentence = {int(b["sentence"]): b for b in (beats or []) if b.get("sentence") is not None}
    ratio = pack.rhythm.split_ratio
    # Which shots get a panel: the shots that sit inside a beat's sentence, spread so about `ratio` of the reel is split.
    candidates = []
    for shot in plan.shots:
        k = base._sentence_at(sentences, (shot.src_in + shot.src_out) / 2)
        shot.slot = k
        if ratio > 0 and k in by_sentence and shot.out_start >= plan.cold_open + 0.01:
            candidates.append(shot)
    chosen = candidates
    split_ids = {id(s) for s in chosen}
    # a key-moment slam owns the whole frame: no panel under it
    windows = []
    for m in key_moments or []:
        if m.get("i") is not None and 0 <= int(m["i"]) < len(sentences):
            windows.append((float(sentences[int(m["i"])]["start"]) - 0.1, float(sentences[int(m["i"])]["start"]) + 2.2))
    for shot in plan.shots:
        shot.split = id(shot) in split_ids and not any(shot.src_in < b and shot.src_out > a for a, b in windows)
        shot.close = (not shot.split) and (shot.out_start // 1 % 2 == 1)

    # A panel scene lives at most MAX_PANEL seconds; a long beat comes back as several panels with the speaker between them
    # (the reference never holds one image for long, and never leaves a long stretch without something new).
    held, gap, in_gap, last_slot = 0.0, 0.0, False, None
    min_gap = min(4.0, max(1.2, MAX_PANEL * (1 - ratio) / max(ratio, 0.1)))      # the less of the reel is panel, the longer the speaker between panels
    for shot in plan.shots:
        if not shot.split:
            held, gap, in_gap, last_slot = 0.0, 0.0, False, None
            continue
        if shot.slot != last_slot:                         # a new beat is a new panel
            held, gap, in_gap, last_slot = 0.0, 0.0, False, shot.slot
        if in_gap and gap < min_gap:
            shot.split = False
            gap += shot.length
            continue
        in_gap = False
        if held > 0 and held + shot.length > MAX_PANEL * 1.25:
            shot.split = False
            held, gap, in_gap = 0.0, shot.length, True
        else:
            held += shot.length
    # a panel shorter than MIN_PANEL has no time to play its motion: it grows into the next shots of the same sentence (else the
    # previous ones), never past MAX_PANEL, instead of being dropped
    shots = plan.shots
    i = 0
    while i < len(shots):
        if not shots[i].split:
            i += 1
            continue
        j = i
        while j + 1 < len(shots) and shots[j + 1].split:
            j += 1
        total = sum(s.length for s in shots[i:j + 1])
        while total < MIN_PANEL:
            nxt = shots[j + 1] if j + 1 < len(shots) else None
            prv = shots[i - 1] if i > 0 else None
            if nxt is not None and not nxt.split and nxt.out_start >= plan.cold_open and nxt.slot == shots[j].slot:
                nxt.split, j, total = True, j + 1, total + nxt.length
            elif prv is not None and not prv.split and prv.out_start >= plan.cold_open + 0.01 and prv.slot == shots[i].slot:
                prv.split, i, total = True, i - 1, total + prv.length
            else:
                break
        if total < MIN_PANEL:
            for s in shots[i:j + 1]:
                s.split = False
        for s in shots[i:j + 1]:
            s.close = (not s.split) and (s.out_start // 1 % 2 == 1)
        i = j + 1
    run = []
    for shot in plan.shots + [None]:
        if shot is not None and shot.split:
            run.append(shot)
            continue
        if run:
            xs = sorted(r.face[0] for r in run)
            ys = sorted(r.face[1] for r in run)
            for r in run:
                r.face = (xs[len(xs) // 2], ys[len(ys) // 2])
        run = []
    plan.script = _script(plan, transcript, decisions, by_sentence, key_moments or [], pack)
    plan.pack = pack
    plan.sentences = sentences
    plan.creative_plan = creative_plan
    return plan


def _word_times(plan: ReelPlan, words: list[dict]) -> list[dict]:
    """Transcript words on the output timeline. The cold-open line is spoken twice in the output (teaser, then in place):
    its words are timed once per occurrence, each against its own shot."""
    from brain.talking_reel import is_filler
    cold = plan.shots[0] if plan.cold_open > 0 else None
    main = plan.shots[1:] if cold else plan.shots
    out = []

    def place(shot: Shot, w: dict) -> None:
        a = shot.out_start + float(w["start"]) - shot.src_in
        b = shot.out_start + float(w["end"]) - shot.src_in
        end = shot.out_start + shot.length
        b = min(max(b, a + 0.12), end)
        if a < end:
            out.append({"w": base.persian_digits(str(w["w"])), "start": round(a, 3), "end": round(b, 3)})

    for w in words:
        if is_filler(w.get("w", "")):
            continue
        t0, t1 = float(w["start"]), float(w["end"])
        if cold and cold.src_in - 1e-3 <= t0 and t1 <= cold.src_out + 1e-3:
            place(cold, w)
        for shot in main:
            if shot.src_in - 1e-3 <= t0 and t1 <= shot.src_out + 1e-3:
                place(shot, w)
                break
    out.sort(key=lambda x: x["start"])
    return out


def _out_map(plan: ReelPlan):
    main = plan.shots[1:] if plan.cold_open > 0 else plan.shots

    def out_time(src: float) -> float | None:
        for s in main:
            if s.src_in - 1e-3 <= src <= s.src_out + 1e-3:
                return s.out_start + max(0.0, src - s.src_in)
        return None
    return out_time


def _script(plan: ReelPlan, transcript: dict, decisions: dict, by_sentence: dict, moments: list[dict], pack: StylePack) -> dict:
    out_time = _out_map(plan)
    words = _word_times(plan, transcript["words"])
    segments, cur = [], None
    for shot in plan.shots:
        layout = "split" if shot.split else "full"
        beat = by_sentence.get(shot.slot) if shot.split else None
        key = (layout, shot.slot if shot.split else None)
        end = shot.out_start + shot.length
        if cur and cur["key"] == key and abs(cur["end"] - shot.out_start) < 0.02:
            cur["end"] = end
        else:
            cur = {"key": key, "start": shot.out_start, "end": end, "layout": layout, "beat": beat}
            segments.append(cur)
    for s in segments:
        s.pop("key", None)
        if s.get("beat"):                                 # what is said while THIS panel is up: a long beat gets a different scene per panel
            said = " ".join(w["w"] for w in words if s["start"] - 0.05 <= w["start"] < s["end"])
            s["beat"] = {**s["beat"], "spoken": said, "part": sum(1 for t in segments[:segments.index(s)] if t.get("beat") and t["beat"].get("sentence") == s["beat"].get("sentence"))}
    sentences = transcript["sentences"]
    slams = []
    for m in moments:
        i = m.get("i")
        if i is None or not (0 <= int(i) < len(sentences)):
            continue
        a = out_time(float(sentences[int(i)]["start"]))
        if a is None:
            continue
        if plan.cold_open > 0:                                         # the teaser owns the opening seconds: a slam waits for it
            a = max(a, plan.cold_open + 0.25)
        if a + 1.0 > plan.duration:
            continue
        slams.append({"text": base.persian_digits(str(m.get("text") or "")), "start": round(a, 3), "end": round(min(a + 2.0, plan.duration), 3)})
    hook = None                                           # captions run from the first word, so there is no static title on top of them
    teaser = [0.0, round(plan.cold_open, 3)] if plan.cold_open > 0 else None
    return {"duration": round(plan.duration, 3), "segments": segments, "words": words, "hook": hook, "teaser": teaser, "moments": slams}


# ── rendering ────────────────────────────────────────────────────────────────────────────────────────────────────────

MIN_TEASER_START = 5.0                # a teaser must come from at least this far into the talk
MIN_GAP = 1.8                         # seconds of speaker between two panels of one long beat
MIN_PANEL = 2.2                       # a panel stays up at least this long
MAX_PANEL = 3.8                       # seconds one panel scene may stay up
EXTRA = 170                           # how far above the card the speaker's head may rise (px)
TALL_H = CARD_H + EXTRA
FACE_FRAC = (EXTRA + 40) / TALL_H     # where the face centre sits in the tall window: just under the card's top edge


TRANSITION = 0.3                      # seconds the card takes to open to full frame (or close to a card)
POP = 130                             # how far the head rises above the card in a split shot (px)
HEAD_UP = 0.17                        # head top above the face centre, as a fraction of the source height


def _placement(plan: ReelPlan, src_w: int, src_h: int) -> tuple[float, float, float, float, float]:
    """(scale, x0, y0, window height, drop) of the one picture every shot uses: a single scale and face position for the whole reel, so no
    shot jumps. `drop` is how far the same picture slides down inside a split shot, so the head ends POP px above the card."""
    xs, ys = sorted(s.face[0] for s in plan.shots), sorted(s.face[1] for s in plan.shots)
    cx, cy = xs[len(xs) // 2], ys[len(ys) // 2]
    h = float(src_h)
    w = h * (W / H)
    if w > src_w:
        w = float(src_w)
        h = w * (H / W)
    scale = W / w
    x0 = min(max(0.0, cx * src_w - w / 2), src_w - w)
    y0 = min(max(0.0, cy * src_h - 0.38 * h), src_h - h)
    head_top = (cy * src_h - HEAD_UP * src_h - y0) * scale
    drop = min(max(0.0, (CARD_Y - POP) - head_top), CARD_Y - EXTRA - 40)
    return scale, x0, y0, h, drop


def _crop(plan: ReelPlan, shot: Shot, src_w: int, src_h: int, pack: StylePack, split: bool) -> tuple[int, int, int, int]:
    """(x, y, w, h) of the source window. Full: the shared picture (a close shot punches in on the face, keeping it where it was).
    Split: the part of the same picture that sits from the head room above the card to the bottom of the frame (the head may rise over the panel)."""
    scale, x0, y0, h, drop = _placement(plan, src_w, src_h)
    w = W / scale
    if split:
        top = (CARD_Y - EXTRA - drop) / scale
        x, y, w2, h2 = x0, y0 + top, w, (H - (CARD_Y - EXTRA)) / scale
    elif shot.close:
        z = pack.rhythm.close_zoom
        w2, h2 = w / z, h / z
        fx, fy = (shot.face[0] * src_w - x0) / w, (shot.face[1] * src_h - y0) / h
        x = min(max(0.0, shot.face[0] * src_w - fx * w2), src_w - w2)
        y = min(max(0.0, shot.face[1] * src_h - fy * h2), src_h - h2)
    else:
        x, y, w2, h2 = x0, y0, w, h
    return int(x) // 2 * 2, int(y) // 2 * 2, int(w2) // 2 * 2, int(h2) // 2 * 2


def _slide(drop: float, enter: bool, leave: bool, d: float) -> str:
    """ffmpeg expression (in t) for how far down the picture sits: `drop` in a card, 0 in full frame, eased over TRANSITION at the cuts to full."""
    tr = TRANSITION
    a = "st(1,clip(t/%.3f,0,1));st(1,ld(1)*ld(1)*(3-2*ld(1)));" % tr if enter else "st(1,1);"
    b = "st(2,clip((t-%.3f)/%.3f,0,1));st(2,1-ld(2)*ld(2)*(3-2*ld(2)));" % (d - tr, tr) if leave else "st(2,1);"
    return a + b + "%.2f*ld(1)*ld(2)" % drop


def _round_mask(path: Path) -> Path:
    """The open card as a full-frame mask: white from CARD_Y down, rounded at the top corners."""
    import cv2
    import numpy as np
    mask = np.zeros((H, W), np.uint8)
    cv2.rectangle(mask, (0, CARD_Y + CARD_RADIUS), (W, H), 255, -1)
    cv2.rectangle(mask, (CARD_RADIUS, CARD_Y), (W - CARD_RADIUS, CARD_Y + CARD_RADIUS), 255, -1)
    cv2.circle(mask, (CARD_RADIUS, CARD_Y + CARD_RADIUS), CARD_RADIUS, 255, -1)
    cv2.circle(mask, (W - CARD_RADIUS, CARD_Y + CARD_RADIUS), CARD_RADIUS, 255, -1)
    cv2.imwrite(str(path), mask)
    return path


def _ramp(opening: bool, fps: int) -> str:
    """Filter source for the card's mask while it opens to full frame (opening) or closes back to a card: eased top edge and corner radius.
    Drawn at a quarter of the size (cheap) and scaled up."""
    q = 4
    span = TRANSITION - 1.0 / fps
    k = "ld(0)" if not opening else "(1-ld(0))"                    # opening: the top edge rises (fraction of the card still covered shrinks)
    expr = (f"st(0,clip(T/{span:.4f},0,1));st(0,ld(0)*ld(0)*(3-2*ld(0)));st(1,{k}*{CARD_Y / q});st(2,{k}*{CARD_RADIUS / q});"
            f"if(gte(Y,ld(1)),if(lt(Y,ld(1)+ld(2)),if(lt(X,ld(2)),lte(hypot(X-ld(2),Y-ld(1)-ld(2)),ld(2)),"
            f"if(gt(X,{W // q}-ld(2)),lte(hypot(X-{W // q}+ld(2),Y-ld(1)-ld(2)),ld(2)),1)),1),0)*255")
    return (f"color=c=white:s={W // q}x{H // q}:r={fps}:d={TRANSITION:.3f},format=gray,geq=lum='{expr}',"
            f"scale={W}:{H}:flags=bilinear,format=gray,setsar=1")


def _hex(color: str) -> str:
    return "0x" + color.lstrip("#")


def _mattes(video: Path, plan: ReelPlan, pack: StylePack, work_dir: Path, src_w: int, src_h: int, fps: int) -> dict[int, Path]:
    """One matte video per split shot (half resolution), or {} when segmentation is unavailable (the head then stays inside the card)."""
    from engine import person_matte
    if not person_matte.available():
        return {}
    jobs, index = [], []
    for i, shot in enumerate(plan.shots):
        if not shot.split:
            continue
        x, y, w, h = _crop(plan, shot, src_w, src_h, pack, True)
        jobs.append({"src": str(video), "start": shot.src_in, "end": shot.src_out, "crop": [x, y, w, h], "size": [W // 2, (TALL_H // 4) * 2],              # even sizes: the matte is an H.264 video
                     
                     "fps": fps, "out": str(work_dir / "mattes" / f"m{i}.mp4")})
        index.append(i)
    if not jobs:
        return {}
    try:
        outs = person_matte.matte(jobs)
    except Exception as exc:                                   # the reel is still good without the pop-out
        log.warning("person matte unavailable: %s", str(exc)[:200])
        return {}
    return dict(zip(index, outs))


def _graph(plan: ReelPlan, pack: StylePack, src_w: int, src_h: int, fps: int, mattes: dict[int, Path], first_matte_input: int) -> tuple[list[str], list[str]]:
    """(filter parts, extra -i arguments) for: bg + panel + speaker layer + head layer + text. Inputs 0 = video, 1 = card mask, then mattes."""
    grade = GRADES.get(pack.grade, GRADES["neutral"])
    parts, slayer, player, alabels = [], [], [], []
    matte_args: list[str] = []
    matte_input = {}
    for k, i in enumerate(sorted(mattes)):
        matte_input[i] = first_matte_input + k
        matte_args += ["-i", str(mattes[i])]
    for i, shot in enumerate(plan.shots):
        a, b = shot.src_in, shot.src_out
        d = b - a
        x, y, w, h = _crop(plan, shot, src_w, src_h, pack, shot.split)
        if shot.split:
            sx, sy, sw, sh = _crop(plan, shot, src_w, src_h, pack, False)
            enter = i > 0 and not plan.shots[i - 1].split and d > 3 * TRANSITION
            leave = i + 1 < len(plan.shots) and not plan.shots[i + 1].split and d > 3 * TRANSITION
            steady = d - TRANSITION * (int(enter) + int(leave))
            pieces = []
            if enter:
                parts.append(f"{_ramp(False, fps)}[ri{i}]")
                pieces.append(f"[ri{i}]")
            parts.append(f"[1:v]trim=duration={steady:.3f},setpts=PTS-STARTPTS,format=gray,fps={fps},setsar=1[rs{i}]")
            pieces.append(f"[rs{i}]")
            if leave:
                parts.append(f"{_ramp(True, fps)}[ro{i}]")
                pieces.append(f"[ro{i}]")
            parts.append(f"{''.join(pieces)}concat=n={len(pieces)}:v=1:a=0,format=gray[mk{i}]")
            drop = _placement(plan, src_w, src_h)[4]
            slide = _slide(drop, enter, leave, d)
            parts.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS,crop={sw}:{sh}:{sx}:{sy},scale={W}:{H}:flags=lanczos,{grade},format=yuv420p[pic{i}]")
            parts.append(f"color=c=black@0.0:s={W}x{H}:r={fps}:d={d:.3f},format=yuva420p[cv{i}]")
            parts.append(f"[cv{i}][pic{i}]overlay=0:'{slide}':eval=frame:format=auto,format=yuv420p[pd{i}]")
            parts.append(f"[pd{i}][mk{i}]alphamerge,format=yuva420p[s{i}]")
            parts.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS,crop={w}:{h}:{x}:{y},scale={W}:{TALL_H}:flags=lanczos,{grade},format=yuv420p[tb{i}]")
            if i in matte_input:
                parts.append(f"[{matte_input[i]}:v]format=gray,scale={W}:{TALL_H}:flags=bilinear,eq=contrast=1.35:brightness=-0.12,erosion,gblur=sigma=0.9,format=gray[mm{i}]")
                parts.append(f"[tb{i}][mm{i}]alphamerge[person{i}]")
                parts.append(f"color=c=black@0.0:s={W}x{H}:r={fps}:d={d:.3f},format=yuva420p[f{i}]")
                parts.append(f"[f{i}][person{i}]overlay=0:'{CARD_Y - EXTRA}-{drop:.2f}+({slide})':eval=frame:format=auto,format=yuva420p[p{i}]")
            else:
                parts.append(f"[tb{i}]nullsink")
                parts.append(f"color=c=black@0.0:s={W}x{H}:r={fps}:d={d:.3f},format=yuva420p[p{i}]")
        else:
            parts.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS,crop={w}:{h}:{x}:{y},scale={W}:{H}:flags=lanczos,{grade},format=yuva420p[s{i}]")
            parts.append(f"color=c=black@0.0:s={W}x{H}:r={fps}:d={d:.3f},format=yuva420p[p{i}]")
        n_frames = max(1, int(round(d * fps)))
        for lab in ("s", "p"):                              # every piece of both layers has exactly the same number of frames: no drift between them
            parts[:] = [(part[:part.rindex("[")] + f"[{lab}r{i}]") if part.endswith(f"[{lab}{i}]") and "color=c=black@0.0" not in part[:0] and part.rindex("[") > 0 and f"[{lab}{i}]" == part[part.rindex("["):] else part for part in parts]
            parts.append(f"[{lab}r{i}]tpad=stop_mode=clone:stop_duration=1,trim=end_frame={n_frames},setpts=N/{fps}/TB[{lab}{i}]")
        parts.append(f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS[a{i}]")
        slayer.append(f"[s{i}]")
        player.append(f"[p{i}]")
        alabels.append(f"[a{i}]")
    n = len(plan.shots)
    parts.append(f"{''.join(slayer)}concat=n={n}:v=1:a=0[L1]")
    parts.append(f"{''.join(player)}concat=n={n}:v=1:a=0[L2]")
    parts.append(f"{''.join(alabels)}concat=n={n}:v=0:a=1[ca]")
    return parts, matte_args


def render_composite(video: Path, plan: ReelPlan, panel: Optional[Path], text: Optional[Path], out: Path, *, work_dir: Path,
                     hook: Optional[Path] = None, music: Optional[Path] = None, pack: StylePack | None = None, on_progress=None) -> Path:
    """One ffmpeg pass: panel colour -> panel layer -> speaker (full frame or card) -> head over the panel -> text; cuts, grade, music, loudness."""
    pack = pack or plan.pack
    work_dir.mkdir(parents=True, exist_ok=True)
    probe = base.probe_video(video)
    src_w, src_h = int(probe[0]), int(probe[1])
    fps = int(round(base.eval_fps(base.probe_fps(video)) or 30))
    mask = _round_mask(work_dir / "card_mask.png")
    mattes = _mattes(video, plan, pack, work_dir, src_w, src_h, fps)
    inputs = ["-i", str(video), "-loop", "1", "-framerate", str(fps), "-i", str(mask)]
    parts, matte_args = _graph(plan, pack, src_w, src_h, fps, mattes, 2)
    inputs += matte_args
    nxt = 2 + len(mattes)
    parts.append(f"color=c={_hex(pack.palette.panel_bg)}:s={W}x{H}:r={fps}:d={plan.duration:.3f}[bg]")
    last = "bg"
    if panel and panel.is_file():
        inputs += ["-c:v", "libvpx-vp9", "-i", str(panel)]
        parts.append(f"[{nxt}:v]format=yuva420p,setpts=PTS-STARTPTS[pn]")
        parts.append(f"[{last}][pn]overlay=0:0:format=auto:eof_action=pass[x1]")
        last, nxt = "x1", nxt + 1
    parts.append(f"[{last}][L1]overlay=0:0:format=auto:shortest=0:eof_action=pass[x2]")
    parts.append("[x2][L2]overlay=0:0:format=auto:eof_action=pass[x3]")
    last = "x3"
    if text and text.is_file():
        inputs += ["-c:v", "libvpx-vp9", "-i", str(text)]
        parts.append(f"[{nxt}:v]format=yuva420p,setpts=PTS-STARTPTS[tx]")
        parts.append(f"[{last}][tx]overlay=0:0:format=auto:eof_action=pass[x4]")
        last, nxt = "x4", nxt + 1
    if hook and hook.is_file():
        inputs += ["-c:v", "libvpx-vp9", "-i", str(hook)]
        parts.append(f"[{nxt}:v]format=yuva420p,setpts=PTS-STARTPTS[hk]")
        parts.append(f"[{last}][hk]overlay=0:0:format=auto:eof_action=pass[x5]")
        last, nxt = "x5", nxt + 1
    parts.append(f"[{last}]fps={fps},format=yuv420p[vout]")
    loud = f"loudnorm=I={LOUDNESS}:TP=-1:LRA=8,aresample=48000[aout]"
    if music and music.is_file():
        inputs += ["-i", str(music_bed(music, plan.duration + 1.0, work_dir))]
        parts.append(f"[{nxt}:a]volume={MUSIC_DB}dB,atrim=0:{plan.duration:.3f}[bed]")
        parts.append("[ca]asplit=2[vox1][vox2]")
        parts.append("[bed][vox1]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=300[bedduck]")
        parts.append(f"[vox2][bedduck]amix=inputs=2:duration=first:normalize=0,{loud}")
    else:
        parts.append(f"[ca]{loud}")
    cmd = ["ffmpeg", "-hide_banner", "-y", *inputs, "-filter_complex", ";".join(parts), "-map", "[vout]", "-map", "[aout]",
           "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-level:v", "4.2", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
           "-t", f"{plan.duration:.3f}", "-movflags", "+faststart", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + proc.stderr[-1600:])
    return out


def render_layer(plan: ReelPlan, out: Path, *, work_dir: Path, part: str, pack: StylePack | None = None,
                 on_progress: Optional[Callable[[int], None]] = None, timeout: int = 5400) -> Optional[Path]:
    """A transparent HyperFrames layer: "panel" (under the speaker) or "text" (over it). None when the layer has nothing in it."""
    from engine.hyperframes import overlay_reel
    from engine.hyperframes.product_reel import _run_cli
    pack = pack or plan.pack
    if part == "panel" and not any(s["layout"] == "split" and s.get("beat") for s in plan.script["segments"]):
        return None
    project = work_dir / f"layer_{part}"
    if project.exists():
        shutil.rmtree(project)
    project.mkdir(parents=True)
    overlay_reel.build_project(project, pack, plan.script, part=part)
    _run_cli(project, out, timeout=timeout, on_progress=on_progress, fmt="webm")
    return out


def render_hook(plan: ReelPlan, work_dir: Path, pack: StylePack) -> Optional[Path]:
    """The opening teaser drawn by a real tscaps template (the words keep their spoken timing). None when the pack asks for the system's own
    word-by-word hook, or when tscaps is unavailable (then the captions page draws the teaser itself)."""
    teaser = plan.script.get("teaser")
    if pack.hook.mode != "tscaps" or not teaser or teaser[1] < 0.8:
        return None
    from engine import tscaps_overlay as ts
    words = [ts.Word(w["w"], float(w["start"]), float(w["end"])) for w in plan.script["words"] if float(w["start"]) < teaser[1]]
    if not words:
        return None
    cues = []
    for k in range(0, len(words), 3):                   # three words at a time: a page the template can set in the frame
        chunk = words[k:k + 3]
        end = words[k + 3].s - 0.02 if k + 3 < len(words) else min(teaser[1], plan.duration)
        cues.append(ts.Cue("hook", max(0.0, chunk[0].s - 0.05), max(end, chunk[-1].e + 0.1), chunk, y=0.44, scale=1.3))
    try:
        out = ts.render_overlay(cues, work_dir / "t5_hook.webm", width=W, height=H, fps=30, duration=plan.duration, work_dir=work_dir / "tscaps",
                                kinds={"hook": {**ts.ROLES["hook"], "template": pack.hook.template}})
    except ts.OverlayUnavailable as exc:
        log.warning("tscaps hook unavailable, using the built-in one: %s", str(exc)[:200])
        return None
    plan.script["teaser"] = [teaser[0], teaser[1], "hidden"]
    return out


def author_panels(plan: ReelPlan, work_dir: Path) -> int:
    """The Motion Designer writes one scene per panel (creative/motion.py, cached next to the job). Returns how many were authored."""
    from creative import motion as creative_motion
    from engine.hyperframes.schema import VisualBeat
    if not creative_motion.enabled():
        return 0
    segs = [s for s in plan.script["segments"] if s["layout"] == "split" and s.get("beat")]
    beats = []
    for n, seg in enumerate(segs):
        b = seg["beat"]
        sentence = int(b.get("sentence") if b.get("sentence") is not None else 0)
        bid = f"beat-{sentence}-{n}"
        b["bid"] = bid
        spoken = b.get("spoken") or (plan.sentences[sentence]["text"] if 0 <= sentence < len(plan.sentences) else "")
        beats.append(VisualBeat(id=bid, start=float(seg["start"]), end=float(seg["end"]), title=(str(b.get("title") or "") or "…")[:80],
                                items=[str(i)[:35] for i in (b.get("items") or [])][:4], layout="top_panel",
                                narrative_role=str(b.get("role") or "evidence"), why=str(b.get("visual") or ""), spoken=spoken))
    if not beats:
        return 0
    creative_motion.PANEL_MAX_Y = CARD_Y - EXTRA - 20          # below this the speaker's head rises into the panel
    for attempt in range(3):                              # a provider hiccup must not cost a scene: compose reuses what is cached and retries the rest
        creative_motion.compose(beats, creative_motion.plan_from_public(plan.creative_plan), plan.sentences, cache=work_dir / "authored_scenes_v2.json")
        if all(b.custom for b in beats):
            break
    done = 0
    for seg, beat in zip(segs, beats):
        if beat.custom:
            seg["beat"]["custom"] = beat.custom
            done += 1
        else:                                            # never show a weak or empty panel: the speaker keeps the whole frame
            seg["layout"], seg["beat"] = "full", None
            for shot in plan.shots:
                if seg["start"] - 1e-3 <= shot.out_start < seg["end"] - 1e-3:
                    shot.split = False
    return done


def render(video: Path, plan: ReelPlan, out: Path, *, work_dir: Path, music: Optional[Path] = None,
           on_progress: Optional[Callable[[int], None]] = None, **kwargs) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    pack = kwargs.get("pack") or plan.pack
    report = (lambda lo, hi: (lambda p: on_progress(lo + int(p * (hi - lo) / 100)))) if on_progress else (lambda lo, hi: None)
    if getattr(plan, "creative_plan", None) is not None and author_panels(plan, work_dir):
        bg = next((s["beat"]["custom"].get("bg") for s in plan.script["segments"] if s.get("beat") and s["beat"].get("custom")), None)
        if bg:                                          # the speaker card's rounded corners show this colour: it must be the panel's
            pack = pack.model_copy(update={"palette": pack.palette.model_copy(update={"panel_bg": bg})})
    panel = render_layer(plan, work_dir / "t5_panel.webm", work_dir=work_dir, part="panel", pack=pack, on_progress=report(5, 45))
    hook = render_hook(plan, work_dir, pack)
    text = render_layer(plan, work_dir / "t5_text.webm", work_dir=work_dir, part="text", pack=pack, on_progress=report(45, 75))
    try:
        fx = choose_effects(plan, pack, work_dir)
    except Exception as exc:
        log.warning("effects not chosen: %s", str(exc)[:300])
        fx = []
    if fx:
        try:
            apply_effects(video, plan, panel, text, hook, fx, out, work_dir=work_dir, music=music, pack=pack, on_progress=report(75, 97))
        except Exception as exc:                          # a failed effect must never cost the reel
            log.warning("effects skipped: %s", str(exc)[:300])
            fx = []
    if not fx:
        render_composite(video, plan, panel, text, out, work_dir=work_dir, hook=hook, music=music, pack=pack)
    if on_progress:
        on_progress(99)
    return out


def choose_effects(plan: ReelPlan, pack: StylePack, work_dir: Path) -> list[dict]:
    """Face effects for the stretches where the speaker has the whole frame (cached next to the job so a re-render keeps the same choice)."""
    import json
    from engine import face_effects
    cache = work_dir / "effects_plan.json"
    if getattr(plan, "effects", None) is not None:
        return plan.effects
    if pack.effects_per_minute <= 0 or not face_effects.available():
        return []
    if cache.is_file():
        try:
            return face_effects.clean_plan(json.loads(cache.read_text()))
        except Exception:
            pass
    from creative import effects_director
    protect = [(float(m["start"]) - 0.2, float(m["end"]) + 0.2) for m in plan.script.get("moments") or []]
    chosen = effects_director.choose(plan, per_minute=pack.effects_per_minute, protect=protect)
    cache.write_text(json.dumps(chosen, ensure_ascii=False))
    return chosen


def apply_effects(video: Path, plan: ReelPlan, panel, text, hook, fx: list[dict], out: Path, *, work_dir: Path, music, pack: StylePack, on_progress=None) -> None:
    """Base reel (speaker, panels, music) -> effects on it -> captions, hook and slams on top, so no effect ever hides the words."""
    from engine import face_effects
    base_out, fx_out = work_dir / "t5_base.mp4", work_dir / "t5_fx.mp4"
    render_composite(video, plan, panel, None, base_out, work_dir=work_dir, music=music, pack=pack)
    face_effects.apply(base_out, fx_out, fx, work=work_dir / "fx", on_progress=(lambda p, stage: on_progress(int(p * 100))) if on_progress else None)
    cmd = ["ffmpeg", "-hide_banner", "-y", "-i", str(fx_out)]
    last, n = "0:v", 1
    parts = []
    for layer in (text, hook):
        if layer and layer.is_file():
            cmd += ["-c:v", "libvpx-vp9", "-i", str(layer)]
            parts.append(f"[{n}:v]format=yuva420p,setpts=PTS-STARTPTS[l{n}]")
            parts.append(f"[{last}][l{n}]overlay=0:0:format=auto:eof_action=pass[o{n}]")
            last, n = f"o{n}", n + 1
    parts.append(f"[{last}]format=yuv420p[vout]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[vout]", "-map", "0:a", "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-level:v", "4.2", "-c:a", "copy",
            "-movflags", "+faststart", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + proc.stderr[-800:])
