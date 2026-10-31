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
    from creative.native_motion import CATALOG_CONTRACT, SUPPORTED
    assert request.count(CATALOG_CONTRACT) == 1
    assert all(resource in request for resource in SUPPORTED)
    assert len(request) < 50_000  # Shared instructions must not be duplicated 45 times.


def test_planner_shared_metadata_compaction_is_lossless():
    import json
    from creative.native_motion import CATALOG_CONTRACT,catalog
    request=mg.plan_request('synthetic metadata audit')
    packed=json.loads(request.split(CATALOG_CONTRACT+'\n',1)[1].split('\nUse only',1)[0])
    original=catalog()
    for expected,row in zip(original,packed['entries'],strict=True):
        restored={**{k:[] for k,v in expected.items() if v==[]},**packed['shared_metadata'],**row}
        assert restored==expected


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


@pytest.mark.parametrize("name,key,value", [("marker-checklist-card","top","این متن بیش از حد طولانی است"),
                                            ("social-proof-card","proof",""),
                                            ("notes-typing","title","الف"*61)])
def test_copy_is_rejected_instead_of_silently_truncated_or_replaced(name,key,value):
    with pytest.raises(ValidationError):
        NativeMotion(resource_id="hyperframes:"+name,text="نمونه",parameters={key:value})


def test_namespaces_nested_ids(tmp_path):
    spec = NativeMotion(resource_id="hyperframes:cursor-text-select", text="نمونه", parameters={"title":"نمونه", "text":"متن نمونه", "phrase":"نمونه"})
    materialize(tmp_path, spec, "s4-native", 4)
    source = (tmp_path / "compositions/s4-native.html").read_text()
    assert 'getElementById("s4-native-ts-title")' in source
    assert 'id="ts-title"' not in source
    render = source.split('function render(t) {')[1].split('var clock = { t: 0 };')[0]
    assert 'offsetIn(' not in render
    assert '.offsetWidth' not in render and '.offsetHeight' not in render
    assert 'document.fonts.ready.then(buildReady)' in source


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


@pytest.mark.parametrize("name,parameters", [
    ("beat-timeline", {"beatCount":4,"labels":"یک,دو"}),
    ("chart-story", {"type":"bars","data":"12,NaN","labels":"الف,ب","emphasize":1,"unit":""}),
    ("chart-story", {"type":"bars","data":"12,24","labels":"الف","emphasize":1,"unit":""}),
    ("tracing-beam", {"labels":"یک,دو"}),
    ("per-word-rise", {"text":"می‌توانیم", "split":"char"}),
    ("cursor-text-select", {"title":"نمونه", "text":"متن درست", "phrase":"غایب"}),
])
def test_production_content_cannot_use_hidden_defaults_or_broken_persian(name, parameters):
    from creative.native_motion import content_problems
    assert content_problems(NativeMotion(resource_id="hyperframes:"+name,text="نمونه",parameters=parameters))


def test_original_task_animation_uses_explicit_labels(tmp_path):
    from creative.native_motion import content_problems
    spec = NativeMotion(resource_id="hyperframes:overwhelm-surround",text="کارها",
                        parameters={"count":8,"centerLabel":"شما","task_labels":"ایمیل,ویرایش,بررسی,انتشار,طراحی,صدا,تصویر,متن"})
    assert not content_problems(spec, 4)
    materialize(tmp_path,spec,"s1-native",4)
    source = (tmp_path / "compositions/s1-native.html").read_text()
    assert "var labels = String(vars.task_labels)" in source
    assert '"Inbox",' not in source


def test_notes_keep_connected_persian_words_and_caret_direction(tmp_path):
    spec = NativeMotion(resource_id="hyperframes:notes-typing",text="یادداشت",
                        parameters={"title":"روایت", "lines":"می‌توانیم بهتر بسازیم"})
    materialize(tmp_path,spec,"s1-native",12)
    source = (tmp_path / "compositions/s1-native.html").read_text()
    assert 'rtlLine ? (line.match(/\\S+\\s*/g)' in source
    assert 'c.rtl ? r.left : r.right' in source
    assert 'c.rtl ? Math.max(1, c.el.textContent.length)' in source


def test_supporting_demo_claims_have_required_typed_bindings(tmp_path):
    from creative.native_motion import parameter_schema, content_problems
    from scripts.component_examples import PERSIAN_CONTENT
    name = "pull-back-reveal"
    assert parameter_schema(name)["support_a_value"]["role"] == "content"
    spec = NativeMotion(resource_id="hyperframes:"+name,text="ایده",parameters=PERSIAN_CONTENT[name])
    assert not content_problems(spec, 4)
    materialize(tmp_path,spec,"s1-native",4)
    source = (tmp_path / "compositions/s1-native.html").read_text()
    assert '["support_a_value", ".pbr-support-value", 0]' in source
    assert 'node.appendChild(document.createTextNode(vars[binding[0]]))' in source
    assert content_problems(spec.model_copy(update={"parameters":{"detail_text":"ایده","headline":"روایت"}}))


def test_plain_ampersand_is_data_not_html(tmp_path):
    spec = NativeMotion(resource_id="hyperframes:text-shimmer",text="R&D",parameters={"text":"R&D"})
    materialize(tmp_path,spec,"s1-native",4)
    source = (tmp_path / "compositions/s1-native.html").read_text()
    assert 'R\\u0026D' in source


@pytest.mark.parametrize("name", __import__("creative.native_motion", fromlist=["source_names"]).source_names())
def test_every_vendored_component_materializes_with_integrity(tmp_path, name):
    import hashlib
    from creative.native_motion import SOURCES
    receipt = materialize(tmp_path, NativeMotion(resource_id="hyperframes:" + name, text="نمونه"), "s1-native", 4)
    assert receipt["source_sha256"] == hashlib.sha256((SOURCES / (name + ".html")).read_bytes()).hexdigest()
    source = (tmp_path / "compositions/s1-native.html").read_text()
    assert '<script src="https:' not in source
    assert 'data-composition-id="s1-native"' in source
