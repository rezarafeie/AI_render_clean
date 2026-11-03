import shutil
import subprocess
from pathlib import Path

import pytest

from creative import directives
from creative.audio import contracts, loudness, persian, quality

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is required")


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


# --- contracts
def test_milliseconds_round_half_up_and_frames_floor():
    assert contracts.ms(0.0005) == 1 and contracts.ms(1.2345) == 1235 and contracts.ms(2.5) == 2500
    assert contracts.frame(999, 30) == 29 and contracts.frame(1000, 30) == 30
    with pytest.raises(Exception):
        contracts.AudioTimingEvent(id="a", type="beat", time_ms=-1)


def test_voice_requests_are_validated():
    ok = contracts.VoiceGenerationRequest(text="سلام", language="fa-IR", direction=contracts.VoiceDirection(emotion="calm", pace=0.9))
    assert ok.direction.pace == 0.9
    with pytest.raises(Exception):
        contracts.VoiceGenerationRequest(text="x", language="persian")
    with pytest.raises(Exception):
        contracts.VoiceDirection(emotion="sleepy")


# --- Persian text
@pytest.mark.parametrize("number,words", [(0, "صفر"), (7, "هفت"), (15, "پانزده"), (21, "بیست و یک"), (100, "صد"), (205, "دویست و پنج"),
                                          (1000, "هزار"), (1205, "هزار و دویست و پنج"), (2500, "دو هزار و پانصد"), (3000000, "سه میلیون")])
def test_number_words(number, words):
    assert persian.number_words(number) == words


def test_speakable_spells_digits_in_any_script_and_percentages():
    assert persian.speakable("قیمت ۲۵۰۰ تومان است") == "قیمت دو هزار و پانصد تومان است"
    assert persian.speakable("تخفیف 20% برای شما") == "تخفیف بیست درصد برای شما"
    assert persian.speakable("كتاب خوب ي") == "کتاب خوب ی"                 # Arabic letter variants unified


def test_decimals_dates_and_codes_are_left_as_written():
    assert persian.speakable("نسخه 3.5 آمد") == "نسخه سه ممیز پنج آمد" and persian.speakable("نسخه 1.2.3 آمد") == "نسخه 1.2.3 آمد"
    assert persian.speakable("تاریخ 1405/08/12 است") == "تاریخ دوازدهم آبان هزار و چهارصد و پنج است"
    assert "2025/08/12" in persian.speakable("date 2025/08/12")             # a Gregorian-looking date is left as written


def test_english_text_is_untouched_except_for_dictionary():
    assert persian.speakable("Meet 5 creators.") == "Meet 5 creators."
    assert persian.speakable("Use the API", {"API": "A P I"}) == "Use the A P I"


def test_pronunciation_entries_apply_whole_words_only():
    spoken = persian.speakable("با EditorGPT و EditorGPTPro کار کن", {"EditorGPT": "ادیتور جی‌پی‌تی"})
    assert "با ادیتور جی‌پی‌تی و EditorGPTPro" in spoken


def test_the_dictionary_is_parsed_from_lines():
    assert persian.parse_dictionary(["EditorGPT = ادیتور جی‌پی‌تی", "bad line", " AI = اِی‌آی "]) == {"EditorGPT": "ادیتور جی‌پی‌تی", "AI": "اِی‌آی"}


def test_pronounce_directive_lines_reach_the_record_and_are_removed():
    text, found = directives.parse("Pronounce: EditorGPT = ادیتور جی‌پی‌تی\nتلفظ: AI = اِی‌آی\nPronounce: nonsense\nScene")
    assert found.pronunciations == {"EditorGPT": "ادیتور جی‌پی‌تی", "AI": "اِی‌آی"} and text == "Scene" and len(found.notes) == 1


# --- quality (objective)
def test_completeness_counts_missing_and_added_words():
    full = quality.completeness("امروز هوا بسیار خوب است", "امروز هوا بسیار خوب است")
    assert full["word_error_rate"] == 0
    cut = quality.completeness("امروز هوا بسیار خوب است", "امروز هوا")
    assert cut["word_error_rate"] == 0.6 and "خوب" in cut["missing"]
    assert quality.completeness("hello world", "Hello, World!")["word_error_rate"] == 0       # case and punctuation do not matter
    assert quality.completeness("a b", "a b c")["added"] == ["c"]


@needs_ffmpeg
def test_loudness_is_measured_and_normalised_to_the_target(tmp_path):
    src = tmp_path / "tone.wav"; out = tmp_path / "norm.wav"
    ff("-f", "lavfi", "-i", "sine=frequency=300:duration=6", "-af", "volume=-30dB", str(src))
    result = loudness.normalize(src, out, "social_video")
    assert result["before"]["integrated_lufs"] < -25
    assert abs(result["after"]["integrated_lufs"] - (-14.0)) < 1.5 and result["after"]["true_peak_dbtp"] <= -1.0


@needs_ffmpeg
def test_the_report_flags_clipping_silence_and_duration(tmp_path):
    clipped = tmp_path / "clipped.wav"; quiet = tmp_path / "quiet.wav"
    ff("-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-af", "volume=8", "-c:a", "pcm_s16le", str(clipped))
    ff("-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-af", "apad=whole_dur=6", str(quiet))
    report = quality.analyse(clipped, expected_duration_s=5.0)
    codes = {w["code"] for w in report["warnings"]}
    assert "clipping" in codes and "duration_mismatch" in codes and report["ok"] is False
    assert "excess_silence" in {w["code"] for w in quality.analyse(quiet)["warnings"]}


@needs_ffmpeg
def test_a_clean_file_passes_and_the_report_says_what_it_cannot_judge(tmp_path):
    good = tmp_path / "good.wav"
    ff("-f", "lavfi", "-i", "sine=frequency=300:duration=4", "-af", "volume=-18dB", str(good))
    report = quality.analyse(good, expected_text="سلام دنیا", recognised_text="سلام دنیا", expected_duration_s=4.0)
    assert report["ok"] is True and any("pronounced" in item for item in report["not_checked"])


def test_missing_and_corrupt_files_are_never_reported_as_fine(tmp_path):
    assert quality.analyse(tmp_path / "none.wav")["warnings"][0]["code"] == "missing_or_empty"
    bad = tmp_path / "bad.wav"; bad.write_bytes(b"not audio")
    assert quality.analyse(bad)["ok"] is False


def test_narration_speaks_normalised_text_and_keeps_the_script(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from app import motion_graphic as app_mg
    from brain import localize
    from creative import motion_graphic as mg
    plan = mg.MotionPlan(title="t", duration=6, scenes=[mg.ScenePlan(headline="h", idea="i", start=0, end=3, narration="قیمت ۲۵۰۰ تومان برای EditorGPT"),
                                                      mg.ScenePlan(headline="h2", idea="i", start=3, end=6, narration="Meet 5 creators.")])
    spoken = {}
    def fake(texts, out, voice="", style=""):
        spoken["texts"] = list(texts)
        return [(tmp_path / f"c{i}.wav", 2.0) for i in range(len(texts))]
    monkeypatch.setattr(localize, "synthesize_narration", fake)
    monkeypatch.setattr(app_mg, "_note", lambda *a, **k: None)
    monkeypatch.setattr(app_mg, "_gate_clips", lambda plan, clips: [])
    retimed, _, _ = app_mg._narrate(tmp_path, {"pronunciations": {"EditorGPT": "ادیتور جی‌پی‌تی"}}, plan, "fp")
    assert spoken["texts"] == ["قیمت دو هزار و پانصد تومان برای ادیتور جی‌پی‌تی", "Meet 5 creators."]
    assert retimed.scenes[0].narration == "قیمت ۲۵۰۰ تومان برای EditorGPT"          # the script shown to the person is unchanged


def test_a_bad_clip_is_reported_but_never_stops_the_build(tmp_path):
    from app import motion_graphic as app_mg
    from creative import motion_graphic as mg
    plan = mg.MotionPlan(title="t", duration=3, scenes=[mg.ScenePlan(headline="h", idea="i", start=0, end=3, narration="سلام")])
    notes = app_mg._gate_clips(plan, [(tmp_path / "missing.wav", 1.0)])
    assert notes and "صحنهٔ 1" in notes[0]


def test_verification_stops_asking_a_recogniser_that_keeps_failing(tmp_path):
    from creative.audio import verify
    calls = []
    def recognise(path, index):
        calls.append(index); return None
    clips = [(tmp_path / f"{i}.wav", 1.0) for i in range(5)]
    _, report = verify.verify_clips(["a b c"] * 5, clips, recognise, lambda i: None)
    assert calls == [0, 1] and [r["status"] for r in report] == ["not_checked"] * 5 and "skipped" in report[4]["reason"]


def test_times_phone_numbers_and_years_are_read_as_people_say_them():
    assert persian.speakable("ساعت 14:30 بیایید") == "ساعت چهارده و سی دقیقه بیایید" and persian.speakable("ساعت 9:00") == "ساعت نه"
    assert persian.speakable("شماره ۰۹۱۲۳۴۵۶۷۸۹") == "شماره صفر نه یک دو سه چهار پنج شش هفت هشت نه"
    assert persian.speakable("سال ۱۴۰۳ و ۰٫۰۵") .startswith("سال هزار و چهارصد و سه")
    assert persian.speakable("از 1403/01/01 تا 1403/12/30") == "از اول فروردین هزار و چهارصد و سه تا سی‌ام اسفند هزار و چهارصد و سه"
    assert persian.speakable("روز 23 و 3.05") == "روز بیست و سه و سه ممیز صفر پنج"
    assert [persian.ordinal(d) for d in (1, 3, 12, 21, 23)] == ["اول", "سوم", "دوازدهم", "بیست و یکم", "بیست و سوم"]
