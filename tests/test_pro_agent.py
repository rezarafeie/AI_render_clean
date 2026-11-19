"""EditorGPT Pro guards (docs/PRO_AGENT_PLAN.md): the run token, the per-chat folder, the PreToolUse policy, the proxy's image lift and the runner's
handling of a resumed session. Runs under pytest, or directly (`python tests/test_pro_agent.py`) inside the app / agent containers, which have no pytest."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("PRO_WORKER_SECRET", "test-secret-" + "x" * 40)
os.environ["PRO_RUNS_DIR"] = tempfile.mkdtemp(prefix="pro-runs-")

from app.agents import pro  # noqa: E402

pro.RUNS = Path(os.environ["PRO_RUNS_DIR"])


def test_token_roundtrip_and_tamper():
    value = pro.token("run1", "7", "abc123")
    claims = pro.verify(value)
    assert (claims["run"], claims["user"], claims["cid"]) == ("run1", "7", "abc123")
    body, sig = value.split(".")
    for bad in (body + "." + sig[:-2] + "AA", body[:-2] + "e30." + sig, "garbage", ""):
        try:
            pro.verify(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted a forged token: {bad[:20]}")


def test_token_expires():
    value = pro.token("run1", "7", "abc123", hours=-0.01)
    try:
        pro.verify(value)
    except ValueError as exc:
        assert "expired" in str(exc)
    else:
        raise AssertionError("an expired token was accepted")


def test_workdir_and_inside():
    root = pro.workdir("abc123")
    root.mkdir(parents=True, exist_ok=True)
    assert pro.inside("abc123", "out/a.mp4") == (root / "out/a.mp4").resolve()
    for bad in ("../x", "/etc/passwd", "out/../../y"):
        try:
            pro.inside("abc123", bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad} escaped the chat folder")
    for bad_key in ("../abc", "a/b", ""):
        try:
            pro.workdir(bad_key)
        except ValueError:
            continue
        raise AssertionError(f"workdir accepted {bad_key!r}")


def _decide(hook, name, args):
    out = asyncio.run(hook({"tool_name": name, "tool_input": args}, "id", None))
    return (out.get("hookSpecificOutput") or {}).get("permissionDecision", "allow")


def test_policy_blocks_network_system_and_outside_paths():
    from app.agents.pro.runner import _policy
    work = pro.workdir("pol1")
    work.mkdir(parents=True, exist_ok=True)
    hook = _policy(work)
    denied = [("Bash", {"command": "curl https://example.com"}), ("Bash", {"command": "pip install requests"}),
              ("Bash", {"command": "cat /etc/passwd"}), ("Bash", {"command": "printenv"}), ("Bash", {"command": "ls /root/"}),
              ("Bash", {"command": "cp a.mp4 /srv/other/"}), ("Read", {"file_path": "/etc/hosts"}),
              ("Write", {"file_path": "/app/creative/x.py"}), ("Edit", {"file_path": "../../other/work/a.txt"})]
    for name, args in denied:
        assert _decide(hook, name, args) == "deny", (name, args)
    allowed = [("Bash", {"command": f"ffmpeg -i {work}/in/a.mp4 -c copy {work}/out/b.mp4"}), ("Bash", {"command": "ffprobe out/b.mp4"}),
               ("Read", {"file_path": "/app/remotion/package.json"}), ("Read", {"file_path": "/app/vendor/motion-skills/README.md"}),
               ("Write", {"file_path": str(work / "src" / "Scenes.tsx")}), ("Write", {"file_path": "timing.json"}),
               ("mcp__editorgpt__deliver", {"path": "out/b.mp4"})]
    for name, args in allowed:
        assert _decide(hook, name, args) == "allow", (name, args)


def test_proxy_lifts_images_out_of_tool_results():
    try:
        from app.routers.agent_proxy import _lift_tool_images
    except ImportError:                       # the agent container has no FastAPI app
        return
    image = {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "AAAA"}}
    data = {"messages": [{"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": [{"type": "text", "text": "still"}, image]},
        {"type": "text", "text": "go on"}]}]}
    assert _lift_tool_images(data) is True
    content = data["messages"][0]["content"]
    assert [b["type"] for b in content] == ["tool_result", "image", "text"]
    assert all(item["type"] != "image" for item in content[0]["content"])
    assert _lift_tool_images({"messages": [{"role": "user", "content": "plain"}]}) is False


def test_first_message_marks_a_follow_up():
    from app.agents.pro.prompt import first_message
    assert "ادامه بده" in first_message("ادامه بده", [], True)
    assert first_message("یک ویدیو بساز", ["a1"], False) != first_message("یک ویدیو بساز", ["a1"], True)


def test_policy_stops_reading_the_same_image_again_and_again():
    from app.agents.pro.runner import _policy
    work = pro.workdir("pol2")
    (work / "out").mkdir(parents=True, exist_ok=True)
    sheet = work / "out" / "sheet.jpg"
    sheet.write_bytes(b"\xff\xd8\xff")
    hook = _policy(work)
    decisions = [_decide(hook, "Read", {"file_path": str(sheet)}) for _ in range(4)]
    assert decisions == ["allow", "allow", "deny", "deny"], decisions
    os.utime(sheet, (time.time() + 5, time.time() + 5))      # a changed file may be looked at again
    assert _decide(hook, "Read", {"file_path": str(sheet)}) == "allow"


def test_runner_knows_when_the_model_service_is_out_of_tokens():
    from app.agents.pro.runner import API_ERROR, NO_ALLOCATION
    text = "API Error: 402 This request would exceed your remaining token allocation."
    assert API_ERROR.search(text) and NO_ALLOCATION.search(text)
    assert not NO_ALLOCATION.search("API Error: 500 Internal server error")


def test_proxy_gives_every_response_its_own_message_id():
    try:
        from app.routers.agent_proxy import _unique_message_id
    except ImportError:
        return
    head = b'event: message_start\ndata: {"type":"message_start","message":{"id":"msg_1tk","type":"message","role":"assistant"}}\n\n'
    a, b = _unique_message_id(head), _unique_message_id(head)
    assert b"msg_1tk" not in a and a != b and a.startswith(b"event: message_start")
    body = b'{"id":"msg_1tk","type":"message","content":[]}'
    out = _unique_message_id(body, stream=False)
    assert b"msg_1tk" not in out and out.endswith(b'"type":"message","content":[]}')


def test_anthropic_provider_serves_only_the_pro_agent():
    try:
        from brain import lm_direct
    except Exception:                         # the agent container has no gateway code
        return
    assert lm_direct.PROVIDERS["anthropic"].get("agent_only")
    original = lm_direct.key_for
    lm_direct.key_for = lambda pid: "test-key"
    try:
        assert "anthropic" not in [p["id"] for p in lm_direct.usable()]
        assert "anthropic" not in [p["id"] for p in lm_direct.usable(kind="speech")]
        switched_on = lm_direct.config()["enabled"] and next(p for p in lm_direct.config()["providers"] if p["id"] == "anthropic")["enabled"]
        assert "anthropic" in [p["id"] for p in lm_direct.usable(kind="agent")] or not switched_on
    finally:
        lm_direct.key_for = original


def test_pro_anthropic_uses_relay_and_jarvis_remains_direct():
    from unittest.mock import patch

    from fastapi import HTTPException
    from app.config import settings
    from app.routers import agent_proxy
    from brain import lm_direct

    providers = [
        {"id": "jarvis", "base_url": "https://jarvis.example/v1/"},
        {"id": "anthropic", "base_url": "https://api.anthropic.com/v1"},
    ]
    with patch.object(lm_direct, "usable", return_value=providers), patch.object(lm_direct, "key_for", side_effect=lambda pid: f"test-{pid}"):
        with patch.object(settings, "GEMINI_RELAY_SECRET", "x" * 32):
            assert agent_proxy._provider() == (agent_proxy.ANTHROPIC_RELAY, {
                "x-api-key": "test-anthropic", "x-relay-secret": "x" * 32,
            })
        with patch.object(settings, "GEMINI_RELAY_SECRET", ""):
            try:
                agent_proxy._provider()
            except HTTPException as exc:
                assert exc.status_code == 503
            else:
                raise AssertionError("Configured Anthropic must never bypass the relay")
    with patch.object(lm_direct, "usable", return_value=providers[:1]), patch.object(lm_direct, "key_for", return_value="test-jarvis"):
        assert agent_proxy._provider() == ("https://jarvis.example/v1/messages", {"x-api-key": "test-jarvis"})


def test_admin_test_uses_the_same_anthropic_messages_relay():
    from unittest.mock import patch

    import httpx
    from app.config import settings
    from brain import lm_direct

    with patch.object(settings, "GEMINI_RELAY_SECRET", "x" * 32), patch.object(lm_direct, "key_for", return_value="test-key"):
        with patch.object(lm_direct, "_post", return_value=httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]})) as sent:
            assert lm_direct.probe("anthropic")["reply"] == "ok"
    endpoint, headers, payload, _ = sent.call_args.args
    assert endpoint == lm_direct.ANTHROPIC_RELAY
    assert headers["x-relay-secret"] == "x" * 32 and headers["x-api-key"] == "test-key"
    assert payload["max_tokens"] == 16 and payload["messages"][0]["role"] == "user"


def test_proxy_gives_every_cache_breakpoint_one_hour():
    try:
        from app.routers.agent_proxy import _long_cache
    except ImportError:
        return
    data = {"system": [{"type": "text", "text": "a", "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": [{"type": "text", "text": "b", "cache_control": {"type": "ephemeral"}}]}]}
    assert _long_cache(data) is True
    assert data["system"][0]["cache_control"]["ttl"] == "1h" and data["messages"][0]["content"][0]["cache_control"]["ttl"] == "1h"
    assert _long_cache(data) is False


def test_engine_tools_are_offered_to_the_agent():
    from app.agents.pro import runner
    from app.agents.pro.prompt import SYSTEM_PROMPT
    for name in ("talking_edit", "talking_revise", "job_wait"):
        assert name in runner.TOOL_NAMES and f"mcp__editorgpt__{name}" in runner.TOOL_FA
    assert "ENGINE FIRST" in SYSTEM_PROMPT and "talking_edit" in SYSTEM_PROMPT


def test_engine_revision_keeps_only_unchanged_graphics_and_marks_the_render_undone():
    try:
        from app.agents.pro import engines
        from creative import claude_premium as engine
    except Exception:                         # the agent container has no engines
        return
    work = Path(tempfile.mkdtemp(prefix="pro-engine-"))
    video = work / "v.mp4"
    video.write_bytes(b"x" * 100)
    words = [{"i": i, "t": f"w{i}", "start": i * 0.5, "end": i * 0.5 + 0.4} for i in range(40)]
    plan = {"props": [{"name": "a", "what": "a phone", "at": 3}, {"name": "b", "what": "a book", "at": 20}], "moments": [], "key": [2]}
    fp = engine._fingerprint(video, words, "ctx")
    engine._save_checkpoint(work, fp, {}, plan=engine.sanitize(engine.Plan.model_validate(plan), words).model_dump(), code={"a": "a()", "b": "b()"},
                            rendered=True, graded=12.0)
    plan["props"][1]["what"] = "a red book"
    engines._apply_plan(engine, work, video, words, "ctx", plan)
    ck = engine._load_checkpoint(work, fp)
    assert ck["rendered"] is False and ck["graded"] == 12.0
    assert set(ck["code"]) == {"a"}, ck["code"]
    assert [p["what"] for p in ck["plan"]["props"]] == ["a phone", "a red book"]


def test_job_wait_returns_when_a_job_ends():
    from app.agents.pro import engines
    path = engines._state_file("waitchat", "job1")
    path.write_text(json.dumps({"job_id": "job1", "state": "done", "progress": 100}))
    out = asyncio.run(engines.wait("waitchat", "job1", 30))
    assert out["state"] == "done" and out["waited_until_end"] is True
    path.write_text(json.dumps({"job_id": "job1", "state": "running", "progress": 40}))
    started = time.time()
    out = asyncio.run(engines.wait("waitchat", "job1", 1))
    assert out["waited_until_end"] is False and time.time() - started < 10
    from app.agents.pro.prompt import SYSTEM_PROMPT
    assert "sleep 25" not in SYSTEM_PROMPT and "call render_status ONCE" in SYSTEM_PROMPT


def test_a_second_talking_edit_of_the_same_video_is_sent_to_revise():
    try:
        from app.agents.pro import engines
        import creative.claude_premium  # noqa: F401
    except Exception:
        return
    cid = "engguard"
    video = pro.inside(cid, "in/v.mp4")
    video.parent.mkdir(parents=True, exist_ok=True)
    video.write_bytes(b"x" * 100)
    work = engines._work(cid, "premium", video)
    work.mkdir(parents=True, exist_ok=True)
    (work / "checkpoint.json").write_text("{}")
    try:
        engines.start({"cid": cid, "user": "1", "run": "r1"}, {"path": "in/v.mp4", "style": "premium"})
    except ValueError as exc:
        assert "talking_revise" in str(exc)
    else:
        raise AssertionError("a second talking_edit started the engine again")


def test_prompt_keeps_samples_away_from_the_fixed_engine():
    from app.agents.pro.prompt import SYSTEM_PROMPT
    assert "SAMPLE" in SYSTEM_PROMPT and "compare_style ONCE first" in SYSTEM_PROMPT and "NEVER call talking_edit again" in SYSTEM_PROMPT
    from app.agents.pro import runner
    assert "compare_style" in runner.TOOL_NAMES


def test_film_tools_are_offered_and_routed():
    from app.agents.pro import runner
    from app.agents.pro.prompt import SYSTEM_PROMPT
    for name in ("film_make", "film_revise"):
        assert name in runner.TOOL_NAMES and f"mcp__editorgpt__{name}" in runner.TOOL_FA
    assert "film_make" in SYSTEM_PROMPT
    try:
        from app.agents.pro import engines
    except Exception:
        return
    try:
        asyncio.run(engines.film_start({"cid": "filmc", "user": "1", "run": "r"}, {"kind": "cartoon", "request": "x"}))
    except ValueError as exc:
        assert "kind must be" in str(exc)
    else:
        raise AssertionError("an unknown film kind was accepted")


def test_jarvis_cache_is_charged_as_plain_input():
    try:
        from app.routers.agent_proxy import _billed_usage, ANTHROPIC_RELAY
    except ImportError:
        return
    usage = {"input_tokens": 4, "cache_read_input_tokens": 70000, "cache_creation_input_tokens": 1000, "output_tokens": 300}
    billed = _billed_usage(usage, "https://api.jarvis.you/v1/messages")
    assert billed["input_tokens"] == 71004 and billed["cache_read_input_tokens"] == 0 and billed["output_tokens"] == 300
    assert _billed_usage(usage, ANTHROPIC_RELAY) is usage


def test_a_message_sent_mid_run_reaches_the_agent_at_its_next_step():
    from app.agents.pro import runner

    class FakeApi:
        def __init__(self, messages):
            self.messages = messages

        async def inbox(self):
            out, self.messages = self.messages, []
            return out
    hook = runner._inbox(FakeApi([{"text": "فونت را دوران کن", "attachment_ids": []}]))
    out = asyncio.run(hook({"tool_name": "Bash", "tool_input": {}}, "id", None))
    context = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse" and "فونت را دوران کن" in context
    assert asyncio.run(hook({"tool_name": "Bash", "tool_input": {}}, "id", None)) == {}


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            started = time.time()
            try:
                fn()
                print(f"ok   {name} ({time.time() - started:.2f}s)")
            except Exception as exc:          # noqa: BLE001
                failed += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    sys.exit(1 if failed else 0)
