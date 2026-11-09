"""Talking-head reel styles (podcast clip -> styled vertical reel).

Every style is a self-contained module in ``engine/talking_styles`` exposing
``track_faces``, ``plan_reel``, ``render`` and ``probe_video``. Saved styles
are frozen: a new look is a new module, never an edit to an existing one.
"""
from __future__ import annotations

from importlib import import_module
from types import ModuleType

STYLES = {
    "talking_1": ("صحبتی ۱", "engine.talking_styles.talking_1"),
    "talking_2": ("صحبتی ۲ (آموزشی دوتکه)", "engine.talking_styles.talking_2"),
    "talking_3": ("صحبتی ۳ (سینمایی)", "engine.talking_styles.talking_3"),
    "talking_4": ("صحبتی ۴ (مینیمال واقعی)", "engine.talking_styles.talking_4"),
    "talking_5": ("صحبتی ۵ (پک استایل: پنل، کارت گوینده، افکت)", "engine.talking_styles.talking_5"),
}
DEFAULT_STYLE = "talking_1"
# Retired from every list a person or the planner picks from; saved jobs that used them still render through get_style.
RETIRED = frozenset({"talking_4"})


def get_style(style_id: str | None) -> ModuleType:
    if style_id not in STYLES:
        style_id = DEFAULT_STYLE
    return import_module(STYLES[style_id][1])


def style_list() -> list[dict]:
    return [{"id": key, "label": label} for key, (label, _) in STYLES.items() if key not in RETIRED]
