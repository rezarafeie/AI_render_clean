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
