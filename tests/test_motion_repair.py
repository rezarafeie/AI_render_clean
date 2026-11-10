import pytest
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
    texts, take = ["x", "x", "x"], None
    audio = tmp_path / "take.mp3"; audio.write_bytes(b"x")
    take = {"audio": audio, "total": 9.0, "lines": [{"start": s, "end": s + 1.5, "words": [{"word": "x", "start": s, "end": s + 1.5}]} for s in (0.2, 3.4, 7.0)]}
    monkeypatch.setattr(localize, "continuous_narration", lambda *a, **k: take)
    monkeypatch.setattr(app_mg, "_note", lambda *a, **k: None)
    retimed, audio_list, notes = app_mg._narrate(tmp_path, {"voice_id": "", "voice_style": ""}, plan, "fp")
    assert len(audio_list) == 1 and audio_list[0]["duration"] == 9.0                                  # one whole reading
    assert retimed.scenes[0].start == 0 and retimed.scenes[1].start == pytest.approx(0.3 + 3.4 - 0.35, abs=0.02)   # a scene starts where its first word is heard (a beat early)
    assert retimed.scenes[0].end == retimed.scenes[1].start and retimed.duration > 9.3


def test_narration_failure_stops_the_build_with_the_reason(monkeypatch, tmp_path):
    from app import motion_graphic as app_mg
    from brain import localize
    from creative import motion_graphic as mg
    plan = mg.MotionPlan(title="t", duration=6, scenes=[mg.ScenePlan(headline="a", idea="i", start=0, end=3, narration="x"), mg.ScenePlan(headline="b", idea="i", start=3, end=6, narration="y")])
    monkeypatch.setattr(localize, "continuous_narration", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("quota")))
    monkeypatch.setattr(app_mg, "_note", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="اعتبار ElevenLabs"):
        app_mg._narrate(tmp_path, {}, plan, "fp")


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


def test_blank_scene_stills_are_found_before_the_render(tmp_path):
    from PIL import Image
    from app import motion_graphic as app_mg
    record = app_mg.create("c1", "u1", "A film.")
    directory = app_mg.folder("u1", "c1", record["id"])
    shots = directory / "snapshots"; shots.mkdir()
    Image.new("RGB", (64, 114), (0, 0, 0)).save(shots / "1.jpg")                  # black: nothing painted
    Image.new("RGB", (64, 114), (240, 230, 200)).save(shots / "2.jpg")             # one flat colour: nothing in it
    busy = Image.new("RGB", (64, 114), (240, 230, 200))
    for x in range(10, 50):
        for y in range(20, 60):
            busy.putpixel((x, y), (20, 20, 20) if (x // 4 + y // 4) % 2 else (230, 60, 50))
    busy.save(shots / "3.jpg")
    saved = app_mg.load(directory); saved["snapshots"] = [{"n": 1, "headline": "a", "t": 1}, {"n": 2, "headline": "b", "t": 2}, {"n": 3, "headline": "c", "t": 3}]; app_mg.save(directory, saved)
    assert app_mg._blank_scenes(directory) == [1, 2]


def test_text_over_text_findings_name_their_scene():
    from app import motion_graphic as app_mg
    line = "layout: content_overlap: Two text blocks overlap and may render unreadable. [#s1-headline] Fix: Give each block its own zone"
    assert app_mg._TEXT_OVERLAP.search(line) and app_mg._scenes_in([line], 8) == [1]


def _fake_take(tmp_path):
    texts = ["سلام دنیا", "این یک آزمایش است"]
    audio = tmp_path / "t.mp3"; audio.write_bytes(b"x")
    def line(words, t0):
        out, t = [], t0
        for w in words:
            out.append({"word": w, "start": t, "end": t + 0.4}); t += 0.5
        return {"start": out[0]["start"], "end": out[-1]["end"], "words": out}
    return texts, {"audio": audio, "total": 6.0, "lines": [line(["سلام", "دنیا"], 0.2), line(["این", "یک", "آزمایش", "است"], 2.5)]}


def test_scenes_are_fitted_to_one_continuous_take(tmp_path, monkeypatch):
    from app import motion_graphic as app_mg
    from creative import motion_graphic as mg
    record = app_mg.create("c1", "u1", "A film.")
    directory = app_mg.folder("u1", "c1", record["id"])
    monkeypatch.setattr(app_mg, "_note", lambda *a, **k: None)
    texts, take = _fake_take(tmp_path)
    plan = mg.MotionPlan(title="t", duration=8, scenes=[mg.ScenePlan(headline="a", idea="i", start=0, end=4, narration=texts[0]), mg.ScenePlan(headline="b", idea="i", start=4, end=8, narration=texts[1])])
    retimed, audio, notes = app_mg._fit_to_take(directory, record, plan, texts, take, "fp", "", "")
    assert len(audio) == 1 and audio[0]["start"] == app_mg._PREROLL and audio[0]["duration"] == 6.0       # one whole reading, never cut
    first, second = retimed.scenes
    assert first.start == 0 and first.end == second.start                                                 # scenes tile with no gap
    assert abs(second.start - (app_mg._PREROLL + 2.5 - app_mg._LEAD)) < 0.02                              # the second scene starts where its first word is heard (a beat early)
    assert retimed.duration >= app_mg._PREROLL + 6.0                                                      # the picture outlasts the voice
    assert [c["word"] for c in second.cues] == ["این", "یک", "آزمایش", "است"] and second.cues[0]["t"] > 0


def test_a_continuous_take_sets_its_tone_once():
    from brain import localize
    full, spans = localize.narration_script(["اول", "دوم"], "calm", tag_once=True)
    full_each, _ = localize.narration_script(["اول", "دوم"], "calm")
    assert full.startswith("[calm]") and full.count("[calm]") == 1
    assert full_each.count("[calm]") == 2


def test_the_narration_becomes_typography_timed_to_its_words():
    from creative import captions
    from creative import motion_graphic as mg
    cues = [{"word": "ثبت", "t": 0.3}, {"word": "شرکت", "t": 0.7}, {"word": "جهانی،", "t": 1.1}, {"word": "بدون", "t": 2.4}, {"word": "مهاجرت", "t": 2.8}]
    scene = mg.ScenePlan(headline="h", idea="i", start=0, end=5, cues=cues)
    palette = mg.Palette(bg="#ffffff", surface="#eef3f5", ink="#142830", accent="#007fa3", accent2="#f04432")
    html, css, js = captions.layer(scene, 1, palette)
    assert len(captions.phrases(cues)) == 2 and "data-layout-allow-overlap" in html            # broken after the comma, and exempt from the overlap check
    assert html.count("cap-w") == 5 and "T + 2.40" in js and "T + 0.30" in js                      # every word lands when it is heard
    assert scene.model_copy(update={"cues": []}) and captions.layer(scene.model_copy(update={"cues": []}), 1, palette) is None
    draft = mg.SceneDraft(html='<h1 id="s1-h">ثبت</h1>', build_js='tl.set("#s1-h", {opacity:1}, T + 0);', timebase="local")
    plan = mg.MotionPlan(title="t", duration=5, scenes=[scene], palette=palette)
    page = mg.assemble_scenes(plan, [draft])
    assert "s1-cp1" in page.scenes_html and "s1-cw1-1" in page.build_js


def test_a_long_brief_may_have_more_than_six_scenes():
    from creative import motion_graphic as mg
    short = "یه ویدیو درباره چای"
    long_brief = " ".join(["کلمه"] * 144)
    assert mg.plan_cap(short) == 6 and mg.plan_cap(long_brief) == 12 and mg.plan_cap("x " * 80) == 10
    assert mg.plan_cap(short, supplied=14) == 14 and mg.MAX_SECONDS == 90.0
