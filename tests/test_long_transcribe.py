import json
import shutil
import subprocess
import wave
from types import SimpleNamespace

import pytest

from engine import long_transcribe as lt

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")


def test_chunks_land_in_pauses_and_cover_everything():
    silences = [(298.0, 299.2), (301.0, 301.5), (590.0, 591.0), (905.0, 905.6), (1202.0, 1203.0)]
    chunks = lt.plan_chunks(1500.0, silences)
    assert chunks[0][0] == 0.0 and chunks[-1][1] == 1500.0
    assert all(a[1] == b[0] for a, b in zip(chunks, chunks[1:]))               # no gaps, no overlaps
    edges = [c[1] for c in chunks[:-1]]
    assert any(abs(e - 298.6) < 0.1 for e in edges) or any(abs(e - 299.2) < 1 for e in edges)      # snapped into the longest pause near 300 s
    assert all(c[1] - c[0] >= 200 for c in chunks)
    assert lt.plan_chunks(120.0, []) == [(0.0, 120.0)]


def test_model_choice_follows_the_machine(monkeypatch):
    monkeypatch.delenv("LONGVIDEO_WHISPER_MODEL", raising=False)
    assert lt.choose_model(1800, 4) == "small" and lt.choose_model(1800, 2) == "base" and lt.choose_model(7200, 4) == "base"
    monkeypatch.setenv("LONGVIDEO_WHISPER_MODEL", "tiny")
    assert lt.choose_model(1800, 8) == "tiny"


class FakeModel:
    """Stands in for faster-whisper: one segment per 10 s of audio, with words."""
    def __init__(self):
        self.calls = 0

    def transcribe(self, audio, language=None, **kw):
        self.calls += 1
        seconds = len(audio) / lt.SAMPLE_RATE
        segs = []
        for k in range(int(seconds // 10)):
            words = [SimpleNamespace(word=f" کلمه{k}_{i}", start=k * 10 + i * 0.5, end=k * 10 + i * 0.5 + 0.4, probability=0.9) for i in range(4)]
            segs.append(SimpleNamespace(text=" ".join(w.word.strip() for w in words), words=words, avg_logprob=-0.3, no_speech_prob=0.01))
        return iter(segs), SimpleNamespace(language="fa", language_probability=0.97)


@pytest.fixture(scope="module")
def video(tmp_path_factory):
    path = tmp_path_factory.mktemp("lt") / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=300:duration=130", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=130:r=5",
                    "-shortest", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def test_chunked_run_streams_real_segments_and_resumes_without_redoing_chunks(video, tmp_path, monkeypatch):
    monkeypatch.setattr(lt, "TARGET_CHUNK_S", 50.0)
    monkeypatch.setattr(lt, "plan_chunks", lambda d, s, target=50.0, window=lt.SNAP_WINDOW_S: [(0.0, 50.0), (50.0, 100.0), (100.0, 130.0)])
    events, model = [], FakeModel()
    raw = lt.transcribe_long(video, tmp_path, language="fa", model_name="base", on_event=lambda k, d: events.append((k, d)), model=model)
    kinds = [k for k, _ in events]
    assert kinds[0] == "transcription.started" and kinds[-1] == "transcription.completed" and model.calls == 3
    assert kinds.count("transcription.chunk.completed") == 3 and "transcription.segment.completed" in kinds
    progress = [d["percent"] for k, d in events if k == "transcription.progress"]
    assert progress == sorted(progress) and progress[-1] == 100.0
    assert len(raw["segments"]) == 13 and raw["language"] == "fa" and raw["segments"][0]["start"] == 0.0
    assert raw["segments"][5]["start"] >= 50.0                                            # absolute times: the second chunk is offset
    # resume: a crash after chunk 1 re-runs only what is missing
    (tmp_path / "chunks" / "0002.json").unlink()
    (tmp_path / "chunks" / "0001.json").unlink()
    again = FakeModel()
    events.clear()
    lt.transcribe_long(video, tmp_path, language="fa", model_name="base", on_event=lambda k, d: events.append((k, d)), model=again)
    assert again.calls == 2 and [d["cached"] for k, d in events if k == "transcription.chunk.completed"] == [True, False, False]


def test_stop_request_keeps_finished_chunks(video, tmp_path, monkeypatch):
    monkeypatch.setattr(lt, "plan_chunks", lambda d, s, target=50.0, window=lt.SNAP_WINDOW_S: [(0.0, 65.0), (65.0, 130.0)])
    def stop():                                           # Stop arrives once the first piece is on disk
        return (tmp_path / "chunks" / "0000.json").is_file()
    with pytest.raises(lt.Stopped):
        lt.transcribe_long(video, tmp_path, language="fa", model_name="base", should_stop=stop, model=FakeModel())
    assert (tmp_path / "chunks" / "0000.json").is_file() and not (tmp_path / "chunks" / "0001.json").is_file()


def test_threads_leave_room_for_the_rest_of_the_machine(monkeypatch):
    monkeypatch.delenv("LONGVIDEO_CPU_THREADS", raising=False)
    monkeypatch.setattr(lt.os, "cpu_count", lambda: 4)
    assert lt.cpu_threads() == 2
    monkeypatch.setattr(lt.os, "cpu_count", lambda: 16)
    assert lt.cpu_threads() == 4
    monkeypatch.setenv("LONGVIDEO_CPU_THREADS", "3")
    assert lt.cpu_threads() == 3
