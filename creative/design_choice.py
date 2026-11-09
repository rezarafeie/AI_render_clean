"""How sure was the director of the design? A reference decides it; a clear winner decides it; a near tie is put to the person (never silently picked)."""
from __future__ import annotations

SCORE_KEYS = ("hook_strength", "originality", "fit_to_content", "feasibility", "faithfulness")
CLEAR_MARGIN = 1.0           # points (0-10) the chosen concept must lead by; less is a doubt worth asking about


def _mean(score) -> float:
    return sum(float(getattr(score, key, 0) or 0) for key in SCORE_KEYS) / len(SCORE_KEYS)


def assess(plan) -> dict:
    """{mode: reference | clear | unsure, margin, chosen, alternatives:[{name, angle, hook, visual_language}]} for a CreativePlan."""
    chosen = getattr(plan, "chosen", None)
    reference = getattr(plan, "reference", None)
    scores = {s.id: _mean(s) for s in getattr(getattr(plan, "critique", None), "scores", []) or []}
    others = [c for c in getattr(plan, "concepts", []) or [] if chosen is not None and c.id != chosen.id]
    ranked = sorted(others, key=lambda c: -scores.get(c.id, 0))
    margin = (scores.get(chosen.id, 0) - scores.get(ranked[0].id, 0)) if chosen is not None and ranked and chosen.id in scores and ranked[0].id in scores else None
    if reference is not None and getattr(reference, "usable", False):
        mode = "reference"
    elif margin is None or margin >= CLEAR_MARGIN:
        mode = "clear"
    else:
        mode = "unsure"
    close = [c for c in ranked if margin is not None and scores.get(chosen.id, 0) - scores.get(c.id, 0) < CLEAR_MARGIN + 0.5][:2]
    return {"mode": mode, "margin": margin, "chosen": getattr(chosen, "name", ""),
            "alternatives": [{"name": c.name, "angle": c.angle, "hook": c.hook, "visual_language": c.visual_language} for c in close]}


def note(info: dict, short=lambda text, n: str(text)[:n]) -> str:
    """The sentence(s) the scenario message adds about the design decision ('' when the director was sure and nothing needs saying)."""
    if info["mode"] == "reference":
        return "طراحی از رفرنس شما پیروی می‌کند؛ ساختار و جزئیات صحنه‌ها خلاقانه و متناسب با همین محتوا نوشته شده‌اند."
    if info["mode"] != "unsure" or not info["alternatives"]:
        return ""
    lines = [f"**در انتخاب طراحی مطمئن نبودم:** «{info['chosen']}» را انتخاب کردم، ولی گزینهٔ نزدیک دیگری هم بود."]
    for alt in info["alternatives"]:
        lines.append(f"- «{alt['name']}»: {short(alt['angle'], 150)}" + (f" — زبان بصری: {short(alt['visual_language'], 110)}" if alt.get("visual_language") else ""))
    lines.append("اگر یکی از این‌ها را می‌خواهی اسمش را بنویس، یا طراحی دلخواهت را توضیح بده، یا یک رفرنس (عکس یا ویدیو) بفرست تا به همان نزدیک شود.")
    return "\n".join(lines)
