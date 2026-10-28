from creative import handoff
from creative.director import direct_idea

TEXT = """یک ریلز اینستاگرام بساز.

ایده: داستان یک انبار پر که خالی شد.

هوک (دو ثانیه‌ی اول): ۳۲۰ میلیون خوابیده

سبک بصری: تایپوگرافی درشت روی کاغذ گرم

حس و حال: تأمل‌برانگیز

سکانس‌ها:
1. (3s) تصویر: انبار پر | متن روی صفحه: ۳۲۰ میلیون خوابیده | روایت: این انبار سه‌صد و بیست میلیون سرمایه‌ی خوابیده بود.
2. (5s) تصویر: کارتن‌ها محو می‌شوند | متن روی صفحه: و اگر خالی شود؟ | روایت: تا روزی که فهمیدم فروش به کارتن نیاز ندارد.
3. (6s) تصویر: لپ‌تاپ | متن روی صفحه: یک فایل | روایت: یک فایل، هزار بار فروش.

دعوت به اقدام: انبار را کامنت کن
"""


def test_an_approved_handoff_is_adopted_word_for_word_without_any_model_call(monkeypatch):
    monkeypatch.setattr("creative.llm.ask", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no model call expected")))
    plan = direct_idea(TEXT, duration_s=30)
    beats = plan.chosen.beats
    assert [b.narration for b in beats][0].startswith("این انبار") and len(beats) == 3 and beats[1].title == "و اگر خالی شود؟"
    assert plan.models == ["approved-script"] and "word for word" in plan.director_notes


def test_text_without_scenes_is_not_a_handoff():
    assert handoff.parse("یک ویدیو درباره فروش بساز") is None
    assert handoff.parse(TEXT.replace("3.", "x").split("سکانس‌ها:")[0]) is None
