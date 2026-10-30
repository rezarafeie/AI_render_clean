import asyncio
import json
import socket

import httpx
import pytest

from app import cloud_storage as cloud
from app import studio_store


@pytest.fixture(autouse=True)
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(studio_store, "ROOT", tmp_path)
    monkeypatch.setattr(cloud, "dispatch", lambda *a, **k: None)
    yield tmp_path


def meta(**over):
    base = {"id": "f1", "name": "clip.mp4", "mime_type": "video/mp4", "size": 1000, "is_folder": False,
            "native": False, "kind": "video", "modified": "2026-01-01T00:00:00Z", "checksum": "abc", "version": "7"}
    return {**base, **over}


def patch_meta(monkeypatch, **over):
    async def fake(user, provider, file_id): return meta(**over)
    async def conv(self, cid, user): return {"id": cid}
    monkeypatch.setattr(cloud, "metadata", fake)
    monkeypatch.setattr(type(cloud.repo), "get_conversation", conv)


def test_list_files_builds_a_scoped_query_and_normalises(monkeypatch):
    seen = {}
    async def fake(user, provider, slug, args):
        seen.update(slug=slug, args=args, user=user)
        return {"files": [{"id": "a", "name": "d", "mimeType": cloud.FOLDER_MIME},
                          {"id": "b", "name": "x.mp4", "mimeType": "video/mp4", "size": "12",
                           "videoMediaMetadata": {"durationMillis": "2500", "width": 1920, "height": 1080},
                           "thumbnailLink": "http://insecure/t"}], "nextPageToken": "n"}
    monkeypatch.setattr(cloud, "_call", fake)
    out = asyncio.run(cloud.list_files("u1", "googledrive", "fold'er", "", "video"))
    assert seen["slug"] == "GOOGLEDRIVE_FIND_FILE" and seen["user"] == "u1"
    assert "'fold\\'er' in parents" in seen["args"]["q"] and "trashed = false" in seen["args"]["q"]
    assert "video/" in seen["args"]["q"] and "audio/" not in seen["args"]["q"]
    folder, video = out["files"]
    assert folder["is_folder"] and video["size"] == 12 and video["duration"] == 2.5 and video["thumbnail"] is None
    assert out["next_page_token"] == "n"


def test_search_ignores_folder_and_escapes_quotes(monkeypatch):
    seen = {}
    async def fake(user, provider, slug, args): seen.update(args); return {}
    monkeypatch.setattr(cloud, "_call", fake)
    asyncio.run(cloud.list_files("u", "googledrive", "root", "a' or 1=1 or name contains '"))
    assert "in parents" not in seen["q"] and "a\\' or 1=1" in seen["q"]


def test_unknown_provider_is_refused():
    with pytest.raises(cloud.CloudError) as err:
        asyncio.run(cloud.list_files("u", "nope"))
    assert err.value.code == "provider_unsupported"


@pytest.mark.parametrize("url", ["http://x.s3.amazonaws.com/a", "https://evil.example.com/a",
                                 "https://u:p@x.s3.amazonaws.com/a", "https://x.s3.amazonaws.com:8443/a",
                                 "https://notamazonaws.com/a"])
def test_download_links_outside_the_allow_list_are_refused(url):
    with pytest.raises(cloud.CloudError) as err:
        cloud.safe_download_url(url)
    assert err.value.code == "unsafe_link"


def test_download_link_resolving_to_a_private_address_is_refused(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("10.0.0.5", 443))])
    with pytest.raises(cloud.CloudError):
        cloud.safe_download_url("https://bucket.s3.amazonaws.com/f")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("52.1.2.3", 443))])
    assert cloud.safe_download_url("https://bucket.s3.amazonaws.com/f")


@pytest.mark.parametrize("over,code", [({"is_folder": True}, "unsupported_file"), ({"native": True}, "unsupported_file"),
                                       ({"name": "notes.pdf"}, "unsupported_file"), ({"size": 3 * 1024**3}, "file_too_large")])
def test_import_refuses_unsuitable_files(monkeypatch, over, code):
    patch_meta(monkeypatch, **over)
    with pytest.raises(cloud.CloudError) as err:
        asyncio.run(cloud.begin_import("u", "c1", "googledrive", "f1"))
    assert err.value.code == code


def test_import_creates_a_queued_record_and_reuses_an_unchanged_active_one(monkeypatch):
    patch_meta(monkeypatch)
    first = asyncio.run(cloud.begin_import("u", "c1", "googledrive", "f1"))
    again = asyncio.run(cloud.begin_import("u", "c1", "googledrive", "f1"))
    assert first["state"] == "queued" and again["id"] == first["id"]


def test_transfers_are_isolated_per_user_and_conversation(monkeypatch):
    patch_meta(monkeypatch)
    record = asyncio.run(cloud.begin_import("alice", "c1", "googledrive", "f1"))
    assert cloud.get_transfer("alice", "c1", record["id"])["id"] == record["id"]
    for user, conv in (("bob", "c1"), ("alice", "c2")):
        with pytest.raises(cloud.CloudError) as err:
            cloud.get_transfer(user, conv, record["id"])
        assert err.value.code == "not_found"
    with pytest.raises(cloud.CloudError):
        cloud.get_transfer("alice", "c1", "../../etc/passwd")


def test_cancel_a_queued_transfer_and_retry_it(monkeypatch):
    patch_meta(monkeypatch)
    record = asyncio.run(cloud.begin_import("u", "c1", "googledrive", "f1"))
    assert cloud.cancel("u", "c1", record["id"])["state"] == "cancelled"
    assert cloud.retry("u", "c1", record["id"])["state"] == "queued"


def run_with_payload(monkeypatch, payload, status=200, expect=None):
    patch_meta(monkeypatch, size=len(payload))
    record = asyncio.run(cloud.begin_import("u", "c1", "googledrive", "f1"))
    async def call(user, provider, slug, args):
        return {"downloaded_file_content": {"s3url": "https://b.s3.amazonaws.com/x", "name": "clip.mp4"}}
    monkeypatch.setattr(cloud, "_call", call)
    monkeypatch.setattr(cloud, "safe_download_url", lambda u: u)
    real = httpx.Client
    monkeypatch.setattr(cloud.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(
        lambda request: httpx.Response(status, content=payload)), **kw))
    async def fin(user, cid, temp, name, kind, mime, size, meta):
        return {"id": "att1", "path": str(temp)}
    monkeypatch.setattr(cloud, "finalize", fin)
    cloud.run_import(record["id"], "u", "c1")
    return cloud.get_transfer("u", "c1", record["id"])


def test_import_streams_the_file_and_registers_an_attachment(monkeypatch):
    done = run_with_payload(monkeypatch, b"x" * 5000)
    assert done["state"] == "completed" and done["attachment_id"] == "att1" and done["bytes"] == 5000


def test_a_failed_download_is_reported_and_leaves_no_partial_file(monkeypatch, root):
    done = run_with_payload(monkeypatch, b"", status=500)
    assert done["state"] == "failed" and done["retryable"] is True
    assert not list(root.rglob("cloud_*.mp4"))


def test_a_short_download_is_not_accepted(monkeypatch):
    patch_meta(monkeypatch, size=9999)
    record = asyncio.run(cloud.begin_import("u", "c1", "googledrive", "f1"))
    async def call(*a): return {"downloaded_file_content": {"s3url": "https://b.s3.amazonaws.com/x"}}
    monkeypatch.setattr(cloud, "_call", call)
    monkeypatch.setattr(cloud, "safe_download_url", lambda u: u)
    real = httpx.Client
    monkeypatch.setattr(cloud.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"abc")), **kw))
    cloud.run_import(record["id"], "u", "c1")
    assert cloud.get_transfer("u", "c1", record["id"])["error_code"] == "network"


def test_provider_errors_are_classified_without_leaking_details():
    assert cloud._classify("HTTP 403 insufficient permission token=abc") == "permission_denied"
    assert "token" not in cloud._public_error("HTTP 403 insufficient permission token=abc")
    assert cloud._classify("invalid_grant") == "reconnect_required"
