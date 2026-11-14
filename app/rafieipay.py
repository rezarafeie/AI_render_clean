"""Rafiei Pay (pay.rafiei.co) client: Mode A, the signed aggregator API. Used by the credit purchase flow (app/credits.py).

Every request is signed HMAC-SHA256 over f"{timestamp}.{raw body}" (empty body for GET). The API key and secret are never in the code or the logs:
they come from RAFIEIPAY_API_KEY / RAFIEIPAY_API_SECRET, or from the root-only file <JOBS_DIR>/rafieipay.json ({"api_key": ..., "api_secret": ..., "base_url": ...}).
Only a server-to-server `payments-get` proves a payment: callback query strings and webhook bodies are used as hints and never trusted.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from pathlib import Path

import httpx

from app.config import settings

log = logging.getLogger(__name__)
DEFAULT_BASE = "https://pay.rafiei.co"


class PayError(RuntimeError):
    pass


def config() -> dict | None:
    key, secret, base = os.environ.get("RAFIEIPAY_API_KEY", ""), os.environ.get("RAFIEIPAY_API_SECRET", ""), os.environ.get("RAFIEIPAY_BASE_URL", "")
    if not (key and secret):
        try:
            saved = json.loads((Path(settings.JOBS_DIR) / "rafieipay.json").read_text())
            key, secret, base = saved.get("api_key", ""), saved.get("api_secret", ""), saved.get("base_url", "") or base
        except (OSError, ValueError):
            return None
    if not (key and secret):
        return None
    return {"api_key": key.strip(), "api_secret": secret.strip(), "base_url": (base or DEFAULT_BASE).rstrip("/")}


def enabled() -> bool:
    return config() is not None


def sign(secret: str, timestamp: str, raw: str) -> str:
    return hmac.new(secret.encode(), f"{timestamp}.{raw}".encode(), hashlib.sha256).hexdigest()


def _headers(cfg: dict, raw: str, post: bool) -> dict:
    ts = str(int(time.time()))
    headers = {"Accept": "application/json", "X-API-Key": cfg["api_key"], "X-Timestamp": ts, "X-Signature": sign(cfg["api_secret"], ts, raw)}
    if post:
        headers["Content-Type"] = "application/json"
    return headers


async def _call(method: str, path: str, *, body: dict | None = None, query: dict | None = None) -> dict:
    cfg = config()
    if cfg is None:
        raise PayError("rafieipay is not configured")
    raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False) if body is not None else ""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(25, connect=10)) as client:
            response = await client.request(method, cfg["base_url"] + path, params=query, headers=_headers(cfg, raw, body is not None),
                                            content=raw.encode() if body is not None else None)
    except httpx.HTTPError as exc:
        raise PayError(f"rafieipay unreachable: {type(exc).__name__}") from exc
    try:
        data = response.json()
    except ValueError:
        raise PayError(f"rafieipay answered HTTP {response.status_code} without JSON")
    if response.status_code >= 400 or (isinstance(data, dict) and data.get("success") is False):
        raise PayError(f"rafieipay refused (HTTP {response.status_code}): {str((data or {}).get('error') or (data or {}).get('message') or '')[:160]}")
    return data


async def request_payment(*, amount_toman: int, order_id: str, description: str, callback_url: str, gateway: str | None = None, metadata: dict | None = None) -> dict:
    """Start a payment. Returns {"payment_id", "url", ...}; send the person's browser to `url`."""
    body = {"amount_toman": int(amount_toman), "order_id": order_id, "description": description, "callback_url": callback_url}
    if gateway: body["gateway"] = gateway
    if metadata: body["metadata"] = metadata
    data = await _call("POST", "/functions/v1/payments-request", body=body)
    url = data.get("checkout_url") or data.get("payment_url")
    if not data.get("payment_id") or not url:
        raise PayError("rafieipay answered without a payment id / url")
    return {"payment_id": str(data["payment_id"]), "url": url, "payment_url": data.get("payment_url"), "checkout_url": data.get("checkout_url")}


async def get_payment(payment_id: str) -> dict:
    """The authoritative record: {"status": "verified"|..., "amount_toman": int, "ref_id": ...}."""
    data = await _call("GET", "/functions/v1/payments-get", query={"id": payment_id})
    body = data.get("body") if isinstance(data.get("body"), dict) else data
    return body.get("payment") if isinstance(body.get("payment"), dict) else body
