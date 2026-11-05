"""The Lite agent: EditorGPT Lite with everything Medium's agent has.

Lite stays a router of fixed flows. This is where it hands a request that is not one fixed flow: something to look at first (an attached file, a link,
a project, the person's connected apps), a check of sound or of an Instagram text, a search of the creative library, several steps in a row, or reels
to find in a long video. The work is done by the same agent graph as Medium's (``app.agents.medium.graph``: one planner, one tool catalog, plans again
after reading something and after a project finished, repairs a rejected step, a ledger so that nothing is done twice, checkpoints that survive a
restart, a project waited for without holding a worker). Two differences, both in the graph itself and keyed on the run's mode: Lite does not ask
before each write (only in manual mode), and it does not repeat the opening reply its own flow already streamed.

The run is the ``studio_agent_runs`` row Lite already creates for the message; ``data.agent`` marks it as handed to the agent.
"""
from __future__ import annotations

from app import studio_flags
from app.agents import store
from app.studio_store import repo, run


def _request(text: str, attachment_ids: list[str], conversation: dict) -> dict:
    return {"text": text, "attachment_ids": list(attachment_ids or []), "manual_question_id": None,
            "initial_project_id": (conversation.get("state") or {}).get("current_project_id")}


def start(cid: str, user: str, message_id, text: str, attachment_ids: list[str]) -> dict:
    """Hand this message to the agent: its run is marked and queued, and a worker takes it (this Lite flow ends, so no worker is held twice)."""
    from app.agents.dispatcher import dispatch
    conversation = run(repo.get_conversation(cid, user))
    found = next((r for r in reversed(run(store.runs(cid, user))) if r["agent_mode"] == "lite" and r["message_id"] == str(message_id)), None)
    if found is None:
        found = run(store.create_run(cid, user, message_id, "lite", _request(text, attachment_ids, conversation)))
    request = {**_request(text, attachment_ids, conversation), "text": text}
    queued = run(store.update(found["id"], user, status="queued", patch={"agent": True, "request": request, "stop_generation": studio_flags.generation(user, cid)}))
    run(dispatch(found["id"], user))
    return queued


def waiting_approval(cid: str, user: str) -> dict | None:
    """A plan of the Lite agent that waits for the person's «تأیید» (manual mode only)."""
    return next((r for r in run(store.runs(cid, user)) if r["agent_mode"] == "lite" and r["data"].get("agent") and r["status"] == "waiting_approval"), None)


def approve(record: dict) -> bool:
    from app.agents.dispatcher import dispatch
    claimed = run(store.update(record["id"], record["user_key"], status="queued", claim={"waiting_approval"}, patch={"resume": {"approve": True}}))
    if claimed:
        run(dispatch(record["id"], record["user_key"]))
    return bool(claimed)


def drop_waiting(record: dict) -> None:
    run(store.update(record["id"], record["user_key"], status="cancelled", claim={"waiting_approval"}, patch={"waiting": None}))
