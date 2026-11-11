"""The music pipeline end to end on real audio: a synthetic song and synthetic narration go through the film's own audio steps and the RESULT is measured
(drop on the accent, beat on the cuts, ducking under speech, loudness and peak, sound effects, a fading end), not the plan."""
import json
import shutil
import subprocess

import numpy as np
import pytest

from app import motion_graphic as app_mg
from creative import motion_graphic as mg
from creative.audio import loudness, music_director as md, music_fit, rhythm
from tests.audio_fixtures import SR, song, speech_like

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")

FILM = 22.0
STARTS = [0.0, 4.6, 9.3, 13.0, 16.4]            # scene starts (the narration fixes them); the last is the film's reveal
SPEECH = [(0.4, 4.0), (5.0, 8.7), (9.7, 12.4), (13.4, 15.8)]    # where the voice speaks; nothing is spoken over the reveal's first second at 16.4


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    folder = tmp_path_factory.mktemp("film")
    truth = song(folder / "song.wav", seconds=40.0, intro=10.0, build=14.0)         # the drop is at 24.0 s of the track: the film can move its reveal later to meet more beats
    clips = []
    for index, (a, b) in enumerate(SPEECH):
        path = folder / f"v{index}.wav"
        speech_like(path, [(0.0, b - a)], seconds=b - a)
        clips.append({"path": str(path), "start": a, "duration": b - a, "role": "voice"})
    scenes = [mg.ScenePlan(headline=f"s{i}", idea="i", start=s, end=(STARTS[i + 1] if i + 1 < len(STARTS) else FILM)) for i, s in enumerate(STARTS)]
    plan = mg.MotionPlan(title="t", duration=FILM, scenes=scenes)
    return folder, truth, clips, plan


@pytest.fixture()
def film(world, tmp_path, monkeypatch):
    folder, truth, clips, plan = world
    monkeypatch.setenv("MUSIC_STORE", str(tmp_path / "store"))
    work = tmp_path / "work"
    work.mkdir()
    record = {"id": "x", "conversation_id": "c", "user_key": "u", "request": "energetic promo", "rhythm": "balanced", "loudness": "social_video", "sfx": "dynamic",
              "audio_plan": {"music_energy": 0.8, "sound_design": "dynamic", "music_mood": "energetic"},
              "music": {"mode": "attached", "path": str(folder / "song.wav"), "name": "song.wav", "sync": True, "cost": "free", "instrumental": True, "variant": 0}}
    return work, record, clips, plan, truth, folder


def run_audio(work, record, clips, plan):
    plan, audio, rhythm_notes = app_mg._sync_rhythm(work, record, plan, list(clips))
    audio, music_notes = app_mg._add_music(work, record, plan, audio)
    audio, sfx_notes = app_mg._add_sfx(work, record, plan, audio)
    plan = app_mg._attach_beats(work, record, plan)
    audio, master_notes = app_mg._master_audio(work, record, plan, audio)
    return plan, audio, [*rhythm_notes, *music_notes, *sfx_notes, *master_notes]


def rms(path, start, end):
    samples = rhythm.decode(path)
    chunk = samples[int(start * rhythm.SR):int(end * rhythm.SR)]
    return float(np.sqrt(np.mean(chunk ** 2))) if len(chunk) else 0.0


def db(a, b):
    return 20 * np.log10(max(a, 1e-9) / max(b, 1e-9))


def test_the_rendered_audio_meets_the_cuts_the_accent_and_the_delivery_standard(film):
    work, record, clips, plan, truth, folder = film
    final, audio, notes = run_audio(work, record, clips, plan)
    fit = json.loads((work / "music_fit.json").read_text())
    starts = [sc.start for sc in final.scenes]
    reveal = starts[-1]

    # 1. the drop of the track lands on the film's reveal, measured on the fitted track itself
    assert fit["anchor"]["kind"] == "drop" and abs(fit["anchor"]["film_ms"] / 1000 - reveal) < 0.06
    fitted = rhythm.analyse(work / "music_fitted.wav")
    assert any(abs(d / 1000 - reveal) <= 0.8 for d in fitted["drops_ms"]), (fitted["drops_ms"], reveal)

    # 2. the film kept every word: speech clips only moved with their own scene, never overlapped, and the total grew by at most the waiting for beats
    assert final.duration - plan.duration <= 3.0 and all(b["start"] >= a["start"] + a["duration"] - 1e-6 for a, b in zip(audio[:3], audio[1:4]) if a.get("role") == "voice" and b.get("role") == "voice")

    # 3. the beat grid of the music that is really in the film meets the cuts better than the same music started at its beginning
    bed = next(c for c in audio if c.get("role") == "master")                       # the final track
    unsynced = music_fit.aligned(rhythm.analyse(folder / "song.wav"), STARTS, 0.0)
    synced = music_fit.aligned(rhythm.analyse(work / "music_fitted.wav"), starts, 0.0, tolerance_ms=90)
    assert synced >= max(3, unsynced), (synced, unsynced, starts)

    # 4. delivery loudness and peak
    measured = loudness.measure(work / "master.m4a")
    assert abs(measured["integrated_lufs"] - (-14.0)) <= 1.5 and measured["true_peak_dbtp"] <= -1.0, measured
    assert abs(music_fit._duration(work / "master.m4a") - final.duration) <= 0.1

    # 5. the music ducks under the narration (the bed, before mastering), by a clear margin, and the voice stays clearly above it
    bed_file = work / "music_bed.m4a"
    speaking = [(c["start"] + 0.5, c["start"] + c["duration"] - 0.3) for c in clips if c["start"] + c["duration"] < reveal - 0.2]
    gaps = [(a[1] + 0.5, b[0] - 0.3) for a, b in zip(speaking, speaking[1:]) if b[0] - a[1] > 1.2]
    under = np.mean([rms(bed_file, a, b) for a, b in speaking])
    clear = np.mean([rms(bed_file, a, b) for a, b in gaps]) if gaps else None
    voice_level = np.mean([rms(clip["path"], 0.5, clip["duration"] - 0.3) for clip in clips])
    assert db(voice_level, under) >= 3.0, db(voice_level, under)                # speech clearly above the music
    if clear:
        assert db(clear, under) >= 4.0, (db(clear, under), "ducking depth")     # music is audibly lower while someone speaks than between lines

    # 6. no abrupt ending: the last half second is far quieter than the film's body
    body = rms(work / "master.m4a", 6.0, 12.0)
    assert rms(work / "master.m4a", final.duration - 0.4, final.duration - 0.05) < 0.35 * body


def test_sound_effects_have_a_purpose_sit_on_the_reveal_and_never_cover_a_word(film):
    work, record, clips, plan, truth, folder = film
    final, audio, notes = run_audio(work, record, clips, plan)
    cues = json.loads((work / "sfx_cues.json").read_text())
    ready = [c for c in cues if c["status"] == "ready"]
    assert ready and all("synthesised" in c["license"] for c in ready)
    reveal_ms = final.scenes[-1].start * 1000
    assert any(c["purpose"] == "reveal" and abs(c["time_ms"] - reveal_ms) <= 150 for c in ready), (ready, reveal_ms)
    track = work / "sfx_track.wav"
    for cue in ready:
        t = cue["time_ms"] / 1000
        assert rms(track, t, t + 0.25) > 4 * max(rms(track, max(0, t - 0.6), max(0.01, t - 0.1)), 1e-4), cue                # a sound really starts there
    words = [(c["start"], c["start"] + c["duration"]) for c in clips]
    for cue in ready:
        if cue["purpose"] != "reveal":
            assert not any(a + 0.15 < cue["time_ms"] / 1000 < b - 0.15 for a, b in words), ("a minor effect over speech", cue)
    assert len(ready) <= 1 + int(FILM / 10) * 4


def test_each_scene_designer_is_told_the_real_beats_and_accent_on_its_own_clock(film):
    work, record, clips, plan, truth, folder = film
    final, audio, notes = run_audio(work, record, clips, plan)
    timing = json.loads((work / "music_timing.json").read_text())["timing"]
    assert timing["bpm"] and abs(timing["bpm"] - 120) <= 2
    last = final.scenes[-1]
    assert last.accent is not None and abs(last.accent) <= 0.1, last.accent                  # the drop is the start of the last scene
    assert all(sc.beats for sc in final.scenes[:-1]) and final.scenes[0].beat_s > 0
    for sc in final.scenes:
        assert all(0 <= b < sc.end - sc.start for b in sc.beats)
    prompt = mg.scene_request(final, len(final.scenes), "brief")
    assert "MUSIC OF THIS FILM" in prompt and "biggest accent" in prompt and "narration cue" in prompt
    assert "MUSIC OF THIS FILM" not in mg.scene_request(plan, 1, "brief")                   # no music: the prompt is exactly what it was


def test_without_sync_the_film_is_untouched_by_the_rhythm_but_still_gets_its_music(film):
    work, record, clips, plan, truth, folder = film
    record["music"]["sync"] = False
    record["rhythm"] = "speech_first"
    final, audio, notes = run_audio(work, record, clips, plan)
    assert [sc.start for sc in final.scenes] == STARTS and final.duration == FILM
    assert not (work / "music_fit.json").exists() and all(not sc.beats and sc.accent is None for sc in final.scenes)
    assert any(c.get("role") == "master" for c in audio) and (work / "music_bed.m4a").exists()


def test_a_track_shorter_than_the_film_loops_without_a_hole_and_still_ends_softly(film, tmp_path):
    work, record, clips, plan, truth, folder = film
    short = tmp_path / "short.wav"
    song(short, seconds=12.0, intro=1.0, build=2.0)
    record["music"].update(path=str(short), name="short.wav")
    final, audio, notes = run_audio(work, record, clips, plan)
    fit = json.loads((work / "music_fit.json").read_text())
    assert fit["loop"] is True and abs(music_fit._duration(work / "music_fitted.wav") - final.duration) <= 0.1
    per_second = [rms(work / "music_fitted.wav", i, i + 1) for i in range(4, int(final.duration) - 1)]
    assert min(per_second) > 0.2 * np.mean(per_second), per_second


def test_music_that_cannot_be_found_is_reported_and_the_film_still_has_its_narration(film, monkeypatch):
    work, record, clips, plan, truth, folder = film
    record["music"] = {"mode": "auto", "words": "calm piano", "sync": True, "cost": "free", "instrumental": True, "variant": 0}
    monkeypatch.setattr(md, "library_tracks", lambda: [])
    final, audio, notes = run_audio(work, record, clips, plan)
    assert any(c.get("role") == "master" for c in audio) and not (work / "music_bed.m4a").exists()
    assert any("موسیقی" in n for n in notes)


def test_auto_music_reuses_a_library_track_before_generating_anything(film, monkeypatch):
    work, record, clips, plan, truth, folder = film
    record["music"] = {"mode": "auto", "words": "energetic electronic", "sync": True, "cost": "balanced", "instrumental": True, "variant": 0}
    track = {"path": str(folder / "song.wav"), "filename": "energetic electronic drop", "tags": ["energetic", "electronic", "drop"], "mood": "energetic", "duration_sec": 40.0, "source": "library"}
    monkeypatch.setattr(md, "library_tracks", lambda: [track])
    from creative.audio import music_providers as mp
    monkeypatch.setattr(mp, "generate", lambda *a, **k: (_ for _ in ()).throw(AssertionError("generated although the library had a fit")))
    final, audio, notes = run_audio(work, record, clips, plan)
    chosen = json.loads((work / "music_choice.json").read_text())
    assert chosen["source"] == "library" and chosen["label"] == "energetic electronic drop"
    assert any(c.get("role") == "master" for c in audio)


def test_a_track_whose_drop_comes_before_the_reveal_gets_a_longer_build_up_and_the_drop_lands_on_the_reveal(film, tmp_path):
    work, record, clips, plan, truth, folder = film
    early = tmp_path / "early.wav"
    song(early, seconds=40.0, intro=4.0, build=4.0)                       # the drop is at 8 s; the film's reveal is at 16.4 s
    record["music"] = {**record["music"], "path": str(early), "name": "early.wav"}
    plan2, audio, notes = run_audio(work, record, clips, plan)
    fit = json.loads((work / "music_fit.json").read_text())
    assert fit["anchor"] and fit["anchor"]["kind"] == "drop", (fit, notes)
    assert any("بیلدآپ" in n for n in notes), notes
    reveal_ms = int(round(plan2.scenes[-1].start * 1000))
    timing = json.loads((work / "music_timing.json").read_text())["timing"]
    assert any(abs(d - reveal_ms) <= 150 for d in timing["drops_ms"]), (timing["drops_ms"], reveal_ms)        # the drop of the lengthened track sits on the reveal, on the film's clock
    assert abs(fit["anchor"]["film_ms"] - reveal_ms) <= 150
