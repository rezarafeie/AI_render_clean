"""Where a project's scratch folders (the panel render, the sparse frames) live.

Beside the project, as always, so local caches keep their place. A cloud worker can write only inside the project's own folder (its filesystem is
read-only elsewhere): there the scratch folder is a hidden folder inside the project instead, which a snapshot of the project never includes.
"""
from __future__ import annotations

import uuid
from pathlib import Path


def writable(directory: Path) -> bool:
    probe = directory / f".write-test-{uuid.uuid4().hex[:8]}"
    try:
        probe.touch()
        probe.unlink()
        return True
    except OSError:
        return False


def scratch_dir(project: Path, name: str) -> Path:
    sibling = project.parent / name
    if sibling.exists() or writable(project.parent):
        return sibling
    return project / f".{name.replace('_', '-')}"
