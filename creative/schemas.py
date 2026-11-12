"""Typed contracts of the Creative Engine. Tolerant on input (models vary), strict on output."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreativeUnavailable(RuntimeError):
    """The creative layer could not produce a validated result. Callers fall back to the standard pipeline."""


def _text(value: Any, limit: int = 600) -> str:
    return " ".join(str(value or "").split())[:limit]


def _texts(value: Any, limit: int = 8, size: int = 300) -> list[str]:
    if isinstance(value, str):
        value = [value]
    return [_text(v, size) for v in (value or []) if _text(v, size)][:limit]


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


class KeyMoment(_Model):
    i: int = Field(ge=0)
    why: str = ""
    emotion: str = ""

    @field_validator("why", "emotion", mode="before")
    @classmethod
    def _clean(cls, value):
        return _text(value, 240)


Kind = Literal["talk", "product", "idea", "images"]


class ContentBrief(_Model):
    kind: Kind = "talk"
    topic: str
    core_message: str
    audience: str = ""
    goal: str = ""
    tone: str = ""
    genre: Literal["education", "story", "motivation", "sales", "explainer", "showcase"] = "explainer"
    emotional_arc: list[str] = Field(default_factory=list)
    key_moments: list[KeyMoment] = Field(default_factory=list)
    proof_points: list[str] = Field(default_factory=list)   # facts actually present in the source
    must_not: list[str] = Field(default_factory=list)       # claims/edits that would distort the source
    must_name: list[str] = Field(default_factory=list)      # the 2-4 terms a viewer must hear to know what the video is about

    @field_validator("topic", "core_message", "audience", "goal", "tone", mode="before")
    @classmethod
    def _clean(cls, value):
        return _text(value)

    @field_validator("emotional_arc", "proof_points", "must_not", "must_name", mode="before")
    @classmethod
    def _list(cls, value):
        return _texts(value)

    @field_validator("key_moments", mode="before")
    @classmethod
    def _moments(cls, value):
        return [v for v in (value or []) if isinstance(v, dict)][:8]


class Beat(_Model):
    role: str = ""                 # hook | setup | claim | proof | turn | payoff | cta ...
    intent: str = ""               # what the viewer should feel/understand here
    visual: str = ""               # concrete on-screen idea (not "nice visuals")
    motion: str = ""               # motion/typography treatment, in terms the engine can render
    sentence: int | None = None    # transcript sentence index when the source is a talk
    title: str = ""
    narration: str = ""
    source_asset_index: int | None = Field(default=None, ge=0)
    visual_type: Literal["concept", "stat", "comparison", "steps", "ui_showcase", "media_collage",
                         "chat", "map_route", "spec_callout", "kinetic_type", "before_after"] = "concept"
    items: list[str] = Field(default_factory=list, max_length=4)
    duration_weight: float = Field(default=1, gt=0, le=10)
    motion_engine: Literal['default','motion_so'] = 'default'
    # Visual-first scriptwriting: every line says what is heard, what is seen, and why.
    line_id: str = ""              # the script line this scene was made for ("L3")
    why_visual: str = ""           # why this picture, for this sentence
    emotion: str = ""              # what the viewer should feel here
    focus: str = ""                # the element that guides attention
    link_prev: str = ""            # how this scene follows from the previous one
    reference_trait: str = ""      # which trait of the reference style this scene carries, when a reference exists

    @field_validator("role", "intent", "visual", "motion", "title", "narration", "line_id", "why_visual", "emotion", "focus",
                     "link_prev", "reference_trait", mode="before")
    @classmethod
    def _clean(cls, value):
        return _text(value, 280)

    @field_validator("sentence", mode="before")
    @classmethod
    def _index(cls, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


class Concept(_Model):
    id: str
    name: str
    angle: str                      # the creative idea in 1–2 sentences
    hook: str                       # exactly what happens in the first 2–3 seconds
    outline: list[str] = Field(default_factory=list)   # compact beat sketch from the proposal stage
    beats: list[Beat] = Field(default_factory=list)    # full beats, filled by the expansion stage
    visual_language: str = ""
    pacing: str = ""
    style_hint: str | None = None   # an existing engine style id (talk only)
    why_it_works: str = ""
    risks: str = ""
    structure: str = ""             # one of STRUCTURES, chosen for this goal and content (not one fixed template)
    payoff: str = ""                # the closing line/image the whole video builds toward
    feeling: str = ""               # what the viewer should feel at the end

    @field_validator("id", "name", "angle", "hook", "visual_language", "pacing", "why_it_works", "risks", "structure", "payoff", "feeling", mode="before")
    @classmethod
    def _clean(cls, value):
        return _text(value, 500)

    @field_validator("beats", mode="before")
    @classmethod
    def _beats(cls, value):
        return [v.model_dump() if isinstance(v, Beat) else v for v in (value or []) if isinstance(v, (dict,Beat))][:9]

    @field_validator("outline", mode="before")
    @classmethod
    def _outline(cls, value):
        return _texts(value, 7, 160)


SCORE_KEYS = ("hook_strength", "originality", "fit_to_content", "feasibility", "faithfulness")


class ConceptScore(_Model):
    id: str
    hook_strength: float = 0
    originality: float = 0
    fit_to_content: float = 0
    feasibility: float = 0
    faithfulness: float = 0
    note: str = ""

    @field_validator(*SCORE_KEYS, mode="before")
    @classmethod
    def _score(cls, value):
        try:
            return max(0.0, min(10.0, float(value)))
        except (TypeError, ValueError):
            return 0.0

    @property
    def total(self) -> float:
        # Faithfulness and feasibility are gates as much as virtues: weight them up.
        return (self.hook_strength * 1.3 + self.originality + self.fit_to_content * 1.2
                + self.feasibility * 1.2 + self.faithfulness * 1.3)


class Critique(_Model):
    scores: list[ConceptScore] = Field(default_factory=list)
    chosen_id: str
    verdict: str = ""
    improvements: list[str] = Field(default_factory=list)
    improved_hook: str = ""

    @field_validator("verdict", "improved_hook", mode="before")
    @classmethod
    def _clean(cls, value):
        return _text(value, 500)

    @field_validator("improvements", mode="before")
    @classmethod
    def _list(cls, value):
        return _texts(value, 6, 300)


STRUCTURES = ("hook_tension_reframe_payoff", "problem_agitation_solution", "curiosity_gap_reveal", "before_after",
              "contrarian_insight", "micro_story", "emotional_buildup", "educational_reveal", "product_demonstration",
              "benefit_commercial")

CRITERIA = ("hook_strength", "originality", "clarity", "emotional_impact", "audience_relevance", "narrative_coherence",
            "curiosity", "memorability", "natural_persian", "visual_potential", "timing", "payoff_quality", "reference_alignment")


class CriterionScore(_Model):
    criterion: str
    score: float = 0
    reason: str = ""
    evidence: str = ""             # a quote from the script (or a measured fact) that justifies the score
    verified: bool = True          # False when the evidence is not actually in the script: the score is then capped

    @field_validator("score", mode="before")
    @classmethod
    def _score(cls, value):
        try:
            return max(0.0, min(10.0, float(value)))
        except (TypeError, ValueError):
            return 0.0

    @field_validator("criterion", "reason", "evidence", mode="before")
    @classmethod
    def _clean(cls, value):
        return _text(value, 400)


class ScriptReview(_Model):
    scores: list[CriterionScore] = Field(default_factory=list)
    verdict: Literal["ship", "rewrite"] = "rewrite"
    must_fix: list[str] = Field(default_factory=list)
    change: list[Literal["angle", "structure", "hook", "ending", "cut", "tone"]] = Field(default_factory=list)
    summary: str = ""

    @field_validator("must_fix", mode="before")
    @classmethod
    def _list(cls, value):
        return _texts(value, 8, 300)

    @field_validator("change", mode="before")
    @classmethod
    def _change(cls, value):
        allowed = {"angle", "structure", "hook", "ending", "cut", "tone"}
        return [v for v in (value if isinstance(value, list) else [value]) if v in allowed]

    @field_validator("summary", mode="before")
    @classmethod
    def _summary(cls, value):
        return _text(value, 600)


class ScriptLine(_Model):
    id: str = ""
    role: str = ""
    narration: str = ""
    title: str = ""
    hear: str = ""
    see: str = ""
    why_visual: str = ""
    motion: str = ""
    emotion: str = ""
    focus: str = ""
    link_prev: str = ""
    visual_type: Literal["concept", "stat", "comparison", "steps", "ui_showcase", "media_collage",
                         "chat", "map_route", "spec_callout", "kinetic_type", "before_after"] = "concept"
    items: list[str] = Field(default_factory=list, max_length=4)
    source_asset_index: int | None = Field(default=None, ge=0)
    reference_trait: str = ""
    motion_engine: Literal['default', 'motion_so'] = 'default'

    @field_validator("id", "role", "narration", "title", "hear", "see", "why_visual", "motion", "emotion", "focus", "link_prev",
                     "reference_trait", mode="before")
    @classmethod
    def _clean(cls, value):
        return _text(value, 360)

    @field_validator("items", mode="before")
    @classmethod
    def _items(cls, value):
        return _texts(value, 4, 80)


class ScriptDraft(_Model):
    structure: str = ""
    lines: list[ScriptLine] = Field(default_factory=list)
    ending: str = ""
    visual_language: str = ""
    pacing: str = ""

    @field_validator("lines", mode="before")
    @classmethod
    def _lines(cls, value):
        return [v.model_dump() if isinstance(v, ScriptLine) else v for v in (value or []) if isinstance(v, (dict, ScriptLine))][:10]

    @field_validator("structure", "ending", "visual_language", "pacing", mode="before")
    @classmethod
    def _clean(cls, value):
        return _text(value, 400)


class ReferenceProfile(_Model):
    """What was actually observed in a reference video. Measured fields come from the file, described fields from sampled frames."""
    status: Literal["analyzed", "unavailable"] = "analyzed"
    reason: str = ""                       # why it is unavailable (shown to the user)
    source: str = ""                       # the link or file name
    duration_s: float = 0
    shot_count: int = 0
    avg_shot_s: float = 0
    shot_lengths_s: list[float] = Field(default_factory=list)
    cuts_per_second: float = 0
    fps: float = 0
    palette: list[str] = Field(default_factory=list)      # dominant colours measured from frames, "#RRGGBB"
    typography: str = ""
    composition: str = ""
    motion_language: str = ""
    transitions: str = ""
    visual_density: str = ""
    hook_structure: str = ""
    narrative_structure: str = ""
    sound: str = ""
    overall_feel: str = ""
    frames_used: int = 0
    frame_table: list[dict] = Field(default_factory=list)   # per sampled frame: {t, shot, text, change}; what was seen, frame by frame
    transcript: str = ""                                      # what the reference says (speech to text); the most reliable source of its subject

    @field_validator("reason", "source", "typography", "composition", "motion_language", "transitions", "visual_density",
                     "hook_structure", "narrative_structure", "sound", "overall_feel", mode="before")
    @classmethod
    def _clean(cls, value):
        return _text(value, 500)

    @property
    def usable(self) -> bool:
        return self.status == "analyzed"


class ScriptReport(_Model):
    """How the script was reached: shown to the user, never a vanity score."""
    attempts: int = 1
    structure: str = ""
    speech_seconds: float = 0
    budget_seconds: float = 0
    timing_ok: bool = True
    review: ScriptReview | None = None
    history: list[dict] = Field(default_factory=list)      # per attempt: what the critic asked to change, and what changed
    deterministic: list[str] = Field(default_factory=list) # measured problems found in the final script (empty = none)
    hard_problems: list[str] = Field(default_factory=list) # the measured problems that force a rewrite (length, scenes, missing subject...)
    stopped: str = ""                                       # why the loop ended: shipped | cap | unavailable | time


class CreativePlan(_Model):
    schema_version: int = 2
    kind: Kind
    brief: ContentBrief
    concepts: list[Concept]
    critique: Critique
    chosen: Concept
    style: str | None = None
    director_notes: str = ""                    # compact guidance the engines receive
    resource_choices: list[dict] = Field(default_factory=list)
    script: ScriptReport | None = None
    reference: ReferenceProfile | None = None
    models: list[str] = Field(default_factory=list)
    elapsed_s: float = 0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def public(self) -> dict:
        """What may be stored on a job and shown to the user: the decision and its reasons, not raw prompts."""
        return {
            "schema_version": self.schema_version,
            "kind": self.kind, "style": self.style, "created_at": self.created_at, "elapsed_s": self.elapsed_s,
            "brief": self.brief.model_dump(),
            "chosen": self.chosen.model_dump(),
            "alternatives": [{"id": c.id, "name": c.name, "angle": c.angle, "hook": c.hook, "style_hint": c.style_hint,
                              "visual_language": c.visual_language, "pacing": c.pacing, "why_it_works": c.why_it_works}
                             for c in self.concepts if c.id != self.chosen.id],
            "verdict": self.critique.verdict, "director_notes": self.director_notes,
            "resource_choices": self.resource_choices,
            "critique":self.critique.model_dump(),
            "script": self.script.model_dump() if self.script else None,
            "reference": self.reference.model_dump() if self.reference else None,
        }
