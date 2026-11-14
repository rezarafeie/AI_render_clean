"""Cutting a clip from a long video reports real progress and can be stopped (the chat showed nothing for minutes)."""
import shutil
import subprocess

import pytest

from app import long_video

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")


@pytest.fixture()
def source(tmp_path):
    path = tmp_path / "long.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25", "-f", "lavfi", "-i", "sine=frequency=440", "-t", "6",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(path)], check=True)
    return path


def test_the_cut_reports_progress_up_to_the_end(tmp_path, source):
    seen = []
    out = long_video.render_clip(source, [[1.0, 4.0]], tmp_path / "clip.mp4", small=False, on_progress=seen.append)
    assert out.is_file() and out.stat().st_size > 0
    assert seen and seen[-1] > 0.9 and all(0 <= x <= 1 for x in seen)


def test_stop_ends_the_cut_and_leaves_no_clip(tmp_path, source):
    with pytest.raises(long_video.PrepareStopped):
        long_video.render_clip(source, [[0.0, 5.0]], tmp_path / "clip.mp4", small=False, on_progress=lambda f: None, should_stop=lambda: True)
    assert not (tmp_path / "clip.mp4").exists()


def test_stop_prepare_only_answers_for_a_chat_being_cut():
    import threading
    assert long_video.stop_prepare("nobody") is False
    long_video._PREP_STOP["chat1"] = threading.Event()
    try:
        assert long_video.stop_prepare("chat1") is True and long_video._PREP_STOP["chat1"].is_set()
    finally:
        long_video._PREP_STOP.pop("chat1", None)
