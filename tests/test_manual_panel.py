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


def test_split_with_output_layers_preserves_frame_count_and_caption_timing():
    from engine.operations import output_duration

    plan = {
        "canvas": {"fps": 30}, "segments": [{"id": "one", "in": .06, "out": 3.48}],
        "captions": [{"start": 0, "end": 2, "text": "سلام"}],
    }
    split = panel._arrange_segments(plan, panel.SegmentChange(operation="split", segment_id="one", start=1))
    assert output_duration(split) == output_duration(plan)
    assert split["captions"] == plan["captions"]
    assert split["segments"][0]["out"] == split["segments"][1]["in"]
    zoom = panel._arrange_segments(plan, panel.SegmentChange(operation="zoom", segment_id="one", zoom_from=1, zoom_to=1.39))
    assert zoom["segments"][0]["zoom"] == {"from": 1, "to": 1.39}
    with pytest.raises(HTTPException, match="زمان‌بندی"):
        panel._arrange_segments(zoom, panel.SegmentChange(operation="split", segment_id="one", start=1))


def test_layer_attachment_is_scoped_to_the_project_conversation(editor, monkeypatch, tmp_path):
    from app import plan_versions

    job = SimpleNamespace(dir=tmp_path / "job", render=SimpleNamespace(status="idle"))
    monkeypatch.setattr(panel, "_native_job", AsyncMock(return_value=(job, {})))
    monkeypatch.setattr(plan_versions, "latest_version", lambda _: {"version": 2})
    staged = AsyncMock()
    monkeypatch.setattr(panel, "_stage_layer_attachment", staged)

    async def scenario():
        target = (await panel.draft(editor))["id"]
        origin = (await panel.draft(editor))["id"]
        project = await studio_store.repo.create_project(target, "owner", "motion", "Demo")
        attachment = await studio_store.repo.create_attachment(origin, "owner", kind="video", filename="sample.mp4",
                                                               path=str(tmp_path / "sample.mp4"), mime_type="video/mp4", size_bytes=27)
        body = panel.LayerChange(version=2, operation="add", kind="broll", attachment_id=attachment["id"], start=0, end=1)
        with pytest.raises(HTTPException) as missing:
            await panel.change_layer(editor, project["id"], body)
        assert missing.value.status_code == 404
        staged.assert_not_called()
    asyncio.run(scenario())


def test_layer_asset_path_stays_local_and_reusable(tmp_path):
    source = tmp_path / "uploaded.mp4"
    source.write_bytes(b"the uploaded clip")
    record = {"id": "f" * 32, "path": str(source), "filename": "cutaway.mp4"}
    job = SimpleNamespace(dir=tmp_path / "job")
    relative, created = panel._stage_layer_attachment(job, record)
    assert relative == f"assets/panel-media/{record['id']}/cutaway.mp4"
    assert created.read_bytes() == source.read_bytes()
    assert panel._stage_layer_attachment(job, record) == (relative, None)
    source.unlink()
    assert created.read_bytes() == b"the uploaded clip"


def test_panel_storyboard_requires_approval_and_does_not_queue_paid_production(editor, monkeypatch):
    from app import studio_orchestrator

    def create(conversation, user, key, request, attachments):
        async def record():
            assert key == f"panel:{conversation}"
            assert not attachments and "45 ثانیه" in request
            project = await studio_store.repo.create_project(conversation, user, "motion", "Storyboard")
            await studio_store.repo.create_action(conversation, project["id"], "generate_motion_video", {}, key)
            await studio_store.repo.update_project(project["id"], user, status="awaiting_confirmation")
        asyncio.run(record())

    monkeypatch.setattr(studio_orchestrator, "_create_motion", create)

    async def scenario():
        cid = (await panel.draft(editor))["id"]
        await panel.save_setup(editor, cid, panel.ProjectSetup(engine="storyboard", topic="معرفی یک نرم‌افزار", seconds=45))
        await panel.start(editor, cid)
        await panel.start(editor, cid)
        chat = await studio_store.repo.get_conversation(cid, "owner")
        assert chat["messages"] == []
        assert [item["status"] for item in chat["projects"]] == ["awaiting_confirmation"]
        assert [item["status"] for item in chat["actions"]] == ["pending"]
        assert credits.gate.await_count == 1
    asyncio.run(scenario())


def test_panel_long_video_dispatch_reuses_the_same_analysis(editor, monkeypatch, tmp_path):
    from app import studio_orchestrator

    def discover(conversation, user, row, attachments, focus):
        assert focus == "استخراج نکات کلاس"
        state = {**row["state"], "discovery": {"analysis_id": "analyzed", "attachment_id": attachments[0]["id"]}}
        asyncio.run(studio_store.repo.set_conversation(conversation, user, state=state))

    monkeypatch.setattr(studio_orchestrator, "_start_discovery", discover)

    async def scenario():
        cid = (await panel.draft(editor))["id"]
        media = await studio_store.repo.create_attachment(cid, "owner", kind="video", filename="class.mp4",
                                                           path=str(tmp_path / "class.mp4"), mime_type="video/mp4", size_bytes=27)
        config = panel.ProjectSetup(engine="discovery", topic="استخراج نکات کلاس", attachment_ids=[media["id"]])
        await panel.save_setup(editor, cid, config)
        await panel.start(editor, cid)
        await panel.start(editor, cid)
        assert credits.gate.await_count == 1
        with pytest.raises(HTTPException) as locked:
            await panel.save_setup(editor, cid, config)
        assert locked.value.status_code == 409
        assert (await studio_store.repo.get_conversation(cid, "owner"))["state"]["discovery"]["analysis_id"] == "analyzed"
    asyncio.run(scenario())


def test_native_cutaways_are_stored_in_render_order_and_cannot_overlap():
    base = {"canvas": {"fps": 30}, "segments": [{"id": "one", "in": 0, "out": 7}]}
    later = panel.LayerChange(kind="broll", operation="add", start=4, end=5)
    earlier = panel.LayerChange(kind="broll", operation="add", start=1, end=2)
    overlap = panel.LayerChange(kind="broll", operation="add", start=1.5, end=3)
    one = panel._apply_layer(base, later, "late.mp4")
    two = panel._apply_layer(one, earlier, "early.mp4")
    assert [row["file"] for row in two["broll"]] == ["early.mp4", "late.mp4"]
    assert [row["at"] for row in two["broll"]] == [1, 4]
    with pytest.raises(HTTPException, match="هم‌پوشانی"):
        panel._apply_layer(two, overlap, "overlap.mp4")
