"""A stopped or failed Claude-motion build continues from what it already made (plan, then code) when the person presses retry."""
import json

import pytest

from creative import claude_motion as cm


def hooks():
    return cm.Hooks(note=lambda *a, **k: None, progress=lambda *a, **k: None, cancelled=lambda: False)


def direction():
    return cm.Direction(title="فیلم آزمایشی", look="flat", beats=[cm.Beat(line="جملهٔ اول", plan="p1"), cm.Beat(line="جملهٔ دوم", plan="p2")])


TIMELINE = {"fps": 30, "width": 1080, "height": 1920, "total": 6.0, "audio": [],
            "scenes": [{"id": "01", "text": "جملهٔ اول", "start": 0.0, "dur": 2.5, "al": {"chars": "جملهٔ اول", "starts": [0.0] * 9}},
                       {"id": "02", "text": "جملهٔ دوم", "start": 2.6, "dur": 2.5, "al": {"chars": "جملهٔ دوم", "starts": [0.0] * 9}}]}


class Stop(Exception):
    pass


def never(name):
    def fail(*a, **k):
        raise AssertionError(f"{name} must not run again")
    return fail


def record():
    return {"request": "یک فیلم بساز", "style": "", "context": "", "answers": []}


def test_retry_after_the_plan_does_not_ask_the_director_again(tmp_path, monkeypatch):
    monkeypatch.setattr(cm, "direct", lambda *a, **k: direction())
    monkeypatch.setattr(cm, "polish_speech", lambda lines: list(lines))
    monkeypatch.setattr(cm, "voice_timeline", lambda *a, **k: (_ for _ in ()).throw(Stop("voice down")))
    with pytest.raises(Stop):
        cm.build(tmp_path, record(), hooks())
    assert json.loads((tmp_path / "checkpoint.json").read_text())["direction"]["title"] == "فیلم آزمایشی"

    monkeypatch.setattr(cm, "direct", never("direct"))
    monkeypatch.setattr(cm, "voice_timeline", lambda *a, **k: TIMELINE)
    monkeypatch.setattr(cm, "write", lambda *a, **k: (_ for _ in ()).throw(Stop("code stops here")))
    with pytest.raises(Stop, match="code stops here"):
        cm.build(tmp_path, record(), hooks())


def test_retry_after_the_code_does_not_write_it_again(tmp_path, monkeypatch):
    film = cm.Film(art="export const A = () => null;", blocks={"01": "const S01: React.FC = () => null;\nconst S02: React.FC = () => null;"})
    monkeypatch.setattr(cm, "direct", lambda *a, **k: direction())
    monkeypatch.setattr(cm, "polish_speech", lambda lines: list(lines))
    monkeypatch.setattr(cm, "voice_timeline", lambda *a, **k: TIMELINE)
    monkeypatch.setattr(cm, "write", lambda *a, **k: film)
    monkeypatch.setattr(cm, "project", lambda *a, **k: (_ for _ in ()).throw(Stop("build stops")))
    with pytest.raises(Stop, match="build stops"):
        cm.build(tmp_path, record(), hooks())
    saved = json.loads((tmp_path / "checkpoint.json").read_text())
    assert saved["final"] and saved["film"]["art"] == film.art

    seen = {}
    monkeypatch.setattr(cm, "direct", never("direct"))
    monkeypatch.setattr(cm, "polish_speech", never("polish_speech"))
    monkeypatch.setattr(cm, "write", never("write"))
    monkeypatch.setattr(cm, "project", lambda work, d, t, code: (seen.setdefault("art", code.art_tsx), (_ for _ in ()).throw(Stop("build stops again")))[1])
    with pytest.raises(Stop, match="build stops again"):
        cm.build(tmp_path, record(), hooks())
    assert seen["art"] == film.art


def test_a_changed_request_starts_over(tmp_path, monkeypatch):
    monkeypatch.setattr(cm, "direct", lambda *a, **k: direction())
    monkeypatch.setattr(cm, "polish_speech", lambda lines: list(lines))
    monkeypatch.setattr(cm, "voice_timeline", lambda *a, **k: (_ for _ in ()).throw(Stop("voice down")))
    with pytest.raises(Stop):
        cm.build(tmp_path, record(), hooks())
    asked = []
    monkeypatch.setattr(cm, "direct", lambda *a, **k: (asked.append(1), direction())[1])
    other = {**record(), "request": "یک فیلم دیگر بساز"}
    with pytest.raises(Stop):
        cm.build(tmp_path, other, hooks())
    assert asked, "a different request must not reuse the old plan"
