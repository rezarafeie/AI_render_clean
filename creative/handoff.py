"""An idea that Instagram GPT hands to the editor already has its script, scenes, look and mood, and the person approved them.
The editor adopts that script instead of writing a new one and judging it again (a rewrite loop that could end with no video at all)."""
from __future__ import annotations

import re

from .schemas import Beat, Concept, ContentBrief, CreativePlan, Critique, ScriptDraft, ScriptLine

SCENE = re.compile(r"^\s*(\d+)\.\s*\((?P<sec>[\d.]+)\s*s\)\s*تصویر:\s*(?P<see>.*?)\s*\|\s*متن روی صفحه:\s*(?P<title>.*?)\s*\|\s*روایت:\s*(?P<say>.*?)\s*$")


def _field(text: str, label: str) -> str:
    found = re.search(rf"^{re.escape(label)}\s*(.+)$", text, flags=re.M)
    return found.group(1).strip() if found else ""


def parse(text: str) -> dict | None:
    """The scenes and direction of an approved handoff, or None when the text is not one or has too few usable scenes."""
    if not text or "متن روی صفحه:" not in text:       # the scene lines below only ever come from a handoff
        return None
    lines = []
    for raw in text.splitlines():
        found = SCENE.match(raw)
        if found and found["say"].strip():
            lines.append({"seconds": float(found["sec"]), "see": found["see"], "title": found["title"], "say": found["say"]})
    if len(lines) < 3:
        return None
    return {"lines": lines, "concept": _field(text, "ایده:"), "hook": _field(text, "هوک (دو ثانیه‌ی اول):"), "style": _field(text, "سبک بصری:"),
            "mood": _field(text, "حس و حال:"), "music": _field(text, "موسیقی:"), "cta": _field(text, "دعوت به اقدام:")}


def adopt(text: str, duration_s: float) -> CreativePlan | None:
    data = parse(text)
    if not data:
        return None
    draft = ScriptDraft(
        structure="hook, story beats, call to action", visual_language="; ".join(x for x in (data["style"], data["music"] and f"music: {data['music']}") if x),
        pacing=data["mood"], ending=data["cta"],
        lines=[ScriptLine(id=f"L{i}", role="hook" if i == 1 else "cta" if i == len(data["lines"]) and data["cta"] else "beat", narration=item["say"], title=item["title"],
                          hear=item["say"], see=item["see"], why_visual="chosen by the approved idea", emotion=data["mood"], visual_type="kinetic_type" if not item["see"] else "concept")
               for i, item in enumerate(data["lines"][:10], 1)])
    from .script import to_beats
    beats = to_beats(draft, duration_s)
    topic = data["concept"] or beats[0].narration
    brief = ContentBrief(kind="idea", topic=topic, core_message=data["concept"] or topic, goal="an Instagram reel the person already approved", tone=data["mood"],
                         genre="explainer", must_not=["rewrite the approved narration", "change the approved on-screen text"])
    chosen = Concept(id="A", name=(data["concept"] or topic)[:80], angle=data["concept"] or topic, hook=data["hook"] or beats[0].narration, beats=beats,
                     visual_language=draft.visual_language, pacing=draft.pacing, payoff=data["cta"], feeling=data["mood"], structure=draft.structure)
    critique = Critique(chosen_id="A", verdict="approved by the person")
    notes = (f"Creative direction — the person approved this idea in Instagram GPT; produce it as written.\nAngle: {chosen.angle}\nHook: {chosen.hook}\n"
             f"Look: {draft.visual_language}\nMood: {data['mood']}\nUse the approved narration and on-screen text word for word.")
    return CreativePlan(kind="idea", brief=brief, concepts=[chosen], critique=critique, chosen=chosen, director_notes=notes, models=["approved-script"])
