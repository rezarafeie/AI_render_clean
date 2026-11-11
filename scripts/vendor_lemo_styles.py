#!/usr/bin/env python3
"""Add the film styles of Lemo-Opuscar (MIT) to vendor/motion-skills/ as skills, without touching the other namespaces.

    python scripts/vendor_lemo_styles.py /path/to/lemo-opuscar [--remove]

Only Markdown is copied (never the demo films, code, fonts or audio). Each style becomes one skill `lemo:<slug>`: SKILL.md is a digest made of the style's own sections
(essence, colour, type, motion, camera: verbatim excerpts) for the scene designers, and the full STYLE.md is kept as its reference file. The director's method
(DIRECTOR.md) is one more skill, `lemo:director-method`. Re-running replaces only the `lemo` entries.
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
NS = "lemo"
REPO = "https://github.com/lemomo-ai/lemo-opuscar"
KEEP = ("1.", "2.", "3.", "4.", "5.", "6.")                   # numbered sections: essence, materials, colour, type, motion, camera
CATEGORY_TAGS = {"graphic": "typography", "type": "typography", "data": "data", "product": "product", "evidence": "data", "edit": "composition", "documentary": "composition",
                 "animation": "motion-craft", "craft": "motion-craft", "title": "typography", "screen": "product", "ui": "product", "news": "composition"}


def sections(text: str) -> list[tuple[str, str]]:
    parts = re.split(r"(?m)^## ", text)
    return [(p.split("\n", 1)[0].strip(), p) for p in parts[1:]]


def digest(slug: str, title: str, text: str, limit: int = 5200) -> str:
    head = text.split("\n## ", 1)[0].strip()
    wanted = [body for name, body in sections(text) if name.startswith(KEEP)]
    out = head + "\n\n" + "\n\n".join("## " + b.strip() for b in wanted)
    return (out[:limit].rsplit("\n", 1)[0] + "\n[… the full style text is the reference file STYLE.md]") if len(out) > limit else out


def main(clone: Path, remove_only: bool = False) -> None:
    index = json.loads((OUT / "index.json").read_text(encoding="utf-8"))
    index["skills"] = [s for s in index["skills"] if s["namespace"] != NS]
    sources = [s for s in json.loads((OUT / "SOURCES.json").read_text(encoding="utf-8")) if s["namespace"] != NS]
    shutil.rmtree(OUT / NS, ignore_errors=True)
    shutil.rmtree(OUT / "_licenses" / NS, ignore_errors=True)
    if not remove_only:
        rev = subprocess.run(["git", "-C", str(clone), "rev-parse", "--short=12", "HEAD"], capture_output=True, text=True).stdout.strip() or "unknown"
        licence = (clone / "LICENSE").read_text(encoding="utf-8", errors="ignore")
        holder = re.search(r"Copyright \(c\) (.+)", licence)
        (OUT / "_licenses" / NS).mkdir(parents=True)
        (OUT / "_licenses" / NS / "lemo-opuscar.LICENSE").write_text(licence)
        sources.append({"namespace": NS, "repo": REPO, "revision": rev, "license": "MIT", "copyright": holder.group(1).strip() if holder else "Lemomo",
                        "license_file": f"_licenses/{NS}/lemo-opuscar.LICENSE",
                        "vendored": "Markdown of the film styles (a digest of each STYLE.md plus the full text as a reference file) and DIRECTOR.md; no films, code, fonts or audio"})
        for folder in sorted((clone / "styles").iterdir()):
            style, meta = folder / "STYLE.md", folder / "style.json"
            if folder.name.startswith("_") or not style.is_file() or not meta.is_file():
                continue
            info = json.loads(meta.read_text(encoding="utf-8"))
            text = style.read_text(encoding="utf-8")
            body = digest(folder.name, info.get("en", folder.name), text)
            skill = OUT / NS / folder.name
            (skill / "references").mkdir(parents=True)
            (skill / "SKILL.md").write_text(body, encoding="utf-8")
            (skill / "references" / "STYLE.md").write_bytes(style.read_bytes())
            uses = [str(u) for u in info.get("uses") or []]
            category = str(info.get("category_en") or "")
            tags = sorted({t for k, t in CATEGORY_TAGS.items() if k in (category + " " + " ".join(uses) + " " + folder.name).lower()} | {"film-style"})
            essence = re.search(r"(?m)^>\s*(.+)$", text)                              # the style's own one-line definition
            hint = f"{info.get('en', folder.name)} ({category}): {(essence.group(1) if essence else '')[:130]} Good for: {', '.join(uses[:3])}"[:260]
            files = {f"{NS}/{folder.name}/SKILL.md": hashlib.sha256(body.encode()).hexdigest(),
                     f"{NS}/{folder.name}/references/STYLE.md": hashlib.sha256(style.read_bytes()).hexdigest()}
            index["skills"].append({"id": f"{NS}:{folder.name}", "name": folder.name, "namespace": NS, "pack": "lemo-opuscar", "description": hint, "repo": REPO, "revision": rev,
                                    "path": f"{NS}/{folder.name}/SKILL.md", "subpath": f"styles/{folder.name}", "bytes": len(body.encode()), "references": [f"{NS}/{folder.name}/references/STYLE.md"],
                                    "tags": tags, "runtime_needed": "", "license": "MIT", "hint": hint, "body_chars": 5200, "files": files})
        director = (clone / "DIRECTOR.md").read_bytes()
        (OUT / NS / "director-method").mkdir(parents=True)
        (OUT / NS / "director-method" / "SKILL.md").write_bytes(director)
        d_hint = "How a film is directed: benchmark first, then sound, rhythm, camera and staging before pretty frames; the treatment, the beats and the checks"
        index["skills"].append({"id": f"{NS}:director-method", "name": "director-method", "namespace": NS, "pack": "lemo-opuscar", "description": d_hint, "repo": REPO, "revision": rev,
                                "path": f"{NS}/director-method/SKILL.md", "subpath": "DIRECTOR.md", "bytes": len(director), "references": [], "tags": ["composition", "film-style"],
                                "runtime_needed": "", "license": "MIT", "hint": d_hint, "body_chars": 4200,
                                "files": {f"{NS}/director-method/SKILL.md": hashlib.sha256(director).hexdigest()}})
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "SOURCES.json").write_text(json.dumps(sources, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]), "--remove" in sys.argv)
