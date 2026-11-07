"""Freeze an authorized project directory without altering any engine's timeline.

This is not an authorization API. Callers must first obtain a root through the
existing project ownership checks. Cloud admission still requires network
isolation; static checks cannot make arbitrary generated JavaScript a sandbox.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .contracts import Asset, RenderSpec, relative_path


def freeze(root: Path, paths: list[str], **render_fields) -> RenderSpec:
    root = root.resolve(strict=True)
    assets = []
    allowance = render_fields['workspace_bytes']
    used = 0
    if not 1 <= len(paths) <= 20000:
        raise ValueError('Invalid asset count')
    for name in paths:
        relative_path(name)
        path = root / name
        # Refuse symlinks in every component, even when pointing back into root.
        # No machine-local indirection is portable to a cloud workspace.
        cursor = root
        for part in Path(name).parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise ValueError('Symlink inputs are not portable')
        if not path.resolve(strict=True).is_relative_to(root) or not path.is_file():
            raise ValueError('Input is outside the owned project')
        size = path.stat().st_size
        used += size
        if used > allowance:
            raise ValueError('Workspace budget exceeded')
        digest = hashlib.sha256()
        with path.open('rb') as source:
            for block in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(block)
        # Freeze races are rejected instead of uploading inconsistent metadata.
        if path.stat().st_size != size:
            raise ValueError('Project changed during preparation')
        assets.append(Asset(path=name, sha256=digest.hexdigest(), size=size))
    return RenderSpec(assets=assets, **render_fields)
