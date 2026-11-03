"""A narration script the person wrote themselves: found in their message, kept word for word.

    Narration (English, speak exactly):
    1. "Every video starts as an idea."
    2. "Then it becomes hours of work."

A script like this is final. It is never rewritten, shortened or extended; when it needs improving the person is asked.
"""
from __future__ import annotations

import re

_HEAD = re.compile(r"^\s*(?:narration|script|voice-?over|روایت|نریشن|متن\s*روایت|سناریو)\b[^\n]*:\s*$", re.I | re.M)
_ITEM = re.compile(r"^\s*(?:\d+\s*[.)]|[-•])\s*[“\"«]?(.+?)[”\"»]?\s*$")


def extract(text: str) -> list[str]:
    """The script's lines in order, or [] when the text carries no numbered/bulleted narration under a narration heading."""
    for head in _HEAD.finditer(text or ""):
        lines: list[str] = []
        for raw in text[head.end():].splitlines():
            if not raw.strip():
                if lines: break
                continue
            found = _ITEM.match(raw)
            if not found:
                break
            lines.append(found.group(1).strip())
        if len(lines) >= 2:
            return lines
    return []


def apply(plan, lines: list[str]):
    """The plan with each scene's narration set to the supplied line (same count required; the caller checks)."""
    scenes = [scene.model_copy(update={"narration": line}) for scene, line in zip(plan.scenes, lines)]
    return plan.model_copy(update={"scenes": scenes})
