import hashlib
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import media_archive, r2_upload, studio_store


class Storage:
    def __init__(self):
        self.objects = {}
        self.parts = {}
        self.key = ""

    def create_multipart_upload(self, Key, **kwargs):
        self.key = Key
        return {"UploadId": "multipart"}

    def generate_presigned_url(self, name, *, Params, ExpiresIn):
        assert name == "upload_part" and Params["ContentLength"] > 0
        return f"https://example.test/part/{Params['PartNumber']}"

    def list_parts(self, **kwargs):
        return {"Parts": [{"PartNumber": n, "ETag": str(n), "Size": len(data)} for n, data in self.parts.items()]}

    def complete_multipart_upload(self, *, Key, MultipartUpload, **kwargs):
        content = b"".join(self.parts[part["PartNumber"]] for part in MultipartUpload["Parts"])
        self.objects[Key] = (content, {})

    def head_object(self, Key, **kwargs):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        data, metadata = self.objects[Key]
        return {"ContentLength": len(data), "Metadata": metadata}

    def get_object(self, Key, **kwargs):
        data = self.objects[Key][0]
        return {"Body": SimpleNamespace(iter_chunks=lambda **options: (data,), close=lambda: None)}

    def copy_object(self, Key, CopySource, Metadata, **kwargs):
        self.objects[Key] = (self.objects[CopySource["Key"]][0], Metadata)

    def delete_object(self, Key, **kwargs):
        self.objects.pop(Key, None)


def test_direct_upload_uses_private_archive_and_retries_safely(tmp_path, monkeypatch):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg and FFprobe are required")
    owner = "owner-one"
    monkeypatch.setattr(studio_store.settings, "STUDIO_DIRECT_R2_UPLOAD", True)
    monkeypatch.setattr(studio_store.settings, "DATABASE_URL", None)
    monkeypatch.setattr(studio_store.settings, "JOBS_DIR", str(tmp_path))
    monkeypatch.setattr(studio_store, "ROOT", tmp_path)
    monkeypatch.setattr(studio_store, "FALLBACK", tmp_path / "studio.json")
    monkeypatch.setattr(studio_store, "DB_AVAILABLE", False)
    monkeypatch.setattr(r2_upload, "PART_SIZE", 1024)
    monkeypatch.setattr(r2_upload, "DISK_RESERVE", 0)
    monkeypatch.setattr(r2_upload, "conversation_dir", lambda user, cid: tmp_path / user / cid)
    storage = Storage()
    store = SimpleNamespace(client=storage, bucket="private", prefix=lambda user: f"staging/{user}/")
    monkeypatch.setattr(media_archive, "_store", lambda: store)
    cid = studio_store.run(studio_store.repo.create_conversation(owner, "Try direct upload"))["id"]
    sample = tmp_path / "sample.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=black:s=160x120:d=1",
                    "-c:v", "libx264", str(sample)], check=True)
    data = sample.read_bytes()
    app = FastAPI()
    app.include_router(r2_upload.router)

    @app.middleware("http")
    async def identity(request, call_next):
        request.state.user = SimpleNamespace(id=request.headers.get("x-test-owner", owner))
        return await call_next(request)

    meta = {"filename": "example.mp4", "size": len(data), "last_modified": 1700}
    endpoint = f"/studio/conversations/{cid}/r2-uploads"
    with TestClient(app) as browser:
        response = browser.post(endpoint, json=meta)
        assert response.status_code == 201, response.json()
        started = response.json()
        status_url = f"{endpoint}/{started['id']}"
        finish = f"{status_url}/complete"
        assert len(started["parts"]) > 1
        assert browser.post(finish, headers={"x-test-owner": "other"}).status_code == 404
        part = started["parts"][0]
        storage.parts[1] = data[part["start"]:part["end"]]
        assert browser.post(finish).status_code == 202
        assert browser.get(status_url).status_code == 409
        resume = browser.post(endpoint, json=meta).json()
        assert resume["id"] == started["id"] and len(resume["parts"]) == len(started["parts"]) - 1
        for part in resume["parts"]:
            storage.parts[int(part["url"].rsplit("/", 1)[-1])] = data[part["start"]:part["end"]]
        assert browser.post(finish).status_code == 202
        response = browser.get(status_url)
        assert response.status_code == 200, response.json()
        assert browser.post(finish).json() == response.json()

    attachments = studio_store.run(studio_store.repo.list_user_attachments(owner))
    assert len(attachments) == 1
    target = Path(attachments[0]["path"])
    assert not target.exists()
    receipt = media_archive.receipt(target, owner)
    assert storage.key not in storage.objects
    assert storage.objects[receipt["key"]][0] == data
    assert receipt["sha256"] == hashlib.sha256(data).hexdigest()
