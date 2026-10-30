"""Versioned public manifests. Unknown capabilities are deliberately nullable."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ManifestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class License(ManifestModel):
    type: str | None = None
    verified: bool = False
    commercial_use_approved: bool = False
    attribution_required: bool | None = None


class Capabilities(ManifestModel):
    seekable: bool | None = None
    transparent: bool | None = None
    supports_rtl: bool | None = None
    supports_vertical: bool | None = None
    supports_preview: bool | None = None


class Parameter(ManifestModel):
    name: str
    value_type: Literal["string", "number", "boolean", "array"]
    default: Any = None
    # A known default is not a validated editing contract.
    editable: bool = False
    description: str = ""
    required: bool = False
    minimum: float | None = None
    maximum: float | None = None
    max_length: int | None = None
    options: tuple[str, ...] = ()
    min_items: int | None = None
    max_items: int | None = None
    item_options: tuple[str, ...] = ()


class Resource(ManifestModel):
    schema_version: Literal[1] = 1
    id: str = Field(pattern=r"^[a-z0-9_-]+:[a-zA-Z0-9_-]+$")
    name: str
    description: str = ""
    type: str
    category: str
    tags: tuple[str, ...] = ()
    provider: str
    source_url: str | None = None
    source_version: str | None = None
    engine: Literal["hyperframes", "ffmpeg", "mlt", "html", "webgl", "asset", "skill"]
    integration_status: Literal["native", "adapter-required", "port-required", "asset-only", "skill-only", "unsupported"]
    availability: Literal["catalog-only", "existing-pipeline", "unsupported"] = "catalog-only"
    contexts: tuple[str, ...] = ()
    legacy_id: str | None = None
    license: License = Field(default_factory=License)
    capabilities: Capabilities = Field(default_factory=Capabilities)
    parameters: tuple[Parameter, ...] = ()
    recommended_for: tuple[str, ...] = ()
    avoid_when: tuple[str, ...] = ()
    preview_video: str | None = None
    preview_poster: str | None = None
    render_time_ms: float | None = None
    peak_memory_mb: float | None = None
    limitations: tuple[str, ...] = ()
