"""Validated JSON calls through the existing LM gateway.

Creative work uses its own routes (``creative_director`` / ``creative_critic`` / ``creative_revision``,
registered in ``brain/lm_tasks.py``) so it is routed by the operator's policy for strong models instead
of the unpinned ``auto`` route that most editor calls fall into.
"""
from __future__ import annotations

import contextvars
import json
import logging
import re
import time
from typing import Callable, TypeVar

from pydantic import BaseModel, ValidationError

from .schemas import CreativeUnavailable

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

DIRECTOR_ROUTE = "creative_director"
CRITIC_ROUTE = "creative_critic"
REVISION_ROUTE = "creative_revision"


_sleep = time.sleep  # indirection so tests do not really wait
_RESET = re.compile(r"reset(?:s)? (?:in )?~?(\d+)\s*s", re.I)
MAX_COOLDOWN_WAIT_S = 60

# Set by the studio for the message being processed: it raises the studio's own "stopped" exception once the person pressed Stop.
# A model call cannot be interrupted, but no further attempt, retry or cooldown wait is started after that.
STOP_CHECK: contextvars.ContextVar[Callable[[], None] | None] = contextvars.ContextVar("creative_stop_check", default=None)


def _stop_point() -> None:
    check = STOP_CHECK.get()
    if check is not None:
        check()


def _transient_network(exc: Exception) -> bool:
    # The gateway wraps a dropped connection as a retryable GatewayError. A *timeout* is not retried: it would only repeat the wait.
    if getattr(exc, "retryable", False) and cooldown_seconds(exc) is None and \
            any(word in str(exc) for word in ("ConnectError", "RemoteProtocolError", "disconnected")):
        return True
    try:
        import httpx
    except ImportError:
        return False
    return isinstance(exc, (httpx.RemoteProtocolError, httpx.ReadError, httpx.ReadTimeout, httpx.ConnectError, httpx.ConnectTimeout,
                            httpx.WriteError, httpx.PoolTimeout))


def cooldown_seconds(exc: Exception) -> int | None:
    """Seconds the gateway says a rate-limited/busy route needs, when the error states it (429/503 only)."""
    status = getattr(exc, "status", None)
    if status not in {429, 503}:
        return None
    match = _RESET.search(str(exc))
    if match:
        return min(int(match.group(1)) + 2, MAX_COOLDOWN_WAIT_S)
    return 8 if status == 429 else None


def configured() -> bool:
    try:
        from brain.lm_gateway import configured as gateway_configured
        return bool(gateway_configured())
    except Exception:
        return False


def ask(schema: type[T], system: str, user: str, *, route: str, tokens: int = 6000, attempts: int = 3,
        used: list[str] | None = None) -> T:
    from app.studio_activity import describe
    stages = {
        'ContentBrief': ('creative_brief', 'دارم هدف، مخاطب، لحن و پیام اصلی ویدیو را استخراج می‌کنم.'),
        '_Concepts': ('creative_concepts', 'دارم چند ایدهٔ متفاوت برای هوک، روایت و زبان بصری می‌سازم.'),
        'Critique': ('creative_review', 'دارم ایده‌ها را مقایسه و نقاط ضعف روایت و جذابیت بصری را بررسی می‌کنم.'),
        '_Expansion': ('creative_storyboard', 'دارم ایدهٔ منتخب را به صحنه‌ها، ریتم و پیشنهادهای موشن تبدیل می‌کنم.'),
        'ScriptDraft': ('creative_script', 'دارم متن گفتاری فارسی را می‌نویسم و برای هر جمله تصویرش را مشخص می‌کنم.'),
        'ScriptReview': ('creative_script_review', 'منتقد مستقل سناریو را می‌خواند و برای هر معیار از خود متن شاهد می‌آورد.'),
    }
    stage, message = stages.get(schema.__name__, (route, 'در حال آماده‌سازی برنامهٔ اجرایی این بخش هستم.'))
    with describe(stage, message):
        return _ask(schema, system, user, route=route, tokens=tokens, attempts=attempts, used=used)


def _ask(schema: type[T], system: str, user: str, *, route: str, tokens: int = 6000, attempts: int = 3,
        used: list[str] | None = None) -> T:
    """Call a route and validate against ``schema``; re-ask once with the validation error if needed."""
    if not configured():
        raise CreativeUnavailable("LM gateway is not configured")
    from brain.llm import gateway_json
    prompt = user
    last = "no response"
    budget = tokens
    for attempt in range(attempts):
        _stop_point()
        try:
            data, usage = gateway_json(system, prompt, route, budget)
        except json.JSONDecodeError as exc:
            # Truncated or malformed JSON: reasoning models spend part of the output budget thinking.
            # Retry once with a larger budget and an explicit request for a compact answer.
            last = f"unparseable JSON ({exc.msg})"
            log.warning("creative %s returned unparseable JSON (attempt %d): %s", route, attempt + 1, exc.msg)
            budget = min(int(budget * 1.8), 16000)
            prompt = user + "\n\nYour previous reply was cut off or malformed. Return one COMPLETE, more compact JSON object only."
            continue
        except Exception as exc:  # timeouts, 429/503 bursts, disabled routes: never fatal for the job
            if _transient_network(exc) and attempt < attempts - 1:
                # A connection the proxy dropped mid-answer (long generations) says nothing about the request: ask again.
                log.warning("creative %s connection dropped (%s); retrying", route, type(exc).__name__)
                last = f"connection dropped ({type(exc).__name__})"
                _stop_point()
                _sleep(3)
                continue
            wait = cooldown_seconds(exc)
            if wait is not None and attempt < attempts - 1:
                # Thin provider capacity: a short cooldown is worth waiting out once, a long one is not.
                log.warning("creative %s rate-limited; waiting %ss", route, wait)
                last = f"rate limited ({wait}s)"
                _stop_point()
                _sleep(wait)
                continue
            raise CreativeUnavailable(f"{route}: {type(exc).__name__}: {str(exc)[:160]}") from exc
        if used is not None and usage.model not in used:
            used.append(usage.model)
        try:
            clean = getattr(schema, "clean_llm_data", None)
            return schema.model_validate(clean(data) if clean else data)
        except ValidationError as exc:
            problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:5])
            last = problems
            log.warning("creative %s invalid JSON (attempt %d): %s", route, attempt + 1, problems)
            prompt = (user + "\n\nYour previous JSON failed validation (" + problems +
                      "). Return the complete corrected JSON object only.")
    raise CreativeUnavailable(f"{route}: response did not validate ({last})")


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=1)
