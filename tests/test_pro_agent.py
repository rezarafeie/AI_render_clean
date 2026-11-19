"""EditorGPT Pro guards (docs/PRO_AGENT_PLAN.md): the run token, the per-chat folder, the PreToolUse policy, the proxy's image lift and the runner's
handling of a resumed session. Runs under pytest, or directly (`python tests/test_pro_agent.py`) inside the app / agent containers, which have no pytest."""
from __future__ import annotations

import asyncio
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
        assert "anthropic" in [p["id"] for p in lm_direct.usable(kind="agent")] or not lm_direct.config()["enabled"]
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
