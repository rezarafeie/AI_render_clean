"""Real LangGraph/checkpoint tests; model and costly backend calls are test doubles only."""
import asyncio
from types import SimpleNamespace

import pytest
from langgraph.types import Command
from app import studio_store as s
from app.agents import store, dispatcher
from app.agents.medium import nodes, tools
from app.agents.medium.graph import build, config, execute
from app.agents.medium.checkpoints import saver


@pytest.fixture(autouse=True)
def local_store(monkeypatch):
    monkeypatch.setattr(s, "DB_AVAILABLE", False)


def call(coro): return asyncio.run(coro)


def seed(mode="medium"):
    cid = call(s.repo.create_conversation("alice"))["id"]
    msg = call(s.repo.add_message(cid, "alice", "user", "ویدیو را بررسی کن", agent_mode=mode))
    return call(store.create_run(cid, "alice", msg["id"], mode, {"text": msg["content"], "attachment_ids": []}))


def test_preferences_scoped_and_legacy_lite():
    assert call(store.preference("alice")) == "lite"
    assert call(store.preference("alice", "medium")) == "medium"
    assert call(store.preference("bob")) == "lite"
    assert call(store.preference("alice")) == "medium"
    with pytest.raises(ValueError): call(store.preference("alice", "auto"))


def test_storyboard_keeps_original_brief_and_source_url(monkeypatch):
    from app import studio_orchestrator as shared
    record = seed()
    original = 'ساخت تبلیغ از https://example.com/product با حفظ تصویر واقعی و نریشن فارسی'
    record['data']['request']['text'] = original
    captured = []
    monkeypatch.setattr(shared, '_create_motion', lambda cid, user, message, prompt, assets: captured.append(prompt))
    tools.execute(record, {'tool':'create_storyboard', 'arguments':{'prompt':'سناریوی محصول را بنویس'}})
    assert original in captured[0]
    assert 'سناریوی محصول را بنویس' in captured[0]


def test_storyboard_reuses_owned_inspected_source_and_images(monkeypatch, tmp_path):
    import hashlib, json
    from app import studio_orchestrator as shared
    from app.studio_flags import conversation_dir
    record=seed();url='https://example.com/product'
    record['data']['request']['text']='تبلیغ '+url
    directory=conversation_dir(record['user_key'],record['conversation_id'])/'medium'/record['id']
    directory.mkdir(parents=True)
    image=directory/'product.jpg';image.write_bytes(b'test-only')
    page={'url':url,'title':'محصول','content':['متن واقعی دریافت‌شده از منبع محصول'], 'images':[{'file':str(image)}]}
    (directory/('source-'+hashlib.sha256(url.encode()).hexdigest()+'.json')).write_text(json.dumps(page))
    monkeypatch.setattr(shared,'_page_brief',lambda p:{'product_name':'محصول'})
    captured=[]
    monkeypatch.setattr(shared,'_create_motion',lambda *args:captured.append(args))
    tools.execute(record,{'tool':'create_storyboard','arguments':{'prompt':'سناریو بساز'}})
    sources=captured[0][-1]
    assert sources.pages[0]['url']==url and sources.images==[str(image)]


def test_run_ownership_and_atomic_claim():
    record = seed()
    with pytest.raises(KeyError): call(store.get_run(record["id"], "bob"))
    assert call(store.update(record["id"], "alice", status="running", claim={"queued"}))
    assert call(store.update(record["id"], "alice", status="running", claim={"queued"})) is None
    assert call(s.repo.get_conversation(record["conversation_id"], "alice"))["messages"][0]["agent_mode"] == "medium"


def test_deterministic_dispatch_lite_unchanged(monkeypatch):
    record = seed("lite")
    import app.studio_orchestrator as legacy
    calls = []
    monkeypatch.setattr(legacy, "process_message", lambda *args: calls.append(args))
    dispatcher.execute_run(record["id"], "alice")
    dispatcher.execute_run(record["id"], "alice")
    assert len(calls) == 1
    assert calls[0] == (record["conversation_id"], "alice", record["message_id"], "ویدیو را بررسی کن", [], None)


def test_medium_failure_never_dispatches_lite(monkeypatch):
    record = seed()
    import app.studio_orchestrator as legacy
    import brain.lm_gateway
    monkeypatch.setattr(legacy, "process_message", lambda *a: pytest.fail("silent Lite fallback"))
    monkeypatch.setattr(brain.lm_gateway, "complete", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("offline")))
    dispatcher.execute_run(record["id"], "alice")
    assert call(store.get_run(record["id"], "alice"))["status"] == "failed"
    with pytest.raises(ValueError): dispatcher.ensure_available("auto")


def test_tools_reject_paths_users_unknown_fields_and_other_projects(tmp_path):
    record = seed()
    for args in ({"attachment_id": "unknown", "path": "/etc/passwd"}, {"attachment_id": "unknown", "user_key": "bob"}):
        with pytest.raises(ValueError): tools.validate(record, {"tool": "inspect_media", "arguments": args})
    other = call(s.repo.create_conversation("bob"))
    project = call(s.repo.create_project(other["id"], "bob", "talking", "Private"))
    with pytest.raises(KeyError): tools.validate(record, {"tool": "check_render_status", "arguments": {"project_id": project["id"]}})
    another = call(s.repo.create_conversation("alice"))
    project = call(s.repo.create_project(another["id"], "alice", "talking", "Other chat"))
    with pytest.raises(ValueError): tools.project(record, project["id"])


def test_sqlite_interrupt_survives_recompile_and_tool_runs_once(monkeypatch):
    record = seed()
    plan = {"summary": "اصلاح همین پروژه", "steps": [{"tool": "modify_project", "arguments": {"project_id": "p", "request": "زوم"}, "label": "اصلاح زوم"}]}
    monkeypatch.setattr(nodes, "plan", lambda r, st: {"plan": plan, "index": 0, "rounds": 1})
    monkeypatch.setattr(nodes, "finish", lambda *a: {"finished": True})
    calls = []
    monkeypatch.setattr(tools, "execute", lambda *a: calls.append(a) or {"result": "edited"})
    with saver() as checkpoint:
        graph = build(record, checkpoint)
        graph.invoke({}, config(record), durability="sync")
        snapshot = graph.get_state(config(record))
        assert snapshot.tasks[0].interrupts[0].value["kind"] == "approval"
        assert not calls
    # New connection and compiled graph, not memory from the first process.
    with saver() as checkpoint:
        graph = build(record, checkpoint)
        graph.invoke(Command(resume={"approve": True}), config(record), durability="sync")
        assert graph.get_state(config(record)).values["finished"]
    assert len(calls) == 1
    # A node retry after persistence loss returns its ledger result instead of repeating a write.
    nodes.tool(record, {"plan": plan, "index": 0, "rounds": 1, "results": []})
    assert len(calls) == 1


def test_uncertain_expensive_operation_not_replayed(monkeypatch):
    record = seed()
    step = {"tool": "modify_project", "arguments": {}, "label": "edit"}
    call(store.update(record["id"], "alice", patch={"operations": {"1:0:modify_project": {"status": "started"}}}))
    monkeypatch.setattr(tools, "execute", lambda *a: pytest.fail("replayed ambiguous write"))
    with pytest.raises(ValueError, match="مشخص نیست"):
        nodes.tool(record, {"plan": {"steps": [step]}, "index": 0, "rounds": 1})


def test_known_preflight_failure_can_retry_but_uncertain_writes_cannot(monkeypatch):
    record = seed()
    step = {"tool": "create_storyboard", "arguments": {}, "label": "طراحی"}
    state = {"plan": {"steps": [step]}, "index": 0, "rounds": 1}
    monkeypatch.setattr(tools, "execute", lambda *a: (_ for _ in ()).throw(tools.PreflightUnavailable("preflight failed")))
    healed = nodes.tool(record, state)                     # a rejected step replans with its error instead of stopping the run
    assert healed["healing"] is True and "preflight failed" in healed["plan_feedback"]
    with pytest.raises(tools.PreflightUnavailable): nodes.tool(record, {**state, "failed": healed["failed"]})     # the same error twice: a loop, stop
    entry = call(store.get_run(record["id"], "alice"))["data"]["operations"]["1:0:create_storyboard"]
    assert entry == {"status": "failed", "tool": "create_storyboard", "safe_to_retry": True}
    monkeypatch.setattr(tools, "execute", lambda *a: {"project_id": "real-id"})
    monkeypatch.setattr(nodes, "narrate_result", lambda *a: None)
    assert nodes.tool(record, state)["results"][-1]["project_id"] == "real-id"


def test_waiting_job_does_not_hold_worker_and_resumes_once(monkeypatch):
    from app.agents.medium.graph import resume_ready
    record = seed()
    project = call(s.repo.create_project(record["conversation_id"], "alice", "talking", "Video", {"workflow": "analyzing"}, "job"))
    call(s.repo.update_project(project["id"], "alice", status="running"))
    call(store.update(record["id"], "alice", status="waiting_job", patch={"waiting": {"project_id": project["id"]}}))
    queued = []
    async def enqueue(*args, **kwargs): queued.append(args)
    monkeypatch.setattr(dispatcher, "dispatch", enqueue)
    call(resume_ready(record["conversation_id"], "alice"))
    assert not queued
    call(s.repo.update_project(project["id"], "alice", status="awaiting_confirmation", state={"workflow": "awaiting_approval"}))
    call(resume_ready(record["conversation_id"], "alice"))
    call(resume_ready(record["conversation_id"], "alice"))
    assert queued == [(record["id"], "alice")]


def test_gateway_stream_uses_existing_sse_contract_and_persists(monkeypatch):
    import brain.lm_gateway as gateway
    record = seed()
    seen = []
    monkeypatch.setattr(gateway, "stream_chat", lambda route, messages, **kwargs: seen.append(route) or iter(["سلام", "؛ آماده‌ام."]))
    nodes.finish(record, {"plan": {"summary": "پرسش ضروری", "steps": []}, "results": []})
    events = call(s.repo.events(record["conversation_id"], "alice"))
    assert seen == ["conversation_response"]
    assert [e["data"]["text"] for e in events if e["type"] == "assistant.response.delta"] == ["سلام", "سلام؛ آماده‌ام."]
    history = call(s.repo.get_conversation(record["conversation_id"], "alice"))
    assert history["messages"][-1]["content"] == "سلام؛ آماده‌ام."
    assert history["messages"][-1]["agent_mode"] == "medium"


def test_medium_opening_streams_persists_and_is_not_repeated(monkeypatch):
    import brain.lm_gateway as gateway
    record = seed()
    monkeypatch.setattr(gateway, "configured", lambda: True)
    monkeypatch.setattr(gateway, "stream_chat", lambda *a, **kw: iter(["ابتدا ویدیوی ", "همین پروژه را بررسی می‌کنم."]))
    nodes.opening(record)
    nodes.opening(record)
    history = call(s.repo.get_conversation(record["conversation_id"], "alice"))
    assert len(history["messages"]) == 2
    assert history["messages"][-1]["agent_mode"] == "medium"
    events = call(s.repo.events(record["conversation_id"], "alice"))
    assert any(e["type"] == "assistant.response.delta" for e in events)
    assert sum(e["type"] == "assistant.response.completed" for e in events) == 1


def test_medium_gateway_configuration_error_is_actionable(monkeypatch):
    import brain.lm_gateway
    from brain.lm_gateway import GatewayError
    record = seed()
    monkeypatch.setattr(brain.lm_gateway, "complete", lambda *a, **kw: (_ for _ in ()).throw(
        GatewayError("No enabled, capability-verified model for this route")))
    execute(record)
    result = call(store.get_run(record["id"], "alice"))
    assert result["status"] == "failed"
    assert "همگام‌سازی" in result["data"]["error"]


def test_medium_completed_tool_narration_not_repeated_on_retry(monkeypatch):
    record = seed()
    step = {"tool": "inspect_media", "arguments": {}, "label": "بررسی ویدیو"}
    state = {"plan": {"steps": [step]}, "index": 0, "rounds": 1}
    narrated = []
    monkeypatch.setattr(tools, "execute", lambda *a: {"duration": 30})
    monkeypatch.setattr(nodes, "narrate_result", lambda *a: narrated.append(a[-1]))
    nodes.tool(record, state)
    nodes.tool(record, state)
    assert narrated == [{"duration": 30}]


def test_protocol_disconnect_uses_configured_stream_fallback(monkeypatch):
    import httpx
    import json
    from brain import lm_gateway as gateway
    from app import lm_store
    from app.config import settings
    monkeypatch.setattr(settings, "LMAPI_API_KEY", "unit-test-only")
    route = gateway.defaults()["conversation_response"]
    lm_store.save("routes", {"conversation_response": {**route, "models": ["one", "two"], "streaming": True}})
    lm_store.save("models", {name: {"enabled": True, "verified": ["chat", "streaming"]} for name in ("one", "two")})
    seen = []
    def respond(request):
        seen.append(json.loads(request.content)["model"])
        if len(seen) == 1: raise httpx.RemoteProtocolError("disconnected")
        data = {"choices": [{"delta": {"content": "سلام"}, "finish_reason": "stop"}]}
        return httpx.Response(200, text="data: " + json.dumps(data) + "\n\ndata: [DONE]\n\n")
    monkeypatch.setattr(gateway, "_client", lambda timeout: httpx.Client(transport=httpx.MockTransport(respond)))
    assert "".join(gateway.stream_chat("conversation_response", [])) == "سلام"
    assert seen == ["one", "two"]


def test_narration_keeps_gateway_owner_and_medium_message(monkeypatch):
    from app import studio_narrator
    from brain import lm_gateway as gateway
    record = seed()
    seen = []
    monkeypatch.setattr(gateway, "configured", lambda: True)
    def stream(*a, **kw):
        seen.append(gateway.user_context.get())
        yield "ویدیو بررسی شد."
    monkeypatch.setattr(gateway, "stream_chat", stream)
    token = gateway.user_context.set("alice")
    try:
        studio_narrator.narrate(record["conversation_id"], "alice", "test-context", {"agent_mode": "medium"}, background=False)
    finally: gateway.user_context.reset(token)
    assert seen == ["alice"]
    history = call(s.repo.get_conversation(record["conversation_id"], "alice"))
    assert history["messages"][-1]["agent_mode"] == "medium"


def test_sse_unavailable_uses_real_same_route_response(monkeypatch):
    from brain import lm_gateway as gateway, lm_direct
    calls = []
    def unavailable(*args, **kwargs):
        raise lm_direct.DirectError("offline")
        yield
    monkeypatch.setattr(lm_direct, "stream_fallback", unavailable)
    monkeypatch.setattr(gateway, "complete", lambda route, *a, **kw: calls.append(route) or (
        {"choices": [{"message": {"content": "پاسخ واقعی"}}]}, {}))
    assert list(gateway.stream_chat("conversation_response", [])) == ["پاسخ واقعی"]
    assert calls == ["conversation_response"]


def test_direct_collected_sse_preserves_json_and_usage(monkeypatch):
    from brain import lm_direct as direct
    provider = {"id": "jarvis", "prefer_stream": True, "format": "openai"}
    def chunks(p, messages, **kwargs):
        assert p is provider and kwargs["extra"] == {"response_format": {"type": "json_object"}}
        kwargs["_metadata"].update(model="actual-model", usage={"prompt_tokens": 2, "completion_tokens": 3}, finish_reason="stop")
        yield '{"ok":'
        yield 'true}'
    monkeypatch.setattr(direct, "stream_call", chunks)
    monkeypatch.setattr(direct, "_post", lambda *a: pytest.fail("must not use broken synchronous transport"))
    response = direct.call(provider, [], model="selected-model", tokens=20, extra={"response_format": {"type": "json_object"}})
    assert response["choices"][0]["message"]["content"] == '{"ok":true}'
    assert response["usage"]["completion_tokens"] == 3
    assert response["model"] == "actual-model"


def test_direct_stream_choice_survives_older_settings_client():
    from brain import lm_direct as direct
    direct.save_config(True, [{"id": "jarvis", "prefer_stream": True}])
    direct.save_config(True, [{"id": "jarvis"}])
    assert next(p for p in direct.config()["providers"] if p["id"] == "jarvis")["prefer_stream"]


def test_online_ai_sync_preserves_local_data_and_hides_secrets(monkeypatch, capsys, tmp_path):
    import json
    import runpy
    import sys
    from pathlib import Path
    from app import lm_store
    from app.config import settings
    from brain import lm_direct, lm_gateway
    record = seed()
    lm_store.save("models", {"local-only": {"id": "local-only"}})
    lm_store.save("routes", {"local-route": {"id": "local-route"}})
    source = {"models": {"online": {"id": "online", "verified": ["image"]}},
              "routes": {"image": {"id": "image", "enabled": True, "models": ["online"]}},
              "direct": lm_direct.config(), "keys": {"jarvis": "unit-test-secret-only"},
              "headers": {}, "settings": {}, "gateway_key": lm_gateway.secret(),
              "gateway_base": settings.LMAPI_BASE_URL}
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout=json.dumps(source).encode()))
    monkeypatch.setattr(sys, "argv", ["sync_online_ai.py", "--identity", "test-key", "--host", "test-host", "--apply"])
    script = Path(__file__).resolve().parents[1] / "scripts/sync_online_ai.py"
    runpy.run_path(str(script), run_name="__main__")
    output = capsys.readouterr().out
    assert "unit-test-secret-only" not in output
    assert json.loads(output)["routes_match"]
    assert "local-only" in lm_store.records("models")
    assert "local-route" in lm_store.records("routes")
    assert call(store.get_run(record["id"], "alice"))["status"] == "queued"
    assert lm_direct.key_for("jarvis") == "unit-test-secret-only"
    backup = Path(json.loads(output)["backup"])
    assert backup.is_dir() and (backup / "state.json").is_file()


def test_planner_bounds_evidence_without_mutating_checkpoint(monkeypatch):
    import brain.lm_gateway
    import json
    record = seed()
    state = {"results": [{"url": "https://example.com", "content": "<p>ویژگی واقعی محصول</p>"}]}
    captured = []
    def model(route, messages, **kwargs):
        captured.append((json.loads(messages[1]["content"]), route, kwargs["tokens"]))
        return {"choices": [{"message": {"content": '{"summary":"تأیید ویژگی‌ها لازم است","steps":[]}'}}]}, None
    monkeypatch.setattr(brain.lm_gateway, "complete", model)
    nodes.plan(record, state)
    payload, route, tokens = captured[0]
    assert payload["context"]["request"] == record["data"]["request"]["text"]
    assert "<p>" not in payload["observations"][0]["content"]
    assert "<p>" in state["results"][0]["content"]
    assert (route, tokens) == ("editing_agent", 6000)


def test_streamed_plan_is_validated_without_exposing_partial_json(monkeypatch):
    import brain.lm_gateway as gateway
    import brain.llm
    record = seed()
    monkeypatch.setattr(gateway, "defaults", lambda: {"editing_agent": {"streaming": True}})
    def complete(*a, **kw):
        assert kw["stream"] is True
        content = '{"summary":"نیاز به تأیید دارد","steps":[]}'
        kw["validate_response"](content)
        return {"choices": [{"message": {"content": content}}]}, {}
    monkeypatch.setattr(gateway, "complete", complete)
    monkeypatch.setattr(brain.llm, "gateway_json", lambda *a: pytest.fail("wrong transport"))
    result = nodes.plan(record, {})
    assert result["plan"]["steps"] == []
    events = call(s.repo.events(record["conversation_id"], "alice"))
    assert not any(e["type"].startswith("assistant.response") for e in events)


@pytest.mark.parametrize("bad", [
    '{"summary":"برنامه","steps":[]}\nExtra commentary',
    '{"summary":"برنامه","steps":[{"tool":"check_render_status","label":"وضعیت","arguments":{"project_id":"unknown"}}]}',
])
def test_real_gateway_rejects_invalid_streamed_plan_before_fallback(monkeypatch, bad):
    from brain import lm_gateway as gateway
    from app import lm_store
    record = seed()
    route = gateway.defaults()["editing_agent"]
    lm_store.save("routes", {"editing_agent": {**route, "streaming": True, "models": ["bad", "good"], "max_retries": 0}})
    lm_store.save("models", {m: {"enabled": True, "verified": ["chat", "streaming"]} for m in ("bad", "good")})
    seen = []
    def wire(endpoint, body, timeout):
        seen.append(body["model"])
        content = bad if body["model"] == "bad" else '{"summary":"اطلاعات لازم دریافت شد","steps":[]}'
        return {"choices": [{"message": {"content": content}}]}, {}, 200
    monkeypatch.setattr(gateway, "_wire_chat_stream", wire)
    monkeypatch.setattr(tools, "execute", lambda *a: pytest.fail("unapproved execution"))
    assert nodes.plan(record, {})["plan"]["steps"] == []
    assert seen == ["bad", "good"]
    audit = lm_store.logs()["items"][0]
    assert audit["fallback_count"] == 1
    assert audit["fallback_history"][0]["error"] == "Model returned invalid structured output"


def test_invalid_plan_has_one_bounded_repair_and_no_tool_execution(monkeypatch):
    from brain import lm_gateway as gateway
    from app import lm_store
    record = seed()
    route = gateway.defaults()["editing_agent"]
    lm_store.save("routes", {"editing_agent": {**route, "streaming": True, "models": ["one"], "max_retries": 0}})
    lm_store.save("models", {"one": {"enabled": True, "verified": ["chat", "streaming"]}})
    requests = []
    def wire(endpoint, body, timeout):
        requests.append(body)
        return {"choices": [{"message": {"content": '{"summary":"برنامه","steps":[]} trailing'}}]}, {}, 200
    monkeypatch.setattr(gateway, "_wire_chat_stream", wire)
    monkeypatch.setattr(gateway, "_direct_fallback", lambda *a, **kw: None)
    monkeypatch.setattr(tools, "execute", lambda *a: pytest.fail("invalid plan executed"))
    with pytest.raises(ValueError, match="پس از تلاش اصلاحی"):
        nodes.plan(record, {})
    assert len(requests) == 2
    assert "Validation rejected" in requests[1]["messages"][-1]["content"]


def test_api_modes_default_sync_and_execution_snapshot(monkeypatch):
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient
    from app.routers.studio import router
    application = FastAPI()
    @application.middleware("http")
    async def user(request: Request, next):
        request.state.user = SimpleNamespace(id="alice")
        return await next(request)
    application.include_router(router)
    queued = []
    async def enqueue(*args, **kwargs): queued.append(args)
    monkeypatch.setattr(dispatcher, "dispatch", enqueue)
    with TestClient(application) as client:
        assert client.get("/studio/agent-preferences").json()["default_agent_mode"] == "lite"
        client.put("/studio/agent-preferences", json={"default_agent_mode": "medium"}).raise_for_status()
        cid = client.post("/studio/conversations", json={}).json()["id"]
        assert call(s.repo.get_conversation(cid, "alice"))["state"]["agent_mode"] == "medium"
        response = client.post(f"/studio/conversations/{cid}/messages", json={"content": "سلام", "agent_mode": "medium"})
        assert response.status_code == 202
        rid = response.json()["agent_run_id"]
        client.patch(f"/studio/conversations/{cid}", json={"agent_mode": "lite"}).raise_for_status()
        assert call(store.get_run(rid, "alice"))["agent_mode"] == "medium"
        assert client.get("/studio/agent-preferences").json()["default_agent_mode"] == "medium"
        assert client.post(f"/studio/conversations/{cid}/messages", json={"content": "x", "agent_mode": "auto"}).status_code == 422
        client.post(f"/studio/conversations/{cid}/messages", json={"content": "legacy"}).raise_for_status()
        assert call(store.runs(cid, "alice"))[-1]["agent_mode"] == "lite"


def test_database_preferences_runs_claims_and_isolation(tmp_path, monkeypatch):
    """Exercise the real SQLAlchemy branch, not just the local JSON fallback."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.pool import NullPool
    from app.models import StudioConversation, StudioAgentPreference, StudioAgentRun
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'agents.db'}", poolclass=NullPool)
    async def schema():
        async with engine.begin() as conn:
            for table in (StudioConversation.__table__, StudioAgentPreference.__table__, StudioAgentRun.__table__):
                await conn.run_sync(table.create)
        async with async_sessionmaker(engine)() as db:
            db.add(StudioConversation(id="chat", user_key="alice", title="Test", language="fa", status_voice_enabled=False, state={}))
            await db.commit()
    call(schema())
    monkeypatch.setattr(s, "DB_AVAILABLE", True)
    monkeypatch.setattr(s, "AsyncSessionLocal", async_sessionmaker(engine, expire_on_commit=False))
    async def owner(cid, user):
        if cid != "chat" or user != "alice": raise KeyError(cid)
        return {"id": cid}
    monkeypatch.setattr(s.repo, "get_conversation", owner)
    assert call(store.preference("alice", "medium")) == "medium"
    assert call(store.preference("bob")) == "lite"
    record = call(store.create_run("chat", "alice", "1", "medium", {"text": "test", "attachment_ids": []}))
    assert call(store.update(record["id"], "alice", status="running", claim={"queued"}))
    assert call(store.update(record["id"], "alice", status="running", claim={"queued"})) is None
    with pytest.raises(KeyError): call(store.get_run(record["id"], "bob"))
    with pytest.raises(ValueError): call(store.create_run("chat", "alice", "2", "medium", {}))
    assert len(call(store.runs("chat", "alice"))) == 1
    call(engine.dispose())


def test_real_medium_runner_interrupt_approval_resume_completion(monkeypatch):
    import brain.llm
    import brain.lm_gateway
    record = seed()
    project = call(s.repo.create_project(record["conversation_id"], "alice", "talking", "Video", {}, "job"))
    plan = {"summary": "زوم اصلاح شود", "steps": [{"tool": "modify_project", "label": "تغییر زوم", "arguments": {"project_id": project["id"], "request": "زوم ۱۱۰"}}]}
    import json
    monkeypatch.setattr(brain.lm_gateway, "complete", lambda *a, **kw: ({"choices": [{"message": {"content": json.dumps(plan)}}]}, {}))
    monkeypatch.setattr(brain.lm_gateway, "stream_chat", lambda *a, **k: iter(["برنامه اعمال شد؛ پیش‌نمایش را بررسی کنید."]))
    calls = []
    monkeypatch.setattr(tools, "execute", lambda *a: calls.append(a) or {"project_id": project["id"], "waiting": False})
    execute(record)
    waiting = call(store.get_run(record["id"], "alice"))
    assert waiting["status"] == "waiting_approval"
    assert not calls
    call(store.update(record["id"], "alice", status="queued", patch={"resume": {"approve": True}}))
    execute(call(store.get_run(record["id"], "alice")))
    assert call(store.get_run(record["id"], "alice"))["status"] == "completed"
    assert len(calls) == 1


def test_missing_medium_dependencies_is_clear_not_fallback(monkeypatch):
    import builtins
    from app.agents.medium.checkpoints import available
    original = builtins.__import__
    def importing(name, *args, **kwargs):
        if name.startswith("langgraph"): raise ImportError("unavailable")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", importing)
    with pytest.raises(ValueError, match="EditorGPT Lite"): available()


def test_stop_generation_blocks_execution(monkeypatch):
    from app import studio_flags
    record = seed()
    call(store.update(record["id"], "alice", patch={"stop_generation": 0}))
    studio_flags.bump_generation("alice", record["conversation_id"])
    monkeypatch.setattr(nodes, "plan", lambda *a: pytest.fail("model ran after stop"))
    execute(call(store.get_run(record["id"], "alice")))
    assert call(store.get_run(record["id"], "alice"))["status"] == "cancelled"


def test_actual_media_probe_adapter(tmp_path):
    import wave
    import shutil
    if not shutil.which("ffprobe"): pytest.skip("native ffprobe unavailable")
    record = seed()
    source = tmp_path / "sample.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 2000)
    asset = call(s.repo.create_attachment(record["conversation_id"], "alice", kind="audio", filename="sample.wav",
        path=str(source), mime_type="audio/wav", size_bytes=source.stat().st_size))
    result = tools.execute(record, {"tool": "inspect_media", "arguments": {"attachment_id": asset["id"]}})
    assert result["has_audio"] is True
    assert result["duration"] == pytest.approx(.25)


def test_api_approval_is_owner_scoped_single_use(monkeypatch):
    from app.routers.studio import resume_agent, AgentResume
    from fastapi import HTTPException
    record = seed()
    call(store.update(record["id"], "alice", status="waiting_approval"))
    queued = []
    async def enqueue(*a, **k): queued.append(a)
    monkeypatch.setattr(dispatcher, "dispatch", enqueue)
    request = SimpleNamespace(state=SimpleNamespace(user=SimpleNamespace(id="bob")))
    with pytest.raises(HTTPException) as private:
        call(resume_agent(request, record["id"], AgentResume(decision="approve")))
    assert private.value.status_code == 404
    request.state.user.id = "alice"
    assert call(resume_agent(request, record["id"], AgentResume(decision="approve")))["status"] == "queued"
    with pytest.raises(HTTPException) as duplicate:
        call(resume_agent(request, record["id"], AgentResume(decision="approve")))
    assert duplicate.value.status_code == 409
    assert len(queued) == 1


def test_url_adapter_cannot_exfiltrate_to_model_chosen_destinations():
    record = seed()
    call(s.repo.add_message(record["conversation_id"], "alice", "user", "https://example.com/source"))
    assert tools.validate(record, {"tool": "inspect_url", "arguments": {"url": "https://example.com/source"}}).url
    for url in ("https://evil.example/steal?data=private", "https://example.com/source?data=private"):
        with pytest.raises(ValueError, match="source URLs"):
            tools.validate(record, {"tool": "inspect_url", "arguments": {"url": url}})


def test_real_job_interrupt_resume_does_not_resubmit_tool(monkeypatch):
    record = seed()
    project = call(s.repo.create_project(record["conversation_id"], "alice", "talking", "Video", {"workflow": "production"}, "job"))
    call(s.repo.update_project(project["id"], "alice", status="running"))
    plan = {"summary": "Render", "steps": [{"tool": "modify_project", "label": "edit", "arguments": {}}]}
    monkeypatch.setattr(nodes, "plan", lambda *a: {"plan": plan, "index": 0, "rounds": 3})
    monkeypatch.setattr(nodes, "finish", lambda *a: {"finished": True})
    calls = []
    monkeypatch.setattr(tools, "execute", lambda *a: calls.append(a) or {"project_id": project["id"], "waiting": True})
    with saver() as checkpoint:
        graph = build(record, checkpoint)
        graph.invoke({}, config(record))
        graph.invoke(Command(resume={"approve": True}), config(record))
        assert graph.get_state(config(record)).tasks[0].interrupts[0].value["kind"] == "job"
    call(s.repo.update_project(project["id"], "alice", status="completed"))
    with saver() as checkpoint:
        graph = build(record, checkpoint)
        graph.invoke(Command(resume={"job": True}), config(record))
        assert graph.get_state(config(record)).values["finished"]
    assert len(calls) == 1


def test_rejected_step_stops_after_the_heal_limit(monkeypatch):
    record = seed()
    step = {"tool": "create_storyboard", "arguments": {"duration": 5}, "label": "طراحی"}
    state = {"plan": {"steps": [step]}, "index": 0, "rounds": 2, "heal": nodes.MAX_HEALS, "approved": True}
    monkeypatch.setattr(tools, "execute", lambda *a: (_ for _ in ()).throw(ValueError("bad duration")))
    with pytest.raises(ValueError): nodes.tool(record, state)
    state["heal"] = 0
    healed = nodes.tool(record, state)
    assert healed["heal"] == 1 and healed["heal_tools"] == ["create_storyboard"]


def test_medium_can_plan_a_voiced_motion_graphic():
    from app.agents.medium.state import EditingPlan
    assert any(item["name"] == "create_motion_graphic" and item["requires_approval"] for item in tools.catalog())
    plan = EditingPlan.model_validate({"summary": "s", "steps": [{"tool": "create_motion_graphic", "arguments": {"request": "سه اشتباه"}, "label": "ساخت ویدیو"}]})
    assert plan.steps[0].tool == "create_motion_graphic"
