import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import long_video, studio_store
from creative import discovery, llm
from engine import long_transcribe as lt

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def store(tmp_path, monkeypatch):
    from app import jobs
    monkeypatch.setattr(jobs, "JOBS_ROOT", tmp_path)
    monkeypatch.setattr(studio_store, "DB_AVAILABLE", False)
    monkeypatch.setattr(studio_store, "ROOT", tmp_path)
    monkeypatch.setattr(long_video, "ROOT", tmp_path)
    monkeypatch.setattr(studio_store, "FALLBACK", tmp_path / "studio.json")
    return studio_store.repo


class Whisper:
    """One 10-second segment of four words per 10 s of audio; words carry real offsets."""
    def transcribe(self, audio, language=None, **kw):
        seconds = len(audio) / lt.SAMPLE_RATE
        segs = []
        for k in range(int(seconds // 10)):
            words = [SimpleNamespace(word=f" واژه{k}_{i}", start=k * 10 + 0.5 + i * 2, end=k * 10 + 1.5 + i * 2, probability=0.9) for i in range(4)]
            segs.append(SimpleNamespace(text=" ".join(w.word.strip() for w in words), words=words, avg_logprob=-0.2, no_speech_prob=0.0))
        return iter(segs), SimpleNamespace(language="fa", language_probability=0.98)


class FakeAI:
    """Answers each schema the way the real model would, from what it is shown."""
    def __init__(self, drop_every=0):
        self.calls = []

    def __call__(self, schema, system, user, **kw):
        self.calls.append(schema.__name__)
        if schema is discovery.EnhancedBatch:
            data = json.loads(user)
            return discovery.EnhancedBatch(items=[{"id": s["id"], "text": "کلمه".join(s["text"].rsplit("واژه", 1)), "uncertain": []} for s in data["segments"]])
        if schema is discovery.WindowTopics:
            return discovery.WindowTopics(topics=[{"title": "موضوع", "summary": "خلاصه", "start": 0, "end": 60}])
        if schema is discovery.Outline:
            return discovery.Outline(overview="یک سخنرانی", kind="lecture", topics=[{"title": "موضوع", "summary": "x", "start": 0, "end": 60}])
        if schema is discovery.CandidateBatch:
            # offers a clip starting at S3..S6 of the window and the same idea again (a duplicate) plus one far too short
            ids = [int(x) for x in __import__("re").findall(r"^S(\d+) ", user, flags=__import__("re").M)]
            a = ids[3] if len(ids) > 8 else ids[0]
            cands = [{"title": f"نکتهٔ {a}", "summary": "توضیح", "hook": "هوک", "category": "آموزشی", "ranges": [{"from": f"S{a}", "to": f"S{a + 3}"}],
                      "rationale": "دلیل", "scores": {"hook": 8, "standalone": 8, "value": 7}},
                     {"title": f"نکتهٔ {a}", "summary": "توضیح", "hook": "هوک", "category": "آموزشی", "ranges": [{"from": f"S{a}", "to": f"S{a + 3}"}],
                      "rationale": "تکرار", "scores": {"hook": 5}},
                     {"title": "خیلی کوتاه", "summary": "x", "hook": "y", "ranges": [{"from": f"S{a}", "to": f"S{a}"}], "scores": {"hook": 9}}]
            return discovery.CandidateBatch(candidates=cands)
        if schema is discovery.VerdictBatch:
            data = json.loads(user)
            return discovery.VerdictBatch(verdicts=[{"index": c["index"], "keep": True, "standalone": 8, "title": c["title"], "hook": c["hook"], "reason": "مستقل"} for c in data["candidates"]])
        raise AssertionError(schema)


@pytest.fixture
def analysis(store, tmp_path, monkeypatch):
    source = tmp_path / "talk.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=300:duration=250", "-f", "lavfi", "-i", "color=c=black:s=96x160:d=250:r=5",
                    "-shortest", "-pix_fmt", "yuv420p", str(source)], check=True)
    monkeypatch.setattr(lt, "_model", lambda *a, **k: Whisper())
    monkeypatch.setattr(lt, "plan_chunks", lambda d, s, **k: [(0.0, 120.0), (120.0, 250.0)])
    events, said = [], []
    monkeypatch.setattr(long_video, "_emit", lambda cid, kind, **data: events.append((kind, data)))
    monkeypatch.setattr(long_video, "_assistant", lambda cid, user, text: said.append(text))
    ai = FakeAI()
    monkeypatch.setattr(llm, "ask", ai)
    conversation = run(store.create_conversation("u", "پادکست"))
    attachment = run(store.create_attachment(conversation["id"], "u", kind="video", filename="talk.mp4", path=str(source), mime_type="video/mp4", size_bytes=source.stat().st_size))
    created = long_video.create(conversation["id"], "u", attachment, "ریلز دربیار")
    directory = long_video.folder("u", conversation["id"], created["id"])
    return SimpleNamespace(directory=directory, events=events, said=said, ai=ai, conversation=conversation, source=source)


def test_whole_flow_streams_transcribes_enhances_finds_and_dedupes(analysis, monkeypatch):
    monkeypatch.setattr(discovery, "WINDOW_S", 100.0)
    long_video._run(analysis.directory)
    kinds = [k for k, _ in analysis.events]
    assert kinds[0] == "transcription.started" and "transcription.segment.completed" in kinds and "transcription.completed" in kinds
    assert kinds.index("transcription.completed") < kinds.index("content.discovery.started") < kinds.index("content.candidate.found") < kinds.index("content.discovery.completed")
    state = long_video.load(analysis.directory)
    assert state["transcription_status"] == "completed" and state["discovery_status"] == "completed" and state["language"] == "fa" and state["transcript_version"]
    # raw and enhanced versions are both kept; the model changed words, not timing
    transcript = json.loads((analysis.directory / "transcript.json").read_text())["segments"]
    raw = json.loads((analysis.directory / "raw.json").read_text())["segments"]
    assert len(transcript) == len(raw) == 25 and transcript[0]["text"].startswith("واژه") and "کلمه" in transcript[0]["enhanced_text"] and transcript[0]["changed"]
    assert [s["start"] for s in transcript] == [s["start"] for s in raw]
    # candidates: duplicates and too-short ideas are gone; boundaries sit on real word edges
    cands = state["candidates"]
    assert cands and len({c["id"] for c in cands}) == len(cands) and all(c["status"] == "discovered" for c in cands)
    assert all(discovery.MIN_CLIP_S <= c["estimated_duration"] <= discovery.MAX_CLIP_S * 1.2 for c in cands)
    words = [w for s in raw for w in s["words"]]
    for c in cands:
        start, end = c["ranges"][0]
        assert any(abs(w["start"] - start) <= 0.15 for w in words) and any(abs(w["end"] - end) <= 0.35 for w in words)
    assert len([c for c in cands if c["title"].startswith("نکتهٔ")]) == len({c["title"] for c in cands})
    assert analysis.said and "محتوای مستقل" in analysis.said[-1]


def test_a_crash_resumes_without_transcribing_or_asking_the_model_again(analysis, monkeypatch):
    monkeypatch.setattr(discovery, "WINDOW_S", 100.0)
    real = lt.transcribe_chunk
    calls = {"n": 0}
    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("worker killed")
        return real(*a, **k)
    monkeypatch.setattr(lt, "transcribe_chunk", flaky)
    with pytest.raises(RuntimeError):
        long_video._run(analysis.directory)
    assert (analysis.directory / "chunks" / "0000.json").is_file() and not (analysis.directory / "chunks" / "0001.json").is_file()
    monkeypatch.setattr(lt, "transcribe_chunk", real)
    analysis.events.clear()
    long_video._run(analysis.directory)
    cached = [d["cached"] for k, d in analysis.events if k == "transcription.chunk.completed"]
    assert cached[0] is True and cached[1] is False                    # chunk 0 was reused, only chunk 1 was heard
    assert long_video.load(analysis.directory)["discovery_status"] == "completed"
    before = len(analysis.ai.calls)
    again = long_video.load(analysis.directory)
    again["discovery_status"] = "running"; long_video.save(analysis.directory, again)
    long_video._run(analysis.directory)
    assert len(analysis.ai.calls) - before == 0 or set(analysis.ai.calls[before:]) <= {"VerdictBatch"}      # windows and outline came from the cache


def test_editing_a_card_keeps_revisions_and_rejects_bad_ranges(analysis, monkeypatch):
    monkeypatch.setattr(discovery, "WINDOW_S", 100.0)
    long_video._run(analysis.directory)
    cid = long_video.load(analysis.directory)["candidates"][0]["id"]
    edited = long_video.edit_candidate(analysis.directory, cid, {"title": "عنوان تازه", "hook": "هوک تازه"})
    assert edited["title"] == "عنوان تازه" and edited["revisions"][0]["revision"] == 1
    moved = long_video.edit_candidate(analysis.directory, cid, {"ranges": [[10.0, 40.0]]})
    assert moved["ranges"] == [[10.0, 40.0]] and moved["estimated_duration"] == 30.0 and len(moved["revisions"]) == 2
    with pytest.raises(ValueError):
        long_video.edit_candidate(analysis.directory, cid, {"ranges": [[40.0, 10.0]]})
    hidden = long_video.edit_candidate(analysis.directory, cid, {"hidden": True})
    assert hidden["hidden"] is True and len(long_video.sorted_visible(long_video.load(analysis.directory))) == len(long_video.load(analysis.directory)["candidates"]) - 1


def test_child_chat_is_created_once_with_the_clip_and_the_transcript_seed(analysis, store, monkeypatch):
    monkeypatch.setattr(discovery, "WINDOW_S", 100.0)
    long_video._run(analysis.directory)
    dispatched = []
    from app import studio_orchestrator
    monkeypatch.setattr(studio_orchestrator, "dispatch_message", lambda *a: dispatched.append(a))
    cid = long_video.load(analysis.directory)["candidates"][0]["id"]
    first = long_video.start_candidate(analysis.directory, cid)               # answers at once: the clip is cut in the background
    second = long_video.start_candidate(analysis.directory, cid)
    import time
    for _ in range(300):
        if dispatched:
            break
        time.sleep(0.1)
    assert first["created"] and not second["created"] and first["conversation_id"] == second["conversation_id"] and len(dispatched) == 1
    assert long_video.load(analysis.directory)["candidates"][0]["child_preparing"] is False
    child = run(store.get_conversation(first["conversation_id"], "u"))
    assert child["state"]["parent"]["candidate_id"] == cid and child["state"]["forced_intent"] == "talking"
    seed = json.loads(Path(child["state"]["seed_transcript_path"]).read_text())
    assert seed["words"] and seed["words"][0]["start"] < 1.5 and seed["duration"] > 9
    first_with_video = next(m for m in child["messages"] if m.get("attachments"))
    attachment = run(store.get_attachments(first_with_video["attachments"], first["conversation_id"], "u"))[0]
    from engine.probe import probe_duration
    assert abs(probe_duration(Path(attachment["path"])) - seed["duration"]) < 1.0       # the clip is cut from the shared source, not uploaded again
    assert long_video.load(analysis.directory)["candidates"][0]["status"] == "selected"


def test_chat_commands_are_understood():
    assert long_video.parse_chat_command("کلیپ سوم رو تدوین کن") == {"index": 3, "like": None}
    assert long_video.parse_chat_command("کلیپ پنجم رو مثل کلیپ دوم تدوین کن") == {"index": 5, "like": 2}
    assert long_video.parse_chat_command("کارت ۷ را شروع کن")["index"] == 7
    assert long_video.parse_chat_command("این چیه؟") is None


def test_a_correction_that_rewrites_instead_of_fixing_is_rejected():
    raw = "ما دربارهٔ سه اشتباه مهم در راه‌اندازی کسب‌وکار صحبت می‌کنیم"
    assert discovery.accept_enhancement(raw, "ما دربارهٔ سه اشتباه مهم در راه‌اندازی کسب و کار صحبت می‌کنیم.")
    assert not discovery.accept_enhancement(raw, "امروز به شما می‌گویم چگونه ثروتمند شوید و فروش را چند برابر کنید")     # a different sentence
    assert not discovery.accept_enhancement(raw, "")
    assert not discovery.accept_enhancement(raw, raw + " " + raw + " " + raw)


def test_segments_the_model_failed_to_correct_are_retried_before_discovery(analysis, monkeypatch):
    monkeypatch.setattr(discovery, "WINDOW_S", 100.0)
    real = analysis.ai
    state = {"fail": 2}
    def flaky(schema, system, user, **kw):
        if schema is discovery.EnhancedBatch and state["fail"] > 0:
            state["fail"] -= 1
            raise RuntimeError("502 upstream")
        return real(schema, system, user, **kw)
    monkeypatch.setattr(llm, "ask", flaky)
    long_video._run(analysis.directory)
    transcript = json.loads((analysis.directory / "transcript.json").read_text())["segments"]
    assert all("not_enhanced" not in s["flags"] for s in transcript) and all("کلمه" in s["enhanced_text"] for s in transcript)


def test_correction_falls_back_to_a_steadier_route_and_stops_at_its_deadline():
    calls = []
    def ask(schema, system, user, route=None, **kw):
        calls.append(route)
        if route == "long_video_enhance":
            raise RuntimeError("503 high demand")
        data = json.loads(user)
        return discovery.EnhancedBatch(items=[{"id": s["id"], "text": s["text"]} for s in data["segments"]])
    segments = [{"id": f"s{i}", "start": i, "end": i + 1, "text": f"متن شمارهٔ {i}", "words": []} for i in range(20)]
    out = discovery.enhance_segments(segments, ask=ask)
    assert all("not_enhanced" not in s["flags"] for s in out) and "creative_revision" in calls and calls[0] == "long_video_enhance"
    late = discovery.enhance_segments(segments, ask=ask, deadline=0.0)          # a deadline in the past: nothing is asked
    assert all("not_enhanced" in s["flags"] and s["enhanced_text"] == s["text"] for s in late)


def test_spelling_repairs_pass_the_guard_but_a_different_sentence_does_not():
    raw = "سی سال پیش همه پساندازم را گزاشتم رو یک فروشکاه اینلاین لباز ورزشی"
    assert discovery.accept_enhancement(raw, "سی ماه پیش همه پس‌اندازم را گذاشتم روی یک فروشگاه اینترنتی لوازم ورزشی.")
    assert not discovery.accept_enhancement(raw, "امروز دربارهٔ مدیریت زمان و تمرکز در محل کار صحبت می‌کنم و چند راه ساده می‌گویم.")
