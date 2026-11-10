"""Additive authenticated resource discovery. No download or code execution API."""
from fastapi import APIRouter, HTTPException, Query, Response
from creative.resources.registry import get_resource, registry_summary, search_resources

router = APIRouter(prefix="/creative-resources", tags=["creative-resources"])


@router.get("")
def search(response: Response, q: str = Query("", max_length=300), engine: str | None = None,
           provider: str | None = None, kind: str | None = None, availability: str | None = None,
           limit: int = Query(24, ge=1, le=100), offset: int = Query(0, ge=0, le=10000)):
    response.headers["Cache-Control"] = "no-store"
    return search_resources(q, engine=engine, provider=provider, kind=kind,
                            availability=availability, limit=limit, offset=offset)


@router.get("/summary")
def summary(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return registry_summary()


@router.get("/{resource_id}/content")
def content(resource_id: str, response: Response, reference: str = Query("", max_length=80), max_chars: int = Query(8000, ge=500, le=20000)):
    """The text of a vendored craft skill (or one of its listed references). Read-only; ids are looked up in the index, never used as paths."""
    from creative import skills_library
    response.headers["Cache-Control"] = "no-store"
    row = skills_library.get(resource_id)
    if row is None:
        raise HTTPException(404, "Creative skill not found")
    text = skills_library.reference(resource_id, reference, max_chars) if reference else skills_library.body(resource_id, max_chars)
    return {"id": row["id"], "source": row["repo"], "revision": row["revision"], "license": "MIT", "references": row["references"], "text": text}


@router.get("/{resource_id}")
def detail(resource_id: str, response: Response):
    response.headers["Cache-Control"] = "no-store"
    try:
        return get_resource(resource_id)
    except KeyError:
        raise HTTPException(404, "Creative resource not found") from None
