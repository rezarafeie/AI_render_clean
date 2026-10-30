"""Bounded adapters executing vendored code, never model-generated replacements.

Only reviewed adapters are selectable. Adding a catalog entry alone cannot
enable execution. Upstream HTML remains unchanged on disk.
"""
import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "assets/hyperframes_components"
SUPPORTED = ("hyperframes:headline-slam", "hyperframes:cta-close", "hyperframes:count-up")


class NativeMotion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource_id: Literal["hyperframes:headline-slam", "hyperframes:cta-close", "hyperframes:count-up"]
    text: str = Field(min_length=1, max_length=64)
    button_label: str = Field(default="", max_length=24)
    accent: Literal["green", "blue", "violet"] = "blue"
    start_value: int = Field(default=0, ge=-1_000_000, le=1_000_000, strict=True)
    end_value: int = Field(default=100, ge=-1_000_000, le=1_000_000, strict=True)
    prefix: str = Field(default="", max_length=12)
    suffix: str = Field(default="", max_length=12)
    locale: Literal["fa-IR", "en-US"] = "fa-IR"


def catalog():
    return [{"id": key, "execution": "vendored-hyperframes-code", "format": "vertical",
             "inputs": "ScenePlan.native_component: {resource_id, text (1–64 chars), button_label (CTA only), accent: blue|green|violet, start_value: integer, end_value: integer, prefix, suffix, locale: fa-IR|en-US}",
             "use": "A supplied verified factual number only; never invent statistics." if key.endswith("count-up") else
                    "Short opening headline or final CTA only; never substitute for an explanatory diagram or scene."}
            for key in SUPPORTED]


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
    # Script-safe JSON: user text is data, including </script> and Unicode.
    payload = json.dumps(values, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    text, count = re.subn(r"var vars\s*=\s*window\.__hyperframes[\s\S]*?:\s*\{\};",
                          lambda _: "var vars = " + payload + ";", text, count=1)
    if count != 1:
        raise ValueError("Upstream variable contract changed")
    text = re.sub(r'<script src="https://cdn\.jsdelivr\.net/[^\"]+"></script>', "", text)
    text = text.replace('id="root"', f'id="{instance}"').replace('#root', f'#{instance}')
    text = text.replace('getElementById("root")', f'getElementById("{instance}")')
    text = text.replace(f'"{name}"', f'"{instance}"')
    text = re.sub(r'data-(?:composition-)?duration="[0-9.]+"', f'data-duration="{duration:.3f}"', text)
    if name == "count-up":
        # Localize only the existing deterministic formatter, not its counter.
        text = text.replace('toLocaleString("en-US")', f'toLocaleString("{spec.locale}")')
    # Local fonts inherited from the host; whole-word spans preserve Persian joins.
    text = text.replace("<style>", "<style>\n" + f"#{instance}{{--font-display:Ray;--font-body:Vazir;--brand:#71f5a7!important;--accent:#61a8ff!important;--accent-2:#b895ff!important;direction:rtl}}\n", 1)
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
