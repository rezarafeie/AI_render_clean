"""Music is fitted to the film by trimming and looping on the grid; the track's drop lands on the film's accent. Checked on rendered audio, not on the plan."""
import shutil

import numpy as np
import pytest

from creative.audio import music_fit, rhythm
from tests.audio_fixtures import song

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")


@pytest.fixture(scope="module")
def track(tmp_path_factory):
    folder = tmp_path_factory.mktemp("fit")
    truth = song(folder / "demo.wav", seconds=24.0)
    return folder, truth, rhythm.analyse(folder / "demo.wav", cache_dir=folder)


def test_the_drop_lands_on_the_films_accent_in_the_rendered_audio(track, tmp_path):
    folder, truth, analysis = track
    fit = music_fit.plan(analysis, film_s=12.0, accent_s=6.0)
    assert fit["anchor"]["kind"] == "drop" and abs(fit["offset_s"] - (analysis["drops_ms"][0] / 1000 - 6.0)) < 0.01
    out = music_fit.render(folder / "demo.wav", tmp_path / "fit.wav", 12.0, fit, analysis)
    assert abs(music_fit._duration(out) - 12.0) < 0.05
    again = rhythm.analyse(out)
    assert any(abs(d - 6000) <= 800 for d in again["drops_ms"]), (again["drops_ms"], fit)      # measured on the output file
    timing = music_fit.film_timing(analysis, fit, 12.0)
    assert any(abs(d - 6000) <= 100 for d in timing["drops_ms"]) and timing["offset_ms"] == int(round(fit["offset_s"] * 1000))


def test_a_drop_that_would_have_to_come_before_the_track_starts_is_reported_not_forced(track):
    _, truth, analysis = track
    fit = music_fit.plan(analysis, film_s=20.0, accent_s=15.0)           # the track's drop is at 8 s: it cannot be moved later than the track allows
    assert fit["offset_s"] == 0.0 and fit["anchor"] is None and any("could not be placed" in n for n in fit["notes"])


def test_a_short_track_is_looped_on_bar_lines_without_a_gap_or_a_drift(track, tmp_path):
    folder, truth, analysis = track
    fit = music_fit.plan(analysis, film_s=50.0, accent_s=None)
    assert fit["loop"] is True
    out = music_fit.render(folder / "demo.wav", tmp_path / "loop.wav", 50.0, fit, analysis)
    assert abs(music_fit._duration(out) - 50.0) < 0.05
    samples = rhythm.decode(out)
    per_second = np.array([np.sqrt(np.mean(samples[i * rhythm.SR:(i + 1) * rhythm.SR] ** 2)) for i in range(48)])
    assert per_second[10:48].min() > 0.25 * per_second[10:48].mean()            # no silent hole at a join (the first seconds are the quiet intro)
    again = rhythm.analyse(out)
    assert abs(again["bpm"] - 120) <= 2 and again["beat_confidence"] > 0.3
    beats = np.array([b for b in again["beats_ms"] if b > 12000])
    grid_error = np.abs((beats - beats[0] + 250) % 500 - 250)                   # distance of every later beat from one regular grid anchored on the first
    assert np.median(grid_error) <= 60 and np.mean(grid_error <= 90) >= 0.8, "the join moved the beat"


def test_without_analysis_or_accent_the_music_starts_at_its_beginning(track):
    _, _, analysis = track
    assert music_fit.plan(None, 10.0, 5.0)["offset_s"] == 0.0
    assert music_fit.plan(analysis, 10.0, None)["offset_s"] == 0.0


def test_beats_continue_on_the_grid_when_the_track_loops(track):
    _, _, analysis = track
    fit = music_fit.plan(analysis, film_s=50.0)
    timing = music_fit.film_timing(analysis, fit, 50.0)
    assert timing["beats_ms"][-1] > 45000 and timing["loop"] is True


def test_the_solver_puts_more_cuts_on_beats_when_the_drop_leaves_room_and_keeps_the_drop_on_the_reveal(tmp_path):
    truth = song(tmp_path / "long.wav", seconds=40.0, intro=10.0, build=14.0)             # the drop is at 24 s
    analysis = rhythm.analyse(tmp_path / "long.wav")
    starts = [0.0, 4.6, 9.3, 13.0, 16.4]
    plain = music_fit.solve(analysis, starts, 22.0, snap=False, tolerance_s=0.35, max_total_s=90)
    synced = music_fit.solve(analysis, starts, 22.0, snap=True, tolerance_s=0.35, max_total_s=90)
    assert plain["moved"] is False and plain["starts"] == starts
    assert synced["moved"] and synced["aligned"] > plain["aligned"] and synced["aligned"] >= 3, (plain["aligned"], synced)
    assert all(b >= a - 1e-9 for a, b in zip(starts, synced["starts"])) and all(y > x for x, y in zip(synced["starts"], synced["starts"][1:]))      # nothing moved earlier
    assert abs(synced["fit"]["anchor"]["film_ms"] / 1000 - synced["starts"][-1]) < 0.02 and synced["fit"]["offset_s"] >= 0       # the drop still meets the (moved) reveal
    assert synced["total"] - 22.0 <= 1.5


def test_the_solver_never_delays_a_scene_past_the_point_the_drop_can_reach(tmp_path):
    song(tmp_path / "tight.wav", seconds=30.0, intro=8.0, build=9.0)                      # drop at 17 s, reveal at 16.4: 0.3 s of room
    analysis = rhythm.analyse(tmp_path / "tight.wav")
    solved = music_fit.solve(analysis, [0.0, 4.6, 9.3, 13.0, 16.4], 22.0, snap=True, tolerance_s=0.35, max_total_s=90)
    assert solved["fit"]["anchor"] is not None and solved["starts"][-1] - 16.4 <= analysis["drops_ms"][0] / 1000 - 16.4 + 1e-6


def test_a_drop_earlier_than_the_reveal_is_reached_by_lengthening_the_build_up(tmp_path):
    from creative.audio import rhythm
    path = tmp_path / "early.wav"
    truth = song(path, bpm=120.0, seconds=30.0, intro=4.0, build=4.0)        # drop at 8 s
    analysis = rhythm.analyse(path, cache_dir=tmp_path)
    assert music_fit.plan(analysis, film_s=40.0, accent_s=20.0)["anchor"] is None        # as before: it cannot start earlier
    ext = music_fit.extend_buildup(path, analysis, 20.0, tmp_path / "ext")
    assert ext and ext["repeats"] >= 1 and ext["drop_ms"] / 1000 >= 20.0 - 0.05
    longer = rhythm.analyse(ext["path"], cache_dir=tmp_path)
    assert any(abs(d - ext["drop_ms"]) <= 400 for d in longer["drops_ms"]), (longer["drops_ms"], ext)        # measured on the new file
    fit = music_fit.plan(longer, film_s=40.0, accent_s=20.0)
    assert fit["anchor"] and fit["anchor"]["kind"] == "drop" and 0 <= fit["offset_s"] < 4.5
    out = music_fit.render(ext["path"], tmp_path / "bed.wav", 40.0, fit, longer)
    again = rhythm.analyse(out, cache_dir=tmp_path)
    assert any(abs(d - 20000) <= 800 for d in again["drops_ms"]), again["drops_ms"]       # the drop sits on the reveal in the rendered audio
    assert music_fit.extend_buildup(path, analysis, 6.0, tmp_path / "ext") is None       # a reveal before the drop: nothing to lengthen
