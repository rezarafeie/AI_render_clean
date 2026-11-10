"""The narration as typography on the film: every spoken word appears on the screen exactly when it is heard, in the scene's own palette.

Built deterministically from the voice take's word times (`scene.cues`, seconds from the scene start), so it is never out of step with the voice and costs no model
call. Each phrase (a few words, broken at punctuation or a pause) is laid in a plate in the lower part of the frame; the scenes alternate between two treatments (words
rise in as they are spoken / all words shown with the spoken one lit). The markup, style and timeline code are appended to the scene's own, so the captions
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


def layer(scene, n: int, palette, width: int = 1080, height: int = 1920) -> tuple[str, str, str] | None:
    """(html, css, js) for scene n, or None when the scene has no word times. The js uses T (the scene start) and D (its length), like the designers' code."""
    cues = [c for c in (getattr(scene, "cues", None) or []) if isinstance(c, dict) and c.get("word")]
    if not ENABLED or not cues:
        return None
    length = round(scene.end - scene.start, 3)
    groups = phrases(cues)
    top = int(height * 0.69)
    size = 76 if width <= 1200 else 64
    css = (f".cap{{position:absolute;left:48px;right:48px;top:{top}px;height:300px;pointer-events:none;direction:rtl;z-index:60}}"
           f".cap-p{{position:absolute;left:0;right:0;top:50%;transform:translateY(-50%);display:flex;flex-wrap:wrap;justify-content:center;gap:0 24px;padding:20px 36px;border-radius:34px;"
           f"background:{_rgba(palette.surface, .86)};color:{palette.ink};font:900 {size}px/1.45 Ray;text-align:center;opacity:0}}"
           f".cap-w{{display:inline-block}}")
    parts, js = [], []
    mode = "reveal" if n % 2 else "light"
    for k, group in enumerate(groups, 1):
        start = group[0]["t"]
        following = groups[k]["t"] if False else (groups[k][0]["t"] if k < len(groups) else None)
        end = min((following - 0.04) if following is not None else group[-1]["t"] + 0.95, length - 0.25)
        end = max(end, start + 0.4)
        words = "".join(f'<span class="cap-w" id="s{n}-cw{k}-{j}">{html_lib.escape(w["word"])}</span>' for j, w in enumerate(group, 1))
        parts.append(f'<div class="cap-p" id="s{n}-cp{k}">{words}</div>')
        js.append(f'tl.fromTo("#s{n}-cp{k}", {{opacity:0, y:26, scale:0.94}}, {{opacity:1, y:0, scale:1, duration:0.2, ease:"power3.out"}}, T + {max(0.0, start - 0.06):.2f});')
        for j, word in enumerate(group, 1):
            at = max(0.0, word["t"])
            nxt = group[j]["t"] if j < len(group) else end
            target = f"#s{n}-cw{k}-{j}"
            if mode == "reveal":
                js.append(f'tl.set("{target}", {{opacity:0, y:34}}, T + 0);')
                js.append(f'tl.to("{target}", {{opacity:1, y:0, duration:0.16, ease:"back.out(2.2)"}}, T + {at:.2f});')
            else:
                js.append(f'tl.set("{target}", {{opacity:0.42}}, T + 0);')
                js.append(f'tl.to("{target}", {{opacity:1, color:"{palette.accent}", scale:1.14, duration:0.12, ease:"back.out(2.4)"}}, T + {at:.2f});')
                js.append(f'tl.to("{target}", {{color:"{palette.ink}", scale:1, duration:0.16, ease:"power2.out"}}, T + {max(at + 0.14, min(nxt, end)):.2f});')
        js.append(f'tl.to("#s{n}-cp{k}", {{opacity:0, y:-20, duration:0.2, ease:"power2.in"}}, T + {end:.2f});')
    return f'<div class="cap" id="s{n}-cap" data-layout-allow-overlap>{"".join(parts)}</div>', css, "\n".join(js)
