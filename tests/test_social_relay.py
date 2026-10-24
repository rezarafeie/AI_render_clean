"""The Vercel social relay: Instagram through a downloader API (key stays on Vercel), yt-dlp as the fallback."""
import importlib.util
import sys
import types
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

SPEC = importlib.util.spec_from_file_location("social_relay", Path(__file__).resolve().parents[1] / "deploy/social-relay/api/index.py")
relay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(relay)
SECRET = "s" * 40
HEADERS = {"x-relay-secret": SECRET}
REEL = "https://www.instagram.com/reel/DefB-rxMrmo/"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("RELAY_SECRET", SECRET)
    monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
    return TestClient(relay.app)


@pytest.mark.parametrize("payload,expected", [
    ({"status": True, "result": {"video_url": "https://cdn.example/v/clip.mp4?sig=1", "video_img": "https://cdn.example/t.jpg"}}, "https://cdn.example/v/clip.mp4?sig=1"),
    ({"media": [{"type": "image", "url": "https://cdn.example/a.jpg"}, {"type": "video", "url": "https://cdn.example/stream/abc"}]}, "https://cdn.example/stream/abc"),
    ({"data": {"medias": [{"thumbnail": "https://cdn.example/t.png", "download_url": "https://cdn.example/dl/video.mp4"}]}}, "https://cdn.example/dl/video.mp4"),
    ({"result": [{"url": "https://cdn.example/x.mp4"}], "profile_pic_url": "https://cdn.example/p.jpg"}, "https://cdn.example/x.mp4"),
])
def test_the_video_link_is_found_in_different_response_shapes(payload, expected):
    assert relay._find_video_url(payload) == expected


@pytest.mark.parametrize("payload", [
    {"error": "Invalid Instagram link"}, {"media": []}, {"result": {"thumbnail": "https://cdn.example/t.jpg", "profile_pic_url": "https://cdn.example/p.jpg"}},
    {"caption": "https://example.com/some-page"}, {"video_url": "http://insecure.example/clip.mp4"},
])
def test_pictures_pages_and_errors_are_never_taken_for_the_video(payload):
    assert relay._find_video_url(payload) is None


def test_only_instagram_links_use_the_downloader_api():
    assert relay._instagram(REEL) and relay._instagram("https://instagram.com/p/x/") and not relay._instagram("https://www.youtube.com/watch?v=x")
    assert not relay._instagram("https://evilinstagram.com/reel/x")


def test_nothing_is_called_without_a_key(monkeypatch, tmp_path):
    monkeypatch.setattr(relay, "_rapid_call", lambda url: pytest.fail("no key, no call"))
    assert relay._rapid_download(REEL, tmp_path) is None


def _video(monkeypatch, tmp_path, body=b"x" * 5000):
    monkeypatch.setenv("RAPIDAPI_KEY", "k-" + "k" * 20)
    monkeypatch.setattr(relay, "_rapid_call", lambda url: {"result": {"video_url": "https://cdn.example/v.mp4"}})

    class Response:
        def __init__(self): self.left = body
        def read(self, n): out, self.left = self.left[:n], self.left[n:]; return out
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(relay.urllib.request, "urlopen", lambda request, timeout=0: Response())


def test_an_instagram_reel_is_downloaded_through_the_api_and_streamed(env, monkeypatch, tmp_path):
    _video(monkeypatch, tmp_path)
    yt = types.SimpleNamespace(utils=None)
    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=lambda o: pytest.fail("yt-dlp must not run when the API worked"), utils=None))
    response = env.post("/api/index", json={"url": REEL}, headers=HEADERS)
    assert response.status_code == 200 and response.headers["x-source-extractor"] == "rapidapi" and len(response.content) == 5000


def test_when_the_api_has_nothing_yt_dlp_is_the_fallback(env, monkeypatch):
    monkeypatch.setenv("RAPIDAPI_KEY", "k-" + "k" * 20)
    monkeypatch.setattr(relay, "_rapid_call", lambda url: {"error": "private account"})

    class YDL:
        def __init__(self, options): self.options = options
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, url, download=True):
            (Path(self.options["outtmpl"]).parent / "video.mp4").write_bytes(b"y" * 3000)
            return {"title": "t", "duration": 9, "extractor_key": "Instagram"}

    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=YDL, utils=types.SimpleNamespace(match_filter_func=lambda s: None), version=types.SimpleNamespace(__version__="x")))
    response = env.post("/api/index", json={"url": REEL}, headers=HEADERS)
    assert response.status_code == 200 and response.headers["x-source-extractor"] == "Instagram" and len(response.content) == 3000


def test_an_oversized_file_is_refused_and_other_sites_skip_the_api(env, monkeypatch, tmp_path):
    _video(monkeypatch, tmp_path)
    monkeypatch.setattr(relay, "MAX_BYTES", 1000)
    assert relay._rapid_download(REEL, tmp_path) is None
    calls = []
    monkeypatch.setattr(relay, "_rapid_call", lambda url: calls.append(url) or {})
    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=lambda o: (_ for _ in ()).throw(RuntimeError("no")), utils=types.SimpleNamespace(match_filter_func=lambda s: None)))
    assert env.post("/api/index", json={"url": "https://www.tiktok.com/@a/video/1"}, headers=HEADERS).status_code == 502 and calls == []


def test_the_secret_is_still_required_and_the_health_page_never_shows_the_key(env, monkeypatch):
    monkeypatch.setenv("RAPIDAPI_KEY", "k-" + "k" * 20)
    assert env.post("/api/index", json={"url": REEL}).status_code == 401
    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(version=types.SimpleNamespace(__version__="9")))
    health = env.get("/api/index").json()
    assert health["rapidapi"] is True and "k-kkkk" not in str(health)
