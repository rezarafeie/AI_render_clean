#!/usr/bin/env python3
"""Add a few OpenMontage (AGPL-3.0) craft skills to vendor/motion-skills/ without touching the MIT ones.

    python scripts/vendor_openmontage_skills.py /path/to/OpenMontage

Only the Markdown of the listed skills is copied, verbatim, with the AGPL-3.0 text and the source revision kept (SOURCES.json, index.json).
Re-running replaces only the `openmontage` entries. The owner accepted AGPL-3.0 for these files (2026-11-11); they stay isolated in
vendor/motion-skills/openmontage/ so they can be removed by deleting that folder and re-running this script's --remove.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "vendor" / "motion-skills"
NS = "openmontage"
REPO = "https://github.com/calesthio/OpenMontage"
SKILLS = {  # file under skills/ -> (id, tags)
    "creative/short-form.md": ("short-form", ["short-form", "composition"]),
    "creative/storytelling.md": ("storytelling", ["explainer", "composition"]),
    "creative/data-visualization.md": ("data-visualization", ["data"]),
    "creative/sound-design.md": ("sound-design", ["sound"]),
    "creative/commercial-product-video.md": ("commercial-product-video", ["product"]),
    "meta/taste-direction.md": ("taste-direction", ["composition", "brand"]),
}


def describe(text: str) -> str:
    title = re.search(r"^#\s+(.+)$", text, re.M)
    para = next((p.strip() for p in re.split(r"\n\s*\n", text) if p.strip() and not p.lstrip().startswith(("#", ">", "`", "|", "-"))), "")
    return re.sub(r"\s+", " ", f"{title.group(1) if title else ''}. {para}").strip()[:600]


def main(clone: Path, remove_only: bool = False) -> None:
    index = json.loads((OUT / "index.json").read_text(encoding="utf-8"))
    index["skills"] = [s for s in index["skills"] if s["namespace"] != NS]
    sources = [s for s in json.loads((OUT / "SOURCES.json").read_text(encoding="utf-8")) if s["namespace"] != NS]
    shutil.rmtree(OUT / NS, ignore_errors=True)
    shutil.rmtree(OUT / "_licenses" / NS, ignore_errors=True)
    if not remove_only:
        rev = subprocess.run(["git", "-C", str(clone), "rev-parse", "--short=12", "HEAD"], capture_output=True, text=True).stdout.strip() or "unknown"
        (OUT / "_licenses" / NS).mkdir(parents=True)
        (OUT / "_licenses" / NS / "OpenMontage.LICENSE").write_text((clone / "LICENSE").read_text(encoding="utf-8", errors="ignore"))
        sources.append({"namespace": NS, "repo": REPO, "revision": rev, "license": "AGPL-3.0", "copyright": "OpenMontage contributors",
                        "license_file": f"_licenses/{NS}/OpenMontage.LICENSE",
                        "vendored": "Markdown of the listed skills only, verbatim; no code, scripts, styles or pipeline manifests"})
        for rel, (name, tags) in SKILLS.items():
            data = (clone / "skills" / rel).read_bytes()
            text = data.decode("utf-8", errors="ignore")
            dst = OUT / NS / name / "SKILL.md"
            dst.parent.mkdir(parents=True)
            dst.write_bytes(data)
            index["skills"].append({
                "id": f"{NS}:{name}", "name": name, "namespace": NS, "pack": "OpenMontage", "description": describe(text), "repo": REPO, "revision": rev,
                "path": f"{NS}/{name}/SKILL.md", "subpath": f"skills/{rel}", "bytes": len(data), "references": [], "tags": tags, "runtime_needed": "",
                "license": "AGPL-3.0", "files": {f"{NS}/{name}/SKILL.md": hashlib.sha256(data).hexdigest()}})
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "SOURCES.json").write_text(json.dumps(sources, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]), "--remove" in sys.argv)
