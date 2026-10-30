import json

import pytest
from pydantic import ValidationError

from creative.native_motion import NativeMotion, materialize
from creative import motion_graphic as mg


@pytest.mark.parametrize("name", ["headline-slam", "cta-close", "count-up"])
def test_original_code_materialized_offline(tmp_path, name):
    spec = NativeMotion(resource_id=f"hyperframes:{name}", text="سلام می‌کنیم </script>", button_label="شروع")
    receipt = materialize(tmp_path, spec, "s2-native", 4)
    source = (tmp_path / "compositions/s2-native.html").read_text()
    assert 'window.__timelines["s2-native"] = tl' in source
    assert 'getElementById("s2-native")' in source
    assert "cdn.jsdelivr" not in source
    assert "\\u003c/script\\u003e" in source
    assert receipt["integration"] == "vendored-code-execution"
    assert not receipt["render_verified"]
    assert (tmp_path / "compositions/LICENSE.hyperframes").exists()


def test_count_uses_validated_numbers_and_original_counter(tmp_path):
    spec = NativeMotion(resource_id="hyperframes:count-up", text="تعداد", end_value=320, suffix=" نفر")
    materialize(tmp_path, spec, "s1-native", 4)
    source = (tmp_path / "compositions/s1-native.html").read_text()
    assert '"end": 320' in source
    assert 'toLocaleString("fa-IR")' in source
    assert "frameRows.forEach" in source
    with pytest.raises(ValidationError):
        NativeMotion(resource_id="hyperframes:count-up", text="تعداد", end_value=float("inf"))


def test_tampered_component_fails_closed(tmp_path, monkeypatch):
    import creative.native_motion as native
    fake = tmp_path / "vendor"
    fake.mkdir()
    (fake / "MANIFEST.json").write_text(json.dumps({"files": {"headline-slam": {"sha256": "bad"}}}))
    (fake / "headline-slam.html").write_text("tampered")
    monkeypatch.setattr(native, "SOURCES", fake)
    with pytest.raises(ValueError, match="integrity"):
        materialize(tmp_path / "project", NativeMotion(resource_id="hyperframes:headline-slam", text="تست"), "s1-native", 4)


def test_input_is_not_code_or_path(tmp_path):
    with pytest.raises(ValidationError):
        NativeMotion(resource_id="../../secret", text="x")
    with pytest.raises(ValidationError):
        NativeMotion(resource_id="hyperframes:headline-slam", text="x", arbitrary_js="alert(1)")
    with pytest.raises(ValueError):
        materialize(tmp_path, NativeMotion(resource_id="hyperframes:headline-slam", text="x"), "../escape", 4)


def test_scene_bypasses_model_and_preserves_native_contract(monkeypatch):
    monkeypatch.setattr(mg.llm, "ask", lambda *a, **k: pytest.fail("Native code must not be rewritten by model"))
    scene = mg.ScenePlan(headline="سلام دنیا", idea="title", start=0, end=4,
                         native_component=NativeMotion(resource_id="hyperframes:headline-slam", text="سلام دنیا"))
    plan = mg.MotionPlan(duration=4, scenes=[scene])
    draft = mg.author_scene(plan, 1, "title")
    page = mg.assemble_scenes(plan, [draft])
    assert len(page.native_components) == 1
    assert 'data-composition-src="compositions/s1-native.html"' in page.scenes_html
    assert "HM.wipe" not in page.build_js
    assert not mg.validate_page(page)
    assert mg.MotionPage.model_validate_json(page.model_dump_json()).native_components == page.native_components


def test_planner_discovers_native_code_separately_from_references():
    request = mg.plan_request("موشن فارسی")
    assert "EXECUTABLE COMPONENTS" in request
    assert "hyperframes:count-up" in request
    assert "AVAILABLE SHOTCRAFT REFERENCES" in request


def test_native_failure_never_enters_plain_title_isolation(tmp_path):
    from types import SimpleNamespace
    from app.motion_graphic import _isolate
    with pytest.raises(RuntimeError, match="refusing plain-title"):
        _isolate(tmp_path, tmp_path, None, SimpleNamespace(native_components=[{}]), ["runtime error"], [])


def test_upstream_parameter_schema_is_enforced():
    spec = NativeMotion(resource_id="hyperframes:line-swap", text="تغییر", parameters={"line_a":"قبل", "line_b":"بعد", "swap_at":1.2})
    assert spec.parameters["line_b"] == "بعد"
    for params in ({"line_a":"<img onerror=x>"}, {"swap_at":float("nan")}, {"script":"x"}, {"accent":"invalid"}):
        with pytest.raises(ValidationError):
            NativeMotion(resource_id="hyperframes:line-swap", text="تغییر", parameters=params)


def test_namespaces_nested_ids(tmp_path):
    spec = NativeMotion(resource_id="hyperframes:cursor-text-select", text="نمونه", parameters={"title":"نمونه", "text":"متن نمونه", "phrase":"نمونه"})
    materialize(tmp_path, spec, "s4-native", 4)
    source = (tmp_path / "compositions/s4-native.html").read_text()
    assert 'getElementById("s4-native-ts-title")' in source
    assert 'id="ts-title"' not in source


def test_namespacing_never_changes_matching_class_names(tmp_path):
    spec = NativeMotion(resource_id="hyperframes:marker-checklist-card", text="نمونه")
    materialize(tmp_path, spec, "s1-native", 4)
    source = (tmp_path / "compositions/s1-native.html").read_text()
    assert 'class="mcc-card" id="s1-native-mcc-card"' in source
    assert 'getElementById("s1-native-mcc-row" +' in source


def test_generic_component_requires_explicit_content_without_calling_model(monkeypatch):
    monkeypatch.setattr(mg.llm, "ask", lambda *a, **k: pytest.fail("No model replacement"))
    spec = NativeMotion(resource_id="hyperframes:line-swap", text="تغییر")
    scene = mg.ScenePlan(headline="تغییر", idea="comparison", start=0, end=4, native_component=spec)
    plan = mg.MotionPlan(duration=4, scenes=[scene])
    with pytest.raises(mg.CreativeUnavailable, match="پارامترهای محتوایی"):
        mg.author_scene(plan, 1, "compare")
    scene.native_component = spec.model_copy(update={"parameters": {"line_a": "روش قبلی", "line_b": "روش تازه", "underline_word": "تازه"}})
    assert mg.author_scene(plan, 1, "compare").native_component.parameters["line_b"] == "روش تازه"


@pytest.mark.parametrize("name", __import__("creative.native_motion", fromlist=["source_names"]).source_names())
def test_every_vendored_component_materializes_with_integrity(tmp_path, name):
    import hashlib
    from creative.native_motion import SOURCES
    receipt = materialize(tmp_path, NativeMotion(resource_id="hyperframes:" + name, text="نمونه"), "s1-native", 4)
    assert receipt["source_sha256"] == hashlib.sha256((SOURCES / (name + ".html")).read_bytes()).hexdigest()
    source = (tmp_path / "compositions/s1-native.html").read_text()
    assert '<script src="https:' not in source
    assert 'data-composition-id="s1-native"' in source
