"""One continuous narration for every engine that voices a film (the explainer / motion engine and the product reel designer).

The whole script is read in a single take (`brain.localize.continuous_narration`); the scenes are then fitted to that take: each scene starts where its first word is
heard (a beat early) and ends where the next begins, and every scene receives the time of each of its words so its motion can land on them. Nothing is cut apart
and glued back together, so the voice keeps its rhythm and tone.
"""
from __future__ import annotations

PREROLL = 0.3          # silence before the voice starts
LEAD = 0.35            # a scene's picture changes this long before its first word is heard
TAIL = 0.9             # how long the last picture holds after the last word


class NarrationFailed(RuntimeError):
    """The narration could not be made. It is shown in the log and stops the build; it is never replaced by another way of voicing the film."""


def fit(take: dict) -> dict:
    """Scene boundaries and word cues from a take: {"starts", "ends", "duration", "cues", "relative", "clip_starts", "audio"}."""
    lines = take["lines"]
    starts = [0.0]
    for line in lines[1:]:
        starts.append(max(starts[-1] + 0.8, PREROLL + line["start"] - LEAD))
    last_end = max(PREROLL + lines[-1]["end"] + TAIL, PREROLL + take["total"] + 0.3)
    ends = starts[1:] + [last_end]
    cues = [[{"word": w["word"], "t": round(max(0.0, PREROLL + w["start"] - begin), 2)} for w in line["words"]] for line, begin in zip(lines, starts)]
    relative = [[{"word": w["word"], "start": round(w["start"] - line["words"][0]["start"], 3), "end": round(w["end"] - line["words"][0]["start"], 3)} for w in line["words"]] for line in lines]
    return {"starts": [round(x, 2) for x in starts], "ends": [round(x, 2) for x in ends], "duration": round(last_end, 2), "cues": cues, "relative": relative,
            "clip_starts": [round(PREROLL + line["start"], 3) for line in lines],
            "audio": [{"path": str(take["audio"]), "start": PREROLL, "duration": round(take["total"], 2)}]}


def apply(plan, fitted: dict):
    """The plan with every scene timed and cued from the take."""
    scenes = [scene.model_copy(update={"start": begin, "end": end, "cues": cues})
              for scene, begin, end, cues in zip(plan.scenes, fitted["starts"], fitted["ends"], fitted["cues"])]
    return plan.model_copy(update={"scenes": scenes, "duration": fitted["duration"]})


def chosen_voice(storyboard: dict, texts: list[str], user=None) -> tuple[str, str]:
    """(voice id, style) for a storyboard: the narrator the person picked or named in the request, else the studio's casting for this content, once for the film."""
    from brain.localize import narrator_for, narrator_ids
    voice = str(storyboard.get("narrator") or "")
    if voice not in narrator_ids():
        voice = narrator_for(str(storyboard.get("prompt") or ""), user)
    return voice, str(storyboard.get("voice_style") or "")


def voice(storyboard: dict, texts: list[str], folder, user=None) -> dict:
    """The take for `texts` (one per scene), cached by its text and voice; raises NarrationFailed with the reason in Persian."""
    from brain import localize
    from creative.audio import persian
    voice_id, style = chosen_voice(storyboard, texts, user)
    spoken = [persian.speakable(text, {}) for text in texts]
    try:
        return localize.continuous_narration(spoken, folder, voice_id, style)
    except Exception as exc:
        if type(exc).__name__ == "VoiceError":                # plan, credit, key or voice: the plain reason, nothing technical
            raise NarrationFailed(f"ساخت نریشن انجام نشد: {exc}") from exc
        reason = "اعتبار ElevenLabs کافی نیست" if "quota" in str(exc).lower() else "ارائه‌دهندهٔ صدا پاسخ نداد"
        raise NarrationFailed(f"ساخت نریشن انجام نشد: {reason} ({str(exc)[:140]}). دوباره امتحان کنید.") from exc
