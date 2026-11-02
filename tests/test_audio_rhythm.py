import wave
from pathlib import Path

import numpy as np
import pytest

from creative.audio import rhythm

SR = 22050


def click_track(path: Path, bpm: float, seconds: float, accent_every: int = 4, lead: float = 0.25) -> Path:
    """Short noise bursts on every beat, louder on the first of each bar, over a quiet pad."""
    rng = np.random.default_rng(7)
    out = 0.01 * np.sin(2 * np.pi * 110 * np.arange(int(SR * seconds)) / SR)
    period = 60.0 / bpm
    t, n = lead, 0
    while t < seconds - 0.1:
        burst = rng.standard_normal(int(SR * 0.04)) * np.exp(-np.arange(int(SR * 0.04)) / (SR * 0.01))
        low = np.sin(2 * np.pi * 80 * np.arange(len(burst)) / SR) * np.exp(-np.arange(len(burst)) / (SR * 0.02))
        gain = 0.9 if n % accent_every == 0 else 0.45
        i = int(t * SR)
        out[i:i + len(burst)] += gain * (0.6 * burst + (0.9 if n % accent_every == 0 else 0.2) * low)[:len(out) - i]
        t += period; n += 1
    pcm = (np.clip(out, -1, 1) * 32000).astype("<i2")
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(SR); f.writeframes(pcm.tobytes())
    return path


@pytest.mark.parametrize("bpm", [100, 120])
def test_tempo_and_beats_are_found_on_a_click_track(tmp_path, bpm):
    result = rhythm.analyse(click_track(tmp_path / "t.wav", bpm, 16))
    assert abs(result["bpm"] - bpm) <= 2.5 and result["bpm_confidence"] > 0.2
    gaps = np.diff(result["beats_ms"])
    assert abs(np.median(gaps) - 60000 / bpm) < 25
    assert min(abs(b - 250) for b in result["beats_ms"][:3]) < 60              # the first click is at 0.25 s
    assert len(result["onsets_ms"]) >= 15


def test_downbeats_are_reported_only_when_they_stand_out(tmp_path):
    accented = rhythm.analyse(click_track(tmp_path / "a.wav", 120, 24, accent_every=4))
    flat = rhythm.analyse(click_track(tmp_path / "f.wav", 120, 24, accent_every=1))
    assert accented["downbeats_reliable"] and accented["downbeats_ms"]
    assert abs(accented["downbeats_ms"][0] - 250) < 80 or abs(accented["downbeats_ms"][0] - 2250) < 80
    assert not flat["downbeats_reliable"] and flat["downbeats_ms"] == []


def test_silence_has_no_beats_and_a_failed_decode_is_an_error(tmp_path):
    quiet = tmp_path / "q.wav"
    with wave.open(str(quiet), "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(SR); f.writeframes(b"\0\0" * SR * 6)
    result = rhythm.analyse(quiet)
    assert result["bpm_confidence"] < 0.1 or result["beats_ms"] == [] or len(result["onsets_ms"]) == 0
    bad = tmp_path / "bad.wav"; bad.write_bytes(b"nope")
    with pytest.raises(ValueError):
        rhythm.analyse(bad)


def test_the_analysis_is_cached_by_file(tmp_path):
    song = click_track(tmp_path / "c.wav", 110, 10)
    first = rhythm.analyse(song, cache_dir=tmp_path / "cache")
    assert list((tmp_path / "cache").glob("rhythm-*.json")) and rhythm.analyse(song, cache_dir=tmp_path / "cache") == first


def test_events_use_the_shared_contract(tmp_path):
    analysis = rhythm.analyse(click_track(tmp_path / "e.wav", 120, 12))
    events = rhythm.events(analysis, "track-1")
    assert {e.type for e in events} >= {"beat", "onset"} and all(isinstance(e.time_ms, int) for e in events)
    assert [e.time_ms for e in events] == sorted(e.time_ms for e in events)


def test_scene_starts_wait_for_a_near_beat_but_never_move_earlier():
    beats = [i * 500 for i in range(1, 40)]                      # every 0.5 s
    starts, total, on_beat = rhythm.snap_starts([0.0, 4.3, 9.1, 13.0], 17.0, beats, 0.35, 60)
    assert starts[0] == 0.0 and all(new >= old for new, old in zip(starts, [0.0, 4.3, 9.1, 13.0]))
    assert starts[1] == 4.5 and on_beat[0] == 1                      # 0.2 s wait to the beat at 4.5
    assert starts[2] == 9.3 and abs(total - 17.4) < 1e-6 or starts[2] >= 9.3   # the delay carries into later scenes
    assert total >= 17.0


def test_a_long_wait_is_not_taken_and_the_limit_is_respected():
    beats = [4000, 5000, 6000]
    starts, total, on_beat = rhythm.snap_starts([0.0, 4.2], 8.0, beats, 0.35, 60)
    assert starts == [0.0, 4.2] and on_beat == []                    # the next beat is 0.8 s away
    unchanged = rhythm.snap_starts([0.0, 4.3], 59.9, [4500], 0.35, 60)
    assert unchanged[0] == [0.0, 4.3] and unchanged[2] == []         # 0.2 s more would pass the 60 s cap


# --- narration verification (pure logic, no speech provider)
from creative.audio import verify


def clips(*seconds):
    return [(Path(f"/tmp/c{i}.wav"), s) for i, s in enumerate(seconds)]


def test_a_matching_scene_is_ok_and_an_incomplete_one_is_repaired_once():
    texts = ["امروز هوا بسیار خوب است", "این صحنه کامل است"]
    heard = {"c0.wav": "امروز هوا", "c1.wav": "این صحنه کامل است", "fresh.wav": "امروز هوا بسیار خوب است"}
    fresh = (Path("/tmp/fresh.wav"), 3.0)
    out, report = verify.verify_clips(texts, clips(2.0, 1.5), lambda p, i: heard[p.name], lambda i: fresh if i == 0 else None)
    assert out[0] == fresh and out[1][0].name == "c1.wav"
    assert [r["status"] for r in report] == ["repaired", "ok"] and report[0]["retried"] == 1


def test_a_scene_that_stays_wrong_is_sent_to_review_and_retries_are_bounded():
    calls = {"n": 0}
    def regenerate(i):
        calls["n"] += 1; return (Path("/tmp/again.wav"), 2.0)
    out, report = verify.verify_clips(["یک دو سه چهار پنج"], clips(2.0), lambda p, i: "یک", regenerate)
    assert report[0]["status"] == "needs_review" and calls["n"] == 1


def test_speech_in_the_wrong_script_is_flagged():
    assert verify.script_mismatch("سلام به همه دوستان", "hello to all my friends")
    assert not verify.script_mismatch("Meet EditorGPT today", "meet editor gpt today")
    out, report = verify.verify_clips(["سلام به همه دوستان"], clips(2.0), lambda p, i: "hello to all my friends", lambda i: None)
    assert report[0]["status"] == "needs_review" and "script" in report[0]["reason"]


def test_a_check_that_cannot_run_is_reported_as_not_checked_never_as_ok():
    def broken(path, index): raise RuntimeError("no speech engine")
    out, report = verify.verify_clips(["متن"], clips(1.0), broken, lambda i: None)
    assert report[0]["status"] == "not_checked" and out == clips(1.0)
    _, none = verify.verify_clips(["متن"], clips(1.0), lambda p, i: None, lambda i: None)
    assert none[0]["status"] == "not_checked"


def test_the_time_budget_stops_further_checks():
    now = {"t": 0.0}
    def clock():
        now["t"] += 100; return now["t"]
    _, report = verify.verify_clips(["الف", "ب"], clips(1.0, 1.0), lambda p, i: "الف", lambda i: None, budget_s=150, clock=clock)
    assert report[-1]["status"] == "not_checked" and "budget" in report[-1]["reason"]


# --- wiring in the motion-graphic build
def test_verify_clips_in_the_build_reports_a_scene_that_does_not_match_the_script(monkeypatch, tmp_path):
    from app import motion_graphic as app_mg
    from brain import localize, transcribe
    monkeypatch.setenv("AUDIO_VERIFY_NARRATION", "1")
    first = tmp_path / "a.wav"; first.write_bytes(b"x")
    monkeypatch.setattr(transcribe, "transcribe", lambda path, out, language=None: {"words": [{"text": "hello"}]})
    monkeypatch.setattr(localize, "synthesize_narration", lambda texts, out, voice="", style="": [(first, 2.0)])
    fixed, notes = app_mg._verify_clips(tmp_path, {}, ["این یک جملهٔ کامل فارسی است"], [(first, 2.0)], "", "")
    assert notes and "صحنهٔ 1" in notes[0] and (tmp_path / "audio_report.json").is_file()


def test_the_verification_can_be_switched_off(monkeypatch, tmp_path):
    from app import motion_graphic as app_mg
    clips_in = [(tmp_path / "a.wav", 1.0)]
    assert app_mg._verify_clips(tmp_path, {}, ["متن"], clips_in, "", "") == (clips_in, [])


def _scene(start, end, text):
    from creative import motion_graphic as mg
    return mg.ScenePlan(headline="h", idea="i", start=start, end=end, narration=text)


def test_balanced_rhythm_moves_a_scene_to_a_near_beat_and_carries_its_voice(monkeypatch, tmp_path):
    from app import motion_graphic as app_mg
    from creative import motion_graphic as mg
    song = click_track(tmp_path / "song.wav", 120, 30)
    plan = mg.MotionPlan(title="t", duration=9.0, scenes=[_scene(0, 4.2, "a"), _scene(4.2, 9.0, "b")])
    audio = [{"path": "/x/a.wav", "start": 0.25, "duration": 3.0}, {"path": "/x/b.wav", "start": 4.45, "duration": 3.0}]
    record = {"rhythm": "balanced", "music": {"mode": "attached", "path": str(song), "name": "song.wav"}}
    new_plan, new_audio, notes = app_mg._sync_rhythm(tmp_path, record, plan, audio)
    assert new_plan.scenes[1].start > 4.2 and new_plan.scenes[1].start - 4.2 <= 0.35 + 1e-6
    assert round(new_audio[1]["start"] - 4.45, 2) == round(new_plan.scenes[1].start - 4.2, 2) and new_audio[0]["start"] == 0.25
    assert new_plan.duration > 9.0 and new_plan.scenes[0].end == new_plan.scenes[1].start and notes and "BPM" in notes[0]


def test_speech_first_and_missing_music_leave_the_timing_alone(tmp_path):
    from app import motion_graphic as app_mg
    from creative import motion_graphic as mg
    plan = mg.MotionPlan(title="t", duration=9.0, scenes=[_scene(0, 4.2, "a"), _scene(4.2, 9.0, "b")])
    audio = [{"path": "/x/a.wav", "start": 0.25, "duration": 3.0}]
    for record in ({"rhythm": "speech_first", "music": {"mode": "attached", "path": "/none.wav"}}, {"rhythm": "balanced", "music": None},
                   {"rhythm": "balanced", "music": {"mode": "attached", "path": str(tmp_path / "nothing.wav")}}):
        assert app_mg._sync_rhythm(tmp_path, record, plan, audio)[:2] == (plan, audio)


def test_the_rhythm_directive_is_understood():
    from creative import directives
    assert directives.parse("Rhythm: music first")[1].rhythm == "music_first"
    assert directives.parse("ریتم: متعادل")[1].rhythm == "balanced"
    assert directives.parse("Rhythm: jazz")[1].notes
