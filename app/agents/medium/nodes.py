"""Graph nodes: actual operations only. Checkpoints contain bounded normalized context."""
import json
import time
import re
from html import unescape
from langgraph.types import interrupt
from app.agents import store
from app.studio_store import repo, run
from app.agents.medium import tools
from app.agents import planner
from app.agents.planner import InvalidEditingPlan
from app.agents.medium.state import EditingPlan


class InvalidEditingPlan(ValueError):
    """Safe public error after bounded validation recovery; no tool was executed."""

def event(record, event_type, **data):
    return planner.event(record, event_type, **data)


def context(record):
    return planner.context(record)


def opening(record):
    """Reuse conversational streaming, not Lite orchestration. Persist once per run."""
    if record.get("agent_mode", "medium") != "medium": return          # Lite already answered the message itself before handing over
    current = run(store.get_run(record["id"], record["user_key"]))
    if current["data"].get("opening_saved"): return
    from app.studio_orchestrator import _stream_response
    conversation = run(repo.get_conversation(record["conversation_id"], record["user_key"]))
    assets = run(repo.get_attachments(record["data"]["request"]["attachment_ids"], record["conversation_id"], record["user_key"]))
    saved = _stream_response(record["conversation_id"], record["user_key"], record["message_id"], conversation, assets, agent_mode="medium")
    run(store.update(record["id"], record["user_key"], patch={"opening_attempted": True, "opening_saved": saved}))


def narrate_result(record, key, step, result):
    """Describe only completed tool evidence; never block editing on narration failure."""
    from app.studio_narrator import narrate
    narrate(record["conversation_id"], record["user_key"], f'{record.get("agent_mode", "medium")}:{record["id"]}:{key}',
            {"language": "fa", "completed_operation": step["label"], "observed_result": result,
             "agent_mode": record.get("agent_mode", "medium")}, background=False)

def plan(record, state):
    parsed = planner.make_plan(record, state)
    run(store.update(record["id"], record["user_key"], patch={"plan": parsed}))
    return {"plan": parsed, "index": 0, "approved": False, "rounds": state.get("rounds", 0) + 1, "healing": False, "plan_feedback": None}


def approval(record, state):
    plan = state["plan"]
    writes = sorted({step["tool"] for step in plan["steps"] if step["tool"] not in tools.READ_ONLY})
    if not writes: return {"approved": True}
    if record.get("agent_mode", "medium") == "lite" and (run(repo.get_conversation(record["conversation_id"], record["user_key"])).get("state") or {}).get("execution_mode") != "manual":
        return {"approved": True}                      # Lite does not ask before each write; only its manual mode does
    if state.get("heal_tools") is not None and writes == state["heal_tools"]: return {"approved": True}    # the person already approved exactly these tools
    decision = interrupt({"kind": "approval", "summary": plan["summary"], "steps": plan["steps"]})
    if decision != {"approve": True}: raise ValueError("Explicit plan approval is required")
    return {"approved": True}


MAX_HEALS = 4


def tool(record, state):
    from creative.schemas import CreativeUnavailable
    step = state["plan"]["steps"][state["index"]]
    key = f'{state.get("rounds", 1)}:{state["index"]}:{step["tool"]}'
    current = run(store.get_run(record["id"], record["user_key"]))
    ledger = dict(current["data"].get("operations", {}))
    entry = ledger.get(key)
    if entry and entry["status"] == "completed": result = entry["result"]
    else:
        # create_storyboard only writes text (no render, no paid media): a run that died while it was "started" may repeat it.
        if entry and step["tool"] not in tools.READ_ONLY and step["tool"] != "create_storyboard" and not (entry.get("status") == "failed" and entry.get("safe_to_retry") is True):
            raise ValueError("نتیجهٔ عملیات قبلی مشخص نیست؛ برای جلوگیری از هزینه یا رندر تکراری، اجرای مجدد خودکار متوقف شد. پروژه را بررسی کنید.")
        ledger[key] = {"status": "started", "tool": step["tool"]}
        run(store.update(record["id"], record["user_key"], patch={"operations": ledger}))
        event(record, "tool.started", tool=step["tool"], message=step["label"],
              request=json.dumps(step.get("arguments", {}), ensure_ascii=False, indent=1)[:1500])
        try:
            result = tools.execute(record, step)
        except (tools.PreflightUnavailable, ValueError, CreativeUnavailable) as exc:          # rejected before anything was submitted (incl. pydantic validation): safe to retry
            ledger[key] = {"status": "failed", "tool": step["tool"], "safe_to_retry": True}
            run(store.update(record["id"], record["user_key"], patch={"operations": ledger}))
            signature = f'{step["tool"]}:{type(exc).__name__}:{str(exc)[:90]}'
            seen, heals = list(state.get("failed", [])), state.get("heal", 0)
            if signature in seen or heals >= MAX_HEALS:
                raise                                   # the same rejection again (or too many tries): stop with the cause instead of looping
            event(record, "tool.progress", tool=step["tool"], stage="repair",
                  message="این مرحله رد شد؛ دارم برنامه را اصلاح می‌کنم و ادامه می‌دهم.")
            writes = sorted({s["tool"] for s in state["plan"]["steps"] if s["tool"] not in tools.READ_ONLY})
            return {"healing": True, "heal": heals + 1, "failed": seen + [signature], "heal_tools": writes if state.get("approved") else state.get("heal_tools"),
                    "plan_feedback": f'Step "{step["label"]}" ({step["tool"]}, arguments {json.dumps(step.get("arguments", {}), ensure_ascii=False)[:400]}) failed: {str(exc)[:400]}'}
        ledger[key] = {"status": "completed", "tool": step["tool"], "result": result}
        run(store.update(record["id"], record["user_key"], patch={"operations": ledger}))
        event(record, "tool.completed", tool=step["tool"], message=step["label"])
        try:
            narrate_result(record, key, step, result)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Medium tool narration unavailable")
    return {"index": state["index"] + 1, "results": [*state.get("results", []), result],
            "waiting_project": result.get("project_id") if result.get("waiting") else None}


def wait(record, state):
    pid = state.get("waiting_project")
    if pid:
        value = tools.project(record, pid)
        if value["status"] == "running" and value["state"].get("workflow") != "awaiting_approval":
            interrupt({"kind": "job", "project_id": pid})
            value = tools.project(record, pid)
        if value["status"] == "running" and value["state"].get("workflow") != "awaiting_approval":
            raise ValueError("Job is still running; no duplicate submission was made")
        observed = value["state"].get("last_observed") or {}
        has_output = bool(value["state"].get("output") or value["state"].get("candidate_output") or observed.get("output") or observed.get("candidate_output"))
        if value["status"] == "canceled" or (value["status"] == "error" and not has_output):
            raise ValueError("پردازش پروژه متوقف شده است؛ خروجی و وضعیت را در Studio بررسی کنید.")
        results = list(state.get("results", []))
        if results:
            results[-1] = {**results[-1], "waiting": False, "job_finished": True, "status": value["status"],
                           "workflow": value["state"].get("workflow"), "has_output": has_output,
                           "needs_review": value["status"] == "error" and has_output}
        return {"waiting_project": None, "results": results}
    return {"waiting_project": None}


def finish(record, state):
    from brain.lm_gateway import stream_chat
    cid, user = record["conversation_id"], record["user_key"]
    current = run(store.get_run(record["id"], user))
    if current["data"].get("reply_saved"): return {"finished": True}
    stream_id = f'{record.get("agent_mode", "medium")}-{record["id"]}'
    event(record, "assistant.response.started", response_id=stream_id, request_message_id=record["message_id"])
    content = ""
    messages = [{"role": "system", "content": "Reply briefly in Persian or English, matching the request, never in another language unless the person wrote in it. Report only observed results. No reasoning, fictional progress or claims a render is complete without evidence. Mention any existing plan approval still needed. If no tools ran, answer or ask the essential question from the plan summary."},
                {"role": "user", "content": json.dumps({"request": record["data"]["request"]["text"], "summary": state["plan"]["summary"], "results": state.get("results", [])}, ensure_ascii=False)}]
    last_flush, flushed = 0.0, ""
    # Existing gateway supplies provider choice, streaming, accounting and configured provider fallbacks.
    for part in stream_chat("conversation_response", messages, tokens=1400, timeout_seconds=90):
        if isinstance(part, dict) and part.get("type") == "delta":
            delta = part.get("text", "")
        elif isinstance(part, str): delta = part
        else: continue
        content += delta
        if time.monotonic() - last_flush >= 0.12:                    # one event per token made the text arrive in slow bursts
            event(record, "assistant.response.delta", response_id=stream_id, text=content)
            last_flush, flushed = time.monotonic(), content
    if content and content != flushed:
        event(record, "assistant.response.delta", response_id=stream_id, text=content)
    if not content.strip(): raise ValueError("Medium پاسخ قابل استفاده‌ای از Gateway دریافت نکرد؛ موتور تغییر نکرده است.")
    message = run(repo.add_message(cid, user, "assistant", content, agent_mode=record.get("agent_mode", "medium")))
    run(store.update(record["id"], user, patch={"reply_saved": message["id"]}))
    event(record, "assistant.response.completed", response_id=stream_id, message_id=message["id"], text=content)
    return {"finished": True}
