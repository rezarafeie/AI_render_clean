"""What each speech model can actually be told, and how a director's wishes are reduced to that.

Capabilities are what this installation is configured to rely on, not a guarantee from the provider. A wish a model cannot
carry is dropped and reported; markup is never put into the spoken text for a model that would read it aloud.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import VoiceGenerationRequest
from .persian import speakable


@dataclass(frozen=True)
class VoiceCapabilities:
    languages: frozenset
    inline_tags: bool = False          # audio tags such as [calm] are interpreted, not spoken
    pauses: bool = False               # explicit pause markup is interpreted
    word_timestamps: bool = False


CAPABILITIES: dict[str, VoiceCapabilities] = {
    "elevenlabs:eleven_v3": VoiceCapabilities(frozenset({"fa", "en"}), inline_tags=True, pauses=True, word_timestamps=True),
    "elevenlabs:eleven_multilingual_v2": VoiceCapabilities(frozenset({"fa", "en"}), word_timestamps=True),
}

TAGS = {"confident": "confident", "excited": "excited", "curious": "curious", "mysterious": "mysterious", "serious": "serious",
        "calm": "calm", "dramatic": "dramatic", "urgent": "urgent", "humorous": "humorous", "empathetic": "empathetic",
        "friendly": "friendly", "inspirational": "inspirational", "cinematic": "dramatic", "persuasive": "confident",
        "educational": "calm", "conversational": "friendly"}


class UnsupportedLanguage(ValueError):
    pass


@dataclass
class Prepared:
    text: str
    applied: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)


def known(model_key: str) -> VoiceCapabilities:
    """Unknown models get no optional features: the safe reading of "not stated"."""
    return CAPABILITIES.get(model_key, VoiceCapabilities(frozenset()))


def choose(language: str, candidates: list[str]) -> str:
    """First candidate model that supports the language. Never falls back to one that does not (no English-only model for Persian)."""
    base = language.split("-")[0].lower()
    for key in candidates:
        if base in known(key).languages:
            return key
    raise UnsupportedLanguage(f"no configured voice model supports '{language}'")


def prepare(request: VoiceGenerationRequest, model_key: str) -> Prepared:
    caps = known(model_key)
    base = request.language.split("-")[0].lower()
    if base not in caps.languages:
        raise UnsupportedLanguage(f"{model_key} is not configured for '{request.language}'")
    direction = request.direction
    text = speakable(request.text, direction.pronunciations)
    out = Prepared(text=text)
    if direction.pronunciations:
        out.applied.append("pronunciations (text substitution)")
    tag = TAGS.get(direction.emotion or "")
    if tag and caps.inline_tags:
        out.text = f"[{tag}] {out.text}"; out.applied.append(f"emotion:{direction.emotion}")
    elif direction.emotion:
        out.dropped.append(f"emotion:{direction.emotion} (the model has no audio tags)")
    if direction.pauses:
        if caps.pauses:
            words = out.text.split(" ")
            for p in sorted(direction.pauses, key=lambda x: -x.after_word):
                if 0 <= p.after_word < len(words):
                    words[p.after_word] += f' <break time="{p.duration_ms / 1000:.1f}s" />'
            out.text = " ".join(words); out.applied.append("pauses")
        else:
            out.dropped.append("pauses (the model has no pause markup)")
    if abs(direction.pace - 1.0) > 0.05:
        out.dropped.append(f"pace:{direction.pace} (applied after generation by retiming, not by the model)")
    return out
