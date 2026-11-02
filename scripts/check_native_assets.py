#!/usr/bin/env python3
"""Fail deployment before startup if bind-mounted native components are missing."""
import hashlib
import json
from pathlib import Path


def verify(directory: Path) -> int:
    manifest = directory / "MANIFEST.json"
    if not manifest.is_file():
        raise ValueError(f"Missing native library: {manifest}. Deploy assets/hyperframes_components into the assets mount.")
    files = json.loads(manifest.read_text(encoding="utf-8"))["files"]
    if not files:
        raise ValueError("Native component manifest is empty")
    for name, expected in files.items():
        if Path(name).name != name or name in {".", ".."}:
            raise ValueError("Invalid native component name")
        source = directory / f"{name}.html"
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != expected["sha256"]:
            raise ValueError(f"Missing or modified native component: {name}")
    return len(files)


if __name__ == "__main__":
    directory = Path(__file__).resolve().parents[1] / "assets/hyperframes_components"
    print(f"Native assets verified: {verify(directory)} components")
