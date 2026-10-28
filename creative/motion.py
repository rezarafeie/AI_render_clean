"""Compatibility for saved motion plans. All graphics use maintained templates.

Legacy authored-scene caches are deliberately never read or executed.
"""
from __future__ import annotations

def plan_from_public(data: dict | None):
    """Rebuild what `compose` needs from `CreativePlan.public()` (what is stored on a job); tolerant of an empty/absent plan."""
    from types import SimpleNamespace
    from .schemas import Beat
    data = data or {}
    brief, chosen = data.get("brief") or {}, data.get("chosen") or {}
    return SimpleNamespace(
        brief=SimpleNamespace(**{k: brief.get(k, "") for k in ("topic", "core_message", "audience", "tone")}),
        chosen=SimpleNamespace(name=chosen.get("name", ""), angle=chosen.get("angle", ""), visual_language=chosen.get("visual_language", ""),
                               pacing=chosen.get("pacing", ""), beats=[Beat(**b) for b in chosen.get("beats", []) if isinstance(b, dict)]))



def enabled() -> bool:
    return False


def compose(beats: list, plan, sentences: list[dict], **kwargs) -> list:
    """Keep validated VisualBeat data; never author or load executable scenes."""
    return beats
