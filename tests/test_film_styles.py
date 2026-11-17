import json

from creative import film_styles as fs
from creative import claude_motion as cm
from creative import claude_vox as vx
from creative.claude_intro import author


def test_the_whole_library_is_offered_in_the_cached_system_prompts():
    catalog = fs.catalog()
    assert catalog.count("\n- ") >= 98 and "swiss-motion" in catalog and "director-method" not in catalog
    assert catalog in cm._direct_guide() and catalog in vx._story_guide()


def test_style_ids_are_checked_and_the_guide_carries_the_adaptation_rules():
    assert fs.valid("swiss-motion") == fs.valid("lemo:swiss-motion") == "lemo:swiss-motion"
    assert fs.valid("lemo:not-a-style") == "" and fs.valid("") == ""
    text = fs.guide("swiss-motion")
    assert text.startswith("THIS FILM'S STYLE «lemo:swiss-motion»") and "letter by letter" in text and "Colour logic" in text
    assert fs.menu("x", ["swiss-motion", "nope"]).endswith("swiss-motion") and fs.menu("x", []) == ""


def test_recent_films_of_the_person_are_read_from_every_chat(tmp_path):
    user = tmp_path / "studio" / "1"
    for i, data in enumerate([{"direction": {"title": "A", "look": "black ground, neon", "style": "lemo:ascii-crt"}},
                              {"vox": True, "story": {"title": "B", "look": "paper_collage", "look_note": "red tape", "style": ""}},
                              {"intro": "story", "direction": {"title": "C", "look": "cream paper", "style": ""}}]):
        folder = user / f"c{i}" / "motion" / f"m{i}"
        folder.mkdir(parents=True)
        (folder / "claude_motion.json").write_text(json.dumps(data))
    me = user / "c9" / "motion" / "m9"
    me.mkdir(parents=True)
    got = fs.recent(me)
    assert {g["title"] for g in got} == {"A", "B", "C"} and {g["engine"] for g in got} == {"motion", "vox", "intro story"}
    assert "must not look like them" in fs.recent_block(got) and fs.recent_block([]) == ""


def test_the_style_reaches_the_scene_writers_of_motion_and_vox():
    d = cm.Direction(title="t", style="lemo:swiss-motion", look="grid")
    brief = cm._brief(d, {"scenes": []})
    assert any(part.startswith("THIS FILM'S STYLE") for part in brief)
    assert not any(part.startswith("THIS FILM'S STYLE") for part in cm._brief(cm.Direction(title="t"), {"scenes": []}))
    story = vx.Story(title="t", style="lemo:swiss-motion")
    assert "LOOK GUIDE above sets the kit" in vx._style_guide(story)


def test_the_intro_author_returns_a_custom_component_and_the_project_routes_to_it(tmp_path):
    design, code = author._clean("=====\n// DESIGN: a navy ground, the mark as a folding paper bird\nexport const Custom = () => null;")
    assert design.startswith("a navy ground") and "export const Custom" in code
    try:
        author._clean("export const Story = () => null;")
        assert False
    except ValueError:
        pass
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "content.json").write_text(json.dumps({"kind": "story"}))
    author.install(tmp_path, code)
    assert json.loads((tmp_path / "src" / "content.json").read_text())["custom"] is True
    author.install(tmp_path, None)
    assert json.loads((tmp_path / "src" / "content.json").read_text())["custom"] is False
    assert "export const Custom" in (tmp_path / "src" / "Custom.tsx").read_text()
    assert author.enabled("story") and author.enabled("reel") and not author.enabled("presenter") and not author.enabled("film3d")
    index = (author.KIT / "index.ts").read_text()
    assert "(content as any).custom ? (Custom" in index


def test_a_story_intro_is_a_claude_motion_film_with_the_brand_guide(tmp_path):
    from creative import claude_intro as ci
    notes = []
    hooks = cm.Hooks(note=lambda *a, **k: notes.append(a), progress=lambda *a: None, cancelled=lambda: False)
    rec = {"request": "معرفی Canva", "context": "Canva is an online design platform. " * 20}
    out = ci.story_as_film(rec, tmp_path, hooks)
    assert out["film_guide"] == ci.STORY_FILM_GUIDE and "old template" in out["film_guide"] and out["context"].startswith("Canva")
    assert (tmp_path / "intro_facts.txt").read_text().startswith("Canva")
    again = ci.story_as_film({**rec, "context": ""}, tmp_path, hooks)          # a retry keeps the same facts (the plan's checkpoint depends on them)
    assert again["context"] == out["context"]
    import inspect
    from app import motion_graphic as mg
    src = inspect.getsource(mg._run_claude)
    assert 'record.get("intro") == "story"' in src and "claude_intro.story_as_film" in src
