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


def test_a_finished_build_whose_render_failed_is_rendered_again_not_rebuilt(tmp_path, monkeypatch):
    film = cm.Film(art="export const A = () => null;", blocks={"01": "const S01: React.FC = () => null;\nconst S02: React.FC = () => null;"})
    (tmp_path / "claude_motion.json").write_text(json.dumps({"direction": direction().model_dump(), "film": film.model_dump()}))
    seen = {}
    monkeypatch.setattr(cm, "direct", never("direct"))
    monkeypatch.setattr(cm, "polish_speech", never("polish_speech"))
    monkeypatch.setattr(cm, "write", never("write"))
    monkeypatch.setattr(cm, "voice_timeline", lambda *a, **k: TIMELINE)
    monkeypatch.setattr(cm, "project", lambda work, d, t, code: (seen.setdefault("art", code.art_tsx), (_ for _ in ()).throw(Stop("build stops")))[1])
    with pytest.raises(Stop, match="build stops"):
        cm.build(tmp_path, record(), hooks())
    assert seen["art"] == film.art


def test_a_call_cut_off_after_minutes_is_split_at_once_not_repeated(monkeypatch):
    clock = {"t": 0.0}
    calls = []

    def slow_then_cut(guide, user, tokens=0):
        calls.append(1)
        clock["t"] += 246.0                      # the provider cut the stream after ~246 s
        raise RuntimeError("provider reported a stream error")

    monkeypatch.setattr(cm, "ask_text", slow_then_cut)
    monkeypatch.setattr(cm.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(cm.time, "sleep", lambda s: None)
    result = cm._one_ask("g", "u", 16000, split=lambda: "split-result", tries=3)
    assert result == "split-result" and len(calls) == 1


def test_a_fast_transient_failure_is_still_retried(monkeypatch):
    calls = []

    def flaky(guide, user, tokens=0):
        calls.append(1)
        if len(calls) < 2:
            raise RuntimeError("502 Upstream AI gateway is unavailable")
        return "ok"

    monkeypatch.setattr(cm, "ask_text", flaky)
    monkeypatch.setattr(cm.time, "sleep", lambda s: None)
    assert cm._one_ask("g", "u", 16000, split=lambda: "split-result", tries=3) == "ok" and len(calls) == 2


def test_a_component_defined_twice_keeps_the_first_definition():
    body = (
        "export const Svg = () => null;\n\n"
        "export const Matchi: React.FC<{p?: number}> = ({p = 0}) => {\n  return <g>{p}</g>;\n};\n\n"
        "const {a, b} = helpers;\n"
        "export function Loupe() {\n  return null;\n}\n\n"
        "export const Matchi: React.FC = () => {\n  return <g>second</g>;\n};\n\n"
        "export const Stopwatch = () => <g/>;\n"
    )
    fixed, dropped = cm.dedupe_art(body)
    assert dropped == ["Matchi"]
    assert fixed.count("export const Matchi") == 1 and "second" not in fixed and "{p}" in fixed
    for kept in ("export const Svg", "export function Loupe", "const {a, b} = helpers;", "export const Stopwatch"):
        assert kept in fixed


def test_distinct_components_are_left_alone():
    body = "export const A = () => null;\nexport const B = () => null;\n"
    assert cm.dedupe_art(body) == (body, [])


def test_a_saved_film_with_a_duplicate_name_builds_with_it_defined_once():
    art = "export const Matchi = () => <g>one</g>;\n\nexport const Matchi = () => <g>two</g>;\n"
    film = cm.Film(art=art, blocks={"01": "const S01: React.FC = () => null;\nconst S02: React.FC = () => null;"})
    code = film.code(TIMELINE)
    assert code.art_tsx.count("export const Matchi") == 1 and "two" not in code.art_tsx


def test_a_voice_only_request_is_recognised():
    assert cm.voice_only_change("صدا را خانم کن")
    assert cm.voice_only_change("فقط صدای نریشن را با صدای خانم بساز.")
    assert not cm.voice_only_change("رنگ پس‌زمینه را سبز کن")
    assert not cm.voice_only_change("صدا را خانم کن و تصویر صحنه ۳ را عوض کن")
    assert not cm.voice_only_change("")


def test_a_voice_only_change_keeps_the_films_code(tmp_path, monkeypatch):
    film = cm.Film(art="export const A = () => null;", blocks={"01": "const S01: React.FC = () => null;\nconst S02: React.FC = () => null;"})
    (tmp_path / "claude_motion.json").write_text(json.dumps({"direction": direction().model_dump(), "film": film.model_dump()}))
    seen = {}
    monkeypatch.setattr(cm, "direct", never("direct"))
    monkeypatch.setattr(cm, "polish_speech", never("polish_speech"))
    monkeypatch.setattr(cm, "write", never("write"))
    monkeypatch.setattr(cm, "voice_timeline", lambda *a, **k: (seen.setdefault("voiced", True), TIMELINE)[1])
    monkeypatch.setattr(cm, "project", lambda work, d, t, code: (seen.setdefault("art", code.art_tsx), (_ for _ in ()).throw(Stop("build stops")))[1])
    with pytest.raises(Stop, match="build stops"):
        cm.build(tmp_path, record(), hooks(), change="صدا را خانم کن")
    assert seen["voiced"] and seen["art"] == film.art
