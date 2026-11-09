"""Stop reaches the work behind a chat: unfinished agent runs are cancelled and no further model attempt starts."""
import asyncio

import pytest
from pydantic import BaseModel

from app import studio_orchestrator as orchestrator
from app import studio_store as s
from app.agents import store
from creative import llm


@pytest.fixture(autouse=True)
def local_store(monkeypatch, tmp_path):
    monkeypatch.setattr(s, "DB_AVAILABLE", False)
    monkeypatch.setattr(s, "ROOT", tmp_path / "studio")


def call(coro):
    return asyncio.run(coro)


def _run(status, mode="medium"):
    cid = call(s.repo.create_conversation("alice"))["id"]
    message = call(s.repo.add_message(cid, "alice", "user", "ویدیو را بررسی کن", agent_mode=mode))
    record = call(store.create_run(cid, "alice", message["id"], mode, {"text": "x", "attachment_ids": []}))
    if status != "queued":
        call(store.update(record["id"], "alice", status=status))
    return cid, record["id"]


@pytest.mark.parametrize("status", ["queued", "running", "waiting_approval", "waiting_job"])
def test_stop_cancels_an_unfinished_agent_run(status):
    cid, run_id = _run(status)
    result = orchestrator.request_stop(cid, "alice")
    assert "agent" in result["stopped"]
    assert call(store.get_run(run_id, "alice"))["status"] == "cancelled"
    assert call(store.get_run(run_id, "alice"))["data"]["stopped"] is True


def test_stop_leaves_a_handed_off_or_finished_run_alone():
    cid, run_id = _run("dispatched", mode="lite")
    result = orchestrator.request_stop(cid, "alice")
    assert "agent" not in result["stopped"]
    assert call(store.get_run(run_id, "alice"))["status"] == "dispatched"


class _Answer(BaseModel):
    ok: bool


def test_no_model_attempt_starts_after_stop(monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "configured", lambda: True)
    import brain.llm
    monkeypatch.setattr(brain.llm, "gateway_json", lambda *a, **k: calls.append(1) or ({"ok": True}, None))

    class Stopped(Exception):
        pass

    def check():
        raise Stopped()

    token = llm.STOP_CHECK.set(check)
    try:
        with pytest.raises(Stopped):
            llm.ask(_Answer, "system", "user", route="creative_critic")
    finally:
        llm.STOP_CHECK.reset(token)
    assert calls == []


def test_a_cooldown_wait_is_not_started_after_stop(monkeypatch):
    waited, attempts = [], []
    monkeypatch.setattr(llm, "configured", lambda: True)
    monkeypatch.setattr(llm, "_sleep", lambda seconds: waited.append(seconds))
    import brain.llm

    class Busy(Exception):
        status = 429

    def busy(*a, **k):
        attempts.append(1)
        raise Busy("reset in 8s")

    monkeypatch.setattr(brain.llm, "gateway_json", busy)

    class Stopped(Exception):
        pass

    state = {"stop": False}

    def check():
        if state["stop"]:
            raise Stopped()

    token = llm.STOP_CHECK.set(check)
    try:
        original = llm.cooldown_seconds

        def stop_then_report(exc):
            state["stop"] = True                       # Stop pressed while the call was in flight
            return original(exc)

        monkeypatch.setattr(llm, "cooldown_seconds", stop_then_report)
        with pytest.raises(Stopped):
            llm.ask(_Answer, "system", "user", route="creative_critic")
    finally:
        llm.STOP_CHECK.reset(token)
    assert attempts == [1] and waited == []


def test_stop_is_written_into_the_chat_once():
    cid, _ = _run("running")
    orchestrator.request_stop(cid, "alice")
    orchestrator.request_stop(cid, "alice")                    # pressing stop again adds nothing
    notes = [m for m in call(s.repo.get_conversation(cid, "alice"))["messages"] if m["role"] == "assistant" and m["content"] == orchestrator.STOPPED_BY_USER]
    assert len(notes) == 1
