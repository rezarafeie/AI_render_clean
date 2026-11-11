"""The graphics layer of a talking reel as one transparent HyperFrames page: panels, captions, the hook and key-moment slams.

The speaker video is edited and composited by ffmpeg (engine/talking_styles/talking_5.py); this page is drawn over it with alpha.
Everything is deterministic HTML + one paused GSAP timeline from (pack, script): no model writes markup here. Whole words only
(never per-letter animation: it breaks Persian joining). No network at render time.
"""
from __future__ import annotations

import json
import re
import shutil
from html import escape
from pathlib import Path

from creative.style_packs import StylePack

ROOT = Path(__file__).resolve().parents[2]
COMPOSITION_ID = "overlay"
W, H = 1080, 1920
SPLIT_Y = 888                   # the panel ends here (the Motion Designer's 1080x888 panel contract), the speaker card starts here
CAPTION_Y_SPLIT = 905           # caption line centre over a split shot


def _f(x: float) -> str:
    return f"{x:.3f}".rstrip("0").rstrip(".") or "0"


def _num_in(text: str) -> str | None:
    found = re.search(r"[0-9۰-۹][0-9۰-۹,٬.٪%]*", text or "")
    return found.group(0) if found else None


# ── panel scenes (top area during a split shot) ──────────────────────────────────────────────────────────────────────

def _title_html(title: str, pack: StylePack, *, size: int = 92) -> str:
    """The panel headline: the last word in the accent voice (calligraphic in Persian), the rest heavy."""
    words = title.split()
    if not words:
        return ""
    head, tail = words[:-1], words[-1]
    parts = [f'<span class="tw">{escape(w)}</span>' for w in head]
    parts.append(f'<span class="tw acc">{escape(tail)}</span>')
    return f'<div class="ptitle" style="font-size:{size}px">{" ".join(parts)}</div>'


def _panel(index: int, beat: dict, pack: StylePack, start: float, end: float) -> tuple[str, list[str]]:
    """(html, js) of one panel scene. beat: {title, items[], visual_type}."""
    pid = f"p{index}"
    title = str(beat.get("title") or "")
    items = [str(i) for i in (beat.get("items") or []) if str(i).strip()][:4]
    vtype = str(beat.get("visual_type") or "concept")
    js: list[str] = []
    body = ""
    kind = "stack"
    if vtype in {"comparison", "before_after"} and len(items) >= 2:
        kind = "versus"
    elif vtype == "stat" or (not items and _num_in(title)):
        kind = "stat"
    elif vtype == "kinetic_type" or not items:
        kind = "kinetic"
    elif vtype == "steps":
        kind = "steps"

    if kind == "stack":
        gap = 22
        avail = 500                                         # the stack lives between the title and the caption line
        h = int(min(150, (avail - (len(items) - 1) * gap) / max(1, len(items))))
        fs = 58 if h >= 130 else 48 if h >= 105 else 40
        badge = max(52, int(h * .56))
        cards = "".join(
            f'<div class="ci{" last" if n == len(items) - 1 else ""}" id="{pid}i{n}" style="height:{h}px;font-size:{fs}px">'
            f'<b style="width:{badge}px;height:{badge}px;font-size:{int(badge * .55)}px">{n + 1}</b><span>{escape(t)}</span></div>' for n, t in enumerate(items))
        body = f'{_title_html(title, pack, size=74)}<div class="stack" style="gap:{gap}px">{cards}</div>'
        js.append(f'tl.from("#{pid} .ptitle .tw",{{opacity:0,y:-40,duration:.45,stagger:.1,ease:"back.out(1.6)"}},{_f(start + .05)});')
        js.append(f'tl.from("#{pid} .ci",{{opacity:0,y:90,scale:.92,duration:.5,stagger:.22,ease:"power3.out"}},{_f(start + .35)});')
    elif kind == "versus":
        a, b = items[0], items[1]
        body = (f'{_title_html(title, pack, size=70)}<div class="versus"><div class="vc" id="{pid}a"><span>{escape(a)}</span></div>'
                f'<div class="vs" id="{pid}v">در برابر</div><div class="vc dk" id="{pid}b"><span>{escape(b)}</span></div></div>')
        js.append(f'tl.from("#{pid} .ptitle .tw",{{opacity:0,y:-40,duration:.45,stagger:.1,ease:"back.out(1.6)"}},{_f(start + .05)});')
        js.append(f'tl.from("#{pid}a",{{opacity:0,x:-160,duration:.55,ease:"power3.out"}},{_f(start + .35)});')
        js.append(f'tl.from("#{pid}b",{{opacity:0,x:160,duration:.55,ease:"power3.out"}},{_f(start + .5)});')
        js.append(f'tl.from("#{pid}v",{{opacity:0,scale:.3,rotation:-30,duration:.5,ease:"back.out(2.4)"}},{_f(start + .85)});')
    elif kind == "stat":
        number = _num_in(title) or ""
        label = title.replace(number, "").strip(" :-–—") if number else title
        body = (f'<div class="bignum" id="{pid}n">{escape(number)}</div><div class="plabel" id="{pid}l">{escape(label)}</div>')
        js.append(f'tl.from("#{pid}n",{{opacity:0,scale:.4,duration:.6,ease:"back.out(2)"}},{_f(start + .1)});')
        js.append(f'tl.from("#{pid}l",{{opacity:0,y:50,duration:.5,ease:"power3.out"}},{_f(start + .55)});')
    elif kind == "steps":
        chips = "".join(f'<div class="step" id="{pid}s{n}"><b>{n + 1}</b><span>{escape(t)}</span></div>' for n, t in enumerate(items))
        body = f'{_title_html(title, pack, size=74)}<div class="steps">{chips}</div>'
        js.append(f'tl.from("#{pid} .ptitle .tw",{{opacity:0,y:-40,duration:.45,stagger:.1,ease:"back.out(1.6)"}},{_f(start + .05)});')
        js.append(f'tl.from("#{pid} .step",{{opacity:0,x:140,duration:.5,stagger:.25,ease:"power3.out"}},{_f(start + .4)});')
    else:  # kinetic: the title as a few giant words
        words = title.split() or [""]
        spans = "".join(f'<span class="kw{" acc" if n == len(words) - 1 else ""}" id="{pid}w{n}">{escape(w)}</span>' for n, w in enumerate(words))
        body = f'<div class="kin">{spans}</div>'
        js.append(f'tl.from("#{pid} .kw",{{opacity:0,y:120,scale:.6,duration:.5,stagger:.16,ease:"back.out(1.8)"}},{_f(start + .1)});')

    html = (f'<section id="{pid}" class="clip panel {pack.panel_theme}" data-start="{_f(start)}" data-duration="{_f(end - start)}">'
            f'<div class="frame"></div>{body}</section>')
    return html, js


def _component_panel(index: int, name: str, values: dict, pack: StylePack, start: float, end: float, zoom: float = 1.0) -> tuple[str, list[str]]:
    """A panel scene made by a vendored HyperFrames registry component: background and frame here, the motion from the library."""
    import json as _json
    pid = f"p{index}"
    attr = _json.dumps(values, ensure_ascii=False).replace("&", "&amp;").replace("'", "&#39;")
    html = (f'<section id="{pid}" class="clip panel {pack.panel_theme}" data-start="{_f(start)}" data-duration="{_f(end - start)}"></section>'
            f'<div id="{pid}h" data-composition-id="{name}" data-composition-src="compositions/components/{name}.html" data-start="{_f(start)}" '
            f'data-duration="{_f(end - start)}" data-track-index="3" data-width="{int(968 / zoom)}" data-height="{int(888 / zoom)}" data-variable-values=\'{attr}\' '
            f'style="position:absolute;left:56px;top:56px;width:{int(968 / zoom)}px;height:{int(888 / zoom)}px;overflow:hidden;zoom:{zoom:.4f}"></div>'
            f'<section id="{pid}f" class="clip panelframe" data-start="{_f(start)}" data-duration="{_f(end - start)}"><div class="frame"></div></section>')
    return html, []


def _authored_panel(index: int, seg: dict, pack: StylePack, start: float, end: float) -> tuple[str, list[str], str]:
    """A panel scene written by the Motion Designer (creative/motion.py): its markup, its scoped css and its GSAP, in the page's one timeline."""
    from engine.hyperframes.scenes import scene_markup, scene_script
    beat = seg["beat"]
    custom = beat["custom"]
    bid = beat["bid"]
    bg = custom.get("bg") or pack.palette.panel_bg
    html = (f'<div id="{bid}-bg" class="clip panelbg" data-start="{_f(start)}" data-duration="{_f(end - start)}" style="background:{bg}"></div>'
            + scene_markup(bid, start, end - start, custom["html"]).replace('class="custom-beat clip"', 'class="custom-beat clip panelscene"'))
    js = [scene_script(bid, start, end, custom["js"], "full")]
    return html, js, custom.get("css", "")


# ── captions / hook / key moments ────────────────────────────────────────────────────────────────────────────────────

def _pages(words: list[dict], per_page: int) -> list[list[dict]]:
    pages, cur, chars = [], [], 0
    for w in words:
        n = len(str(w["w"]))
        if cur and (len(cur) >= per_page or chars + n > 22 or float(w["start"]) - float(cur[-1]["end"]) > 0.6):
            pages.append(cur)
            cur, chars = [], 0
        cur.append(w)
        chars += n + 1
    if cur:
        pages.append(cur)
    return pages


def _captions(words: list[dict], pack: StylePack, layout_at, blocked: list[tuple[float, float]] | None = None,
              teaser: list[float] | None = None) -> tuple[str, list[str]]:
    html, js = [], []
    cap = pack.caption
    blocked = blocked or []
    words = [w for w in words if not any(a <= float(w["start"]) < b for a, b in blocked)]
    if teaser and teaser[2:] == ["hidden"]:                  # another renderer (tscaps) draws the teaser words
        words = [w for w in words if float(w["start"]) >= teaser[1]]
        teaser = None
    lead = [w for w in words if teaser and float(w["start"]) < teaser[1]]            # the teaser is the hook: one big word at a time
    pages = _pages(lead, 1) + _pages(words[len(lead):], cap.per_page)
    for p, page in enumerate(pages):
        big = p < len(_pages(lead, 1))
        t0 = float(page[0]["start"])
        t1 = float(page[-1]["end"]) + 0.12
        if p + 1 < len(pages):
            t1 = min(t1, float(pages[p + 1][0]["start"]) - 0.01)
        layout = layout_at(t0)
        split = layout == "split"
        size = cap.size_split if split else cap.size_full
        y = int(H * cap.y_full)
        if big:
            size, y = int(cap.size_full * 1.55), int(H * 0.44)
        base_c = "#ffffff"
        hl_c = pack.palette.highlight
        split = False
        spans = "".join(f'<span class="cw" id="c{p}w{q}">{escape(str(w["w"]))}</span>' for q, w in enumerate(page))
        cls = "cpage" + (" boxed" if cap.box and not split and not big else "") + (" onpanel" if split else "") + (" teaser" if big else "")
        html.append(f'<div id="c{p}" class="{cls}" style="top:{y}px;font-size:{size}px;color:{base_c}">{spans}</div>')
        js.append(f'tl.set("#c{p}",{{opacity:1}},{_f(t0)});')
        js.append(f'tl.set("#c{p}",{{opacity:0}},{_f(t1)});')
        for q, w in enumerate(page):
            at = float(w["start"])
            nxt = float(page[q + 1]["start"]) if q + 1 < len(page) else t1
            if big:
                js.append(f'tl.fromTo("#c{p}w{q}",{{opacity:0,scale:1.45}},{{opacity:1,scale:1.0,duration:.18,ease:"power4.out"}},{_f(at)});')
            elif cap.mode == "slam":
                js.append(f'tl.fromTo("#c{p}w{q}",{{opacity:0,scale:1.5,color:"{base_c}"}},{{opacity:1,scale:1.0,color:"{hl_c}",duration:.16,ease:"power4.out"}},{_f(at)});')
            else:
                js.append(f'tl.fromTo("#c{p}w{q}",{{opacity:0.3,scale:{.82 if cap.pop else 1},color:"{base_c}"}},{{opacity:1,scale:1,color:"{hl_c}",duration:.14,ease:"back.out(2)"}},{_f(at)});')
            js.append(f'tl.to("#c{p}w{q}",{{color:"{base_c}",duration:.12}},{_f(max(at + .15, nxt))});')
    return "\n".join(html), js


def _hook(hook: dict | None, pack: StylePack) -> tuple[str, list[str]]:
    if not hook or pack.hook.mode == "none" or not str(hook.get("text") or "").strip():
        return "", []
    start, end = float(hook.get("start", 0.0)), min(float(hook.get("end", 3.0)), float(hook.get("start", 0.0)) + pack.hook.seconds)
    marked = {w for w in str(hook.get("highlight") or "").split()}
    words = str(hook["text"]).split()
    spans = "".join(f'<span class="hw{" hl" if w.strip(".,،…:!؟?") in marked else ""}" >{escape(w)}</span>' for w in words)
    html = (f'<section id="hook" class="clip hookbox {pack.hook.mode}" data-start="{_f(start)}" data-duration="{_f(end - start)}">'
            f'<div class="hookline" style="font-size:{pack.hook.size}px">{spans}</div></section>')
    js = [f'tl.from("#hook .hw",{{opacity:0,y:-70,scale:.8,duration:.45,stagger:.1,ease:"back.out(1.7)"}},{_f(start + .05)});',
          f'tl.to("#hook .hookline",{{opacity:0,y:-30,duration:.3,ease:"power2.in"}},{_f(max(start + .6, end - .3))});']
    return html, js


def _moments(moments: list[dict], pack: StylePack, layout_at) -> tuple[str, list[str]]:
    html, js = [], []
    for n, m in enumerate(moments):
        start, end = float(m["start"]), float(m["end"])
        if end - start < 0.5:
            continue
        split = layout_at(start) == "split"
        words = str(m["text"]).split()
        spans = "".join(f'<span class="mw{" acc" if k == len(words) - 1 else ""}">{escape(w)}</span>' for k, w in enumerate(words))
        html.append(f'<section id="m{n}" class="clip moment{" onpanel" if split else ""}" data-start="{_f(start)}" data-duration="{_f(end - start)}">'
                    f'<div class="mline">{spans}</div></section>')
        js.append(f'tl.from("#m{n} .mw",{{opacity:0,scale:2.1,y:40,duration:.32,stagger:.12,ease:"power4.out"}},{_f(start)});')
        js.append(f'tl.to("#m{n} .mline",{{opacity:0,duration:.2}},{_f(max(start + .4, end - .2))});')
    return "\n".join(html), js


# ── page ─────────────────────────────────────────────────────────────────────────────────────────────────────────────

def css(pack: StylePack) -> str:
    p = pack.palette
    accent_font = "Kharazmi" if pack.accent_font == "Kharazmi" else "Ray"
    accent_weight = 400 if pack.accent_font == "Kharazmi" else 900
    return f"""
html,body{{margin:0;background:transparent}}
#root{{position:relative;width:100%;height:100%;background:transparent;font-family:Ray,Vazir,sans-serif;direction:rtl;overflow:hidden;--font-display:Ray;--font-body:Ray;--fg:{p.panel_ink};--bg:{p.panel_bg};--brand:{p.accent};--accent:{p.accent};--accent-2:{p.accent_2};--surface:{p.card};--border:{p.panel_ink}33;--muted:{p.panel_ink}99}}
.panelframe{{position:absolute;left:0;top:0;width:{W}px;height:{SPLIT_Y}px;pointer-events:none}}
.panel{{position:absolute;left:0;top:0;width:{W}px;height:{SPLIT_Y}px;overflow:hidden;color:{p.panel_ink};background:{p.panel_bg}}}
.panel.ink{{color:#F4F1E8}} .panel.gradient{{background:linear-gradient(160deg,{p.panel_bg},{p.accent_2}55)}}
.frame{{position:absolute;left:48px;top:48px;right:48px;bottom:48px;border-radius:44px;border:5px solid {p.accent};opacity:.9}}
.ptitle{{position:absolute;left:96px;right:96px;top:120px;font-weight:900;line-height:1.3;text-align:center;display:flex;flex-wrap:wrap;justify-content:center;gap:0 22px}}
.tw{{display:inline-block}} .acc{{color:{p.accent};font-family:{accent_font},Ray;font-weight:{accent_weight}}}
.stack{{position:absolute;left:110px;right:110px;top:290px;display:flex;flex-direction:column}}
.ci{{display:flex;align-items:center;gap:28px;padding:0 34px;border-radius:34px;box-sizing:border-box;background:{p.card};color:{p.panel_ink};font-weight:900;box-shadow:0 18px 40px #0003}}
.ci b{{display:grid;place-items:center;border-radius:22px;background:{p.panel_ink};color:{p.card}}}
.ci.last{{background:{p.accent};color:#fff}} .ci.last b{{background:#fff;color:{p.accent}}}
.versus{{position:absolute;left:90px;right:90px;top:330px;height:480px;display:flex;align-items:center;justify-content:space-between;gap:20px}}
.vc{{flex:1;height:420px;border-radius:44px;background:{p.card};color:{p.panel_ink};display:grid;place-items:center;text-align:center;padding:30px;font-size:64px;font-weight:900;line-height:1.3;box-shadow:0 18px 40px #0003}}
.vc.dk{{background:{p.panel_ink};color:{p.card}}}
.vs{{position:absolute;left:50%;top:50%;margin:-62px 0 0 -62px;display:grid;place-items:center;width:124px;height:124px;border-radius:50%;background:{p.accent};color:#fff;font-size:34px;font-weight:900;z-index:2}}
.bignum{{position:absolute;left:0;right:0;top:230px;text-align:center;font-size:360px;line-height:1;font-weight:900;color:{p.accent}}}
.plabel{{position:absolute;left:100px;right:100px;top:660px;text-align:center;font-size:76px;font-weight:900;line-height:1.35}}
.steps{{position:absolute;left:110px;right:110px;top:320px;display:flex;flex-direction:column;gap:30px}}
.step{{display:flex;align-items:center;gap:30px;font-size:60px;font-weight:900}}
.step b{{display:grid;place-items:center;width:96px;height:96px;border-radius:50%;background:{p.accent};color:#fff;font-size:54px}}
.kin{{position:absolute;left:80px;right:80px;top:220px;display:flex;flex-wrap:wrap;justify-content:center;align-content:center;gap:10px 28px;height:620px;font-size:170px;font-weight:900;line-height:1.15;text-align:center}}
.kw{{display:inline-block}}
.cpage{{position:absolute;left:40px;right:40px;margin-top:-1em;display:flex;flex-wrap:wrap;justify-content:center;gap:0 .3em;font-weight:900;line-height:1.3;text-align:center;opacity:0;color:#fff;text-shadow:0 6px 22px #000c,0 0 4px #000a}}
.cpage.boxed{{left:90px;right:90px;padding:16px 30px;border-radius:30px;background:#0009;text-shadow:none}}
.cw{{display:inline-block}}
.cpage.onpanel{{text-shadow:none}} .onpanel .cw{{text-shadow:none}}
.hookbox{{position:absolute;left:0;top:0;width:{W}px;height:520px;display:flex;align-items:flex-end;justify-content:center;background:linear-gradient(#000b,transparent)}}
.hookline{{width:920px;padding:0 0 70px;display:flex;flex-wrap:wrap;justify-content:center;gap:0 .3em;font-weight:900;line-height:1.28;text-align:center;color:#fff;text-shadow:0 6px 24px #000c}}
.hw{{display:inline-block}} .hw.hl{{color:{p.highlight}}}
.moment{{position:absolute;left:0;top:0;width:{W}px;height:{H}px;display:flex;align-items:center;justify-content:center;background:#0006}}
.moment.onpanel{{height:{SPLIT_Y}px;background:{p.panel_bg}f2;color:{p.panel_ink}}}
.moment.onpanel .mline{{color:{p.panel_ink};text-shadow:none}}
.moment.onpanel .mw.acc{{color:{p.accent}}}
.mline{{width:900px;display:flex;flex-wrap:wrap;justify-content:center;gap:10px 26px;font-size:150px;font-weight:900;line-height:1.2;text-align:center;color:#fff;text-shadow:0 10px 40px #000}}
.mw{{display:inline-block}} .mw.acc{{color:{p.highlight};font-family:{accent_font},Ray;font-weight:{accent_weight}}}
"""


def build_project(directory: Path, pack: StylePack, script: dict, part: str = "all") -> Path:
    """index.html + assets for the overlay. part: "panel" (the panels, drawn UNDER the speaker so a head can rise over them), "text" (captions, hook,
    key-moment slams, drawn OVER the speaker) or "all". script: duration, segments[{start,end,layout,beat?}], words[{w,start,end}], hook?, moments[]."""
    from engine.hyperframes.assets import ensure_gsap
    from engine.hyperframes.scenes import FONT_FILES, fonts_css
    duration = float(script["duration"])
    assets = directory / "assets"
    (assets / "fonts").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ensure_gsap(), assets / "gsap.min.js")
    for target, source in FONT_FILES.items():
        shutil.copy2(ROOT / "presets" / "fonts" / source, assets / "fonts" / target)

    segments = script.get("segments") or []

    def layout_at(t: float) -> str:
        for s in segments:
            if s["start"] - 1e-6 <= t < s["end"]:
                return s.get("layout", "full")
        return "full"

    from creative import panel_library
    html, js = [], []
    scene_css: list[str] = []
    used: set[str] = set()
    comps = directory / "compositions" / "components"
    n = 0
    for seg in (segments if part in ("all", "panel") else []):
        if seg.get("layout") == "split" and seg.get("beat"):
            if seg["beat"].get("custom"):
                h, j, extra_css = _authored_panel(n, seg, pack, float(seg["start"]), float(seg["end"]))
                scene_css.append(extra_css)
                seg["component"] = "authored"
                pick = None
            else:
                pick = (panel_library.forced(seg["beat"]) or panel_library.choose(seg["beat"], used, seed=str(n))) if script.get("use_library", True) else None
                if pick:
                    name, values = pick
                    comps.mkdir(parents=True, exist_ok=True)
                    (comps / f"{name}.html").write_text(panel_library.fitted_html(name, float(seg["end"]) - float(seg["start"])), encoding="utf-8")
                    used.add(name)
                    h, j = _component_panel(n, name, values, pack, float(seg["start"]), float(seg["end"]), panel_library.LIBRARY[name].zoom)
                    seg["component"] = name
                else:
                    h, j = _panel(n, seg["beat"], pack, float(seg["start"]), float(seg["end"]))
            html.append(h)
            js.extend(j)
            n += 1
    if part in ("all", "text"):
        blocked = [(float(m["start"]), float(m["end"])) for m in (script.get("moments") or []) if float(m["end"]) - float(m["start"]) >= 0.5]
        h, j = _captions(script.get("words") or [], pack, layout_at, blocked, script.get("teaser"))
        html.append(h)
        js.extend(j)
        h, j = _hook(script.get("hook"), pack)
        html.append(h)
        js.extend(j)
        h, j = _moments(script.get("moments") or [], pack, layout_at)
        html.append(h)
        js.extend(j)

    page = f"""<!doctype html>
<html lang="fa"><head><meta charset="utf-8"><meta name="viewport" content="width={W}, height={H}">
<script src="./assets/gsap.min.js"></script>
<style>
{fonts_css()}
{css(pack)}
.panelbg{{position:absolute;left:0;top:0;width:{W}px;height:{SPLIT_Y}px}}
.panelscene{{position:absolute;left:0;top:0;width:{W}px;height:{SPLIT_Y}px;overflow:hidden}}
{''.join(scene_css)}
</style></head><body>
<div id="root" data-composition-id="{COMPOSITION_ID}" data-start="0" data-width="{W}" data-height="{H}" data-duration="{_f(duration)}">
{chr(10).join(x for x in html if x)}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
{chr(10).join(js)}
window.__timelines["{COMPOSITION_ID}"] = tl;
</script></body></html>"""
    (directory / "index.html").write_text(page, encoding="utf-8")
    (directory / "script.json").write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
    return directory / "index.html"
