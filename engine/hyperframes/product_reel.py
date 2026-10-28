"""The directed product reel as a HyperFrames page: the cinematic look of the Remotion composition, rendered by the HyperFrames engine.

Deterministic: no model writes any of this. Every word on screen is the scene's own overlay or narration text; the page is plain
HTML + one paused GSAP timeline, narration and music are <audio> tracks the engine mixes. Needs no network at render time.
"""
from __future__ import annotations

import json
import random
import re
import shutil
import subprocess
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSITION_ID = "reel"
FPS = 30
OVERLAP_S = 9 / FPS                 # the next scene wipes in over the previous one
WIDTH, HEIGHT = 1080, 1920

# Camera moves, one per scene in rotation (the same photo reads as different shots): scale, x, y, rotation  (start -> end)
CAMERAS = [
    {"s": (1.02, 1.22), "x": (0, 0), "y": (0, -18), "r": (0, 0)},
    {"s": (1.7, 1.95), "x": (70, -50), "y": (30, -10), "r": (-1.2, .6)},
    {"s": (1.32, 1.32), "x": (-120, 90), "y": (0, 0), "r": (0, 0)},
    {"s": (1.5, 1.08), "x": (0, 0), "y": (-40, 10), "r": (1.2, 0)},
    {"s": (2.15, 2.4), "x": (-40, 60), "y": (60, 20), "r": (.8, -.6)},
    {"s": (1.12, 1.28), "x": (60, -60), "y": (20, -20), "r": (-.8, .8)},
]
CUTOUT_MAX_SCALE = 1.45             # a cut-out has a hard outline: keep it inside the frame
PAGE_WORDS = 4


def _shade(color: str, amount: float) -> str:
    value = int(color.lstrip("#"), 16)
    parts = [max(0, min(255, round(c * amount))) for c in ((value >> 16) & 255, (value >> 8) & 255, value & 255)]
    return "rgb(%d,%d,%d)" % tuple(parts)


def _accent(value: str | None) -> str:
    return value if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value) else "#d9b36c"


def _fmt(x: float) -> str:
    return f"{x:.3f}".rstrip("0").rstrip(".") or "0"


def word_times(text: str, start: float, end: float) -> list[tuple[str, float]]:
    """Each word of the narration with the time it appears: spread over the scene by word length (the voice is not aligned word by word)."""
    words = text.split()
    if not words:
        return []
    weights = [max(2, len(w)) + 1 for w in words]
    total = sum(weights)
    span = max(.3, end - start)
    out, at = [], start
    for word, weight in zip(words, weights):
        out.append((word, at))
        at += span * weight / total
    return out


def _scene_html(i: int, scene: dict, start: float, dur: float, lead: float, count: int, rng: random.Random) -> tuple[str, list[str]]:
    accent = _accent(scene.get("accent"))
    cutout = scene.get("kind") == "cutout"
    sid = f"s{i}"
    js: list[str] = []
    t0 = start - lead
    total = dur + lead
    cam = CAMERAS[(i * 2 + (1 if scene.get("visual_type") == "spec_callout" else 0)) % len(CAMERAS)]
    s0, s1 = cam["s"]
    if cutout:
        s0, s1 = min(s0, CUTOUT_MAX_SCALE), min(s1, CUTOUT_MAX_SCALE)

    title = str(scene.get("title") or "")
    head_words = title.split()
    head_size = 78 if len(title) > 26 else 104
    head = "".join(f'<span class="hw">{escape(w)}</span>' for w in head_words)

    sparkles = []
    for k in range(6):
        x, y, size = rng.random() * 1000 + 40, rng.random() * 820 + 250, 9 + rng.random() * 11
        sparkles.append(f'<i class="sp" id="{sid}k{k}" style="left:{x:.0f}px;top:{y:.0f}px;width:{size:.0f}px;height:{size:.0f}px;box-shadow:0 0 {size * 2:.0f}px {size * .8:.0f}px {accent}"></i>')
        delay = rng.random() * 1.6
        cycle = .45 + rng.random() * .3
        repeats = max(0, int((dur - delay - 1) / (cycle + .5)))
        js.append(f'tl.fromTo("#{sid}k{k}",{{opacity:0,scale:.3,rotation:{k * 20}}},{{opacity:.95,scale:1.15,rotation:{k * 20 + 70},duration:{_fmt(cycle)},'
                  f'ease:"sine.inOut",yoyo:true,repeat:{min(repeats, 3) * 2 + 1},repeatDelay:{_fmt(.1 + rng.random() * .4)}}},{_fmt(start + delay)});')

    # Captions: pages of four words; the word being said takes the accent colour.
    timed = word_times(str(scene.get("narration_text") or ""), start + .2, start + dur - .35)
    pages = [timed[p:p + PAGE_WORDS] for p in range(0, len(timed), PAGE_WORDS)]
    caps = []
    for p, page in enumerate(pages):
        words = "".join(f'<span class="cw" id="{sid}c{p}w{q}">{escape(w)}</span>' for q, (w, _) in enumerate(page))
        caps.append(f'<div class="cpage" id="{sid}c{p}">{words}</div>')
        first = page[0][1]
        last = pages[p + 1][0][1] if p + 1 < len(pages) else start + dur
        js.append(f'tl.set("#{sid}c{p}",{{opacity:1}},{_fmt(first)});')
        js.append(f'tl.set("#{sid}c{p}",{{opacity:0}},{_fmt(last)});')
        for q, (_, at) in enumerate(page):
            nxt = page[q + 1][1] if q + 1 < len(page) else min(last, at + .5)
            js.append(f'tl.fromTo("#{sid}c{p}w{q}",{{opacity:0,scale:.6,y:18,color:"#ffffff"}},{{opacity:1,scale:1.16,y:0,color:"{accent}",duration:.18,ease:"back.out(2)"}},{_fmt(at)});')
            js.append(f'tl.to("#{sid}c{p}w{q}",{{scale:1,color:"#ffffff",duration:.15}},{_fmt(nxt)});')

    ticks = "".join(
        f'<div class="tk"><div class="tkf" id="{sid}t{n}" style="width:{100 if n < i else 0}%"></div></div>' for n in range(count))

    html = f"""<section id="{sid}" class="clip scene" data-start="{_fmt(t0)}" data-duration="{_fmt(total)}">
<div class="wp" id="{sid}wp">
<div class="bg" style="background:radial-gradient(120% 70% at 50% 40%,{_shade(accent, .42)} 0%,{_shade(accent, .14)} 48%,#07050a 100%)"></div>
<div class="glow" id="{sid}gl" style="background:radial-gradient(circle,{accent}66 0%,{accent}22 38%,transparent 66%)"></div>
<div class="stage"><div class="pw" id="{sid}pw"><img class="pr{' cut' if cutout else ''}" id="{sid}pr" src="assets/p{i}{escape(Path(scene['asset']).suffix, quote=True)}"></div></div>
{''.join(sparkles)}
<div class="vs"></div>
<div class="head" id="{sid}hd" style="font-size:{head_size}px">{head}</div>
<div class="bar" id="{sid}br" style="background:{accent};box-shadow:0 0 22px {accent};top:{236 if len(title) > 26 else 262}px"></div>
{''.join(caps)}
<div class="ticks">{ticks}</div>
{'<div class="cta" id="' + sid + 'cta" style="background:' + accent + ';box-shadow:0 0 30px ' + accent + '"></div>' if i == count - 1 else ''}
</div>
<div class="flash" id="{sid}fl"></div>
<div class="edge" id="{sid}eg" style="background:{accent};box-shadow:0 0 60px 10px {accent}"></div>
</section>"""

    # --- timeline for this scene ---
    if i > 0:
        js.append(f'tl.fromTo("#{sid}wp",{{clipPath:"inset(0% 0% 0% 100%)"}},{{clipPath:"inset(0% 0% 0% 0%)",duration:{_fmt(lead)},ease:"power3.out"}},{_fmt(t0)});')
        js.append(f'tl.fromTo("#{sid}eg",{{x:{WIDTH},opacity:.9}},{{x:0,opacity:0,duration:{_fmt(lead)},ease:"power3.out"}},{_fmt(t0)});')
        js.append(f'tl.fromTo("#{sid}fl",{{opacity:0}},{{opacity:.35,duration:{_fmt(lead / 3)},yoyo:true,repeat:1,ease:"none"}},{_fmt(t0)});')
    js.append(f'tl.fromTo("#{sid}pr",{{scale:{s0},x:{cam["x"][0]},y:{cam["y"][0]},rotation:{cam["r"][0]}}},'
              f'{{scale:{s1},x:{cam["x"][1]},y:{cam["y"][1]},rotation:{cam["r"][1]},duration:{_fmt(total)},ease:"sine.inOut"}},{_fmt(t0)});')
    js.append(f'tl.fromTo("#{sid}pw",{{opacity:0,scale:.9}},{{opacity:1,scale:1,duration:.6,ease:"power3.out"}},{_fmt(start)});')
    js.append(f'tl.fromTo("#{sid}gl",{{scale:.92}},{{scale:1.12,duration:{_fmt(total)},ease:"sine.inOut"}},{_fmt(t0)});')
    if head_words:
        js.append(f'tl.from("#{sid}hd .hw",{{opacity:0,y:-46,scale:.85,duration:.5,ease:"back.out(1.7)",stagger:.13}},{_fmt(start + .05)});')
    js.append(f'tl.from("#{sid}br",{{scaleX:0,duration:.5,ease:"power3.out"}},{_fmt(start + .1)});')
    js.append(f'tl.fromTo("#{sid}t{i}",{{width:"0%"}},{{width:"100%",duration:{_fmt(dur)},ease:"none"}},{_fmt(start)});')
    if i == count - 1:
        js.append(f'tl.fromTo("#{sid}cta",{{scaleX:1.4}},{{scaleX:2.6,duration:.45,ease:"sine.inOut",yoyo:true,repeat:{max(1, int(dur / .45) // 2 * 2 - 1)}}},{_fmt(start + .3)});')
    return html, js


CSS = """
html,body{margin:0;background:#08060b}
#root{position:relative;width:100%;height:100%;overflow:hidden;background:#08060b;font-family:Ray,Vazir,sans-serif;direction:rtl}
.scene{position:absolute;inset:0;overflow:hidden}
.wp{position:absolute;inset:0;overflow:hidden}
.bg,.vs{position:absolute;inset:0}
.vs{background:linear-gradient(180deg,#000b 0%,transparent 22%,transparent 52%,#000c 100%),radial-gradient(90% 60% at 50% 45%,transparent 45%,#000a 100%)}
.glow{position:absolute;left:-110px;top:140px;width:1300px;height:1300px;border-radius:50%}
.stage{position:absolute;left:0;top:245px;width:1080px;height:1080px}
.pw{position:absolute;left:0;top:0;width:1080px;height:1080px}
.pr{position:absolute;left:0;top:0;width:1080px;height:1080px;object-fit:contain;-webkit-mask-image:radial-gradient(circle at 50% 50%,#000 50%,transparent 74%);mask-image:radial-gradient(circle at 50% 50%,#000 50%,transparent 74%)}
.pr.cut{-webkit-mask-image:none;mask-image:none}
.sp{position:absolute;opacity:0;border-radius:50%;background:#fff}
.head{position:absolute;left:60px;right:60px;top:104px;display:flex;flex-wrap:wrap;justify-content:center;gap:0 20px;font-weight:900;line-height:1.3;color:#fff;text-shadow:0 8px 28px #000c}
.hw{display:inline-block}
.bar{position:absolute;left:430px;width:220px;height:7px;border-radius:7px}
.cpage{position:absolute;left:56px;right:56px;bottom:250px;opacity:0;display:flex;flex-wrap:wrap;justify-content:center;gap:6px 22px;font-weight:900;font-size:92px;line-height:1.32;text-align:center;color:#fff}
.cw{display:inline-block;color:#fff;text-shadow:0 4px 18px #000d,0 0 3px #000d}
.ticks{position:absolute;left:60px;right:60px;top:48px;display:flex;gap:8px;direction:ltr}
.tk{flex:1;height:6px;border-radius:6px;background:#ffffff30;overflow:hidden}
.tkf{height:100%;background:#fff}
.cta{position:absolute;left:470px;bottom:96px;width:140px;height:14px;border-radius:14px}
.flash{position:absolute;inset:0;background:#fff;opacity:0;pointer-events:none}
.edge{position:absolute;top:0;bottom:0;left:0;width:18px;opacity:0;pointer-events:none}
"""


def _fit_music(source: Path, target: Path, seconds: float) -> None:
    """The bed loops for the whole reel (the engine plays an audio file once)."""
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-stream_loop", "-1", "-i", str(source), "-t", f"{seconds:.3f}", "-c:a", "libmp3lame", "-b:a", "128k", str(target)],
                   check=True, capture_output=True, timeout=120)


def build_project(directory: Path, config: dict, *, job_dir: Path | None = None) -> Path:
    """Write index.html and its local assets into *directory*. *config* is the Remotion scene config after engine.remotion_renderer._enrich:
    absolute asset / narration paths, kind, accent, title, narration_text and frames per scene."""
    from engine.motion_contract import validate_motion_config
    config = validate_motion_config(config, job_dir or directory.parent)
    from engine.hyperframes.assets import ensure_gsap
    from engine.hyperframes.fonts import FONT_FILES, fonts_css
    scenes = config["scenes"]
    assets = directory / "assets"
    (assets / "fonts").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ensure_gsap(), assets / "gsap.min.js")
    for target, source in FONT_FILES.items():
        shutil.copy2(ROOT / "presets" / "fonts" / source, assets / "fonts" / target)

    starts, cursor = [], 0.0
    for scene in scenes:
        starts.append(cursor)
        cursor += scene["frames"] / FPS
    total = round(cursor, 3)

    parts, js, audio = [], [], []
    for i, scene in enumerate(scenes):
        source = Path(scene["asset"])
        shutil.copy2(source, assets / f"p{i}{source.suffix}")
        dur = scene["frames"] / FPS
        lead = 0.0 if i == 0 else OVERLAP_S
        html, code = _scene_html(i, scene, starts[i], dur, lead, len(scenes), random.Random(f"{source.name}{i}"))
        parts.append(html)
        js.extend(code)
        if scene.get("narration"):
            voice = Path(scene["narration"])
            shutil.copy2(voice, assets / f"vo{i}{voice.suffix}")
            audio.append(f'<audio id="vo{i}" src="assets/vo{i}{escape(voice.suffix, quote=True)}" data-start="{_fmt(starts[i])}" data-duration="{_fmt(dur)}" data-track-index="1"></audio>')
    if config.get("music"):
        _fit_music(Path(config["music"]), assets / "music.mp3", total)
        audio.append(f'<audio id="music" src="assets/music.mp3" data-start="0" data-duration="{_fmt(total)}" data-track-index="2" data-volume="0.1"></audio>')

    page = f"""<!doctype html>
<html lang="fa">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width={WIDTH}, height={HEIGHT}">
<title>Product reel</title>
<script src="./assets/gsap.min.js"></script>
<style>
{fonts_css()}
{CSS}
</style>
</head>
<body>
<div id="root" data-composition-id="{COMPOSITION_ID}" data-start="0" data-width="{WIDTH}" data-height="{HEIGHT}" data-duration="{_fmt(total)}">
{chr(10).join(parts)}
{chr(10).join(audio)}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
{chr(10).join(js)}
window.__timelines = window.__timelines || {{}};
window.__timelines["{COMPOSITION_ID}"] = tl;
</script>
</body>
</html>
"""
    (directory / "index.html").write_text(page, encoding="utf-8")
    (directory / "reel.json").write_text(json.dumps({"scenes": len(scenes), "duration": total}), encoding="utf-8")
    return directory / "index.html"


def _run_cli(project: Path, output: Path, *, timeout: int, on_progress=None, should_cancel=None) -> None:
    """hyperframes render with live progress: the CLI prints "@hf-progress {...done,total...}" while it captures frames."""
    import os
    import re
    import signal
    import threading
    import time
    from collections import deque
    from engine.hyperframes.cli import cli_command
    from engine.hyperframes.renderer import HyperFramesError, summarize_failure
    from engine.hyperframes.standalone import ensure_browser
    ensure_browser()
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [*cli_command(), "render", ".", "--output", str(output.resolve()), "--quality", "standard", "--workers", "1", "--fps", "30", "--sdr"]
    process = subprocess.Popen(command, cwd=project, env={**os.environ, "NO_COLOR": "1"}, text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, start_new_session=True)
    tail: deque[str] = deque(maxlen=60)
    state = {"pct": -1}

    def pump() -> None:
        for line in process.stdout:
            tail.append(line)
            found = re.search(r'@hf-progress \{"code":"capture","done":(\d+),"total":(\d+)', line)
            if found and on_progress:
                pct = min(95, int(int(found.group(1)) * 95 / max(1, int(found.group(2)))))
                if pct != state["pct"]:
                    state["pct"] = pct
                    on_progress(pct)

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    started = time.monotonic()
    while process.poll() is None:
        time.sleep(2)
        if (should_cancel and should_cancel()) or time.monotonic() - started > timeout:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
            raise HyperFramesError("HyperFrames render canceled" if should_cancel and should_cancel() else f"HyperFrames render timed out after {timeout} seconds")
    reader.join(timeout=5)
    if process.returncode or not output.is_file():
        raise HyperFramesError("HyperFrames render failed: " + summarize_failure("".join(tail)[-2400:]))


def render(config: dict, output: Path, *, job_dir: Path, on_progress=None, should_cancel=None, timeout: int = 5400) -> Path:
    from engine.motion_contract import validate_motion_config
    config = validate_motion_config(config, job_dir)
    project = job_dir / "hyperframes_reel"
    if project.exists():
        shutil.rmtree(project)
    project.mkdir(parents=True)
    build_project(project, config, job_dir=job_dir)
    _run_cli(project, output, timeout=timeout, on_progress=on_progress, should_cancel=should_cancel)
    shutil.rmtree(project, ignore_errors=True)         # the page and its copied assets are rebuilt on every render
    return output
