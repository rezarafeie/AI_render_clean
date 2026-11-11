"""The art-director pass: weak scenes are redesigned from the critic's fixes, and only a redesign the same eye scores higher replaces the original."""
from pathlib import Path

import pytest
from PIL import Image

from creative import design_critic as dc


@pytest.fixture
def stills(tmp_path):
    out = {}
    for n in (1, 2, 3, 4):
        path = tmp_path / f"{n}.jpg"
        Image.new("RGB", (270, 480), (n * 40, 60, 90)).save(path)
        out[n] = path
    return out


def _ask(scores_by_call):
    calls = []

    def ask(rubric, context, sheet):
        calls.append(sheet)
        scores = scores_by_call[min(len(calls) - 1, len(scores_by_call) - 1)]
        return {"scenes": [{"scene": n, "score": s, "problems": [f"problem {n}"], "fix": f"fix {n}"} for n, s in scores.items()]}
    ask.calls = calls
    return ask


def _loop(stills, tmp_path, scores_by_call, protected=frozenset(), rebuild_ok=True, replaceable=frozenset()):
    drafts = {n: f"old{n}" for n in stills}
    log, notes, built = {"authored": [], "rebuilt": 0, "restored": 0}, [], {"n": 0}

    def author(n, feedback):
        log["authored"].append((n, feedback))
        return f"new{n}"

    def rebuild():
        log["rebuilt"] += 1
        return rebuild_ok

    def restore(before):
        log["restored"] += 1
        drafts.clear(); drafts.update(before)
    result = dc.refine(drafts=drafts, headlines={n: f"h{n}" for n in stills}, protected=set(protected), stills=lambda: stills, author=author, rebuild=rebuild, restore=restore,
                       work=tmp_path / "w", note=notes.append, ask=_ask(scores_by_call), replaceable=set(replaceable))
    return result, drafts, log, notes


def test_a_film_the_critic_likes_is_left_alone(stills, tmp_path):
    result, drafts, log, notes = _loop(stills, tmp_path, [{1: 8, 2: 7, 3: 9, 4: 6}])
    assert not log["authored"] and not result["changed"] and drafts == {n: f"old{n}" for n in stills}


def test_the_weakest_scenes_are_redesigned_from_the_fix_and_kept_only_when_they_score_higher(stills, tmp_path):
    result, drafts, log, notes = _loop(stills, tmp_path, [{1: 8, 2: 3, 3: 5, 4: 4}, {2: 7, 3: 5, 4: 6}])
    assert [n for n, _ in log["authored"]] == [2, 4, 3]                                          # weakest first
    assert any("FIX: fix 2" in line for line in log["authored"][0][1])
    assert result["kept"] == [2, 4] and drafts[2] == "new2" and drafts[4] == "new4" and drafts[3] == "old3"      # scene 3 did not improve: back to the original
    assert result["before"][2] == 3 and result["after"][2] == 7


def test_protected_scenes_ready_made_components_are_never_redesigned(stills, tmp_path):
    result, drafts, log, notes = _loop(stills, tmp_path, [{1: 2, 2: 2, 3: 9, 4: 9}, {2: 8}], protected={1})
    assert [n for n, _ in log["authored"]] == [2]


def test_a_redesign_that_fails_the_browser_check_leaves_the_original_page(stills, tmp_path):
    result, drafts, log, notes = _loop(stills, tmp_path, [{1: 2, 2: 9, 3: 9, 4: 9}], rebuild_ok=False)
    assert drafts[1] == "old1" and log["restored"] == 1 and result["changed"] == []


def test_an_unavailable_critic_changes_nothing(stills, tmp_path):
    def broken(rubric, context, sheet):
        raise RuntimeError("no vision route")
    drafts = {n: "old" for n in stills}
    result = dc.refine(drafts=drafts, headlines={}, protected=set(), stills=lambda: stills, author=lambda n, f: "new", rebuild=lambda: True, restore=lambda b: None,
                       work=tmp_path / "w", ask=broken)
    assert result["before"] == {} and set(drafts.values()) == {"old"}


def test_the_contact_sheet_numbers_every_tile_and_the_flag_turns_it_off(stills, tmp_path, monkeypatch):
    sheet = dc._sheet(stills, {}, tmp_path / "s.jpg")
    assert Image.open(sheet).size[0] >= 3 * 300
    monkeypatch.setenv("DESIGN_CRITIC", "0")
    assert not dc.enabled()
    monkeypatch.delenv("DESIGN_CRITIC")
    assert dc.enabled()


def test_a_poor_ready_made_component_is_replaced_but_a_fair_one_is_left_alone(stills, tmp_path):
    result, drafts, log, notes = _loop(stills, tmp_path, [{1: 3, 2: 5, 3: 9, 4: 9}, {1: 7}], protected={1, 2}, replaceable={1, 2})
    assert [n for n, _ in log["authored"]] == [1] and drafts[1] == "new1" and drafts[2] == "old2"       # 3 <= REPLACE_SCORE, 5 is only flawed: the component stays
