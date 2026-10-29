"""Real metadata/API/tool tests. No paid models, media generation or downloads."""
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from creative.resources import providers, registry
from app.routers.creative_resources import router


def test_pinned_installer_rejects_tampering_and_unknown_names(tmp_path, monkeypatch):
    import hashlib
    from engine.hyperframes import registry_pins as pins
    source, license_text = b"<html>reviewed source</html>", b"reviewed license"
    monkeypatch.setattr(pins, "PINS", {"known": hashlib.sha256(source).hexdigest()})
    monkeypatch.setattr(pins, "LICENSE_SHA256", hashlib.sha256(license_text).hexdigest())
    urls = []
    def fetch(url):
        urls.append(url)
        return license_text if url.endswith("/LICENSE") else source
    monkeypatch.setattr(pins, "_fetch", fetch)
    assert not pins.install_pinned(tmp_path, "../../escape") and not urls
    assert pins.install_pinned(tmp_path, "known")
    receipt = json.loads((tmp_path / "resource-receipts/known.json").read_text())
    assert receipt["upstream_commit"] in receipt["source_url"]
    assert not receipt["commercial_use_approved"]
    monkeypatch.setattr(pins, "_fetch", lambda url: b"tampered")
    with pytest.raises(ValueError, match="integrity"):
        pins.install_pinned(tmp_path, "known")
    assert (tmp_path / "compositions/components/known.html").read_bytes() == source


def test_pinned_installer_rejects_symlink_escape(tmp_path, monkeypatch):
    import hashlib
    from engine.hyperframes import registry_pins as pins
    root, outside = tmp_path / "project", tmp_path / "outside"
    root.mkdir(); outside.mkdir()
    (root / "compositions").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(pins, "PINS", {"known": hashlib.sha256(b"x").hexdigest()})
    monkeypatch.setattr(pins, "LICENSE_SHA256", hashlib.sha256(b"x").hexdigest())
    monkeypatch.setattr(pins, "_fetch", lambda url: b"x")
    with pytest.raises(ValueError, match="escapes"):
        pins.install_pinned(root, "known")


def test_real_native_qc_allows_intentional_static_black_and_detects_truncation(tmp_path):
    import subprocess
    import shutil
    from engine.hyperframes.quality import review_render, improve_beats
    from engine.hyperframes.schema import VisualBeat
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("Native media tools unavailable")
    video = tmp_path / "intentional-black.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "color=c=black:s=64x96:r=30:d=4", "-c:v", "libx264", str(video)],
                   check=True, capture_output=True, timeout=30)
    beats = [VisualBeat(id="first", start=0, end=1.5, title="شروع", visual_type="steps"),
             VisualBeat(id="last", start=1.5, end=3.5, title="پایان", visual_type="steps")]
    report = review_render(video, beats, tmp_path)
    assert report["passed"] and report["status"] == "passed"
    assert report["samples"] == 2 and report["warnings"]
    assert report["media"]["width"] == 64
    before = [b.model_dump() for b in beats]
    assert [b.model_dump() for b in improve_beats(beats)] == before
    beats[-1].end = 5
    report = review_render(video, beats, tmp_path)
    assert report["status"] == "failed"
    assert "output ends before an approved visual beat" in report["problems"]


def test_qc_unavailable_is_not_reported_as_visual_defect(tmp_path, monkeypatch):
    import subprocess
    from engine.hyperframes import quality
    def timed_out(*args, **kwargs):
        raise subprocess.TimeoutExpired("inspection", 30)
    monkeypatch.setattr(quality.subprocess, "run", timed_out)
    report = quality.review_render(tmp_path / "video.mp4", [], tmp_path)
    assert report["status"] == "unavailable" and not report["passed"]
    assert not report["problems"] and report["unavailable"]


def test_source_grounded_resource_planning_and_compiler_binding():
    from creative.resources.planning import plan_talking_resources, resolve_talking_recipe
    from creative.schemas import Beat, Concept, ContentBrief, Critique, CreativePlan
    from creative.production import bind_talking
    beats = [Beat(sentence=0, title="سه مرحله", visual_type="steps", role="steps"),
             Beat(sentence=1, title="آمار", visual_type="stat"),
             Beat(sentence=99, title="نامعتبر")]
    sentences = [{"text": "سه مرحله برای شروع"}, {"text": "عدد مشخصی نداریم"}]
    choices = plan_talking_resources(beats, sentences, "talking_2")
    assert choices[0]["resource_id"] == "editorgpt-recipe:steps-rail"
    assert choices[1]["reason"] == "no-numeric-source-evidence"
    assert choices[2]["reason"] == "missing-source-anchor"
    assert plan_talking_resources(beats, sentences, "talking_1") == []
    assert resolve_talking_recipe(choices[0]["resource_id"], "steps").renderer == "steps"
    with pytest.raises(ValueError): resolve_talking_recipe("hyperframes:data-chart", "steps")
    with pytest.raises(ValueError): resolve_talking_recipe(choices[0]["resource_id"], "stat")
    concept = Concept(id="A", name="Test", angle="Teaching", hook="Start", beats=beats[:1])
    plan = CreativePlan(kind="talk", brief=ContentBrief(topic="Test", core_message="Steps"),
                        concepts=[concept], chosen=concept, critique=Critique(chosen_id="A"),
                        style="talking_2", resource_choices=choices[:1])
    board = bind_talking(plan, {}, sentences)["storyboard"]
    assert board[0]["resource_id"] == choices[0]["resource_id"]
    assert plan.public()["resource_choices"] == choices[:1]


def test_repeated_steps_are_not_replaced_with_unrelated_visual_types():
    from engine.hyperframes.builder import build_visual_beats
    from types import SimpleNamespace
    plan = SimpleNamespace(duration=30, shots=[SimpleNamespace(src_in=0, src_out=30, out_start=0)])
    sentences = [{"start": 0, "end": 10, "text": "مرحله اول"}, {"start": 10, "end": 20, "text": "مرحله دوم"}]
    decisions = {"storyboard": [{"i": i, "title": "مرحله", "items": ["شروع", "پایان"], "visual_type": "steps"} for i in range(2)]}
    beats = build_visual_beats(plan, decisions, {"sentences": sentences})
    assert [b.visual_type for b in beats] == ["steps", "steps"]
    assert [b.sentence_indices for b in beats] == [[0], [1]]


def test_snapshot_fingerprints_are_actual_and_not_license_approval():
    from creative.resources.provenance import snapshot_integrity
    report = snapshot_integrity()
    assert report["verified"] and len(report["files"]) == 6
    assert not report["license_approved"] and not report["upstream_install_pinned"]


def test_snapshot_tampering_or_missing_sources_is_visible(tmp_path, monkeypatch):
    from creative.resources import provenance
    monkeypatch.setattr(provenance, "ROOT", tmp_path)
    monkeypatch.setattr(provenance, "SNAPSHOT", {"changed.json": "0" * 64, "missing.json": "1" * 64})
    (tmp_path / "changed.json").write_text("changed")
    report = provenance.snapshot_integrity()
    assert not report["verified"]
    assert report["files"][0]["actual_sha256"] is not None
    assert report["files"][1]["actual_sha256"] is None


def test_resource_selection_never_switches_engines_or_promotes_unknown_capabilities():
    from creative.resources.selection import ResourceRequirements, assess_resource
    requirements = ResourceRequirements(context="edit-plan", engine="mlt", kind="transition")
    assert assess_resource("editorgpt-transition:crossfade", requirements)["eligible"]
    assert not assess_resource("hyperframes:data-chart", requirements)["eligible"]
    assert assess_resource("missing:resource", requirements)["reasons"] == ["unknown-resource"]
    strict = requirements.model_copy(update={"require_rtl": True, "require_alpha": True,
                                              "require_commercial_approval": True})
    result = assess_resource("editorgpt-transition:crossfade", strict)
    assert not result["eligible"]
    assert set(result["reasons"]) == {"unverified-supports_rtl", "unverified-transparent", "commercial-license-not-approved"}


def test_snapshot_indexes_existing_sources_without_claiming_execution():
    from engine.hyperframes.catalog import load_catalog
    from engine.effects_v4 import EFFECT_CATALOG_V4
    from engine.motion_recipes import RECIPES
    summary = registry.registry_summary()
    from creative.shotcraft import catalog as shotcraft_catalog
    assert summary["total"] == len(load_catalog()["items"]) + len(EFFECT_CATALOG_V4) + 4 + len(RECIPES) + len(shotcraft_catalog())
    rows = registry.search_resources(limit=100)["items"]
    assert len({r["id"] for r in rows}) == len(rows)
    assert all(r["render_time_ms"] is None and r["peak_memory_mb"] is None for r in rows)
    assert all(not r["license"]["verified"] for r in rows)


def test_only_real_hyperframes_adapters_are_connected():
    from engine.hyperframes.registry_runtime import SUPPORTED_REGISTRY_ADAPTERS
    rows = registry.search_resources(engine="hyperframes", provider="hyperframes-official",
                                     availability="existing-pipeline")["items"]
    assert {r["legacy_id"] for r in rows} == SUPPORTED_REGISTRY_ADAPTERS
    assert all(r["contexts"] == ["talking_2"] for r in rows)
    assert registry.get_resource("hyperframes:data-chart")["availability"] == "catalog-only"


def test_unsupported_effects_not_silently_promoted():
    row = registry.get_resource("editorgpt:speed_ramp")
    assert row["availability"] == row["integration_status"] == "unsupported"
    assert "timing" in row["limitations"][0]


def test_transition_mapping_preserves_legacy_renderer():
    row = registry.get_resource("editorgpt-transition:crossfade")
    assert row["engine"] == "mlt"  # do not mislabel existing MLT as native xfade
    assert row["legacy_id"] == "crossfade"


def test_snapshot_metadata_does_not_certify_rtl_from_orientation():
    row = registry.get_resource("hyperframes:caption-kinetic-slam")
    assert row["capabilities"]["supports_rtl"] is None
    assert row["capabilities"]["supports_vertical"] is None
    assert all(not p["editable"] for p in row["parameters"])


def test_search_filter_pagination_and_stable_revision():
    full = registry.search_resources(engine="hyperframes", limit=100)
    first = registry.search_resources(engine="hyperframes", limit=3)
    second = registry.search_resources(engine="hyperframes", limit=3, offset=3)
    assert first["items"] + second["items"] == full["items"][:6]
    assert first["total"] == second["total"]
    assert registry.search_resources("nonexistentxyz")["items"] == []
    assert registry.registry_summary()["revision"] == registry.registry_summary()["revision"]
    assert "kinetic" in json.dumps(registry.search_resources("kinetic typography")["items"]).lower()


@pytest.mark.parametrize("kwargs", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"offset": 10001}, {"query": "x" * 301}])
def test_boundaries(kwargs):
    with pytest.raises(ValueError):
        registry.search_resources(**kwargs)


def test_snapshot_cannot_be_mutated_through_public_dict():
    row = registry.get_resource("hyperframes:data-chart")
    row["license"]["verified"] = True
    row["tags"].append("secret")
    again = registry.get_resource("hyperframes:data-chart")
    assert not again["license"]["verified"] and "secret" not in again["tags"]


@pytest.mark.parametrize("value", ["http://127.0.0.1/file", "https://evil.example/video.mp4", "javascript:alert(1)",
                                   "https://static.heygen.ai.evil/hyperframes/file", "https://static.heygen.ai/hyperframes/v.mp4?key=secret"])
def test_preview_rejects_untrusted_urls(value):
    assert providers._preview_url(value) is None


def test_discovery_never_runs_network_shell_or_mutates_project(monkeypatch):
    import subprocess
    import httpx
    def forbidden(*args, **kwargs):
        pytest.fail("Discovery must be read-only, local metadata")
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(httpx, "get", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)
    registry._snapshot.cache_clear()
    assert registry.registry_summary()["total"] > 400


def test_http_contract_bounds_details_and_no_store():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    response = client.get("/creative-resources?q=kinetic&limit=2")
    assert response.status_code == 200 and len(response.json()["items"]) == 2
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/creative-resources?limit=101").status_code == 422
    assert client.get("/creative-resources/unknown:thing").status_code == 404
    assert client.get("/creative-resources/summary").json()["total"] > 400
    assert client.get("/creative-resources/hyperframes:data-chart").json()["id"] == "hyperframes:data-chart"
    assert client.post("/creative-resources/hyperframes:data-chart", json={"install": True}).status_code == 405


def test_app_auth_not_bypassed_for_resource_routes():
    from app.main import app
    # No lifespan: don't start real workers or recover the developer's jobs.
    client = TestClient(app, base_url="https://lan.editor.invalid")
    assert client.get("/creative-resources").status_code == 401
    assert client.get("/creative-resources/summary").status_code == 401


def test_shared_and_medium_tool_validation_without_mutation():
    from app import studio_tools
    from app.agents.medium import tools
    result = studio_tools.execute("search_creative_resources", {"query": "chart", "limit": 2})
    assert len(result["items"]) == 2
    assert "search_creative_resources" in tools.READ_ONLY
    spec = next(t for t in tools.catalog() if t["name"] == "search_creative_resources")
    assert not spec["requires_approval"]
    assert tools.execute({"id": "test"}, {"tool": "search_creative_resources", "arguments": {"query": "chart", "limit": 2}}) == result
    with pytest.raises(ValueError):
        studio_tools.execute("search_creative_resources", {"query": "chart", "path": "/etc/passwd"})
    with pytest.raises(KeyError):
        registry.get_resource("../../etc/passwd")
