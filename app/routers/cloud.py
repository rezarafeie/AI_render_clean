"""Cloud media storage API. Identity always comes from the authenticated request, never from the body."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app import cloud_storage as cloud

router = APIRouter(prefix="/studio/cloud", tags=["cloud-storage"])


def _user(request: Request) -> str:
    return str(request.state.user.id)


async def _guard(call):
    try:
        return await call
    except cloud.CloudError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code, "message": exc.message}) from None


class ImportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversation_id: str = Field(min_length=1, max_length=64)
    file_ids: list[str] = Field(min_length=1, max_length=20)


@router.get("/providers")
async def providers(request: Request):
    from fastapi import HTTPException as HE
    from hermes.services.composio_sessions import allowed_toolkits, connections
    enabled = set(allowed_toolkits())
    connected: dict[str, dict] = {}
    try:
        for item in (await connections(_user(request)))["applications"]:
            connected[item["application"]] = item
    except HE:
        pass   # not configured / disabled: providers show as not connected
    return {"providers": [{"id": key, "name": value["name"], "enabled": value["toolkit"] in enabled,
                           "connected": bool(connected.get(value["toolkit"], {}).get("connected")),
                           "status": connected.get(value["toolkit"], {}).get("status", "NOT_CONNECTED"),
                           "capabilities": value["capabilities"]} for key, value in cloud.PROVIDERS.items()]}


@router.get("/{provider}/files")
async def files(request: Request, provider: str, folder: str = Query("root", max_length=200),
                q: str = Query("", max_length=200), media: str = Query("", max_length=10),
                page_token: str | None = Query(None, max_length=2000), page_size: int = Query(50, ge=1, le=100),
                sort: str = Query("name", max_length=10)):
    return await _guard(cloud.list_files(_user(request), provider, folder, q, media, page_token, page_size, sort))


@router.get("/{provider}/files/{file_id}")
async def file_metadata(request: Request, provider: str, file_id: str):
    return await _guard(cloud.metadata(_user(request), provider, file_id))


@router.post("/{provider}/import", status_code=202)
async def start_import(request: Request, provider: str, body: ImportBody):
    user = _user(request)
    results, errors = [], []
    for file_id in dict.fromkeys(body.file_ids):
        try:
            results.append(await cloud.begin_import(user, body.conversation_id, provider, file_id))
        except cloud.CloudError as exc:
            errors.append({"file_id": file_id, "code": exc.code, "message": exc.message})
    if not results and errors:
        first = errors[0]
        raise HTTPException(422, detail={"code": first["code"], "message": first["message"], "errors": errors})
    return {"transfers": results, "errors": errors}


@router.get("/transfers")
async def transfers(request: Request, conversation_id: str = Query(..., max_length=64)):
    return {"transfers": [cloud.public(r) for r in cloud.list_transfers(_user(request), conversation_id)]}


@router.get("/transfers/{transfer_id}")
async def transfer(request: Request, transfer_id: str, conversation_id: str = Query(..., max_length=64)):
    return await _guard(_sync(lambda: cloud.public(cloud.get_transfer(_user(request), conversation_id, transfer_id))))


@router.post("/transfers/{transfer_id}/cancel")
async def cancel(request: Request, transfer_id: str, conversation_id: str = Query(..., max_length=64)):
    return await _guard(_sync(lambda: cloud.cancel(_user(request), conversation_id, transfer_id)))


@router.post("/transfers/{transfer_id}/retry", status_code=202)
async def retry(request: Request, transfer_id: str, conversation_id: str = Query(..., max_length=64)):
    return await _guard(_sync(lambda: cloud.retry(_user(request), conversation_id, transfer_id)))


async def _sync(fn):
    return fn()
