from pathlib import Path

import pytest

from brain import localize as loc


def test_style_tags_open_every_line_and_spans_cover_them():
    full, spans = loc.narration_script(["سلام", "خداحافظ"], "reflective")
    tags = loc.VOICE_STYLES["reflective"][1]
    assert full == f"{tags}سلام. {tags}خداحافظ."
    assert [full[a:b] for a, b in spans] == [f"{tags}سلام.", f"{tags}خداحافظ."]


def test_natural_style_leaves_the_script_unchanged():
    assert loc.narration_script(["سلام"]) == loc.narration_script(["سلام"], "") == ("سلام.", [(0, 5)])


def test_a_chosen_narrator_is_used_as_picked_and_keys_the_cache(tmp_path: Path):
    liam = "TX3LPaxmHKxFdv7VOQHJ"
    assert loc._cast("سلام", liam) == (liam, "eleven_v3")
    other = loc._narration_paths("سلام", tmp_path, "JBFqnCBsd6RMkjVDRZzb")
    assert loc._narration_paths("سلام", tmp_path, liam) != other


def test_unlisted_voices_fall_back_to_studio_casting(monkeypatch):
    monkeypatch.setattr("brain.speech_policy.eleven_cast", lambda *a, **k: ("studio-voice", "eleven_v3"))
    assert loc._cast("سلام", "not-in-the-list") == ("studio-voice", "eleven_v3")
    assert loc._cast("سلام", "") == ("studio-voice", "eleven_v3")


def test_options_list_the_studio_default_first_and_liam():
    assert loc.NARRATORS[0][0] == "" and "TX3LPaxmHKxFdv7VOQHJ" in loc.narrator_ids()
    assert "reflective" in loc.VOICE_STYLES and "" in loc.VOICE_STYLES
