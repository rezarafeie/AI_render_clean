"""EditorGPT Medium as a worker agent: one decision at a time, not a plan.

Every turn the model sees the whole conversation and everything this run has observed (what it looked at, what each tool returned, what a finished job
produced) and answers with ONE decision: what to tell the person now, and either one tool to use next, or nothing (the work for this message is done, or
it is waiting for the person's answer). After the tool, it sees the result and decides again. A film or an edit that takes minutes is waited for without
holding a worker (the run sleeps and wakes when the job ends), and the agent then watches the finished video (review_output) and fixes what it finds
before it says the work is ready.

There is no intent list and no plan approval: the person's request is the consent to make what they asked. The only gate is money that was not asked
for (generating music), which the agent must ask for in words first. Ownership checks, the operation ledger (a write whose result is unknown is never
repeated), Stop, budgets and checkpoints are Medium's own.
"""
from __future__ import annotations

import json
import logging
import re
from html import unescape

from pydantic import BaseModel, ConfigDict, Field

from app.agents import planner, store
from app.agents.medium import tools
from app.agents.medium.state import Step
from app.studio_store import repo, run

log = logging.getLogger(__name__)
MAX_TURNS = 16              # decisions per execution (a wait for a job starts a new execution)
CONSENT = {"generate_music"}   # paid and never implied by a request for something else: asked in words first

GUIDE = """You are EditorGPT: a senior video editor and creative director who works WITH the person, with real tools. You are not a router and not a form.
Each turn you get the conversation, what this run has observed so far, and the tools. You answer with ONE decision as JSON:
{"say": "...", "action": {"tool": "...", "arguments": {...}, "label": "..."} | null, "done": true|false, "consent": "..."}
- say: what you tell the person NOW, in their language (Persian unless they wrote otherwise), short and human, like a colleague: what you saw, what you
  are about to do and why, what you found, a question. Empty when there is nothing worth saying before the next action. Never narrate trivia, never
  claim something you have not observed, never write "please wait".
- action: the ONE next tool call (arguments exactly per its schema, only real IDs from the context/observations; label = a short Persian description of
  this concrete operation), or null.
- done: true when the work for this message is finished, or when you asked the person something and must wait for their reply (then action is null).

HOW YOU WORK
- The observations are what THIS run already did, in order. Read them first. Never redo work that already succeeded: if the request is already
  fulfilled (the film or edit exists and your review says deliver), tell the person it is ready and what you checked, action null, done=true. A new
  creation is only for a new subject or when the person asks for another one.
- Understand before acting. Look at what the person gave you (look_at_media for a video, inspect_url for a link they sent) before deciding what to make
  with it, unless an observation already did. Decide from what you SAW and what they WANT, not from keywords.
- If the material does not fit the request, say so plainly and propose what would work (an already produced video asked to "improve its motion" -> ask
  for the raw footage, say exactly what you saw). If the request is ambiguous in a way that changes the result, ask ONE precise question or offer two or
  three concrete directions with a reason each, then done=true. If it is clear, act; the request itself is the consent: never ask "shall I start?".
- Be the creative lead. When you start a film, the request you give the engine carries the person's words unchanged PLUS your direction, which must be
  specific to THIS subject and impossible to reuse for another one: (1) the angle in one sentence (a surprising fact, a tension, a concrete person or
  moment, not "the importance of X"); (2) the opening image and line of the first 2 seconds; (3) one visual idea that runs through the film (a metaphor
  or object that transforms, a counter, a map, a split screen...); (4) the arc in 3-5 beats with what each SHOWS; (5) how it ends: the last line and the
  final held frame. Words like «خلاقانه», «جذاب», «حرفه‌ای», «انیمیشن‌های زیبا» say nothing: never write them. Look at the history: if this person already
  got films, choose a structure and look unlike those.
- Say only what is true. Never promise a voice, a length, a style or a feature that the arguments you send do not carry; use the person's cloned voice
  only when they ask for their own voice.
- Check your work. When a film or an edit you started has finished (an observation shows job_finished / a new version), use review_output on it. If
  it says fix (or you see a real problem), apply the concrete fixes with revise_motion_graphic or modify_project, then check again (at most two rounds).
  Only then tell the person it is ready, with one honest sentence about what you checked.
- When a tool fails, read the error and choose another way; never repeat the same call with the same arguments.
- A long job (a film, a talking edit, a dub) runs in the background: when you start one, the run waits for it by itself and your next turn sees how it
  ended (job_finished, the film's versions, notes, questions). So in the turn that starts it, say briefly what you are making and why it will be good.
- Money that was not asked for (generate_music) needs the person's yes in words first: ask, done=true. If they already said yes in this conversation,
  put their words in consent.
- Follow-ups belong to what exists: a change to the film this chat holds is revise_motion_graphic; the reply to a question the film engine asked is
  answer_motion_graphic; clips of a long video are discovery_command; a Studio project is modify_project. A clearly new subject is a new creation.

""" + planner.PROMPT.split("Respond in Persian or English", 1)[1].split("Writes require explicit user approval.", 1)[0]


class Decision(BaseModel):
    model_config = ConfigDict(extra="ignore")
    say: str = Field(default="", max_length=3000)
    action: Step | None = None
    done: bool = False
    consent: str = Field(default="", max_length=400)


def _observations(state: dict) -> list[dict]:
    out = []
    for item in state.get("results", [])[-14:]:
        item = dict(item)
        if isinstance(item.get("content"), str):
            item["content"] = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(item["content"])))[:5000]
        out.append(item)
    return out


def _context(record: dict, state: dict) -> dict:
    shared = planner.context(record)["context"]
    latest_project = next((r.get("project_id") for r in reversed(state.get("results", [])) if r.get("project_id")), None)
    if latest_project:
        shared["current_project_id"] = latest_project
    try:
        from brain import voice_clone
        shared["person_has_cloned_voice"] = bool(voice_clone.list_clones(str(record["user_key"])))
    except Exception:
        pass
    return shared


def post(record: dict, text: str, key: str) -> None:
    """A message from the agent in the chat, once per key (a resumed run never says the same thing twice)."""
    text = (text or "").strip()
    if not text:
        return
    current = run(store.get_run(record["id"], record["user_key"]))
    said = list(current["data"].get("said") or [])
    if key in said:
        return
    rid = f'medium-{record["id"]}-{key}'
    planner.event(record, "assistant.response.started", response_id=rid, request_message_id=record["message_id"])
    planner.event(record, "assistant.response.delta", response_id=rid, text=text)
    message = run(repo.add_message(record["conversation_id"], record["user_key"], "assistant", text, agent_mode="medium"))
    planner.event(record, "assistant.response.completed", response_id=rid, message_id=message["id"], text=text)
    run(store.update(record["id"], record["user_key"], patch={"said": said + [key], "reply_saved": message["id"]}))


def think(record: dict, state: dict) -> dict:
    from brain.llm import _extract_json
    from brain.lm_gateway import complete, defaults
    from brain.lm_adapters import text as response_text
    turn = state.get("turns", 0) + 1
    if turn > MAX_TURNS:
        return {"decision": {"say": "این مرحله طولانی شد؛ کارهای انجام‌شده ذخیره‌اند. بگویید از کجا ادامه بدهم.", "action": None, "done": True}, "turns": turn}
    planner.event(record, "tool.started", tool="medium_think", stage="thinking", message="دارم وضعیت و نتیجه‌ها را می‌سنجم و قدم بعدی را انتخاب می‌کنم.")
    payload = {"context": _context(record, state), "observations": _observations(state), "turn": turn,
               "tools": tools.catalog(), "decision_schema": Decision.model_json_schema()}
    feedback = ""

    def validate(text):
        nonlocal feedback
        try:
            value = Decision.model_validate(_extract_json(text))
        except ValueError:
            feedback = "Return exactly ONE JSON object matching decision_schema."
            raise ValueError(feedback) from None
        if value.action is not None:
            try:
                tools.validate(record, value.action.model_dump())
            except (KeyError, ValueError) as exc:
                feedback = f"The action's arguments are invalid or name IDs that do not exist ({str(exc)[:200]}). Use only real IDs from the context and observations."
                raise ValueError(feedback) from None
        return value

    messages = [{"role": "system", "content": GUIDE + "\nReturn exactly one JSON object, with no text before or after it."},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)}]
    decision = None
    for attempt in range(2):
        try:
            response, _audit = complete("editing_agent", messages, tokens=5000, stream=bool(defaults()["editing_agent"].get("streaming")), validate_response=validate)
            decision = validate(response_text("chat", response))
            break
        except Exception as exc:
            if attempt or not feedback:
                raise
            messages.append({"role": "user", "content": "Your last answer was rejected: " + feedback})
    planner.event(record, "tool.completed", tool="medium_think", message=(decision.action.label if decision.action else "تصمیم گرفته شد."))
    data = decision.model_dump()
    if decision.action is not None and decision.action.tool in CONSENT and not decision.consent.strip():
        data.update(action=None, done=True, say=(decision.say + "\n" if decision.say else "") + "برای این کار موسیقی تازه ساخته می‌شود که اعتبار مصرف می‌کند؛ اگر موافقید بگویید.")
    post(record, data["say"], f"t{turn}")
    return {"decision": data, "turns": turn}


def act(record: dict, state: dict) -> dict:
    """The decided tool, once (the ledger keeps a write whose result is unknown from running twice). A rejected call becomes an observation, not a crash."""
    from creative.schemas import CreativeUnavailable
    step = state["decision"]["action"]
    import hashlib
    digest = hashlib.sha256(json.dumps(step.get("arguments", {}), sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:10]
    key = f'{state.get("turns", 0)}:{step["tool"]}:{digest}'
    current = run(store.get_run(record["id"], record["user_key"]))
    ledger = dict(current["data"].get("operations", {}))
    entry = ledger.get(key)
    if entry and entry["status"] == "completed":
        result = entry["result"]
    else:
        if entry and step["tool"] not in tools.READ_ONLY and not entry.get("safe_to_retry"):
            raise ValueError("نتیجهٔ عملیات قبلی مشخص نیست؛ برای جلوگیری از هزینه یا رندر تکراری، اجرای مجدد خودکار متوقف شد.")
        ledger[key] = {"status": "started", "tool": step["tool"]}
        run(store.update(record["id"], record["user_key"], patch={"operations": ledger}))
        planner.event(record, "tool.started", tool=step["tool"], message=step["label"], request=json.dumps(step.get("arguments", {}), ensure_ascii=False, indent=1)[:1500])
        try:
            result = tools.execute(record, step)
        except (tools.PreflightUnavailable, ValueError, CreativeUnavailable) as exc:      # rejected before anything was submitted: the agent reads it and chooses again
            ledger[key] = {"status": "failed", "tool": step["tool"], "safe_to_retry": True}
            run(store.update(record["id"], record["user_key"], patch={"operations": ledger}))
            planner.event(record, "tool.completed", tool=step["tool"], message=f"{step['label']} — انجام نشد")
            failures = [r for r in state.get("results", []) if r.get("error")]
            if sum(1 for r in failures if r.get("tool") == step["tool"] and r.get("error") == str(exc)[:400]) >= 1:
                raise                                 # the same rejection twice: stop with the cause instead of looping
            return {"results": [*state.get("results", []), {"tool": step["tool"], "arguments": step.get("arguments", {}), "error": str(exc)[:400]}], "waiting": None}
        ledger[key] = {"status": "completed", "tool": step["tool"], "result": result}
        run(store.update(record["id"], record["user_key"], patch={"operations": ledger}))
        planner.event(record, "tool.completed", tool=step["tool"], message=step["label"])
    observed = {"tool": step["tool"], "label": step["label"], **(result if isinstance(result, dict) else {"result": result})}
    waiting = None
    if isinstance(result, dict) and result.get("waiting") and result.get("project_id"):
        waiting = {"kind": "job", "project_id": result["project_id"]}
    elif isinstance(result, dict) and result.get("motion_id") and step["tool"] in {"create_motion_graphic", "revise_motion_graphic", "answer_motion_graphic"}:
        waiting = {"kind": "job", "motion_id": result["motion_id"]}
    return {"results": [*state.get("results", []), observed], "waiting": waiting}


def _motion_state(record: dict, motion_id: str) -> dict:
    from app import motion_graphic as mg
    directory = mg.locate(motion_id, record["user_key"])
    value = mg.load(directory)
    latest = value["versions"][-1] if value["versions"] else {}
    return {"status": value["status"], "message": value.get("message", ""), "error": value.get("error"), "questions": value.get("questions") or [],
            "versions": len(value["versions"]), "title": latest.get("title", ""), "duration": latest.get("duration"), "notes": (latest.get("notes") or [])[:6]}


def wait(record: dict, state: dict) -> dict:
    """Sleep until the started job ends (no worker is held: the run is resumed by the studio's sync), then observe how it ended."""
    from langgraph.types import interrupt
    waiting = state.get("waiting")
    if not waiting:
        return {}
    results = list(state.get("results", []))
    if waiting.get("project_id"):
        value = tools.project(record, waiting["project_id"])
        if value["status"] == "running" and value["state"].get("workflow") != "awaiting_approval":
            interrupt({"kind": "job", "project_id": waiting["project_id"]})
            value = tools.project(record, waiting["project_id"])
        observed = value["state"].get("last_observed") or {}
        results[-1] = {**results[-1], "waiting": False, "job_finished": value["status"] != "running", "status": value["status"], "workflow": value["state"].get("workflow"),
                       "has_output": bool(value["state"].get("output") or value["state"].get("candidate_output") or observed.get("output")),
                       "plan_waiting_for_approval": value["state"].get("workflow") == "awaiting_approval"}
    else:
        from app import motion_graphic as mg
        seen = _motion_state(record, waiting["motion_id"])
        if seen["status"] in mg.ACTIVE:
            interrupt({"kind": "job", "motion_id": waiting["motion_id"]})
            seen = _motion_state(record, waiting["motion_id"])
        results[-1] = {**results[-1], "waiting": False, "job_finished": seen["status"] not in mg.ACTIVE, "film": seen}
    return {"waiting": None, "results": results}


def finish(record: dict, state: dict) -> dict:
    return {"finished": True}


def after_think(state: dict) -> str:
    decision = state.get("decision") or {}
    if decision.get("action"):
        return "act"
    return "finish"


def after_act(state: dict) -> str:
    return "wait" if state.get("waiting") else "think"
