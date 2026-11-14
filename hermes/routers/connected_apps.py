"""Authenticated Composio settings and explicit user-initiated OAuth links."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from hermes.security import current_user
from hermes.services import composio_sessions as service
from hermes.composio_contracts import ConnectInput, DiscoverInput, ReadInput

router = APIRouter(prefix="/api/hermes/composio", tags=["hermes-connected-apps"])


class EnableInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


@router.get("")
async def status(user=Depends(current_user)):
    return await service.status(str(user.id))


@router.put("")
async def configure(body: EnableInput, user=Depends(current_user)):
    return await service.set_enabled(str(user.id), body.enabled)


@router.get("/connections")
async def connections(user=Depends(current_user)):
    return await service.connections(str(user.id))


@router.delete("/connections/{application}")
async def disconnect(application: str, user=Depends(current_user)):
    return await service.disconnect(str(user.id), application.lower())


@router.post("/connect")
async def connect(body: ConnectInput, user=Depends(current_user)):
    return await service.connect(str(user.id), body.application)


@router.post("/discover")
async def discover(body: DiscoverInput, user=Depends(current_user)):
    return await service.discover(str(user.id), body.application, body.query)


@router.post("/read")
async def execute_read(body: ReadInput, user=Depends(current_user)):
    from hermes.services.composio_read import execute
    return await execute(str(user.id), body.application, body.tool, body.arguments)
