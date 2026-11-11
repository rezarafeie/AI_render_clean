"""The style-pack talking reel (talking_5) gets the music director too: the person's choice stays theirs, the studio's default is replaced by a fitted pick."""
import subprocess
from types import SimpleNamespace

import pytest

from app import talking_reel as tr
from creative import style_packs
from creative.audio import film_music, music_director as md


@pytest.fixture
def parts(tmp_path, monkeypatch):
    track = tmp_path / "pick.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=220:d=12", str(track)], check=True)
    seen = {}
    monkeypatch.setattr(film_music, "choose", lambda directory, request, progress=None: (seen.update(request=request) or md.Result(path=track, label="picked", source="library")))
    monkeypatch.setattr(film_music, "fit", lambda directory, choice, starts, total, accent, notes: (seen.update(starts=starts, accent=accent) or (track, None, None)))
    job = tmp_path / "job"
    job.mkdir()
    tr.save(job, {"status": "x"})
    plan = SimpleNamespace(duration=30.0, script={"segments": [{"start": 0.0}, {"start": 2.1}, {"start": 4.0}]})
    return SimpleNamespace(job=job, plan=plan, pack=style_packs.get("ref-ai-news"), seen=seen, track=track)


def test_the_studios_default_music_is_replaced_by_the_directors_pick_fitted_to_the_cuts(parts):
    state = {"music": tr.DEFAULT_MUSIC, "hook": "هوک", "title": "عنوان"}
    got = tr._style5_music(parts.job, state, parts.plan, parts.pack, {"chosen": {"name": "n", "pacing": "fast"}}, {"text": "متن"})
    request = parts.seen["request"]
    assert got == parts.track and request.mode == "auto" and request.cost == "free" and request.accent_s is None and request.energy == 0.75
    assert parts.seen["starts"] == [0.0, 2.1, 4.0] and parts.seen["accent"] is None
    assert tr.load(parts.job)["music_notes"][0].startswith("موسیقی")


def test_a_track_the_person_chose_stays_theirs_and_no_music_stays_silent(parts, monkeypatch):
    mine = tr.music_library()[0]["path"] if tr.music_library() else None
    if mine:
        got = tr._style5_music(parts.job, {"music": mine, "music_chosen": True}, parts.plan, parts.pack, None, {})
        assert parts.seen["request"].mode == "attached" and got == parts.track
    parts.seen.clear()
    assert tr._style5_music(parts.job, {"music": None}, parts.plan, parts.pack, None, {}) is None and "request" not in parts.seen


def test_the_flag_keeps_the_old_behaviour(parts, monkeypatch):
    monkeypatch.setenv("FILM_MUSIC_DIRECTOR", "0")
    got = tr._style5_music(parts.job, {"music": tr.DEFAULT_MUSIC}, parts.plan, parts.pack, None, {})
    assert "request" not in parts.seen and got == tr.resolve_music(tr.DEFAULT_MUSIC)
