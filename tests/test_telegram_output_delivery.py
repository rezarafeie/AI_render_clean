import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx

from app.routers import telegram_studio as tg


def test_large_output_resumes_and_completes(tmp_path, monkeypatch):
    upload = tmp_path / "result.mp4"
    upload.touch()
    monkeypatch.setenv("EDITOR_TELEGRAM_DOWNLOAD_RELAY_URL", "https://relay.example/api/download")
    monkeypatch.setattr(tg, "_config", lambda: ("token", "secret", "https://editor.rafiei.co"))
    monkeypatch.setattr(tg, "_media_url", AsyncMock(return_value="https://editor.rafiei.co/api/integrations/telegram/media/ticket"))
    send = AsyncMock()
    monkeypatch.setattr(tg, "_send", send)
    replies = [httpx.Response(200, json={"offset": 4194304, "session": "sealed"}),
               httpx.Response(200, json={"sent": True})]
    post = AsyncMock(side_effect=replies)
    client = AsyncMock()
    client.__aenter__.return_value = SimpleNamespace(post=post)
    monkeypatch.setattr(tg.httpx, "AsyncClient", lambda **options: client)
    db = SimpleNamespace(get=AsyncMock(side_effect=lambda key: "owner" if ":tg:" in key else None),
                         set=AsyncMock(), delete=AsyncMock())
    asyncio.run(tg._send_output_file(db, "token", 123, "conversation", "owner", upload, 27_000_000, "render", "id"))
    assert post.await_count == 2
    first, final = [call.kwargs["json"] for call in post.call_args_list]
    assert first["offset"] == 0 and final["offset"] == 4194304
    assert final["session"] == "sealed" and first["randomId"] == final["randomId"]
    assert post.call_args.args[0] == "https://relay.example/api/upload"
    send.assert_not_awaited()


def test_oversize_output_falls_back_to_private_download(tmp_path, monkeypatch):
    download = "https://editor.rafiei.co/api/integrations/telegram/media/private-ticket"
    monkeypatch.setattr(tg, "_config", lambda: ("token", "secret", "https://editor.rafiei.co"))
    monkeypatch.setattr(tg, "_media_url", AsyncMock(return_value=download))
    send = AsyncMock()
    monkeypatch.setattr(tg, "_send", send)
    asyncio.run(tg._send_output_file(None, "token", 123, "conversation", "owner", tmp_path / "video.mp4",
                                     2_001_000_000, "", "id"))
    assert send.call_args.kwargs["buttons"][0][0]["url"] == download
