from creative.motion_graphic import repair_js


def test_direct_gsap_calls_move_onto_the_timeline_at_time_zero():
    code = 'gsap.to("#s1 .a", {opacity: 1, duration: .5});\ngsap.fromTo(".b", {y: 10}, {y: 0, duration: 1});\ngsap.set("#s1", {x: 0});'
    fixed = repair_js(code, 10)
    assert fixed == 'tl.to("#s1 .a", {opacity: 1, duration: .5}, 0);\ntl.fromTo(".b", {y: 10}, {y: 0, duration: 1}, 0);\ntl.set("#s1", {x: 0}, 0);'


def test_nested_commas_and_strings_do_not_confuse_the_rewrite():
    code = 'gsap.to(".a,.b", {x: function(i){ return i * 2; }, ease: "power2.out(1, 2)"});'
    assert repair_js(code, 5) == 'tl.to(".a,.b", {x: function(i){ return i * 2; }, ease: "power2.out(1, 2)"}, 0);'


def test_shapes_that_cannot_be_moved_safely_are_left_for_the_validator():
    code = 'gsap.to(".a");\nconst q = gsap.utils.toArray(".x");'
    assert repair_js(code, 5) == code


def test_infinite_repeat_becomes_the_finite_count_that_covers_the_clip():
    fixed = repair_js('tl.to(".spin", {rotation: 360, duration: 2, repeat: -1, ease: "none"}, 0);', 12)
    assert "repeat: 7" in fixed and "-1" not in fixed
    assert "repeat: 13" in repair_js('tl.to(".x", {y: 5, repeat: -1}, 0);', 12)        # no duration given: one second per loop


def test_every_scene_gets_its_start_and_length_as_variables():
    from creative import motion_graphic as mg
    plan = mg.MotionPlan(title="t", summary="s", format="vertical", duration=10, palette=mg.Palette(),
                         scenes=[mg.ScenePlan(headline="a", idea="x", start=0, end=4), mg.ScenePlan(headline="b", idea="y", start=4, end=10)])
    drafts = [mg.SceneDraft(html="<p>a</p>", css="", build_js='tl.to("#s1 p", {y: 0}, T + .5);'), mg.SceneDraft(html="<p>b</p>", css="", build_js='tl.to("#s2 p", {y: 0}, T + D - .3);')]
    page = mg.assemble_scenes(plan, drafts)
    assert "(function (T, D) {\ntl.to(\"#s1 p\", {y: 0}, T + .5);\n})(0, 4);" in page.build_js
    assert "(function (T, D) {\ntl.to(\"#s2 p\", {y: 0}, T + D - .3);\n})(4, 6);" in page.build_js


def test_js_syntax_error_reports_broken_scene_code():
    from creative.motion_graphic import js_syntax_error
    assert js_syntax_error('tl.to(".a", {x: 1}, 0);') == ""
    assert "missing" in js_syntax_error('tl.to(".a", {x: 1}, 0')


def test_hand_written_stroke_styles_are_rejected():
    import re
    from creative.motion_graphic import _FORBIDDEN_JS
    bad = ['p.style.strokeDasharray = "5"', 'document.querySelectorAll(".a").style.opacity = 0']
    assert all(any(re.search(pattern, code) for pattern, _ in _FORBIDDEN_JS) for code in bad)
    assert not any(re.search(pattern, 'tl.to(".a", {strokeDashoffset: 0}, 0)') for pattern, _ in _FORBIDDEN_JS)


def test_kit_draw_accepts_lists_of_selectors():
    import shutil, subprocess
    from pathlib import Path
    import pytest
    if not shutil.which("node"):
        pytest.skip("node is not installed")
    kit = Path(__file__).resolve().parent.parent / "creative" / "motion_kit" / "kit.js"
    script = (
        'const mk=id=>({nodeType:1,id,style:{},getTotalLength:()=>50});const els={"#a":[mk("a")],"#b":[mk("b")]};'
        'global.document={querySelectorAll:s=>els[s]||[]};global.window=global;eval(require("fs").readFileSync(process.argv[1],"utf8"));'
        'const calls=[];const tl={fromTo(p){calls.push(p.id);return tl}};HM._bind(tl,{duration:5,width:1080,height:1920});'
        'HM.draw(["#a","#b"],0,{});HM.draw([1,null],1);console.log(calls.join(","));'
    )
    done = subprocess.run(["node", "-e", script, str(kit)], capture_output=True, text=True, timeout=20)
    assert done.stdout.strip() == "a,b", done.stderr


def test_unknown_kit_helpers_are_reported():
    from creative.motion_graphic import unknown_helpers
    assert unknown_helpers('HM.set(".a", {opacity: 0}, 0); HM.rise(".b", 1);') == []
    assert unknown_helpers('HM.explode(".a"); HM.rise(".b", 1); const s = "HM.nope";') == ["explode"]


def test_isolate_replaces_only_the_scene_that_breaks_the_page(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from app import motion_graphic as app_mg
    from creative import motion_graphic as mg
    from engine.hyperframes import standalone
    plain = SimpleNamespace(tag="plain")
    plan = SimpleNamespace(scenes=[SimpleNamespace(headline=f"h{i}") for i in range(3)])
    build = SimpleNamespace(plan=plan, drafts={1: "a", 2: "BAD", 3: "c"}, audio=[])
    monkeypatch.setattr(mg, "fallback_scene", lambda p, n: "plain")
    monkeypatch.setattr(mg, "assemble_scenes", lambda p, drafts, audio=None: list(drafts))
    monkeypatch.setattr(mg, "write_project", lambda work, page: setattr(build, "written", page))
    monkeypatch.setattr(standalone, "check", lambda work, should_cancel=None: SimpleNamespace(blocking=["x"] if "BAD" in build.written else []))
    monkeypatch.setattr(app_mg, "_note", lambda *a, **k: None)
    monkeypatch.setattr(app_mg, "_cancelled", lambda key: False)
    notes: list[str] = []
    page = app_mg._isolate(tmp_path, tmp_path, build, None, ["page_error: boom"], notes)
    assert page == ["a", "plain", "c"] and len(notes) == 1


def test_narration_retimes_scenes_to_the_voice(monkeypatch, tmp_path):
    from app import motion_graphic as app_mg
    from brain import localize
    from creative import motion_graphic as mg
    plan = mg.MotionPlan(title="t", duration=9, scenes=[mg.ScenePlan(headline=f"h{i}", idea="i", start=3 * i, end=3 * i + 3, narration="x") for i in range(3)])
    monkeypatch.setattr(localize, "synthesize_narration", lambda texts, out, voice="", style="": [(tmp_path / f"c{i}.wav", s) for i, s in enumerate((4.0, 1.0, 2.0))])
    monkeypatch.setattr(app_mg, "_note", lambda *a, **k: None)
    retimed, audio, notes = app_mg._narrate(tmp_path, {"voice_id": "", "voice_style": ""}, plan, "fp")
    assert [round(s.end - s.start, 2) for s in retimed.scenes] == [4.7, 3.0, 3.7]      # long voice stretches its scene; short ones keep the plan; the last holds 1 s
    assert retimed.duration == 11.4 and audio[0]["start"] == 0.25 and audio[1]["start"] == 4.95 and notes == []


def test_narration_failure_keeps_the_clip_silent_but_alive(monkeypatch, tmp_path):
    from app import motion_graphic as app_mg
    from brain import localize
    from creative import motion_graphic as mg
    plan = mg.MotionPlan(title="t", duration=6, scenes=[mg.ScenePlan(headline="a", idea="i", start=0, end=3, narration="x"), mg.ScenePlan(headline="b", idea="i", start=3, end=6, narration="y")])
    monkeypatch.setattr(localize, "synthesize_narration", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("quota")))
    monkeypatch.setattr(app_mg, "_note", lambda *a, **k: None)
    same, audio, notes = app_mg._narrate(tmp_path, {}, plan, "fp")
    assert same is plan and audio == [] and "بی‌صدا" in notes[0]


def test_approved_script_fixes_the_scenes_of_the_plan():
    from creative import motion_graphic as mg
    brief = "\n".join(["ایده: سه اشتباه", "1. (3s) تصویر: نقشه | متن روی صفحه: اشتباه اول | روایت: اولین اشتباه نداشتن برنامه است.",
                       "2. (3s) تصویر: خرج | متن روی صفحه: اشتباه دوم | روایت: دومی خرج بی‌هدف است.", "3. (3s) تصویر: مسیر | متن روی صفحه: شروع کن | روایت: همین امروز شروع کن."])
    plan = mg.MotionPlan(title="t", duration=15, summary="s", scenes=[mg.ScenePlan(headline="z", idea="i", start=0, end=15, narration="q")])
    out = mg.apply_handoff(plan, brief)
    assert [s.headline for s in out.scenes] == ["اشتباه اول", "اشتباه دوم", "شروع کن"] and out.scenes[0].narration.startswith("اولین")
    assert out.scenes[1].start == out.scenes[0].end
    assert mg.apply_handoff(plan, "یک درخواست ساده") is plan


def test_page_with_narration_has_audio_tracks(tmp_path):
    from creative import motion_graphic as mg
    clip = tmp_path / "c.wav"
    clip.write_bytes(b"RIFF")
    page = mg.MotionPage(title="t", duration=5, scenes_html='<section class="hm-scene" id="s1"><p id="s1-a">سلام</p></section>', build_js="tl.to('#s1-a',{opacity:1},0)",
                         audio=[{"path": str(clip), "start": 0.25, "duration": 3.5}])
    html = mg.assemble(page)
    assert '<audio id="vo1" src="assets/vo1.wav" data-start="0.25" data-duration="3.5" data-track-index="1">' in html
