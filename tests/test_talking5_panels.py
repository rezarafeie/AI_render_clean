"""Talking 5 panels come from the curated panel library first; the Motion Designer only fills what nothing in it fits."""
from types import SimpleNamespace

import pytest

from creative import motion as creative_motion
from creative import panel_library
from creative.style_packs import REFERENCE_AI_NEWS
from engine.hyperframes import overlay_reel
from engine.talking_styles import talking_5 as t5


def _plan(beats):
    segments = [{"start": i * 6.0, "end": i * 6.0 + 5.0, "layout": "split", "beat": dict(b)} for i, b in enumerate(beats)]
    shots = [SimpleNamespace(out_start=s["start"], split=True) for s in segments]
    return SimpleNamespace(script={"segments": segments, "duration": 6.0 * len(beats), "words": [], "moments": []}, shots=shots,
                           sentences=[{"text": f"جملهٔ {i}"} for i in range(len(beats))], creative_plan={"chosen": {}, "brief": {}})


BEATS = [
    {"title": "پنج منبع", "items": ["مدرسه", "دانشگاه", "رسانه", "خانواده"], "visual_type": "steps"},
    {"title": "۷۲٪ رشد", "items": [], "visual_type": "stat"},
    {"title": "قدیمی در برابر جدید", "items": ["قدیمی", "جدید"], "visual_type": "comparison"},
    {"title": "یک جملهٔ کوتاه", "items": [], "visual_type": "kinetic_type"},
]


@pytest.fixture
def offline(monkeypatch):
    """The designer is faked: it fills every beat it is given and remembers which ones those were."""
    asked = []

    def compose(beats, plan, sentences, **kw):
        for b in beats:
            asked.append(b.id)
            b.custom = {"html": "<p>x</p>", "css": "", "js": "", "bg": "#101010"}
    monkeypatch.setattr(creative_motion, "compose", compose)
    monkeypatch.setattr(creative_motion, "enabled", lambda: True)
    return asked


def test_the_library_fills_the_panels_it_fits_and_the_designer_is_not_asked_for_them(offline, monkeypatch):
    monkeypatch.setenv("TALKING5_PANELS", "library")
    plan = _plan(BEATS)
    assert t5.author_panels(plan, __import__("pathlib").Path("/tmp")) == 4
    info = plan.script["panels_info"]
    assert [r["source"] for r in info].count("library") >= 3 and all(r.get("component") in panel_library.LIBRARY for r in info if r["source"] == "library")
    names = [r["component"] for r in info if r["source"] == "library"]
    assert len(names) == len(set(names))                                    # never the same component twice in one reel
    assert len(offline) == sum(1 for r in info if r["source"] == "authored")        # the designer only got what the library could not fill


def test_the_page_builds_exactly_the_components_chosen_here(offline, tmp_path, monkeypatch):
    monkeypatch.setenv("TALKING5_PANELS", "library")
    plan = _plan(BEATS)
    t5.author_panels(plan, tmp_path)
    expected = [r["component"] for r in plan.script["panels_info"] if r["source"] == "library"]
    overlay_reel.build_project(tmp_path / "page", REFERENCE_AI_NEWS, plan.script, part="panel")
    html = (tmp_path / "page" / "index.html").read_text()
    assert all(f'data-composition-id="{name}"' in html for name in expected)


def test_authored_mode_keeps_the_old_behaviour_and_mixed_leaves_headlines_to_the_designer(offline, monkeypatch, tmp_path):
    monkeypatch.setenv("TALKING5_PANELS", "authored")
    plan = _plan(BEATS)
    t5.author_panels(plan, tmp_path)
    assert {r["source"] for r in plan.script["panels_info"]} == {"authored"} and len(offline) == 4
    offline.clear()
    monkeypatch.setenv("TALKING5_PANELS", "mixed")
    plan = _plan(BEATS)
    t5.author_panels(plan, tmp_path)
    by_title = {r["title"]: r["source"] for r in plan.script["panels_info"]}
    assert by_title["یک جملهٔ کوتاه"] == "authored" and by_title["۷۲٪ رشد"] == "library"


def test_a_panel_nobody_can_fill_is_dropped_and_no_designer_means_the_pages_own_template(monkeypatch, tmp_path):
    monkeypatch.setenv("TALKING5_PANELS", "authored")
    monkeypatch.setattr(creative_motion, "enabled", lambda: True)
    monkeypatch.setattr(creative_motion, "compose", lambda *a, **k: None)           # the designer returns nothing
    plan = _plan(BEATS[:1])
    assert t5.author_panels(plan, tmp_path) == 0 and plan.script["segments"][0]["layout"] == "full" and plan.script["panels_info"][0]["source"] == "dropped"
    monkeypatch.setattr(creative_motion, "enabled", lambda: False)
    plan = _plan(BEATS[:1])
    assert t5.author_panels(plan, tmp_path) == 1 and plan.script["segments"][0]["layout"] == "split" and plan.script["panels_info"][0]["source"] == "template"


def test_a_component_is_fitted_to_the_panels_length_so_it_does_not_leave_the_panel_empty(tmp_path):
    html = panel_library.fitted_html("headline-slam", 6.25)
    assert html.count('data-duration="6.25"') >= 2 and 'data-composition-duration="6.25"' in html and 'data-duration="3.5"' not in html
    assert "cdn.jsdelivr.net" not in html                                      # the page's own GSAP is used: a render worker has no network
    plan = _plan(BEATS[3:])
    plan.script["segments"][0]["end"] = 6.25
    plan.script["segments"][0]["beat"]["force_component"] = "headline-slam"
    overlay_reel.build_project(tmp_path / "page", REFERENCE_AI_NEWS, plan.script, part="panel")
    assert 'data-duration="6.25"' in (tmp_path / "page" / "compositions" / "components" / "headline-slam.html").read_text()


def test_a_weak_library_panel_is_swapped_for_another_component_and_kept_only_if_it_scores_higher(offline, monkeypatch, tmp_path):
    from PIL import Image
    from creative import design_critic
    monkeypatch.setenv("TALKING5_PANELS", "library")
    plan = _plan(BEATS[:2])
    t5.author_panels(plan, tmp_path)
    segs = [s for s in plan.script["segments"] if s["layout"] == "split" and s.get("beat")]
    first = {i: s["beat"]["force_component"] for i, s in enumerate(segs, 1) if s["beat"].get("force_component")}
    shots = tmp_path / "shots"
    shots.mkdir()

    def snap(plan_, pack_, work_, out_):
        items = []
        for i, seg in enumerate(segs, 1):
            f = shots / f"{i}-{seg['beat'].get('force_component')}.jpg"
            Image.new("RGB", (270, 400), (30 * i, 90, 120)).save(f)
            items.append({"n": i, "t": 1.0, "title": "", "file": f, "seg": i})
        return items
    monkeypatch.setattr(t5, "snapshot_panels", snap)
    seen = {"calls": 0}

    def fake_ask(rubric, context, sheet):
        seen["calls"] += 1
        weak = seen["calls"] == 1                                   # first look: panel 1 is weak; second look: its replacement is better
        return {"scenes": [{"scene": 1, "score": 3 if weak else 8, "problems": ["too plain"], "fix": "bigger type"}, {"scene": 2, "score": 8}][:2 if weak else 1]}
    real = design_critic.critique
    monkeypatch.setattr(design_critic, "critique", lambda *a, **k: real(*a, **{**k, "ask": fake_ask}))
    notes = []
    frames = t5.refine_panels(plan, REFERENCE_AI_NEWS, tmp_path, snap(None, None, None, None), lambda text, **kw: notes.append(text))
    after = {i: s["beat"]["force_component"] for i, s in enumerate(segs, 1) if s["beat"].get("force_component")}
    assert after[1] != first[1] and after.get(2) == first.get(2) and frames and notes


def test_a_long_panel_is_never_given_a_component_that_animates_out_early(monkeypatch):
    assert not panel_library.lasts("headline-slam", 6.0) and panel_library.lasts("headline-slam", 3.5) and panel_library.lasts("kinetic-type-swap", 6.5)
    assert panel_library.lasts("state-chip-rail", 6.0)                                  # not measurable: not filtered
    beat = {"title": "ایده‌ای که همه‌چیز را عوض کرد", "items": [], "visual_type": "kinetic_type"}
    for seed in range(12):
        pick = panel_library.choose(beat, set(), seed=str(seed), seconds=6.0)
        assert pick is None or panel_library.lasts(pick[0], 6.0)
    short = {panel_library.choose(beat, set(), seed=str(seed), seconds=3.0)[0] for seed in range(12)}
    assert "headline-slam" in short or "push-in" in short or len(short) >= 2          # short panels may use the short components


def test_a_reel_with_library_panels_is_kept_off_the_cloud_until_the_worker_image_has_the_fixed_library():
    from app.render_cloud import hooks
    library = _plan(BEATS[:2])
    for seg in library.script["segments"]:
        seg["beat"]["force_component"] = "beat-timeline"
    assert hooks._library_panels(library)
    authored = _plan(BEATS[:2])
    for seg in authored.script["segments"]:
        seg["beat"]["custom"] = {"html": "<p>x</p>", "css": "", "js": ""}
    assert not hooks._library_panels(authored)
    plain = _plan(BEATS[:1])
    plain.script["segments"][0]["layout"] = "full"
    assert not hooks._library_panels(plain)


def test_best_mode_makes_both_candidates_and_the_art_director_keeps_the_higher_scoring_one(offline, monkeypatch, tmp_path):
    from PIL import Image
    from creative import design_critic
    monkeypatch.delenv("TALKING5_PANELS", raising=False)                       # the default is "best"
    plan = _plan(BEATS[:3])
    t5.author_panels(plan, tmp_path)
    segs = [s for s in plan.script["segments"] if s["layout"] == "split" and s.get("beat")]
    assert all(s["beat"].get("custom") and s["beat"].get("force_component") for s in segs)          # both candidates for every beat
    assert {r["source"] for r in plan.script["panels_info"]} == {"both"}
    shots = tmp_path / "shots"
    shots.mkdir()

    def snap(plan_, pack_, work_, out_):
        items = []
        for i, seg in enumerate(segs, 1):
            f = shots / f"{out_.name}-{i}.jpg"
            Image.new("RGB", (270, 400), (30 * i, 90, 120)).save(f)
            items.append({"n": i, "t": 1.0, "title": "", "file": f, "seg": i})
        return items
    monkeypatch.setattr(t5, "snapshot_panels", snap)
    scores = {"panel_frames_library": {1: 8, 2: 4, 3: 6}, "panel_frames_authored": {1: 5, 2: 7, 3: 6}}          # 1: library wins, 2: designer wins, 3: tie goes to the designer
    real = design_critic.critique
    monkeypatch.setattr(design_critic, "critique", lambda stills, headlines, work, **kw: real(stills, headlines, work, **{**kw, "ask": lambda rubric, ctx, sheet: {"scenes": [
        {"scene": n, "score": sc} for n, sc in scores["panel_frames_library" if "library" in str(work) else "panel_frames_authored"].items()]}}))
    notes = []
    t5.pick_panels(plan, REFERENCE_AI_NEWS, tmp_path, lambda text, **kw: notes.append((text, kw)))
    assert segs[0]["beat"].get("force_component") and not segs[0]["beat"].get("custom")
    assert segs[1]["beat"].get("custom") and not segs[1]["beat"].get("force_component")
    assert segs[2]["beat"].get("custom") and not segs[2]["beat"].get("force_component")
    assert [r["source"] for r in plan.script["panels_info"]] == ["library", "authored", "authored"] and notes
    assert not any(k.startswith("_alt") for s in segs for k in s["beat"])


def test_a_chart_or_a_rating_is_never_offered_without_the_numbers_the_speaker_said():
    beat = {"title": "نگرش‌ها", "items": ["الف", "ب", "ج"], "visual_type": "stat"}
    for seed in range(20):
        pick = panel_library.choose(beat, set(), seed=str(seed), seconds=4.0)
        assert pick is None or pick[0] not in panel_library.FABRICATES | {"chart-story", "count-up", "conic-progress-ring"}
    numeric = {"title": "۷۲٪ رشد", "items": [], "visual_type": "stat"}
    assert "count-up" in panel_library.alternatives(numeric, set(), 4.0) or "conic-progress-ring" in panel_library.alternatives(numeric, set(), 3.0)
    assert not any(n in panel_library.alternatives(numeric, set(), 4.0) for n in panel_library.FABRICATES)
