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


def _activity(api: Api):
    """PostToolUse: the person sees which kind of work is happening (never raw arguments or output)."""
    labels = {"Bash": "اجرای ابزار", "Write": "نوشتن فایل", "Edit": "ویرایش فایل", "Read": "بررسی فایل", "Skill": "خواندن راهنما"}

    async def hook(data, tool_use_id, context):
        name = data.get("tool_name", "")
        if name in {"Bash", "Skill"}:
            args = data.get("tool_input") or {}
            label = str(args.get("description") or args.get("skill") or args.get("command", "")[:60] or labels.get(name, name))[:120]
            try:
                await api.tool("step", {"label": label, "state": "done"})
            except Exception:
                pass
        return {}
    return hook


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
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[_policy(work)])], "PostToolUse": [HookMatcher(matcher=None, hooks=[_activity(api)])]},
        max_turns=int(os.environ.get("PRO_MAX_TURNS", "250")),
        env={"ANTHROPIC_BASE_URL": APP + "/internal/anthropic", "ANTHROPIC_AUTH_TOKEN": job["token"], "ANTHROPIC_API_KEY": "",
             "CLAUDE_CONFIG_DIR": str(config), "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1", "DISABLE_TELEMETRY": "1",
             "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "DISABLE_AUTOUPDATER": "1", "REMOTION_BROWSER_EXECUTABLE": os.environ.get("REMOTION_BROWSER_EXECUTABLE", "")},
        resume=job.get("resume") or None,
    )
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
