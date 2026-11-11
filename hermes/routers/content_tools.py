"""Read-only Instagram checks shared by authenticated Hermes clients and Studio."""
import asyncio
import subprocess
import threading

from fastapi import APIRouter, Depends, HTTPException

from app.studio_tools import InstagramContentCheckInput, ResourceSearchInput, SkillReadInput, execute
from hermes.security import current_user

router = APIRouter(prefix="/api/hermes/content-tools", tags=["hermes-content-tools"])
_capacity = threading.BoundedSemaphore(2)


def _execute(payload):
    if not _capacity.acquire(blocking=False):
        raise HTTPException(429, detail={"code": "INSTAGRAM_CHECK_BUSY"}, headers={"Retry-After": "1"})
    try:
        return execute("instagram_content_check", payload)
    finally:
        _capacity.release()


@router.post("/check")
async def check(body: InstagramContentCheckInput, user=Depends(current_user)):
    try:
        return await asyncio.to_thread(_execute, body.model_dump())
    except ValueError:
        raise HTTPException(422, detail={"code": "INSTAGRAM_CHECK_UNSUPPORTED_INPUT"}) from None
    except subprocess.TimeoutExpired:
        raise HTTPException(504, detail={"code": "INSTAGRAM_CHECK_TIMEOUT"}) from None
    except RuntimeError:
        raise HTTPException(502, detail={"code": "INSTAGRAM_CHECK_FAILED"}) from None


@router.post("/skills/search")
async def search_skills(body: ResourceSearchInput, user=Depends(current_user)):
    """The craft-skill catalogue (short-form, storytelling, data-visualization, sound-design, product video, motion…): read-only, no execution."""
    payload = body.model_dump()
    payload["engine"] = "skill"
    return await asyncio.to_thread(execute, "search_creative_resources", payload)


@router.post("/skills/read")
async def read_skill(body: SkillReadInput, user=Depends(current_user)):
    result = await asyncio.to_thread(execute, "read_creative_skill", body.model_dump())
    if result.get("error"):
        raise HTTPException(404, detail={"code": "SKILL_NOT_FOUND"})
    return result
