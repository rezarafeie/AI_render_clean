import asyncio
import json

import pytest
from fastapi import HTTPException

from app import resumable_upload as up
from app import studio_store


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(studio_store, "ROOT", tmp_path)
    async def conv(self, cid, user): return {"id": cid}
    monkeypatch.setattr(type(up.repo), "get_conversation", conv)
    finished = []
    async def fin(user, cid, temp, name, kind, mime, size, metadata=None):
        finished.append((name, kind, size, temp.read_bytes()))
        return {"id": "att1", "kind": kind, "filename": name, "mime_type": mime, "size_bytes": size, "path": str(temp)}
    monkeypatch.setattr(up, "finalize", fin)
    return finished


def begin(user="u", name="clip.mp4", size=10, **kw):
    return asyncio.run(up.start(user, "c1", up.Start(filename=name, size=size, **kw), free_bytes=kw.get("free", 10**12) if False else 10**12))


async def gen(data, piece=3):
    for i in range(0, len(data), piece):
        yield data[i:i + piece]


def send(upload, offset, data, user="u", declared=None):
    return asyncio.run(up.append(user, "c1", upload["id"], offset, len(data) if declared is None else declared, gen(data)))


def test_pieces_in_order_complete_and_register_the_attachment(env):
    s = begin(size=10)
    assert send(s, 0, b"01234")["received"] == 5
    done = send(s, 5, b"56789")
    assert done["done"] and done["attachment"]["id"] == "att1"
    assert env[0][3] == b"0123456789" and env[0][1] == "video"


def test_a_piece_at_the_wrong_offset_is_refused_and_says_where_to_resume():
    s = begin(size=10)
    send(s, 0, b"0123")
    with pytest.raises(HTTPException) as err:
        send(s, 6, b"6789")
    assert err.value.status_code == 409 and err.value.detail["received"] == 4


def test_a_cut_off_piece_does_not_advance_and_is_overwritten_on_retry(env):
    s = begin(size=8)
    with pytest.raises(HTTPException) as err:
        send(s, 0, b"abcd", declared=8)              # promised 8 bytes, only 4 arrived
    assert err.value.detail["code"] == "incomplete_chunk"
    assert asyncio.run(up.start("u", "c1", up.Start(filename="clip.mp4", size=8), free_bytes=10**12))["received"] == 0
    assert send(s, 0, b"ABCDEFGH")["done"]
    assert env[0][3] == b"ABCDEFGH"


def test_the_same_file_chosen_again_continues_the_same_upload():
    first = begin(size=10, last_modified=5)
    send(first, 0, b"01234")
    again = asyncio.run(up.start("u", "c1", up.Start(filename="clip.mp4", size=10, last_modified=5), free_bytes=10**12))
    assert again["id"] == first["id"] and again["received"] == 5


def test_limits_unsupported_types_disk_space_and_active_uploads():
    with pytest.raises(HTTPException) as e1:
        asyncio.run(up.start("u", "c1", up.Start(filename="a.pdf", size=5), free_bytes=10**12))
    assert e1.value.detail["code"] == "unsupported_file"
    with pytest.raises(HTTPException) as e2:
        asyncio.run(up.start("u", "c1", up.Start(filename="a.mp4", size=11 * 1024**3), free_bytes=10**13))
    assert e2.value.status_code == 413
    asyncio.run(up.start("u", "c1", up.Start(filename="a.mp4", size=10 * 1024**3), free_bytes=10**13))   # 10 GB video is allowed
    with pytest.raises(HTTPException) as e3:
        asyncio.run(up.start("u", "c1", up.Start(filename="b.mp4", size=10**9), free_bytes=10**9))      # no room beyond the reserve
    assert e3.value.status_code == 507
    asyncio.run(up.start("u", "c1", up.Start(filename="c.mp4", size=20), free_bytes=10**13))
    with pytest.raises(HTTPException) as e4:
        asyncio.run(up.start("u", "c1", up.Start(filename="d.mp4", size=30), free_bytes=10**13))
    assert e4.value.status_code == 429


def test_uploads_belong_to_one_user_and_conversation():
    s = begin(size=10)
    for user, conv in (("other", "c1"), ("u", "c2")):
        with pytest.raises(HTTPException) as err:
            asyncio.run(up.append(user, conv, s["id"], 0, 3, gen(b"abc")))
        assert err.value.status_code == 404
    with pytest.raises(HTTPException):
        up._file("u", "c1", "../../x")


def test_a_file_that_fails_validation_is_discarded(monkeypatch):
    async def bad(*a, **k): raise ValueError("no video stream")
    monkeypatch.setattr(up, "finalize", bad)
    s = begin(size=3)
    with pytest.raises(HTTPException) as err:
        send(s, 0, b"abc")
    assert err.value.status_code == 422
    with pytest.raises(HTTPException):
        asyncio.run(up.append("u", "c1", s["id"], 0, 3, gen(b"abc")))   # session is gone


def test_the_http_protocol_end_to_end(env, monkeypatch):
    """Real request streaming, content-length and status codes, not just the functions."""
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    @app.middleware("http")
    async def who(request, call_next):
        request.state.user = SimpleNamespace(id="u")
        return await call_next(request)
    app.include_router(up.router)
    monkeypatch.setattr(up.shutil, "disk_usage", lambda p: SimpleNamespace(free=10**13))
    client = TestClient(app)
    base = "/studio/conversations/c1/uploads"
    created = client.post(base, json={"filename": "big.mov", "size": 9}).json()
    assert created["received"] == 0 and created["chunk_size"] == up.CHUNK_SIZE
    r = client.put(f"{base}/{created['id']}?offset=0", content=b"abc", headers={"content-type": "application/octet-stream"})
    assert r.json() == {"done": False, **{k: r.json()[k] for k in ("id", "received", "size", "chunk_size", "filename")}} and r.json()["received"] == 3
    stale = client.put(f"{base}/{created['id']}?offset=0", content=b"abc")
    assert stale.status_code == 409 and stale.json()["detail"]["received"] == 3
    assert client.get(f"{base}/{created['id']}").json()["received"] == 3
    client.put(f"{base}/{created['id']}?offset=3", content=b"def")
    last = client.put(f"{base}/{created['id']}?offset=6", content=b"ghi").json()
    assert last["done"] and last["attachment"]["filename"] == "big.mov"
    assert env[0][3] == b"abcdefghi"
    assert client.get(f"{base}/{created['id']}").status_code == 404
