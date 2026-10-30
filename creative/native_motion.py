"""Bounded adapters executing vendored code, never model-generated replacements.

Only reviewed adapters are selectable. Adding a catalog entry alone cannot
enable execution. Upstream HTML remains unchanged on disk.
"""
import hashlib
import json
import re
import math
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "assets/hyperframes_components"
LEGACY_INPUTS = ("hyperframes:headline-slam", "hyperframes:cta-close", "hyperframes:count-up")
# Explicitly reviewed browser runs; new files/catalog rows never enable themselves.
SUPPORTED = tuple("hyperframes:" + name for name in (
    "beat-timeline", "chart-story", "conic-progress-ring", "constellation-hub", "count-up",
    "cta-lockup", "cta-close", "headline-slam", "kinetic-type-swap", "line-swap",
    "marker-highlight", "match-cut", "notification-stack", "native-notification-pop",
    "overwhelm-surround", "radial-surround", "pan-stations", "per-word-rise",
    "perspective-marquee", "pull-back-reveal", "push-in", "social-proof-card",
    "split-tilt-cards", "comparison-split", "before-after-wipe", "focus-rack",
    "state-chip-rail", "svg-mask-reveal", "text-shimmer", "titlecard-calm", "titlecard-lockup",
    "typed-prompt", "vox-annotate", "grid-card-assemble", "toggle-flip", "star-rating-fill",
    "tracing-beam", "avatar-cloud", "multiplayer-cursors", "drift-hold", "staggered-fade-up", "text-stagger",
    "marker-checklist-card", "notes-typing", "cursor-text-select",
))


def source_names():
    return tuple(json.loads((SOURCES / "MANIFEST.json").read_text())["files"])


def parameter_schema(name: str):
    if name not in source_names():
        raise ValueError("Unknown vendored component")
    class Metadata(HTMLParser):
        variables = []
        def handle_starttag(self, tag, attrs):
            value = dict(attrs).get("data-composition-variables")
            if value:
                self.variables = json.loads(value)
    parser = Metadata()
    parser.feed((SOURCES / f"{name}.html").read_text())
    result = {v["id"]: v for v in parser.variables}
    if name == "overwhelm-surround":
        result["task_labels"] = {"id":"task_labels", "type":"string", "role":"content", "label":"Task labels",
                                 "description":"Comma-separated task labels, exactly count entries. Explicit content replaces the original fixed English demo labels."}
    return result


def content_problems(spec, duration=None):
    """Production-only semantic guards. Demo materialization may use defaults."""
    if spec.resource_id in LEGACY_INPUTS:
        return []
    name = spec.resource_id.split(":")[1]
    schema, p = parameter_schema(name), spec.parameters
    missing = {k for k,v in schema.items() if v.get("role") == "content"} - p.keys()
    if missing:
        return ["Explicit component content required: " + ", ".join(sorted(missing))]
    problems = []
    def parts(key):
        return [v.strip() for v in str(p.get(key, "")).split(",")]
    paired_counts = {"beat-timeline":("labels","beatCount"), "multiplayer-cursors":("labels","cursorCount"),
                     "overwhelm-surround":("task_labels","count")}
    if name in paired_counts:
        labels, count = paired_counts[name]
        expected = p[count]
        if float(expected) != int(expected) or len(parts(labels)) != expected or not all(parts(labels)):
            problems.append(f"{labels} must contain exactly {count} nonempty labels; demo fallbacks are forbidden")
    if name == "tracing-beam" and (len(parts("labels")) != 3 or not all(parts("labels"))):
        problems.append("tracing-beam requires three explicit nonempty labels")
    if name == "chart-story":
        try:
            values = [float(v) for v in parts("data")]
            if not 2 <= len(values) <= 12 or not all(math.isfinite(v) and abs(v) <= 1_000_000 for v in values):
                raise ValueError()
            if len(parts("labels")) != len(values) or not all(parts("labels")):
                problems.append("Chart labels must match all explicit data values")
        except ValueError:
            problems.append("Chart data requires 2–12 finite bounded comma-separated numbers")
    if name == "per-word-rise" and p.get("split") == "char" and re.search(r"[\u0600-\u06ff]", str(p.get("text", ""))):
        problems.append("Persian text requires word splitting to preserve joined glyphs")
    if name == "cursor-text-select" and p["phrase"] not in p["text"]:
        problems.append("Selection phrase must exist in the supplied text")
    if name == "notes-typing" and duration is not None:
        required = max(10, len(str(p["lines"])) * .2 / max(.5, float(p.get("speed", 1))) + 2)
        if duration < required:
            problems.append(f"notes-typing needs at least {required:g} seconds; do not truncate its text")
    return problems


class NativeMotion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource_id: str
    text: str = Field(min_length=1, max_length=64)
    button_label: str = Field(default="", max_length=24)
    accent: Literal["green", "blue", "violet"] = "blue"
    start_value: int = Field(default=0, ge=-1_000_000, le=1_000_000, strict=True)
    end_value: int = Field(default=100, ge=-1_000_000, le=1_000_000, strict=True)
    prefix: str = Field(default="", max_length=12)
    suffix: str = Field(default="", max_length=12)
    locale: Literal["fa-IR", "en-US"] = "fa-IR"
    parameters: dict[str, str | float | bool] = Field(default_factory=dict, max_length=24)

    @field_validator("resource_id")
    @classmethod
    def known_resource(cls, value):
        if value not in {f"hyperframes:{name}" for name in source_names()}:
            raise ValueError("Unknown vendored component")
        return value

    @model_validator(mode="after")
    def checked_parameters(self):
        schema = parameter_schema(self.resource_id.split(":")[1])
        for key, value in self.parameters.items():
            if key not in schema:
                raise ValueError(f"Unknown component parameter: {key}")
            item = schema[key]
            kind = item["type"]
            if kind == "number":
                if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or abs(value) > 1_000_000:
                    raise ValueError(f"Invalid bounded number: {key}")
                if value < item.get("min", -1_000_000) or value > item.get("max", 1_000_000):
                    raise ValueError(f"Parameter outside component range: {key}")
            elif kind == "boolean":
                if not isinstance(value, bool):
                    raise ValueError(f"Boolean required: {key}")
            elif kind in {"string", "enum", "color"}:
                if not isinstance(value, str) or len(value) > 1200 or any(c in value for c in "<>&"):
                    raise ValueError(f"Bounded plain text required: {key}")
                if kind == "enum" and value not in [o["value"] for o in item.get("options", [])]:
                    raise ValueError(f"Unknown enum value: {key}")
                if kind == "color" and not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                    raise ValueError(f"Hex color required: {key}")
            else:
                raise ValueError(f"Unsupported parameter type: {kind}")
        return self


def catalog():
    from engine.hyperframes.catalog import load_catalog, load_profiles
    entries = {v["name"]:v for v in load_catalog().get("items", [])}
    profiles = load_profiles()
    result = []
    for key in SUPPORTED:
        name = key.split(":")[1]
        profile = profiles.get(name, {})
        result.append({"id":key, "execution":"vendored-hyperframes-code", "format":"vertical",
                       "description":entries.get(name, {}).get("description", name),
                       "best_for":profile.get("best_for", []), "avoid_when":profile.get("avoid_when", []),
                       "inputs":{"resource_id":key,"text":"short exact approved headline", "parameters":{
                           k: {"type":v["type"], "description":(v.get("description") or v.get("label", ""))[:100],
                               **({"min":v["min"]} if "min" in v else {}),
                               **({"max":v["max"]} if "max" in v else {}),
                               **({"options":[o["value"] for o in v["options"]]} if "options" in v else {})}
                           for k,v in parameter_schema(name).items()},
                           "required_content":[k for k,v in parameter_schema(name).items() if v.get("role")=="content"]},
                       "minimum_seconds":10 if name=="notes-typing" else 2.5,
                       "contract":"Supply every required_content parameter explicitly, including empty optional copy. Counts must match complete nonempty label lists; charts require finite factual data and one label per datum; tracing-beam needs exactly three labels. Persian per-word-rise must use split=word. Do not retain upstream demo claims, brands or statistics. Data only, never JS; original source executes.",
                       "certification":"Portrait demo browser-checked, not certification of every copy, duration, RTL input or encoded output."})
    return result


def materialize(project: Path, spec: NativeMotion, instance: str, duration: float):
    """Write a namespaced subcomposition and provenance, without network calls."""
    if not re.fullmatch(r"s[1-8]-native", instance) or not 0.5 <= duration <= 60:
        raise ValueError("Invalid native component instance or duration")
    name = spec.resource_id.split(":")[1]
    source = SOURCES / f"{name}.html"
    data = source.read_bytes()
    expected = json.loads((SOURCES / "MANIFEST.json").read_text())["files"][name]["sha256"]
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected:
        raise ValueError("Native component source integrity mismatch")
    text = data.decode()
    values = {"text": spec.text, "action_line": spec.text,
              "button_label": spec.button_label, "accent": spec.accent,
              "shadow": False, "exit": "none", "start": spec.start_value,
              "end": spec.end_value, "prefix": spec.prefix, "suffix": spec.suffix, "glow": False}
    # New component inputs are sourced from its own bounded upstream schema.
    # Original defaults remain intact unless an explicit parameter overrides them.
    if spec.resource_id not in LEGACY_INPUTS:
        values = {k: v["default"] for k, v in parameter_schema(name).items() if "default" in v}
        if "text" in values:
            values["text"] = spec.text
    values.update(spec.parameters)
    if name == "overwhelm-surround" and "task_labels" in spec.parameters:
        text, replaced = re.subn(r'var labels = \[[\s\S]*?\];', 'var labels = String(vars.task_labels).split(",").map(function(v){return v.trim();});', text, count=1)
        if replaced != 1:
            raise ValueError("Upstream task label contract changed")
    # Script-safe JSON: user text is data, including </script> and Unicode.
    payload = json.dumps(values, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    text, count = re.subn(r"var vars\s*=\s*window\.__hyperframes[\s\S]*?:\s*\{\};",
                          lambda _: "var vars = " + payload + ";", text, count=1)
    if count != 1:
        if name != "cursor-text-select":
            raise ValueError("Upstream variable contract changed")
        text, count = re.subn(r"var vars = Object\.assign\([^;]+;", lambda _: "var vars = " + payload + ";", text, count=1)
        if count != 1:
            raise ValueError("Cursor variable contract changed")
    text = re.sub(r'<script src="https://cdn\.jsdelivr\.net/[^\"]+"></script>', "", text)
    text = text.replace('id="root"', f'id="{instance}"').replace('#root', f'#{instance}')
    text = text.replace('getElementById("root")', f'getElementById("{instance}")')
    text = text.replace(f'"{name}"', f'"{instance}"')
    # Namespace every remaining ID, including SVG references and document lookups.
    ids = re.findall(r'\bid="([^\"]+)"', text)
    for old in sorted(set(ids), key=len, reverse=True):
        if old == instance:
            continue
        new = instance + "-" + old
        text = text.replace(f'id="{old}"', f'id="{new}"').replace(f'getElementById("{old}")', f'getElementById("{new}")')
        text = re.sub(r"#" + re.escape(old) + r"(?![\w-])", "#" + new, text)
    if name == "marker-checklist-card":
        text = text.replace('getElementById("mcc-row" +', f'getElementById("{instance}-mcc-row" +')
    if name == "cursor-text-select":
        # Preserve connected Persian words. The original per-character spans
        # create overlapping selection backgrounds within joined glyphs.
        text = text.replace('for (var i = 0; i < phrase.length; i++) {',
                            'var rtlPhrase = /[\\u0600-\\u06ff]/.test(phrase); var units = rtlPhrase ? (phrase.match(/\\S+\\s*/g) || []) : Array.from(phrase); for (var i = 0; i < units.length; i++) {')
        text = text.replace('span.textContent = phrase[i];', 'span.textContent = units[i];')
        text = text.replace('box.l + (box.r - box.l) * frac', '(rtlPhrase ? box.r - (box.r - box.l) * frac : box.l + (box.r - box.l) * frac)')
    text = re.sub(r'data-(?:composition-)?duration="[0-9.]+"', f'data-duration="{duration:.3f}"', text)
    if name == "count-up":
        # Localize only the existing deterministic formatter, not its counter.
        text = text.replace('toLocaleString("en-US")', f'toLocaleString("{spec.locale}")')
    if name == "marker-checklist-card":
        text = re.sub(r'@font-face\s*\{[^}]+\}', '', text)
        text = text.replace('"Permanent Marker", cursive', 'Ray, sans-serif').replace('"Courier Prime", monospace', 'Vazir, monospace')
    # Per-source typography fixes for the metrics of the shipped Persian fonts.
    # Do not silence checks: increase the actual line boxes / fix real contrast.
    corrections = {
        "beat-timeline": ".bt-title{line-height:1.8}.bt-index{color:#111}",
        "match-cut": ".mc-label-a,.mc-label-b{line-height:1.5}",
        "notification-stack": ".ns-title,.ns-body{line-height:1.5}",
        "native-notification-pop": ".nnp-title{line-height:1.5}",
        "radial-surround": ".rs-card-label{line-height:1.5}",
        "drift-hold": ".dh-label{line-height:1.8}",
        "focus-rack": ".fr-label{line-height:1.8}.fr-kicker{color:#111}",
        "star-rating-fill": ".srf-value{color:#d5e1ec}",
        "avatar-cloud": ".ac-label{line-height:1.8}.ac-avatar{color:#111;background:#e2e8f0}",
        "tracing-beam": ".tb-label{line-height:1.8;font-size:26px;white-space:normal;overflow-wrap:anywhere}",
        "svg-mask-reveal": ".smr-mask-text,.smr-outline{font-size:170px}",
        "social-proof-card": ".spc-proof{color:#32689f}",
        "cursor-text-select": ".ts-title{line-height:1.5;margin-bottom:8cqw}.ts-para{line-height:1.8}.ts-meta{color:#596278}",
    }
    if name in corrections:
        text = text.replace('</style>', corrections[name] + '</style>', 1)
    if name in {"perspective-marquee", "staggered-fade-up", "text-stagger"}:
        # Upstream ships these as snippets with an explicit integration recipe,
        # not subcompositions. Mount the original snippet and its own recipe.
        recipes = {
            "perspective-marquee": "tl.fromTo('#ID .hf-catalog-perspective-marquee div',{'--hf-marquee-x':'0px'},{'--hf-marquee-x':'-360px',duration:D,ease:'none'},0);",
            "staggered-fade-up": "tl.fromTo('#ID .hf-catalog-staggered-fade-up span',{opacity:0,'--hf-word-y':'22px','--hf-word-scale':.92,'--hf-word-blur':'5px'},{opacity:1,'--hf-word-y':'0px','--hf-word-scale':1,'--hf-word-blur':'0px',duration:.3,stagger:.055,ease:'power3.out'},0);",
            "text-stagger": "tl.fromTo('#ID .hf-transition-text-stagger span',{opacity:0,y:48,filter:'blur(14px)'},{opacity:1,y:0,filter:'blur(0px)',duration:.54,stagger:.09,ease:'power3.out'},.35);tl.to('#ID .hf-transition-text-stagger span',{backgroundPosition:'100% 0%',duration:.72,stagger:.04,ease:'power2.inOut'},1.05);",
        }
        recipe = recipes[name].replace('ID', instance).replace('duration:D', f'duration:{duration:g}')
        text = (f'<template><div id="{instance}" data-composition-id="{instance}" data-duration="{duration:g}" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;direction:rtl;background:#eee">'
                + text + f'<script>(function(){{var tl=gsap.timeline({{paused:true}});{recipe}window.__timelines["{instance}"]=tl;}})();</script></div></template>')
    # Local fonts inherited from the host; whole-word spans preserve Persian joins.
    local_fonts = "@font-face{font-family:Ray;src:url('../assets/fonts/ray-extrabold.ttf')}@font-face{font-family:Vazir;src:url('../assets/fonts/vazirmatn.ttf')}"
    text = text.replace("<style>", "<style>\n" + local_fonts + f"#{instance}{{--font-display:Ray;--font-body:Vazir;--brand:#71f5a7!important;--accent:#61a8ff!important;--accent-2:#b895ff!important;direction:rtl}}\n", 1)
    if re.search(r'<script[^>]+src=|fetch\s*\(', text):
        raise ValueError("Native adapter contains an unapproved dependency")
    root = project.resolve()
    target = root / "compositions" / f"{instance}.html"
    if not target.resolve().is_relative_to(root):
        raise ValueError("Component output escapes project")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    for filename in ("LICENSE.hyperframes", "NOTICE.md"):
        (target.parent / filename).write_bytes((SOURCES / filename).read_bytes())
    return {"resource_id": spec.resource_id, "instance": instance,
            "integration": "vendored-code-execution", "source_sha256": digest,
            "source_revision": "3b2058a2b7a2", "adapter_version": 1,
            "code_license": "Apache-2.0", "render_verified": False}
