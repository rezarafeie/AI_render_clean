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
        assert row["status"] == ("browser-checked" if filename == "index.json" else "synthetic-frame-checked" if filename == "claude-effects.json" else "upstream-demo-checked")
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


@pytest.mark.parametrize("resource",["shotcraft:bezier-source-converge-merge","shotcraft:text-column-converge"])
def test_native_shotcraft_preview_is_encoded_and_frozen(resource):
    from creative.shotcraft_native import source_fingerprint
    rows = json.loads((GALLERY / "native-shotcraft.json").read_text())["items"]
    assert set(rows) == {"shotcraft:bezier-source-converge-merge","shotcraft:text-column-converge"}
    row = rows[resource]
    assert row["status"] == "native-component-checked"
    assert row["encoded_output_verified"] and row["hybrid_browser_checked"]
    assert row["source_adapter_sha256"] == source_fingerprint()
    for field, digest in [("poster", "poster_sha256"), ("preview_video", "video_sha256")]:
        path = GALLERY / row[field].rsplit("/", 1)[1]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row[digest]
    assert row["media"]["max_keyframe_interval"] <= 1.1
    assert row["frame_audit"]["decoded_frames"] == 180
    assert row["hybrid_opening_audit"]["decoded_frames"] == 1
    assert row["frame_audit"]["min_bright_pixels" if resource.endswith("text-column-converge") else "min_dark_pixels"] >= 12
    html = (GALLERY / "gallery.html").read_text()
    assert "native-shotcraft.json" in html
    assert "preload='none'" in html or 'preload="none"' in html or "preload='none'" in html.replace('"', "'")


@pytest.mark.parametrize("blank", [255, 0])
def test_frame_gate_rejects_blank_middle_frames(monkeypatch, blank):
    from scripts import build_native_shotcraft_preview as audit
    from types import SimpleNamespace
    size=288*512
    valid=bytes([40])*100+bytes([240])*(size-100)
    monkeypatch.setattr(audit.subprocess,"run",lambda *a,**k:SimpleNamespace(stdout=valid+bytes([blank])*size+valid))
    with pytest.raises(ValueError,match="index 1"):
        audit.inspect_light_fixture_frames(Path("synthetic.mp4"))


def test_frame_gate_checks_complete_encoded_sequence(monkeypatch):
    from scripts import build_native_shotcraft_preview as audit
    from types import SimpleNamespace
    valid=bytes([40])*100+bytes([240])*(288*512-100)
    monkeypatch.setattr(audit.subprocess,"run",lambda *a,**k:SimpleNamespace(stdout=valid*5))
    assert audit.inspect_light_fixture_frames(Path("synthetic.mp4"))["decoded_frames"] == 5


@pytest.mark.parametrize("blank",[0,255])
def test_dark_fixture_gate_rejects_blank_frames(monkeypatch,blank):
    from scripts import build_native_shotcraft_preview as audit
    from types import SimpleNamespace
    size=288*162
    valid=bytes([240])*100+bytes([20])*(size-100)
    monkeypatch.setattr(audit.subprocess,"run",lambda *a,**k:SimpleNamespace(stdout=valid+bytes([blank])*size))
    with pytest.raises(ValueError,match="index 1"):
        audit.inspect_light_fixture_frames(Path("synthetic.mp4"),dark_background=True,height=162)


def test_native_frame_gate_rejects_wrong_or_unbounded_sequence(monkeypatch):
    from creative.native_video_checks import inspect_native_frames
    from types import SimpleNamespace
    import creative.native_video_checks as checks
    valid=bytes([40])*100+bytes([240])*(288*512-100)
    monkeypatch.setattr(checks.subprocess,"run",lambda *a,**k:SimpleNamespace(stdout=valid*2))
    with pytest.raises(ValueError,match="frame count"):
        inspect_native_frames("synthetic.mp4",expected_frames=180)
    with pytest.raises(ValueError,match="dimensions"):
        inspect_native_frames("synthetic.mp4",width=99999)


def test_every_generic_adapter_has_explicit_valid_persian_test_content():
    from creative.native_motion import NativeMotion, SUPPORTED, LEGACY_INPUTS, content_problems
    from scripts.component_examples import PERSIAN_CONTENT
    assert set(PERSIAN_CONTENT) == {s.split(":")[1] for s in SUPPORTED if s not in LEGACY_INPUTS}
    for name, values in PERSIAN_CONTENT.items():
        spec = NativeMotion(resource_id="hyperframes:"+name,text="نمونه",parameters=values)
        assert not content_problems(spec, 20), (name, content_problems(spec, 20))
