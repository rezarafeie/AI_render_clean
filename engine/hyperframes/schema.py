"""Strict internal contract between the edit planner and HyperFrames."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class VisualBeat(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_-]+$")
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    anchor_word: str = ""
    visual_type: Literal[
        "concept", "stat", "comparison", "steps", "ui_showcase", "media_collage",
        "chat", "map_route", "spec_callout", "kinetic_type", "before_after",
    ] = "concept"
    title: str = Field(min_length=1, max_length=80)
    items: list[str] = Field(default_factory=list, max_length=4)
    layout: Literal["top_panel", "full_frame"] = "top_panel"
    accent: Literal["teal", "amber", "coral", "blue", "ink"] = "teal"
    registry_refs: list[str] = Field(default_factory=list, max_length=3)
    recipe_id: str = ""
    narrative_role: str = "evidence"
    motion_style: str = "slide"
    why: str = ""
    sentence_indices: list[int] = Field(default_factory=list)
    spoken: str = ""

    @model_validator(mode="after")
    def valid_range(self):
        if self.end <= self.start:
            raise ValueError("visual beat end must be after start")
        if self.end - self.start < 0.65:
            raise ValueError("visual beat must remain readable for at least 0.65 seconds")
        return self
