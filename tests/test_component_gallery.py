"""Frozen preview inventory is evidence, never an automatic execution allowlist."""
import hashlib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GALLERY = ROOT / "web/public/creative-previews"


@pytest.mark.parametrize("filename,count", [("index.json",45),("claude-effects.json",42),("shotcraft.json",10),("lemo.json",1)])
def test_gallery_has_real_local_images_and_truthful_status(filename, count):
    rows = json.loads((GALLERY / filename).read_text())["items"]
    assert len(rows) == count
    for row in rows.values():
        assert re.fullmatch(r"/creative-previews/[a-z0-9-]+\.png", row["poster"])
        image = GALLERY / row["poster"].rsplit("/",1)[1]
        assert image.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        if row.get("poster_sha256"):
            assert hashlib.sha256(image.read_bytes()).hexdigest() == row["poster_sha256"]
        if filename in {"shotcraft.json", "lemo.json"}:
            assert row["demonstration_only"] is True
            assert row["production_template_ready"] is False


def test_vendored_lemo_and_shotcraft_dependencies_are_pinned():
    for directory, filename in [("lemo_data","manifest.json"),("shotcraft_data","runtime_sha256.json")]:
        base = ROOT / "creative" / directory
        manifest = json.loads((base / filename).read_text())
        for name, expected in manifest["sha256"].items():
            source = (base / name).resolve()
            assert source.is_relative_to(base.resolve())
            assert hashlib.sha256(source.read_bytes()).hexdigest() == expected
