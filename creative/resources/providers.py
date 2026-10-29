"""Read-only adapters over committed, versioned sources. No network/install calls."""
from urllib.parse import urlsplit

from .models import Capabilities, License, Parameter, Resource


def _preview_url(value):
    """Only the known public preview CDN; never advertise arbitrary media URLs."""
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    if (parsed.scheme == "https" and parsed.netloc == "static.heygen.ai"
            and parsed.path.startswith("/hyperframes/") and not parsed.query and not parsed.fragment):
        return value
    return None


def hyperframes_resources():
    from engine.hyperframes.catalog import load_catalog, load_profiles
    from engine.hyperframes.registry_runtime import SUPPORTED_REGISTRY_ADAPTERS
    catalog, profiles = load_catalog(), load_profiles()
    # The index owns membership/version. Profiles only enrich matching items;
    # the two snapshots currently have different item counts.
    for item in catalog.get("items", []):
        key = item["name"]
        profile = profiles.get(key, {})
        preview = profile.get("preview") or {}
        video, poster = _preview_url(preview.get("video")), _preview_url(preview.get("poster"))
        wired = key in SUPPORTED_REGISTRY_ADAPTERS
        yield Resource(
            id=f"hyperframes:{key}", name=item.get("title", key),
            description=item.get("description", ""), type=item.get("type", "component"),
            category=(item.get("tags") or ["motion"])[0], tags=tuple(item.get("tags", [])),
            provider="hyperframes-official", source_version=catalog.get("hyperframes_version"),
            source_url="https://github.com/heygen-com/hyperframes/tree/main/registry",
            engine="hyperframes", integration_status="native" if wired else "adapter-required",
            availability="existing-pipeline" if wired else "catalog-only",
            contexts=("talking_2",) if wired else (), legacy_id=key,
            capabilities=Capabilities(supports_preview=True if video or poster else None),
            parameters=tuple(Parameter(name=str(name), value_type="string")
                             for name in profile.get("variables", [])),
            recommended_for=tuple(profile.get("best_for", [])),
            avoid_when=tuple(profile.get("avoid_when", [])),
            preview_video=video, preview_poster=poster,
            limitations=("Capabilities, asset licenses and performance require per-resource verification.",
                         "Existing adapters are context-specific, not a generic execution API." if wired else
                         "Metadata only; not yet connected to an EditorGPT render adapter."),
        )


def existing_effect_resources():
    from engine.effects_v4 import EFFECT_CATALOG_V4, UNSUPPORTED_EFFECTS, is_renderable_effect
    for key, item in EFFECT_CATALOG_V4.items():
        supported = is_renderable_effect(key)
        parameters = []
        for name, value in item.get("params", {}).items():
            kind = "boolean" if isinstance(value, bool) else "number" if isinstance(value, (float, int)) else "string"
            parameters.append(Parameter(name=name, value_type=kind, default=value))
        yield Resource(
            id=f"editorgpt:{key}", name=item.get("label", key),
            description=item.get("description", ""), type="effect", category=item.get("category", "motion"),
            tags=tuple(filter(None, (item.get("mood"), item.get("motion"), item.get("light")))),
            provider="editorgpt-existing", engine="mlt", legacy_id=key,
            integration_status="native" if supported else "unsupported",
            availability="existing-pipeline" if supported else "unsupported",
            contexts=("edit-plan",) if supported else (), parameters=tuple(parameters),
            recommended_for=tuple(item.get("best_roles", [])),
            limitations=(UNSUPPORTED_EFFECTS.get(key, "Uses the existing validated EditPlan effect operation; parameter editing is not enabled here."),),
        )


def existing_transition_resources():
    from engine.schema import TransitionType
    from typing import get_args
    for key in get_args(TransitionType):
        yield Resource(
            id=f"editorgpt-transition:{key}", name=key.replace("_", " ").title(),
            description="Existing frame-accurate EditPlan boundary transition.",
            type="transition", category="transition", provider="editorgpt-existing", engine="mlt",
            integration_status="native", availability="existing-pipeline", contexts=("edit-plan",),
            legacy_id=key, limitations=("Uses existing BoundaryTransition validation and overlap timing; not an xfade catalog.",),
        )


def existing_recipe_resources():
    from engine.motion_recipes import RECIPES
    for recipe in RECIPES:
        yield Resource(
            id=f"editorgpt-recipe:{recipe.id}", name=recipe.title, description=recipe.best_for,
            type="motion-preset", category=recipe.renderer, tags=recipe.intents,
            provider="editorgpt-existing", engine="hyperframes", integration_status="native",
            availability="existing-pipeline", contexts=("talking_2",), legacy_id=recipe.id,
            recommended_for=(recipe.best_for,), avoid_when=(recipe.avoid_when,),
            limitations=("Existing recipe adapter only; portrait_safe is an authored policy, not a per-resource render certification.",),
        )


def shotcraft_resources():
    from creative.shotcraft import catalog, REVISION
    for item in catalog():
        yield Resource(
            id=item["id"], name=item["id"].split(":", 1)[1], description=item["intent"],
            type="motion-reference", category="explainer", provider="video-shotcraft",
            source_url="https://github.com/Vincentwei1021/video-shotcraft", source_version=REVISION,
            engine="hyperframes", integration_status="port-required", availability="catalog-only",
            contexts=("motion-graphic",), license=License(type="Apache-2.0", verified=True, attribution_required=True),
            limitations=("Pinned recipe and TSX guide scene authoring. TSX is not executed; no certified native port or automatic Remotion fallback.",),
        )
