"""Only frame rendering opens the render card; the Claude engines' Persian planning, cutting, graphics, check and mix messages are steps of the chat."""
from app.studio_assets import render_stage

NOT_RENDER = ["دارم تدوین و گرافیک‌ها را برنامه‌ریزی می‌کنم.", "دارم برش‌ها را می‌زنم.", "دارم گرافیک‌ها را کدنویسی می‌کنم.",
              "دارم صحنه‌ها را می‌سازم و بررسی می‌کنم.", "دارم صحنه‌ها را بررسی می‌کنم.", "دارم صدا را میکس می‌کنم.", "دارم ایده، متن و سبک فیلم را می‌نویسم."]


def test_planning_cutting_graphics_checks_and_mix_are_not_the_render_card():
    for text in NOT_RENDER:
        assert not render_stage(text).startswith("render"), text


def test_the_real_render_message_opens_the_render_card():
    assert render_stage("دارم ویدیو را رندر می‌کنم.") == "rendering"
    assert render_stage("رندر ابری: ۴۰٪") == "rendering"


def test_the_old_english_messages_behave_as_before():
    assert render_stage("designing scene 3") == "designing motion scenes"
    assert render_stage("adding subtitles") == "adding subtitles"
    assert render_stage("Rendering frames 40%") == "rendering"
    assert render_stage("") == "rendering"


def test_the_claude_talking_steps_are_numbered():
    from app.talking_reel import step_label
    assert [step_label(p) for p in (18, 24, 32, 45, 56, 66, 80, 95)] == [
        "مرحلهٔ 1 از 7", "مرحلهٔ 2 از 7", "مرحلهٔ 3 از 7", "مرحلهٔ 4 از 7", "مرحلهٔ 5 از 7", "مرحلهٔ 6 از 7", "مرحلهٔ 6 از 7", "مرحلهٔ 7 از 7"]
