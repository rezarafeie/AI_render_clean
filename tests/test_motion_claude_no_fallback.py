"""A Claude-motion film whose code is already written stays on the Claude engine when only the render fails; before that it may fall back."""
import json

import pytest

from app import motion_graphic as mg


class Boom(RuntimeError):
    pass


def make(tmp_path, monkeypatch, engine="claude"):
    d = tmp_path / "m1"
    d.mkdir()
    record = {"id": "m1", "status": "queued", "engine": engine, "conversation_id": "c", "user_key": "u", "request": "x", "log": []}
    monkeypatch.setattr(mg, "load", lambda directory: dict(record))
    monkeypatch.setattr(mg, "save", lambda directory, rec: rec)
    monkeypatch.setattr(mg, "_note", lambda *a, **k: None)
    monkeypatch.setattr(mg, "_cancelled", lambda key: False)
    return d


def test_render_failure_after_the_film_was_built_does_not_fall_back(tmp_path, monkeypatch):
    d = make(tmp_path, monkeypatch)
    (d / "claude_motion.json").write_text(json.dumps({"direction": {}, "film": {}}))
    monkeypatch.setattr(mg, "_run_claude", lambda *a, **k: (_ for _ in ()).throw(Boom("cloud render failed after 3 tries")))
    with pytest.raises(Boom):
        mg._run(d, "")


def test_a_film_whose_code_never_built_may_still_fall_back(tmp_path, monkeypatch):
    d = make(tmp_path, monkeypatch)
    (d / "claude_motion.json").write_text(json.dumps({"direction": {}, "film": {}}))
    monkeypatch.setattr(mg, "_run_claude", lambda *a, **k: (_ for _ in ()).throw(Boom("the film's code did not build after four attempts: x")))
    switched = []
    monkeypatch.setattr(mg, "_note", lambda directory, key, *a, **k: switched.append(key))
    with pytest.raises(Exception) as caught:
        mg._run(d, "")
    assert "engine-switch" in switched and not isinstance(caught.value, Boom)


def test_a_failure_before_the_code_exists_may_fall_back(tmp_path, monkeypatch):
    d = make(tmp_path, monkeypatch)
    monkeypatch.setattr(mg, "_run_claude", lambda *a, **k: (_ for _ in ()).throw(Boom("provider down")))
    switched = []
    monkeypatch.setattr(mg, "_note", lambda directory, key, *a, **k: switched.append(key))
    with pytest.raises(Exception) as caught:
        mg._run(d, "")
    assert "engine-switch" in switched and not isinstance(caught.value, Boom)


def test_render_errors_get_a_clear_persian_message():
    assert "ذخیره شده" in mg._public_error(RuntimeError("Cloud render failed; resource cleanup is tracked separately"))
