import asyncio
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app import credits, studio_store, studio_tools
from app.agents import store as agent_store
from app.routers import panel


@pytest.fixture
def editor(tmp_path, monkeypatch):
    monkeypatch.setattr(studio_store, "DB_AVAILABLE", False)
    monkeypatch.setattr(studio_store, "ROOT", tmp_path)
    monkeypatch.setattr(studio_store, "FALLBACK", tmp_path / "studio.json")
    monkeypatch.setattr(panel, "_lock", lambda *_: nullcontext())
    monkeypatch.setattr(agent_store, "preference", AsyncMock(return_value="medium"))
    monkeypatch.setattr(credits, "gate", AsyncMock())
    return SimpleNamespace(state=SimpleNamespace(user=SimpleNamespace(id="owner")), headers={}, cookies={})


def test_panel_creates_and_reopens_the_same_studio_project_without_user_messages(editor, monkeypatch, tmp_path):
    execute = []

    def tool(name, args):
        execute.append((name, args))
        return {"external_ref": "123456789abc"}

    monkeypatch.setattr(studio_tools, "execute", tool)

    async def scenario():
        draft = await panel.draft(editor)
        cid = draft["id"]
        file = await studio_store.repo.create_attachment(cid, "owner", kind="video", filename="sample.mp4",
                                                         path=str(tmp_path / "sample.mp4"), mime_type="video/mp4", size_bytes=27)
        setup = panel.ProjectSetup(title="Demo", style="talking_2", attachment_ids=[file["id"]])
        await panel.save_setup(editor, cid, setup)
        assert (await panel.draft_media(editor, cid))[0] == {
            "id": file["id"], "filename": "sample.mp4", "kind": "video", "mime_type": "video/mp4", "size_bytes": 27,
        }
        await panel.start(editor, cid)
        await panel.start(editor, cid)
        chat = await studio_store.repo.get_conversation(cid, "owner")
        assert chat["messages"] == []
        assert chat["title"] == "Demo"
        assert chat["state"]["agent_mode"] == "medium"
        assert len(chat["projects"]) == 1
        assert chat["projects"][0]["state"]["selected_style"] == "talking_2"
        assert chat["projects"][0]["state"]["auto_render"] is False
    asyncio.run(scenario())
    assert len(execute) == 1 and execute[0][0] == "analyze_talking_reel"
    assert execute[0][1]["user_key"] == "owner"


def test_setup_rejects_another_users_source_and_start_rejects_missing_video(editor, monkeypatch):
    monkeypatch.setattr(studio_tools, "execute", lambda *_: pytest.fail("must validate ownership and media first"))

    async def scenario():
        cid = (await panel.draft(editor))["id"]
        other = SimpleNamespace(state=SimpleNamespace(user=SimpleNamespace(id="other")), headers={}, cookies={})
        with pytest.raises(HTTPException, match="پروژه پیدا نشد") as wrong_owner:
            await panel.save_setup(other, cid, panel.ProjectSetup())
        assert wrong_owner.value.status_code == 404
        with pytest.raises(HTTPException) as wrong_asset:
            await panel.save_setup(editor, cid, panel.ProjectSetup(attachment_ids=["other_asset"]))
        assert wrong_asset.value.status_code == 404
        with pytest.raises(HTTPException) as no_video:
            await panel.start(editor, cid)
        assert no_video.value.status_code == 422
        credits.gate.assert_not_called()
    asyncio.run(scenario())


def test_native_operations_send_explicit_source_time_and_reject_stale_version(editor, monkeypatch):
    from app import jobs, plan_versions
    job = SimpleNamespace(id="ownedjob", render=SimpleNamespace(status="idle"))
    snapshot = {"canvas": {"fps": 30}, "segments": [{"id": "one", "in": 1.0, "out": 6.0}]}
    monkeypatch.setattr(panel, "_native_job", AsyncMock(return_value=(job, snapshot)))
    monkeypatch.setattr(plan_versions, "latest_version", lambda _: {"version": 3})
    monkeypatch.setattr(plan_versions, "list_versions", lambda _: [{"version": 3}])
    operations = []

    def apply(job, ops, **guard):
        operations.append((ops, guard))

    monkeypatch.setattr(jobs, "apply_plan_operations", apply)

    async def scenario():
        result = await panel.change_segment(editor, "p", panel.SegmentChange(version=3, operation="trim", segment_id="one", start=2, end=5))
        assert result["segments"][0]["source_in"] == 1
        assert operations == [([{"op": "trim_segment", "segment_id": "one", "source_in": 2, "source_out": 5}],
                               {"base_version": 3, "base_plan": snapshot})]
        with pytest.raises(HTTPException) as stale:
            await panel.change_segment(editor, "p", panel.SegmentChange(version=2, operation="remove_range", start=0.3, end=1))
        assert stale.value.status_code == 409
        assert len(operations) == 1
    asyncio.run(scenario())


def test_native_layer_bounds_and_no_destructive_reorder():
    base = {"canvas": {"fps": 30}, "segments": [{"id": "one", "in": 0, "out": 4}]}
    plan = panel._arrange_segments(base, panel.SegmentChange(operation="split", segment_id="one", start=2))
    assert len(plan["segments"]) == 2 and len(base["segments"]) == 1
    assert plan["segments"][0]["out"] == plan["segments"][1]["in"] == 2
    plan = panel._apply_layer(plan, panel.LayerChange(kind="caption", operation="add", start=0, end=2, text="سلام، دنیا"))
    assert plan["captions"] == [{"start": 0, "end": 2, "text": "سلام، دنیا", "position": "bottom"}]
    with pytest.raises(HTTPException) as invalid_split:
        panel._arrange_segments(plan, panel.SegmentChange(operation="duplicate", segment_id="one"))
    assert invalid_split.value.status_code == 409
    with pytest.raises(HTTPException) as invalid_time:
        panel._apply_layer(plan, panel.LayerChange(kind="caption", operation="add", start=3, end=6, text="Outside"))
    assert invalid_time.value.status_code == 422
