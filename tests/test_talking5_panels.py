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
    monkeypatch.delenv("TALKING5_PANELS", raising=False)
    plan = _plan(BEATS)
    assert t5.author_panels(plan, __import__("pathlib").Path("/tmp")) == 4
    info = plan.script["panels_info"]
    assert [r["source"] for r in info].count("library") >= 3 and all(r.get("component") in panel_library.LIBRARY for r in info if r["source"] == "library")
    names = [r["component"] for r in info if r["source"] == "library"]
    assert len(names) == len(set(names))                                    # never the same component twice in one reel
    assert len(offline) == sum(1 for r in info if r["source"] == "authored")        # the designer only got what the library could not fill


def test_the_page_builds_exactly_the_components_chosen_here(offline, tmp_path):
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
