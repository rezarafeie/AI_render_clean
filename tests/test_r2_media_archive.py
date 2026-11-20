import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import media_archive, motion_graphic
from app.routers import studio


def test_private_range_and_local_restore(tmp_path, monkeypatch):
    contents = b"synthetic data used for the archive test"
    digest = hashlib.sha256(contents).hexdigest()
    path = tmp_path / "clip.mp4"
    key = "media-archive/v1/" + hashlib.sha256(b"owner-one").hexdigest() + "/" + digest + ".mp4"
    path.with_suffix(".mp4.r2.json").write_text(json.dumps({
        "path": path.name, "key": key, "size": len(contents), "mtime_ns": 1000000000, "sha256": digest,
    }))
    monkeypatch.setattr(media_archive.settings, "JOBS_DIR", str(tmp_path))
    requests = []
    closed = []

    def get_object(**params):
        requests.append(params)
        assert params["Key"] == key
        data = contents
        content_range = {}
        if params.get("Range"):
            assert params["Range"] == "bytes=4-9"
            data = contents[4:10]
            content_range["ContentRange"] = f"bytes 4-9/{len(contents)}"
        return dict(**content_range, ContentLength=len(data), Body=SimpleNamespace(
            iter_chunks=lambda **kwargs: iter([data]), close=lambda: closed.append(True),
        ))

    store = SimpleNamespace(bucket="media", client=SimpleNamespace(get_object=get_object), prefix=lambda user: user + "/")
    monkeypatch.setattr(media_archive, "_store", lambda: store)
    assert media_archive.available(path, "owner-one")
    assert not media_archive.available(path, "owner-two")
    assert path in media_archive.media_paths(tmp_path, "*.mp4", "owner-one")
    async def attachment(ids, conversation_id, user, *, restore_media):
        assert not restore_media
        if ids != ["existing-id"] or conversation_id != "old-chat" or user != "owner-one":
            raise KeyError(ids)
        return [{"path": str(path), "filename": "clip.mp4", "mime_type": "video/mp4"}]

    monkeypatch.setattr(studio.repo, "get_attachments", AsyncMock(side_effect=attachment))
    app = FastAPI()
    app.include_router(studio.router)

    @app.middleware("http")
    async def test_identity(request, call_next):
        request.state.user = SimpleNamespace(id=request.headers.get("x-test-owner", "owner-one"))
        return await call_next(request)

    client = TestClient(app)
    existing_url = "/studio/conversations/old-chat/attachments/existing-id"
    selected = client.get(existing_url, headers={"Range": "bytes=4-9"})
    assert selected.status_code == 206 and selected.content == contents[4:10]
    assert selected.headers["content-range"] == f"bytes 4-9/{len(contents)}"
    assert client.get(existing_url, headers={"x-test-owner": "owner-two"}).status_code == 404
    assert client.get(existing_url, headers={"Range": "bytes=1000-"}).status_code == 416
    assert not path.exists()
    assert media_archive.materialize(path, "owner-one").read_bytes() == contents
    assert len(requests) == len(closed) == 2


def test_archived_motion_version_remains_playable(tmp_path, monkeypatch):
    content = b"abc"
    digest = hashlib.sha256(content).hexdigest()
    owner = "owner-one"
    folder = tmp_path / "motion"
    version = folder / "v1"
    version.mkdir(parents=True)
    (folder / "motion.json").write_text(json.dumps(
        {"current": 1, "versions": [{"n": 1}], "user_key": owner},
    ))
    path = version / "motion.mp4"
    key = f"media-archive/v1/{hashlib.sha256(owner.encode()).hexdigest()}/{digest}.mp4"
    path.with_suffix(".mp4.r2.json").write_text(json.dumps(
        {"path": "motion/v1/motion.mp4", "key": key, "sha256": digest, "size": 3, "mtime_ns": 1000000000},
    ))
    monkeypatch.setattr(media_archive.settings, "JOBS_DIR", str(tmp_path))
    store = SimpleNamespace(bucket="media", client=SimpleNamespace(get_object=lambda **kwargs: {
        "ContentLength": len(content),
        "Body": SimpleNamespace(iter_chunks=lambda **options: iter([content]), close=lambda: None),
    }))
    monkeypatch.setattr(media_archive, "_store", lambda: store)
    monkeypatch.setattr(motion_graphic, "locate", lambda motion_id, user: folder)
    app = FastAPI()
    app.include_router(studio.router)

    @app.middleware("http")
    async def test_identity(request, call_next):
        request.state.user = SimpleNamespace(id=request.headers.get("x-test-owner", owner))
        return await call_next(request)

    with TestClient(app) as client:
        response = client.get("/studio/motion/example/video?v=1")
        assert response.status_code == 200 and response.content == content
        assert response.headers["content-disposition"].startswith("inline;")
        assert client.get("/studio/motion/example/video?v=1", headers={"x-test-owner": "other"}).status_code == 404
    assert not path.exists()
    assert motion_graphic.media_path(folder, "video", 1).read_bytes() == content
