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
    assert length_problems(_plan(74), 45) and "117" in length_problems(_plan(74), 45)[0]          # 45 s × 2.6 words
    assert not length_problems(_plan(44), 45) and not length_problems(_plan(52), 45) and not length_problems(_plan(74), None)
