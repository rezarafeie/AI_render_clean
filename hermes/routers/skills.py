from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from hermes.security import current_user
from hermes.services import composio_account, skills

router = APIRouter(prefix="/api/hermes/skills", tags=["hermes-skills"])


class RunBody(BaseModel):
    text: str = Field(default="", max_length=20_000)
    language: str = Field(default="fa", pattern=r"^(fa|en)$")
    options: dict = Field(default_factory=dict)


@router.get("")
async def catalog(user=Depends(current_user)):
    return {"skills": skills.catalog()}


@router.get("/account")
async def account(user=Depends(current_user)):
    """The connected account's profile and recent media, read live through Composio (read-only)."""
    row = await composio_account.account(str(user.id))
    if not row:
        return {"connected": False}
    try:
        media = await composio_account.posts(str(user.id))
    except Exception:
        media = []
    return {"connected": True, "profile": row, "recent_posts": media}


@router.post("/{skill}")
async def run(skill: str, body: RunBody, user=Depends(current_user)):
    return await skills.run(str(user.id), skill, body.text, body.language, body.options)
