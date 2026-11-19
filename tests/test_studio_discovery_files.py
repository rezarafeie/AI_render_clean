import asyncio
import shutil
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import long_video, studio_files, studio_store
from app.routers.studio import LibraryAttach, attach_from_library
from engine.probe import probe


def test_old_and_new_discovery_clips_are_available_to_the_owner_and_attach_at_full_resolution(tmp_path, monkeypatch):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg and FFprobe are required")
    monkeypatch.setattr(studio_store, "DB_AVAILABLE", False)
    monkeypatch.setattr(studio_store, "ROOT", tmp_path)
    monkeypatch.setattr(studio_store, "FALLBACK", tmp_path / "studio.json")
    monkeypatch.setattr(long_video, "ROOT", tmp_path)
    monkeypatch.setattr(studio_files, "_outputs", lambda project: [{"path": source, "id": "output-test", "name": project["title"]}])
    source = tmp_path / "long.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", "color=blue:s=640x480:d=4",
                    "-c:v", "libx264", str(source)], check=True)

    async def scenario():
        repo = studio_store.repo
        parent = (await repo.create_conversation("owner", "Original long video"))["id"]
        target = (await repo.create_conversation("owner", "Fresh editing chat"))["id"]
        other = (await repo.create_conversation("other", "Another account"))["id"]
        child = (await repo.create_conversation("owner", "Edited candidate"))["id"]
        await repo.set_conversation(child, "owner", state={"parent": {"analysis_id": "abcdef123456", "candidate_id": "c123456789"}})
        await repo.create_project(child, "owner", "talking", "Rendered reel")

        def save_analysis(analysis_id, candidate_id, title, created_at):
            directory = long_video.folder("owner", parent, analysis_id)
            directory.mkdir(parents=True)
            long_video.save(directory, {"id": analysis_id, "user_key": "owner", "conversation_id": parent,
                "source_path": str(source), "candidates": [
                    {"id": candidate_id, "title": title, "ranges": [[0.5, 2.5]], "created_at": created_at},
                    {"id": "c000000000", "title": "Hidden", "ranges": [[0, 2]], "hidden": True},
                ]})
            return directory

        old = save_analysis("abcdef123456", "c123456789", "Old clip", 100)
        await repo.set_conversation(parent, "owner", state={"discovery": {"analysis_id": "123456abcdef"}})
        initial = (await studio_files.library("owner"))["files"]
        assert {item["name"] for item in initial} == {"Old clip.mp4", "Rendered reel"}
        save_analysis("123456abcdef", "c987654321", "New clip", 200)

        entries = (await studio_files.library("owner"))["files"]
        assert all(item["folder"] == "discovery" for item in entries)
        cuts = [item for item in entries if item["source"] == "discovery"]
        assert [item["name"] for item in cuts] == ["New clip.mp4", "Old clip.mp4"]
        assert (await studio_files.library("other"))["files"] == []
        with pytest.raises(KeyError):
            await studio_files.attach("other", other, cuts[0]["id"])
        with pytest.raises(KeyError):
            await studio_files.attach("owner", other, cuts[0]["id"])

        item = await studio_files.attach("owner", target, cuts[1]["id"])
        attached = Path(item["path"])
        video = next(stream for stream in probe(attached)["streams"] if stream["codec_type"] == "video")
        assert (video["width"], video["height"]) == (640, 480)
        assert float(video["duration"]) == pytest.approx(2.0, abs=0.05)
        cache, = (old / "clips").glob("*.mp4")
        assert cache.samefile(attached)
        assert item["filename"] == "Old clip.mp4"

        render = long_video.render_clip
        started, release = threading.Event(), threading.Event()
        renders = []

        def slow_render(*args, **kwargs):
            renders.append(1)
            started.set()
            assert release.wait(8)
            return render(*args, **kwargs)

        monkeypatch.setattr(long_video, "render_clip", slow_render)
        request = SimpleNamespace(state=SimpleNamespace(user=SimpleNamespace(id="owner")), headers={}, cookies={})
        body = LibraryAttach(file_id=cuts[0]["id"], defer=True)
        pending = await asyncio.wait_for(attach_from_library(request, target, body), timeout=2)
        assert pending.status_code == 202
        try:
            assert await asyncio.to_thread(started.wait, 2)
            assert (await attach_from_library(request, target, body)).status_code == 202
            assert renders == [1]
        finally:
            release.set()
        async with asyncio.timeout(8):
            while not isinstance(ready := await attach_from_library(request, target, body), dict):
                await asyncio.sleep(0.03)
        assert ready["filename"] == "New clip.mp4"
        assert renders == [1]

        analysis = long_video.load(old)
        analysis["candidates"][0]["ranges"] = [[1, 3]]
        long_video.save(old, analysis)
        with pytest.raises(KeyError):
            await studio_files.attach("owner", target, cuts[1]["id"])
        assert attached.is_file()

    asyncio.run(scenario())
