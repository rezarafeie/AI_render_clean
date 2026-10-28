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
    assert [p["engine"] for p in state["proposals"]] == ["talking", "explainer"] and all(p["status"] == "proposed" for p in state["proposals"])   # 50 % talking by default
    # an answer removes its question and saves competitor handles
    asyncio.run(agent.answer("7", "competitors", "@a, b"))
    state = asyncio.run(agent.load("7"))
    assert state["competitors"] == ["a", "b"] and not state["questions"]
    item = asyncio.run(agent.set_status("7", state["proposals"][0]["id"], "in_production", conversation_id="c1"))
    assert item["status"] == "in_production" and item["conversation_id"] == "c1"


def test_the_talking_share_splits_the_ideas_between_the_engines():
    assert [agent._split(4, share) for share in (0, 25, 50, 75, 100)] == [(0, 4), (1, 3), (2, 2), (3, 1), (4, 0)]
    assert agent._share({}) == 50 and agent._share({"prefs": {"talking_share": 999}}) == 100 and agent._share({"prefs": {"talking_share": "x"}}) == 50


def test_a_zero_share_asks_only_for_produced_ideas_and_the_share_is_saved(store, monkeypatch):
    asked = []

    def llm(system, user, model):
        asked.append("talking" if "TALKING reels" in system else "explainer")
        return {"proposals": [{"title": "t", "script": "متن", "concept": "c", "style": "s", "mood": "m", "scenes": [{"seconds": 3, "visual": "v", "on_screen_text": "x", "narration": "n"}]}]}
    monkeypatch.setattr(agent.skills, "_complete", llm)
    asyncio.run(agent.set_prefs("9", 0))
    state = asyncio.run(agent.load("9"))
    assert state["prefs"]["talking_share"] == 0 and agent.public(state)["prefs"]["talking_share"] == 0
    asyncio.run(agent.propose("9", state, 4))
    assert asked == ["explainer"] and [p["engine"] for p in state["proposals"]] == ["explainer"]
    assert state["proposals"][0]["style"] == "s" and state["proposals"][0]["scenes"][0]["narration"] == "n"


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


def test_the_agent_chats_about_the_open_page(store, monkeypatch):
    seen = {}

    def fake(system, user, *args, **kwargs):
        seen["user"], seen["route"] = user, kwargs.get("route")
        return {"reply": "این صفحه خالی است.", "suggestions": ["بررسی جدید"], "action": {"type": "open_tab", "tab": "content"}}
    monkeypatch.setattr(agent.skills, "_complete", fake)
    out = asyncio.run(agent.chat("9", "اینجا چی می‌بینم؟", {"title": "Overview", "text": "۰ پست زمان‌بندی‌شده"}, [{"role": "user", "text": "سلام"}]))
    assert out["reply"] and out["action"] == {"type": "open_tab", "tab": "content"} and seen["route"] == "hermes_chat" and "زمان‌بندی‌شده" in seen["user"]


def test_chats_are_stored_listed_titled_and_deleted(store, monkeypatch):
    from hermes.services import chats
    rows = {}

    async def get(table, key): return rows.get(key)
    async def save(table, row): rows[row["id"]] = row
    async def listing(table): return list(rows.values())
    async def delete(table, key): rows.pop(key, None)
    for name, fn in (("get_row", get), ("save_row", save), ("list_rows", listing), ("delete_row", delete)):
        monkeypatch.setattr(chats, name, fn)

    async def fake_chat(user_id, message, page, history):
        return {"reply": "جواب", "suggestions": ["بعدی"], "activity": [{"label": "x", "tool": "page"}], "action": None}
    monkeypatch.setattr(chats.agent, "chat", fake_chat)
    created = asyncio.run(chats.create("5"))
    out = asyncio.run(chats.send("5", created["id"], "سلام، یک ایده بده", {"title": "Overview", "text": "x"}))
    assert out["chat"]["title"].startswith("سلام") and out["reply"]["role"] == "assistant"
    again = asyncio.run(chats.get("5", created["id"]))
    assert [m["role"] for m in again["messages"]] == ["user", "assistant"]
    assert len(asyncio.run(chats.list_chats("5"))) == 1 and asyncio.run(chats.list_chats("6")) == []
    with pytest.raises(HTTPException):
        asyncio.run(chats.get("6", created["id"]))
    asyncio.run(chats.remove("5", created["id"]))
    assert asyncio.run(chats.list_chats("5")) == []
