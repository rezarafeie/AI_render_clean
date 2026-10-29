from typing import TypedDict, Literal
from pydantic import BaseModel, ConfigDict, Field


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: Literal["inspect_media", "inspect_url", "inspect_project", "analyze_talking_reel", "localize_video",
                  "create_storyboard", "modify_project", "render_approved_plan", "check_render_status",
                  "instagram_content_check", "discover_connected_app_tools", "read_connected_app"]
    arguments: dict = Field(default_factory=dict)
    label: str = Field(min_length=1, max_length=180)


class EditingPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=1800)
    steps: list[Step] = Field(default_factory=list, max_length=8)


class State(TypedDict, total=False):
    context: dict
    plan: dict
    index: int
    results: list[dict]
    waiting_project: str | None
    approved: bool
    finished: bool
    rounds: int
    healing: bool                 # the last tool step was rejected before anything was submitted: plan again with its error
    heal: int                     # how many times this run has replanned after a rejected step
    failed: list                  # signatures of the errors already seen (the same one twice means a loop: stop)
    plan_feedback: str | None
    heal_tools: list | None       # write tools the person already approved; a replan using the same ones is not asked again
