"""One deterministic metadata registry, shared by HTTP, UI and agent tools."""
from collections import Counter
from functools import lru_cache
import hashlib
import json
import re

from .models import Resource
from .providers import existing_effect_resources, existing_recipe_resources, existing_transition_resources, hyperframes_resources, shotcraft_resources


@lru_cache(maxsize=1)
def _snapshot() -> dict[str, Resource]:
    rows = {}
    for provider in (hyperframes_resources, existing_effect_resources, existing_transition_resources, existing_recipe_resources, shotcraft_resources):
        for item in provider():
            if item.id in rows:
                raise ValueError(f"Duplicate creative resource ID: {item.id}")
            rows[item.id] = item
    return rows


def get_resource(resource_id: str) -> dict:
    """Exact namespaced IDs only; never interpret names as commands or paths."""
    return _snapshot()[resource_id].model_dump(mode="json")


def resolve_edit_plan_resource(resource_id: str, kind: str) -> str:
    """Only an existing native EditPlan binding may resolve to a legacy ID.

    This is not an installer and cannot turn metadata, foreign engine adapters,
    HTML or user-provided paths into executable operations.
    """
    try:
        row = get_resource(resource_id)
    except KeyError:
        raise ValueError("Unknown creative resource") from None
    from .selection import ResourceRequirements, assess_resource
    assessment = assess_resource(resource_id, ResourceRequirements(context="edit-plan", engine="mlt", kind=kind))
    if (not assessment["eligible"]
            or "edit-plan" not in row["contexts"] or row["engine"] != "mlt"
            or row["provider"] != "editorgpt-existing" or row["type"] != kind or not row["legacy_id"]):
        raise ValueError("This resource has no supported EditPlan adapter; no installation or render was started")
    return row["legacy_id"]


def _words(value: str) -> set[str]:
    return set(re.findall(r"[^\W_]+", value.casefold().replace("ي", "ی").replace("ك", "ک")))


def search_resources(query: str = "", *, engine: str | None = None, provider: str | None = None,
                     kind: str | None = None, availability: str | None = None,
                     limit: int = 24, offset: int = 0) -> dict:
    if len(query) > 300 or not 1 <= limit <= 100 or not 0 <= offset <= 10000:
        raise ValueError("Resource search exceeds supported bounds")
    words = _words(query)
    matches = []
    for row in _snapshot().values():
        if any(wanted is not None and actual != wanted for actual, wanted in (
                (row.engine, engine), (row.provider, provider), (row.type, kind), (row.availability, availability))):
            continue
        text = " ".join((row.id, row.name, row.description, row.category, *row.tags, *row.recommended_for))
        score = len(words & _words(text))
        if words and not score:
            continue
        matches.append((score, row))
    matches.sort(key=lambda item: (-item[0], item[1].id))
    return {"schema_version": 1, "total": len(matches), "offset": offset, "limit": limit,
            "items": [row.model_dump(mode="json") for _, row in matches[offset:offset + limit]]}


def registry_summary() -> dict:
    from .provenance import snapshot_integrity
    rows = list(_snapshot().values())
    encoded = json.dumps([row.model_dump(mode="json") for row in rows], sort_keys=True).encode()
    return {"schema_version": 1, "revision": hashlib.sha256(encoded).hexdigest()[:16], "total": len(rows),
            "provenance": snapshot_integrity(),
            "providers": dict(Counter(row.provider for row in rows)),
            "availability": dict(Counter(row.availability for row in rows)),
            "notice": "Discovery does not install, execute, license-approve or modify any resource or project."}
