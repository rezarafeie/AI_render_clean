"""Motion graphics from a chat message: the model writes the scenes, the platform assembles a correct page around them.

The model returns the *parts* of a clip (scene markup, CSS, the body of ``build(tl)`` and an optional ``update(t)``). The
document itself (HyperFrames root, sizes, duration, fonts, GSAP, the kit, timeline registration) is assembled here, so none
of the contract can be got wrong. Every part is validated before anything is rendered, and a rejection is fed back to the model.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import llm
from .schemas import CreativeUnavailable

log = logging.getLogger(__name__)

DESIGNER_ROUTE = "motion_graphic_designer"
REPAIR_ROUTE = "motion_graphic_repair"

ROOT = Path(__file__).resolve().parents[1]
KIT = Path(__file__).resolve().parent / "motion_kit"       # inside the code layer: /app/presets is a host mount on the server
FORMATS = {"vertical": (1080, 1920), "horizontal": (1920, 1080), "square": (1080, 1080)}
MIN_SECONDS, MAX_SECONDS = 4.0, 30.0
LIMITS = {"scenes_html": 40_000, "css": 24_000, "build_js": 20_000, "update_js": 8_000}
COMPOSITION_ID = "main"


class MotionPage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    questions: list[str] = Field(default_factory=list)       # asked INSTEAD of a page when essential facts are missing
    title: str = ""
    summary: str = ""                                          # what the clip shows, one or two sentences, in the user's language
    format: Literal["vertical", "horizontal", "square"] = "vertical"
    duration: float = 15.0
    scenes_html: str = ""
    css: str = ""
    build_js: str = ""
    update_js: str = ""

    @field_validator("questions")
    @classmethod
    def _few(cls, value):
        return [str(q).strip() for q in value if str(q).strip()][:3]

    @property
    def size(self) -> tuple[int, int]:
        return FORMATS[self.format]

    def asks(self) -> bool:
        return bool(self.questions) and not self.scenes_html.strip()

    def public(self) -> dict:
        return {"title": self.title, "summary": self.summary, "format": self.format, "duration": self.duration,
                "width": self.size[0], "height": self.size[1]}


# ── validation ───────────────────────────────────────────────────────────────

_FORBIDDEN_TAGS = {"script", "style", "link", "iframe", "object", "embed", "form", "input", "button", "textarea", "select", "video", "audio",
                   "base", "meta", "br", "img", "image", "foreignobject", "source", "track", "html", "head", "body"}
_FORBIDDEN_JS = (
    (r"\bMath\.random\b", "Math.random (use HM.random(seed))"), (r"\bDate\b", "Date"), (r"\bperformance\b", "performance"),
    (r"\bsetTimeout\b|\bsetInterval\b", "timers"), (r"\brequestAnimationFrame\b", "requestAnimationFrame"),
    (r"\bfetch\b|\bXMLHttpRequest\b|\bWebSocket\b|\bEventSource\b|\bsendBeacon\b", "network access"),
    (r"\bimport\b|\brequire\b|\beval\b|\bFunction\s*\(", "dynamic code or imports"), (r"\bdocument\.write\b", "document.write"),
    (r"\blocalStorage\b|\bsessionStorage\b|\bindexedDB\b|\bcookie\b", "storage"), (r"\bwebgl2?\b|\bTHREE\b", "WebGL"),
    (r"\brepeat\s*:\s*-1\b", "infinite repeat"), (r"\bgsap\s*\.", "gsap.* (add tweens to tl instead)"),
    (r"\bwindow\b|\bglobalThis\b", "window/globalThis"), (r"\.split\(\s*(?:\"\"|'')\s*\)", "splitting text into letters"),
    (r"\binnerHTML\b|\binsertAdjacentHTML\b|\bouterHTML\b", "injecting markup from JS (write it in scenes_html)"),
    (r"\bvw\b|\bvh\b|innerWidth|innerHeight", "viewport units"),
    (r"\.style\s*\.\s*stroke|\.style\s*\.\s*setProperty\s*\(\s*[\"']stroke", "setting stroke styles by hand (draw SVG lines with HM.draw, or tl.fromTo(path, {strokeDashoffset: len}, {strokeDashoffset: 0}))"),
    (r"(?:querySelectorAll|getElementsBy\w+)\s*\([^)]*\)\s*\.style\b", "a list of elements has no .style (loop over it or hand the selector to tl/HM)"),
)
_FORBIDDEN_CSS = (
    (r"@import", "@import"), (r"@keyframes", "@keyframes"), (r"\banimation(?:-[a-z-]+)?\s*:", "CSS animation"),
    (r"\btransition(?:-[a-z-]+)?\s*:", "CSS transition"), (r"position\s*:\s*fixed", "position:fixed"),
    (r"url\(\s*['\"]?(?!#|data:image/svg)", "url() other than #fragment or inline SVG"), (r"expression\(|behavior\s*:", "legacy script hooks"),
    (r"-?\d+(?:\.\d+)?\s*(?:vw|vh|vmin|vmax)\b", "viewport units (use pixels inside the stage)"),
    (r"font-family\s*:[^;}]*", None),
)
_FONTS = {"ray", "vazir", "kharazmi"}


class _Scan(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.problems: list[str] = []
        self.ids: list[str] = []
        self.scenes: list[str] = []
        self.depth = 0
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _FORBIDDEN_TAGS:
            self.problems.append(f"<{tag}> is not allowed in scenes_html")
        a = {k.lower(): (v or "") for k, v in attrs}
        for name, value in a.items():
            if name.startswith("on"):
                self.problems.append(f"event attribute {name} is not allowed")
            if name in {"href", "src", "xlink:href"} and not (value.startswith("#") or value.startswith("data:image/svg")):
                self.problems.append(f"{name}=\"{value[:40]}\" points outside the page (only #fragments are allowed)")
            if name == "style" and re.search(r"url\(\s*['\"]?(?!#)|animation|transition|position\s*:\s*fixed|\d\s*(?:vw|vh)\b", value, re.I):
                self.problems.append("inline style uses a forbidden property (url/animation/transition/fixed/vw/vh)")
        if "id" in a:
            self.ids.append(a["id"])
        if tag == "section" and "hm-scene" in a.get("class", "").split():
            self.scenes.append(a.get("id", ""))

    def handle_data(self, data):
        if data.strip():
            self.text.append(data.strip())


def _strip_strings(code: str) -> str:
    code = re.sub(r"/\*.*?\*/|//[^\n]*", " ", code, flags=re.S)
    return re.sub(r"([\"'`])(?:\\.|(?!\1).)*\1", '""', code, flags=re.S)


_KIT_NAMES = frozenset(re.findall(r"\bHM\.(\w+)\s*=", (KIT / "kit.js").read_text(encoding="utf-8")))


def unknown_helpers(code: str) -> list[str]:
    """HM.<name> calls that the kit does not define: the page would die with "HM.x is not a function" in the browser."""
    return sorted({name for name in re.findall(r"\bHM\.(\w+)", _strip_strings(code)) if name not in _KIT_NAMES})


def js_syntax_error(code: str) -> str:
    """The parser's complaint about ``code`` as a function body ("" when it parses or node is unavailable): the browser check would only report it
    as an opaque lint failure after the whole scene was already built."""
    if not code.strip():
        return ""
    probe = 'let s=require("fs").readFileSync(0,"utf8");try{new Function("tl","HM","t","T","D",s)}catch(e){console.log(e.message);process.exit(1)}'
    try:
        done = subprocess.run(["node", "-e", probe], input=code, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip()[:200] if done.returncode == 1 else ""


def validate_page(page: MotionPage, *, min_scenes: int = 1) -> list[str]:
    """Human-readable problems (empty list = ready to assemble). They are sent back to the model verbatim."""
    problems: list[str] = []
    if not MIN_SECONDS <= page.duration <= MAX_SECONDS:
        problems.append(f"duration must be between {MIN_SECONDS:g} and {MAX_SECONDS:g} seconds (got {page.duration:g})")
    for name, limit in LIMITS.items():
        if len(getattr(page, name)) > limit:
            problems.append(f"{name} is too long ({len(getattr(page, name))} > {limit} characters): simplify")
    if not page.scenes_html.strip():
        return problems + ["scenes_html is empty"]
    if not page.build_js.strip():
        problems.append("build_js is empty: add every animation to tl")
    scan = _Scan()
    scan.feed(page.scenes_html)
    problems += list(dict.fromkeys(scan.problems))
    if not scan.scenes:
        problems.append('scenes_html must contain <section class="hm-scene" id="..."> layers (one per scene)')
    if len(scan.scenes) != len(set(scan.scenes)) or "" in scan.scenes:
        problems.append("every scene needs its own unique id")
    if len(scan.ids) != len(set(scan.ids)):
        problems.append("duplicate element ids: " + ", ".join(sorted({i for i in scan.ids if scan.ids.count(i) > 1})[:5]))
    if not min_scenes <= len(scan.scenes) <= 8:
        problems.append(f"use 2-6 scenes (got {len(scan.scenes)})")
    css = re.sub(r"/\*.*?\*/", " ", page.css, flags=re.S)
    for pattern, label in _FORBIDDEN_CSS:
        for match in re.finditer(pattern, css, re.I):
            if label is None:
                families = {f.strip(" '\"").lower() for f in match.group(0).split(":", 1)[1].split(",")}
                other = sorted(f for f in families if f and f not in _FONTS and f not in {"sans-serif", "serif", "monospace", "inherit"})
                if other:
                    problems.append("fonts other than Ray, Vazir and Kharazmi are not available: " + ", ".join(other[:3]))
            else:
                problems.append(f"CSS: {label} is not allowed")
                break
    sizes = [float(m.group(1)) for m in re.finditer(r"font-size\s*:\s*(\d+(?:\.\d+)?)px", css, re.I)]
    sizes += [float(m.group(1)) for m in re.finditer(r"font\s*:\s*(?:[a-z]+\s+)?\d{3}\s+(\d+(?:\.\d+)?)px", css, re.I)]
    floor = 36 if page.size[0] >= 1080 else 28
    small = sorted({int(x) for x in sizes if x < floor})
    if small:
        problems.append(f"text of {', '.join(str(x) + 'px' for x in small[:4])} is unreadable on a phone: every text must be at least {floor}px (body 44px+, headlines 110px+)")
    for field in ("build_js", "update_js"):
        code = _strip_strings(getattr(page, field))
        for pattern, label in _FORBIDDEN_JS:
            if re.search(pattern, code):
                problems.append(f"{field}: {label} is not allowed")
    for field in ("build_js", "update_js"):
        missing = unknown_helpers(getattr(page, field))
        if missing:
            problems.append(f"{field}: HM.{', HM.'.join(missing)} does not exist. HM has only: " + ", ".join(sorted(n for n in _KIT_NAMES if not n.startswith("_") and n not in {"width", "height", "duration", "colors"})) + " (anything else: use tl.* with a selector)")
        broken = js_syntax_error(getattr(page, field))
        if broken:
            problems.append(f"{field} has a JavaScript syntax error ({broken}): check brackets, quotes and commas, and write plain valid JS")
    if re.search(r"</?\s*script", page.build_js + page.update_js, re.I):
        problems.append("do not include <script> tags in build_js/update_js: they are function bodies")
    if not re.search(r"\btl\s*\.|\bHM\s*\.", _strip_strings(page.build_js)):
        problems.append("build_js never adds an animation (use tl.fromTo/tl.to or HM.rise/HM.fadeUp ...)")
    visible_text = " ".join(scan.text)
    if len(visible_text) < 6:
        problems.append("the scenes carry almost no text: write the copy inside the scenes")
    return list(dict.fromkeys(problems))


# ── assembly ─────────────────────────────────────────────────────────────────

def _fonts_css() -> str:
    from engine.hyperframes.scenes import fonts_css
    return fonts_css()


def assemble(page: MotionPage) -> str:
    """The complete HyperFrames page. The only file the renderer opens."""
    width, height = page.size
    duration = round(page.duration, 3)
    update = page.update_js.strip()
    update_block = (
        f"const __update = function (t) {{\n{update}\n}};\n"
        f"const __clock = {{ t: 0 }};\n"
        f"tl.to(__clock, {{ t: {duration}, duration: {duration}, ease: 'none', onUpdate() {{ __update(__clock.t); }} }}, 0);\n"
        f"__update(0);\n" if update else ""
    )
    return f"""<!doctype html>
<html lang="fa">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width={width}, height={height}">
<title>{escape(page.title or 'Motion graphic')}</title>
<script src="./assets/gsap.min.js"></script>
<script src="./assets/kit.js"></script>
<style>
{_fonts_css()}
{(KIT / 'kit.css').read_text()}
{page.css}
</style>
</head>
<body>
<div id="root" data-composition-id="{COMPOSITION_ID}" data-start="0" data-width="{width}" data-height="{height}" data-duration="{duration}">
<div id="stage">
{page.scenes_html}
</div>
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
HM._bind(tl, {{ duration: {duration}, width: {width}, height: {height} }});
(function build(tl) {{
{page.build_js}
}})(tl);
{update_block}window.__timelines["{COMPOSITION_ID}"] = tl;
</script>
</body>
</html>
"""


def write_project(directory: Path, page: MotionPage) -> Path:
    """index.html + local assets (GSAP, the kit, fonts). No network is needed at render time."""
    from engine.hyperframes.assets import ensure_gsap
    from engine.hyperframes.scenes import FONT_FILES
    assets = directory / "assets"
    (assets / "fonts").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ensure_gsap(), assets / "gsap.min.js")
    shutil.copy2(KIT / "kit.js", assets / "kit.js")
    for target, source in FONT_FILES.items():
        shutil.copy2(ROOT / "presets" / "fonts" / source, assets / "fonts" / target)
    (directory / "index.html").write_text(assemble(page), encoding="utf-8")
    (directory / "page.json").write_text(page.model_dump_json(indent=1), encoding="utf-8")
    return directory / "index.html"


# ── authoring ────────────────────────────────────────────────────────────────

GUIDE = """You are a senior motion designer for a Persian-first video studio. A person describes a short motion graphic in chat; you design it.
It is rendered frame by frame in a headless browser at 30 fps, so you will never see it: build it correct by construction and make it look
designed by a professional: specific to this content, layered, alive, with ONE memorable signature idea. Never a slideshow of fades.

Return ONE JSON object and nothing else:
{"questions": [], "title": "...", "summary": "...", "format": "vertical|horizontal|square", "duration": 15,
 "scenes_html": "...", "css": "...", "build_js": "...", "update_js": ""}

WHEN TO ASK: only if the request lacks something you cannot responsibly invent: the topic itself, or hard facts the clip must state (names,
prices, dates, numbers, links, offers). Then return {"questions": ["..."]} (at most 3, short, in the user's language) and leave the rest empty.
If the person answers that you should decide ("خودت انتخاب کن", "هر چی خودت صلاح می‌دونی"), do not ask again: use short generic wording and
placeholders without any invented number, price, date, address or name of a real thing. If the request gives a topic and you can write honest copy from it, do NOT ask: decide and design. Never invent statistics, prices, dates,
testimonials or claims. Use only facts in the request or in the page content provided. Defaults: vertical 1080x1920, 15-20 s.

THE PARTS
- format/duration: vertical 1080x1920 (default), horizontal 1920x1080 or square 1080x1080; 4-30 seconds. End on a held final frame (1.5 s+).
- scenes_html: 2-6 full-frame layers, in order: <section class="hm-scene" id="s1">...</section>. Later layers sit on top. The first is visible from
  the start; reveal the others with HM.wipe or your own tween. Position everything absolutely in PIXELS inside the frame (never vw/vh/%-of-window).
  Unique ids everywhere. Inline SVG for any drawing (icons, charts, diagrams, logos you invent); no <img>, <video>, <br>, <script>, <style>, forms.
- css: plain CSS for your markup. Fonts: ONLY "Ray" (Persian + Latin, weights 300/400/500/700/800/900: use extreme weight contrast),
  "Kharazmi" (Persian editorial serif, 400, one accent voice) and "Vazir" (400). Do not set transform in CSS on anything you animate; no
  @keyframes, animation, transition, @import, position:fixed, remote url().
- build_js: the BODY of function build(tl). Add EVERY animation to the paused timeline with an absolute start time as the last argument, for
  example tl.from("#title", {opacity: 0, y: 60, duration: .7}, 1.2) or HM.rise(".t1", 1.2). Do not use gsap.* directly, timers, Date,
  Math.random, window, fetch. Anything that appears later must start hidden through its own entrance tween.
- update_js (optional): the BODY of function update(t) for per-frame effects that depend only on t: typing, counters, streaming words,
  progress bars, particles from HM.random(seed). Idempotent: it may be called for any t, in any order.

KIT (global HM; build helpers add to the timeline at the given time in seconds)
- HM.rise(targets, at, {stagger, duration}) slides text up from a mask. Markup: <span class="hm-mask"><span class="hm-rise">text</span></span>;
  target the .hm-rise. HM.sink(targets, at) exits upward.
- HM.fadeUp(targets, at, {y, stagger, duration}), HM.fadeOut(targets, at), HM.pop(targets, at, {from}) scale-in with overshoot,
  HM.slide(targets, at, {x, dir:"right"|"left"}).
- HM.wipe(scene, at, {x, y, band, duration}) reveals a .hm-scene with a growing diamond from (x, y) (default: centre); band is a colour that
  leads the edge; it also hides the scenes it covers. If you reveal a scene by your own tween, call HM.hide(earlierScene, at) once covered.
  HM.draw(svgPaths, at, {duration, stagger}) strokes SVG paths drawing themselves (give them stroke, fill none). Never write el.style.strokeDasharray
  or any .style by hand: the element may not exist yet and the page crashes; tween with tl/HM and a selector string instead.
- HM.set(targets, vars, at) jumps to a state at a time (HM.set(".a", {opacity: 0}, 0)). These are ALL the HM helpers; never call another one.
- HM.words(element) wraps whole words in spans for HM.stream. Call it in build_js.
- In update_js: HM.type(el, text, start, charsPerSecond, t); HM.stream(spans, start, wordsPerSecond, t); HM.counter(el, value, start, duration, t,
  {prefix, suffix, decimals, persian}); HM.progress(barEl, percent, start, duration, t); HM.fa(n) Persian digits; HM.clamp, HM.easeOut(p),
  HM.random(seed) -> function returning 0..1.
- HM.width, HM.height are the frame size.

PERSIAN TYPOGRAPHY (breaking these breaks the text)
- Write the copy in Persian unless the person wrote in another language. Whole-word or whole-line animation only: never split a word into
  letters, never animate letters individually (it breaks the joining). Use the half-space (نیم‌فاصله) correctly and Persian digits.
- dir is rtl and text is right-aligned; wrap Latin names, URLs and numbers-with-units in dir="ltr" elements.
- Line-height at least 1.35 for Persian. Leave room: a headline of N words in a 900 px column needs about N x 110 px at 120 px type.

DESIGN
- USE THE WHOLE FRAME: spread content over the full safe area (vertical: y 220-1540); never leave the lower third or the sides empty. Fewer, larger
  elements beat many small ones. No text under 36 px anywhere (labels 40 px+, body 44 px+).
- Hook: something moves in the first 0.5 s and the subject is clear by 2 s. One idea per scene, 3-6 s each, few words, very large type
  (headlines 110-300 px, body at least 44 px on a 1080-wide frame). Vertical: keep key content between y=220 and y=1540 (apps cover the edges).
- Pick a palette of 3-5 colours from the subject, tint neutrals toward the accent, make the accent vivid. One repeated motion device (a shape,
  a transition, a type treatment); keep everything else quiet. Backgrounds are never flat: a gradient, shape, grain (SVG feTurbulence) or grid.
- Easing: power3.out entrances, power3.in exits, 0.5-0.9 s per move, staggers 0.06-0.15 s. Start the next scene's entrance before the previous ends.
  Use contrast between scale, weight and colour for hierarchy. Text must stay inside the frame and clear of other text.
- No GPU: keep blur, backdrop-filter and large shadows few and small.
- Text must keep readable contrast (WCAG large text 3:1+) against whatever is behind it at every moment, and nothing may overlap other text.
- Do not add branding for any company that is not the subject of the request.
"""

EXAMPLE = {
    "questions": [], "title": "کافه نارنج", "summary": "کلیپ ۱۰ ثانیه‌ای معرفی کافه با سه صحنه.", "format": "vertical", "duration": 10,
    "scenes_html": ('<section class="hm-scene" id="s1"><p class="lede"><span class="hm-mask"><span class="hm-rise">هر صبح، تازه برشته</span></span></p></section>'
                    '<section class="hm-scene" id="s2"><p class="big" id="beans">۰</p><p class="label"><span class="hm-mask"><span class="hm-rise">نوع دانه از شش کشور</span></span></p></section>'
                    '<section class="hm-scene" id="s3"><p class="cta"><span class="hm-mask"><span class="hm-rise">کافه نارنج</span></span></p></section>'),
    "css": ("#stage{background:#12332B;color:#FDF7F3}#s2{background:#FDF7F3;color:#12332B}#s3{background:#E8772E}"
            ".lede{position:absolute;top:760px;right:90px;left:90px;margin:0;font:900 150px/1.35 Ray}"
            ".big{position:absolute;top:520px;right:90px;left:90px;margin:0;font:900 300px/1.1 Ray;color:#B8470F}"
            ".label{position:absolute;top:900px;right:90px;left:90px;margin:0;font:800 64px/1.4 Ray}"
            ".cta{position:absolute;top:760px;right:60px;left:60px;margin:0;text-align:center;font:900 140px/1.3 Ray;color:#12332B}"),
    "build_js": ('HM.rise("#s1 .hm-rise", 0.2);\nHM.wipe("#s2", 3.2, {band: "#E8772E"});\nHM.fadeUp("#beans", 3.8);\nHM.rise("#s2 .hm-rise", 4.1);\n'
                 'HM.wipe("#s3", 6.8, {band: "#12332B", y: 1400});\nHM.rise("#s3 .hm-rise", 7.4);'),
    "update_js": 'HM.counter("#beans", 6, 3.8, 1.2, t);',
}


def build_request(brief: str, *, context: str = "", previous: MotionPage | None = None, change: str = "", brand: str = "", style: str = "") -> str:
    parts = [f"REQUEST:\n{brief.strip()}"]
    if style:
        parts.append(f"REFERENCE STYLE (keep following it):\n{style.strip()[:1800]}")
    if brand:
        parts.append(f"BRAND (use only when the request is about this brand):\n{brand.strip()}")
    if context:
        parts.append(f"PAGE CONTENT the person linked (the only source of facts besides the request):\n{context.strip()[:6000]}")
    if previous is not None:
        parts.append("CURRENT VERSION (apply the change to this and return the COMPLETE new object; keep everything not mentioned):\n"
                     + json.dumps(previous.model_dump(exclude={"questions"}), ensure_ascii=False))
        parts.append(f"CHANGE REQUESTED:\n{change.strip()}")
    parts.append("EXAMPLE of the exact shape (content invented only to show the kit):\n" + json.dumps(EXAMPLE, ensure_ascii=False))
    return "\n\n".join(parts)


def author(brief: str, *, context: str = "", previous: MotionPage | None = None, change: str = "", brand: str = "", style: str = "",
           used: list[str] | None = None, repairs: int = 2) -> MotionPage:
    """One validated page (or the questions to ask first). Rejections are fed back to the model."""
    request = build_request(brief, context=context, previous=previous, change=change, brand=brand, style=style)
    problems: list[str] = []
    for attempt in range(repairs + 1):
        user = request if not problems else request + "\n\nYour previous answer was rejected. Fix EVERY point and return the complete JSON object again:\n- " + "\n- ".join(problems[:10])
        route = DESIGNER_ROUTE if attempt == 0 else REPAIR_ROUTE
        page = llm.ask(MotionPage, GUIDE, user, route=route, tokens=12000, attempts=2, used=used)
        if page.asks():
            return page
        page.build_js, page.update_js = repair_js(page.build_js, page.duration), repair_js(page.update_js, page.duration)
        problems = validate_page(page)
        if not problems:
            return page
        log.warning("motion graphic rejected (attempt %d): %s", attempt + 1, problems[:3])
    raise CreativeUnavailable("motion graphic did not pass validation: " + "; ".join(problems[:3]))


def repair(page: MotionPage, failure: str, *, brief: str = "", used: list[str] | None = None) -> MotionPage:
    """A page that passed static validation but failed the browser checks or the render: ask for a corrected full page."""
    request = build_request(brief or page.title, previous=page, change="The renderer rejected this page. Fix exactly what it reports and change nothing else:\n" + failure[:1800])
    corrected = llm.ask(MotionPage, GUIDE, request, route=REPAIR_ROUTE, tokens=12000, attempts=2, used=used)
    corrected.build_js, corrected.update_js = repair_js(corrected.build_js, corrected.duration), repair_js(corrected.update_js, corrected.duration)
    problems = validate_page(corrected)
    if corrected.asks() or problems:
        raise CreativeUnavailable("the corrected page did not pass validation: " + "; ".join(problems[:3] or ["it asked a question"]))
    return corrected


# ── planned authoring: a plan first, then every scene on its own (in parallel) ───────────────────────────────────

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class Palette(BaseModel):
    model_config = ConfigDict(extra="ignore")
    bg: str = "#0F172A"
    surface: str = "#1E293B"
    ink: str = "#F8FAFC"
    accent: str = "#F59E0B"
    accent2: str = "#38BDF8"

    @field_validator("bg", "surface", "ink", "accent", "accent2")
    @classmethod
    def _hex(cls, value):
        text = str(value).strip()
        if not _HEX.match(text):
            raise ValueError("colours must be #RRGGBB")
        return text


class ScenePlan(BaseModel):
    model_config = ConfigDict(extra="ignore")
    headline: str                      # the exact on-screen copy of the scene's main line
    idea: str                          # what happens visually, in one or two sentences (the user's language)
    start: float
    end: float


class MotionPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")
    questions: list[str] = Field(default_factory=list)
    title: str = ""
    summary: str = ""
    format: Literal["vertical", "horizontal", "square"] = "vertical"
    duration: float = 15.0
    palette: Palette = Field(default_factory=Palette)
    signature: str = ""                # the one memorable device that repeats through the clip
    scenes: list[ScenePlan] = Field(default_factory=list)

    @field_validator("questions")
    @classmethod
    def _few(cls, value):
        return [str(q).strip() for q in value if str(q).strip()][:3]

    def asks(self) -> bool:
        return bool(self.questions) and not self.scenes


class SceneDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")
    html: str
    css: str = ""
    build_js: str
    update_js: str = ""


PLAN_GUIDE = """You are the creative director of a Persian-first motion-graphics studio. A person describes a short clip in chat. Plan it so that
scene designers can build each scene on their own. Return ONE JSON object and nothing else:
{"questions": [], "title": "...", "summary": "...", "format": "vertical|horizontal|square", "duration": 15,
 "palette": {"bg": "#RRGGBB", "surface": "#RRGGBB", "ink": "#RRGGBB", "accent": "#RRGGBB", "accent2": "#RRGGBB"},
 "signature": "...", "scenes": [{"headline": "...", "idea": "...", "start": 0, "end": 4}]}

WHEN TO ASK: only if the request lacks something you cannot responsibly invent: the topic itself, or hard facts the clip must state (names, prices,
dates, numbers, links, offers). Then return {"questions": ["..."]} (at most 3, short, in the user's language) and nothing else. If the person answers that
you should decide, use short generic wording and placeholders without any invented number, price, date, address or name of a real thing. If the
request gives a topic and you can write honest copy from it, do NOT ask. Never invent statistics, prices, dates, testimonials or claims: use only facts
in the request or in the page content provided. Defaults: vertical, 15-20 seconds.

PLAN
- 2-6 scenes that tile the whole duration without gaps (the first starts at 0, each starts where the previous ends, the last ends at duration), each
  at least 2.5 s; the last scene holds still for 1.5 s+ (name, call to action). 4-30 seconds in total.
- headline: the exact Persian words shown as that scene's main line (short: 2-7 words; whole words only). idea: what moves and how, concretely
  (a counter climbing, a diagram drawing itself, cards stacking...), specific to this content and different from the neighbours.
- palette: 3-5 colours chosen from the subject; ink must read clearly on bg (contrast 4.5:1+), accent must be vivid. signature: ONE memorable
  device that repeats (a shape, a transition, a type treatment). title: 2-5 words. summary: one or two sentences describing the clip, user's language.
- When PAGE CONTENT is provided, build the scenes from its real facts: use its exact names, platforms, benefits, numbers, offers and address, quoted as
  written; never replace them with generic claims. Leave out what the page does not state.
- Do not add branding for any company that is not the subject of the request.
"""

_SCENE_INTRO = """You are a senior motion designer. You build ONE scene of a clip that a creative director planned; other designers build the other scenes at
the same time, so stay inside your scene. It is rendered frame by frame in a headless browser (you never see it): build it correct by construction and make
it look designed by a professional. Return ONE JSON object and nothing else:
{"html": "...", "css": "...", "build_js": "...", "update_js": ""}

THE CONTRACT
- html: the INNER markup of your scene (the platform wraps it in <section class="hm-scene" id="sN"> that already has the palette background and ink colour).
  Position everything absolutely in PIXELS inside the frame. Every id you create must start with "sN-". Inline SVG for any drawing; no <img>, <video>,
  <br>, <script>, <style>, forms, remote URLs.
- css: plain CSS for your markup. EVERY selector must start with #sN (for example `#sN .hero{...}`). Fonts: ONLY "Ray" (weights 300-900), "Kharazmi" (400) and
  "Vazir" (400). No transform on elements you animate, no @keyframes, animation, transition, @import, position:fixed, remote url(). No text under 36 px.
- build_js: the BODY of build(tl). The scene is on screen from time T to T+D (given below; T and D are also defined as numeric variables in your code, so T + 0.4 works); its entrance transition (a growing diamond) is added by the
  platform, so start your content tweens at T+0.15 or later, using ABSOLUTE times (T + offset) as the last argument, and finish them by T+D-0.3. Use
  tl.fromTo/tl.from/tl.to/tl.set or the HM helpers; never gsap.* directly, timers, Date, Math.random, window, fetch. Anything that appears later must start
  hidden through its own entrance tween.
- update_js (optional): the BODY of update(t) for per-frame effects that depend only on t (counters, typing, streaming words, bars).
- Use the whole frame: the scene must look complete at every moment from T+1 s on, with nothing important in the lower third missing. No overlapping text.
"""


def _between(text: str, start: str, end: str) -> str:
    return text[text.index(start):text.index(end)]


SCENE_GUIDE = (_SCENE_INTRO + "\n" + _between(GUIDE, "KIT (global HM", "DESIGN") + "\n" + _between(GUIDE, "DESIGN", "- Do not add branding").replace("\n- Hook:", "\n- (Hook, applies to the clip) ", 1))


def validate_plan(plan: MotionPlan) -> list[str]:
    problems: list[str] = []
    if not MIN_SECONDS <= plan.duration <= MAX_SECONDS:
        problems.append(f"duration must be between {MIN_SECONDS:g} and {MAX_SECONDS:g} seconds")
    if not 2 <= len(plan.scenes) <= 6:
        problems.append(f"plan 2-6 scenes (got {len(plan.scenes)})")
        return problems
    cursor = 0.0
    for index, scene in enumerate(plan.scenes, 1):
        if abs(scene.start - cursor) > 0.15:
            problems.append(f"scene {index} must start at {cursor:g} (the previous scene's end), not {scene.start:g}")
        if scene.end - scene.start < 2.4:
            problems.append(f"scene {index} is shorter than 2.5 seconds")
        if not scene.headline.strip():
            problems.append(f"scene {index} has no headline")
        cursor = scene.end
    if abs(cursor - plan.duration) > 0.3:
        problems.append(f"the last scene must end at the duration ({plan.duration:g}), not {cursor:g}")
    return problems


def plan_request(brief: str, *, context: str = "", brand: str = "", style: str = "") -> str:
    parts = [f"REQUEST:\n{brief.strip()}"]
    if style:
        parts.append(f"REFERENCE STYLE (observed in the reference video the person gave: follow its rhythm, type treatment, colour feel, transitions and density; never copy its words):\n{style.strip()[:1800]}")
    if brand:
        parts.append(f"BRAND (use only when the request is about this brand):\n{brand.strip()}")
    if context:
        parts.append(f"PAGE CONTENT the person linked (the only source of facts besides the request):\n{context.strip()[:6000]}")
    return "\n\n".join(parts)


PLAN_ROUTE = "motion_graphic_planner"


def plan(brief: str, *, context: str = "", brand: str = "", style: str = "", used: list[str] | None = None, repairs: int = 2) -> MotionPlan:
    """The plan (or the questions to ask first). A plan that does not tile the duration is sent back with the reasons."""
    request = plan_request(brief, context=context, brand=brand, style=style)
    problems: list[str] = []
    for attempt in range(repairs + 1):
        user = request if not problems else request + "\n\nYour previous plan was rejected. Fix EVERY point and return the complete JSON again:\n- " + "\n- ".join(problems)
        result = llm.ask(MotionPlan, PLAN_GUIDE, user, route=PLAN_ROUTE, tokens=3500, attempts=2, used=used)
        if result.asks():
            return result
        problems = validate_plan(result)
        if not problems:
            return result
        log.warning("motion plan rejected (attempt %d): %s", attempt + 1, problems[:3])
    raise CreativeUnavailable("motion plan did not pass validation: " + "; ".join(problems[:3]))


def scope_css(n: int, css: str) -> str:
    """Every rule of scene N is confined to #sN: a selector that forgets the prefix gets it (a deterministic repair, not another model call)."""
    prefix = f"#s{n}"

    def rule(match):
        parts = []
        for raw in match.group(1).split(","):
            selector = raw.strip()
            if not selector:
                continue
            parts.append(selector if selector.startswith(prefix) else f"{prefix} {selector}")
        return ",".join(parts) + "{" + match.group(2) + "}"

    return re.sub(r"([^{}]+)\{([^{}]*)\}", rule, re.sub(r"/\*.*?\*/", " ", css, flags=re.S))


def _scene_page(n: int, draft: SceneDraft, plan: MotionPlan) -> MotionPage:
    return MotionPage(title=plan.title, format=plan.format, duration=plan.duration,
                      scenes_html=f'<section class="hm-scene" id="s{n}">{draft.html}</section>', css=scope_css(n, draft.css),
                      build_js=draft.build_js, update_js=draft.update_js)


def scene_request(plan: MotionPlan, n: int, brief: str, context: str = "", style: str = "") -> str:
    scene = plan.scenes[n - 1]
    outline = [{"scene": i, "headline": sc.headline, "idea": sc.idea, "from": sc.start, "to": sc.end} for i, sc in enumerate(plan.scenes, 1)]
    parts = [f"YOU BUILD SCENE s{n} (N = {n}). T = {scene.start:g}, D = {round(scene.end - scene.start, 2):g} (it is on screen from {scene.start:g} s to {scene.end:g} s).",
             f"THIS SCENE\nheadline (exact words, Persian): {scene.headline}\nidea: {scene.idea}",
             f"THE WHOLE CLIP (for rhythm and coherence; do not build the other scenes)\ntitle: {plan.title}; format {plan.format} {FORMATS[plan.format][0]}x{FORMATS[plan.format][1]}; "
             f"{plan.duration:g} s; palette {plan.palette.model_dump_json()}; signature device: {plan.signature or 'none'}\n" + json.dumps(outline, ensure_ascii=False),
             f"ORIGINAL REQUEST:\n{brief.strip()[:1500]}"]
    if context:
        parts.append("FACTS you may use (the only ones besides the request):\n" + context.strip()[:5000])
    if style:
        parts.append("REFERENCE STYLE to echo (rhythm, type treatment, transitions, density):\n" + style.strip()[:900])
    parts.append("Palette background and ink are already applied to #s%d; use accent colours for emphasis." % n)
    return "\n\n".join(parts)


SCENE_ROUTE = "motion_graphic_designer"
SCENE_ATTEMPTS = 3          # the first answer and two corrections

_EXPLAIN = (
    (r"unreadable on a phone", "متن خیلی کوچک است (زیر ۳۶ پیکسل)"), (r"must start with s\d+-", "شناسه‌ها با پیشوند صحنه شروع نمی‌شوند"),
    (r"CSS transition|CSS animation|@keyframes", "از transition/انیمیشن CSS استفاده کرده که مجاز نیست"), (r"timers|requestAnimationFrame", "از تایمر استفاده کرده که مجاز نیست"),
    (r"Math\.random", "از Math.random استفاده کرده"), (r"gsap\.\*", "مستقیم از gsap استفاده کرده به‌جای timeline"), (r"network access|fetch", "درخواست شبکه داشته"),
    (r"fonts other than", "فونت غیرمجاز"), (r"viewport units", "واحد vw/vh استفاده شده"), (r"<img>|<br>|<script>|<style>|is not allowed in scenes_html", "تگ غیرمجاز در صحنه"),
    (r"outside the page", "لینک یا منبع بیرونی"), (r"event attribute", "ویژگی رویداد (onclick…) غیرمجاز"), (r"duplicate element ids", "شناسه‌های تکراری"),
    (r"never adds an animation", "هیچ انیمیشنی اضافه نکرده"), (r"almost no text", "صحنه تقریباً متنی ندارد"), (r"splitting text into letters", "متن را به حروف تقسیم کرده"),
    (r"window|globalThis", "استفاده از window"), (r"innerHTML|outerHTML", "تزریق markup از JS"), (r"duration", "مدت نامعتبر"),
    (r"gsap_css_transform_conflict", "تداخل transform در CSS و انیمیشن"), (r"font_family_without_font_face", "فونت بدون تعریف"), (r"text_box_overflow|container_overflow", "متن از کادرش بیرون زده"),
    (r"contrast", "کنتراست متن کم است"), (r"content_overlap|text_occluded", "متن‌ها روی هم افتاده‌اند"),
)


def _close(code: str, open_at: int) -> tuple[int, int]:
    """Index of the parenthesis closing the one at ``open_at`` and the number of top-level arguments, skipping strings; (-1, 0) when unbalanced."""
    depth, args, i, quote = 0, 1, open_at, ""
    while i < len(code):
        ch = code[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in "\"'`":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                return i, args
        elif ch == "," and depth == 1:
            args += 1
        i += 1
    return -1, 0


_ARGS = {"to": 2, "from": 2, "set": 2, "fromTo": 3}


def repair_js(code: str, duration: float) -> str:
    """Rewrite the two mistakes models keep making instead of rejecting a scene for them: gsap.to/from/fromTo/set(...) outside the timeline becomes
    tl.to(..., 0) (it would start at time 0 anyway), and repeat:-1 becomes the finite count that covers the clip. Anything else is left for the validator."""
    position = 0
    while True:
        found = re.compile(r"\bgsap\.(to|from|fromTo|set)\s*\(").search(code, position)
        if not found:
            break
        end, args = _close(code, found.end() - 1)
        if end < 0 or args != _ARGS[found[1]]:
            position = found.end()                                   # not a shape we can move safely
            continue
        code = code[:found.start()] + f"tl.{found[1]}" + code[found.end() - 1:end] + ", 0)" + code[end + 1:]
        position = found.start() + 3

    def finite(match: re.Match) -> str:
        left, right = code.rfind("{", 0, match.start()), code.find("}", match.end())
        span = code[left if left >= 0 else 0:right if right >= 0 else len(code)]
        each = re.search(r"\bduration\s*:\s*(\d+(?:\.\d+)?)", span)
        length = float(each[1]) if each and float(each[1]) > 0 else 1.0
        return f"repeat: {min(60, max(1, int(duration / length + 1)))}"
    return re.sub(r"\brepeat\s*:\s*-1\b", finite, code)


def explain_problem(text: str) -> str:
    """A validator or check message as one short Persian phrase for the person watching (the technical text is a fallback)."""
    for pattern, phrase in _EXPLAIN:
        if re.search(pattern, text, re.I):
            return phrase
    return text.strip()[:90]


def author_scene(plan: MotionPlan, n: int, brief: str, *, context: str = "", used: list[str] | None = None, repairs: int = SCENE_ATTEMPTS - 1,
                 feedback: list[str] | None = None, on_retry=None, style: str = "") -> SceneDraft:
    """One validated scene. Rejections are fed back to the model (``on_retry(next_attempt, problems)`` tells the caller); ``feedback`` starts the
    conversation with problems an earlier check found in this scene. The caller falls back to a plain scene when this raises."""
    request = scene_request(plan, n, brief, context, style)
    guide = SCENE_GUIDE.replace("sN", f"s{n}")
    problems: list[str] = list(feedback or [])
    for attempt in range(repairs + 1):
        user = request if not problems else request + "\n\nYour previous answer was rejected. Fix EVERY point and return the complete JSON again:\n- " + "\n- ".join(problems[:8])
        draft = llm.ask(SceneDraft, guide, user, route=SCENE_ROUTE if attempt == 0 else REPAIR_ROUTE, tokens=7000, attempts=2, used=used)
        draft.build_js, draft.update_js = repair_js(draft.build_js, plan.duration), repair_js(draft.update_js, plan.duration)
        problems = validate_page(_scene_page(n, draft, plan))
        problems += [f"every id must start with s{n}-: {i}" for i in dict.fromkeys(re.findall(r'\bid="(?!s%d-)([^"]+)"' % n, draft.html))][:3]
        if not problems:
            return draft
        log.warning("scene %d rejected (attempt %d): %s", n, attempt + 1, problems[:3])
        if on_retry and attempt < repairs:
            on_retry(attempt + 2, problems)
    raise CreativeUnavailable(f"scene {n} did not pass validation: " + "; ".join(problems[:3]))


def fallback_scene(plan: MotionPlan, n: int) -> SceneDraft:
    """A plain, always-valid scene for the planned headline: used when a designer's scene could not be validated."""
    scene = plan.scenes[n - 1]
    accent = plan.palette.accent
    width, height = FORMATS[plan.format]
    size = 150 if width >= 1080 and height > width else 120
    return SceneDraft(
        html=f'<div class="s{n}-bar"></div><p class="s{n}-head"><span class="hm-mask"><span class="hm-rise">{escape(scene.headline)}</span></span></p>',
        css=(f"#s{n} .s{n}-bar{{position:absolute;right:{int(width*.08)}px;top:{int(height*.4)}px;width:160px;height:14px;background:{accent}}}"
             f"#s{n} .s{n}-head{{position:absolute;right:{int(width*.08)}px;left:{int(width*.08)}px;top:{int(height*.4)+50}px;margin:0;font:900 {size}px/1.4 Ray}}"),
        build_js=f'HM.fadeUp("#s{n} .s{n}-bar", {scene.start + 0.15:g});\nHM.rise("#s{n} .hm-rise", {scene.start + 0.35:g});')


def assemble_scenes(plan: MotionPlan, drafts: list[SceneDraft]) -> MotionPage:
    """The clip: every scene in its own layer, entrance wipes added here, each scene's code isolated in its own function."""
    width, height = FORMATS[plan.format]
    palette = plan.palette
    html, css, build, update = [], [], [], []
    corners = [(width / 2, height / 2), (width * .85, height * .75), (width * .15, height * .25), (width / 2, height * .9), (width * .85, height * .2), (width * .2, height * .8)]
    for n, (scene, draft) in enumerate(zip(plan.scenes, drafts), 1):
        html.append(f'<section class="hm-scene" id="s{n}">{draft.html}</section>')
        css.append(f"#s{n}{{background:{palette.bg};color:{palette.ink}}}\n{scope_css(n, draft.css)}")
        if n > 1:
            x, y = corners[(n - 1) % len(corners)]
            build.append(f'HM.wipe("#s{n}", {max(0.0, scene.start - 0.9):g}, {{band: "{palette.accent}", x: {int(x)}, y: {int(y)}}});')
        # T and D (the scene's start and length) are real variables in its code: the designer's prompt names them, and a scene that writes T + 0.5
        # must not crash the page with "T is not defined".
        span = f"{scene.start:g}, {round(scene.end - scene.start, 3):g}"
        build.append(f"(function (T, D) {{\n{draft.build_js}\n}})({span});")
        if draft.update_js.strip():
            update.append(f"(function (t, T, D) {{\n{draft.update_js}\n}})(t, {span});")
    return MotionPage(title=plan.title, summary=plan.summary, format=plan.format, duration=plan.duration,
                      scenes_html="\n".join(html), css="\n".join(css), build_js="\n".join(build), update_js="\n".join(update))
