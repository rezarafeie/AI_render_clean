"""Motion Designer: authors a real motion scene for each beat, instead of filling a fixed template.

For every visual beat the model writes HTML + scoped CSS + a GSAP snippet (rendered by HyperFrames), guided by one
shared design system so the whole video looks like one identity. Output is validated (engine/hyperframes/scenes.py)
and repaired once or twice from the validator's messages; a beat that cannot be authored simply keeps the built-in
template, so authoring can raise the ceiling but never lower the floor.
"""
from __future__ import annotations

import json
import re
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import llm
from .schemas import CreativeUnavailable

log = logging.getLogger(__name__)

MOTION_ROUTE = "creative_motion"

PANEL_MAX_Y = 856          # the lowest y a top-panel scene may use; talking_5 lowers it so the speaker's head can rise into the rest

PALETTES = {
    "shadow-cut": {"bg": "#0B0D0C", "surface": "#161A18", "ink": "#F2F0E8", "accent": "#C8FF3D", "accent2": "#FF5A36", "muted": "#8C938E"},
    "velvet": {"bg": "#0F2A24", "surface": "#173A32", "ink": "#F4EBD8", "accent": "#D9A441", "accent2": "#E8E1CF", "muted": "#9DB3AA"},
    "swiss-pulse": {"bg": "#F3F0E8", "surface": "#FFFFFF", "ink": "#101414", "accent": "#E4332B", "accent2": "#1C4FD8", "muted": "#6B6E69"},
    "ink-and-saffron": {"bg": "#14110F", "surface": "#221C18", "ink": "#FBF3E4", "accent": "#FFB81C", "accent2": "#FF6B57", "muted": "#A89B8C"},
    "deep-sea": {"bg": "#071A2B", "surface": "#0E2C47", "ink": "#EAF4FF", "accent": "#35E0C4", "accent2": "#7AA2FF", "muted": "#7F9BB5"},
    "paper-bold": {"bg": "#EFE7DA", "surface": "#FAF5EC", "ink": "#1B1712", "accent": "#0E7C66", "accent2": "#E8572A", "muted": "#7A6F60"},
}


class DesignSystem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = "shadow-cut"
    bg: str = "#0B0D0C"
    surface: str = "#161A18"
    ink: str = "#F2F0E8"
    accent: str = "#C8FF3D"
    accent2: str = "#FF5A36"
    muted: str = "#8C938E"
    mood: str = ""
    personality: str = ""          # how things move and feel
    shape: str = ""                # corner radius, strokes, grid
    display_font: str = "Ray 900"  # one expressive voice
    text_font: str = "Ray 500"

    @field_validator("bg", "surface", "ink", "accent", "accent2", "muted", mode="before")
    @classmethod
    def _hex(cls, value):
        text = str(value or "").strip()
        return text if len(text) in {4, 7} and text.startswith("#") and all(c in "0123456789abcdefABCDEF" for c in text[1:]) else "#888888"

    def tokens(self) -> str:
        return (f"bg {self.bg}, surface {self.surface}, ink {self.ink}, accent {self.accent}, accent2 {self.accent2}, muted {self.muted}; "
                f"mood: {self.mood}; motion personality: {self.personality}; shape language: {self.shape}; "
                f"display font: {self.display_font}; text font: {self.text_font}")


class AuthoredScene(BaseModel):
    model_config = ConfigDict(extra="ignore")
    speaker: str = "full"
    html: str
    css: str = ""
    js: str
    notes: str = ""


class SceneSpec(BaseModel):
    id: str
    start: float
    end: float
    spoken: str = ""            # what the speaker says in this part (the only source of on-screen words besides title/items)
    title: str = ""
    items: list[str] = Field(default_factory=list)
    role: str = ""
    visual_idea: str = ""       # from the director's beat
    motion_idea: str = ""
    archetype: str = ""         # a compositional direction to keep neighbouring scenes different
    prior_scenes: list[str] = Field(default_factory=list)
    layout: str = 'full_frame'

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 2)


ARCHETYPES = [
    "giant typographic statement with an oversized ghost word bleeding off the frame and one highlighted word",
    "split frame: two opposing ideas on either side of a divider that slides, with a clear winner emerging",
    "hand-built SVG diagram (nodes, arrows or a growth curve) that draws itself in the order the speaker explains it",
    "stack of layered cards with depth, parallax and a focal card that lifts forward",
    "a single big number with an animated counter, a progress ring or bar, and a small label that explains it",
    "a conversation or message thread that types in, one bubble at a time",
    "a path or timeline that draws across the frame with labelled milestones",
    "a grid of simple custom SVG icons that assemble one by one, then one icon scales up as the point",
    "before/after wipe where the second state replaces the first with a decisive motion",
    "editorial caption: serif accent word, thin rules, small metadata labels, slow deliberate reveal",
]

DESIGN_SYSTEM_PROMPT = """You are the art director of a Persian short-form video studio. From the content brief and the chosen creative
concept, define ONE visual identity for the whole video. Return ONLY JSON:
{"name": "<2-3 word name>", "bg": "#hex", "surface": "#hex", "ink": "#hex", "accent": "#hex", "accent2": "#hex", "muted": "#hex",
 "mood": "<what the viewer should feel>", "personality": "<how things move: speed, ease character, what never happens>",
 "shape": "<corner radius, stroke weight, grid, texture>", "display_font": "Ray 900" , "text_font": "Ray 500"}
Rules: tint neutrals toward the accent hue (no dead grey); the accent must be vivid enough to survive video compression; pick the
palette from the content's emotion, not from habit. Palettes you may start from or deliberately depart from:
""" + "\n".join(f"- {name}: {tokens}" for name, tokens in PALETTES.items()) + """
Fonts available (Persian + Latin): "Ray" weights 300/400/500/700/800/900 (use extreme weight contrast: 300 vs 900), "Kharazmi" (Persian
editorial serif, 400 only, use as ONE accent voice), "Vazir" 400. Do not mix more than two voices."""

AUTHOR_PROMPT = """You are a senior motion designer. You write ONE scene of a vertical (1080x1920, 30 fps) Persian short video as real
HTML + CSS + GSAP. It will be rendered frame by frame by HyperFrames, so everything must be deterministic. Make it look designed by a
professional: specific to this content, layered, and alive. Never a template, never decoration without meaning.

THE CONTRACT (violations are rejected and sent back to you)
- The renderer already created the root `<section id="{ID}">`, absolutely positioned over the whole 1080x1920 frame, `dir="rtl"`.
  You write only its INNER html. Every id you create must start with "{ID}-". No <script>, <style>, <img>, <video>, <br>, forms or external URLs.
  Use inline SVG (paths, shapes, gradients, masks, feTurbulence grain) for any drawing, icon or diagram.
- CSS: every selector must start with #{ID} (for example `#{ID} .hero{...}`). No @keyframes, animation, transition, @import, url(), position:fixed.
- JS: you are given `tl` (the seekable GSAP timeline), `root`, `$(sel)` (scoped querySelectorAll returning an array), `T` (this scene's start in
  seconds) and `D` (its duration). Write ONLY tl.fromTo(...) / tl.to(...) / tl.set(...) calls whose position argument is `T + offset`. Never use
  tl.from, gsap.*, Math.random, Date, timers, window, fetch. Never tween the same property of one element from two overlapping tweens. An element that a tween moves or scales (x, y, z, scale, rotation) must have NO `transform` in its CSS (GSAP would overwrite it): give it its resting
  position with `tl.set(sel, {x, y, z, rotationY, scale}, T)` as the first call for it, or with left/top/margin. Never use
  `repeat`, `repeatDelay` or `yoyo` in any tween (they are rejected): an ambient or looping motion (grain, rays, a pulse, a float) is written as several
  separate fromTo steps, one per swing, each at its own `T + offset`, until T + D - 0.4. Every
  animated element needs both start and end states in fromTo. Finish building by T + D - 0.4; the renderer fades the root out at the end.
- Text must fit its box: the renderer checks every text against the box it sits in and rejects the scene when it overflows. Make the box at least as
  large as the text (a 96px Persian line is about 55px per character wide), lower the font-size, or let it wrap with `max-width` and `white-space: normal`.
- Persian text: use font-family Ray (weights 300-900), optionally Kharazmi for ONE accent word/line. letter-spacing must be 0 for Persian (negative
  tracking breaks the joins). Never split a Persian word into letters; for word-by-word motion wrap whole words in inline-block spans. Numbers: use
  Persian digits when the speech does. Use `direction: ltr` for Latin/numeric chunks that must read left to right.
- Words on screen: only words/numbers from SPOKEN, TITLE and ITEMS (or obvious labels that restate them). Never invent facts, statistics, names, logos.

CRAFT (adapted from the Apache-2.0 "motion-design" skill of nexu-io/open-design and the HyperFrames house rules)
- Art direction before movement: decide ONE concrete visual premise for this moment (what fills the frame, where attention rests, the material:
  editorial ink, precise instrument, folded paper, tactile collage, vector geometry...). "Premium", "cinematic", "modern" are not premises.
  A weak still frame is never rescued by effects: make the resting frame beautiful first, then animate it.
- One mechanism, not unrelated cards: let one object, shape, line or word transform to carry the idea (a number grows into a bar, two words collide
  into one, a line becomes the route). Each movement must change the meaning.
- Banned defaults: neon gradient, glass cards, a glowing orb, three equal cards under a centred headline, everything centred, symmetric layouts,
  the same entrance on every element, decorative lines that connect nothing.
- Timing: accent 0.12-0.22s snap then settle; main arrival 0.35-0.65s quick travel with a controlled landing; a meaningful transformation
  0.6-1.2s with readable setup and resolution; a large reveal 0.9-1.8s. Precise/instrument motion does not bounce; playful material may overshoot.
  Constant speed only for clocks, scans, tickers. Alternate action and rest: the strongest transformation belongs to the central idea.
- Attention: the primary action carries the idea, a secondary action shows weight or consequence (a trailing label, a shadow settling), ambient
  motion only if the scene needs it. Reading time is longer than reveal time: hold the key words long enough to read them.
- Kinetic type: keep a stable reading window; animate a phrase as one unit when word-by-word would hinder comprehension; never rotate/blur/scatter
  every line. SVG scale entrances: set the same svgOrigin in BOTH the from and the to state.

DESIGN RULES (this is where quality comes from)
- Fill the frame. Hero text 60-80% of width, headlines 110-190px, body 44px+, labels 28px+. Persian display text needs line-height 1.35+.
- At least three layers: a background treatment (radial glow, oversized faded type, shape, grain/texture, grid) that is never empty; the message; and
  foreground details (rules, labels, small marks) that make it look produced. No full-screen linear gradients on dark (banding): use radial or solid.
- Two focal points so the eye travels. Anchor to edges and use asymmetry; avoid a lone centred block floating in space.
- Colour: use the design-system tokens exactly; one colour must pull the eye at full saturation.
- Motion is the verb: build (0-30% of D) / breathe (one ambient motion) / resolve. Use at least three different eases and entrance directions
  (never everything `y:30, opacity:0`). Enter with .out eases (expo.out, power4.out, back.out) and move with .inOut. Offset the first tween by
  0.1-0.25s. Vary speed: some elements 0.15-0.3s, one slow 0.8s+. Stagger by importance. Animate scale, clip-path, strokeDashoffset, x/y, rotation,
  blur, letter-by-letter ONLY for Latin. Keep something alive in the breathe phase (slow drift, pulse, line drawing, counter).
- Every line, arrow or rail must connect two real things and do a job (reveal, route, prove, emphasise); otherwise remove it.
- Compose WITH the speaker. Pick `speaker`:
{SPEAKER_AREAS}
  When the speaker stays visible (full, pip) keep text off his face and give text a scrim/panel for legibility.

ART DIRECTION FOR THIS SCENE
Design system: {DESIGN}
Scene role: {ROLE}. Duration D = {D}s. The speaker says: «{SPOKEN}»
On-screen title: «{TITLE}»   Items: {ITEMS}
Director's idea: {VISUAL}
Director's motion: {MOTION}
Compositional direction (start here, make it your own): {ARCHETYPE}
{PRIOR}
Return ONLY JSON: {"speaker": "full|dim|pip|hidden", "html": "...", "css": "...", "js": "...", "notes": "<one sentence: the idea in the scene>"}"""


def _speaker_areas() -> str:
    from engine.hyperframes.scenes import FREE_AREA
    return "\n".join(f"    - {mode}: {text}" for mode, text in FREE_AREA.items())


def build_prompt(spec: SceneSpec, design: DesignSystem) -> str:
    prior = ("Scenes already designed for this video (do NOT repeat their layout or motion): " + "; ".join(spec.prior_scenes)) if spec.prior_scenes else ""
    prompt = (AUTHOR_PROMPT.replace("{ID}", spec.id).replace("{SPEAKER_AREAS}", _speaker_areas()).replace("{DESIGN}", design.tokens())
            .replace("{ROLE}", spec.role or "evidence").replace("{D}", f"{spec.duration:g}").replace("{SPOKEN}", spec.spoken[:3000])
            .replace("{TITLE}", spec.title).replace("{ITEMS}", " | ".join(spec.items) or "(none)").replace("{VISUAL}", spec.visual_idea or "(your call)")
            .replace("{MOTION}", spec.motion_idea or "(your call)").replace("{ARCHETYPE}", spec.archetype or ARCHETYPES[0]).replace("{PRIOR}", prior))
    if spec.layout == 'top_panel':
        prompt = prompt.replace('1080x1920', '1080x888')
        prompt += ('\nOVERRIDING TALKING 2 CONTRACT: your entire scene is a 1080x888 TOP PANEL. '
                   'The separate full-width speaker and caption rail below are owned by the renderer. '
                   'Return speaker="full"; never move or hide the speaker. Fill this panel with an opaque '
                   'design-system background. Explain ALL supplied sentences as a coherent evolving visual, '
                   'with meaningful intermediate states throughout D, not a 2-second entrance then empty space. '
                   f'Keep every label within x=32..1048, y=24..{PANEL_MAX_Y}. Headlines 64–100px; body 38px+. '
                   'Do not use emoji or unsupported symbol glyphs; draw icons with inline SVG.')
    return prompt


def design_system(brief_text: str, concept_text: str, used: list[str] | None = None) -> DesignSystem:
    try:
        return llm.ask(DesignSystem, DESIGN_SYSTEM_PROMPT, f"Brief:\n{brief_text}\n\nChosen concept:\n{concept_text}",
                       route=llm.DIRECTOR_ROUTE, tokens=1500, used=used)
    except CreativeUnavailable as exc:
        log.warning("design system unavailable, using a preset: %s", exc)
        return DesignSystem(**{"name": "shadow-cut", **PALETTES["shadow-cut"], "mood": "bold and precise", "personality": "fast decisive entrances, slow breathing ambient motion",
                               "shape": "radius 28px, 3px strokes, hairline rules"})


def author_scene(spec: SceneSpec, design: DesignSystem, *, used: list[str] | None = None, repairs: int = 2, feedback: list[str] | None = None) -> AuthoredScene:
    """One validated scene. Repairs feed the validator's messages back to the model."""
    from engine.hyperframes.scenes import validate_scene, scope_owned_selectors
    prompt = build_prompt(spec, design)
    last: list[str] = list(feedback or [])   # what the render check said about an earlier version of this scene
    for attempt in range(repairs + 1):
        user = prompt if not last else prompt + "\n\nYour previous answer was rejected for these reasons. Fix every one and return the full JSON again:\n- " + "\n- ".join(last[:8])
        scene = llm.ask(AuthoredScene, "You output a single JSON object and nothing else.", user, route=MOTION_ROUTE, tokens=9000, attempts=2, used=used)
        scene.css = scope_owned_selectors(spec.id, scene.html, scene.css)
        last = validate_scene(spec.id, scene.html, scene.css, scene.js, scene.speaker)
        if any("repeat" in p or "yoyo" in p for p in last):
            last.append("do not loop with repeat/yoyo: write every swing of the ambient motion as its own tl.fromTo at T + offset (for example four back-and-forth steps across the scene)")
        if any("transition" in p for p in last):
            last.append("CSS must not contain `transition:`; every change of state is a tl.fromTo in the JS")
        if not last:
            return scene
        log.warning("scene %s rejected (attempt %d): %s", spec.id, attempt + 1, last[:3])
    raise CreativeUnavailable(f"scene {spec.id} did not pass validation: {last[:3]}")


def layout_feedback(message: str, beats: list) -> dict[str, list[str]]:
    """What a failed HyperFrames check says about each authored scene: {beat id: [what to fix]} (empty when it names no scene of ours)."""
    found: dict[str, list[str]] = {}
    for part in str(message).split(" | "):
        match = re.search(r"@#([\w-]+)", part)
        if not match:
            continue
        target = next((b.id for b in beats if b.custom and (match.group(1) == b.id or match.group(1).startswith(b.id + "-"))), None)
        if target:
            found.setdefault(target, []).append("the rendered scene failed HyperFrames' own check: " + part.strip()[:420]
                                                + ". Rewrite the scene so every element sits inside its container at every moment (size the boxes to the text, use a smaller font-size, or allow wrapping with max-width).")
    return found


def plan_from_public(data: dict | None):
    """Rebuild what `compose` needs from `CreativePlan.public()` (what is stored on a job); tolerant of an empty/absent plan."""
    from types import SimpleNamespace
    from .schemas import Beat
    data = data or {}
    brief, chosen = data.get("brief") or {}, data.get("chosen") or {}
    return SimpleNamespace(
        brief=SimpleNamespace(**{k: brief.get(k, "") for k in ("topic", "core_message", "audience", "tone")}),
        chosen=SimpleNamespace(name=chosen.get("name", ""), angle=chosen.get("angle", ""), visual_language=chosen.get("visual_language", ""),
                               pacing=chosen.get("pacing", ""), beats=[Beat(**b) for b in chosen.get("beats", []) if isinstance(b, dict)]))


def enabled() -> bool:
    """Authored motion is part of the creative layer; CREATIVE_MOTION=0 keeps only the built-in templates."""
    import os
    from . import director
    return director.enabled() and os.environ.get("CREATIVE_MOTION", "1").strip().lower() not in {"0", "false", "off", "no"}


def _fingerprint(beat, plan=None) -> str:
    from .reuse import fingerprint
    chosen=getattr(plan,'chosen',None)
    context={k:getattr(chosen,k,'') for k in ('name','angle','visual_language','pacing')}
    context['beats']=[b.model_dump() for b in getattr(chosen,'beats',[])]
    return fingerprint({'version':2,'beat':beat.model_dump(exclude={'custom'}),'direction':context})


def compose(beats: list, plan, sentences: list[dict], *, max_workers: int = 4, used: list[str] | None = None,
            cache: Path | None = None, cached_only: bool = False, feedback: dict[str, list[str]] | None = None) -> list:
    """Attach authored scenes to `beats` (VisualBeat objects). Beats that fail keep their template. Returns the same list.

    `cache` is a JSON file next to the job: scenes already authored for the same beat id and timing are reused, so a
    re-render or a retry never pays for the same scene twice."""
    if not beats:
        return beats
    stored = {"design": None, "scenes": {}}
    if cache and cache.is_file():
        try:
            stored = {**stored, **json.loads(cache.read_text())}
        except (OSError, ValueError):
            pass
    if cached_only:
        # A render continuation may reuse authored work, never ask an LLM to
        # redesign missing scenes or silently replace them with other visuals.
        for beat in beats:
            hit = stored['scenes'].get(beat.id)
            match=hit and (hit.get('fp') == _fingerprint(beat,plan) or
                hit.get('fp') == f'{beat.start:.1f}')  # read-only legacy continuation; never pay to migrate
            if not match:
                raise ValueError('صحنهٔ موشن آماده نیست؛ ادامه نیازمند تأیید تولید صحنه است.')
            beat.custom = {k:v for k,v in hit.items() if k != 'fp'}
            beat.custom['bg'] = (stored.get('design') or {}).get('bg', '#0B0D0C')
        return beats
    brief = plan.brief
    brief_text = f"topic: {brief.topic}; message: {brief.core_message}; audience: {brief.audience}; tone: {brief.tone}"
    concept = plan.chosen
    concept_text = f"{concept.name}: {concept.angle}. Visual language: {concept.visual_language}. Pacing: {concept.pacing}"
    design = DesignSystem(**stored["design"]) if stored.get("design") else design_system(brief_text, concept_text, used)
    by_sentence = {b.sentence: b for b in concept.beats if b.sentence is not None}
    specs: list[SceneSpec] = []
    for index, beat in enumerate(beats):
        try:
            sentence = int(beat.id.split("-")[1])
        except (IndexError, ValueError):
            sentence = -1
        idea = by_sentence.get(sentence) or (concept.beats[index] if index < len(concept.beats) else None)
        specs.append(SceneSpec(id=beat.id, start=beat.start, end=beat.end,
                               spoken=beat.spoken or (sentences[sentence]["text"] if 0 <= sentence < len(sentences) else ""),
                               title=beat.title, items=beat.items, role=beat.narrative_role,
                               visual_idea=(idea.visual if idea else beat.why), motion_idea=(idea.motion if idea else ""),
                               archetype=ARCHETYPES[(index * 3 + len(beat.title)) % len(ARCHETYPES)], layout=beat.layout))
    feedback = feedback or {}
    results: dict[str, AuthoredScene] = {}

    def work(spec: SceneSpec):
        try:
            return spec.id, author_scene(spec, design, used=used, feedback=feedback.get(spec.id))
        except Exception as exc:  # any failure keeps the template for this beat
            log.warning("motion author failed for %s: %s", spec.id, str(exc)[:200])
            return spec.id, None

    fresh = []
    for spec, beat in zip(specs, beats):
        hit = stored["scenes"].get(spec.id)
        kept = None
        if hit and hit.get("fp") == _fingerprint(beat,plan) and spec.id not in feedback:
            from engine.hyperframes.scenes import validate_scene
            kept = AuthoredScene(**{k: v for k, v in hit.items() if k != "fp"})
            if validate_scene(spec.id, kept.html, kept.css, kept.js, kept.speaker):   # a scene stored before a rule existed is written again, not reused
                kept = None
        if kept:
            results[spec.id] = kept
        else:
            fresh.append(spec)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for beat_id, scene in pool.map(work, fresh):
            if scene:
                results[beat_id] = scene
    if cache:
        by_id = {beat.id: beat for beat in beats}
        stored["design"] = design.model_dump()
        stored["scenes"] = {**stored["scenes"], **{bid: {**sc.model_dump(), "fp": _fingerprint(by_id[bid],plan)} for bid, sc in results.items()}}
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(stored, ensure_ascii=False))
        except OSError:
            pass
    for beat in beats:
        scene = results.get(beat.id)
        if scene:
            beat.custom = {"html": scene.html, "css": scene.css, "js": scene.js, "speaker": scene.speaker, "notes": scene.notes, "bg": design.bg}
    log.info("motion designer: %d of %d scenes authored", len(results), len(beats))
    return beats
