"""Independent Medium workflow; shared engines/tools, never Lite message dispatch."""
import hashlib
import logging
import time
import httpx
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
from app.agents.medium.state import State
from app.agents.medium import nodes, tools
from app.agents.medium.checkpoints import saver
from app.agents import store
from app.studio_store import repo, run
from app import studio_flags
from brain.lm_gateway import conversation_scope
from langsmith import tracing_context

log = logging.getLogger(__name__)


def config(record):
    # Always computed from the owner-checked run. Never take client checkpoint config.
    scope = f'{record["user_key"]}:{record["conversation_id"]}:{record["id"]}'
    return {"configurable": {"thread_id": hashlib.sha256(scope.encode()).hexdigest()}, "recursion_limit": 50}


def build(record, checkpoint, guard=lambda: None):
    graph = StateGraph(State)
    for name, handler in (("context", lambda s: nodes.context(record)),
                          ("plan", lambda s: nodes.plan(record, s)),
                          ("approval", lambda s: nodes.approval(record, s)),
                          ("tool", lambda s: nodes.tool(record, s)),
                          ("wait", lambda s: nodes.wait(record, s)),
                          ("finish", lambda s: nodes.finish(record, s))):
        def wrapped(state, fn=handler):
            guard()
            result = fn(state)
            guard()
            return result
        graph.add_node(name, wrapped)
    graph.add_edge(START, "context")
    graph.add_edge("context", "plan")
    graph.add_conditional_edges("plan", lambda s: "approval" if s["plan"]["steps"] else "finish")
    graph.add_edge("approval", "tool")
    graph.add_edge("tool", "wait")

    def after_wait(state):
        if state["index"] < len(state["plan"]["steps"]): return "tool"
        # Inspect first, then use its real observations to design the editing plan.
        if (state["plan"]["steps"] and all(x["tool"] in tools.READ_ONLY for x in state["plan"]["steps"])
                and state.get("rounds", 0) < 3): return "plan"
        if (state.get("results") and state["results"][-1].get("job_finished")
                and state.get("rounds", 0) < 3): return "plan"
        return "finish"
    graph.add_conditional_edges("wait", after_wait)
    graph.add_edge("finish", END)
    return graph.compile(checkpointer=checkpoint)


@conversation_scope
def _execute(cid, user, record):
    rid = record["id"]
    if not run(store.update(rid, user, status="running", patch={"error": None}, claim={"queued"})): return
    generation = record["data"].get("stop_generation", studio_flags.generation(user, cid))
    deadline = time.monotonic() + 900
    def guard():
        if studio_flags.generation(user, cid) != generation: raise InterruptedError("Stopped by user")
        if time.monotonic() > deadline: raise TimeoutError("Medium execution time limit reached")
    # Share cancellation with existing engine helper calls too.
    from app.studio_orchestrator import _generation
    token = _generation.set((cid, user, generation))
    nodes.event(record, "work.state", busy=True)
    nodes.event(record, "message.started", message_id=record["message_id"])
    try:
        with studio_flags.working(user, cid), saver() as checkpoint:
            nodes.opening(record)
            graph = build(record, checkpoint, guard)
            cfg = config(record)
            previous = graph.get_state(cfg)
            resume = record["data"].get("resume")
            if previous.tasks and any(t.interrupts for t in previous.tasks):
                if resume is None: raise ValueError("This workflow needs an explicit resume decision")
                payload = Command(resume=resume)
            else:
                payload = None if previous.values else {}
            # Do not export private Studio state to an unrelated tracing service.
            with tracing_context(enabled=False):
                graph.invoke(payload, cfg, durability="sync")
            snapshot = graph.get_state(cfg)
            interruptions = [i.value for task in snapshot.tasks for i in task.interrupts]
            if interruptions:
                waiting = interruptions[0]
                status = "waiting_approval" if waiting["kind"] == "approval" else "waiting_job"
                run(store.update(rid, user, status=status, patch={"waiting": waiting, "resume": None}))
                if status == "waiting_approval":
                    nodes.event(record, "question.required", kind="medium_approval", question=waiting["summary"])
                    run(repo.add_message(cid, user, "assistant", waiting["summary"], agent_mode="medium"))
                else:
                    nodes.event(record, "tool.progress", tool="medium_job", project_id=waiting["project_id"],
                                message="کار به موتور پروژه تحویل شد؛ ادامهٔ برنامه پس از پایان این مرحله انجام می‌شود.")
            else:
                run(store.update(rid, user, status="completed", patch={"waiting": None, "resume": None}))
    except Exception as exc:
        stopped = isinstance(exc, InterruptedError) or studio_flags.generation(user, cid) != generation
        log.exception("Medium execution stopped run=%s", rid)
        # Keep provider errors, filesystem paths and prompts in server logs only.
        message = ("اجرای Medium با درخواست شما متوقف شد." if stopped else
                   "اجرای EditorGPT Medium کامل نشد. وضعیت پروژه و مراحل ذخیره شده‌اند؛ می‌توانید از همین اجرا دوباره تلاش کنید یا برای پیام بعدی خودتان Lite را انتخاب کنید. موتور خودکار تغییر نکرد.")
        from brain.lm_gateway import GatewayError
        if isinstance(exc, (nodes.InvalidEditingPlan, tools.PreflightUnavailable)):
            message = str(exc)
        elif isinstance(exc, GatewayError) and "capability-verified model" in str(exc):
            message = "اتصال مدل برای این مسیر در Gateway لوکال آماده نیست؛ فهرست مدل‌ها را همگام‌سازی و قابلیت متن مدل انتخاب‌شده را آزمایش کنید. اجرا متوقف شد و موتور Medium تغییر نکرد."
        elif isinstance(exc, httpx.TransportError) or (isinstance(exc, GatewayError) and (exc.status == 504 or "RemoteProtocolError" in str(exc))):
            message = "سرویس مدل در Gateway پاسخ را کامل نداد یا اتصال را قطع کرد. مراحل ذخیره شده‌اند؛ از همین اجرا دوباره تلاش کنید. موتور Medium و مدل انتخاب‌شده خودکار تغییر نکردند."
        detail = f"{type(exc).__name__}: {str(exc)[:600]}"            # kept on the run (not shown to the person) so the cause survives a container restart
        run(store.update(rid, user, status="cancelled" if stopped else "failed", patch={"error": message, "error_detail": detail}))
        nodes.event(record, "message.stopped" if stopped else "tool.failed", message=message)
        run(repo.add_message(cid, user, "assistant", message, agent_mode="medium"))
    finally:
        _generation.reset(token)
        nodes.event(record, "work.state", busy=studio_flags.busy(user, cid))


def execute(record):
    return _execute(record["conversation_id"], record["user_key"], record)


async def resume_ready(cid, user):
    """Called after existing job synchronization. No polling thread, LLM, or occupied worker while waiting."""
    from app.agents.dispatcher import dispatch
    for record in await store.runs(cid, user):
        if record["agent_mode"] != "medium" or record["status"] != "waiting_job": continue
        waiting = record["data"].get("waiting") or {}
        value = await repo.get_project(waiting["project_id"], user)
        if value["status"] == "running" and value["state"].get("workflow") != "awaiting_approval": continue
        claimed = await store.update(record["id"], user, status="queued", claim={"waiting_job"}, patch={"resume": {"job": True}})
        if claimed: await dispatch(record["id"], user)


async def recover_interrupted(cid, user):
    """Lost workers become manually resumable; never replay ambiguous writes automatically."""
    from datetime import datetime, timezone
    if studio_flags.busy(user, cid): return
    for record in await store.runs(cid, user):
        if record["agent_mode"] != "medium" or record["status"] != "running": continue
        updated = datetime.fromisoformat(record["updated_at"])
        if not updated.tzinfo: updated = updated.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - updated).total_seconds() < 30: continue
        await store.update(record["id"], user, status="failed", claim={"running"}, patch={"error":
            "ارتباط با اجرای Medium قطع شده است. مراحل ذخیره‌اند؛ ادامه فقط با تأیید شما انجام می‌شود و عملیات با نتیجهٔ نامشخص تکرار نمی‌شود."})
