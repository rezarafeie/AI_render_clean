import json
import shutil
import subprocess
from pathlib import Path

import pytest

from creative import directives, music_bed
from creative import motion_graphic as mg
from app import motion_graphic as app_mg

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is required")


def tone(path: Path, seconds: float, freq: int = 440) -> Path:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={seconds}", str(path)], check=True)
    return path


def seconds(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def test_directive_lines_choose_the_narrator_style_and_music_and_are_removed_from_the_brief():
    text, found = directives.parse("Narrator: Eric\nVoice style: Calm\nMusic: library, cinematic minimal\nScene 1\nروایت: hello")
    assert text == "Scene 1\nروایت: hello"
    assert found.narrator == "cjVigY5qzO86Huf0OWal" and found.style == "calm"
    assert found.music == "library" and found.music_words == "cinematic minimal" and found.notes == []


def test_persian_labels_synonyms_and_music_switches():
    _, found = directives.parse("راوی: Daniel\nسبک صدا: جدی\nموسیقی: بدون")
    assert found.narrator == "onwK4e9ZLuTAKqWW03F9" and found.style == "serious" and found.music == "off"
    assert directives.parse("Music: attached")[1].music == "attached"
    assert directives.parse("Voice style: natural")[1].style == ""
    assert directives.parse("Narrator: default")[1].narrator == ""


def test_what_cannot_be_understood_is_reported_not_guessed():
    _, found = directives.parse("Narrator: Nobody\nVoice style: sleepy")
    assert found.narrator is None and found.style is None and len(found.notes) == 2
    assert "Eric" in found.notes[0]


def test_text_without_directives_is_untouched():
    text, found = directives.parse("Make a launch film about our app.\nScene 1: music for everyone")
    assert text.endswith("music for everyone") and found.narrator is None and found.music is None


def test_create_applies_the_directives_to_the_record(tmp_path, monkeypatch):
    monkeypatch.setattr(app_mg, "ROOT", tmp_path)
    record = app_mg.create("c1", "u1", "Narrator: Eric\nVoice style: calm\nMusic: off\nA film.", voice_id="old", voice_style="")
    assert record["voice_id"] == "cjVigY5qzO86Huf0OWal" and record["voice_style"] == "calm"
    assert record["request"] == "A film." and record["music"]["mode"] == "off"


def test_attached_music_without_a_file_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(app_mg, "ROOT", tmp_path)
    record = app_mg.create("c1", "u1", "Music: attached\nA film.")
    assert any("پیوست" in note for note in record["directive_notes"])


@needs_ffmpeg
def test_the_bed_is_cut_to_the_film_length_and_ducks_under_the_voice(tmp_path):
    song = tone(tmp_path / "song.wav", 4)                        # shorter than the film: it must loop
    voice = tone(tmp_path / "voice.wav", 2, 880)
    out = music_bed.make_bed(song, tmp_path / "bed.m4a", 10.0, [{"path": str(voice), "start": 3.0, "duration": 2.0}])
    assert abs(seconds(out) - 10.0) < 0.25
    loud = subprocess.run(["ffmpeg", "-i", str(out), "-af", "astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-", "-f", "null", "-"],
                          capture_output=True, text=True).stdout
    levels = [float(line.split("=")[1]) for line in loud.splitlines() if "RMS_level" in line and "inf" not in line]
    assert levels and max(levels) > min(levels) + 3             # not flat: the bed gets quieter under the voice and fades at the ends


@needs_ffmpeg
def test_an_unreadable_music_file_is_refused(tmp_path):
    bad = tmp_path / "bad.mp3"; bad.write_bytes(b"not audio")
    with pytest.raises(ValueError):
        music_bed.make_bed(bad, tmp_path / "bed.m4a", 5.0, [])


def test_library_pick_prefers_the_track_that_matches_the_words(tmp_path, monkeypatch):
    from engine import library
    a = tmp_path / "upbeat-pop.mp3"; b = tmp_path / "calm-cinematic.mp3"
    a.write_bytes(b"x"); b.write_bytes(b"x")
    assets = [library.LibraryAsset(filename=a.name, category="music", path=str(a), tags=["pop", "upbeat"], duration_sec=60),
              library.LibraryAsset(filename=b.name, category="music", path=str(b), tags=["cinematic", "calm"], mood="minimal", duration_sec=30)]
    monkeypatch.setattr(library, "scan_category", lambda category: assets)
    path, label = music_bed.pick_from_library("cinematic minimal", 45)
    assert label == "calm-cinematic.mp3"


def test_no_music_in_the_library_is_said_plainly(tmp_path, monkeypatch):
    from engine import library
    monkeypatch.setattr(library, "scan_category", lambda category: [])
    audio, notes = app_mg._add_music(tmp_path, {"music": {"mode": "library", "words": "calm"}}, type("P", (), {"duration": 20})(), [])
    assert audio == [] and "کتابخانهٔ موسیقی" in notes[0]


@needs_ffmpeg
def test_attached_music_becomes_a_ducked_track_after_the_narration(tmp_path):
    song = tone(tmp_path / "song.wav", 6)
    voice = tone(tmp_path / "v.wav", 2, 700)
    plan = type("P", (), {"duration": 8})()
    app_mg.save(tmp_path, {"id": "x", "log": [], "status": "running"})
    audio, notes = app_mg._add_music(tmp_path, {"music": {"mode": "attached", "path": str(song), "name": "my.wav"}}, plan,
                                     [{"path": str(voice), "start": 0.25, "duration": 2.0}])
    assert [clip.get("role") for clip in audio] == [None, "music"] and notes == ["موسیقی: my.wav"]
    assert Path(audio[1]["path"]).is_file() and audio[1]["duration"] == 8
    again, _ = app_mg._add_music(tmp_path, {"music": {"mode": "attached", "path": str(song), "name": "my.wav"}}, plan, [audio[0]])
    assert again[1]["path"] == audio[1]["path"]               # the finished bed is reused, not mixed again


def test_the_page_plays_the_music_on_its_own_track(tmp_path):
    clip = tmp_path / "c.wav"; clip.write_bytes(b"RIFF")
    bed = tmp_path / "music_bed.m4a"; bed.write_bytes(b"x")
    page = mg.MotionPage(title="t", duration=5, scenes_html='<section class="hm-scene" id="s1"><p id="s1-a">hi</p></section>', build_js="tl.to('#s1-a',{opacity:1},0)",
                         audio=[{"path": str(clip), "start": 0.25, "duration": 3.5}, {"path": str(bed), "start": 0, "duration": 5, "role": "music"}])
    html = mg.assemble(page)
    assert '<audio id="vo1" src="assets/vo1.wav"' in html and 'data-track-index="1"' in html
    assert '<audio id="music" src="assets/music.m4a" data-start="0" data-duration="5" data-track-index="3">' in html
