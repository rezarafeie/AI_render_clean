"""The long-video chat shows its work: steps with state, elapsed time, narration and log, and the transcript as it is heard."""
import json
import shutil
import sys
import subprocess
from types import SimpleNamespace

import pytest

from app import long_video
from creative import discovery, llm
from engine import long_transcribe as lt
from tests.test_long_video import FakeAI, Whisper, run, store  # noqa: F401  (fixtures reused)

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")


@pytest.fixture
def analysis(store, tmp_path, monkeypatch):
    from app import studio_store, transcribe_prefs
    source = tmp_path / "talk.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=300:duration=250", "-f", "lavfi", "-i", "color=c=black:s=96x160:d=250:r=5",
                    "-shortest", "-pix_fmt", "yuv420p", str(source)], check=True)
    monkeypatch.setattr(lt, "_model", lambda *a, **k: Whisper())
    monkeypatch.setattr(lt, "plan_chunks", lambda d, s, **k: [(0.0, 120.0), (120.0, 250.0)])
    monkeypatch.setattr(transcribe_prefs, "get", lambda user: {"engine": "whisper", "whisper_model": ""})
    events, said = [], []
    monkeypatch.setattr(long_video, "_emit", lambda cid, kind, **data: events.append((kind, data)))
    monkeypatch.setattr(long_video, "_assistant", lambda cid, user, text: said.append(text))
    monkeypatch.setattr(long_video, "prepare_media_in_background", lambda *a, **k: None)
    monkeypatch.setattr(long_video, "ensure_media", lambda *a, **k: None)
    monkeypatch.setattr(llm, "ask", FakeAI())
    monkeypatch.setattr(discovery, "WINDOW_S", 100.0)
    conversation = run(store.create_conversation("u", "پادکست"))
    attachment = run(store.create_attachment(conversation["id"], "u", kind="video", filename="talk.mp4", path=str(source), mime_type="video/mp4", size_bytes=source.stat().st_size))
    created = long_video.create(conversation["id"], "u", attachment, "ریلز دربیار")
    directory = long_video.folder("u", conversation["id"], created["id"])
    return SimpleNamespace(directory=directory, events=events, said=said, source=source)


def steps_of(directory):
    return {s["key"]: s for s in long_video.load(directory)["steps"]}


def test_every_stage_is_a_step_with_state_narration_and_log_in_order(analysis):
    long_video._run(analysis.directory)
    steps = long_video.load(analysis.directory)["steps"]
    assert [s["key"] for s in steps] == ["file", "audio", "transcribe", "enhance", "outline", "find", "cards"][:len(steps)]
    assert [s["key"] for s in steps][:6] == ["file", "audio", "transcribe", "enhance", "outline", "find"]
    for step in steps[:6]:
        assert step["state"] == "done" and step["narration"] and step["log"] and step["done_at"] >= step["at"] and step["label"]
    by = {s["key"]: s for s in steps}
    assert by["transcribe"]["label"].startswith("رونویسی با Whisper") and any("2 تکه" in l["text"] for l in by["transcribe"]["log"])
    assert any("تکه 1 از 2" in line["text"] for line in by["transcribe"]["log"]) and any("تکه 2 از 2" in line["text"] for line in by["transcribe"]["log"])
    assert by["transcribe"]["progress"] == 100
    assert any("پذیرفته شد" in line["text"] for line in by["find"]["log"])
    assert by["find"]["note"].endswith("کاندیدا")
    # the view hands the same steps to a page that was just refreshed
    assert [s["key"] for s in long_video.view(analysis.directory)["steps"]] == [s["key"] for s in steps]


def test_sentences_are_published_the_moment_a_batch_is_heard_and_survive_a_refresh(analysis):
    seen = []
    real = long_video._live_add

    def spy(directory, segments):
        real(directory, segments)
        seen.append((len(json.loads((directory / "live.json").read_text())), long_video.view(directory)["transcript_tail"][-1]["text"]))

    long_video._live_add = spy
    try:
        long_video._run(analysis.directory)
    finally:
        long_video._live_add = real
    assert seen and seen[0][0] <= 3 and seen[-1][0] > seen[0][0]                  # it grows while the audio is still being heard, not at the end
    batches = [d["segments"] for k, d in analysis.events if k == "transcription.segment.completed"]
    assert len(batches) > 1 and all(b for b in batches)


def test_a_stop_closes_the_working_step_as_stopped_and_a_resume_continues_from_the_saved_pieces(analysis, monkeypatch):
    real = lt.transcribe_chunk
    calls = {"n": 0}

    def stops(*a, **k):
        calls["n"] += 1
        if calls["n"] == 2:
            raise lt.Stopped("stopped")
        return real(*a, **k)

    monkeypatch.setattr(lt, "transcribe_chunk", stops)
    with pytest.raises(lt.Stopped):
        long_video._run(analysis.directory)
    long_video._close_steps(analysis.directory, "stopped", "شما متوقف کردید.")
    steps = steps_of(analysis.directory)
    assert steps["transcribe"]["state"] == "stopped" and steps["transcribe"]["log"][-1]["text"] == "شما متوقف کردید." and steps["file"]["state"] == "done"
    assert steps["transcribe"]["done_at"] >= steps["transcribe"]["at"]
    monkeypatch.setattr(lt, "transcribe_chunk", real)
    long_video._run(analysis.directory)
    steps = steps_of(analysis.directory)
    assert steps["transcribe"]["state"] == "done" and any("از قبل ذخیره بود" in l["text"] for l in steps["transcribe"]["log"])
    assert steps["find"]["state"] == "done"


def test_a_failure_marks_the_working_step_failed_with_the_reason(analysis, monkeypatch):
    monkeypatch.setattr(lt, "transcribe_chunk", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("provider down")))
    with pytest.raises(RuntimeError):
        long_video._run(analysis.directory)
    long_video._close_steps(analysis.directory, "failed", "خطا: provider down")
    step = steps_of(analysis.directory)["transcribe"]
    assert step["state"] == "failed" and "provider down" in step["log"][-1]["text"]


def test_a_step_that_changes_nothing_writes_and_announces_nothing(analysis):
    long_video._step(analysis.directory, "file", "active", note="x")
    count = len(analysis.events)
    long_video._step(analysis.directory, "file", "active", note="x")
    assert len(analysis.events) == count


def test_elevenlabs_pieces_stream_in_as_each_returns_and_a_stop_keeps_what_was_heard(analysis, tmp_path, monkeypatch):
    from brain import transcribe_elevenlabs as el
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test")
    monkeypatch.setenv("ELEVENLABS_PROXY_URL", "https://relay.example.test")
    calls = []

    class Client:
        def __init__(self, **k):
            self.speech_to_text = self

        def convert(self, file, request_options=None, **k):
            index = len(calls)
            calls.append(index)
            words = [SimpleNamespace(type="word", text=f"واژه{index}_{i}" + ("." if i == 3 else ""), logprob=-0.1, start=i * 2.0, end=i * 2.0 + 1.0) for i in range(4)]
            return SimpleNamespace(words=words, language_code="fa")

    monkeypatch.setitem(sys.modules, "elevenlabs", SimpleNamespace(ElevenLabs=Client))
    got = []
    out = tmp_path / "eleven"
    out.mkdir()
    transcript, cost = el.transcribe_elevenlabs(analysis.source, out, language="fa", file_digest="abc", on_event=lambda k, d: got.append((k, d)), chunk_s=100)
    kinds = [k for k, _ in got]
    assert kinds[:2] == ["audio.started", "audio.done"] and kinds.count("piece.started") == 3 and kinds.count("piece.done") == 3
    done = [d for k, d in got if k == "piece.done"]
    assert all(d["sentences"] for d in done) and sorted(d["heard"] for d in done) == [1, 2, 3]
    starts = sorted(s["start"] for d in done for s in d["sentences"])
    assert starts[0] < 10 and starts[-1] >= 200 and len(transcript["sentences"]) == 3
    # a second run of the same file hears nothing again (the whole transcript is archived)
    calls.clear()
    el.transcribe_elevenlabs(analysis.source, out, language="fa", file_digest="abc", on_event=lambda k, d: got.append((k, d)), chunk_s=100)
    assert not calls and got[-1][0] == "cached"


def test_elevenlabs_stop_between_pieces_keeps_the_heard_pieces_for_the_resume(analysis, tmp_path, monkeypatch):
    from brain import transcribe_elevenlabs as el
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test")
    monkeypatch.setenv("ELEVENLABS_PROXY_URL", "https://relay.example.test")
    calls = []

    class Client:
        def __init__(self, **k):
            self.speech_to_text = self

        def convert(self, file, request_options=None, **k):
            calls.append(1)
            return SimpleNamespace(words=[SimpleNamespace(type="word", text="سلام.", logprob=-0.1, start=1.0, end=2.0)], language_code="fa")

    monkeypatch.setitem(sys.modules, "elevenlabs", SimpleNamespace(ElevenLabs=Client))
    heard = []
    out = tmp_path / "eleven"
    out.mkdir()
    with pytest.raises(RuntimeError):
        el.transcribe_elevenlabs(analysis.source, out, language="fa", file_digest="abc", chunk_s=100, on_event=lambda k, d: heard.append(k),
                                 should_stop=lambda: heard.count("piece.done") >= 1)
    saved = list((out / "asr_pieces").glob("*.json"))
    assert saved and len(saved) < 3 + 1
    first = len(calls)
    el.transcribe_elevenlabs(analysis.source, out, language="fa", file_digest="abc", chunk_s=100)
    assert len(calls) - first <= 3 - len(saved)                                    # the pieces that were heard are not bought again


def test_elevenlabs_run_shows_each_piece_as_a_step_log_with_percent_and_streams_its_sentences(analysis, monkeypatch):
    from app import transcribe_prefs
    from brain import transcribe_elevenlabs as el
    monkeypatch.setattr(transcribe_prefs, "get", lambda user: {"engine": "elevenlabs", "whisper_model": ""})

    def fake(video, out_dir, *, language, file_digest, on_event, should_stop, chunk_s, **k):
        assert chunk_s == 300 and file_digest
        on_event("audio.started", {})
        on_event("audio.done", {"duration_s": 250.0, "seconds": 1.5})
        words, sentences = [], []
        for piece, (a, b) in enumerate([(0, 120), (120, 250)]):
            on_event("piece.started", {"index": piece, "pieces": 2, "start": a, "end": b})
            mine = []
            for i in range(4):
                w = {"w": f"واژه{piece}{i}" + ("." if i == 3 else ""), "start": a + 1 + i * 2.0, "end": a + 2 + i * 2.0, "prob": 0.9}
                words.append(w); mine.append(w)
            sentence = {"text": " ".join(w["w"] for w in mine), "start": mine[0]["start"], "end": mine[-1]["end"]}
            sentences.append(sentence)
            on_event("piece.done", {"index": piece, "pieces": 2, "start": a, "end": b, "cached": False, "heard": piece + 1, "seconds": 3,
                                    "sentences": [{"id": f"p{piece:03d}-000", **sentence}]})
        return {"duration": 250.0, "language": "fa", "words": words, "sentences": sentences, "requested_language": "fa"}, 0.03

    monkeypatch.setattr(el, "transcribe_elevenlabs", fake)
    long_video._run(analysis.directory)
    by = steps_of(analysis.directory)
    assert by["transcribe"]["label"] == "رونویسی با ElevenLabs" and by["transcribe"]["state"] == "done"
    log = [l["text"] for l in by["transcribe"]["log"]]
    assert any("تکه 1 از 2" in t and "به ElevenLabs رفت" in t for t in log) and any("تکه 2 از 2 برگشت: 1 جمله" in t for t in log)
    assert by["audio"]["state"] == "done" and by["file"]["state"] == "done" and any("شناسهٔ فایل" in l["text"] for l in by["file"]["log"])
    assert by["enhance"]["state"] == "done" and by["enhance"]["note"] == "نیاز نبود"
    live = [d["segments"] for k, d in analysis.events if k == "transcription.segment.completed"]
    assert [len(x) for x in live] == [1, 1]
    progress = [d["percent"] for k, d in analysis.events if k == "transcription.progress"]
    assert progress[0] == 48.0 and progress[-1] == 100
    assert long_video.load(analysis.directory)["discovery_status"] == "completed"
