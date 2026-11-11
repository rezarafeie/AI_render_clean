"""creative/audio/film_music.py: the motion engine's music glue for engines whose scene times are fixed by a recorded voice."""
import json

from creative import motion_graphic as mg
from creative.audio import film_music


def _plan():
    rows = [mg.ScenePlan(headline=f"h{i}", idea="i", narration="x", start=i * 4.0, end=(i + 1) * 4.0) for i in range(3)]
    return mg.MotionPlan(duration=12.0, scenes=rows)


def test_each_scene_learns_the_beats_and_the_accent_inside_it(tmp_path):
    timing = {"bpm": 120, "beat_confidence": 0.9, "strong_beats_ms": [500, 4500, 8500], "bars_ms": [], "beats_ms": [], "drops_ms": [8200]}
    (tmp_path / "music_timing.json").write_text(json.dumps({"timing": timing}))
    plan = film_music.attach_beats(tmp_path, _plan())
    assert plan.scenes[0].beats == [0.5] and plan.scenes[2].accent == 0.2 and plan.scenes[2].beat_s == 0.5 and plan.scenes[1].accent is None


def test_without_a_reliable_grid_the_plan_is_untouched_and_missing_files_are_fine(tmp_path):
    plan = _plan()
    assert film_music.attach_beats(tmp_path, plan) is plan
    (tmp_path / "music_timing.json").write_text(json.dumps({"timing": {"bpm": 120, "beat_confidence": 0.1}}))
    assert film_music.attach_beats(tmp_path, plan) is plan


def test_sfx_none_and_master_without_voice_return_nothing(tmp_path):
    assert film_music.sfx(tmp_path, [0, 4], 8, [], 4.0, "none") == (None, [])
    assert film_music.master(tmp_path, [], None, 8.0) == (None, [])
    assert film_music.master(tmp_path, [{"path": "x", "start": 0}], None, 8.0, "off") == (None, [])


def test_the_director_flag_defaults_on_and_turns_off(monkeypatch):
    monkeypatch.delenv("FILM_MUSIC_DIRECTOR", raising=False)
    assert film_music.director_enabled()
    monkeypatch.setenv("FILM_MUSIC_DIRECTOR", "0")
    assert not film_music.director_enabled()
