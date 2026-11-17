"""One EditorGPT Pro run inside the agent container: a Claude Agent SDK session whose model calls go to the app's proxy (run token only) and whose
editorgpt tools call the app's internal endpoints. Imports claude_agent_sdk; used only by the agent worker (app/agents/pro/daemon.py)."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
from pathlib import Path

import httpx

from app.agents.pro import RUNS, workdir
from app.agents.pro.prompt import SYSTEM_PROMPT, first_message

log = logging.getLogger("pro.runner")
APP = os.environ.get("PRO_APP_URL", "http://editor.rafiei.co:8000")
SKILLS = Path(__file__).resolve().parent / "skills"
READ_ROOTS = ("/app/remotion", "/app/creative", "/app/presets/fonts")
BLOCKED = re.compile(r"\b(curl|wget|ssh|scp|sftp|nc|ncat|telnet|sudo|apt|apt-get|pip|pip3|npm\s+(i|install)|docker|mkfs|shutdown|reboot)\b|"
                     r"/etc/|/proc/|/root/|\benv\b|printenv|rm\s+-rf\s+/(\s|$)")


class Api:
    def __init__(self, token: str):
        self.client = httpx.AsyncClient(base_url=APP, headers={"x-pro-token": token}, timeout=300)

    async def tool(self, name: str, args: dict) -> dict:
        r = await self.client.post("/internal/pro/tool", json={"name": name, "args": args})
        r.raise_for_status()
        return r.json()

    async def event(self, **body) -> None:
        try:
            await self.client.post("/internal/pro/event", json=body)
        except Exception:
            pass

    async def stop_requested(self) -> bool:
        try:
            r = await self.client.get("/internal/pro/status")
            return bool(r.json().get("stop"))
        except Exception:
            return False

    async def finish(self, **body) -> None:
        for _ in range(3):
            try:
                (await self.client.post("/internal/pro/finish", json=body)).raise_for_status()
                return
            except Exception:
                await asyncio.sleep(3)


def _tools(api: Api):
    from claude_agent_sdk import create_sdk_mcp_server, tool

    def result(value: dict) -> dict:
        if value.get("ok"):
            import json
            return {"content": [{"type": "text", "text": json.dumps(value.get("result"), ensure_ascii=False)}]}
        return {"content": [{"type": "text", "text": "error: " + str(value.get("error"))}], "is_error": True}

    @tool("say", "Send a short message to the person, in Persian.", {"text": str})
    async def say(args):
        return result(await api.tool("say", args))

    @tool("step", "Show a stage of the work in the person's activity panel. state: running | done | failed.", {"label": str, "state": str})
    async def step(args):
        return result(await api.tool("step", args))

    @tool("assets_list", "List the files the person attached in this chat (id, name, kind, size, duration).", {})
    async def assets_list(args):
        return result(await api.tool("assets_list", args))

    @tool("assets_fetch", "Copy one of the person's files into in/ of the working folder; returns its path.", {"asset_id": str})
    async def assets_fetch(args):
        return result(await api.tool("assets_fetch", args))

    @tool("show_stills", "Show up to 12 still images (paths in the working folder) to the person, with a short Persian caption.",
          {"type": "object", "properties": {"paths": {"type": "array", "items": {"type": "string"}}, "caption": {"type": "string"}}, "required": ["paths"]})
    async def show_stills(args):
        return result(await api.tool("show_stills", args))

    @tool("deliver", "Deliver the finished file (path in the working folder) to the person, with a title and a short Persian note.",
          {"type": "object", "properties": {"path": {"type": "string"}, "title": {"type": "string"}, "notes": {"type": "string"}}, "required": ["path"]})
    async def deliver(args):
        return result(await api.tool("deliver", args))

    return create_sdk_mcp_server(name="editorgpt", tools=[say, step, assets_list, assets_fetch, show_stills, deliver])


TOOL_NAMES = ["say", "step", "assets_list", "assets_fetch", "show_stills", "deliver"]


def _policy(work: Path):
    """PreToolUse: the second line of defence (the container has no internet and no keys): no network or system commands, files only in the chat's folder."""
    root = str(work.resolve())

    def deny(reason: str) -> dict:
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}

    async def hook(data, tool_use_id, context):
        name = data.get("tool_name", "")
        args = data.get("tool_input") or {}
        if name == "Bash":
            command = str(args.get("command") or "")
            if BLOCKED.search(command):
                return deny("This command is not allowed here (no network, packages or system access). Use the editorgpt tools.")
            for path in re.findall(r"(?<![\w.])(/[\w./-]+)", command):
                if not (path.startswith(root) or path.startswith(READ_ROOTS) or path.startswith(("/tmp", "/dev/null", "/usr/", "/bin/", "/opt/venv"))):
                    return deny(f"The path {path} is outside the working folder.")
        if name in {"Read", "Write", "Edit", "MultiEdit", "NotebookEdit", "Glob", "Grep"}:
            target = str(args.get("file_path") or args.get("path") or root)
            full = os.path.realpath(target if os.path.isabs(target) else os.path.join(root, target))
            writable = full.startswith(root)
            readable = writable or full.startswith(READ_ROOTS)
            if (name in {"Write", "Edit", "MultiEdit", "NotebookEdit"} and not writable) or not readable:
                return deny("Files outside the working folder cannot be used.")
        return {}
    return hook


TOOL_FA = {"Read": "بررسی فایل", "Write": "نوشتن فایل", "Edit": "اصلاح فایل", "MultiEdit": "اصلاح فایل", "Glob": "پیدا کردن فایل‌ها",
           "Grep": "جست‌وجو در فایل‌ها", "Skill": "خواندن راهنمای کار", "TodoWrite": "برنامه‌ریزی مراحل", "Bash": "اجرای ابزار",
           "mcp__editorgpt__assets_list": "دیدن فایل‌های شما", "mcp__editorgpt__assets_fetch": "دریافت فایل شما",
           "mcp__editorgpt__show_stills": "نمایش استیل‌ها", "mcp__editorgpt__deliver": "تحویل خروجی", "mcp__editorgpt__say": "پیام",
           "mcp__editorgpt__step": "مرحله"}
PERSIAN = re.compile(r"[\u0600-\u06FF]")


def _detail(name: str, args: dict) -> str:
    """What the step does, shown when the person opens it (like Claude Code's tool lines): the command, the file, the skill, the arguments."""
    if name == "Bash":
        return "$ " + str(args.get("command") or "")[:1400]
    if name in {"Read", "Write", "Edit", "MultiEdit"}:
        path = str(args.get("file_path") or "")
        if name == "Write":
            body = str(args.get("content") or "")
            return f"{path}\n({len(body.splitlines())} خط)\n" + body[:900]
        if name in {"Edit", "MultiEdit"}:
            return f"{path}\n- {str(args.get('old_string') or '')[:300]}\n+ {str(args.get('new_string') or '')[:500]}"
        return path
    if name == "Skill":
        return str(args.get("skill") or "")
    if name == "TodoWrite":
        return "\n".join(("✓ " if t.get("status") == "completed" else "• ") + str(t.get("content") or "") for t in (args.get("todos") or [])[:12])
    import json
    return json.dumps(args, ensure_ascii=False)[:1200]


def _result_text(block) -> str:
    content = block.content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(item.get("text") or ("[تصویر]" if item.get("type") == "image" else ""))
        content = "\n".join(p for p in parts if p)
    text = str(content or "").strip()
    return (text[:1500] + "\n…") if len(text) > 1500 else text


def _label(name: str, args: dict) -> str:
    """A Persian label for a tool step (the agent writes Bash descriptions in Persian; anything else gets a plain Persian name)."""
    if name == "Bash" and PERSIAN.search(str(args.get("description") or "")):
        return str(args["description"])[:120]
    if name == "Skill" and args.get("skill"):
        return "خواندن راهنمای " + str(args["skill"])[:60]
    if name in {"Read", "Write", "Edit"} and args.get("file_path"):
        return TOOL_FA[name] + " " + os.path.basename(str(args["file_path"]))[:60]
    return TOOL_FA.get(name, "در حال کار")


async def _forward(api: Api, message, live: dict) -> None:
    """The agent's reply text streams into the chat (started → live deltas every ~0.4 s → completed, saved as a message) and every tool call is a
    timeline step that opens when the call starts and closes with its result."""
    import time
    import uuid
    from claude_agent_sdk import AssistantMessage, StreamEvent, TextBlock, ThinkingBlock, ToolResultBlock, ToolUseBlock, UserMessage

    async def close_text():
        if live["id"] is not None:
            await api.event(kind="text_done", response_id=live["id"], text=live["text"])
            live.update(text="", id=None)

    root = live.get("root", "")

    def short(text: str) -> str:
        return text.replace(root + "/", "").replace(root, ".") if root else text

    if isinstance(message, StreamEvent):
        event = message.event or {}
        kind = event.get("type")
        if kind == "content_block_start" and (event.get("content_block") or {}).get("type") in {"thinking", "redacted_thinking"}:
            live["think"] = {"id": "think-" + uuid.uuid4().hex[:12], "index": event.get("index"), "text": ""}
            await api.event(kind="tool_start", id=live["think"]["id"], tool="think", label="در حال فکر کردن…")      # shown live, like Claude Code
            return
        if kind == "content_block_delta" and (event.get("delta") or {}).get("type") == "thinking_delta" and live.get("think"):
            live["think"]["text"] += event["delta"].get("thinking", "")
            return
        if kind == "content_block_stop" and live.get("think") and event.get("index") == live["think"]["index"]:
            think = live.pop("think")
            live["thought"] = True
            await api.event(kind="tool_done", id=think["id"], tool="think", label="فکر کردن دربارهٔ قدم بعدی",
                            detail=think["text"].strip()[:1500] or "(متن فکر نمایش داده نمی‌شود)")
            return
        if kind == "content_block_delta" and (event.get("delta") or {}).get("type") == "text_delta":
            if live["id"] is None:
                live["id"] = "pro-" + uuid.uuid4().hex[:16]
                await api.event(kind="text_start", response_id=live["id"])
            live["text"] += event["delta"].get("text", "")
            if time.monotonic() - live["sent"] > 0.4:
                live["sent"] = time.monotonic()
                await api.event(kind="text_delta", response_id=live["id"], text=live["text"])
        return
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, ThinkingBlock) and (block.thinking or "").strip() and not live.pop("thought", False):
                tid = "think-" + uuid.uuid4().hex[:12]           # the agent's reasoning, as one closed step the person can open (like Claude Code)
                await api.event(kind="tool_start", id=tid, tool="think", label="فکر کردن دربارهٔ قدم بعدی", detail=block.thinking[:1500])
                await api.event(kind="tool_done", id=tid, tool="think", label="فکر کردن دربارهٔ قدم بعدی", detail=block.thinking[:1500])
            if isinstance(block, TextBlock) and live["id"] is None and block.text.strip():
                live["id"] = "pro-" + uuid.uuid4().hex[:16]                # no stream events arrived: the whole text at once
                await api.event(kind="text_start", response_id=live["id"])
                live["text"] = block.text
            if isinstance(block, ToolUseBlock):
                await close_text()
                if block.name in {"mcp__editorgpt__say", "mcp__editorgpt__step"}:
                    continue
                tool = block.name.split("__")[-1]
                live["tools"][block.id] = (tool, _label(block.name, block.input or {}))
                path = str((block.input or {}).get("file_path") or "")
                if block.name == "Read" and path.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                    live["images"][block.id] = path
                await api.event(kind="tool_start", id=block.id, tool=tool, label=live["tools"][block.id][1], detail=short(_detail(block.name, block.input or {})))
        await close_text()
        return
    if isinstance(message, UserMessage) and isinstance(message.content, list):
        for block in message.content:
            if isinstance(block, ToolResultBlock) and block.tool_use_id in live["tools"]:
                tool, label = live["tools"].pop(block.tool_use_id)
                # always closes the same row (a tool.failed event would open a separate one); an error is said in the row's detail
                image = live["images"].pop(block.tool_use_id, None)
                await api.event(kind="tool_done", id=block.tool_use_id, tool=tool, label=label, image=image,
                                detail=short(("خطا: " if block.is_error else "") + (_result_text(block) or "انجام شد")))


async def run(job: dict) -> None:
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher, ResultMessage, SystemMessage
    api = Api(job["token"])
    cid = job["cid"]
    work = workdir(cid)
    skills = work / ".claude" / "skills"
    skills.mkdir(parents=True, exist_ok=True)
    for folder in SKILLS.iterdir():
        if folder.is_dir():
            shutil.copytree(folder, skills / folder.name, dirs_exist_ok=True)
    config = RUNS / cid / ".claude-config"
    config.mkdir(parents=True, exist_ok=True)
    options = ClaudeAgentOptions(
        system_prompt={"type": "preset", "preset": "claude_code", "append": SYSTEM_PROMPT},
        model=job.get("model") or "claude-opus-5-5",
        cwd=str(work),
        setting_sources=["project"],
        allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash", "Skill", "TodoWrite", *[f"mcp__editorgpt__{n}" for n in TOOL_NAMES]],
        disallowed_tools=["WebFetch", "WebSearch"],
        mcp_servers={"editorgpt": _tools(api)},
        permission_mode="dontAsk",
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[_policy(work)])]},
        max_turns=int(os.environ.get("PRO_MAX_TURNS", "250")),
        env={"ANTHROPIC_BASE_URL": APP + "/internal/anthropic", "ANTHROPIC_AUTH_TOKEN": job["token"], "ANTHROPIC_API_KEY": "",
             "CLAUDE_CONFIG_DIR": str(config), "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1", "DISABLE_TELEMETRY": "1",
             "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "DISABLE_AUTOUPDATER": "1", "REMOTION_BROWSER_EXECUTABLE": os.environ.get("REMOTION_BROWSER_EXECUTABLE", "")},
        resume=job.get("resume") or None,
        include_partial_messages=True,
    )
    live = {"text": "", "id": None, "sent": 0.0, "tools": {}, "images": {}, "root": str(work)}
    status, error, session, turns, cost, reason = "failed", None, None, None, None, None
    stopped = False
    try:
        async with ClaudeSDKClient(options) as client:
            async def watch():
                nonlocal stopped
                while True:
                    await asyncio.sleep(5)
                    if await api.stop_requested():
                        stopped = True
                        await client.interrupt()
                        return
            watcher = asyncio.create_task(watch())
            try:
                await client.query(first_message(job["text"], job.get("attachment_ids") or [], bool(job.get("resume"))))
                async for message in client.receive_response():
                    await _forward(api, message, live)
                    if isinstance(message, SystemMessage) and message.subtype == "init":
                        session = (message.data or {}).get("session_id") or session
                    elif isinstance(message, ResultMessage):
                        session = message.session_id or session
                        turns, cost = message.num_turns, message.total_cost_usd
                        reason = getattr(message, "stop_reason", None) or message.subtype
                        status = "stopped" if stopped else ("completed" if not message.is_error else "failed")
                        if message.is_error:
                            error = str(getattr(message, "result", "") or message.subtype)[:400]
            finally:
                watcher.cancel()
    except Exception as exc:
        log.exception("pro run %s failed", job["run"])
        status, error = ("stopped" if stopped else "failed"), (None if stopped else f"{type(exc).__name__}: {str(exc)[:300]}")
    await api.finish(status=status, error=error, session_id=session, turns=turns, cli_cost_usd=cost, stop_reason=reason)
    await api.client.aclose()
