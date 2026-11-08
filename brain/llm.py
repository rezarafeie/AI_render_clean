"""Existing editor intelligence contract: every model call goes through the AI router (the gateway's routes, with the gateway's own direct fallbacks).

Two top-level functions:
  chat_json()    → text/JSON plan generation   (the route's models)
  chat_vision()  → image + text content analysis  (the route's vision-capable models)

With no router configured nothing is sent: there is no other transport here.
"""
from __future__ import annotations

import base64
import json
import logging
import math
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from app.config import settings

log = logging.getLogger(__name__)

_DEFAULT_PROVIDER_TIMEOUT_SECONDS = 300.0
_MAX_PROVIDER_TIMEOUT_SECONDS = 600.0


def _provider_timeout_seconds(override: float | None = None) -> float:
    """Bound hosted model calls so a background job cannot wait indefinitely."""
    try:
        configured_timeout = float(settings.AI_PROVIDER_TIMEOUT_SECONDS)
    except (TypeError, ValueError):
        configured_timeout = _DEFAULT_PROVIDER_TIMEOUT_SECONDS
    if not math.isfinite(configured_timeout) or configured_timeout <= 0:
        configured_timeout = _DEFAULT_PROVIDER_TIMEOUT_SECONDS
    fallback = min(configured_timeout, _MAX_PROVIDER_TIMEOUT_SECONDS)
    if override is None:
        return fallback
    try:
        timeout = float(override)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(timeout) or timeout <= 0:
        return fallback
    return min(timeout, _MAX_PROVIDER_TIMEOUT_SECONDS)

# Pricing per 1M tokens (input, output) — approximate
_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-sonnet-5": (2.00, 10.00),
    "anthropic/claude-sonnet-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-5-5-image": (5.00, 20.00),
    "DEEPSEEK_V4_FLASH": (0.10, 0.30),
}


@dataclass
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    elapsed_sec: float = 0.0

    @property
    def cost_estimate(self) -> float:
        inp_price, out_price = _PRICING.get(self.model, (3.0, 15.0))
        return (self.input_tokens * inp_price + self.output_tokens * out_price) / 1_000_000


# ── env helpers ──────────────────────────────────────────────────────────────

def _getenv_ci(name: str) -> str | None:
    """Case-insensitive env var lookup."""
    value = getattr(settings, name, None)
    return value if isinstance(value, str) and value else None


def provider_configured() -> bool:
    from .lm_gateway import configured
    return configured()


# ── plan/text model ───────────────────────────────────────────────────────────

def chat_json(
    system: str,
    user: str,
    *,
    model: Optional[str] = None,
    max_tokens: int = 16000,
    temperature: float = 0.0,
    timeout_seconds: Optional[float] = None,
    provider: Optional[str] = None,
    route: Optional[str] = None,
) -> tuple[dict, LLMUsage]:
    """Send a single-turn request expecting a JSON response.

    Uses LLM_PROVIDER + LLM_MODEL (default: CLAUDE_SONNET_5_5).
    Returns (parsed_json, usage).
    """
    from .lm_gateway import route_context
    _require_router()
    return gateway_json(system, user, route or route_context.get() or "editing_agent", max_tokens)


def gateway_json(system, user, route="editing_agent", max_tokens=16000):
    from .lm_gateway import complete
    from .lm_adapters import text, PATHS
    system = system + "\nReturn exactly one valid JSON object. Do not include markdown fences, commentary, or additional JSON documents."
    result, record = complete(route, [{"role":"system","content":system}, {"role":"user","content":user}], tokens=max_tokens,
                              validate_response=_extract_json)
    endpoint = next(key for key,value in PATHS.items() if value == record["endpoint"])
    return _extract_json(text(endpoint, result)), LLMUsage(
        input_tokens=record.get("input_tokens") or 0, output_tokens=record.get("output_tokens") or 0,
        model=record.get("actual_model") or record["requested_model"], elapsed_sec=record["latency_ms"]/1000)


def _cooldown_hint(exc: Exception) -> int | None:
    """The gateway states how long a rate-limited route needs ("Soonest reset ~38s"); use it when present."""
    import re
    match = re.search(r"reset(?:s)? (?:in )?~?(\d+)\s*s", str(exc), re.I)
    return int(match.group(1)) + 2 if match else None


def gateway_json_resilient(system, user, route="editing_agent", max_tokens=16000, attempts=4, _sleep=None):
    """gateway_json with bounded waits for transient provider failures (429/5xx/timeouts).

    Real jobs died at "editing text" on a single 502/ReadTimeout. The gateway already falls through its model
    list inside one call; this adds time-based retries on top, because provider capacity is bursty.
    """
    import time
    from .lm_gateway import GatewayError
    sleep = _sleep or time.sleep
    delay = 4
    for attempt in range(attempts):
        try:
            return gateway_json(system, user, route, max_tokens)
        except GatewayError as exc:
            if not exc.retryable or attempt == attempts - 1:
                raise
            wait = min(_cooldown_hint(exc) or delay, 60)
            log.warning("LM route %s transient failure (%s); retry %d/%d in %ss", route, exc.status, attempt + 1, attempts - 1, wait)
            sleep(wait)
            delay = min(delay * 2, 30)


# ── vision / content-analysis model ──────────────────────────────────────────

def chat_vision(
    system: str,
    user: str,
    *,
    images: Optional[list[Union[str, Path, bytes]]] = None,
    model: Optional[str] = None,
    max_tokens: int = 4096,
    temperature: float = 0.3,
    return_json: bool = False,
    timeout_seconds: Optional[float] = None,
    route: str = "video_understanding",
) -> tuple[str | dict, LLMUsage]:
    """Image-capable call for content generation, editing, and engagement hints.

    Goes through the AI router (the route's vision-capable models).

    images: list of file paths (str/Path), URLs (str starting with http), or raw bytes.
    return_json: if True, parse the response as JSON and return a dict.
    Returns (text_or_dict, usage).
    """
    from .lm_gateway import complete
    from .lm_adapters import text
    _require_router()
    content = []
    for img in images or []:
        if isinstance(img, str) and img.startswith("https://"):
            url = img
        else:
            b64, media_type = _encode_image(img)
            url = f"data:{media_type};base64,{b64}"
        content.append({"type":"image_url","image_url":{"url":url}})
    content.append({"type":"text","text":user})
    data, record = complete(route, [{"role":"system","content":system},
        {"role":"user","content":content}], required={"chat","vision"}, tokens=max_tokens,
        validate_response=_extract_json if return_json else None)
    value = text("chat", data)
    usage = LLMUsage(input_tokens=record.get("input_tokens") or 0, output_tokens=record.get("output_tokens") or 0,
        model=record.get("actual_model") or record["requested_model"], elapsed_sec=record["latency_ms"]/1000)
    return (_extract_json(value) if return_json else value), usage


def _require_router() -> None:
    """Every model call goes through the AI router (gateway routes, with its own direct fallbacks): with no router configured nothing is sent."""
    from .lm_gateway import configured
    if not configured():
        raise RuntimeError("The AI router is not configured; no model request was sent")


# ── shared helpers ─────────────────────────────────────────────────────────

def _encode_image(img: Union[str, Path, bytes]) -> tuple[str, str]:
    """Return (base64_str, media_type) from a file path or raw bytes."""
    if isinstance(img, bytes):
        raw = img
        media_type = "image/jpeg"
    else:
        p = Path(img)
        raw = p.read_bytes()
        ext = p.suffix.lower()
        media_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }.get(ext, "image/jpeg")
    return base64.b64encode(raw).decode(), media_type


def _log_usage(usage: LLMUsage, *, preset: str = "",
               provider: str = "", base_url: str = "",
               call_type: str = "text") -> None:
    tag = f" ({preset})" if preset else ""
    url_tag = f" base_url={base_url}" if base_url else ""
    print(
        f"[LLM {call_type}] model={usage.model} provider={provider or 'default'}"
        f"{url_tag}{tag}: {usage.input_tokens} in / {usage.output_tokens} out, "
        f"~${usage.cost_estimate:.4f}, {usage.elapsed_sec:.1f}s"
    )
    log.info(
        "LLM %s%s: %d in / %d out tokens, ~$%.4f, %.1fs",
        usage.model, tag,
        usage.input_tokens, usage.output_tokens,
        usage.cost_estimate, usage.elapsed_sec,
    )


def _extract_json(text: str) -> dict:
    """Accept one structured document, including a fenced document plus prose.

    Never silently choose between two documents or repair invalid JSON values.
    Downstream task schemas still validate the returned structure.
    """
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as original:
        import re
        fences = list(re.finditer(r'```(?:json)?\s*\n(.*?)```', text, re.DOTALL | re.IGNORECASE))
        if len(fences) == 1:
            match = fences[0]
            surrounding = text[:match.start()] + text[match.end():]
            if any(char in surrounding for char in '{['):
                raise ValueError('پاسخ مدل شامل چند ساختار یا بخش مبهم است؛ برنامه اجرا نشد.') from original
            return json.loads(match.group(1).strip())
        raise ValueError('پاسخ ساختاریافتهٔ مدل معتبر نیست؛ برنامه اجرا نشد و نیاز به بررسی دارد.') from original
