"""Craft skills (vendor/motion-skills) and Motion Kit: discoverable, lazily loaded, bounded, attributed, inert, and compatible with the motion engine."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from creative import motion_graphic as mg
from creative import skills_library as sl
from creative.resources.registry import get_resource, search_resources

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "motion-skills"


def test_every_skill_is_one_registry_entry_and_ids_are_unique():
    rows = sl.index()
    found = search_resources("", engine="skill", limit=100)
    assert found["total"] == len(rows) >= 50
    ids = [i["id"] for i in found["items"]]
    assert len(ids) == len(set(ids))
    for item in found["items"]:
        assert item["type"] == "skill" and item["integration_status"] == "skill-only" and item["license"]["type"] == ("AGPL-3.0" if item["id"].startswith("openmontage:") else "MIT") and item["license"]["attribution_required"] and not item["license"]["commercial_use_approved"]
        assert item["source_url"].startswith("https://github.com/") and item["source_version"]


def test_one_skill_name_is_kept_once_and_the_best_resource_wins():
    assert sum(1 for r in sl.index().values() if r["name"] == "lower-thirds") == 1
    assert sl.get("iart:lower-thirds")["also_in"] == "lower-thirds-skills" or sl.get("iart:lower-thirds")["pack"] == "lower-thirds-skills"


def test_each_source_keeps_its_licence_and_revision():
    sources = sl.notices()
    assert {s["namespace"] for s in sources} == {"iart", "charlie", "barty", "bang", "motionkit", "motionclone", "openmontage"}
    for source in sources:
        licence = (VENDOR / source["license_file"]).read_text()
        if source["namespace"] == "openmontage":      # the owner accepted AGPL-3.0 for these files; they stay isolated and removable
            assert source["license"] == "AGPL-3.0" and "GNU AFFERO GENERAL PUBLIC LICENSE" in licence.upper()
        else:
            assert licence.startswith("MIT License") and "Permission is hereby granted" in licence and source["copyright"] in licence
        assert len(source["revision"]) == 12
    assert (ROOT / "creative" / "motion_kit" / "MOTION-KIT-LICENSE").read_text().startswith("MIT License")


def test_vendored_content_is_text_only_and_matches_its_hashes():
    assert {p.suffix for p in VENDOR.rglob("*") if p.is_file()} <= {".md", ".txt", ".json", ".LICENSE"}   # nothing in there can run
    report = sl.verify()
    assert report["ok"], report


def test_a_tampered_file_is_reported(tmp_path, monkeypatch):
    shutil.copytree(VENDOR, tmp_path / "v")
    monkeypatch.setattr(sl, "DIR", tmp_path / "v")
    sl.index.cache_clear()
    victim = next(iter(sl.index().values()))["path"]
    (tmp_path / "v" / victim).write_text("changed")
    assert victim in sl.verify()["mismatched"]
    monkeypatch.undo()
    sl.index.cache_clear()


def test_nothing_is_read_until_a_skill_is_asked_for():
    sl.index.cache_clear()
    assert sl.index.cache_info().currsize == 0
    sl.get("iart:kinetic-typography")
    assert sl.index.cache_info().currsize == 1


def test_the_planner_can_only_choose_real_selectable_skills_and_at_most_two():
    assert sl.normalize_ids(["iart:kinetic-typography", "nope", "barty:object-separation", "../../etc/passwd", "charlie:brand-intake", "iart:promo-video"]) == ["iart:kinetic-typography", "charlie:brand-intake"]
    assert mg.MotionPlan(skills=["iart:promo-video", "x"]).skills == ["iart:promo-video"]
    assert mg.MotionPlan().skills == []
    assert "barty:object-separation" not in sl.planning_block() and "iart:kinetic-typography" in sl.planning_block()


def test_a_skill_is_read_bounded_and_never_by_path():
    text = sl.body("iart:kinetic-typography", 1500)
    assert 200 < len(text) <= 1500 + 60 and not text.startswith("---")
    assert sl.body("../../../etc/passwd") == "" and sl.body("") == ""
    assert sl.reference("motionkit:motion-designer", "LIBRARY.md").startswith("#")
    assert sl.reference("motionkit:motion-designer", "../../../../etc/passwd") == ""


def test_runtime_skills_are_listed_but_not_offered():
    row = get_resource("barty:object-separation")
    assert row["availability"] == "catalog-only" and row["contexts"] == [] and "SAM 2" in " ".join(row["limitations"])
    assert get_resource("motionclone:motionclone")["availability"] == "catalog-only"


def test_the_scene_designer_gets_craft_rules_and_only_the_chosen_skills():
    plan = mg.MotionPlan(title="t", skills=["iart:kinetic-typography"], scenes=[mg.ScenePlan(headline="h", idea="i", start=0, end=4)])
    prompt = mg.scene_request(plan, 1, "brief")
    assert "MOTION CRAFT" in prompt and "COMPOSITION (anti-slide)" in prompt and "SKILL «iart:kinetic-typography»" in prompt
    assert "SKILL «iart:promo-video»" not in prompt
    plain = mg.scene_request(mg.MotionPlan(title="t", scenes=plan.scenes), 1, "brief")
    assert "SKILL «" not in plain and len(plain) < len(prompt)
    assert len(sl.designer_block([])) < 6000 and len(sl.designer_block(["iart:kinetic-typography", "charlie:brand-intake"])) < 12000


def test_the_planner_sees_the_skill_catalogue():
    assert "CRAFT SKILLS" in mg.plan_request("a film about tea")


def test_unknown_motion_kit_calls_are_caught_and_real_ones_are_not():
    assert mg.unknown_motion_kit("MotionKit.arc(tl, el, {x:1}, {x:0}, 1); MotionKit.curve('kit.land')") == []
    assert mg.unknown_motion_kit("MotionKit.explode(tl)") == ["explode"]
    assert mg.unknown_motion_kit("// MotionKit.nope\nHM.rise('.a', 1)") == []
    assert {"arc", "spring", "react", "anticipate", "typeOn", "dur", "curve"} <= mg._motion_kit_names()


def test_invented_curve_names_are_caught_before_the_browser_and_real_ones_pass():
    assert mg.unknown_motion_curves("MotionKit.curve('kit.land'); const c = curve(\"m3.emphasizedDecelerate\"); curve('easings.outExpo')") == []
    assert mg.unknown_motion_curves("tl.to(el,{ease:MotionKit.curve('kit.pop')}); curve('kit.bounce')") == ["kit.bounce", "kit.pop"]
    assert mg.unknown_motion_curves("// curve('kit.pop')\nHM.rise('.a', 1)") == []
    assert {"kit.land", "kit.heavy", "kit.whip", "kit.reveal", "kit.leave", "kit.wind", "kit.drift", "easings.outExpo", "m3.standard", "ramp.slowMid"} <= mg._motion_kit_curves()
    page = mg.MotionPage(title="t", width=1080, height=1920, duration=4, css="", scenes_html='<section class="hm-scene" id="s1"></section>', build_js="tl.to('#s1',{x:1,ease:MotionKit.curve('kit.pop')},0)", update_js="")
    assert any("kit.pop" in p and "kit.land" in p for p in mg.validate_page(page, min_scenes=1))


def test_the_page_loads_motion_kit_and_the_project_ships_it(tmp_path):
    page = mg.MotionPage(title="t", width=1080, height=1920, duration=4, css="", scenes_html='<section id="s1"></section>', build_js="", update_js="") if hasattr(mg, "MotionPage") else None
    html = mg.assemble(page) if page else ""
    assert html.index("assets/kit.js") < html.index("assets/motion-kit.js") < html.index("<style>")
    mg.write_project(tmp_path, page)
    assert (tmp_path / "assets" / "motion-kit.js").is_file() and "MotionKit" in (tmp_path / "assets" / "motion-kit.js").read_text()


def test_skill_tool_and_endpoint_are_read_only_and_bounded():
    from app.studio_tools import SkillReadInput, _read_skill
    got = _read_skill(SkillReadInput(skill_id="motionkit:motion-designer", max_chars=800))
    assert got["license"] == "MIT" and got["source"].endswith("/motion-kit") and len(got["text"]) <= 900 and "LIBRARY.md" in " ".join(got["references"])
    assert _read_skill(SkillReadInput(skill_id="../../etc/passwd"))["error"] == "unknown-skill"


CHROME = next((p for p in (os.environ.get("CHROME_BIN", ""), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", shutil.which("chromium") or "", shutil.which("google-chrome") or "") if p and Path(p).is_file()), None)


@pytest.mark.skipif(CHROME is None, reason="needs a local Chrome")
def test_motion_kit_frames_do_not_depend_on_how_the_timeline_is_played(tmp_path):
    """Seek-safety in a real browser: the same time gives the same pixels' transforms whether reached by playing forward or by jumping around."""
    from engine.hyperframes.assets import ensure_gsap
    shutil.copy2(ensure_gsap(), tmp_path / "gsap.min.js")
    shutil.copy2(mg.KIT / "kit.js", tmp_path / "kit.js")
    shutil.copy2(mg.KIT / "motion-kit.js", tmp_path / "motion-kit.js")
    (tmp_path / "t.html").write_text("""<!doctype html><html><body>
<div data-composition-id="root" data-duration="6" style="width:1080px;height:1920px">
<div id="a">a</div><div id="b">b</div><div id="c">c</div><div id="d" dir="rtl" style="direction:rtl;width:400px">سلام دنیا</div><div id="e">x</div></div>
<script src="gsap.min.js"></script><script src="kit.js"></script><script src="motion-kit.js"></script>
<script>
const MK = MotionKit, tl = gsap.timeline({paused:true});
['#a','#b','#c'].forEach((el,i)=>MK.arc(tl, el, {x:900,y:80},{x:0,y:0}, 1 + MK.react(i)));
MK.anticipate(tl,'#e','x',0,300,2); const s = MK.spring({response:.45,damping:.8}); tl.fromTo('#e',{y:80},{y:0,duration:s.duration,ease:s.ease},3);
MK.typeOn(tl, document.querySelector('#d'), 1); MK.exitTo(tl,'#a',{x:-900,y:0},4);
const state = () => ['a','b','c','d','e'].map(id => { const el = document.getElementById(id); return el.style.transform + '|' + el.style.clipPath + '|' + el.style.opacity; }).join(';');
const times = [0,.7,1.3,2.1,2.6,3.2,3.9,4.4,5.5], fwd = {}, jump = {};
times.forEach(t => { tl.time(t, false); fwd[t] = state(); });
[...times].reverse().forEach(t => { tl.time(t, false); jump[t] = state(); });
const dClip = (tl.time(1.01,false), document.getElementById('d').style.clipPath);
document.title = JSON.stringify({same: times.every(t => fwd[t] === jump[t]), dClip, moved: fwd[0] !== fwd[2.6], sample: fwd[1.3]});
</script></body></html>""")
    out = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--virtual-time-budget=3000", "--dump-dom", f"file://{tmp_path / 't.html'}"], capture_output=True, text=True, timeout=60).stdout
    title = out.split("<title>")[1].split("</title>")[0].replace("&quot;", '"')
    report = json.loads(title.replace("&amp;", "&"))
    assert report["same"], report
    assert report["moved"], report
    assert "100%" in report["dClip"] and report["dClip"].split("inset(")[1].split(" ")[3].startswith("100"), report     # right-to-left text starts hidden from its right edge
