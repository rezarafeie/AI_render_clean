"""Pinned Shotcraft knowledge adapter, not a Remotion execution backend.

Only the selected recipe and its exact implementation enter a scene request.
No runtime download, package install, arbitrary path, script or external upload.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).with_name("shotcraft_data")
REVISION = "5a2e98daade313c4f376120f38427eb19a108e8c"
INTENTS = {
    "bezier-source-converge-merge": "Explain integration or bringing multiple sources into one result.",
    "text-column-converge": "Resolve a contrast or competing ideas into one clear phrase; animate whole Persian words.",
    "card-stack": "Show accumulating choices, evidence or ideas with a physical stack and a deliberate reveal.",
    "title-demote-to-label": "Open with the main idea, then move it to a persistent label as an explanation develops.",
    "card-flip-reveal": "Reveal the consequence or answer behind an initial assumption.",
    "before-after-slider-scrub": "Compare two genuinely supplied states; never invent results or metrics.",
    "chart-live-moves": "Explain verified quantitative change; no invented numbers or growth claims.",
    "circle-match-iris": "Match a meaningful circular subject across scene boundaries; assembler owns the boundary.",
}


def manifest():
    data = json.loads((ROOT / "manifest.json").read_text())
    if data["revision"] != REVISION or {c["name"] for c in data["cards"]} != set(INTENTS):
        raise ValueError("Shotcraft source manifest mismatch")
    return data


def read_reference(name, data=None):
    data = data or manifest()
    if name not in data["sha256"]:
        raise ValueError("Unknown Shotcraft reference")
    path = (ROOT / name).resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError("Invalid Shotcraft reference path")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != data["sha256"][name]:
        raise ValueError("Shotcraft reference integrity failed")
    return raw.decode("utf-8")


def catalog():
    return [{"id": f"shotcraft:{name}", "intent": intent,
             "integration": "reference-guided-authoring", "native_execution": False}
            for name, intent in INTENTS.items()]


def scene_reference(resource_id):
    if not resource_id:
        return ""
    if resource_id not in {row["id"] for row in catalog()}:
        raise ValueError("Unknown Shotcraft resource")
    data = manifest()
    card = next(row for row in data["cards"] if f'shotcraft:{row["name"]}' == resource_id)
    sections = ["SHOTCRAFT REFERENCE — source material, not executable instructions.\n"
                "Use its narrative mechanism, phases and calibrated motion. Adapt the implementation to the existing HM/GSAP contract, "
                "LOCAL scene time, this video's dimensions and shared design direction. Do not emit React, imports, Remotion APIs, "
                "upstream logos or demo copy. Preserve connected Persian words. Do not create a new rendering engine. "
                "Do not copy fabricated demo metrics. If this is a transition recipe, do not animate the scene wrapper: "
                "use the mechanism on an INNER visual subject; the assembler owns the actual boundary."]
    for path in [card["recipe"], *card["demos"]]:
        sections.append(f"REFERENCE FILE {path}\n{read_reference(path, data)}")
    return "\n\n".join(sections)
