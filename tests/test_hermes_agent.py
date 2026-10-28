import asyncio

import pytest
from fastapi import HTTPException

from hermes.services import agent


@pytest.fixture
def store(monkeypatch):
    rows = {}

    async def get(table, key):
        return rows.get(key)

    async def save(table, row):
        rows[row["id"]] = row
    monkeypatch.setattr(agent, "get_row", get)
    monkeypatch.setattr(agent, "save_row", save)
    return rows


def fake_llm(system, user, model):
    if "ANALYZE" in system or "ig-profile" in system:
        return {"profile": {"score": 61, "parts": [{"part": "بیو", "score": 5, "note": "کلی", "rewrite": "بیو جدید"}]},
                "content": {"top": [{"post": "الف", "why": "هوک"}], "weak": [], "patterns": ["a"], "do_more": ["x"], "stop": ["y"]},
                "strategy": {"niche": "فروش دیجیتال", "audience": "مبتدی", "pillars": ["آموزش"], "format_mix": "ریلز"},
                "questions": [{"id": "competitors", "kind": "handles", "text": "رقبا؟"}], "data_gaps": ["آمار ریچ نیست"]}
    return {"proposals": [{"title": "چرا فروش نمی‌کنی؟", "engine": "talking", "hook": "چرا فروش نمی‌کنی؟", "script": "سلام. این یک متن است.", "caption": "کپشن",
                           "hashtags": ["#a"], "editor_brief": "بریف", "length_seconds": 30, "why": "چون"}, {"title": "بدون متن"}]}


def test_a_full_agent_pass_stores_findings_questions_and_proposals(store, monkeypatch):
    async def account(user_id, fresh=False):
        return {"username": "u", "followers": 10, "follows": 1, "media_count": 2, "ig_user_id": "1"}

    async def posts(user_id, strict=False):
        return [{"id": "1", "caption": "پست", "likes": 3, "comments": 1}]
    monkeypatch.setattr(agent.composio_account, "account", account)
    monkeypatch.setattr(agent.composio_account, "posts", posts)
    monkeypatch.setattr(agent.skills, "_complete", fake_llm)
    asyncio.run(agent.run("7"))
    state = asyncio.run(agent.load("7"))
    assert state["run"]["status"] == "done" and state["analysis"]["profile"]["score"] == 61
    assert [q["id"] for q in state["questions"]] == ["competitors"]
    assert len(state["proposals"]) == 1 and state["proposals"][0]["status"] == "proposed" and state["proposals"][0]["engine"] == "talking"
    # an answer removes its question and saves competitor handles
    asyncio.run(agent.answer("7", "competitors", "@a, b"))
    state = asyncio.run(agent.load("7"))
    assert state["competitors"] == ["a", "b"] and not state["questions"]
    item = asyncio.run(agent.set_status("7", state["proposals"][0]["id"], "in_production", conversation_id="c1"))
    assert item["status"] == "in_production" and item["conversation_id"] == "c1"


def test_a_failed_connection_is_recorded_not_raised(store, monkeypatch):
    async def account(user_id, fresh=False):
        return None
    monkeypatch.setattr(agent.composio_account, "account", account)
    asyncio.run(agent.run("8"))
    assert asyncio.run(agent.load("8"))["run"]["error"] == "AGENT_NO_ACCOUNT"
    with pytest.raises(HTTPException):
        asyncio.run(agent.set_status("8", "missing", "approved"))


def test_instagram_briefs_get_the_skill_playbook_in_the_editors_engines():
    from creative import instagram_playbook as pb
    assert pb.wanted("یک ریلز اینستاگرام بساز") and not pb.wanted("یک ویدیوی تبلیغاتی محصول")
    guide = pb.add_to("GUIDE", "ریلز اینستاگرام درباره فروش")
    assert guide.startswith("GUIDE") and "Hook formulas" in guide and "Cost Confession" in guide
    assert pb.add_to("GUIDE", "ویدیوی محصول") == "GUIDE"
