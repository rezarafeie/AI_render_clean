from types import SimpleNamespace

from app import studio_orchestrator as o


def test_scenario_message_lists_every_scene_with_narration_text_and_picture_idea():
    board = {"total_duration_s": 20, "scenes": [
        {"duration_s": 8, "narration_text": "اول مشکل را نشان می‌دهیم", "text_overlay": "مشکل", "media_prompt": "a worn leather notebook", "media_method": "generate"},
        {"duration_s": 12, "narration_text": "بعد راه‌حل", "text_overlay": "", "description": "نمودار رشد", "media_method": "upload"}]}
    text = o._scenario_message(board, 30, estimate=0.42)
    assert "۲" not in text and "2 صحنه" in text and "20 ثانیه" in text
    assert "**صحنهٔ 1 · 8 ثانیه**" in text and "نریشن: «اول مشکل را نشان می‌دهیم»" in text
    assert "متن روی تصویر: مشکل" in text and "تصویر (ساخته‌شده با هوش مصنوعی): a worn leather notebook" in text
    assert "تصویر (فایل شما): نمودار رشد" in text and "$0.42" in text


def test_scenario_message_says_motion_clips_cost_credits():
    text = o._scenario_message({"scenes": [{"duration_s": 5}]}, 5, motion_scenes=1)
    assert "اعتبار" in text


def test_idea_message_gives_understanding_and_chosen_idea_once():
    chosen = SimpleNamespace(id="a", name="ادعای بی‌مقدمه", angle="ادعا را مثل حکم می‌کوبیم", hook="جملهٔ اول", visual_language="ساده", pacing="تند", why_it_works="روشن است")
    other = SimpleNamespace(id="b", name="زنجیرهٔ علت")
    plan = SimpleNamespace(brief=SimpleNamespace(topic="جنگ", core_message="پیام", audience="عموم", goal="آگاهی", tone="جدی"), chosen=chosen, concepts=[chosen, other])
    text = o._idea_message(plan)
    assert "موضوع: جنگ" in text and "ایدهٔ انتخاب‌شده: «ادعای بی‌مقدمه»" in text and "«زنجیرهٔ علت»" in text
    assert text.count("ادعای بی‌مقدمه") == 1


def test_scenario_message_names_graphics_honestly_and_rounds_seconds():
    board = {"scenes": [{"duration_s": 7.73333333, "narration_text": "متن", "media_prompt": "کارت دو ستونی", "visual_type": "comparison", "media_method": "generate"}]}
    text = o._scenario_message(board, 8)
    assert "7.7 ثانیه" in text and "7.73333" not in text and "گرافیک و تایپوگرافی متحرک" in text


def test_the_chosen_idea_leads_the_scenario_message():
    from types import SimpleNamespace
    from app import studio_orchestrator as o
    idea = SimpleNamespace(chosen=SimpleNamespace(name="نوبت صدای تو", angle="هدست را با دو نقش معرفی می‌کنیم", hook="بازی رو می‌شنوی؟", visual_language="ذغالی و آبی"))
    text = o._scenario_message({"scenes": [{"duration_s": 5, "narration_text": "سلام"}]}, 30, idea=idea)
    assert text.startswith("**ایدهٔ انتخاب‌شده: «نوبت صدای تو»**")
    assert "شروع: بازی رو می‌شنوی؟" in text and "**سناریوی پیشنهادی**" in text
    assert text.index("ایدهٔ انتخاب‌شده") < text.index("سناریوی پیشنهادی")
    assert "ایدهٔ انتخاب‌شده" not in o._scenario_message({"scenes": [{"duration_s": 5}]}, 30)       # without a plan nothing changes
