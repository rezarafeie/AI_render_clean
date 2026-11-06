"""Authored ("custom") scenes: validation and speaker treatments.

A scene is HTML + scoped CSS + a small GSAP snippet written by the Motion Designer (creative/motion.py) for ONE
beat. The renderer never trusts it: everything is validated here, fonts and GSAP come from local files, and the
speaker video is moved by the builder (not by the scene) so it always returns to its normal place.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from html.parser import HTMLParser

MAX_HTML, MAX_CSS, MAX_JS = 24_000, 16_000, 12_000
SPEAKER_MODES = ("full", "dim", "pip", "hidden")

# Geometry of the 1080x1920 canvas for each speaker treatment: the part a scene may rely on being free.
FREE_AREA = {
    "full": "the whole frame, drawn OVER the moving speaker (keep backgrounds transparent or translucent; protect legibility with a scrim)",
    "dim": "the whole frame; the speaker stays behind it, blurred and darkened to about 35% brightness",
    "pip": "the top 960px (x 0-1080, y 0-960). The speaker shrinks into a rounded picture at the bottom centre (about y 970-1850)",
    "hidden": "the whole frame, opaque; the speaker is hidden (audio continues). Use sparingly, for emphasis",
}

# What the builder animates on #speaker-stage for each mode (enter at start, return before the end).
SPEAKER_TWEENS = {
    "dim": {"to": {"filter": "blur(16px) brightness(.34) saturate(.75)", "scale": 1.08}, "back": {"filter": "blur(0px) brightness(1) saturate(1)", "scale": 1}},
    "pip": {"to": {"scale": .46, "y": 452, "borderRadius": 64, "boxShadow": "0 40px 90px rgba(0,0,0,.55)"}, "back": {"scale": 1, "y": 0, "borderRadius": 0, "boxShadow": "0 0 0 rgba(0,0,0,0)"}},
    "hidden": {"to": {"opacity": 0}, "back": {"opacity": 1}},
}

_FORBIDDEN_TAGS = {"script", "style", "link", "iframe", "object", "embed", "form", "input", "button", "video", "audio", "canvas", "base", "meta", "br", "img"}
_FORBIDDEN_JS = (r"\bMath\.random\b", r"\bDate\b", r"\bsetTimeout\b", r"\bsetInterval\b", r"\brequestAnimationFrame\b", r"\bfetch\b",
                 r"\bXMLHttpRequest\b", r"\bimport\b", r"\beval\b", r"\bFunction\s*\(", r"\bdocument\.write\b", r"\bwindow\b", r"\blocalStorage\b",
                 r"\brepeat\s*:\s*-?[1-9]",r"\byoyo\b", r"\bgsap\.(to|from|fromTo|set|timeline)\b", r"\bperformance\b", r"\bnew\s+Worker\b")
_FORBIDDEN_CSS = (r"@import", r"@keyframes", r"\banimation\s*:", r"\banimation-", r"\btransition\s*:", r"\btransition-", r"position\s*:\s*fixed",
                  r"url\(\s*['\"]?(?!#)", r"expression\(", r"behavior\s*:")


class _Scan(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.ids: list[str] = []
        self.problems: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag in _FORBIDDEN_TAGS:
            self.problems.append(f"<{tag}> is not allowed")
        for name, value in attrs:
            if name.startswith("on"):
                self.problems.append(f"event handler attribute {name} is not allowed")
            if name == "id" and value:
                self.ids.append(value)
            if name in {"href", "src", "xlink:href"} and value and not value.startswith("#"):
                self.problems.append(f"external reference in {name}")
            if name == "style" and value and re.search(r"url\(|position\s*:\s*fixed|animation|transition", value, re.I):
                self.problems.append("unsafe inline style")
            if name == "data-start" or name == "data-duration":
                self.problems.append(f"{name} is controlled by the renderer")


def _css_rules(css: str) -> list[tuple[str, str]]:
    """(selector list, body) pairs for a flat stylesheet (no nested at-rules are allowed)."""
    return [(m.group(1).strip(), m.group(2)) for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css)]


def scope_owned_selectors(beat_id: str, html: str, css: str) -> str:
    """Qualify a scene's own child IDs without accepting global CSS.

    Models often use #scene-id-child instead of #scene-id #scene-id-child.
    This is a deterministic namespace repair, not a reason for another model
    request. Unknown IDs, unscoped classes and at-rules still fail validation.
    """
    scan = _Scan()
    scan.feed(html)
    owned = {i for i in scan.ids if i.startswith(beat_id + '-')}

    def rule(match):
        selectors = []
        for raw in match.group(1).split(','):
            selector = raw.strip()
            head = re.match(r'^#([A-Za-z0-9_-]+)(?=[\s.:\[>+~#]|$)', selector)
            if head and head[1] in owned:
                selector = f'#{beat_id} ' + selector
            selectors.append(selector)
        return ','.join(selectors) + '{' + match.group(2) + '}'

    return re.sub(r'([^{}]+)\{([^{}]*)\}', rule, css)


def validate_scene(beat_id: str, html: str, css: str, js: str, speaker: str) -> list[str]:
    """Problems that make a scene unsafe or undeterministic. Empty list = acceptable."""
    problems: list[str] = []
    if speaker not in SPEAKER_MODES:
        problems.append(f"speaker must be one of {SPEAKER_MODES}")
    if not html.strip() or len(html) > MAX_HTML:
        problems.append("html is empty or too large")
    if len(css) > MAX_CSS or len(js) > MAX_JS:
        problems.append("css or js is too large")
    scan = _Scan()
    try:
        scan.feed(html)
    except Exception:  # malformed markup
        problems.append("html could not be parsed")
    problems += scan.problems
    prefix = f"{beat_id}-"
    bad_ids = [value for value in scan.ids if not value.startswith(prefix)]
    if bad_ids:
        problems.append(f"every id must start with '{prefix}' (found {bad_ids[:3]})")
    for pattern in _FORBIDDEN_CSS:
        if re.search(pattern, css, re.I):
            problems.append(f"css uses a forbidden construct ({pattern})")
    scope = f"#{beat_id}"
    for selector_list, _ in _css_rules(css):
        if selector_list.startswith("@"):
            problems.append("at-rules are not allowed in css")
            continue
        for selector in (s.strip() for s in selector_list.split(",")):
            if selector and not (selector == scope or selector.startswith(scope + " ") or selector.startswith(scope + ".") or selector.startswith(scope + ">") or selector.startswith(scope + ":")):
                problems.append(f"css selector '{selector[:60]}' must start with {scope}")
    if not re.search(r"\btl\.(to|from|fromTo|set)\(", js):
        problems.append("js must build the animation with tl.fromTo/tl.to on the provided timeline `tl`")
    for pattern in _FORBIDDEN_JS:
        if re.search(pattern, js):
            problems.append(f"js uses a forbidden construct ({pattern})")
    # GSAP replaces the whole CSS transform of an element it moves (x, y, scale, rotation): HyperFrames rejects that, so catch it here where the model can repair it.
    animated = re.compile(r"\b(x|y|z|xPercent|yPercent|scale|scaleX|scaleY|rotation|rotationX|rotationY|rotationZ|skewX|skewY)\s*:")
    if animated.search(js):
        for selector_list, body in _css_rules(css):
            if not re.search(r"(^|[;\s])transform\s*:", body):
                continue
            for selector in (x.strip() for x in selector_list.split(",")):
                last = re.split(r"[\s>+~]+", selector)[-1] if selector else ""
                tokens = re.findall(r"[#.][A-Za-z_][\w-]*", last)
                if any(token in js for token in tokens):
                    problems.append(f"css `transform` on '{selector[:60]}' is also animated by GSAP in js, which overwrites it: remove `transform` from the css and place the element with tl.set('{tokens[-1] if tokens else selector}', {{x, y, z, rotationY, scale}}, T) instead")
                    break
    if re.search(r"\btl\.from\(", js):
        problems.append("use tl.fromTo instead of tl.from (immediateRender breaks seeking)")
    if re.search(r"letter-spacing\s*:\s*-", css + html):
        problems.append("negative letter-spacing breaks Persian letter joins; use 0 for Persian text")
    if not problems:
        node = shutil.which('node')
        if not node:
            problems.append('Node.js is required to validate motion JavaScript syntax')
        else:
            try:
                parsed = subprocess.run([node, '--check'],
                    input='function scene(tl,root,$,T,D){\n'+js+'\n}',
                    text=True,capture_output=True,timeout=10)
                if parsed.returncode:
                    detail=next((line.strip() for line in parsed.stderr.splitlines() if 'SyntaxError:' in line), 'invalid JavaScript')
                    problems.append(detail[:220])
            except (OSError,subprocess.TimeoutExpired):
                problems.append('Motion JavaScript syntax could not be verified')
    return problems


def fonts_css() -> str:
    """@font-face for the local Persian-capable families the designer may use (files are copied by the builder)."""
    faces = [("Ray", 300, "ray-light.ttf"), ("Ray", 400, "ray.ttf"), ("Ray", 500, "ray-medium.ttf"), ("Ray", 700, "ray-bold.ttf"),
             ("Ray", 800, "ray-extrabold.ttf"), ("Ray", 900, "ray-black.ttf"), ("Kharazmi", 400, "kharazmi.ttf"), ("Vazir", 400, "vazirmatn.ttf")]
    return "".join(f"@font-face{{font-family:{family};font-weight:{weight};src:url('./assets/fonts/{file}')}}" for family, weight, file in faces)


FONT_FILES = {
    "ray-light.ttf": "RAY-LIGHT.TTF", "ray.ttf": "RAY.TTF", "ray-medium.ttf": "RAY-MEDIUM.TTF", "ray-bold.ttf": "RAY-BOLD.TTF",
    "ray-extrabold.ttf": "RAY-EXTRABOLD.TTF", "ray-black.ttf": "RAY-BLACK.TTF",
    "kharazmi.ttf": "IRAN_Kharazmi/IRAN Kharazmi.ttf", "vazirmatn.ttf": "Vazirmatn-Regular.ttf",
}


def scene_backdrop(beat_id: str, start: float, duration: float, bg: str = "") -> str:
    """Full-frame colour (the design system's background) UNDER the speaker, so a shrunken speaker never floats on raw
    black below or beside the scene's artwork. Placed before #speaker-stage; visible only while the speaker is small."""
    color = bg if re.fullmatch(r"#[0-9a-fA-F]{6}", bg or "") else "#0B0D0C"
    return (f'<div id="{beat_id}-backdrop" class="custom-backdrop clip" data-start="{start:.3f}" data-duration="{duration:.3f}" '
            f'data-track-index="1" style="position:absolute;inset:0;background:{color}"></div>')


def scene_markup(beat_id: str, start: float, duration: float, html: str) -> str:
    # This is a clip driven by the parent's single timeline, not an independently
    # registered composition. A composition-id here advertises a child timeline
    # that does not exist and makes runtime discovery/validation misleading.
    return (f'<section id="{beat_id}" class="custom-beat clip" data-start="{start:.3f}" data-duration="{duration:.3f}" '
            f'data-track-index="2" dir="rtl">{html}</section>')


def scene_script(beat_id: str, start: float, end: float, js: str, speaker: str) -> str:
    """The scene's JS runs inside a closure that provides: tl, root, $ (scoped query), T (start seconds), D (duration)."""
    duration = end - start
    # GSAP's default immediateRender eagerly applies later fromTo start states.
    # Those states can overwrite earlier explicit sets when the renderer seeks
    # directly into a scene. Enforce the seek-safe contract at the adapter, not
    # by rewriting model-authored JavaScript or asking the model to regenerate.
    lines = ['(function(parent){ const tl = new Proxy(parent, {get(target, key){ '
             'const value = Reflect.get(target, key, target); '
             'if (typeof value !== "function") return value; '
             'return (...args) => { '
             'for (const index of (key === "fromTo" ? [1,2] : (["to","set"].includes(key) ? [1] : []))) { '
             'if (args[index] && args[index].svgOrigin === null) { '
             'const {svgOrigin, ...vars} = args[index]; args[index] = vars; }} '
             'if (key === "fromTo") args[2] = {...args[2], immediateRender:false}; '
             'const result = value.apply(target, args); return result === target ? tl : result; }; }}); '
             f'const root = document.getElementById("{beat_id}"); const $ = (s) => Array.from(root.querySelectorAll(s)); '
             f'const T = {start:.3f}, D = {duration:.3f};', js, '})(tl);']
    tweens = SPEAKER_TWEENS.get(speaker)
    if tweens:
        enter = {**tweens["to"], "duration": .5, "ease": "power3.inOut", "overwrite": "auto"}
        leave = {**tweens["back"], "duration": .45, "ease": "power3.inOut", "overwrite": "auto"}
        lines.append(f'tl.to("#speaker-stage", {_js(enter)}, {start:.3f});')
        lines.append(f'tl.to("#speaker-stage", {_js(leave)}, {max(start + .6, end - .45):.3f});')
    lines.append(f'tl.to("#{beat_id}", {{opacity:0, duration:.28, ease:"power1.in", overwrite:"auto"}}, {max(start + .5, end - .28):.3f});')
    return "\n".join(lines)


def _js(value: dict) -> str:
    import json
    return json.dumps(value)
