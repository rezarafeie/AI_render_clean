"""Authored motion scenes: validation, the builder contract and the compose fallbacks (model mocked)."""
import json
import re
from pathlib import Path

import pytest

from creative import llm, motion
from engine.hyperframes import VisualBeat, build_project
from engine.hyperframes import scenes

GOOD_HTML = '<div id="beat-1-0-stage" class="stage"><h2 id="beat-1-0-title">خدمات سقف دارد</h2><svg viewBox="0 0 10 10"><path d="M0 0L10 10"/></svg></div>'
GOOD_CSS = "#beat-1-0 .stage{position:absolute;inset:0;font-family:Ray;font-weight:900} #beat-1-0 h2{font-size:150px;letter-spacing:0}"
GOOD_JS = 'tl.fromTo($(".stage"), {opacity:0,y:60}, {opacity:1,y:0,duration:.5,ease:"expo.out"}, T+.15);'


def check(html=GOOD_HTML, css=GOOD_CSS, js=GOOD_JS, speaker="pip", beat="beat-1-0"):
    return scenes.validate_scene(beat, html, css, js, speaker)


def test_a_well_formed_scene_passes():
    assert check() == []


@pytest.mark.parametrize("html", ["<script>alert(1)</script>", '<img id="beat-1-0-a" src="https://x.com/a.png">', "<div id='beat-1-0-a'><br></div>",
                                   '<div id="beat-1-0-a" onclick="x()"></div>', '<a id="beat-1-0-a" href="https://evil.example">x</a>',
                                   '<video id="beat-1-0-v"></video>', '<div id="other-1">x</div>', '<div id="beat-1-0-a" data-start="3">x</div>',
                                   '<div id="beat-1-0-a" style="position:fixed">x</div>'])
def test_unsafe_or_off_contract_html_is_rejected(html):
    assert check(html=html)


@pytest.mark.parametrize("css", ["#beat-1-0 .a{animation: x 1s}", "@keyframes x{from{opacity:0}}", "#beat-1-0 .a{transition: all 1s}", ".global{color:red}",
                                  "#beat-1-0 .a{background:url(https://x.com/a.png)}", "@import url(x)", "body #beat-1-0 .a{color:red}", "#beat-1-0 .a{position:fixed}"])
def test_css_must_be_scoped_and_static(css):
    assert check(css=css)


@pytest.mark.parametrize("js", ['tl.from($(".a"),{opacity:0})', 'gsap.to(".a",{x:1})', 'tl.to($(".a"),{x:Math.random()*9},T)', 'setTimeout(()=>{},9)',
                                 'tl.to($(".a"),{x:1,repeat:-1},T)', 'fetch("/x")', 'window.__timelines.x=1;tl.to($(".a"),{x:1},T)', "const a = 1;"])
def test_js_must_be_seekable_and_self_contained(js):
    assert check(js=js)


def test_negative_letter_spacing_is_rejected_for_persian_joins():
    assert any("letter-spacing" in p for p in check(css=GOOD_CSS + " #beat-1-0 h2{letter-spacing:-0.04em}"))


def test_unknown_speaker_mode_is_rejected():
    assert check(speaker="teleport")


def beat(custom=True, **extra):
    data = {"id": "beat-1-0", "start": 4.0, "end": 6.2, "title": "خدمات سقف دارد", "visual_type": "kinetic_type", "layout": "full_frame"}
    data.update(extra)
    if custom:
        data["custom"] = {"html": GOOD_HTML, "css": GOOD_CSS, "js": GOOD_JS, "speaker": "pip"}
    return VisualBeat(**data)


def test_builder_emits_scoped_scene_speaker_stage_and_local_assets(tmp_path, monkeypatch):
    gsap = tmp_path / "gsap.min.js"
    gsap.write_text("/* GSAP 3.14.2 */" + "x" * 60_000)
    monkeypatch.setattr("engine.hyperframes.assets.ensure_gsap", lambda *a, **k: gsap)
    base = tmp_path / "base.mp4"
    base.write_bytes(b"\x00" * 16)
    project = tmp_path / "p"
    build_project(project, base, [beat()], duration=20, enable_registry=False)
    html = (project / "index.html").read_text()
    assert 'src="./assets/gsap.min.js"' in html and "cdn.jsdelivr" not in html            # no network at render time
    assert '<div id="speaker-stage"' in html and 'id="rough-cut"' in html                  # speaker is wrapped, never animated directly
    assert '<section id="beat-1-0" class="custom-beat clip" data-start="4.000" data-duration="2.200"' in html
    assert 'data-composition-id="beat-1-0-scene"' not in html
    assert "#beat-1-0 .stage{" in html and "@font-face{font-family:Ray;font-weight:900" in html
    assert '"scale": 0.46' in html and 'tl.to("#speaker-stage"' in html                      # pip enter + return
    assert (project / "assets" / "fonts" / "ray-black.ttf").is_file() and (project / "assets" / "gsap.min.js").is_file()
    assert "Math.random" not in html
    assert html.index('id="beat-1-0-backdrop"') < html.index('id="speaker-stage"') < html.index('<section id="beat-1-0"')   # backdrop sits UNDER the speaker


def test_template_beats_are_unchanged_without_custom(tmp_path, monkeypatch):
    gsap = tmp_path / "g.js"
    gsap.write_text("x" * 60_000)
    monkeypatch.setattr("engine.hyperframes.assets.ensure_gsap", lambda *a, **k: gsap)
    base = tmp_path / "b.mp4"
    base.write_bytes(b"\x00")
    build_project(tmp_path / "p", base, [beat(custom=False)], duration=20, enable_registry=False)
    html = (tmp_path / "p" / "index.html").read_text()
    assert "visual-beat" in html and "custom-beat clip" not in html


# ── composing with a mocked model ────────────────────────────────────────────
class FakeModel:
    def __init__(self, bad_for=()):
        self.calls, self.bad_for = [], set(bad_for)

    def __call__(self, system, user, route="editing_agent", max_tokens=16000):
        from brain.llm import LLMUsage
        self.calls.append(route)
        usage = LLMUsage(input_tokens=1, output_tokens=1, model="fake", elapsed_sec=0.0)
        if route == llm.DIRECTOR_ROUTE:
            return {"name": "نام", "bg": "#101010", "surface": "#1a1a1a", "ink": "#ffffff", "accent": "#ff8800", "accent2": "#00ccaa", "muted": "#999999",
                    "mood": "m", "personality": "p", "shape": "s"}, usage
        beat_id = re.search(r"beat-\d+-\d+", user).group(0)
        if beat_id in self.bad_for:
            return {"speaker": "full", "html": "<script>x</script>", "css": "", "js": "tl.from(1)"}, usage
        return {"speaker": "pip", "html": GOOD_HTML.replace("beat-1-0", beat_id), "css": GOOD_CSS.replace("beat-1-0", beat_id), "js": GOOD_JS, "notes": "n"}, usage


@pytest.fixture
def fake(monkeypatch):
    def apply(model):
        monkeypatch.setattr("brain.llm.gateway_json", model)
        monkeypatch.setattr(llm, "configured", lambda: True)
        return model
    return apply


SENTENCES = [{"start": 0, "end": 3, "text": "الف"}, {"start": 3, "end": 6, "text": "ولی خدمات سقف دارد"}]


def test_compose_attaches_valid_scenes_and_keeps_templates_for_failures(fake):
    model = fake(FakeModel(bad_for={"beat-0-1"}))
    beats = [beat(custom=False, id="beat-1-0"), beat(custom=False, id="beat-0-1", start=9.0, end=11.2)]
    motion.compose(beats, motion.plan_from_public(None), SENTENCES)
    assert beats[0].custom and beats[0].custom["speaker"] == "pip" and f'id="beat-1-0-stage"' in beats[0].custom["html"]
    assert beats[1].custom is None                        # failed validation after repairs → template stays
    assert model.calls.count(motion.MOTION_ROUTE) >= 3    # one good call + initial and repairs for the bad one


def test_compose_survives_a_dead_gateway(monkeypatch):
    monkeypatch.setattr(llm, "configured", lambda: False)
    beats = [beat(custom=False)]
    motion.compose(beats, motion.plan_from_public(None), SENTENCES)
    assert beats[0].custom is None


def test_design_system_falls_back_to_a_preset_when_unavailable(monkeypatch):
    monkeypatch.setattr(llm, "configured", lambda: False)
    design = motion.design_system("brief", "concept")
    assert design.name == "shadow-cut" and design.accent.startswith("#")


def test_prompt_carries_contract_speaker_geometry_and_the_real_words():
    spec = motion.SceneSpec(id="beat-1-0", start=4, end=6.2, spoken="ولی خدمات سقف دارد", title="خدمات سقف دارد", role="claim")
    prompt = motion.build_prompt(spec, motion.DesignSystem())
    for needle in ("beat-1-0", "ولی خدمات سقف دارد", "#beat-1-0", "pip:", "top 960px", "letter-spacing must be 0", "tl.fromTo"):
        assert needle in prompt


# ── scene cache and sound design ─────────────────────────────────────────────
def test_compose_reuses_cached_scenes_without_calling_the_model(fake, tmp_path):
    model = fake(FakeModel())
    cache = tmp_path / "authored_scenes.json"
    first = [beat(custom=False, id="beat-1-0")]
    motion.compose(first, motion.plan_from_public(None), SENTENCES, cache=cache)
    assert first[0].custom and cache.is_file()
    calls = len(model.calls)
    again = [beat(custom=False, id="beat-1-0")]
    motion.compose(again, motion.plan_from_public(None), SENTENCES, cache=cache)
    assert again[0].custom == first[0].custom and len(model.calls) == calls      # no new model calls, same scene
    moved = [beat(custom=False, id="beat-1-0", start=20.0, end=22.2)]
    motion.compose(moved, motion.plan_from_public(None), SENTENCES, cache=cache)
    assert len(model.calls) > calls                                              # different timing → authored again


def test_sound_cues_cover_authored_beats_only_and_stay_inside_the_video():
    from engine import sfx
    cues = sfx.cues_for([beat(), beat(custom=False, id="beat-2-0", start=10.0, end=12.2)])
    assert [name for _, name in cues] == ["whoosh", "hit", "whoosh"] and cues == sorted(cues)
    files = {"whoosh": Path("w.wav"), "hit": Path("h.wav")}
    html = sfx.markup(cues, duration=5.0, files=files)
    assert html.count("<audio") == 2 and "data-volume" in html                  # the return whoosh at 5.7s is past the end


def test_sound_effects_are_synthesised_not_shipped(tmp_path):
    from engine import sfx
    made = sfx.ensure(tmp_path, {"tick", "pop"})
    assert set(made) == {"tick", "pop"} and all(path.stat().st_size > 500 for path in made.values())


def test_builder_reuses_a_supplied_gsap_without_touching_the_network(tmp_path, monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("must not download when a verified copy is supplied")
    monkeypatch.setattr("engine.hyperframes.assets.ensure_gsap", forbidden)
    shipped = tmp_path / "shipped.js"
    shipped.write_text("/* GSAP 3.14.2 */" + "x" * 60_000)
    base = tmp_path / "base.mp4"
    base.write_bytes(b"\x00" * 16)
    project = tmp_path / "p"
    build_project(project, base, [beat()], duration=20, enable_registry=False, gsap_source=shipped)
    assert (project / "assets" / "gsap.min.js").read_text() == shipped.read_text()
