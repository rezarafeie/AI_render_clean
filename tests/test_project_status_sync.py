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
