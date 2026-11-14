"""Public endpoints for Rafiei Pay: the webhook (POST /webhook/rafieipay) and the browser return (GET /webhook/rafieipay/return).
Neither is trusted: both only name an order; the credits are added after a server-to-server check with Rafiei Pay (credits.settle_order)."""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app import credits

log = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook/rafieipay", tags=["rafieipay"])
_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def _ids(body) -> list[str]:
    found = []
    sources = [body] + ([body["payment"]] if isinstance(body, dict) and isinstance(body.get("payment"), dict) else [])
    for source in sources:
        if isinstance(source, dict):
            for key in ("order_id", "payment_id", "id"):
                value = source.get(key)
                if isinstance(value, str) and _ID.match(value) and value not in found:
                    found.append(value)
    return found


@router.post("")
async def webhook(request: Request):
    try:
        body = await request.json()
    except ValueError:
        body = {}
    for ident in _ids(body):
        order_id = await credits.order_id_for(ident)
        if order_id:
            try:
                await credits.settle_order(order_id)
            except Exception:
                log.exception("settling order %s from the webhook failed", order_id)
            break
    return JSONResponse({"ok": True})


@router.get("/return")
async def back_from_gateway(order_id: str = ""):
    state = "unknown"
    if _ID.match(order_id or ""):
        try:
            order = await credits.settle_order(order_id)
            state = "ok" if order["status"] == "paid" else "pending"
        except KeyError:
            state = "unknown"
        except Exception:
            log.exception("settling order %s on return failed", order_id)
            state = "pending"
    return RedirectResponse(f"/credits?pay={state}&order={order_id if _ID.match(order_id or '') else ''}", status_code=303)
