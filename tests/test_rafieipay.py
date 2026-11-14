"""Rafiei Pay: signing, order flow, amount guard, idempotent fulfilment, untrusted callbacks."""
import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import credits, rafieipay
from app.models import Base
from app.routers import rafieipay_webhook as hook


@pytest.fixture()
def pay(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/p.db", poolclass=NullPool)
    async def init():
        async with engine.begin() as conn: await conn.run_sync(Base.metadata.create_all)
    asyncio.run(init())
    monkeypatch.setattr(credits, "AsyncSessionLocal", async_sessionmaker(engine, expire_on_commit=False))
    monkeypatch.setattr(credits, "DB_AVAILABLE", True)
    monkeypatch.setattr(credits, "settings", lambda fresh=False: {**credits.DEFAULT_SETTINGS})
    state = {"status": "pending", "amount": 500000, "requests": []}
    async def request_payment(**kw):
        state["requests"].append(kw); return {"payment_id": "rp_pay_abc123456789", "url": "https://pay.rafiei.co/checkout/rp_pay_abc123456789"}
    async def get_payment(pid):
        return {"status": state["status"], "amount_toman": state["amount"], "ref_id": "REF1"}
    monkeypatch.setattr(rafieipay, "request_payment", request_payment)
    monkeypatch.setattr(rafieipay, "get_payment", get_payment)
    asyncio.run(credits.save_package({"id": "p1", "title": "t", "credits": 5_000_000, "price": 500000, "currency": "IRT", "active": True, "sort": 1}))
    return state


def order(user="7"):
    created = asyncio.run(credits.create_order(user, "p1"))
    return asyncio.run(credits.start_payment(created["id"], user, "https://editor.example"))


def test_signature_is_hmac_sha256_over_timestamp_dot_body():
    assert len(rafieipay.sign("s", "1731634800", "")) == 64
    import hashlib, hmac
    assert rafieipay.sign("sec", "17", '{"a":1}') == hmac.new(b"sec", b'17.{"a":1}', hashlib.sha256).hexdigest()


def test_the_order_is_sent_with_its_price_and_a_server_return_address(pay):
    started = order()
    request = pay["requests"][0]
    assert request["amount_toman"] == 500000 and request["order_id"] == started["id"]
    assert request["callback_url"] == f"https://editor.example/api/webhook/rafieipay/return?order_id={started['id']}"
    assert started["payment_url"].startswith("https://pay.rafiei.co/checkout/") and started["gateway_ref"] == "rp_pay_abc123456789"


def test_unpaid_stays_pending_and_paid_adds_credits_exactly_once(pay):
    started = order()
    assert asyncio.run(credits.settle_order(started["id"]))["status"] == "pending"
    pay["status"] = "verified"
    for _ in range(3):
        assert asyncio.run(credits.settle_order(started["id"]))["status"] == "paid"
    assert asyncio.run(credits.account("7"))["balance"] == 1_000_000 + 5_000_000


def test_a_verified_payment_with_the_wrong_amount_is_never_fulfilled(pay):
    started = order()
    pay.update(status="verified", amount=1000)
    assert asyncio.run(credits.settle_order(started["id"]))["status"] == "pending"
    assert asyncio.run(credits.account("7"))["balance"] == 1_000_000


def test_a_person_cannot_pay_someone_elses_order_or_an_unpriced_package(pay):
    started = asyncio.run(credits.create_order("7", "p1"))
    with pytest.raises(KeyError):
        asyncio.run(credits.start_payment(started["id"], "8", "https://x"))
    asyncio.run(credits.save_package({"id": "p2", "title": "free", "credits": 10, "price": 0, "currency": "IRT", "active": True, "sort": 2}))
    free = asyncio.run(credits.create_order("7", "p2"))
    with pytest.raises(ValueError):
        asyncio.run(credits.start_payment(free["id"], "7", "https://x"))


def test_webhook_and_return_only_name_an_order_the_gateway_decides(pay):
    started = order()
    class Req:
        headers = {}
        async def body(self): return b'{"payment_id": "rp_pay_abc123456789", "status": "verified", "amount_toman": 1}'      # claims are ignored
    assert asyncio.run(hook.webhook(Req())).status_code == 200
    assert asyncio.run(credits.account("7"))["balance"] == 1_000_000                                     # the gateway says pending
    pay["status"] = "verified"
    asyncio.run(hook.webhook(Req()))
    assert asyncio.run(credits.account("7"))["balance"] == 6_000_000
    back = asyncio.run(hook.back_from_gateway(started["id"]))
    assert back.status_code == 303 and "pay=ok" in back.headers["location"]
    assert "pay=unknown" in asyncio.run(hook.back_from_gateway("nonexistent-order-id")).headers["location"]
    assert "pay=unknown" in asyncio.run(hook.back_from_gateway("../x")).headers["location"]


def test_config_comes_from_the_environment_or_a_private_file(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "JOBS_DIR", str(tmp_path))
    for name in ("RAFIEIPAY_API_KEY", "RAFIEIPAY_API_SECRET", "RAFIEIPAY_BASE_URL"): monkeypatch.delenv(name, raising=False)
    assert rafieipay.config() is None and not rafieipay.enabled()
    (tmp_path / "rafieipay.json").write_text('{"api_key": "k", "api_secret": "s"}')
    assert rafieipay.config() == {"api_key": "k", "api_secret": "s", "base_url": "https://pay.rafiei.co"}


def test_webhook_signature_follows_the_documented_scheme(tmp_path, monkeypatch):
    import time
    from app.config import settings
    monkeypatch.setattr(settings, "JOBS_DIR", str(tmp_path))
    (tmp_path / "rafieipay.json").write_text('{"api_key": "k", "api_secret": "sec"}')
    body = b'{"event":"payment.paid"}'
    ts = str(int(time.time()))
    good = rafieipay.sign("sec", ts, body.decode())
    assert rafieipay.webhook_signature_ok(body, ts, good)
    assert not rafieipay.webhook_signature_ok(body, ts, "0" * 64)
    assert not rafieipay.webhook_signature_ok(body + b" ", ts, good)
    assert not rafieipay.webhook_signature_ok(body, str(int(time.time()) - 5000), rafieipay.sign("sec", str(int(time.time()) - 5000), body.decode()))
    assert not rafieipay.webhook_signature_ok(body, None, good)
