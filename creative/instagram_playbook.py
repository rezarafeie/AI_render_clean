"""The Instagram playbook of instagram-agent-skill (MIT, vendor/) for the editor's idea and script engines.

When a brief is for Instagram (a Hermes proposal, or the person says so), the director and the scriptwriter get the skill's rules: the 26 hook formulas,
the first-seconds rules, the structure of a reel and the caption rules. The text is read from the vendored skill, so updating the skill updates the engines."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[1] / "vendor" / "instagram-agent-skill" / "skills"
TRIGGERS = ("اینستاگرام", "instagram", "ریلز", "reels", "reel ", "hermes")


def wanted(text: str) -> bool:
    low = (text or "").lower()
    return any(token in low for token in TRIGGERS)


def _body(folder: str, limit: int) -> str:
    try:
        text = (SKILLS / folder / "SKILL.md").read_text(encoding="utf-8")
    except OSError:
        return ""
    return re.sub(r"\A---.*?---\s*", "", text, flags=re.S)[:limit]


@lru_cache(maxsize=1)
def playbook() -> str:
    try:
        hooks = json.loads((SKILLS / "ig-reel" / "hooks.json").read_text(encoding="utf-8")).get("hooks") or []
    except (OSError, ValueError):
        hooks = []
    formulas = "\n".join(f"- {h.get('name')}: {h.get('template')} (best for: {str(h.get('best_for', ''))[:90]})" for h in hooks[:26])
    parts = ["INSTAGRAM PLAYBOOK (apply to this video; adapt every formula to natural Persian, never translate it word by word):",
             "Hook formulas:\n" + formulas if formulas else "",
             "Reel skill (rules and structure):\n" + _body("ig-reel", 4200),
             "Caption skill:\n" + _body("ig-caption", 1800)]
    return "\n\n".join(p for p in parts if p)


def add_to(guide: str, source_text: str) -> str:
    """The structure guide with the playbook appended when the brief is for Instagram."""
    return guide + "\n\n" + playbook() if wanted(source_text) and playbook() else guide
