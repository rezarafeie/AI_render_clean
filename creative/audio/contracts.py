"""Typed contracts shared by narration, music, rhythm, sound design and the mixer.

Time is always an integer number of milliseconds on one timeline; seconds appear only at the edges and are
converted with `ms()`, which rounds half up, so two modules never disagree by a rounding step.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EventType = Literal["word", "pause", "beat", "downbeat", "onset", "energy_peak", "music_transition", "sfx", "narrative_emphasis"]
Emotion = Literal["confident", "excited", "curious", "mysterious", "serious", "educational", "conversational", "friendly", "persuasive",
                  "inspirational", "cinematic", "calm", "dramatic", "urgent", "humorous", "empathetic"]
RhythmMode = Literal["speech_first", "music_first", "balanced", "cinematic", "custom"]


def ms(seconds: float) -> int:
    """Seconds to whole milliseconds, rounding half up (never banker's rounding)."""
    return int((Decimal(str(seconds)) * 1000).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def frame(time_ms: int, fps: int) -> int:
    """The frame a millisecond falls in (floor): a cue never lands before its time."""
    return (time_ms * fps) // 1000


class AudioTimingEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    type: EventType
    time_ms: int = Field(ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    importance: float | None = Field(default=None, ge=0, le=1)
    source_asset_id: str | None = None
    metadata: dict = Field(default_factory=dict)


class PauseInstruction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    after_word: int = Field(ge=0)
    duration_ms: int = Field(ge=50, le=5000)


class VoiceDirection(BaseModel):
    """What the director wants. Providers support different parts; the rest is dropped and reported, never guessed."""
    model_config = ConfigDict(extra="forbid")
    emotion: Emotion | None = None
    intensity: float = Field(default=0.5, ge=0, le=1)
    pace: float = Field(default=1.0, ge=0.5, le=1.5)
    energy: float = Field(default=0.5, ge=0, le=1)
    speaking_style: str = ""
    pauses: list[PauseInstruction] = Field(default_factory=list)
    pronunciations: dict[str, str] = Field(default_factory=dict)


class VoiceGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=20000)
    language: str = Field(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    voice_id: str | None = None
    provider: str | None = None
    direction: VoiceDirection = Field(default_factory=VoiceDirection)
    target_duration_ms: int | None = Field(default=None, gt=0)
    output_format: str = "mp3"


class MixSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preset: Literal["instagram_reels", "tiktok", "youtube", "podcast", "social_video", "custom"] = "social_video"
    auto_ducking: bool = True
    music_gain_db: float = Field(default=-10.0, ge=-40, le=0)
    ducking_depth_db: float = Field(default=12.0, ge=0, le=30)


class AudioDirectionPlan(BaseModel):
    """The Creative Director's single plan for all audio decisions of one video."""
    model_config = ConfigDict(extra="forbid")
    language: str = "fa-IR"
    creative_intent: str = ""
    rhythm_mode: RhythmMode = "speech_first"
    voice: VoiceDirection = Field(default_factory=VoiceDirection)
    music_mood: str = ""
    music_instrumental: bool = True
    music_energy: float = Field(default=0.5, ge=0, le=1)
    sound_design: Literal["none", "minimal", "balanced", "dynamic", "cinematic"] = "minimal"
    mixing: MixSettings = Field(default_factory=MixSettings)
