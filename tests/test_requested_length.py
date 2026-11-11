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
        seen.append(user)
        return shaped
    monkeypatch.setattr(mg.llm, "ask", fake_ask)
    import pytest
    from creative.schemas import CreativeUnavailable
    kept = mg.plan("یک ریل حدود ۴۵ ثانیه‌ای بساز", repairs=1)             # still too long after the repair: kept, a long film beats no film
    assert len(seen) == 2 and "asked for about 45" in seen[1] and "LENGTH" in seen[0] and kept.duration > 54
