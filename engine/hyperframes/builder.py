"""Generate deterministic HyperFrames projects from approved visual beats."""
from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path

from .schema import VisualBeat
from .catalog import recommend
from engine.motion_recipes import select_recipe

ROOT = Path(__file__).resolve().parents[2]
RAY = ROOT / "presets" / "fonts" / "RAY-EXTRABOLD.TTF"


VISUAL_TYPES = {"concept", "stat", "comparison", "steps", "ui_showcase", "media_collage",
                "chat", "map_route", "spec_callout", "kinetic_type", "before_after"}


def _visual_type(title: str, items: list[str], requested: str = "") -> str:
    if requested in VISUAL_TYPES and requested != "concept":
        return requested
    if len(items) >= 2:
        return "steps"
    if re.search(r"[۰-۹0-9٪%]", title):
        return "stat"
    if any(token in title for token in ("مقایسه", "در برابر", "یا ", "قبل", "بعد")):
        return "comparison"
    return "concept"


def _out_time(plan, source_time: float) -> float | None:
    """Map a source transcript timestamp to the edited output timeline."""
    matches = [shot for shot in plan.shots if float(shot.src_in) <= source_time <= float(shot.src_out)]
    if not matches:
        return None
    shot = matches[-1]  # prefer the main edit over an earlier cold-open duplicate
    return float(shot.out_start) + source_time - float(shot.src_in)


def build_visual_beats(plan, decisions: dict, transcript: dict | None = None) -> list[VisualBeat]:
    """Turn the approved storyboard into short, varied output-time worlds.

    Story beats deliberately do not inherit sentence duration: Persian speech
    transcripts often contain one enormous sentence, which used to produce one
    enormous card.  Every catalog item is scored for every beat; selected
    references are unique until the suitable pool is exhausted.
    """
    if getattr(plan, 'continuous_split', False):
        return _continuous_beats(plan, decisions, transcript or {})
    chips = {int(item["i"]): list(item.get("items") or []) for item in decisions.get("chips") or []}
    storyboard = list(decisions.get("storyboard") or [])
    if not storyboard:
        storyboard = [{**item, "title": item.get("label") or item.get("visual") or "نکته مهم"}
                      for item in decisions.get("broll") or []]
    duration = float(getattr(plan, "duration", 0) or 0)
    if not storyboard or duration < 1:
        return []
    count = min(5, len(storyboard))
    # Keep the ending/payoff when a model returns too many beats.  Taking the
    # first five used to silently discard the conclusion and overrepresent the
    # hook.
    if len(storyboard) > count:
        # First cover distinct spoken sentences.  Fill remaining slots across
        # the unused ideas, always preserving the payoff at the end.
        chosen: list[int] = []
        seen_sentences: set[int] = set()
        for index, item in enumerate(storyboard):
            sentence = int(item.get("i", 0))
            if sentence not in seen_sentences:
                chosen.append(index)
                seen_sentences.add(sentence)
        for index in [len(storyboard) - 1] + [round(i * (len(storyboard) - 1) / (count - 1)) for i in range(count)]:
            if index not in chosen:
                chosen.append(index)
            if len(chosen) >= count:
                break
        storyboard = [storyboard[i] for i in sorted(chosen[:count])]
    else:
        storyboard = storyboard[:count]
    sentences = list((transcript or {}).get("sentences") or [])
    per_sentence: dict[int, list[int]] = {}
    for n, item in enumerate(storyboard):
        per_sentence.setdefault(int(item.get("i", 0)), []).append(n)
    used_refs: set[str] = set()
    used_recipes: dict[str, int] = {}
    fallback_types = ["kinetic_type", "concept", "comparison", "media_collage", "ui_showcase", "stat", "chat", "before_after"]
    fallback_motions = ["slam", "assemble", "wipe", "collage", "orbit", "count_up", "type_on", "reveal"]
    beats: list[VisualBeat] = []
    for n, item in enumerate(storyboard):
        sentence = int(item["i"])
        siblings = per_sentence.get(sentence, [n])
        rank = siblings.index(n)
        start = None
        if 0 <= sentence < len(sentences):
            source = sentences[sentence]
            a, b = float(source.get("start") or 0), float(source.get("end") or a)
            source_anchor = a + (b - a) * ((rank + 1) / (len(siblings) + 1))
            start = _out_time(plan, source_anchor)
        if start is None:
            start = 3.0 + n * max(4.0, (duration - 4.0) / max(1, count))
        scene_duration = 2.15
        start = max(1.2, min(duration - scene_duration - .35, start - scene_duration * .42))
        end = min(duration - .35, start + scene_duration)
        title = " ".join(str(item.get("title") or item.get("label") or "").split())[:80]
        if not title:
            title = " ".join(str(item.get("visual") or "").split()[:5]) or "نکته مهم"
        broll_item = next((value for value in decisions.get("broll") or [] if int(value.get("i", -1)) == sentence), {})
        raw_items = list(item.get("items") or []) or chips.get(sentence, []) or list(broll_item.get("items") or [])
        values = [" ".join(str(value).split())[:35] for value in raw_items if str(value).strip()]
        visual_type = _visual_type(title, values, str(item.get("visual_type") or ""))
        if visual_type == "stat" and not re.search(r"[۰-۹0-9٪%]", title + " " + " ".join(values)):
            visual_type = "concept"
        if visual_type == "before_after" and (" یا " in title or set(values) & {"محصول فیزیکی", "محصول دیجیتال"}):
            visual_type = "comparison"
        if beats and visual_type == beats[-1].visual_type:
            visual_type = fallback_types[n % len(fallback_types)]
        recipe = select_recipe(
            role=str(item.get("narrative_role") or "evidence"), title=title,
            items=values, used=used_recipes, talking=True,
        )
        used_recipes[recipe.id] = used_recipes.get(recipe.id, 0) + 1
        # A storyboard can explicitly request a semantic type, but a vague
        # "concept" now resolves through the audited recipe registry instead
        # of repeatedly falling back to the same generic world.
        if visual_type == "concept":
            visual_type = recipe.renderer
        motion_style = str(item.get("motion_style") or recipe.motion or fallback_motions[n % len(fallback_motions)])
        if beats and motion_style == beats[-1].motion_style:
            motion_style = fallback_motions[n % len(fallback_motions)]
        # Catalog search informs the choreography vocabulary, but a reference
        # is recorded only when its actual registry code is installed/wired.
        refs: list[str] = []
        beats.append(VisualBeat(
            id=f"beat-{sentence}-{n}", start=start, end=end,
            anchor_word=title.split()[0], visual_type=visual_type,
            title=title, items=values, accent=("ink", "teal")[n % 2],
            layout="top_panel",
            registry_refs=refs,
            narrative_role=str(item.get("narrative_role") or "evidence"),
            motion_style=motion_style,
            recipe_id=recipe.id,
            why=str(item.get("why") or ""),
        ))
    # Output edits may repeat a source range (cold open) or collapse adjacent
    # anchors.  Enforce one readable visual at a time after source-to-output
    # mapping so motion cards can never stack or flash over each other.
    beats.sort(key=lambda beat: beat.start)
    previous_end = .4
    for beat in beats:
        length = beat.end - beat.start
        beat.start = max(beat.start, previous_end + .70)
        beat.end = min(duration - .35, beat.start + length)
        if beat.end - beat.start < 1.45:
            beat.start = max(previous_end + .35, beat.end - 1.45)
        previous_end = beat.end
    return [beat for beat in beats if beat.end - beat.start >= 1.2]


def _continuous_beats(plan, decisions: dict, transcript: dict) -> list[VisualBeat]:
    """Cover the kept speech with contiguous, transcript-grounded 4–5-sentence groups.

    Sentence indices remain source references; timing is mapped through the
    actual cuts, rather than spreading a handful of decorative flashes.
    """
    sentences = transcript.get('sentences') or []
    dropped = set(decisions.get('drop') or [])
    kept = [i for i, s in enumerate(sentences) if i not in dropped and
            any(float(shot.src_in) < float(s['end']) and float(shot.src_out) > float(s['start']) for shot in plan.shots)]
    groups = [kept[i:i+5] for i in range(0, len(kept), 5)]
    if len(groups) > 1 and len(groups[-1]) == 1:
        groups[-1].insert(0, groups[-2].pop())
    board = decisions.get('storyboard') or decisions.get('broll') or []
    result = []
    for n, indices in enumerate(groups):
        evidence = ' '.join(str(sentences[i].get('text') or '') for i in indices)
        idea = next((b for b in board if int(b.get('i', -1)) in indices), {})
        title = ' '.join(str(idea.get('title') or idea.get('label') or evidence).split()[:9])[:80]
        if not title:
            continue
        start = 0.0 if not result else result[-1].end
        next_index = groups[n+1][0] if n+1 < len(groups) else None
        if next_index is None:
            end = float(plan.duration)
        else:
            boundary = float(sentences[next_index]['start'])
            # A source pause may have been removed: take the first kept shot
            # that reaches the next sentence, then map its actual boundary.
            shot = next((s for s in plan.shots if float(s.src_out) > boundary and
                         float(s.out_start) >= float(getattr(plan, 'cold_open', 0))), None)
            end = float(shot.out_start) + max(0, boundary-float(shot.src_in)) if shot else float(plan.duration)
        if end-start < .65:
            continue
        result.append(VisualBeat(id=f'beat-{indices[0]}-group-{n}', start=start, end=end,
            title=title, items=[str(x)[:35] for x in idea.get('items', [])][:4],
            visual_type=_visual_type(title, idea.get('items') or [], str(idea.get('visual_type') or '')),
            layout='top_panel', narrative_role=str(idea.get('narrative_role') or 'explanation'),
            why=str(idea.get('visual') or evidence), spoken=evidence, sentence_indices=indices,
            motion_style=str(idea.get('motion_style') or 'assemble')))
    return result


def _beat_markup(beat: VisualBeat) -> str:
    title = html.escape(beat.title)
    if beat.registry_refs and beat.registry_refs[0] == "caption-kinetic-slam":
        body = (f'<div class="registry-stage"><div data-composition-id="caption-kinetic-slam" '
                f'data-composition-src="compositions/components/caption-kinetic-slam.html" data-start="{beat.start:.3f}" '
                f'data-duration="{beat.end - beat.start:.3f}" data-width="1080" data-height="1920" data-track-index="0"></div></div>')
    elif beat.registry_refs and beat.registry_refs[0] == "comparison-split":
        body = (f'<div class="registry-stage"><div data-composition-id="comparison-split" '
                f'data-composition-src="compositions/components/comparison-split.html" data-start="{beat.start:.3f}" '
                f'data-duration="{beat.end - beat.start:.3f}" data-width="1080" data-height="1920" data-track-index="0"></div></div>')
    elif beat.registry_refs and beat.registry_refs[0] == "paper-collage-reveal":
        values = beat.items or ["گوشی", "دوره آموزشی", "پادکست", "نرم‌افزار"]
        slot = '<div class="registry-collage-content">' + ''.join(
            f'<span>{html.escape(value)}</span>' for value in values[:4]
        ) + '</div>'
        body = (f'<template data-slot="paper-collage-reveal-content">{slot}</template>'
                f'<div class="registry-stage"><div data-composition-id="paper-collage-reveal" '
                f'data-composition-src="compositions/components/paper-collage-reveal.html" data-start="{beat.start:.3f}" '
                f'data-duration="{beat.end - beat.start:.3f}" data-width="1080" data-height="1920" data-track-index="0"></div></div>')
    elif beat.registry_refs and beat.registry_refs[0] == "hw-pipeline":
        body = (f'<div class="registry-stage"><div data-composition-id="hw-pipeline" '
                f'data-composition-src="compositions/hw-pipeline.html" data-start="{beat.start:.3f}" data-duration="{beat.end - beat.start:.3f}" '
                'data-width="1080" data-height="1920" data-track-index="0"></div></div>')
    elif beat.visual_type == "steps" and beat.items:
        body = "".join(
            f'<div class="step"><b>{i + 1:02d}</b><span>{html.escape(value)}</span></div>'
            for i, value in enumerate(beat.items)
        )
    elif beat.visual_type == "comparison":
        labels = beat.items[:2] or [value.strip() for value in re.split(r"(?:در برابر| یا )", beat.title) if value.strip()][:2]
        labels = (labels + ["خدمت", "محصول"])[:2]
        body = (f'<div class="compare"><div><strong>×۱</strong><span>{html.escape(labels[0])}</span></div>'
                f'<i><b>→</b></i><div><strong>×∞</strong><span>{html.escape(labels[1])}</span></div></div>')
    elif beat.visual_type == "stat":
        match = re.search(r"[۰-۹0-9]+(?:[٫.][۰-۹0-9]+)?(?:\s*[٪%×x])?", beat.title)
        value = html.escape(match.group(0) if match else beat.title.split()[0])
        body = f'<div class="stat">{value}</div><div class="meter"><i></i></div>'
    elif beat.visual_type == "ui_showcase":
        body = '<div class="ui-stage"><i></i><i></i><i></i><span></span></div>'
    elif beat.visual_type == "media_collage":
        values = beat.items or ["گوشی", "دوره آموزشی", "پادکست", "نرم‌افزار"]
        glyphs = ["▣", "▶", "◉", "⌁"]
        body = '<div class="collage">' + ''.join(
            f'<div><b>{glyphs[n % 4]}</b><span>{html.escape(value)}</span></div>' for n, value in enumerate(values[:4])
        ) + '</div>'
    elif beat.visual_type == "chat":
        values = beat.items or ["سؤال دقیق", "پاسخ روشن"]
        body = '<div class="chat-stack">' + ''.join(
            f'<span class="bubble b{n % 2}">{html.escape(value)}</span>' for n, value in enumerate(values[:3])
        ) + '</div>'
    elif beat.visual_type == "map_route":
        body = '<div class="route"><svg viewBox="0 0 800 260"><path d="M70 190 C220 30 410 245 720 65"/><circle cx="70" cy="190" r="18"/><circle cx="720" cy="65" r="18"/></svg></div>'
    elif beat.visual_type == "spec_callout":
        values = beat.items or ["Software", "as a", "Service"]
        body = '<div class="saas-mark"><b>S</b><i></i><div>' + ''.join(
            f'<span>{html.escape(value)}</span>' for value in values[:3]
        ) + '</div></div>'
    elif beat.visual_type == "kinetic_type":
        body = f'<div class="kinetic" dir="rtl">{title}</div>'
    elif beat.visual_type == "before_after":
        values = [re.sub(r"^(?:قبل|بعد)\s*[:：-]?\s*", "", value).strip() for value in beat.items[:2]]
        values = (values + ["خودت خدمت می‌دهی", "نرم‌افزار می‌فروشد"])[:2]
        body = f'<div class="before-after"><span><small>وابسته به زمان</small>{html.escape(values[0])}</span><i></i><span><small>مقیاس‌پذیر</small>{html.escape(values[1])}</span></div>'
    else:
        body = '<div class="concept"><div><i></i><small>×۱</small></div><div><i></i><i></i><i></i><i></i><small>×۴</small></div><div class="many"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><small>×۱۶</small></div></div>'
    return (
        f'<section id="{beat.id}" data-motion="{html.escape(beat.motion_style)}" class="visual-beat {beat.visual_type} {beat.accent} {beat.layout} {"registry-beat" if beat.registry_refs else ""} clip" '
        f'data-start="{beat.start:.3f}" data-duration="{beat.end - beat.start:.3f}" data-track-index="2">'
        f'<div class="beat-inner"><div class="ghost">{html.escape(beat.anchor_word)}</div><div class="eyebrow">{html.escape(beat.narrative_role)}</div><h2 dir="rtl">{title}</h2>{body}</div></section>'
    )


def _timeline_script(beats: list[VisualBeat]) -> str:
    lines = ['const tl = gsap.timeline({ paused: true });']
    for beat in beats:
        duration = beat.end - beat.start
        selector = f"#{beat.id} .beat-inner"
        entrances = {
            "slam": ('{opacity:0,scale:1.34,rotation:2}', '"back.out(1.45)"'),
            "wipe": ('{opacity:0,x:520,clipPath:"inset(0 0 0 100%)"}', '"power4.out"'),
            "assemble": ('{opacity:0,y:180,rotation:-3}', '"expo.out"'),
            "orbit": ('{opacity:0,scale:.55,rotation:-14}', '"power3.out"'),
            "type_on": ('{opacity:0,filter:"blur(24px)"}', '"power2.out"'),
            "count_up": ('{opacity:0,y:-120,scale:.8}', '"back.out(1.7)"'),
            "collage": ('{opacity:0,x:-260,rotation:5}', '"power3.out"'),
        }
        origin, ease = entrances.get(beat.motion_style, ('{opacity:0,y:90,scale:.94}', '"power3.out"'))
        lines.append(f'tl.fromTo("{selector}", {origin}, {{opacity:1,x:0,y:0,scale:1,rotation:0,clipPath:"inset(0 0 0 0)",filter:"blur(0px)",duration:.52,ease:{ease},immediateRender:false}}, {beat.start:.3f});')
        lines.append(
            f'tl.to("{selector}", {{opacity:0,duration:.22,ease:"power1.in"}}, '
            f'{max(beat.start + .4, beat.end - .22):.3f});'
        )
        if beat.visual_type == "stat":
            lines.append(
                f'tl.fromTo("#{beat.id} .meter i", {{scaleX:0}}, '
                f'{{scaleX:1,duration:{min(1.0, duration * .45):.3f},ease:"power2.out"}}, {beat.start + .18:.3f});'
            )
        elif beat.visual_type in {"steps", "chat", "spec_callout"}:
            child = ".step" if beat.visual_type == "steps" else (".bubble" if beat.visual_type == "chat" else ".specs span")
            lines.append(
                f'tl.fromTo("#{beat.id} {child}", {{opacity:0,y:28}}, '
                f'{{opacity:1,y:0,duration:.28,stagger:.09,ease:"power2.out"}}, {beat.start + .16:.3f});'
            )
        elif beat.visual_type in {"ui_showcase", "media_collage"}:
            child = ".ui-stage i" if beat.visual_type == "ui_showcase" else ".collage div"
            lines.append(
                f'tl.fromTo("#{beat.id} {child}", {{opacity:0}}, '
                f'{{opacity:1,duration:.32,stagger:.08,ease:"power1.out"}}, {beat.start + .14:.3f});'
            )
        elif beat.visual_type == "map_route":
            lines.append(
                f'tl.fromTo("#{beat.id} .route path", {{strokeDashoffset:420}}, '
                f'{{strokeDashoffset:0,duration:{min(1.2, duration * .55):.3f},ease:"power1.inOut"}}, {beat.start + .15:.3f});'
            )
        elif beat.visual_type == "kinetic_type":
            lines.append(
                f'tl.fromTo("#{beat.id} .kinetic", {{scale:.72,rotation:-2}}, '
                f'{{scale:1,rotation:0,duration:.38,ease:"back.out(1.7)"}}, {beat.start + .12:.3f});'
            )
        elif beat.visual_type == "before_after":
            lines.append(
                f'tl.fromTo("#{beat.id} .before-after i", {{scaleY:0}}, '
                f'{{scaleY:1,duration:.4,ease:"power3.out"}}, {beat.start + .15:.3f});'
            )
    lines.extend(['window.__timelines = window.__timelines || {};', 'window.__timelines["main"] = tl;', 'tl.seek(0);'])
    return "\n".join(lines)


def build_project(project_dir: Path, base_video: Path, beats: list[VisualBeat], *, duration: float,
                  enable_registry: bool = True, motion_only: bool = False, allow_full_frame: bool = False) -> Path:
    """Write a self-contained 1080x1920 HyperFrames composition."""
    if not allow_full_frame and any(b.layout == "full_frame" for b in beats):
        raise ValueError("Full-screen talking graphics require explicit permission")
    project_dir.mkdir(parents=True, exist_ok=True)
    assets = project_dir / "assets"
    assets.mkdir(exist_ok=True)
    video = assets / "base.mp4"
    if video.exists() or video.is_symlink():
        video.unlink()
    try:
        video.symlink_to(base_video.resolve())
    except OSError:
        shutil.copy2(base_video, video)
    shutil.copy2(RAY, assets / "ray-extrabold.ttf")
    # Local, integrity-checked GSAP: fail here, before any frame is encoded, if it is unavailable.
    from .assets import ensure_gsap
    shutil.copy2(ensure_gsap(), assets / "gsap.min.js")
    (project_dir / "hyperframes.json").write_text(json.dumps({
        "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
        "media": {"autoProxy": True},
    }, indent=2))
    if enable_registry:
        from .registry_runtime import wire_registry
        wire_registry(project_dir, [b for b in beats if b.layout != 'top_panel'])
    visual_library = []
    for beat in beats:
        value = beat.model_dump()
        visual_library.append(value)
    metadata = {
        "id": "ai-render-talking-2-panel" if motion_only else "ai-render-talking-2", "name": "AI Render Talking 2",
        "visual_library": visual_library, "duration": duration,
    }
    (project_dir / "meta.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
    cards = "\n".join(_beat_markup(beat) for beat in beats)
    backdrops = ""
    sfx_markup = ""
    panel_ids = ','.join('#'+b.id for b in beats if b.layout == 'top_panel')
    panel_css = (panel_ids + '{position:absolute!important;left:0!important;right:0!important;top:0!important;'
                 'bottom:auto!important;width:1080px!important;height:888px!important;'
                 'border-radius:0!important;overflow:hidden!important;}') if panel_ids else ''
    document = f'''<!doctype html>
<html lang="fa"><head><meta charset="UTF-8"><meta name="viewport" content="width=1080,height=1920">
<script src="./assets/gsap.min.js"></script>
<style>
{panel_css}
@font-face{{font-family:Ray;src:url('./assets/ray-extrabold.ttf')}}
*{{box-sizing:border-box}}html,body{{margin:0;width:1080px;height:1920px;overflow:hidden;background:#080b0c}}
#root{{position:relative;width:100%;height:100%;overflow:hidden;font-family:Ray,sans-serif}}
.base{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
.visual-beat{{--bg:#f3f0e8;--fg:#151a1b;position:absolute;left:42px;right:42px;top:72px;height:720px;padding:62px 58px;border-radius:42px;overflow:hidden;background:var(--bg);color:var(--fg);box-shadow:0 28px 80px #0007;direction:rtl}}
.visual-beat.full_frame{{inset:0;height:1920px;border-radius:0;display:grid;align-items:center}}
.visual-beat.full_frame .beat-inner{{padding:240px 86px}}.visual-beat.full_frame h2{{font-size:108px;max-width:920px}}
.beat-inner{{position:absolute;inset:0;padding:62px 58px;opacity:0}}
.visual-beat:after{{content:"";position:absolute;inset:0;border:2px solid color-mix(in srgb,var(--fg) 12%,transparent);border-radius:42px;pointer-events:none}}
.ghost{{position:absolute;left:-20px;top:8px;font-size:190px;opacity:.045;white-space:nowrap;direction:rtl}}.eyebrow{{font-size:22px;color:color-mix(in srgb,var(--fg) 55%,transparent);margin-bottom:25px;letter-spacing:0}}h2{{font-size:66px;line-height:1.28;margin:0;max-width:870px;letter-spacing:0}}
.teal{{--accent:#15977f;--bg:#f1efe7;--fg:#14221f}}.amber,.coral,.blue,.ink{{--accent:#d4ff42;--bg:#111513;--fg:#f4f1e8}}.stat{{font-size:150px;color:var(--accent);margin-top:58px;line-height:1}}
.meter{{height:18px;background:#d8d4ca;border-radius:12px;margin-top:34px;overflow:hidden;direction:ltr}}.meter i{{display:block;width:78%;height:100%;background:var(--accent);transform-origin:left}}
.step{{display:flex;align-items:center;gap:24px;margin-top:27px;font-size:40px}}.step b{{display:grid;place-items:center;width:72px;height:72px;border-radius:22px;background:var(--accent);color:white;font-size:28px}}.step span{{border-bottom:2px solid #151a1b20;padding:10px 0;flex:1}}
.compare{{display:grid;grid-template-columns:1fr 120px 1fr;align-items:center;gap:18px;margin-top:70px;text-align:center}}.compare>div{{height:220px;border:3px solid currentColor;border-radius:34px;display:grid;place-items:center;padding:20px}}.compare strong{{display:block;font:900 80px/1 Ray;color:var(--accent)}}.compare span{{font-size:31px}}.compare i{{font-style:normal;color:var(--accent);font-size:74px}}.compare i b{{font-weight:900}}
.concept{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:30px;align-items:end;height:300px;margin-top:38px;direction:ltr}}.concept>div{{display:flex;flex-wrap:wrap;align-content:flex-end;justify-content:center;gap:10px;padding:24px;border-bottom:5px solid var(--accent);min-height:130px}}.concept>div:nth-child(2){{min-height:205px}}.concept>div:nth-child(3){{min-height:280px}}.concept i{{display:block;width:45px;height:45px;border-radius:12px;background:var(--accent)}}.concept small{{width:100%;font:900 32px Ray;color:var(--fg);text-align:center}}
.ui-stage{{position:relative;height:360px;margin-top:28px;perspective:900px}}.ui-stage i{{position:absolute;width:250px;height:300px;border-radius:26px;background:#171c1d;border:4px solid #fff;box-shadow:0 24px 45px #0005}}.ui-stage i:nth-child(1){{right:70px;transform:rotate(7deg)}}.ui-stage i:nth-child(2){{right:320px;top:22px;transform:scale(1.08)}}.ui-stage i:nth-child(3){{right:570px;transform:rotate(-7deg)}}.ui-stage span{{position:absolute;right:365px;top:75px;width:160px;height:16px;background:var(--accent);box-shadow:0 45px #ffffff30,0 90px #ffffff30}}
.collage{{display:grid;grid-template-columns:1fr 1fr;gap:18px;height:350px;margin-top:28px;direction:rtl}}.collage div{{display:grid;grid-template-columns:74px 1fr;align-items:center;gap:15px;padding:18px 22px;border-radius:24px;background:color-mix(in srgb,var(--fg) 8%,transparent);border:2px solid color-mix(in srgb,var(--fg) 22%,transparent)}}.collage b{{display:grid;place-items:center;width:64px;height:64px;border-radius:18px;background:var(--accent);color:var(--bg);font-size:34px}}.collage span{{font-size:30px}}
.chat-stack{{display:flex;flex-direction:column;gap:18px;margin-top:40px}}.bubble{{max-width:72%;padding:20px 28px;border-radius:28px;font-size:34px}}.bubble.b0{{align-self:flex-start;background:#e1ddd3}}.bubble.b1{{align-self:flex-end;background:var(--accent);color:#fff}}
.route{{height:300px;margin-top:25px}}.route svg{{width:100%;height:100%;overflow:visible}}.route path{{fill:none;stroke:var(--accent);stroke-width:14;stroke-linecap:round;stroke-dasharray:22 22}}.route circle{{fill:#f3f0e8;stroke:var(--accent);stroke-width:12}}
.saas-mark{{display:grid;grid-template-columns:190px 80px 1fr;align-items:center;gap:20px;margin-top:46px;direction:ltr}}.saas-mark>b{{display:grid;place-items:center;width:180px;height:180px;border-radius:48px;background:var(--accent);color:var(--bg);font:900 110px Ray}}.saas-mark>i{{height:5px;background:var(--accent);position:relative}}.saas-mark>i:after{{content:"";position:absolute;right:-2px;top:-11px;border:13px solid transparent;border-left-color:var(--accent)}}.saas-mark>div{{display:flex;flex-direction:column;gap:9px}}.saas-mark span{{font:900 35px/1.2 Ray;color:var(--fg)}}
.kinetic{{font-size:118px;line-height:1.3;margin-top:55px;color:var(--accent);max-width:900px;min-height:190px;padding-bottom:30px;overflow:hidden}}
.kinetic_type h2{{display:none}}.kinetic_type .kinetic{{font-size:132px;margin-top:160px;max-width:920px}}
.before-after{{display:grid;grid-template-columns:1fr 90px 1fr;gap:18px;align-items:center;margin-top:65px;font-size:34px;text-align:center}}.before-after span{{height:210px;border-radius:32px;border:3px solid currentColor;display:flex;flex-direction:column;justify-content:center;padding:24px}}.before-after small{{display:block;color:var(--accent);font-size:23px;margin-bottom:15px}}.before-after i{{height:5px;background:var(--accent);position:relative}}.before-after i:after{{content:"→";position:absolute;left:28px;top:-38px;color:var(--accent);font-style:normal;font-size:60px}}
.registry-beat .beat-inner{{position:absolute;inset:0;padding:0!important}}.registry-beat .ghost,.registry-beat .eyebrow,.registry-beat h2{{display:none}}
.registry-beat .registry-stage{{position:absolute;inset:0;width:100%;height:100%;margin:0;overflow:hidden;border-radius:0;background:#080b0c}}
.registry-stage>[data-composition-src]{{position:absolute;inset:0;width:100%;height:100%}}
.registry-collage-content{{width:100%;height:100%;padding:230px 90px;display:grid;grid-template-columns:1fr 1fr;gap:28px;background:#0b1010;direction:rtl}}
.registry-collage-content span{{display:grid;place-items:center;padding:32px;border:2px solid #d9ff4f;border-radius:30px;color:#f7f5ed;background:#151b1b;font:76px/1.15 Ray;text-align:center}}
</style></head><body><main id="root" data-composition-id="main" data-start="0" data-duration="{duration:.3f}" data-width="1080" data-height="1920">
{backdrops}
<div id="speaker-stage" style="position:absolute;inset:0;overflow:hidden;transform-origin:50% 50%"><video id="rough-cut" class="base clip" src="./assets/base.mp4" data-start="0" data-duration="{duration:.3f}" data-track-index="0" data-has-audio="true"></video></div>
{cards}
{sfx_markup}</main><script>{_timeline_script(beats)}</script></body></html>'''
    if motion_only:
        # Browser draws only the actual graphics panel. The native speaker,
        # captions and original audio are composited later without Chromium.
        document = document.replace('width=1080,height=1920', 'width=1080,height=888')
        document = document.replace('height:1920px', 'height:888px')
        document = document.replace('data-height="1920"', 'data-height="888"')
        document = re.sub(r'<div id="speaker-stage".*?</video></div>', '', document, flags=re.S)
    entry = project_dir / "index.html"
    entry.write_text(document)
    return entry
