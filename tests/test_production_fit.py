from types import SimpleNamespace

import pytest

from creative import production, speech
from creative.schemas import CreativeUnavailable


def _plan(words: int, scenes: int = 4):
    line = " ".join(["کلمه"] * words)
    beats = [SimpleNamespace(narration=line, duration_weight=1.0, title="t", visual="v", role="r", source_asset_index=None, motion_engine="default",
                             visual_type="x", motion="m", line_id="l", why_visual="w", emotion="e", focus="f", link_prev="", reference_trait="") for _ in range(scenes)]
    return SimpleNamespace(chosen=SimpleNamespace(beats=beats), models=["m"])


def test_narration_longer_than_requested_length_extends_the_video():
    plan = _plan(30)
    need = sum(speech.speech_seconds(b.narration) * speech.MARGIN for b in plan.chosen.beats)
    assert need > 21
    board = production.storyboard_from_plan(plan, prompt="p", language="fa", style="s", duration=21, asset_indices=set())
    assert board.total_duration_s >= need


def test_narration_beyond_ninety_seconds_is_still_rejected():
    with pytest.raises(CreativeUnavailable):
        production.storyboard_from_plan(_plan(400), prompt="p", language="fa", style="s", duration=30, asset_indices=set())


def test_content_duration_is_clamped_not_rejected():
    from app.studio_tools import ContentInput
    base = {"prompt": "abc", "user_key": "1", "provider": "p"}
    assert ContentInput.model_validate({**base, "duration": 5}).duration == 15
    assert ContentInput.model_validate({**base, "duration": 400}).duration == 90
    assert ContentInput.model_validate({**base, "duration": 42}).duration == 42
