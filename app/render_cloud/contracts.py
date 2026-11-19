"""Render prepared inputs with the existing engines; never interpret a second timeline."""
from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or any(ord(c)<32 or ord(c)==127 for c in value) or value.startswith('/') or '\\' in value or ':' in value or any(
        part in {'', '.', '..'} for part in value.split('/')
    ):
        raise ValueError('Expected a normalized relative file path')
    return str(path)


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Asset(Strict):
    path: str = Field(max_length=500)
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    size: int = Field(ge=1, le=50 * 1024**3)

    _path = field_validator('path')(relative_path)


class MltOptions(Strict):
    preview: bool = False
    style_name: str = Field(default='rafiei_reel', pattern=r'^[a-zA-Z0-9_-]{1,100}$')
    apply_loudnorm: bool = False
    style_override: dict | None = None
    crf_override: int | None = Field(default=None, ge=0, le=51)

    @field_validator('style_override')
    @classmethod
    def bounded_style(cls, value):
        import json
        if value is not None and len(json.dumps(value,allow_nan=False)) > 100000:
            raise ValueError('Style override exceeds limit')
        return value


class RenderSpec(Strict):
    version: Literal[1] = 1
    job_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,100}$')
    project_id: str = Field(min_length=1, max_length=100)
    # Server-derived identity, never accepted without an ownership check upstream.
    user_id: str = Field(min_length=1, max_length=200)
    engine: Literal['hyperframes_page', 'hyperframes_project', 'hyperframes_product', 'remotion', 'mlt', 'talking_1', 'talking_2', 'talking_3', 'talking_4', 'talking_5', 'localize', 'claude_motion', 'ffmpeg_job', 'face_effects', 'person_matte']
    entrypoint: str
    assets: list[Asset] = Field(min_length=1, max_length=20000)
    duration_seconds: float = Field(gt=0, le=7200)
    fps: int = Field(ge=1, le=120)
    width: int = Field(ge=16, le=7680)
    height: int = Field(ge=16, le=7680)
    timeout_seconds: int = Field(ge=1, le=21600)
    workspace_bytes: int = Field(ge=1024**2, le=200 * 1024**3)
    output: str = 'output.mp4'
    export_format: Literal['mp4','webm'] = 'mp4'
    audio_required: bool = False
    runtime_env: dict[str, str] = Field(default_factory=dict)
    features: list[str] = Field(default_factory=list,max_length=100)
    gpu_required: bool = False

    @field_validator('features')
    @classmethod
    def bounded_features(cls,value):
        if any(not isinstance(v,str) or not 1<=len(v)<=120 for v in value):
            raise ValueError('Invalid render feature')
        return sorted(set(value))
    mlt_options: MltOptions = Field(default_factory=MltOptions)

    @field_validator('runtime_env')
    @classmethod
    def allowed_runtime(cls, value):
        choices = {'REMOTION_LOOK': {'classic', 'cinematic'},
                   'REMOTION_CONCURRENCY': {'1','2','3','4'}, 'HYPERFRAMES_WORKERS': {'1','2','3','4'}}
        if any(key not in choices or val not in choices[key] for key, val in value.items()):
            raise ValueError('Unsupported render runtime setting')
        return value

    _paths = field_validator('entrypoint', 'output')(relative_path)

    @model_validator(mode='after')
    def unique_paths(self):
        paths = [asset.path for asset in self.assets]
        if len(paths) != len(set(paths)) or self.entrypoint not in paths or self.output in paths:
            raise ValueError('Duplicate asset, missing entrypoint or output/input collision')
        all_paths = set(paths + [self.output])
        for path in all_paths:
            if any(str(parent) in all_paths for parent in PurePosixPath(path).parents if str(parent) != '.'):
                raise ValueError('A file cannot also be a directory')
        if sum(asset.size for asset in self.assets) > self.workspace_bytes:
            raise ValueError('Assets exceed workspace allowance')
        return self


class Observation(Strict):
    state: Literal['queued', 'provisioning', 'preparing', 'downloading', 'rendering',
                   'uploading', 'completed', 'failed', 'cancelled']
    # Stage progress only. An unknown percentage is not a fabricated estimate.
    progress: float | None = Field(default=None, ge=0, le=100)
    error_code: str | None = Field(default=None, pattern=r'^[a-z0-9_]{1,80}$')
    # Short sanitized failure class + message (no URLs, paths or tokens) so a failed stage can be diagnosed.
    reason: str | None = Field(default=None, max_length=2400)
