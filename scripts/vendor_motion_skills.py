#!/usr/bin/env python3
"""Vendor the text of selected open-source motion skills into vendor/motion-skills/ and (re)build its index.

    python scripts/vendor_motion_skills.py /path/to/dir-with-the-clones

Only text (Markdown/TXT) is copied: never scripts, binaries, audio, fonts or fixtures, so nothing here can run. Every source keeps its LICENSE and its
revision (SOURCES.json). The index (index.json) is what the registry and the lazy loader read; skill bodies are read only when a skill is selected.
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
MAX_FILE = 120_000

# namespace -> list of (clone dir, repo url, skill dirs relative to the clone | None for "the clone root is one skill", skill name override)
IART_PACKS = {
    "tiktok-video-skills": ["caption-animation", "countdown-video", "short-form-video", "lower-thirds"],
    "ecommerce-video-skills": ["photo-slideshow", "product-demo-video", "promo-video"],
    "ad-video-skills": ["ad-creative-video", "launch-video", "testimonial-video"],
    "data-animation-skills": ["animated-infographic", "chart-animation", "presentation-video"],
    "explainer-video-skills": ["diagram-animation", "explainer-video", "isometric-animation", "whiteboard-animation", "wrapped-video"],
    "kinetic-typography-skills": ["kinetic-typography"],
    "motion-design-skills": ["animation-principles", "beat-sync-editing", "color-motion", "logo-animation", "motion-art-direction", "motion-background",
                             "remotion-video", "shot-composition"],            # after-effects is not vendored: there is no After Effects in the studio
    "lower-thirds-skills": ["lower-thirds"],
    "b-roll-skills": ["talking-head-b-roll"],
    "javascript-animation-skills": ["javascript-animation", "soundtrack"],
    "webgl-animation-skills": ["particle-system", "shader-glsl", "threejs-animation"],
    "youtube-video-skills": ["audiogram", "youtube-intro-outro"],
}
SKIP_NAMES = {"ae-bridge-higgsfield.md", "roadmap.md", "CHANGELOG.md"}

# skills that need a runtime or hardware the studio does not run by default: listed, never offered to the planner
RUNTIME_NEEDED = {
    "barty:object-separation": "needs a SAM 2 model and a machine to run it on",
    "motionclone:motionclone": "needs the motionclone CLI (Node and a Playwright browser) to measure a page",
    "iart:threejs-animation": "WebGL scenes are not rendered by the studio's HyperFrames path yet",
    "iart:particle-system": "WebGL scenes are not rendered by the studio's HyperFrames path yet",
    "iart:shader-glsl": "WebGL scenes are not rendered by the studio's HyperFrames path yet",
    "charlie:title-sequence-3d": "needs Three.js scenes, which the studio does not render yet",
    "iart:soundtrack": "writes music in code (Web Audio); the studio mixes its own music library instead",
    "barty:sound-effects": "its measured pass runs a separate script; the studio's own SFX engine does the mixing, this is guidance",
}


def git_rev(path: Path) -> str:
    return subprocess.run(["git", "-C", str(path), "rev-parse", "--short=12", "HEAD"], capture_output=True, text=True).stdout.strip()


def frontmatter(text: str) -> tuple[dict, str]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.S)
    if not match:
        return {}, text
    data = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip().strip('"\'')
    return data, text[match.end():]


def copy_text(src: Path, dst: Path) -> list[str]:
    copied = []
    for file in sorted(src.rglob("*")):
        if not file.is_file() or file.suffix.lower() not in {".md", ".txt"} or file.name in SKIP_NAMES:
            continue
        if any(part in {"node_modules", ".git", "examples", "scripts", "templates"} for part in file.relative_to(src).parts):
            continue
        if file.stat().st_size > MAX_FILE:
            continue
        target = dst / file.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(file.read_bytes())
        copied.append(str(target.relative_to(OUT)))
    return copied


TAGS = {
    "typography": r"kinetic|typograph|caption|text animation|lower third",
    "explainer": r"explainer|whiteboard|diagram|isometric|educat",
    "product": r"product|e-?commerce|launch|promo|advert|ad creative|testimonial",
    "data": r"chart|infographic|data|graph|presentation",
    "short-form": r"tiktok|reels?|shorts?|vertical|short-form|9:16",
    "b-roll": r"b-roll|broll|talking[- ]head",
    "sound": r"sound|sfx|audio|music|beat|soundtrack",
    "composition": r"composition|camera|shot|art direction|anti-?ppt|storytelling",
    "motion-craft": r"easing|spring|timing|anticipation|principles|curve|motion designer",
    "brand": r"brand|logo|colou?r|palette",
    "reference": r"reference|clone|recreate",
    "transparent-overlay": r"transparent|alpha|overlay|lower third",
    "webgl": r"three\.?js|webgl|glsl|shader|particle",
}


def tags_for(name: str, description: str, body: str) -> list[str]:
    text = f"{name} {description}".lower()
    found = [tag for tag, pattern in TAGS.items() if re.search(pattern, text)]
    low = body.lower()
    engines = [e for e, p in (("remotion", r"\bremotion\b"), ("hyperframes", r"hyperframes"), ("gsap", r"\bgsap\b"), ("canvas", r"\bcanvas\b"), ("ffmpeg", r"\bffmpeg\b")) if re.search(p, low)]
    return found + [f"engine:{e}" for e in engines]


def main(clones: Path) -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    sources: list[dict] = []
    skills: list[dict] = []

    def add_source(ns: str, clone: Path, repo: str, license_holder_from: Path) -> Path:
        lic = (clone / "LICENSE").read_text(errors="ignore")
        holder = re.search(r"Copyright \(c\) (.+)", lic)
        key = f"{ns}/{clone.name}"
        base = OUT / "_licenses" / ns
        base.mkdir(parents=True, exist_ok=True)
        (base / f"{clone.name}.LICENSE").write_text(lic)
        sources.append({"namespace": ns, "repo": repo, "revision": git_rev(clone), "license": "MIT",
                        "copyright": holder.group(1).strip() if holder else "", "license_file": f"_licenses/{ns}/{clone.name}.LICENSE",
                        "vendored": "Markdown/TXT of the listed skills only; scripts, binaries, audio, fonts and fixtures are not vendored"})
        return clone

    def add_skill(ns: str, clone: Path, repo: str, src_dir: Path, name: str, pack: str, subpath: str):
        text = (src_dir / "SKILL.md").read_text(encoding="utf-8")
        meta, body = frontmatter(text)
        dst = OUT / ns / name
        files = copy_text(src_dir, dst)
        sid = f"{ns}:{name}"
        description = re.sub(r"\s+", " ", meta.get("description", "")).strip()
        skills.append({
            "id": sid, "name": meta.get("name", name), "namespace": ns, "pack": pack, "description": description[:600],
            "repo": repo, "revision": git_rev(clone), "path": f"{ns}/{name}/SKILL.md", "subpath": subpath,
            "bytes": len(text.encode()), "references": [f for f in files if not f.endswith("/SKILL.md")],
            "tags": tags_for(name, description, body), "runtime_needed": RUNTIME_NEEDED.get(sid, ""),
        })

    # iArt: the index repo lists 19 packs, each its own repository
    for pack, names in IART_PACKS.items():
        clone = clones / f"iart-{pack}"
        if not clone.is_dir():
            continue
        repo = f"https://github.com/iart-ai/{pack}"
        add_source("iart", clone, repo, clone)
        for name in names:
            add_skill("iart", clone, repo, clone / "skills" / name, name, pack, f"skills/{name}")
    # one name, one skill: the same skill name from two iArt packs keeps the longer (more complete) one
    best: dict[str, dict] = {}
    for skill in skills:
        if skill["namespace"] == "iart":
            old = best.get(skill["id"])
            if old is None or skill["bytes"] > old["bytes"]:
                best[skill["id"]] = skill
    chosen = {s["id"]: s for s in best.values()}
    dropped = [s for s in skills if s["namespace"] == "iart" and chosen[s["id"]] is not s]
    skills = [s for s in skills if s["namespace"] != "iart" or chosen[s["id"]] is s]
    for old in dropped:                    # the losing duplicate's folder name is the same, so its files were overwritten by the copy order; rebuild the winner
        winner = chosen[old["id"]]
        src = clones / f"iart-{winner['pack']}" / winner["subpath"]
        dst = OUT / "iart" / winner["name"]
        shutil.rmtree(dst, ignore_errors=True)
        winner["references"] = [f for f in copy_text(src, dst) if not f.endswith("/SKILL.md")]
        winner["also_in"] = old["pack"]

    for ns, repo_name, owner, sub in (("charlie", "motion-graphics-skills", "charlie947", "skills"), ("barty", "motion-graphics", "Barty-Bart", "skills")):
        clone = clones / repo_name
        repo = f"https://github.com/{owner}/{repo_name}"
        add_source(ns, clone, repo, clone)
        for d in sorted((clone / sub).iterdir()):
            if (d / "SKILL.md").is_file():
                add_skill(ns, clone, repo, d, d.name, repo_name, f"{sub}/{d.name}")
    clone = clones / "motion-kit"
    add_source("motionkit", clone, "https://github.com/hughminhphan/motion-kit", clone)
    add_skill("motionkit", clone, "https://github.com/hughminhphan/motion-kit", clone / "skills" / "motion-designer", "motion-designer", "motion-kit", "skills/motion-designer")
    clone = clones / "bang-motion"
    add_source("bang", clone, "https://github.com/bangtutorial/bang-motion", clone)
    root_skill = OUT / "bang" / "bang-motion"
    root_skill.mkdir(parents=True)
    (root_skill / "SKILL.md").write_bytes((clone / "SKILL.md").read_bytes())
    refs = []
    for ref in sorted((clone / "references").glob("*.md")):
        if ref.name not in SKIP_NAMES and ref.stat().st_size <= MAX_FILE:
            (root_skill / "references").mkdir(exist_ok=True)
            (root_skill / "references" / ref.name).write_bytes(ref.read_bytes())
            refs.append(f"bang/bang-motion/references/{ref.name}")
    meta, body = frontmatter((clone / "SKILL.md").read_text(encoding="utf-8"))
    skills.append({"id": "bang:bang-motion", "name": "bang-motion", "namespace": "bang", "pack": "bang-motion", "description": re.sub(r"\s+", " ", meta.get("description", ""))[:600],
                   "repo": "https://github.com/bangtutorial/bang-motion", "revision": git_rev(clone), "path": "bang/bang-motion/SKILL.md", "subpath": "SKILL.md",
                   "bytes": (clone / "SKILL.md").stat().st_size, "references": refs, "tags": tags_for("bang-motion", meta.get("description", ""), body) + ["language:id"],
                   "runtime_needed": ""})
    # MotionClone: the real project that matches the description (MIT, measures web motion as numbers and rebuilds it)
    clone = clones / "motionclone"
    repo = "https://github.com/codename-zen/motionclone"
    add_source("motionclone", clone, repo, clone)
    add_skill("motionclone", clone, repo, clone / "skill", "motionclone", "motionclone", "skill")

    for skill in skills:                  # every vendored file is pinned by its hash; creative/skills_library.verify() re-checks them
        skill["files"] = {rel: hashlib.sha256((OUT / rel).read_bytes()).hexdigest() for rel in [skill["path"], *skill["references"]]}
    skills.sort(key=lambda s: s["id"])
    (OUT / "SOURCES.json").write_text(json.dumps(sources, indent=1, ensure_ascii=False) + "\n")
    (OUT / "index.json").write_text(json.dumps({"schema_version": 1, "skills": skills}, indent=1, ensure_ascii=False) + "\n")
    rows = "\n".join(f"| {s['namespace']} | {s['repo']} | `{s['revision']}` | {s['license']} · © {s['copyright']} |" for s in sources)
    excluded = "\n".join(f"- `{k}`: {v}" for k, v in sorted(RUNTIME_NEEDED.items()))
    (OUT / "README.md").write_text(f"""# Vendored craft skills

Text of {len(skills)} open-source motion/creative skills, read on demand by `creative/skills_library.py` and listed in the creative resource registry
(`engine: skill`). They are guidance for the existing engines (HyperFrames, Remotion, GSAP/HTML, FFmpeg); nothing here is executed. Regenerate with
`python scripts/vendor_motion_skills.py <dir with the clones>`; `creative.skills_library.verify()` re-checks every file against the SHA-256 hashes in `index.json`.

| id prefix | repository | revision | licence |
|---|---|---|---|
{rows}

Only Markdown/TXT is vendored. Scripts, binaries, audio, fonts, fixtures and After Effects files are not. Each licence file is kept in `_licenses/`.

## Listed for discovery but never offered to the planner
{excluded}

## Not imported
- `after-effects` (iArt motion-design pack): the studio has no After Effects.
- `blixvip/MotionClone` (the address in the request) does not exist. `codename-zen/motionclone` (MIT, measures web motion as numbers and rebuilds it) matches the described purpose and is registered as a skill whose runtime is optional. `LPengYang/MotionClone` (ICLR 2025 video diffusion research) is a GPU model with no licence file, so nothing was copied from it.
- iArt packs not taken: manim, text-message, map, freelance, generative-illustration, talking-head (generates footage with external models), web-animation (front-end development).
""", encoding="utf-8")
    total = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    print(f"{len(skills)} skills from {len(sources)} sources, {total / 1024:.0f} KB")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
