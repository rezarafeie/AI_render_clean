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
    from creative.native_motion import SUPPORTED, source_names, parameter_schema
    from pathlib import Path
    import json
    gallery_path = Path(__file__).resolve().parents[2] / "web/public/creative-previews/index.json"
    try:
        gallery = json.loads(gallery_path.read_text()).get("items", {})
    except (OSError, ValueError):
        gallery = {}
    catalog, profiles = load_catalog(), load_profiles()
    def native_parameters(name):
        return tuple(Parameter(name=k, value_type="number" if v["type"] == "number" else "boolean" if v["type"] == "boolean" else "string",
                               default=v.get("default"), editable=True, description=v.get("description") or v.get("label", ""),
                               required=v.get("role")=="content", minimum=v.get("min"), maximum=v.get("max"),
                               max_length=v.get("maxLength"),
                               options=tuple(o["value"] for o in v.get("options", [])))
                     for k,v in parameter_schema(name).items())
    # The index owns membership/version. Profiles only enrich matching items;
    # the two snapshots currently have different item counts.
    for item in catalog.get("items", []):
        key = item["name"]
        profile = profiles.get(key, {})
        preview = profile.get("preview") or {}
        video, poster = _preview_url(preview.get("video")), _preview_url(preview.get("poster"))
        local = gallery.get(f"hyperframes:{key}", {})
        expected_poster = f"/creative-previews/{key}.png"
        if local.get("poster") == expected_poster and (gallery_path.parent / f"{key}.png").is_file():
            poster = expected_poster
        motion = f"hyperframes:{key}" in SUPPORTED
        talking = key in SUPPORTED_REGISTRY_ADAPTERS
        wired = talking or motion
        yield Resource(
            id=f"hyperframes:{key}", name=item.get("title", key),
            description=item.get("description", ""), type=item.get("type", "component"),
            category=(item.get("tags") or ["motion"])[0], tags=tuple(item.get("tags", [])),
            provider="hyperframes-official", source_version=catalog.get("hyperframes_version"),
            source_url="https://github.com/heygen-com/hyperframes/tree/main/registry",
            engine="hyperframes", integration_status="native" if wired else "adapter-required",
            availability="existing-pipeline" if wired else "catalog-only",
            contexts=(("talking_2",) if talking else ()) + (("motion-graphic",) if motion else ()), legacy_id=key,
            capabilities=Capabilities(supports_preview=True if video or poster else None),
            parameters=native_parameters(key) if motion else tuple(Parameter(name=str(name), value_type="string")
                             for name in profile.get("variables", [])),
            recommended_for=tuple(profile.get("best_for", [])),
            avoid_when=tuple(profile.get("avoid_when", [])),
            preview_video=video, preview_poster=poster,
            limitations=("Capabilities, asset licenses and performance require per-resource verification.",
                         "Bounded ScenePlan.native_component adapter; portrait browser-tested, encoded-output certification pending." if motion else
                         "Existing adapters are context-specific, not a generic execution API." if wired else
                         "Metadata only; not yet connected to an EditorGPT render adapter."),
        )
    # The vendored executable snapshot is newer/different from the discovery
    # index. Do not lose real local components merely because that index lags.
    indexed = {item["name"] for item in catalog.get("items", [])}
    for key in sorted(set(source_names()) - indexed):
        rid = "hyperframes:" + key
        local = gallery.get(rid, {})
        wired = rid in SUPPORTED
        poster = f"/creative-previews/{key}.png"
        yield Resource(id=rid, name=key.replace("-", " ").title(),
                       description=f"Pinned {key} source; typed upstream parameters, local runtime and per-instance timeline.",
                       type="component", category="motion", provider="hyperframes-official",
                       source_url="https://github.com/heygen-com/hyperframes/tree/3b2058a2b7a2/registry/components",
                       source_version="3b2058a2b7a2", engine="hyperframes",
                       integration_status="native" if wired else "adapter-required",
                       availability="existing-pipeline" if wired else "catalog-only",
                       contexts=("motion-graphic",) if wired else (), legacy_id=key,
                       parameters=native_parameters(key),
                       preview_poster=poster if local.get("poster") == poster else None,
                       limitations=("Portrait demonstration browser-checked only; not certification of all inputs, RTL, timings or encoded output." if wired else "Adapter check failed; not eligible for production selection.",))


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
        text_native = item["id"] == "shotcraft:text-column-converge"
        native = item["id"] in {"shotcraft:bezier-source-converge-merge","shotcraft:text-column-converge"}
        yield Resource(
            id=item["id"], name=item["id"].split(":", 1)[1], description=item["intent"],
            type="component" if native else "motion-reference", category="explainer", provider="video-shotcraft",
            source_url="https://github.com/Vincentwei1021/video-shotcraft", source_version=REVISION,
            engine="hyperframes", integration_status="native" if native else "port-required", availability="existing-pipeline" if native else "catalog-only",
            contexts=("motion-graphic",), license=License(type="Apache-2.0", verified=True, attribution_required=True),
            preview_poster="/creative-previews/shotcraft-native-"+item["id"].split(":",1)[1]+".png" if native else "/creative-previews/shotcraft-" + ("chart-axis-rescale" if item["id"] == "shotcraft:chart-live-moves" else item["id"].split(":",1)[1]) + ".png",
            preview_video="/creative-previews/shotcraft-native-"+item["id"].split(":",1)[1]+".mp4" if native else None,
            capabilities=Capabilities(supports_vertical=not text_native,supports_rtl=True,supports_preview=True,transparent=False) if native else Capabilities(),
            parameters=(Parameter(name="caption",value_type="string",editable=True,required=True,max_length=48,description="Exact approved headline, at most eight complete words"),
                        Parameter(name="source_icons",value_type="array",editable=True,required=True,min_items=4,max_items=4,item_options=("shot","card","code","wave"),description="Four bounded media icons, in source order"),
                        Parameter(name="output_icon",value_type="string",editable=True,default="play",options=("check","play","spark")),
                        Parameter(name="accent",value_type="string",editable=True,default="#5b63d3",description="#RRGGBB only"),
                        Parameter(name="locale",value_type="string",editable=True,default="fa-IR",options=("fa-IR","en-US"))) if native and not text_native else (
                        Parameter(name="caption",value_type="string",editable=True,required=True,max_length=24,description="Exact approved final headline"),
                        Parameter(name="prefix",value_type="string",editable=True,required=True,max_length=12),
                        Parameter(name="features",value_type="array",editable=True,required=True,min_items=2,max_items=6,description="Unique plain phrases, at most 24 UTF16 units / three words each"),
                        Parameter(name="subtitle",value_type="string",editable=True,required=True,max_length=48),
                        Parameter(name="locale",value_type="string",editable=True,default="fa-IR",options=("fa-IR","en-US"))) if text_native else (),
            limitations=("Native shotcraft_component uses original TSX through existing Remotion → HyperFrames. Horizontal only; pinned opposing edges, a single convergence, shaped local-font width checks, explicit reading hold. No arbitrary UI, URLs or source code; no fallback or clipping.",) if text_native else (
                         "Native shotcraft_component executes pinned TSX through the existing Remotion renderer, then embeds an owned video in HyperFrames; shotcraft_id alone remains reference guidance. Four media icons and abstract output icon only; no arbitrary UI/logo or code. 4–12 s with a caption reading hold; current retained hybrid audit is portrait Persian.",) if native else
                         ("Production uses the pinned recipe as authoring guidance, not native TSX. Gallery executes original TSX demos only; user-content binding is incomplete. No automatic Remotion fallback.",),
        )


def face_effect_resources():
    """Discover the existing real compositor; do not duplicate its execution API."""
    from engine.face_effects import CATALOG
    for item in CATALOG:
        yield Resource(
            id=f'claude-effects:{item["id"]}', name=item["title"], description=item["description"],
            type="face-effect", category="talking-head", provider="claude-video-effects",
            source_url="https://github.com/Vibha-Ramprakash/claude-video-effects",
            engine="ffmpeg", integration_status="native", availability="existing-pipeline",
            contexts=("talking-reel",), legacy_id=item["id"], recommended_for=(item.get("use", ""),),
            license=License(type="MIT", verified=True, attribution_required=True),
            preview_poster=f'/creative-previews/claude-{item["id"]}.png',
            parameters=tuple(Parameter(name=v["key"], value_type="number" if v["type"] == "number" else "string", default=v.get("default")) for v in item.get("options", [])),
            limitations=("Uses existing engine.face_effects.clean_plan/apply, cancellation and Talking Reel jobs. Requires video/person tracking runtime and model assets.",
                         "Gallery demonstrates the real compositor on synthetic geometry and a fixed matte; it does not certify tracking or complete encoded video."),
        )
