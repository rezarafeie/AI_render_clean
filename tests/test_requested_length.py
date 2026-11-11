"""The length a person asks for ("حدود ۴۵ ثانیه") reaches the planner and a plan far from it is sent back."""
from creative import motion_graphic as mg
from creative.motion_graphic import MotionPlan, ScenePlan, length_problems, requested_seconds


def test_the_requested_length_is_read_in_persian_and_english_and_product_claims_are_ignored():
    assert requested_seconds("ریل پرانرژی حدود ۴۵ ثانیه‌ای بساز") == 45
    assert requested_seconds("make a 45 seconds promo") == 45
    assert requested_seconds("30-40 seconds") == 35
    assert requested_seconds("یک دقیقه") == 60 and requested_seconds("۲ دقیقه") is None and requested_seconds("بدون عدد") is None
    assert requested_seconds("ویدیو در ۳۰ ثانیه ساخته می‌شود؛ ریل ۴۵ ثانیه‌ای") == 45
    assert requested_seconds("within 20 seconds") is None and requested_seconds("video 200 seconds") is None


def _plan(duration: float, words: int = 20) -> MotionPlan:
    scene = ScenePlan(headline="x", narration=" ".join(["کلمه"] * words), idea="i", start=0, end=duration)
    return MotionPlan(duration=duration, scenes=[scene, scene.model_copy(update={"start": duration, "end": duration})])


def test_a_plan_far_from_the_requested_length_is_rejected_with_the_word_budget_and_a_close_one_is_not():
    assert length_problems(_plan(74), 45) and "36-54 s" in length_problems(_plan(74), 45)[0]          # the budget is said in seconds and in words
    assert not length_problems(_plan(44), 45) and not length_problems(_plan(52), 45) and not length_problems(_plan(74), None)


def test_an_invented_catalogue_id_or_component_is_dropped_instead_of_rejecting_the_whole_plan():
    scene = {"headline": "h", "idea": "i", "start": 0, "end": 5, "narration": "n", "shotcraft_id": "shotcraft:made-up",
             "native_component": {"resource_id": "nope", "intensity": 3}}
    plan = MotionPlan.model_validate(MotionPlan.clean_llm_data({"duration": 5, "scenes": [scene, {**scene, "start": 5, "end": 10}]}))
    assert [s.shotcraft_id for s in plan.scenes] == ["", ""] and all(s.native_component is None for s in plan.scenes)
    import pytest
    with pytest.raises(ValueError):
        ScenePlan(headline="h", idea="i", start=0, end=5, shotcraft_id="bad")


def test_a_plan_stretched_by_the_timing_repair_is_still_held_to_the_requested_length(monkeypatch):
    long_words = " ".join(["کلمه"] * 80)
    scenes = [{"headline": "h", "idea": "i", "start": 0, "end": 22, "narration": long_words}, {"headline": "h", "idea": "i", "start": 22, "end": 44, "narration": long_words}]
    shaped = MotionPlan.model_validate({"duration": 44, "scenes": scenes})
    seen = []

    def fake_ask(schema, system, user, **kw):
        if schema is MotionPlan:
            seen.append(user)
        return shaped
    monkeypatch.setattr(mg.llm, "ask", fake_ask)
    import pytest
    from creative.schemas import CreativeUnavailable
    kept = mg.plan("یک ریل حدود ۴۵ ثانیه‌ای بساز", repairs=1)             # still too long after the repair: kept, a long film beats no film
    assert len(seen) == 2 and "asked for about 45" in seen[1] and "LENGTH" in seen[0] and kept.duration > 54


def _long_plan(scenes: int = 6, words: int = 20, each: float = 12.0) -> MotionPlan:
    rows = [ScenePlan(headline=f"h{i}", idea="i", narration=" ".join(["کلمه"] * words), start=i * each, end=(i + 1) * each) for i in range(scenes)]
    return MotionPlan(duration=scenes * each, scenes=rows)


def test_retime_tiles_the_scenes_to_the_asked_length_and_never_cuts_below_what_the_words_need():
    plan = mg.retime_to(_long_plan(5, 10, 14), 45)
    assert abs(plan.duration - 45) < 0.2 and plan.scenes[0].start == 0 and all(a.end == b.start for a, b in zip(plan.scenes, plan.scenes[1:]))
    tight = mg.retime_to(_long_plan(5, 40, 14), 20)           # 200 words cannot be spoken in 20 s: the scenes keep what the words need
    assert tight.duration > 20


def test_a_plan_only_too_long_is_fitted_by_one_small_narration_call_instead_of_another_whole_plan(monkeypatch):
    calls = []

    def fake_ask(schema, system, user, **kw):
        calls.append(schema.__name__)
        if schema is mg._Narration:
            return mg._Narration(lines=[" ".join(["کلمه"] * 8)] * 6)
        return _long_plan(6, 30, 12)                                     # the planner keeps writing a 72 s film with 180 words
    monkeypatch.setattr(mg.llm, "ask", fake_ask)
    result = mg.plan("ریل ۴۵ ثانیه‌ای برای محصول بساز", repairs=2)
    assert calls == ["MotionPlan", "_Narration"] and 36 <= result.duration <= 54 and all(len(s.narration.split()) == 8 for s in result.scenes)


def test_an_unusable_narration_answer_falls_back_to_regenerating_the_plan(monkeypatch):
    seen = []

    def fake_ask(schema, system, user, **kw):
        seen.append(schema.__name__)
        if schema is mg._Narration:
            return mg._Narration(lines=["only one"])
        return _long_plan(6, 30, 12) if len(seen) < 3 else _long_plan(5, 15, 9)
    monkeypatch.setattr(mg.llm, "ask", fake_ask)
    assert 36 <= mg.plan("ریل ۴۵ ثانیه‌ای برای محصول بساز", repairs=2).duration <= 54
