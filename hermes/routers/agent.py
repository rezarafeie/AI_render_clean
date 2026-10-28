import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from hermes.security import current_user
from hermes.services import agent, skills

router = APIRouter(prefix="/api/hermes/agent", tags=["hermes-agent"])
_running: dict[str, asyncio.Task] = {}


class AnswerBody(BaseModel):
    key: str = Field(min_length=1, max_length=40)
    value: str = Field(max_length=2000)


class RunBody(BaseModel):
    steps: list[str] = Field(default_factory=lambda: list(agent.STEPS))
    count: int = Field(default=4, ge=1, le=8)


class AskBody(BaseModel):
    skill: str
    text: str = Field(default="", max_length=20_000)
    language: str = Field(default="fa", pattern=r"^(fa|en)$")


class StatusBody(BaseModel):
    status: str = Field(pattern=r"^(approved|rejected|in_production|produced|queued)$")
    conversation_id: str | None = Field(default=None, max_length=64)


@router.get("")
async def state(user=Depends(current_user)):
    return agent.public(await agent.load(str(user.id)))


@router.post("/run", status_code=202)
async def run(body: RunBody, user=Depends(current_user)):
    uid = str(user.id)
    task = _running.get(uid)
    if task and not task.done():
        return {"status": "running"}
    steps = tuple(step for step in body.steps if step in agent.STEPS) or agent.STEPS
    _running[uid] = asyncio.create_task(agent.run(uid, steps, body.count))
    return {"status": "started"}


@router.post("/answer")
async def answer(body: AnswerBody, user=Depends(current_user)):
    return agent.public(await agent.answer(str(user.id), body.key, body.value))


@router.post("/proposals/{proposal_id}")
async def proposal(proposal_id: str, body: StatusBody, user=Depends(current_user)):
    extra = {"conversation_id": body.conversation_id} if body.conversation_id else {}
    return await agent.set_status(str(user.id), proposal_id, body.status, **extra)


@router.post("/ask")
async def ask(body: AskBody, user=Depends(current_user)):
    """One of the 13 skills on demand, inside the agent (not a separate tool): the answer is added to the agent's notes."""
    if body.skill not in skills.SKILLS:
        raise HTTPException(404, detail={"code": "SKILL_NOT_FOUND"})
    return await skills.run(str(user.id), body.skill, body.text, body.language, {})
