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


def _graph(plan: ReelPlan, pack: StylePack, src_w: int, src_h: int, fps: int, mattes: dict[int, Path], first_matte_input: int,
           video: Path | None = None, rng: range | None = None, with_audio: bool = True) -> tuple[list[str], list[str], int]:
    """(filter parts, extra -i arguments, how many of those are pinned-shot inputs) for: bg + panel + speaker layer + head layer + text.
    Inputs 0 = video, 1 = card mask, then mattes, then one short window of the video per pinned shot.

    A shot that plays before footage the reel shows later (the cold open) reads its own window of the file: on the shared input, the processed
    frames of every shot in between would wait in concat's queues, gigabytes of them."""
    grade = GRADES.get(pack.grade, GRADES["neutral"])
    parts, slayer, player, alabels = [], [], [], []
    matte_args: list[str] = []
    matte_input = {}
    rng = rng if rng is not None else range(len(plan.shots))
    mattes = {i: m for i, m in mattes.items() if i in rng}
    for k, i in enumerate(sorted(mattes)):
        matte_input[i] = first_matte_input + k
        matte_args += ["-i", str(mattes[i])]
    pinned: dict[int, tuple[int, float]] = {}
    if video is not None:
        for i in rng:
            shot = plan.shots[i]
            if any(plan.shots[j].src_in < shot.src_in - 0.5 for j in range(i + 1, rng.stop)):
                begin = max(0.0, shot.src_in - 1.0)
                pinned[i] = (first_matte_input + len(mattes) + len(pinned), begin)
                matte_args += ["-ss", f"{begin:.3f}", "-t", f"{shot.src_out - begin + 1.0:.3f}", "-i", str(video)]
    for i in rng:
        shot = plan.shots[i]
        a, b = shot.src_in, shot.src_out
        d = b - a
        vin, off = (f"[{pinned[i][0]}:v]", pinned[i][1]) if i in pinned else ("[0:v]", 0.0)
        ain = f"[{pinned[i][0]}:a]" if i in pinned else "[0:a]"
        ta, tb_ = a - off, b - off
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
            parts.append(f"{vin}trim=start={ta:.3f}:end={tb_:.3f},setpts=PTS-STARTPTS,crop={sw}:{sh}:{sx}:{sy},scale={W}:{H}:flags=lanczos,{grade},format=yuv420p[pic{i}]")
            parts.append(f"color=c=black@0.0:s={W}x{H}:r={fps}:d={d:.3f},format=yuva420p[cv{i}]")
            parts.append(f"[cv{i}][pic{i}]overlay=0:'{slide}':eval=frame:format=auto,format=yuv420p[pd{i}]")
            parts.append(f"[pd{i}][mk{i}]alphamerge,format=yuva420p[s{i}]")
            parts.append(f"{vin}trim=start={ta:.3f}:end={tb_:.3f},setpts=PTS-STARTPTS,crop={w}:{h}:{x}:{y},scale={W}:{TALL_H}:flags=lanczos,{grade},format=yuv420p[tb{i}]")
            if i in matte_input:
                parts.append(f"[{matte_input[i]}:v]format=gray,scale={W}:{TALL_H}:flags=bilinear,eq=contrast=1.35:brightness=-0.12,erosion,gblur=sigma=0.9,format=gray[mm{i}]")
                parts.append(f"[tb{i}][mm{i}]alphamerge[person{i}]")
                parts.append(f"color=c=black@0.0:s={W}x{H}:r={fps}:d={d:.3f},format=yuva420p[f{i}]")
                parts.append(f"[f{i}][person{i}]overlay=0:'{CARD_Y - EXTRA}-{drop:.2f}+({slide})':eval=frame:format=auto,format=yuva420p[p{i}]")
            else:
                parts.append(f"[tb{i}]nullsink")
                parts.append(f"color=c=black@0.0:s={W}x{H}:r={fps}:d={d:.3f},format=yuva420p[p{i}]")
        else:
            parts.append(f"{vin}trim=start={ta:.3f}:end={tb_:.3f},setpts=PTS-STARTPTS,crop={w}:{h}:{x}:{y},scale={W}:{H}:flags=lanczos,{grade},format=yuva420p[s{i}]")
            parts.append(f"color=c=black@0.0:s={W}x{H}:r={fps}:d={d:.3f},format=yuva420p[p{i}]")
        n_frames = max(1, int(round(d * fps)))
        for lab in ("s", "p"):                              # every piece of both layers has exactly the same number of frames: no drift between them
            parts[:] = [(part[:part.rindex("[")] + f"[{lab}r{i}]") if part.endswith(f"[{lab}{i}]") and "color=c=black@0.0" not in part[:0] and part.rindex("[") > 0 and f"[{lab}{i}]" == part[part.rindex("["):] else part for part in parts]
            # setsar=1: footage with a non-square pixel aspect (1984:1989 from some phones) gives each piece a slightly different SAR and concat refuses to join them
            parts.append(f"[{lab}r{i}]tpad=stop_mode=clone:stop_duration=1,trim=end_frame={n_frames},setpts=N/{fps}/TB,setsar=1[{lab}{i}]")
        if with_audio:
            parts.append(f"{ain}atrim=start={ta:.3f}:end={tb_:.3f},asetpts=PTS-STARTPTS[a{i}]")
            alabels.append(f"[a{i}]")
        slayer.append(f"[s{i}]")
        player.append(f"[p{i}]")
    n = len(slayer)
    parts.append(f"{''.join(slayer)}concat=n={n}:v=1:a=0[L1]")
    parts.append(f"{''.join(player)}concat=n={n}:v=1:a=0[L2]")
    if with_audio:
        parts.append(f"{''.join(alabels)}concat=n={n}:v=0:a=1[ca]")
    return parts, matte_args, len(pinned)


CHUNK_SECONDS = 8.0


def _chunks(plan: ReelPlan) -> list[range]:
    """Consecutive shots grouped to about CHUNK_SECONDS of the reel each."""
    out, start, length = [], 0, 0.0
    for i, shot in enumerate(plan.shots):
        length += shot.length
        if length >= CHUNK_SECONDS:
            out.append(range(start, i + 1))
            start, length = i + 1, 0.0
    if start < len(plan.shots):
        out.append(range(start, len(plan.shots)))
    return out


def render_composite(video: Path, plan: ReelPlan, panel: Optional[Path], text: Optional[Path], out: Path, *, work_dir: Path,
                     hook: Optional[Path] = None, music: Optional[Path] = None, pack: StylePack | None = None, on_progress=None) -> Path:
    """Panel colour -> panel layer -> speaker (full frame or card) -> head over the panel -> text, then cuts, grade, music, loudness.

    The picture is made a few seconds at a time and the sound in one pass: in one graph, every piece of the reel was generated far ahead of its turn and
    waited in concat's queues (gigabytes for a minute of reel, an out-of-memory kill on a 4 GB worker)."""
    pack = pack or plan.pack
    work_dir.mkdir(parents=True, exist_ok=True)
    probe = base.probe_video(video)
    src_w, src_h = int(probe[0]), int(probe[1])
    fps = int(round(base.eval_fps(base.probe_fps(video)) or 30))
    mask = _round_mask(work_dir / "card_mask.png")
    mattes = _mattes(video, plan, pack, work_dir, src_w, src_h, fps)
    chunks = _chunks(plan)
    segments = []
    for number, rng in enumerate(chunks):
        t0 = plan.shots[rng.start].out_start
        length = sum(plan.shots[i].length for i in rng)
        inputs = ["-i", str(video), "-loop", "1", "-framerate", str(fps), "-i", str(mask)]
        parts, extra, pinned_inputs = _graph(plan, pack, src_w, src_h, fps, mattes, 2, video, rng=rng, with_audio=False)
        inputs += extra
        nxt = 2 + len([i for i in mattes if i in rng]) + pinned_inputs
        parts.append(f"color=c={_hex(pack.palette.panel_bg)}:s={W}x{H}:r={fps}:d={length:.3f}[bg]")
        last = "bg"
        window = ["-ss", f"{t0:.3f}", "-t", f"{length + 0.5:.3f}", "-c:v", "libvpx-vp9", "-i"]
        for label, layer, name in (("pn", panel, "panel"), ("tx", text, "text"), ("hk", hook, "hook")):
            if name == "text":                                  # the speaker layers go between the panel and the text
                parts.append(f"[{last}][L1]overlay=0:0:format=auto:shortest=0:eof_action=pass[xa]")
                parts.append("[xa][L2]overlay=0:0:format=auto:eof_action=pass[xb]")
                last = "xb"
            if layer and layer.is_file():
                inputs += [*window, str(layer)]
                parts.append(f"[{nxt}:v]format=yuva420p,setpts=PTS-STARTPTS[{label}]")
                parts.append(f"[{last}][{label}]overlay=0:0:format=auto:eof_action=pass[o{label}]")
                last, nxt = f"o{label}", nxt + 1
        if last == "bg":                                         # no layers at all: the speaker layers still have to be laid over the colour
            parts.append("[bg][L1]overlay=0:0:format=auto:shortest=0:eof_action=pass[xa]")
            parts.append("[xa][L2]overlay=0:0:format=auto:eof_action=pass[xb]")
            last = "xb"
        elif "[xb]" not in ";".join(parts):                      # a panel but neither text nor hook
            parts.append(f"[{last}][L1]overlay=0:0:format=auto:shortest=0:eof_action=pass[xa]")
            parts.append("[xa][L2]overlay=0:0:format=auto:eof_action=pass[xb]")
            last = "xb"
        parts.append(f"[{last}]fps={fps},format=yuv420p[vout]")
        segment = work_dir / f"t5_chunk_{number:03d}.mp4"
        cmd = ["ffmpeg", "-hide_banner", "-y", *inputs, "-filter_complex", ";".join(parts), "-map", "[vout]", "-an",
               "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-level:v", "4.2", "-pix_fmt", "yuv420p", "-r", str(fps),
               "-t", f"{length:.3f}", str(segment)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError("ffmpeg failed: " + proc.stderr[-1600:])
        segments.append(segment)
        if on_progress:
            on_progress(int(80 * (number + 1) / len(chunks)))

    # the sound, once, over the whole reel
    aparts, ainputs = [], ["-i", str(video)]
    labels = []
    for i, shot in enumerate(plan.shots):
        aparts.append(f"[0:a]atrim=start={shot.src_in:.3f}:end={shot.src_out:.3f},asetpts=PTS-STARTPTS[a{i}]")
        labels.append(f"[a{i}]")
    aparts.append(f"{''.join(labels)}concat=n={len(labels)}:v=0:a=1[ca]")
    loud = f"loudnorm=I={LOUDNESS}:TP=-1:LRA=8,aresample=48000[aout]"
    if music and music.is_file():
        ainputs += ["-i", str(music_bed(music, plan.duration + 1.0, work_dir))]
        aparts.append(f"[1:a]volume={MUSIC_DB}dB,atrim=0:{plan.duration:.3f}[bed]")
        aparts.append("[ca]asplit=2[vox1][vox2]")
        aparts.append("[bed][vox1]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=300[bedduck]")
        aparts.append(f"[vox2][bedduck]amix=inputs=2:duration=first:normalize=0,{loud}")
    else:
        aparts.append(f"[ca]{loud}")
    sound = work_dir / "t5_sound.m4a"
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-y", *ainputs, "-filter_complex", ";".join(aparts), "-map", "[aout]", "-c:a", "aac", "-b:a", "192k",
                           "-t", f"{plan.duration:.3f}", str(sound)], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + proc.stderr[-1600:])
    listing = work_dir / "t5_chunks.txt"
    listing.write_text("".join("file '" + str(path).replace("'", "'\\''") + "'\n" for path in segments))
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-i", str(sound), "-map", "0:v", "-map", "1:a",
                           "-c", "copy", "-t", f"{plan.duration:.3f}", "-movflags", "+faststart", str(out)], capture_output=True, text=True)
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


def panel_mode() -> str:
    """TALKING5_PANELS: "best" (default: BOTH a library component and a Motion Designer scene are made for every beat, an art director scores each in a still and the better one is used) |
    "library" (the curated panel library first, the Motion Designer only for a beat nothing in it fits) | "authored" (the old behaviour:
    the Motion Designer writes every panel) | "mixed" (library for lists/numbers/comparisons, the designer for headlines and concepts)."""
    import os
    value = os.environ.get("TALKING5_PANELS", "best").strip().lower()
    return value if value in {"best", "library", "authored", "mixed"} else "best"


def author_panels(plan: ReelPlan, work_dir: Path) -> int:
    """Fills every panel: first from the curated panel library (creative/panel_library.py: finished, Persian-checked HyperFrames components, never the same one twice in a reel),
    and only where nothing in it fits, by the Motion Designer (creative/motion.py, cached next to the job). Returns how many panels are ready; `plan.script["panels_info"]`
    says, per panel, where it came from. A panel nobody could fill is dropped (the speaker keeps the whole frame)."""
    from creative import motion as creative_motion
    from creative import panel_library
    from engine.hyperframes.schema import VisualBeat
    segs = [s for s in plan.script["segments"] if s["layout"] == "split" and s.get("beat")]
    if not segs:
        return 0
    mode = panel_mode()
    # The same walk as overlay_reel.build_project (panel index, components used so far), so the page makes exactly the pick made here.
    used: set[str] = set()
    from_library: dict[int, str] = {}
    if mode != "authored":
        for n, seg in enumerate(segs):
            if mode == "mixed" and panel_library.role_of(seg["beat"]) in {"headline", "concept"}:
                continue
            pick = panel_library.choose(seg["beat"], used, seed=str(n), seconds=float(seg["end"]) - float(seg["start"]))
            if pick:
                used.add(pick[0])
                from_library[n] = pick[0]
    to_author = [n for n in range(len(segs)) if mode == "best" or n not in from_library]
    beats: dict[int, VisualBeat] = {}
    for n in to_author:
        b = segs[n]["beat"]
        sentence = int(b.get("sentence") if b.get("sentence") is not None else 0)
        bid = f"beat-{sentence}-{n}"
        b["bid"] = bid
        spoken = b.get("spoken") or (plan.sentences[sentence]["text"] if 0 <= sentence < len(plan.sentences) else "")
        beats[n] = VisualBeat(id=bid, start=float(segs[n]["start"]), end=float(segs[n]["end"]), title=(str(b.get("title") or "") or "…")[:80],
                              items=[str(i)[:35] for i in (b.get("items") or [])][:4], layout="top_panel",
                              narrative_role=str(b.get("role") or "evidence"), why=str(b.get("visual") or ""), spoken=spoken)
    attempted = bool(beats) and creative_motion.enabled() and getattr(plan, "creative_plan", None) is not None
    if attempted:
        creative_motion.PANEL_MAX_Y = CARD_Y - EXTRA - 20          # below this the speaker's head rises into the panel
        ordered = [beats[n] for n in to_author]
        for attempt in range(3):                              # a provider hiccup must not cost a scene: compose reuses what is cached and retries the rest
            creative_motion.compose(ordered, creative_motion.plan_from_public(plan.creative_plan), plan.sentences, cache=work_dir / "authored_scenes_v2.json")
            if all(b.custom for b in ordered):
                break
    info, done = [], 0
    for n, seg in enumerate(segs):
        title = str((seg["beat"] or {}).get("title") or "")
        if n in from_library and n in beats and beats[n].custom:                # best mode: both candidates exist, pick_panels decides
            seg["beat"]["force_component"] = from_library[n]
            seg["beat"]["custom"] = beats[n].custom
            info.append({"n": n + 1, "title": title, "source": "both", "component": from_library[n]})
            done += 1
        elif n in from_library:
            seg["beat"]["force_component"] = from_library[n]                  # the page builds exactly this one (and a later swap names another)
            info.append({"n": n + 1, "title": title, "source": "library", "component": from_library[n]})
            done += 1
        elif n in beats and beats[n].custom:
            seg["beat"]["custom"] = beats[n].custom
            info.append({"n": n + 1, "title": title, "source": "authored"})
            done += 1
        elif not attempted:                              # no designer available (no creative plan): the page's own audited template fills the panel, as before
            info.append({"n": n + 1, "title": title, "source": "template"})
            done += 1
        else:                                            # never show a weak or empty panel: the speaker keeps the whole frame
            info.append({"n": n + 1, "title": title, "source": "dropped"})
            seg["layout"], seg["beat"] = "full", None
            for shot in plan.shots:
                if seg["start"] - 1e-3 <= shot.out_start < seg["end"] - 1e-3:
                    shot.split = False
    plan.script["panels_info"] = info
    return done


def snapshot_panels(plan: ReelPlan, pack: StylePack, work_dir: Path, out_dir: Path, limit: int = 8) -> list[dict]:
    """One still of each designed panel (60 % into its stretch, where its text and motion are in place), composited on the panel colour, so the person sees the
    designs before the render. Bounded; returns [{n, t, title, file}] and never raises (a missing preview is not a failed reel)."""
    import os
    import subprocess
    segs = [s for s in plan.script["segments"] if s["layout"] == "split" and s.get("beat")]
    if not segs:
        return []
    try:
        from PIL import Image
        from engine.hyperframes import overlay_reel
        from engine.hyperframes.cli import cli_command
        step = max(1, -(-len(segs) // limit))
        picked = segs[::step][:limit]
        times = [round(min(float(s["start"]) + (float(s["end"]) - float(s["start"])) * 0.6, plan.duration - 0.1), 2) for s in picked]
        project, raw = work_dir / "layer_panel_preview", work_dir / ".panel_snapshots"
        for folder in (project, raw):
            shutil.rmtree(folder, ignore_errors=True)
            folder.mkdir(parents=True)
        overlay_reel.build_project(project, pack, plan.script, part="panel")
        done = subprocess.run([*cli_command(), "snapshot", ".", "--at", ",".join(f"{t:g}" for t in times), "--no-end", "--keep", "--describe", "false", "-o", str(raw)],
                              cwd=project, capture_output=True, text=True, timeout=150, env={**os.environ, "NO_COLOR": "1"})
        out_dir.mkdir(parents=True, exist_ok=True)
        items = []
        for n, (seg, t) in enumerate(zip(picked, times), 1):
            source = raw / f"at-{t:g}s.png"
            if not source.is_file():
                continue
            with Image.open(source) as layer:                   # the panel layer is transparent: show it on the panel colour it will have under the speaker
                base = Image.new("RGB", layer.size, pack.palette.panel_bg)
                base.paste(layer.convert("RGBA"), (0, 0), layer.convert("RGBA"))
                base = base.crop((0, 0, base.width, min(base.height, int(base.height * CARD_Y / H))))      # the panel's own area (the rest is the speaker's)
                base.thumbnail((540, 960))
                target = out_dir / f"panel{n}.jpg"
                base.save(target, quality=82)
            items.append({"n": n, "t": t, "title": str((seg.get("beat") or {}).get("title") or "")[:60], "file": target, "seg": segs.index(seg) + 1})
        if not items:
            log.warning("panel previews not made: %s", (done.stderr or done.stdout or "")[-200:])
        return items
    except Exception as exc:
        log.warning("panel previews failed: %s", str(exc)[:200])
        return []


def _panel_segs(plan: ReelPlan) -> list[dict]:
    return [s for s in plan.script["segments"] if s["layout"] == "split" and s.get("beat")]


def pick_panels(plan: ReelPlan, pack: StylePack, work_dir: Path, note: Callable[..., None]) -> None:
    """For a beat that has BOTH a library component and a Motion Designer scene, an art director (creative/design_critic.py) scores a still of each and the better one is used
    (a tie goes to the designed scene: it is the one written for these words). Beats with only one candidate are untouched. Never raises."""
    from creative import design_critic
    segs = _panel_segs(plan)
    both = [i for i, s in enumerate(segs) if s["beat"].get("custom") and s["beat"].get("force_component")]
    if not both or not design_critic.enabled():
        return

    def show(use: str) -> list[dict]:
        for i in both:
            beat = segs[i]["beat"]
            custom, comp = beat.get("custom") or beat.pop("_alt_custom", None), beat.get("force_component") or beat.pop("_alt_comp", None)
            for key in ("custom", "force_component", "_alt_custom", "_alt_comp"):
                beat.pop(key, None)
            if use == "library":
                beat["force_component"], beat["_alt_custom"] = comp, custom
            else:
                beat["custom"], beat["_alt_comp"] = custom, comp
        return snapshot_panels(plan, pack, work_dir, work_dir / f"panel_frames_{use}")

    try:
        looks = {}
        for use in ("library", "authored"):
            frames = show(use)
            stills = {f["seg"]: f["file"] for f in frames if f["seg"] - 1 in both}
            looks[use] = design_critic.critique(stills, {i + 1: str(segs[i]["beat"].get("title") or "") for i in both}, work_dir / f"critic_{use}", style_note=pack.summary)
        chosen = {}
        for i in both:
            lib, auth = looks["library"].get(i + 1), looks["authored"].get(i + 1)
            chosen[i] = "authored" if (auth and (not lib or auth.score >= lib.score)) or not (lib or auth) else "library"
        report = []
        for i in both:
            beat = segs[i]["beat"]
            custom, comp = beat.get("custom") or beat.pop("_alt_custom", None), beat.get("force_component") or beat.pop("_alt_comp", None)
            for key in ("custom", "force_component", "_alt_custom", "_alt_comp"):
                beat.pop(key, None)
            if chosen[i] == "authored":
                beat["custom"] = custom
            else:
                beat["force_component"] = comp
            lib, auth = looks["library"].get(i + 1), looks["authored"].get(i + 1)
            report.append(f"{i + 1}. {str(beat.get('title') or '')[:30]} — کتابخانه {lib.score if lib else '?'} · طراح موشن {auth.score if auth else '?'} ← {'طراح موشن' if chosen[i] == 'authored' else 'کتابخانه (' + str(comp) + ')'}")
            for row in plan.script.get("panels_info") or []:
                if row["n"] == i + 1:
                    row["source"] = chosen[i]
        note("طراح ارشد برای هر پنل بین المان کتابخانه و صحنهٔ طراح موشن بهترین را انتخاب کرد", stage="art director", done=True, detail="\n".join(report))
    except Exception as exc:
        log.warning("panel tournament skipped: %s", str(exc)[:200])
        for i in both:                                      # whatever state the variants left: authored scene wins, the library is the fallback
            beat = segs[i]["beat"]
            custom = beat.get("custom") or beat.pop("_alt_custom", None)
            for key in ("custom", "force_component", "_alt_custom", "_alt_comp"):
                beat.pop(key, None)
            if custom:
                beat["custom"] = custom


def refine_panels(plan: ReelPlan, pack: StylePack, work_dir: Path, frames: list[dict], note: Callable[..., None]) -> list[dict]:
    """The art-director pass (creative/design_critic.py) on the final panel stills. A weak LIBRARY panel is swapped for another component that fits the beat and lasts as long;
    a weak AUTHORED panel is written again by the Motion Designer from the critic's fixes; either is kept only if the same eye scores it higher. Returns the (possibly new) frames."""
    from creative import design_critic, panel_library
    segs = _panel_segs(plan)
    drafts = {}
    for i, s in enumerate(segs, 1):
        if s["beat"].get("custom"):
            drafts[i] = {"custom": s["beat"]["custom"]}
        elif s["beat"].get("force_component"):
            drafts[i] = {"lib": s["beat"]["force_component"]}
    if not frames or not drafts:
        return frames
    state = {"frames": frames, "tried": {n: {d["lib"]} if "lib" in d else set() for n, d in drafts.items()}}

    def stills():
        return {f["seg"]: f["file"] for f in state["frames"]}

    def author(n, feedback):
        beat = segs[n - 1]["beat"]
        if "custom" in drafts[n]:
            from creative import motion as creative_motion
            from engine.hyperframes.schema import VisualBeat
            sentence = int(beat.get("sentence") if beat.get("sentence") is not None else 0)
            fresh = VisualBeat(id=str(beat.get("bid") or f"beat-{sentence}-{n - 1}"), start=float(segs[n - 1]["start"]), end=float(segs[n - 1]["end"]),
                               title=(str(beat.get("title") or "") or "…")[:80], items=[str(x)[:35] for x in (beat.get("items") or [])][:4], layout="top_panel",
                               narrative_role=str(beat.get("role") or "evidence"), why=str(beat.get("visual") or ""), spoken=str(beat.get("spoken") or ""))
            creative_motion.PANEL_MAX_Y = CARD_Y - EXTRA - 20
            creative_motion.compose([fresh], creative_motion.plan_from_public(plan.creative_plan), plan.sentences, cache=work_dir / "authored_scenes_v2.json", feedback={fresh.id: feedback})
            if not fresh.custom:
                raise ValueError("the designer returned nothing")
            return {"custom": fresh.custom}
        seconds = float(segs[n - 1]["end"]) - float(segs[n - 1]["start"])
        taken = {d["lib"] for d in drafts.values() if "lib" in d} | state["tried"][n]
        options = panel_library.alternatives(beat, taken, seconds)
        if not options:
            raise ValueError("no other component fits")
        state["tried"][n].add(options[0])
        return {"lib": options[0]}

    def apply_all():
        for n, draft in drafts.items():
            beat = segs[n - 1]["beat"]
            for key in ("custom", "force_component"):
                beat.pop(key, None)
            if "custom" in draft:
                beat["custom"] = draft["custom"]
            else:
                beat["force_component"] = draft["lib"]

    def rebuild():
        apply_all()
        state["frames"] = snapshot_panels(plan, pack, work_dir, work_dir / "panel_frames") or state["frames"]
        return True

    def restore(before):
        drafts.clear(); drafts.update(before)

    verdict = design_critic.refine(drafts=drafts, headlines={i + 1: str(s["beat"].get("title") or "") for i, s in enumerate(segs)}, protected={i + 1 for i in range(len(segs)) if (i + 1) not in drafts},
                                   stills=stills, author=author, rebuild=rebuild, restore=restore, work=work_dir / "critic", brief=str(getattr(plan, "title", "") or ""),
                                   style_note=pack.summary, note=lambda text: note(text, stage="art director", done=True))
    apply_all()
    if verdict["before"]:
        note("نظر طراح ارشد دربارهٔ پنل‌ها آماده شد", stage="art director", done=True,
             detail="امتیاز هر پنل (از ۱۰): " + "، ".join(f"{n}:{v}" for n, v in sorted(verdict["before"].items())))
    return state["frames"]


def render(video: Path, plan: ReelPlan, out: Path, *, work_dir: Path, music: Optional[Path] = None,
           on_progress: Optional[Callable[[int], None]] = None, **kwargs) -> Path:
    """Server side: everything that asks a model (the panels, the effects) and the tscaps hook. The browser layers, the person matte, the effects and the
    composition are `compose`, which runs on a RunPod worker when the cloud profile admits it and here otherwise."""
    work_dir.mkdir(parents=True, exist_ok=True)
    pack = kwargs.get("pack") or plan.pack
    note = kwargs.get("note") or (lambda *a, **k: None)         # the chat's step log (app/talking_reel.note); never required
    total_panels = sum(1 for s in plan.script["segments"] if s["layout"] == "split" and s.get("beat"))
    if total_panels:
        note("دارم برای هر پنل از کتابخانهٔ المان‌های آمادهٔ موشن انتخاب می‌کنم و فقط جایی که چیزی نمی‌خورد، طراح موشن صحنه می‌نویسد", stage="designing panels")
    authored = author_panels(plan, work_dir)
    if authored:
        bg = next((s["beat"]["custom"].get("bg") for s in plan.script["segments"] if s.get("beat") and s["beat"].get("custom")), None)
        if bg:                                          # the speaker card's rounded corners show this colour: it must be the panel's
            pack = pack.model_copy(update={"palette": pack.palette.model_copy(update={"panel_bg": bg})})
        info = plan.script.get("panels_info") or []
        lib = sum(1 for r in info if r["source"] == "library")
        made = sum(1 for r in info if r["source"] == "authored")
        label = {"library": "کتابخانهٔ المان‌ها", "authored": "طراح موشن", "both": "هر دو (انتخاب با طراح ارشد)", "template": "قالب پایهٔ سبک", "dropped": "ساخته نشد"}
        note(f"{authored} پنل آماده شد" + (f" از {total_panels}" if total_panels != authored else "") + f" · {lib} از کتابخانهٔ المان‌ها، {made} با طراح موشن",
             stage="designing panels", done=True,
             detail="\n".join(f"{r['n']}. {r['title']} — {label[r['source']]}" + (f" ({r['component']})" if r.get("component") else "") for r in info))
        pick_panels(plan, pack, work_dir, note)
        frames = snapshot_panels(plan, pack, work_dir, work_dir / "panel_frames")
        try:
            from creative import design_critic
            if frames and design_critic.enabled():
                frames = refine_panels(plan, pack, work_dir, frames, note)
        except Exception as exc:
            log.warning("panel design critic skipped: %s", str(exc)[:200])
        if frames:
            note(f"فریم {len(frames)} پنل آماده شد؛ پیش از رندر می‌توانید طراحی‌ها را ببینید", stage="panel previews", done=True, frames=frames)
    elif total_panels:
        note("پنل‌های موشن ساخته نشد؛ گوینده تمام‌قاب می‌ماند", stage="designing panels", done=True)
    hook = render_hook(plan, work_dir, pack)
    if plan.script.get("teaser"):
        note("هوک ابتدایی با قالب tscaps ساخته شد" if hook else "هوک ابتدایی با قالب داخلی کپشن‌ها کشیده می‌شود", stage="hook", done=True)
    try:
        fx = choose_effects(plan, pack, work_dir)
    except Exception as exc:
        log.warning("effects not chosen: %s", str(exc)[:300])
        fx = []
    note(f"{len(fx)} جلوهٔ چهره انتخاب شد" if fx else "جلوهٔ چهره‌ای انتخاب نشد", stage="effects", done=True,
         detail="\n".join(f"{e.get('kind') or e.get('effect') or e.get('type') or '?'} · {float(e.get('start', 0)):.1f}s" for e in fx[:8]) if fx else "")
    from app.render_cloud.hooks import talking5 as cloud_talking5
    if cloud_talking5(video, plan, out, work_dir=work_dir, music=music, pack=pack, fx=fx, hook=hook, on_progress=on_progress):
        return out
    return compose(video, plan, out, work_dir=work_dir, music=music, pack=pack, fx=fx, hook=hook, on_progress=on_progress)


def compose(video: Path, plan: ReelPlan, out: Path, *, work_dir: Path, music: Optional[Path], pack: StylePack, fx: list[dict],
            hook: Optional[Path], on_progress: Optional[Callable[[int], None]] = None) -> Path:
    """The panel and text layers (HyperFrames pages), then the speaker, the person matte, the face effects, the music and the loudness in one pass."""
    work_dir.mkdir(parents=True, exist_ok=True)
    report = (lambda lo, hi: (lambda p: on_progress(lo + int(p * (hi - lo) / 100)))) if on_progress else (lambda lo, hi: None)
    panel = render_layer(plan, work_dir / "t5_panel.webm", work_dir=work_dir, part="panel", pack=pack, on_progress=report(5, 45))
    text = render_layer(plan, work_dir / "t5_text.webm", work_dir=work_dir, part="text", pack=pack, on_progress=report(45, 75))
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
