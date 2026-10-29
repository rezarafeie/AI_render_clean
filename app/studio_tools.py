"""Typed allow-listed tools used by the Video Studio orchestrator.

The model may propose a tool name and arguments, but only this registry can
touch project engines.  No shell or arbitrary endpoint execution is exposed.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InspectMediaInput(ToolInput):
    path: str


class InspectUrlInput(ToolInput):
    url: str
    output_dir: str


class ResourceSearchInput(ToolInput):
    query: str = Field(default="", max_length=300)
    engine: str | None = None
    availability: str | None = None
    limit: int = Field(default=6, ge=1, le=12)


def _search_resources(args: ResourceSearchInput) -> dict:
    from creative.resources import search_resources
    return search_resources(args.query, engine=args.engine, availability=args.availability, limit=args.limit)


class LocalizeInput(ToolInput):
    source_path: str
    filename: str
    user_key: str
    request: str = Field(default='',max_length=2000)


class TalkingInput(ToolInput):
    source_path: str
    filename: str
    user_key: str
    style: str | None = None      # None: the creative director chooses from the content
    request: str = Field("", max_length=2000)
    transcript: dict | None = None    # a transcript prepared by long-video discovery: the clip is not transcribed again


class ContentInput(ToolInput):
    prompt: str = Field(min_length=3, max_length=12_000)
    user_key: str
    provider: str
    language: str = "fa"
    source_assets: list[str] = Field(default_factory=list, max_length=20)
    creative_brief: dict[str, str] = Field(default_factory=dict)
    creative_plan: dict | None = None
    asset_catalog: list[dict] | None = None
    duration: float = Field(default=30, ge=15, le=90)

    @field_validator("duration", mode="before")
    @classmethod
    def _fit_duration(cls, value):
        """A plan that asks for 5 s or 120 s gets the nearest length the engine supports instead of failing the whole build."""
        try:
            return min(90.0, max(15.0, float(value)))
        except (TypeError, ValueError):
            return 30.0


class ProjectRefInput(ToolInput):
    engine: str
    external_ref: str


class InstagramContentCheckInput(ToolInput):
    operation: str = Field(pattern=r"^(hook|beats|caption|humanize|audit_text|swipe)$")
    text: str = Field(min_length=1, max_length=20_000)
    language: str = Field(pattern=r"^(fa|en)$")
    wpm: float = Field(default=150, ge=60, le=300, allow_inf_nan=False)
    target: float | None = Field(default=None, ge=1, le=600, allow_inf_nan=False)


def _instagram_content_check(args: InstagramContentCheckInput) -> dict:
    from hermes.services.instagram_quality import evaluate
    return evaluate(args.operation, args.text, args.language, wpm=args.wpm, target=args.target)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[ToolInput]
    permission: str
    expensive: bool
    idempotent: bool
    handler: Callable[[ToolInput], dict]

    def public(self) -> dict:
        return {"name": self.name, "description": self.description,
                "input_schema": self.input_model.model_json_schema(),
                "permission": self.permission, "expensive": self.expensive,
                "idempotent": self.idempotent}


def _inspect_media(args: InspectMediaInput) -> dict:
    from engine.probe import probe
    path = Path(args.path).resolve()
    if not path.is_file(): raise FileNotFoundError("media file not found")
    info = probe(path)
    video = next((item for item in info.get("streams", []) if item.get("codec_type") == "video"), {})
    audio = next((item for item in info.get("streams", []) if item.get("codec_type") == "audio"), {})
    return {"duration": float(info.get("format", {}).get("duration") or 0),
            "width": int(video.get("width") or 0), "height": int(video.get("height") or 0),
            "has_audio": bool(audio), "format": info.get("format", {}).get("format_name")}


def _inspect_url(args: InspectUrlInput) -> dict:
    from app.studio_url import inspect_page
    return inspect_page(args.url, Path(args.output_dir))


def _localize(args: LocalizeInput) -> dict:
    from app import localize
    with open(Path(args.source_path), "rb") as source:
        state = localize.create(args.user_key, args.filename, source, "", None)
    state['creative_plan']={'schema_version':2,'kind':'localize','request':args.request,
        'limits':['Existing OCR covers and retypes captions; arbitrary graphic recreation is not implemented.']}
    localize.save(state)
    localize.start_analyze(state["id"])
    return {"external_ref": state["id"], "status": "analyzing"}


def _talking(args: TalkingInput) -> dict:
    from app import jobs, talking_reel
    job = jobs.create_job(user_id=args.user_key)
    with open(Path(args.source_path), "rb") as source:
        jobs.save_raw(job, args.filename, source, expected_size=Path(args.source_path).stat().st_size)
    if args.transcript and args.transcript.get("words"):
        from brain.transcribe import file_hash
        seeded = {**args.transcript, "file_hash": file_hash(job.dir / "raw" / job.raw_name), "requested_language": "fa", "engine": "whisper"}
        (job.dir / "transcript.json").write_text(json.dumps(seeded, ensure_ascii=False))
    talking_reel.analyze(job.dir, job.dir / "raw" / job.raw_name, style=args.style, request=args.request)
    return {"external_ref": job.id, "status": "analyzing", "style": args.style}


def _content(args: ContentInput) -> dict:
    from brain.content_creator import create_content
    result = create_content(prompt=args.prompt, content_type="reel", language=args.language,
                            style="rafiei_reel", provider_name=args.provider,
                            creative_brief=args.creative_brief, user_id=args.user_key,
                            source_assets=[Path(item) for item in args.source_assets],
                            creative_plan=args.creative_plan,asset_catalog=args.asset_catalog,duration=args.duration)
    return {"external_ref": result["job_id"], "storyboard": result["storyboard"],
            "status": "storyboard_ready"}


def _status(args: ProjectRefInput) -> dict:
    if args.engine == "localize":
        from app.localize import load, public
        return public(load(args.external_ref))
    if args.engine == "talking":
        from app import jobs, talking_reel
        job = jobs.get(args.external_ref)
        if not job: raise KeyError(args.external_ref)
        return talking_reel.public(talking_reel.load(job.dir))
    if args.engine == "motion":
        from app import jobs
        from brain.content_creator import get_storyboard_status
        job = jobs.get(args.external_ref)
        if not job: raise KeyError(args.external_ref)
        return {"generation": get_storyboard_status(job), "render": job.render.__dict__,
                "storyboard": (Path(job.dir) / "storyboard.json").is_file()}
    raise ValueError("unsupported engine")


def _cancel(args: ProjectRefInput) -> dict:
    if args.engine == "localize":
        from app.localize import cancel
        return cancel(args.external_ref)
    if args.engine == "talking":
        from app import jobs, talking_reel
        job = jobs.get(args.external_ref)
        if not job: raise KeyError(args.external_ref)
        return talking_reel.cancel(job.dir)
    if args.engine == "motion":
        from app import jobs
        job = jobs.get(args.external_ref)
        if not job: raise KeyError(args.external_ref)
        # Generic render supports process termination through the render
        # subsystem only when a cancel token exists; do not pretend otherwise.
        raise ValueError("This motion render cannot be canceled safely in its current stage")
    raise ValueError("unsupported engine")


TOOLS = {
    spec.name: spec for spec in (
        ToolSpec("search_creative_resources", "Search shared creative metadata. Catalog-only entries cannot be rendered. No installation, uploads or project changes.", ResourceSearchInput, "catalog_read", False, True, _search_resources),
        ToolSpec("instagram_content_check", "Check supplied Instagram hooks, script timing, captions or naturalness locally. English: hook, beats, caption, humanize, audit_text, swipe. Persian/mixed Persian: hook, beats, caption, humanize only; preserve ZWNJ. Heuristics are not virality predictions. No research, publishing or media generation.", InstagramContentCheckInput, "supplied_text", False, True, _instagram_content_check),
        ToolSpec("inspect_media", "Read duration, streams and dimensions of an owned upload.", InspectMediaInput, "owned_attachment", False, True, _inspect_media),
        ToolSpec("inspect_url", "Read a public product page and download verified product images.", InspectUrlInput, "public_url", False, True, _inspect_url),
        ToolSpec("localize_video", "Run the existing Persian Localize analysis pipeline.", LocalizeInput, "owned_attachment", True, False, _localize),
        ToolSpec("analyze_talking_reel", "Create a job and run the selected real Talking Reel style.", TalkingInput, "owned_attachment", True, False, _talking),
        ToolSpec("create_storyboard", "Create a real Content Creator storyboard from text and owned images.", ContentInput, "owned_attachment", True, False, _content),
        ToolSpec("check_render_status", "Read real engine state for a linked project.", ProjectRefInput, "owned_project", False, True, _status),
        ToolSpec("cancel_operation", "Cancel only engines that expose a real cancellation hook.", ProjectRefInput, "owned_project", False, True, _cancel),
    )
}


def list_tools() -> list[dict]:
    return [spec.public() for spec in TOOLS.values()]


def execute(name: str, payload: dict) -> dict:
    spec = TOOLS.get(name)
    if spec is None: raise ValueError("Tool is not allowed")
    arguments = spec.input_model.model_validate(payload)
    return spec.handler(arguments)


def idempotency_key(conversation_id: str, message_id: int | str, tool: str, payload: dict) -> str:
    value = f"{conversation_id}:{message_id}:{tool}:{sorted(payload.items())}"
    return hashlib.sha256(value.encode()).hexdigest()
