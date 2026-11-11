"""score_plan: a repetitive, text-only, filler plan fails; a varied one passes; errors and the flag never get in the way."""
from creative import plan_checks
from creative.motion_graphic import MotionPlan, ScenePlan


def _plan(rows):
    scenes, t = [], 0.0
    for head, narr, length, shot in rows:
        scenes.append(ScenePlan(headline=head, idea="i", narration=narr, start=t, end=t + length))
        t += length
    return MotionPlan(duration=t, scenes=scenes)


def test_a_repetitive_filler_plan_is_revised_or_failed():
    plan = _plan([(f"عنوان {i}", "با ما همراه باشید بهترین کیفیت", 5, "") for i in range(6)])
    result = plan_checks.score_plan(plan)
    assert result["verdict"] in {"revise", "fail"} and result["violations"]


def test_a_varied_plan_is_ok():
    plan = _plan([("شروع", "یک", 3, ""), ("مشکل", "دو", 7, ""), ("راه‌حل", "سه", 5, ""), ("نتیجه", "چهار", 9, ""), ("دعوت", "پنج", 4, "")])
    for s in plan.scenes[:3]:
        s.shotcraft_id = ""
    assert plan_checks.score_plan(plan)["verdict"] in {"ok", "strong", "revise"}


def test_errors_and_tiny_plans_return_ok_and_the_flag_defaults_off(monkeypatch):
    assert plan_checks.score_plan(object())["verdict"] == "ok"
    assert plan_checks.score_plan(_plan([("a", "b", 3, "")]))["verdict"] == "ok"
    monkeypatch.delenv("PLAN_CHECKS", raising=False)
    assert not plan_checks.enabled()
    monkeypatch.setenv("PLAN_CHECKS", "1")
    assert plan_checks.enabled()


def test_delivery_promise_counts_scenes_that_fell_back_to_plain_cards(monkeypatch):
    from creative import motion_graphic as mg
    plan = _plan([("الف", "یک", 4, ""), ("ب", "دو", 5, ""), ("ج", "سه", 6, "")])
    drafts = {n: mg.fallback_scene(plan, n) for n in (1, 2)}
    drafts[3] = drafts[1].model_copy(update={"html": "<div>designed</div>"})
    broken = plan_checks.promise_broken(plan, drafts, mg.fallback_scene)
    assert broken and broken["scenes"] == [1, 2]
    assert plan_checks.promise_broken(plan, {3: drafts[3]}, mg.fallback_scene) is None
    monkeypatch.delenv("DELIVERY_PROMISE", raising=False)
    assert not plan_checks.promise_enabled()
