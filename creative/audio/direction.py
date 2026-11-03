"""The Creative Director's single audio plan: derived from the brief, the production directives and the script.

Rules only; a stated directive always wins over an inferred one, and what was inferred is listed in `notes`.
"""
from __future__ import annotations

import re

from .contracts import AudioDirectionPlan, Emotion, MixSettings, VoiceDirection
from .persian import is_persian

_INTENT = [
    (r"teaser|trailer|launch|reveal|تیزر|رونمایی|معرفی", ("persuasive product introduction", "confident", "cinematic modern", 0.7, "balanced")),
    (r"explain|tutorial|how to|آموزش|توضیح", ("educational explainer", "educational", "light neutral", 0.35, "none")),
    (r"story|documentary|emotional|داستان|مستند|احساسی", ("emotional storytelling", "empathetic", "ambient emotional", 0.4, "minimal")),
    (r"sale|offer|discount|urgent|تخفیف|فروش|فوری", ("promotional offer", "urgent", "upbeat rhythmic", 0.8, "dynamic")),
]
_VOICE_STYLE_EMOTION = {"calm": "calm", "serious": "serious", "energetic": "excited", "reflective": "empathetic"}
_PACE_ENERGY = {"calm": (0.92, 0.35), "serious": (0.97, 0.5), "energetic": (1.05, 0.85), "reflective": (0.9, 0.4)}


def plan(brief: str, directives, language: str | None = None) -> tuple[AudioDirectionPlan, list[str]]:
    notes: list[str] = []
    lang = language or ("fa-IR" if is_persian(brief) else "en-US")
    intent, emotion, mood, music_energy, sound = "general narrated video", "conversational", "neutral", 0.5, "minimal"
    for pattern, values in _INTENT:
        if re.search(pattern, brief or "", re.I):
            intent, emotion, mood, music_energy, sound = values; notes.append(f"intent inferred: {intent}"); break
    pace, energy = 1.0, 0.5
    if directives.style:
        emotion = _VOICE_STYLE_EMOTION.get(directives.style, emotion)
        pace, energy = _PACE_ENERGY.get(directives.style, (pace, energy))
    voice = VoiceDirection(emotion=emotion, intensity=0.7, pace=pace, energy=energy, pronunciations=dict(directives.pronunciations))
    mix = MixSettings(preset=directives.loudness if directives.loudness not in (None, "off") else "social_video")
    music_off = directives.music == "off"
    return AudioDirectionPlan(language=lang, creative_intent=intent, rhythm_mode=directives.rhythm or "speech_first", voice=voice,
                              music_mood=("" if music_off else directives.music_words or mood), music_energy=0.0 if music_off else music_energy,
                              sound_design=sound, mixing=mix), notes


def emotion_arc(lines: list[str], base: AudioDirectionPlan) -> list[dict]:
    """One direction per narrated line: a question opens curious, the last line lands confident, the rest keep the plan's emotion."""
    arc = []
    for index, line in enumerate(lines):
        emotion: Emotion | None = base.voice.emotion
        intensity, pace = base.voice.intensity, base.voice.pace
        if index == 0 and re.search(r"[?؟]\s*$", line.strip()):
            emotion, intensity, pace = "curious", 0.65, min(pace, 0.9)
        elif index == len(lines) - 1 and len(lines) > 1:
            emotion, intensity = "confident", max(intensity, 0.85)
        arc.append({"line": index + 1, "text": line, "emotion": emotion, "intensity": round(intensity, 2), "pace": round(pace, 2)})
    return arc
