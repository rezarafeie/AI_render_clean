import subprocess
from pathlib import Path
import pytest
from app import studio_overview as so
from app.config import settings


def test_cards_carry_kind_status_thumb_and_the_chat(monkeypatch):
    conv = {"id": "c1", "title": "فیلم من", "updated_at": "2026-11-15", "state": {}}
    done = so.summarize(conv, [{"id": "p1", "engine": "talking", "status": "done", "state": {"output": "x.mp4"}, "updated_at": "1"}], None)
    assert (done["id"], done["kind"], done["status"], done["thumb"]) == ("c1", "talking", "ready", "/studio/projects/p1/thumb")
    motion = so.summarize({**conv, "state": {"motion": {"motion_id": "m"}}}, [], {"id": "abc", "status": "completed", "completed": True})
    assert motion["kind"] == "motion" and motion["thumb"] == "/studio/motion/abc/thumb" and motion["status"] == "ready"
    running = so.summarize(conv, [{"id": "p2", "engine": "talking", "status": "running", "state": {}, "updated_at": "1"}], None)
    assert running["status"] == "running" and running["thumb"] is None
    assert so.summarize(conv, [], None)["kind_label"] == "گفتگو"


def test_a_frame_is_cut_once_and_a_new_render_gets_a_new_picture(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "JOBS_DIR", str(tmp_path))
    video = tmp_path / "v.mp4"
    if subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=320x240:d=2", "-y", str(video)]).returncode != 0:
        pytest.skip("ffmpeg is not available")
    first = so.cut_frame(video, "p1")
    assert first and first.suffix == ".jpg" and first.stat().st_size > 0
    assert so.cut_frame(video, "p1") == first
    video.write_bytes(video.read_bytes() + b"\0")
    assert so.cut_frame(video, "p1") != first


def test_the_closing_message_is_told_what_was_asked_and_what_was_made(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from app import studio_orchestrator as orch
    async def conversation(cid, user, message_limit=None):
        return {"messages": [{"role": "user", "content": "یک ریلز از ویدیوم بساز https://x.example/a"}, {"role": "assistant", "content": "باشه"}, {"role": "user", "content": "با زیرنویس زرد"}]}
    monkeypatch.setattr(orch.repo, "get_conversation", conversation)
    facts = asyncio.run(orch._delivery_facts("c", "1", {"title": "ریلز من"}, "talking", {"style": "talking_5", "creative_review": {"summary": "ریتم خوب و زیرنویس خوانا"}}, None))
    assert facts["what_the_person_asked_for"] == "با زیرنویس زرد" and facts["project_title"] == "ریلز من"
    assert facts["automatic_review_of_the_result"] == "ریتم خوب و زیرنویس خوانا" and facts["style"] == "talking_5" and facts["video_is_ready"]
    assert "https" not in str(facts)
