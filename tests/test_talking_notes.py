"""Talking reels write a step log the chat shows (like the motion designer's notes), and style 5 has a preview frame."""
import json
import subprocess
from pathlib import Path

from app import studio_assets, talking_reel


def test_notes_are_appended_in_order_and_read_back(tmp_path):
    talking_reel.note(tmp_path, "گفتار آماده است", stage="transcript", done=True)
    talking_reel.note(tmp_path, "طراحی پنل‌ها", stage="designing panels", detail="1. الف\n2. ب")
    notes = studio_assets.talking_notes(tmp_path)
    assert [n["stage"] for n in notes] == ["transcript", "designing panels"] and notes[0]["done"] and notes[1]["detail"].startswith("1.")


def test_panel_frames_become_assets_only_when_they_live_inside_the_job_folder(tmp_path):
    frames = tmp_path / "panel_frames"
    frames.mkdir()
    (frames / "panel1.jpg").write_bytes(b"\xff\xd8x")
    talking_reel.note(tmp_path, "فریم پنل‌ها", stage="panel previews", done=True, frames=[{"n": 1, "t": 3.2, "title": "منبع اول", "file": frames / "panel1.jpg"}])
    entry = studio_assets.talking_notes(tmp_path)[0]
    assets = studio_assets.note_frames(tmp_path, entry)
    assert assets == [{"kind": "image", "scene": 1, "group": "پیش‌نمایش پنل‌های طراحی‌شده (پیش از رندر)", "label": "پنل 1 · منبع اول", "src": "panel_frames/panel1.jpg"}]
    entry["frames"][0]["src"] = "../../etc/passwd"
    assert studio_assets.note_frames(tmp_path, entry) == []


def test_a_note_outside_the_job_folder_never_raises(tmp_path):
    talking_reel.note(tmp_path, "x", frames=[{"n": 1, "file": Path("/etc/hosts")}])        # logged away, the reel goes on
    assert studio_assets.talking_notes(tmp_path) == []


def test_style_5_has_a_preview_frame_like_the_other_styles(tmp_path):
    from engine.style_frames import BUILDERS, render_mockup
    assert "talking_5" in BUILDERS
    video = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=s=640x360:d=2:r=25", "-f", "lavfi", "-i", "sine=d=2", "-shortest", str(video)], check=True)
    out = render_mockup(video, tmp_path / "p.jpg", style_id="talking_5", at=1.0, hook="هوک", caption="یک جملهٔ نمونه", card="کارت")
    assert out.is_file() and out.stat().st_size > 2000
