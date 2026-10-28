import asyncio

import pytest
from fastapi import HTTPException

from hermes.services import skills


def test_all_thirteen_skills_have_a_definition_and_a_group():
    assert len(skills.SKILLS) == 13
    for key, folder in skills.FOLDER.items():
        assert (skills.SKILL_DIR / folder / "SKILL.md").is_file(), key
        assert skills.SKILLS[key]["group"] in {"understand", "plan", "create", "engage", "quality"}


def test_a_skill_runs_with_the_account_and_checks_what_it_wrote(monkeypatch):
    seen = {}

    def fake_chat(system, user, **kwargs):
        seen["system"], seen["user"] = system, user
        return {"title": "ریلز", "hooks": ["چرا فروش نمی‌کنی؟"], "script": "سلام. امروز می‌گویم چرا فروش نمی‌کنی.", "caption": "کپشن کوتاه"}, None

    async def fake_account(user_id):
        return {"username": "someone", "followers": 10, "follows": 2, "media_count": 3}

    async def fake_posts(user_id):
        return [{"id": "1", "caption": "x", "likes": 5, "comments": 1}]
    monkeypatch.setattr(skills, "chat_json", fake_chat)
    monkeypatch.setattr(skills.composio_account, "account", fake_account)
    monkeypatch.setattr(skills.composio_account, "posts", fake_posts)
    out = asyncio.run(skills.run("1", "reel", "ایده: فروش محصول دیجیتال", "fa"))
    assert out["account_used"] and out["can_produce"] and "hooks" in out["checks"]
    assert "someone" in seen["user"] and "ig-reel" not in seen["user"] and len(seen["system"]) > 500


def test_unknown_skill_and_empty_request_without_account(monkeypatch):
    async def none(user_id):
        return None
    monkeypatch.setattr(skills.composio_account, "account", none)
    with pytest.raises(HTTPException) as bad:
        asyncio.run(skills.run("1", "nope", "x"))
    assert bad.value.status_code == 404
    with pytest.raises(HTTPException) as empty:
        asyncio.run(skills.run("1", "audit", ""))
    assert empty.value.status_code == 422
