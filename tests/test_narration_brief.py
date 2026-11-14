"""«با صدای خانم» in the request reaches the voice casting (it used to see only a fixed 'narration educational')."""
from brain import localize
from brain import speech_policy

VOICES = [
    {"voice_id": "m1", "languages": ["fa"], "labels": {"gender": "male"}},
    {"voice_id": "f1", "languages": ["fa"], "labels": {"gender": "female"}},
]


def cast(brief):
    token = localize.narration_brief(brief)
    try:
        return speech_policy.choose_voice(VOICES, (localize._BRIEF.get() + " narration educational").strip(), "")
    finally:
        localize._BRIEF.reset(token)


def test_a_female_voice_request_picks_a_female_voice():
    assert cast("این موشن گرافی را با صدای خانم بساز") == "f1"


def test_without_a_request_the_default_stays_male():
    assert cast("") == "m1"


def test_a_workshop_brief_stays_male():
    assert cast("تبلیغ ابزار کارگاه") == "m1"


def test_cast_passes_the_brief_to_the_casting(monkeypatch):
    seen = {}
    monkeypatch.setattr(speech_policy, "eleven_cast", lambda text, voice, model, *, language="", context="": (seen.setdefault("context", context), "model")[1:] and ("v", "m"))
    monkeypatch.setattr(localize, "language_of", lambda text: "fa")
    monkeypatch.setattr(localize, "tts_voice", lambda: "")
    monkeypatch.setattr(localize, "tts_model", lambda: "")
    token = localize.narration_brief("با صدای خانم")
    try:
        localize._cast("متن فارسی")
    finally:
        localize._BRIEF.reset(token)
    assert "با صدای خانم" in seen["context"]


def test_an_explicit_gender_beats_the_studios_preferred_voice():
    voices = [{"voice_id": "m1", "languages": ["fa"], "labels": {"gender": "male"}},
              {"voice_id": "f1", "languages": ["fa"], "labels": {"gender": "female"}}]
    assert speech_policy.choose_voice(voices, "این را با صدای خانم بساز narration educational", "m1") == "f1"
    assert speech_policy.choose_voice(voices, "گوینده مرد باشد narration educational", "f1") == "m1"
    # no explicit request: the preferred voice still wins, as before
    assert speech_policy.choose_voice(voices, "یک فیلم دربارهٔ تغذیه narration educational", "m1") == "m1"
    assert speech_policy.choose_voice(voices, "یک فیلم narration educational", "f1") == "f1"


def test_explicit_gender_is_read_from_plain_words():
    assert speech_policy.explicit_gender("موشن را با صدای خانم بساز") == "female"
    assert speech_policy.explicit_gender("گوینده زن") == "female"
    assert speech_policy.explicit_gender("با صدای آقا") == "male"
    assert speech_policy.explicit_gender("female voice please") == "female"
    assert speech_policy.explicit_gender("برای خانم‌ها محصول آرایشی") == ""
    assert speech_policy.explicit_gender("") == ""
