#!/usr/bin/env python3
"""Add the FFmpeg know-how of kajisho5/ffmpeg-skill (MIT) to vendor/motion-skills/ as ONE agent-reference skill, `ffmpegskill:ffmpeg-skill`.

    python scripts/vendor_ffmpeg_skill.py /path/to/ffmpeg-skill [--remove]

Only the Markdown that is guidance is copied: the workflow digest (probe -> lossless first -> dry run -> chain -> check -> look) as the skill body and gotchas, workflow, timestamps,
flags and process-pitfalls as reference files. None of its 42 Python tools is copied or executed: EditorGPT already has FFmpeg/MLT code, so this is *reference for agents*
(read_creative_skill), listed as catalog-only (never offered to the motion planner). Re-running replaces only the `ffmpegskill` entry.
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
NS = "ffmpegskill"
REPO = "https://github.com/kajisho5/ffmpeg-skill"
REFS = ["gotchas.md", "workflow.md", "timestamps.md", "flags.md", "process-pitfalls.md"]


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
        (OUT / "_licenses" / NS / "ffmpeg-skill.LICENSE").write_text(licence)
        sources.append({"namespace": NS, "repo": REPO, "revision": rev, "license": "MIT", "copyright": holder.group(1).strip() if holder else "",
                        "license_file": f"_licenses/{NS}/ffmpeg-skill.LICENSE", "vendored": "Markdown guidance only (workflow digest and five reference files); none of its Python tools"})
        text = (clone / "SKILL.md").read_text(encoding="utf-8")
        text = re.sub(r"\A---\s*\n.*?\n---\s*\n", "", text, count=1, flags=re.S)
        keep = [part for part in re.split(r"(?m)^(?=## )", text) if part.startswith(("## Workflow", "## Before you run anything", "## What this skill does and does not decide"))]
        body = "# FFmpeg editing know-how (digest of kajisho5/ffmpeg-skill, MIT)\n\n" + "\n".join(keep)
        skill = OUT / NS / "ffmpeg-skill"
        (skill / "references").mkdir(parents=True)
        (skill / "SKILL.md").write_text(body, encoding="utf-8")
        files = {f"{NS}/ffmpeg-skill/SKILL.md": hashlib.sha256(body.encode()).hexdigest()}
        refs = []
        for name in REFS:
            data = (clone / "references" / name).read_bytes()
            (skill / "references" / name).write_bytes(data)
            files[f"{NS}/ffmpeg-skill/references/{name}"] = hashlib.sha256(data).hexdigest()
            refs.append(f"{NS}/ffmpeg-skill/references/{name}")
        hint = "FFmpeg editing know-how for agents: probe first, lossless before re-encode, dry run, filter order, timestamps, loudness, platform exports, checking the output"
        index["skills"].append({"id": f"{NS}:ffmpeg-skill", "name": "ffmpeg-skill", "namespace": NS, "pack": "ffmpeg-skill", "description": hint, "repo": REPO, "revision": rev,
                                "path": f"{NS}/ffmpeg-skill/SKILL.md", "subpath": "SKILL.md", "bytes": len(body.encode()), "references": refs, "tags": ["ffmpeg", "sound"],
                                "runtime_needed": "agent reference for FFmpeg/MLT edits; not a motion-design skill, so the motion planner is not offered it", "license": "MIT",
                                "hint": hint, "body_chars": 4000, "files": files})
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "SOURCES.json").write_text(json.dumps(sources, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]), "--remove" in sys.argv)
