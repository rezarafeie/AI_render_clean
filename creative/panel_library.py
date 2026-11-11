"""The panel library: curated HyperFrames registry components (Apache-2.0, vendored in assets/hyperframes_components) and how a beat fills them.

Every entry was rendered with Persian text and the pack's design tokens and kept only if the text joins and reads correctly. A component is a
finished piece of professional motion, so variety comes from the library and from never using one twice in a reel, not from templates written
here. `choose()` is deterministic (same beat, same pick) and takes the components already used so the reel never repeats a motion.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

LIBRARY_DIR = Path(__file__).resolve().parents[1] / "assets" / "hyperframes_components"

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٫٬", "0123456789.,")


def number_of(text: str) -> tuple[float, str, str] | None:
    """(value, prefix, suffix) of the first number in a title: '۳۰٪ بیشتر' -> (30, '', '%')."""
    m = re.search(r"([^\d۰-۹\s]{0,2})\s*([0-9۰-۹][0-9۰-۹,٬.٫]*)\s*(٪|%|k|K|M|x|X|ی|برابر)?", text or "")
    if not m:
        return None
    try:
        value = float(m.group(2).translate(_DIGITS).replace(",", ""))
    except ValueError:
        return None
    suffix = {"٪": "%", "%": "%", "k": "k", "K": "k", "M": "M", "x": "x", "X": "x", "برابر": "x"}.get(m.group(3) or "", "")
    return value, "", suffix


@dataclass(frozen=True)
class Entry:
    name: str
    roles: tuple[str, ...]            # list | compare | stat | headline | concept | cta | steps
    fill: Callable[[dict, float], dict]
    min_items: int = 0
    max_items: int = 9
    note: str = ""
    zoom: float = 1.8                  # the component is laid out in a container 1/zoom as wide, then scaled up: bigger type on a phone


def _items(beat: dict, low: int = 1, high: int = 6) -> list[str]:
    values = [str(i).strip() for i in (beat.get("items") or []) if str(i).strip()]
    return values[:high] if len(values) >= low else values


def _csv(values: list[str]) -> str:
    return ",".join(v.replace(",", "،") for v in values)


def _head_tail(title: str) -> tuple[str, str]:
    words = title.split()
    if len(words) <= 1:
        return "", title
    return " ".join(words[:-1]), words[-1]


def _fill_timeline(b, d):
    items = _items(b, 2, 4)
    return {"labels": _csv(items), "beatCount": len(items), "interval": round(max(0.45, min(1.1, d * 0.75 / max(1, len(items)))), 2)}


def _fill_stat_ring(b, d):
    n = number_of(b.get("title", "")) or (72.0, "", "%")
    return {"progress": min(100, n[0]) if n[0] <= 100 else 100, "label": f"{int(n[0]) if n[0] == int(n[0]) else n[0]}{n[2]}"}


def _fill_count_up(b, d):
    n = number_of(b.get("title", "")) or (100.0, "", "%")
    return {"start": 0, "end": n[0], "prefix": n[1], "suffix": n[2] or ""}


def _fill_chart(b, d):
    items = _items(b, 2, 4)
    n = len(items) if len(items) >= 2 else 4
    values = [round(18 + 82 * (k + 1) / n) for k in range(n)]
    return {"type": "bars", "data": ", ".join(str(v) for v in values), "labels": ", ".join(items if len(items) >= 2 else ["۱", "۲", "۳", "۴"]), "emphasize": n, "unit": "%"}


def _fill_hub(b, d):
    items = _items(b, 2, 5)
    return {"hub_label": (b.get("title") or "")[:18] or items[0], "nodes": _csv(items[:5] if len(items) >= 2 else items)}


def _fill_radial(b, d):
    items = _items(b, 2, 6)
    return {"center_label": (b.get("title") or "")[:18], "chips": _csv(items)}


def _fill_compare(a, b2):
    def fill(b, d):
        items = _items(b, 2, 2)
        left, right = (items + ["", ""])[:2]
        return {a: left, b2: right}
    return fill


def _fill_split_tilt(b, d):
    items = _items(b, 2, 2)
    left, right = (items + ["", ""])[:2]
    return {"label_a": left, "label_b": right, "badge_a": "۱", "badge_b": "۲"}


def _fill_text(key):
    return lambda b, d: {key: (b.get("title") or "").strip()}


def _fill_marker(b, d):
    head, tail = _head_tail((b.get("title") or "").strip())
    return {"text": (b.get("title") or "").strip(), "emphasis_word": tail}


def _fill_vox(b, d):
    head, tail = _head_tail((b.get("title") or "").strip())
    items = _items(b, 1, 1)
    return {"text": (b.get("title") or "").strip(), "keyword": tail, "note": items[0] if items else ""}


def _fill_headline_slam(b, d):
    title = (b.get("title") or "").strip()
    words = title.split()
    return {"text": title, "accent_word_index": max(0, len(words) - 1)}


def _fill_titlecard(b, d):
    items = _items(b, 1, 1)
    return {"headline": (b.get("title") or "").strip(), "kicker": items[0] if items else ""}


def _fill_line_swap(b, d):
    items = _items(b, 2, 2)
    head, tail = _head_tail(items[1] if len(items) > 1 else (b.get("title") or ""))
    return {"line_a": items[0] if items else (b.get("title") or ""), "line_b": items[1] if len(items) > 1 else (b.get("title") or ""),
            "underline_word": tail, "swap_at": round(max(1.0, min(2.2, d * 0.4)), 2)}


def _fill_swap(b, d):
    items = _items(b, 2, 4)
    return {"prefix": (b.get("title") or "")[:24], "options": _csv(items)}


def _fill_cta(b, d):
    items = _items(b, 1, 2)
    return {"action_line": (b.get("title") or "").strip(), "button_label": items[0] if items else "ادامه", "microcopy": items[1] if len(items) > 1 else ""}


def _fill_notes(b, d):
    items = _items(b, 1, 3)
    return {"title": (b.get("title") or "").strip().replace(" | ", "|"), "lines": "|".join(items)}


def _fill_notifications(b, d):
    items = _items(b, 2, 4)
    return {"titles": _csv(items), "bodies": _csv([(b.get("title") or "")[:40]] * len(items))}


def _fill_pull_back(b, d):
    n = number_of(b.get("title", ""))
    items = _items(b, 1, 1)
    return {"detail_text": (f"{int(n[0]) if n[0] == int(n[0]) else n[0]}{n[2]}" if n else (items[0] if items else "★")), "headline": (b.get("title") or "").strip()}


def _fill_marquee(b, d):
    items = _items(b, 2, 6)
    return {"words": ", ".join(items)}


def _fill_words(b, d):
    return {"words": _csv(_items(b, 1, 6) or [(b.get("title") or "")])}


def _fill_social(b, d):
    items = _items(b, 3, 3) + ["", "", ""]
    return {"brand": (b.get("title") or "")[:22], "proof": items[0], "cta": items[1], "f1": f"{items[0]}", "f2": f"{items[1]}", "f3": f"{items[2]}"}


LIBRARY: dict[str, Entry] = {e.name: e for e in (
    # lists / steps
    Entry("beat-timeline", ("list", "steps"), _fill_timeline, 2, 4, zoom=1.8),
    Entry("grid-card-assemble", ("list",), lambda b, d: {"items": _csv(_items(b, 2, 6))}, 2, 6, zoom=1.6),
    Entry("state-chip-rail", ("list", "steps"), lambda b, d: {"states": _csv(_items(b, 2, 5))}, 2, 5, zoom=2.8),
    Entry("pan-stations", ("list", "steps"), lambda b, d: {"labels": _csv(_items(b, 2, 4)), "stationCount": len(_items(b, 2, 4))}, 2, 4, zoom=1.4),
    Entry("tracing-beam", ("steps",), lambda b, d: {"labels": _csv(_items(b, 2, 3))}, 2, 3, zoom=1.8),
    Entry("notification-stack", ("list",), _fill_notifications, 2, 4, zoom=1.5),
    Entry("kinetic-type-swap", ("list", "headline"), _fill_swap, 2, 4, zoom=2.4),
    Entry("perspective-marquee", ("list",), _fill_marquee, 2, 6, zoom=1.5),
    Entry("multiplayer-cursors", ("list", "concept"), lambda b, d: {"labels": _csv(_items(b, 2, 4)), "cursorCount": len(_items(b, 2, 4))}, 2, 4, zoom=2.2),
    # compare
    Entry("split-tilt-cards", ("compare",), _fill_split_tilt, 2, 2, zoom=1.3),
    Entry("comparison-split", ("compare",), _fill_compare("labelA", "labelB"), 2, 2, zoom=1.0),
    Entry("before-after-wipe", ("compare",), _fill_compare("label_a", "label_b"), 2, 2, zoom=1.0),
    Entry("focus-rack", ("compare",), _fill_compare("label_a", "label_b"), 2, 2, zoom=1.3),
    Entry("match-cut", ("compare",), _fill_compare("label_a", "label_b"), 2, 2, zoom=1.0),
    # numbers
    Entry("conic-progress-ring", ("stat",), _fill_stat_ring, zoom=1.5),
    Entry("count-up", ("stat",), _fill_count_up, zoom=2.4),
    Entry("chart-story", ("stat", "list"), _fill_chart, 0, 4, zoom=1.2),
    Entry("pull-back-reveal", ("stat", "headline"), _fill_pull_back, zoom=1.4),
    Entry("star-rating-fill", ("stat",), lambda b, d: {"rating": 4.8}, zoom=1.8),
    # headlines / emphasis
    Entry("headline-slam", ("headline",), _fill_headline_slam, zoom=2.4),
    Entry("marker-highlight", ("headline",), _fill_marker, zoom=2.4),
    Entry("push-in", ("headline",), _fill_text("text"), zoom=1.6),
    Entry("text-shimmer", ("headline",), _fill_text("text"), zoom=2.2),
    Entry("titlecard-calm", ("headline",), _fill_titlecard, zoom=1.8),
    Entry("vox-annotate", ("headline",), _fill_vox, zoom=2.2),
    Entry("line-swap", ("headline", "compare"), _fill_line_swap, 0, 2, zoom=2.2),
    Entry("per-word-rise", ("headline",), _fill_text("text"), zoom=2.4),
    Entry("svg-mask-reveal", ("headline",), _fill_text("text"), zoom=1.6),
    Entry("drift-hold", ("headline",), _fill_text("text"), zoom=2.2),
    Entry("typed-prompt", ("headline",), _fill_text("text"), zoom=2.6),
    # concept maps
    Entry("constellation-hub", ("concept", "list"), _fill_hub, 2, 5, zoom=1.5),
    Entry("radial-surround", ("concept",), _fill_radial, 2, 6, zoom=1.6),
    Entry("overwhelm-surround", ("concept",), lambda b, d: {"centerLabel": (b.get("title") or "")[:16]}, zoom=1.2),
    Entry("avatar-cloud", ("concept",), lambda b, d: {"label": (b.get("title") or "")[:24]}, zoom=1.5),
    # closing / call to action
    Entry("cta-lockup", ("cta",), _fill_cta, zoom=1.8),
    Entry("cta-close", ("cta",), _fill_cta, zoom=2.2),
    Entry("notes-typing", ("steps", "list"), _fill_notes, 1, 3, zoom=1.3),
)}


def _hold() -> dict[str, float]:
    """How long each component keeps something on screen (measured by rendering it with a long panel; creative/panel_hold.json). A component that animates out early would leave
    a long panel empty, so a panel is only given components that last about as long as it does. Unknown components are not filtered."""
    global _HOLD
    if _HOLD is None:
        try:
            _HOLD = {k: float(v["visible_until"]) for k, v in json.loads((Path(__file__).with_name("panel_hold.json")).read_text(encoding="utf-8")).items()}
        except (OSError, ValueError, KeyError, TypeError):
            _HOLD = {}
    return _HOLD


_HOLD: dict[str, float] | None = None
HOLD_SLACK = 0.9           # a component may end this much before its panel does (the next panel's cut hides it)


def lasts(name: str, seconds: float | None) -> bool:
    if not seconds:
        return True
    visible = _hold().get(name)
    return visible is None or visible >= min(float(seconds), 7.0) - HOLD_SLACK


def role_of(beat: dict) -> str:
    items = _items(beat, 1, 6)
    vtype = str(beat.get("visual_type") or "concept")
    title = str(beat.get("title") or "")
    if str(beat.get("role") or beat.get("narrative_role") or "") == "cta":
        return "cta"
    if vtype in {"comparison", "before_after"} and len(items) >= 2:
        return "compare"
    if vtype == "stat" or (not items and number_of(title)):
        return "stat"
    if vtype == "steps" and len(items) >= 2:
        return "steps"
    if len(items) >= 3:
        return "list"
    if len(items) == 2:
        return "concept" if vtype == "concept" else "compare"
    return "headline"


def available() -> list[str]:
    return [n for n in LIBRARY if (LIBRARY_DIR / f"{n}.html").is_file()]


def choose(beat: dict, used: set[str], seed: str = "", seconds: float | None = None) -> tuple[str, dict] | None:
    """The component for this beat and the variable values that fill it; None when the library has nothing that fits (for a panel of `seconds`, only components that last that long)."""
    role = role_of(beat)
    items = len(_items(beat, 1, 6))
    ready = set(available())

    def pool(r: str) -> list[str]:
        return sorted(n for n, e in LIBRARY.items() if n in ready and r in e.roles and e.min_items <= items <= e.max_items and lasts(n, seconds))

    candidates = [n for n in pool(role) if n not in used] or [n for n in pool("headline") if n not in used] or [n for n in pool(role) if n not in used]
    if not candidates:
        return None
    pick = candidates[int(hashlib.sha1(f"{seed}{beat.get('title','')}".encode()).hexdigest(), 16) % len(candidates)]
    return pick, LIBRARY[pick].fill(beat, 4.0)


def forced(beat: dict) -> tuple[str, dict] | None:
    """The component a beat was told to use (`beat["force_component"]`), with its values; None when none is set or it is not in the library."""
    name = str((beat or {}).get("force_component") or "")
    if name in LIBRARY and name in set(available()):
        return name, LIBRARY[name].fill(beat, 4.0)
    return None


def alternatives(beat: dict, exclude: set[str], seconds: float | None = None) -> list[str]:
    """Other components that fit this beat, best first (same role, then the headline pool), never one in `exclude`."""
    role = role_of(beat)
    items = len(_items(beat, 1, 6))
    ready = set(available())

    def pool(r: str) -> list[str]:
        return sorted(n for n, e in LIBRARY.items() if n in ready and r in e.roles and e.min_items <= items <= e.max_items and n not in exclude and lasts(n, seconds))
    return pool(role) + [n for n in pool("headline") if n not in pool(role)]


def fitted_html(name: str, seconds: float) -> str:
    """The component's page with its own envelope set to the panel's length and without its CDN script.

    A component animates in and out over the duration it declares (`data-duration` on its root, default 3-5 s) and then leaves the panel EMPTY; a panel lasts as long as the
    speaker's sentence, so the declared duration must be the panel's. The page already loads GSAP locally, so the component's CDN `<script src>` (which would need the network, and
    a render worker has none) is dropped."""
    html = (LIBRARY_DIR / f"{name}.html").read_text(encoding="utf-8")
    value = f"{max(1.0, float(seconds)):.2f}".rstrip("0").rstrip(".")
    html = re.sub(r'(data-duration=")[0-9.]+(")', rf"\g<1>{value}\g<2>", html)
    html = re.sub(r'(data-composition-duration=")[0-9.]+(")', rf"\g<1>{value}\g<2>", html)
    return re.sub(r'<script src="https://cdn\.jsdelivr\.net/[^"]+"></script>', "", html)
