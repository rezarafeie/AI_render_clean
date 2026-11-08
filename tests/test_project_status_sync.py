"""The status a project gets from its engine: a stopped job is canceled, never "running"."""
import pytest

from app.studio_orchestrator import _project_status


@pytest.mark.parametrize("raw,output,expected", [
    ("canceled", None, "canceled"),
    ("cancelled", None, "canceled"),
    ("running", None, "running"),
    ("analyzing", None, "running"),
    ("rendering", None, "running"),
    ("error", None, "error"),
    ("paused", None, "paused"),
    ("awaiting_input", None, "awaiting_input"),
    ("awaiting_confirmation", None, "awaiting_confirmation"),
    ("done", "/api/jobs/x/output", "done"),
    ("running", "/api/jobs/x/output", "done"),
    ("canceled", "/api/jobs/x/output", "done"),
])
def test_project_status_from_engine(raw, output, expected):
    assert _project_status(raw, output) == expected


def test_cancel_project_settles_a_project_whose_engine_has_nothing_running(monkeypatch):
    """Stop on a project that reads running while its engine was already stopped must end as canceled (it used to raise and stay running)."""
    import asyncio

    from app import studio_orchestrator as orchestrator

    project = {"id": "p1", "conversation_id": "c1", "engine": "talking", "external_ref": "ref", "status": "running", "state": {"last_observed": {"x": 1}}}
    updates = []

    async def get_project(pid, user):
        return dict(project)

    async def update_project(pid, user, **fields):
        updates.append(fields)
        return {**project, **fields}

    def nothing_running(name, payload):
        raise ValueError("talking reel is not running")

    monkeypatch.setattr(orchestrator.repo, "get_project", get_project)
    monkeypatch.setattr(orchestrator.repo, "update_project", update_project)
    monkeypatch.setattr(orchestrator, "execute", nothing_running)
    monkeypatch.setattr(orchestrator, "_emit", lambda *a, **k: None)
    result = orchestrator.cancel_project("p1", "alice")
    assert result == {"status": "not_running"}
    assert updates and updates[-1]["status"] == "canceled" and updates[-1]["state"]["last_observed"] == {}
