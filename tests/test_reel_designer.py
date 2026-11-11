import json
import subprocess
from pathlib import Path

from creative import motion as motion_designer
from creative import motion_graphic as mg
from creative import reel_designer


def _job(tmp_path):
    job = tmp_path / "job"
    (job / "generated" / "source_assets").mkdir(parents=True)
    pics = []
    for n in range(2):
        pic = job / "generated" / "source_assets" / f"asset_0{n + 1}.jpg"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=s=320x320:r=1", "-frames:v", "1", str(pic)], check=True)
        pics.append(pic)
    (job / "generated" / "asset_catalog.json").write_text(json.dumps([{"index": 0, "subject": "headset"}, {"index": 1, "subject": "microphone diagram"}]))
    (job / "generated" / "asset_map.json").write_text(json.dumps({"0": "generated/source_assets/asset_01.jpg", "1": "generated/source_assets/asset_02.jpg"}))
    (job / "storyboard.json").write_text(json.dumps({"prompt": "reel", "scenes": [
        {"description": "hook: push in", "motion_style": "push", "why_visual": "product"}, {"description": "spec", "motion_style": "pan", "why_visual": "mic"}]}))
    voice = job / "generated" / "v.mp3"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "2", str(voice)], check=True)
    config = {"scenes": [
        {"asset": str(pics[0]), "title": "نوبت صدای تو", "narration_text": "سلام", "frames": 90, "narration": str(voice), "items": []},
        {"asset": str(pics[1]), "title": "میکروفون", "narration_text": "میکروفون", "frames": 90, "narration": str(voice), "items": ["میکروفون"]}], "music": None}
    return job, config


class Job:
    def __init__(self, dir):
        self.dir = dir


def fake_voice(monkeypatch, tmp_path):
    """The one continuous take of the whole script (the provider is not called in tests)."""
    from creative import narration_take
    audio = tmp_path / "take.mp3"
    audio.write_bytes(b"x")
    lines = [{"start": 0.2, "end": 1.0, "words": [{"word": "سلام", "start": 0.2, "end": 1.0}]}, {"start": 2.4, "end": 3.2, "words": [{"word": "میکروفون", "start": 2.4, "end": 3.2}]}]
    monkeypatch.setattr(narration_take, "voice", lambda storyboard, texts, folder, user=None: {"audio": audio, "total": 4.0, "lines": lines})
    from creative import visual_gate
    monkeypatch.setattr(visual_gate, "blank_scenes", lambda project, plan, work: [])        # the stills have their own test


def test_plan_is_made_from_the_approved_storyboard_with_the_pictures_the_designer_may_use(tmp_path):
    job, config = _job(tmp_path)
    design = motion_designer.DesignSystem(bg="#abc", accent="#ff8800")
    plan, pictures, subjects = reel_designer.build_plan(config, json.loads((job / "storyboard.json").read_text()), {"chosen": {"name": "ایده", "visual_language": "bold"}}, design, tmp_path / "p", job)
    assert [s.headline for s in plan.scenes] == ["نوبت صدای تو", "میکروفون"]
    assert plan.duration == 6.0 and plan.palette.bg == "#aabbcc"
    assert all(mg._PICTURE.search(s.idea) for s in plan.scenes)                 # the picture rules of the designer apply to every scene
    assert "microphone diagram" in plan.scenes[1].idea


def test_designed_scenes_are_assembled_checked_and_rendered(tmp_path, monkeypatch):
    job, config = _job(tmp_path)
    fake_voice(monkeypatch, tmp_path)
    monkeypatch.setenv("CREATIVE_DIRECTOR", "1")
    monkeypatch.setattr(reel_designer, "enabled", lambda: True)
    monkeypatch.setenv("TSCAPS_OVERLAY", "0")
    monkeypatch.setattr(motion_designer, "design_system", lambda *a, **k: motion_designer.DesignSystem())
    def author(plan, n, brief, **kw):
        return mg.SceneDraft(html=f'<p class="s{n}-t">{plan.scenes[n-1].headline}</p>', css=f"#s{n} .s{n}-t{{position:absolute;top:700px;right:80px;font:900 120px/1.4 Ray}}",
                             build_js=f'HM.rise("#s{n} .s{n}-t", 0.2);')
    monkeypatch.setattr(mg, "author_scene", author)
    monkeypatch.setattr(mg, "write_project", lambda directory, page, **k: (directory / "index.html").write_text(page.scenes_html))
    from engine.hyperframes import product_reel, standalone
    monkeypatch.setattr(standalone, "check", lambda *a, **k: standalone.CheckResult(ran=True))
    out = tmp_path / "out.mp4"
    monkeypatch.setattr(product_reel, "_run_cli", lambda project, output, **k: output.write_bytes(b"x"))
    data = {"generation_meta": {"creative_plan": {"chosen": {"name": "ایده"}, "brief": {"topic": "t"}}}, "music": None}
    assert reel_designer.render(Job(job), data, config, out) is True
    assert out.is_file() and (job / "reel_design" / "scenes" / "s1.json").is_file()      # designed scenes are kept: a retry does not pay for them again


def test_a_reel_without_a_creative_plan_is_left_to_the_builtin_page(tmp_path, monkeypatch):
    job, config = _job(tmp_path)
    monkeypatch.setattr(reel_designer, "enabled", lambda: True)
    monkeypatch.setenv("TSCAPS_OVERLAY", "0")
    assert reel_designer.render(Job(job), {"generation_meta": {}}, config, tmp_path / "o.mp4") is False


def test_svg_paths_that_would_stop_the_page_are_caught_before_rendering():
    assert reel_designer.path_problem("M10 10 L20 20 C80 146 64 122 5 5 Z") is None
    assert reel_designer.path_problem("M10 10 C80 146 64 122Z") is not None            # a curve needs six numbers
    assert reel_designer.path_problem("L10 10") is not None
    assert reel_designer.svg_problems('<svg><path d="M0 0 C1 2 3"/></svg>')


def test_a_scene_that_breaks_the_browser_check_is_repaired_then_replaced_and_the_rest_keeps_its_design(tmp_path, monkeypatch):
    job, config = _job(tmp_path)
    fake_voice(monkeypatch, tmp_path)
    monkeypatch.setattr(reel_designer, "enabled", lambda: True)
    monkeypatch.setenv("TSCAPS_OVERLAY", "0")
    monkeypatch.setattr(motion_designer, "design_system", lambda *a, **k: motion_designer.DesignSystem())
    calls = []
    def author(plan, n, brief, **kw):
        calls.append((n, bool(kw.get("feedback"))))
        return mg.SceneDraft(html=f'<p class="s{n}-t">{plan.scenes[n-1].headline}</p>', css=f"#s{n} .s{n}-t{{position:absolute;top:700px;font:900 120px/1.4 Ray}}", build_js=f'HM.rise("#s{n} .s{n}-t", 0.2);')
    monkeypatch.setattr(mg, "author_scene", author)
    monkeypatch.setattr(mg, "write_project", lambda directory, page, **k: (directory / "index.html").write_text(page.scenes_html))
    from engine.hyperframes import product_reel, standalone
    state = {"n": 0}
    def check(*a, **k):
        state["n"] += 1
        return standalone.CheckResult(ran=True, blocking=["runtime: console_error: <path> attribute d @#s2-t"] if state["n"] <= 2 else [])
    monkeypatch.setattr(standalone, "check", check)
    monkeypatch.setattr(product_reel, "_run_cli", lambda project, output, **k: output.write_bytes(b"x"))
    out = tmp_path / "out.mp4"
    j = Job(job)
    data = {"generation_meta": {"creative_plan": {"chosen": {"name": "ایده"}, "brief": {"topic": "t"}}}, "music": None}
    assert reel_designer.render(j, data, config, out) is True and out.is_file()
    assert (2, True) in calls                                         # scene 2 was redesigned once with the browser's message
    assert "جایگزین" in getattr(j, "designer_note", "")              # then replaced by a plain scene, and the person is told


def test_the_approved_storyboard_is_handed_to_the_planner_in_the_studio_hand_over_format(tmp_path):
    from creative import handoff
    job, config = _job(tmp_path)
    config["scenes"].append({**config["scenes"][0], "title": "سه"})
    storyboard = json.loads((job / "storyboard.json").read_text())
    storyboard["scenes"].append({"description": "cta"})
    pictures = {Path(r["asset"]).name: ("./assets/ui-0123456789abcdef.png", 320, 320) for r in config["scenes"]}
    text = reel_designer.handoff_brief(config, storyboard, {"chosen": {"name": "ایده", "angle": "زاویه", "hook": "هوک", "visual_language": "bold"}}, pictures, {}, [3.0, 3.0, 3.0])
    parsed = handoff.parse(text)
    assert parsed and len(parsed["lines"]) == 3 and parsed["lines"][0]["title"] == "نوبت صدای تو"
    assert "ui-0123456789abcdef.png" in parsed["lines"][0]["see"]


def test_scenes_last_as_long_as_their_narration_plus_a_breath(tmp_path):
    job, config = _job(tmp_path)                                       # each narration is 2 s
    lengths = reel_designer.scene_lengths(config, 0)
    assert all(2.4 <= length <= 2.7 for length in lengths)
    assert all(length > 3 for length in reel_designer.scene_lengths(config, 12))           # a film far shorter than planned gets longer breaths


def test_a_plain_scene_is_sent_back_and_a_rich_one_passes():
    plain = mg.SceneDraft(html='<p class="s1-t">x</p>', css="#s1 .s1-t{position:absolute}", build_js='HM.rise("#s1 .s1-t", 0.2);')
    assert len(reel_designer.richness_problems(plain)) >= 3                     # few moves, few layers, no product picture
    rich = mg.SceneDraft(html='<div class="s1-bg"></div><div class="s1-card"><img class="s1-pic" src="./assets/ui-0123456789abcdef.png"></div>' + "".join(f'<span class="s1-m{i}">m</span>' for i in range(6)),
                         css="#s1 .s1-bg{position:absolute}", build_js="\n".join(f'tl.fromTo("#s1 .s1-m{i}", {{opacity:0, y:20}}, {{opacity:1, y:0, duration:.4}}, T + {i * .2});' for i in range(10)))
    assert reel_designer.richness_problems(rich) == []


def test_every_scene_after_the_first_gets_a_whoosh_and_the_last_a_hit(tmp_path):
    plan = mg.MotionPlan(duration=9, scenes=[mg.ScenePlan(headline="a", idea="i", start=0, end=3), mg.ScenePlan(headline="b", idea="i", start=3, end=6), mg.ScenePlan(headline="c", idea="i", start=6, end=9)])
    clips = reel_designer.sound_effects(tmp_path, plan)
    assert [round(c["start"], 2) for c in clips] == [2.65, 5.65, 6.05] and all(Path(c["path"]).is_file() for c in clips)


def test_a_narration_failure_stops_the_reel_instead_of_using_another_way_of_voicing(tmp_path, monkeypatch):
    import pytest
    from creative import narration_take
    job, config = _job(tmp_path)
    monkeypatch.setenv("CREATIVE_DIRECTOR", "1")
    monkeypatch.setattr(reel_designer, "enabled", lambda: True)
    def broken(storyboard, texts, folder, user=None):
        raise narration_take.NarrationFailed("ساخت نریشن انجام نشد: اعتبار ElevenLabs کافی نیست")
    monkeypatch.setattr(narration_take, "voice", broken)
    data = {"generation_meta": {"creative_plan": {"chosen": {"name": "ایده"}, "brief": {"topic": "t"}}}, "music": None}
    with pytest.raises(narration_take.NarrationFailed):
        reel_designer.render(Job(job), data, config, tmp_path / "out.mp4")


def test_scenes_follow_the_take_and_carry_word_cues():
    from creative import narration_take
    take = {"audio": "/x.mp3", "total": 5.0, "lines": [{"start": 0.2, "end": 1.0, "words": [{"word": "a", "start": 0.2, "end": 0.6}, {"word": "b", "start": 0.6, "end": 1.0}]},
                                                   {"start": 2.4, "end": 3.2, "words": [{"word": "c", "start": 2.4, "end": 3.2}]}]}
    fitted = narration_take.fit(take)
    plan = mg.MotionPlan(title="t", duration=8, scenes=[mg.ScenePlan(headline="h1", idea="i", start=0, end=4), mg.ScenePlan(headline="h2", idea="i", start=4, end=8)])
    out = narration_take.apply(plan, fitted)
    assert out.scenes[0].end == out.scenes[1].start and out.scenes[1].cues[0]["word"] == "c" and out.duration == fitted["duration"]
    assert fitted["audio"][0]["duration"] == 5.0


def test_the_visual_gate_sends_blank_and_overlapping_scenes_back(tmp_path, monkeypatch):
    from creative import visual_gate
    plan = mg.MotionPlan(title="t", duration=8, scenes=[mg.ScenePlan(headline="a", idea="i", start=0, end=4), mg.ScenePlan(headline="b", idea="i", start=4, end=8)])
    monkeypatch.setattr(visual_gate, "blank_scenes", lambda project, plan, work: [2])
    quality = ["layout: content_overlap: Two text blocks overlap and may render unreadable. [#s1-headline] Fix: x", "layout: contrast: low [#s2-t]"]
    first = visual_gate.problems(tmp_path, plan, tmp_path, quality, True)
    assert first and first[0].startswith("s1-overlap")                      # an overlap is sent back first
    again = visual_gate.problems(tmp_path, plan, tmp_path, quality, False)
    assert again and again[0].startswith("s2-visual")                        # then the blank scene


def _render_with_music(tmp_path, monkeypatch, attached=None):
    """A product reel through the whole designer with the music director's choice faked; returns (what the director was asked, the audio the page was assembled with)."""
    from creative.audio import film_music, music_director as md
    job, config = _job(tmp_path)
    fake_voice(monkeypatch, tmp_path)
    monkeypatch.setattr(reel_designer, "enabled", lambda: True)
    monkeypatch.setenv("TSCAPS_OVERLAY", "0")
    monkeypatch.setattr(motion_designer, "design_system", lambda *a, **k: motion_designer.DesignSystem())
    monkeypatch.setattr(mg, "author_scene", lambda plan, n, brief, **kw: mg.SceneDraft(
        html=f'<p class="s{n}-t">{plan.scenes[n-1].headline}</p>', css=f"#s{n} .s{n}-t{{position:absolute;top:700px;right:80px;font:900 120px/1.4 Ray}}", build_js=f'HM.rise("#s{n} .s{n}-t", 0.2);'))
    monkeypatch.setattr(mg, "write_project", lambda directory, page, **k: (directory / "index.html").write_text(page.scenes_html))
    from engine.hyperframes import product_reel, standalone
    monkeypatch.setattr(standalone, "check", lambda *a, **k: standalone.CheckResult(ran=True))
    monkeypatch.setattr(product_reel, "_run_cli", lambda project, output, **k: output.write_bytes(b"x"))
    track = tmp_path / "track.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=220:d=12", str(track)], check=True)
    asked, seen = {}, {}
    from creative import music_bed
    monkeypatch.setattr(music_bed, "make_bed", lambda source, output, duration, voice, **k: (output.write_bytes(b"bed") or output))      # the voice is a stub file here
    monkeypatch.setattr(film_music, "choose", lambda directory, request, progress=None: (asked.update(req=request) or md.Result(path=track, label="test track", source="library")))
    monkeypatch.setattr(film_music, "master", lambda directory, voice, music, total, preset="social_video": (None, []))
    real = mg.assemble_scenes
    monkeypatch.setattr(mg, "assemble_scenes", lambda plan, drafts, audio, *a, **k: (seen.update(audio=list(audio)) or real(plan, drafts, audio, *a, **k)))
    data = {"generation_meta": {"creative_plan": {"chosen": {"name": "ایده", "pacing": "fast"}, "brief": {"topic": "t"}}}, "music": {"file": str(attached)} if attached else None}
    assert reel_designer.render(Job(job), data, config, tmp_path / "out.mp4") is True
    return asked["req"], seen["audio"], job


def test_a_product_reel_without_attached_music_gets_the_directors_track_with_the_drop_on_its_last_scene(tmp_path, monkeypatch):
    request, audio, job = _render_with_music(tmp_path, monkeypatch)
    timeline = json.loads((job / "reel_design" / "timeline.json").read_text())
    assert request.mode == "auto" and request.cost == "free" and request.accent_s == timeline["scenes"][-1]["start"] and "fast" in request.words
    assert any(clip.get("role") == "music" for clip in audio)          # the bed was made from the director's track and ducked under the voice
    assert (job / "reel_design" / "music_timing.json").is_file()


def test_attached_music_stays_the_persons_choice_and_goes_through_the_same_fit(tmp_path, monkeypatch):
    mine = tmp_path / "mine.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=330:d=12", str(mine)], check=True)
    request, audio, _ = _render_with_music(tmp_path, monkeypatch, attached=mine)
    assert request.mode == "attached" and request.path == str(mine)
