"""What the person taught the studio on the Style Learner and My Effects pages, handed to the engines that design motion (explainer / motion graphics and product reels).

Those two pages used to feed only the edit planner (brain/planner.py via app/jobs.py). The motion engines read none of it: a person could teach the studio their pace and
write rules like «calm down before the call to action» and every explainer ignored them. This turns the same data into the plain-language guidance the planner and the
scene designers already take as the REFERENCE STYLE. A reference video given in the chat always wins over it."""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)
MARK = "THE PERSON'S OWN HABITS"


def _learned_lines(user_id) -> list[str]:
    from app import style_store
    profile = style_store.load_profile(user_id)
    if not profile or profile.get("enabled") is False:
        return []
    learned = profile.get("learned_metrics") or {}
    if not learned.get("sufficient"):
        return []
    metrics, lines = learned.get("metrics") or {}, []
    cut, per_minute = metrics.get("cut_length_avg"), metrics.get("cuts_per_minute")
    if cut:
        lines.append(f"Pace: the reels this person learned from cut every {cut:g} s on average" + (f" ({per_minute:g} cuts a minute)" if per_minute else "")
                     + f"; give scenes about {max(2.5, min(float(cut), 6.0)):g} s (never below 2.5 s) and keep the energy of that pace.")
    early, late = metrics.get("pacing_early_avg"), metrics.get("pacing_late_avg")
    if early and late and abs(early - late) > 0.4:
        lines.append("Rhythm: cuts get " + ("faster" if late < early else "slower") + " toward the end in the reels they learned from; shape the film the same way.")
    density = metrics.get("caption_density_wps")
    if density:
        lines.append(f"Text density: about {density:g} words a second appear on screen in their reels; keep on-screen copy at that density.")
    return lines


def _rule_lines() -> list[str]:
    try:
        from engine.effects_v4 import MyEffectsPreset
        rules = MyEffectsPreset().rules
    except Exception as exc:
        log.warning("my effects rules not read: %s", str(exc)[:120])
        return []
    lines = []
    for rule in rules[:10]:
        text = str(rule.get("text") if isinstance(rule, dict) else rule).strip()
        if text:
            hard = isinstance(rule, dict) and rule.get("priority") == "hard"
            lines.append(f"{'MUST' if hard else 'Prefer'}: {text}")
    return lines


def motion_notes(user_id) -> str:
    """The person's learned pace and written rules as guidance text for the motion engines; '' when they taught the studio nothing."""
    lines: list[str] = []
    try:
        lines += _learned_lines(user_id)
    except Exception as exc:
        log.warning("learned style not read: %s", str(exc)[:120])
    rules = _rule_lines()
    if rules:
        lines.append("Their own rules for how a film should behave (written in Persian; apply them to scene order, emphasis and motion where they fit):")
        lines += rules
    return (MARK + " (learned from the reference reels they gave and the rules they wrote; follow them where they fit this film):\n" + "\n".join(f"- {line}" for line in lines)) if lines else ""
