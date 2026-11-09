"""What the render engines can actually do, in words a director can plan with.

A concept that needs something the engines cannot render is worthless, so the director is told the
real vocabulary (and the real limits) instead of being left to imagine them.
"""
from __future__ import annotations

TALKING_STYLES = {
    "talking_1": "Energetic personal-brand reel: pinned curiosity hook with highlighted words, punchy zoom accents on the "
                 "speaker, up to 3 black-and-white emotional moments, up to 2 short on-screen takeaways, word-synced captions, "
                 "cold-open teaser. Speaker stays full-frame. Best for charisma, opinions, motivation, personal brand.",
    "talking_2": "Educational split screen: speaker on the bottom, designed motion cards on the top half (concept diagram, "
                 "statistic, comparison, steps, UI showcase, media collage, chat thread, map route, spec callout, kinetic type, "
                 "before/after) timed to the speech, plus chips for tool names or steps. Best for teaching, lists, processes, tools.",
    "talking_3": "Cinematic split: like talking_2 but still-life photographic pictures and elegant chapter title cards. "
                 "Best for emotional stories, big ideas, reflective narratives.",
}

NOT_AVAILABLE = ("generated or stock video footage, face or voice cloning, 3D scenes, logos or brand assets the user "
                 "has not provided, claims that are not in the source.")


def recipe_digest(limit: int = 20) -> str:
    try:
        from engine.motion_recipes import RECIPES
    except Exception:
        return ""
    rows = [f"- {r.id} ({r.renderer}): {r.best_for}; avoid: {r.avoid_when}" for r in RECIPES[:limit]]
    return "Motion recipes the renderer can build:\n" + "\n".join(rows)


def talk_capabilities(only_style: str | None = None) -> str:
    """With ``only_style`` the creator already fixed the look: plan only what that style can render."""
    items = {only_style: TALKING_STYLES[only_style]} if only_style in TALKING_STYLES else TALKING_STYLES
    styles = "\n".join(f"- {key}: {text}" for key, text in items.items())
    lead = ("The creator fixed this style; use it as style_hint and plan only what it can render" if only_style in TALKING_STYLES
            else "Talking-reel styles (pick exactly one id as style_hint)")
    return f"{lead}:\n{styles}\n\n{recipe_digest()}\n\nNot available: {NOT_AVAILABLE}"


def product_capabilities() -> str:
    motion='Motion.so is NOT available. Use motion_engine=default.'
    try:
        from brain.motion_so import configured
        if configured():
            motion=('Motion.so is configured: motion_engine=motion_so may be chosen per scene for silent, '
                'code-based diagrams/line-art motion, light effort; it consumes external credits and requires '
                'user approval before execution. Captions/narration are added by EditorGPT. '
                'Do not choose it for stock footage, image editing or a scene requiring unverified media capabilities.')
    except (ImportError,OSError):
        pass
    return ("Vertical 9:16 reel built from still images (user uploads or images found on the supplied page, optionally generated "
            "stills) with Persian narration, music, animated Persian text overlays, Ken-Burns and layered motion, "
            "typographic scenes. default uses the existing fixed-code native/Remotion renderer, not arbitrary generated React. "
            "Do not claim it can execute every HyperFrames recipe on product images. "
            +motion+f"\n\nNot available: {NOT_AVAILABLE}")
