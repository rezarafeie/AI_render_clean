"""The narration as typography on the film: every spoken word appears on the screen exactly when it is heard, in the film's own palette AND fonts.

Built deterministically from the voice take's word times (`scene.cues`, seconds from the scene start), so it is never out of step with the voice and costs no model
call. The planner picks one of six caption designs for the whole film (plate, marker, bar, pop, outline, minimal) so the captions belong to the film's design rather
than being one fixed plate; they are set in the film's body (or title) font. The markup, style and timeline code are appended to the scene's own, so the captions
come and go with the scene.
"""
from __future__ import annotations

import html as html_lib
import os
import re

ENABLED = os.environ.get("MOTION_CAPTIONS", "1") != "0"
_BREAK = re.compile(r"[.؟?!،,:;…]$")


def phrases(cues: list[dict], max_words: int = 5, pause: float = 0.7) -> list[list[dict]]:
    """Cue words grouped into phrases: at most `max_words`, broken after punctuation and at a pause between words."""
    groups: list[list[dict]] = []
    current: list[dict] = []
    for index, cue in enumerate(cues):
        current.append(cue)
        gap = (cues[index + 1]["t"] - cue["t"]) if index + 1 < len(cues) else 0.0
        if len(current) >= max_words or _BREAK.search(cue["word"]) or gap > pause:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def _rgba(color: str, alpha: float) -> str:
    color = str(color or "#000000").lstrip("#")
    if len(color) == 3:
        color = "".join(c * 2 for c in color)
    try:
        r, g, b = (int(color[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        r = g = b = 0
    return f"rgba({r},{g},{b},{alpha})"


STYLES = ("plate", "marker", "bar", "pop", "outline", "minimal")


def choose_style(wanted: str, seed: str = "") -> str:
    """The planner's choice when valid; else one fixed by the film's title/signature (always the same for the same film)."""
    wanted = (wanted or "").strip().lower()
    if wanted in STYLES:
        return wanted
    import hashlib
    return STYLES[int(hashlib.sha256((seed or "").encode()).hexdigest(), 16) % len(STYLES)]


def _on(color: str) -> str:
    """Readable text colour on `color`."""
    c = str(color or "#000000").lstrip("#")
    if len(c) == 3:
        c = "".join(x * 2 for x in c)
    try:
        r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return "#ffffff"
    return "#111111" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "#ffffff"


def _family(font: str) -> str:
    return str(font or "Ray").replace("'", "").replace('"', "").strip() or "Ray"


def layer(scene, n: int, palette, width: int = 1080, height: int = 1920, *, style: str = "plate", font: str = "Ray", display_font: str = "") -> tuple[str, str, str] | None:
    """(html, css, js) for scene n, or None when the scene has no word times. The js uses T (the scene start) and D (its length), like the designers' code."""
    cues = [c for c in (getattr(scene, "cues", None) or []) if isinstance(c, dict) and c.get("word")]
    if not ENABLED or not cues:
        return None
    style = style if style in STYLES else "plate"
    length = round(scene.end - scene.start, 3)
    groups = phrases(cues, max_words=1 if style == "pop" else 5)
    top = int(height * 0.69)
    base = 76 if width <= 1200 else 64
    body, title = _family(font), _family(display_font or font)
    ink, accent, surface, bg = palette.ink, palette.accent, palette.surface, palette.bg
    zone = (f".cap{{position:absolute;left:48px;right:48px;top:{top}px;height:300px;pointer-events:none;direction:rtl;z-index:60;font-family:'{body}'}}"
           f".cap-p{{position:absolute;left:0;right:0;top:50%;transform:translateY(-50%);display:flex;flex-wrap:wrap;justify-content:center;gap:0 24px;text-align:center;opacity:0}}"
           f".cap-w{{display:inline-block}}")
    if style == "plate":
        look = (f".cap-p{{padding:20px 36px;border-radius:34px;background:{_rgba(surface, .86)};color:{ink};font:800 {base}px/1.45 '{body}'}}")
    elif style == "marker":
        look = (f".cap-p{{color:{ink};font:900 {base}px/1.6 '{body}';text-shadow:0 0 22px {_rgba(bg, .9)},0 3px 0 {_rgba(bg, .9)}}}"
                f".cap-w{{padding:0 14px;border-radius:14px}}")
    elif style == "bar":
        look = (f".cap{{left:0;right:0}}.cap-p{{left:0;right:0;justify-content:flex-start;padding:24px 70px 24px 48px;background:{_rgba(surface, .94)};color:{ink};font:800 {int(base * .92)}px/1.5 '{body}';"
                f"border-right:16px solid {accent}}}")
    elif style == "pop":
        look = (f".cap-p{{color:{accent};font:900 {int(base * 1.65)}px/1.2 '{title}';text-shadow:0 0 26px {_rgba(bg, .85)},0 5px 0 {_rgba(bg, .8)}}}")
    elif style == "outline":
        look = (f".cap-p{{color:{ink};font:900 {int(base * 1.08)}px/1.5 '{title}';-webkit-text-stroke:11px {bg};paint-order:stroke fill;text-shadow:0 6px 18px {_rgba(bg, .6)}}}")
    else:                                              # minimal
        look = (f".cap-p{{color:{ink};font:600 {int(base * .72)}px/1.7 '{body}';letter-spacing:.02em;padding-bottom:18px}}"
                f".cap-line{{position:absolute;right:0;bottom:6px;height:5px;width:100%;background:{accent};border-radius:3px;transform-origin:right center;transform:scaleX(0)}}")
    css = zone + look
    parts, js = [], []
    for k, group in enumerate(groups, 1):
        start = group[0]["t"]
        following = groups[k][0]["t"] if k < len(groups) else None
        end = min((following - 0.04) if following is not None else group[-1]["t"] + 0.95, length - 0.25)
        end = max(end, start + 0.4)
        words = "".join(f'<span class="cap-w" id="s{n}-cw{k}-{j}">{html_lib.escape(w["word"])}</span>' for j, w in enumerate(group, 1))
        line = f'<i class="cap-line" id="s{n}-cl{k}"></i>' if style == "minimal" else ""
        parts.append(f'<div class="cap-p" id="s{n}-cp{k}">{words}{line}</div>')
        enter = {"pop": "{opacity:0, scale:0.55}, {opacity:1, scale:1, duration:0.16, ease:\"back.out(2.6)\"}",
                 "bar": "{opacity:0, x:80}, {opacity:1, x:0, duration:0.24, ease:\"power3.out\"}"}.get(style, "{opacity:0, y:26, scale:0.94}, {opacity:1, y:0, scale:1, duration:0.2, ease:\"power3.out\"}")
        js.append(f'tl.fromTo("#s{n}-cp{k}", {enter}, T + {max(0.0, start - 0.06):.2f});')
        if style == "minimal":
            js.append(f'tl.to("#s{n}-cl{k}", {{scaleX:1, duration:{max(0.3, end - start):.2f}, ease:"none"}}, T + {max(0.0, start):.2f});')
        for j, word in enumerate(group, 1):
            at = max(0.0, word["t"])
            nxt = group[j]["t"] if j < len(group) else end
            target = f"#s{n}-cw{k}-{j}"
            if style in ("marker", "plate", "outline", "bar"):
                lit = {"marker": f'{{opacity:1, backgroundColor:"{accent}", color:"{_on(accent)}", scale:1.08, duration:0.12, ease:"back.out(2.4)"}}',
                       "outline": f'{{opacity:1, color:"{accent}", scale:1.12, duration:0.12, ease:"back.out(2.4)"}}'}.get(style, f'{{opacity:1, color:"{accent}", scale:1.14, duration:0.12, ease:"back.out(2.4)"}}')
                back = {"marker": f'{{backgroundColor:"rgba(0,0,0,0)", color:"{ink}", scale:1, duration:0.16, ease:"power2.out"}}'}.get(style, f'{{color:"{ink}", scale:1, duration:0.16, ease:"power2.out"}}')
                js.append(f'tl.set("{target}", {{opacity:0.5}}, T + 0);')
                js.append(f'tl.to("{target}", {lit}, T + {at:.2f});')
                js.append(f'tl.to("{target}", {back}, T + {max(at + 0.14, min(nxt, end)):.2f});')
            elif style == "pop":
                pass
            else:                                      # minimal: the words rise in
                js.append(f'tl.set("{target}", {{opacity:0, y:22}}, T + 0);')
                js.append(f'tl.to("{target}", {{opacity:1, y:0, duration:0.18, ease:"power2.out"}}, T + {at:.2f});')
        js.append(f'tl.to("#s{n}-cp{k}", {{opacity:0, y:-20, duration:0.18, ease:"power2.in"}}, T + {end:.2f});')
    return f'<div class="cap" id="s{n}-cap" data-layout-allow-overlap>{"".join(parts)}</div>', css, "\n".join(js)
