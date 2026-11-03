"""No routing, inference, or cross-engine fallback: the recorded choice is binding."""
from app.agents import store
from app.studio_store import repo, run


def ensure_available(mode):
    store.validate_mode(mode)
    if mode == "medium":
        from app.agents.medium.checkpoints import available
        available()  # Imports only for an explicit Medium request.


def execute_run(run_id, user):
    record = run(store.get_run(run_id, user))
    mode = store.validate_mode(record["agent_mode"])
    request = record["data"]["request"]
    if mode == "medium":
        try:
            from app.agents.medium.graph import execute
        except ImportError:
            message = "EditorGPT Medium روی Worker فعال نیست؛ وابستگی‌های Worker باید به‌روز شوند. هیچ درخواست Lite اجرا نشد."
            run(store.update(run_id, user, status="failed", patch={"error": message}))
            run(repo.emit(record["conversation_id"], "tool.failed", {"message": message, "agent_mode": mode, "run_id": run_id}))
            return
        try:
            from app.studio_title import title_in_background
            title_in_background(record["conversation_id"], user, request.get("text", ""))
        except Exception:                                   # a title is never worth a failed run
            pass
        return execute(record)
    if not run(store.update(run_id, user, status="running", claim={"queued"})): return
    from app.studio_orchestrator import process_message
    try:
        process_message(record["conversation_id"], user, record["message_id"],
                        request["text"], request["attachment_ids"], request.get("manual_question_id"))
        # Lite keeps its own workflow/error handling; do not reinterpret it.
        run(store.update(run_id, user, status="dispatched"))
    except Exception:
        run(store.update(run_id, user, status="failed")); raise


async def dispatch(run_id, user, *, lite_dispatch=None):
    record = await store.get_run(run_id, user)
    if record["agent_mode"] == "lite":
        # Preserve Lite's existing Celery task / threading path, not only its prompts.
        from app.studio_orchestrator import dispatch_message
        request = record["data"]["request"]
        if not await store.update(run_id, user, status="dispatched", claim={"queued"}): return
        try:
            (lite_dispatch or dispatch_message)(record["conversation_id"], user, record["message_id"],
                request["text"], request["attachment_ids"], request.get("manual_question_id"))
        except Exception:
            await store.update(run_id, user, status="failed"); raise
        return
    from app.celery_app import CELERY_AVAILABLE
    if CELERY_AVAILABLE:
        from app.tasks import task_studio_agent
        from request_context import celery_request_headers
        task_studio_agent.apply_async(args=[run_id, user], headers=celery_request_headers())
    else:
        import contextvars
        import threading
        context = contextvars.copy_context()
        threading.Thread(target=context.run, args=(execute_run, run_id, user),
                         daemon=True, name="studio-agent").start()
