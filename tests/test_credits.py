"""Token credits: weighted cost, atomic balance, gate, attribution through threads, orders."""
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import credits
from app.models import Base
from brain import lm_gateway as gateway
from brain import lm_adapters as adapters


@pytest.fixture()
def db(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path}/c.db"
    engine = create_async_engine(url, poolclass=NullPool)
    async def init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    asyncio.run(init())
    monkeypatch.setattr(credits, "AsyncSessionLocal", async_sessionmaker(engine, expire_on_commit=False))
    monkeypatch.setattr(credits, "DB_AVAILABLE", True)
    monkeypatch.setattr(credits, "settings", lambda fresh=False: {**credits.DEFAULT_SETTINGS})
    return engine


def record(**kw):
    base = {"id": "r1", "user_id": "7", "route": "script_writer", "endpoint": "chat/completions", "requested_model": "CLAUDE_OPUS_5_5", "actual_model": "CLAUDE_OPUS_5_5",
            "status": "success", "input_tokens": 32930, "output_tokens": 3279, "conversation_id": "c1", "project_id": "m1", "project_kind": "motion", "job_id": "m1"}
    return {**base, **kw}


def test_opus_cost_matches_the_gateway_price():
    cost = credits.compute(record())
    assert cost["credits"] == 32930 + 3279 * 5                     # 1 per input token, 5 per output token
    assert round(cost["credits"] * credits.USD_PER_CREDIT, 4) == 0.1973   # $4 / $20 per million = the real price of that call


def test_cache_tokens_are_priced_apart_and_not_double_counted():
    cost = credits.compute(record(input_tokens=10000, output_tokens=0, cache_read_tokens=8000, cache_write_tokens=1000))
    assert cost["credits"] == 1000 * 1.0 + 8000 * 0.1 + 1000 * 1.25
    assert cost["breakdown"]["fresh_in"] == 1000


def test_models_are_matched_by_family_even_through_custom_prefixes():
    assert credits.weight_for("custom:CLAUDE_OPUS_5_5#jarvis-all-models")[0] == "claude_opus"
    assert credits.weight_for("claude-sonnet-5-5")[0] == "claude_sonnet"
    assert credits.weight_for("gpt-4.1-mini")[0] == "gpt_4_1_mini"          # the longer key wins over gpt_4_1
    assert credits.weight_for("something-new")[0] == "default"


def test_failed_calls_without_tokens_cost_nothing_but_media_costs_a_flat_fee():
    assert credits.compute(record(status="failed", input_tokens=None, output_tokens=None))["credits"] == 0
    image = credits.compute(record(route="photorealistic_image", endpoint="images/generations", input_tokens=None, output_tokens=None, requested_model="gemini-3-1-flash-image", actual_model=None))
    assert image["unit"] == "call" and image["credits"] == credits.DEFAULT_SETTINGS["per_call"]["image"]


def test_usage_parsing_keeps_cache_apart():
    openai = adapters.usage({"usage": {"prompt_tokens": 100, "completion_tokens": 5, "prompt_tokens_details": {"cached_tokens": 60}}})
    assert (openai["input_tokens"], openai["cache_read_tokens"]) == (100, 60)
    claude = adapters.usage({"usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 80, "cache_creation_input_tokens": 10}})
    assert claude["input_tokens"] == 100 and claude["cache_write_tokens"] == 10      # Anthropic's input excludes the cache; we add it back


def test_missing_usage_is_estimated_from_the_text():
    usage = gateway._estimate_missing({"input_tokens": None, "output_tokens": None}, "chat", {"messages": [{"role": "user", "content": "x" * 3000}]}, {"output_text": "y" * 300}, None)
    assert usage["usage_estimated"] and usage["output_tokens"] == 100 and usage["input_tokens"] > 1000
    assert gateway._estimate_missing({"input_tokens": 5, "output_tokens": 1}, "chat", {}, {}, None)["input_tokens"] == 5


def test_charge_takes_from_the_balance_and_links_the_ledger(db):
    rec = record()
    credits.charge(rec)
    assert rec["credits"] == 49325 and rec["credits_balance_after"] == 1_000_000 - 49325
    ledger = asyncio.run(credits.ledger("7"))
    assert ledger["total"] == 2                                       # the initial grant + this call
    usage = [e for e in ledger["items"] if e["kind"] == "usage"][0]
    assert (usage["request_id"], usage["conversation_id"], usage["project_id"], usage["amount"]) == ("r1", "c1", "m1", -49325)
    assert rec["cost_estimated"] and round(rec["cost"], 4) == 0.1973


def test_a_call_without_a_user_is_recorded_but_not_billed(db):
    rec = record(user_id=None)
    credits.charge(rec)
    assert rec["credits"] > 0 and "credits_balance_after" not in rec


def test_concurrent_charges_never_lose_an_update(db):
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda i: credits.charge(record(id=f"r{i}", input_tokens=1000, output_tokens=0)), range(40)))
    state = asyncio.run(credits.account("7"))
    assert state["balance"] == 1_000_000 - 40 * 1000 and state["used_total"] == 40 * 1000


def test_new_requests_are_refused_when_empty_but_running_work_may_go_negative(db):
    credits.charge(record(input_tokens=999_000, output_tokens=0))
    asyncio.run(credits.require("7"))                                 # still 1000 left: allowed
    credits.charge(record(id="r2", input_tokens=5000, output_tokens=0))      # the running film finishes anyway
    assert asyncio.run(credits.account("7"))["balance"] == -4000
    with pytest.raises(credits.CreditsExhausted):
        asyncio.run(credits.require("7"))
    with pytest.raises(HTTPException) as caught:
        asyncio.run(credits.gate("7"))
    assert caught.value.status_code == 402 and "اعتبار" in caught.value.detail["message"]


def test_admin_adjustment_and_unlimited(db):
    asyncio.run(credits.account("9"))
    assert asyncio.run(credits.apply("9", -1_000_000, "admin", fields={"actor": "1"})) == 0
    with pytest.raises(credits.CreditsExhausted):
        asyncio.run(credits.require("9"))
    asyncio.run(credits.set_unlimited("9", True))
    asyncio.run(credits.require("9"))
    assert asyncio.run(credits.apply("9", 500, "admin")) == 500


def test_enforcement_can_be_switched_off(db, monkeypatch):
    monkeypatch.setattr(credits, "settings", lambda fresh=False: {**credits.DEFAULT_SETTINGS, "enforce": False})
    asyncio.run(credits.apply("8", -2_000_000, "admin"))
    asyncio.run(credits.require("8"))


def test_an_order_grants_its_credits_exactly_once(db):
    packages = asyncio.run(credits.packages())
    order = asyncio.run(credits.create_order("7", packages[0]["id"]))
    assert order["status"] == "pending" and asyncio.run(credits.account("7"))["balance"] == 1_000_000
    for _ in range(3):
        asyncio.run(credits.mark_paid(order["id"], actor="1"))
    assert asyncio.run(credits.account("7"))["balance"] == 1_000_000 + packages[0]["credits"]


def test_usage_totals_per_chat_and_per_project(db):
    credits.charge(record(id="a", conversation_id="c1", project_id="m1", input_tokens=1000, output_tokens=0))
    credits.charge(record(id="b", conversation_id="c1", project_id="m2", input_tokens=2000, output_tokens=0))
    by_chat = asyncio.run(credits.usage_by("7", "conversation_id"))
    assert by_chat[0]["id"] == "c1" and by_chat[0]["credits"] == 3000 and by_chat[0]["calls"] == 2
    assert {p["id"]: p["credits"] for p in asyncio.run(credits.usage_by("7", "project_id"))} == {"m1": 1000, "m2": 2000}
    assert asyncio.run(credits.project_breakdown("7", "m1"))["total"] == 1000


def test_attribution_follows_threads_and_pools():
    seen = {}
    def read(name):
        seen[name] = (gateway.user_context.get(), gateway.conversation_context.get(), gateway.work_context.get(), gateway.job_context.get())
    with gateway.work_scope("motion", "m1", user=7, conversation="c1"):
        t = threading.Thread(target=read, args=("thread",)); t.start(); t.join()
        with ThreadPoolExecutor(2) as pool:
            pool.submit(read, "pool").result()
    expected = ("7", "c1", ("motion", "m1"), "m1")
    assert seen == {"thread": expected, "pool": expected}
    t = threading.Thread(target=read, args=("after",)); t.start(); t.join()
    assert seen["after"] == (None, None, None, None)                  # nothing leaks out of the scope


def test_pooled_worker_does_not_keep_the_previous_owner():
    with ThreadPoolExecutor(1) as pool:
        out = []
        with gateway.work_scope("motion", "m1", user=1):
            pool.submit(lambda: out.append(gateway.user_context.get())).result()
        pool.submit(lambda: out.append(gateway.user_context.get())).result()
    assert out == ["1", None]


def test_record_carries_the_work_and_tokens(monkeypatch):
    with gateway.work_scope("talking", "j9", user=3, conversation="c5"):
        rec = gateway._record("script_writer", "chat", "CLAUDE_OPUS_5_5", 0.0, [{"model": "CLAUDE_OPUS_5_5", "http_status": 200}],
                              {"model": "CLAUDE_OPUS_5_5", "usage": {"prompt_tokens": 10, "completion_tokens": 2}}, {}, request={"messages": []})
    assert (rec["user_id"], rec["conversation_id"], rec["project_kind"], rec["project_id"], rec["job_id"]) == ("3", "c5", "talking", "j9", "j9")
    assert rec["input_tokens"] == 10 and rec["output_tokens"] == 2


def test_admin_routes_adjust_pay_and_settings(db, tmp_path, monkeypatch):
    from types import SimpleNamespace
    from app.config import settings as app_settings
    from app.routers import lm_admin
    monkeypatch.setattr(app_settings, "JOBS_DIR", str(tmp_path / "jobs"))
    request = SimpleNamespace(state=SimpleNamespace(user=SimpleNamespace(id=1)))
    after = asyncio.run(lm_admin.credit_adjust(request, "7", lm_admin.CreditAdjust(amount=2_000_000, note="هدیه")))
    assert after["balance"] == 3_000_000 and after["granted_total"] == 3_000_000
    entries = asyncio.run(credits.ledger("7"))["items"]
    assert entries[0]["kind"] == "admin" and entries[0]["actor"] == "1" and entries[0]["note"] == "هدیه"
    with pytest.raises(HTTPException):
        asyncio.run(lm_admin.credit_adjust(request, "7", lm_admin.CreditAdjust(amount=0)))
    order = asyncio.run(credits.create_order("7", asyncio.run(credits.packages())[0]["id"]))
    paid = asyncio.run(lm_admin.credit_order_paid(request, order["id"]))
    assert paid["status"] == "paid"
    with pytest.raises(HTTPException):
        asyncio.run(lm_admin.credit_order_paid(request, "missing"))


def test_weights_table_is_editable_and_changes_the_cost(tmp_path, monkeypatch):
    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "JOBS_DIR", str(tmp_path / "jobs"))
    credits._cache.update(at=0.0, value=None)
    saved = credits.save_settings({"initial_grant": 250000, "weights": {"claude_opus": {"in": 2.0, "out": 10.0, "cache": 0.2, "write": 2.5}}})
    assert saved["initial_grant"] == 250000 and saved["weights"]["claude_opus"]["in"] == 2.0 and "claude_sonnet" in saved["weights"]
    assert credits.compute(record(input_tokens=1000, output_tokens=100))["credits"] == 3000
    credits._cache.update(at=0.0, value=None)


def test_tables_are_created_on_first_use_without_a_migration(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/empty.db", poolclass=NullPool)
    monkeypatch.setattr(credits, "AsyncSessionLocal", async_sessionmaker(engine, expire_on_commit=False))
    monkeypatch.setattr(credits, "DB_AVAILABLE", True)
    monkeypatch.setattr(credits, "_schema_ready", False)
    monkeypatch.setattr(credits, "settings", lambda fresh=False: {**credits.DEFAULT_SETTINGS})
    assert asyncio.run(credits.account("5"))["balance"] == 1_000_000
    assert asyncio.run(credits.packages())[0]["id"] == "p1"


def test_a_films_calls_count_under_its_chat_even_when_they_carry_no_chat_id(db):
    from app.models import StudioConversation, StudioProject
    async def seed():
        async with credits.AsyncSessionLocal() as s:
            s.add(StudioConversation(id="c9", user_key="7", title="t"))
            s.add(StudioProject(id="p9", conversation_id="c9", user_key="7", engine="talking", title="film", external_ref="job9"))
            await s.commit()
    asyncio.run(seed())
    credits.charge(record(id="a", conversation_id="c9", project_id=None, input_tokens=1000, output_tokens=0))
    credits.charge(record(id="b", conversation_id=None, project_id="job9", project_kind="talking", input_tokens=2000, output_tokens=0))
    chats = asyncio.run(credits.chat_usage("7"))
    assert [(c["id"], c["credits"], c["calls"]) for c in chats] == [("c9", 3000, 2)]
    assert asyncio.run(credits.conversation_for_project("job9")) == "c9"
