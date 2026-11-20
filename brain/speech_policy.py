"""Language-aware casting. Metadata is evidence, not a claim of subjective quality.

No synthesis, retries or provider fallbacks happen here. Unsupported voices fail
before a billable request. Gateway routes still own execution and permissions.
"""
from __future__ import annotations

import os
import json
import hashlib
import re
import threading
import time

_cache: tuple[str, float, list[dict]] = ("", 0, [])
_lock = threading.Lock()
FA = {"fa", "fas", "per", "persian", "farsi", "fa-ir", "iranian persian"}


def persian(text: str = "", language: str = "") -> bool:
    if language:
        return language.strip().lower().replace("_", "-") in FA
    # Arabic script alone is not evidence of Persian. Persian-specific letters
    # or common Persian function words provide a conservative text fallback.
    return bool(re.search(r"[پچژگکی]|(?:^|\s)(?:این|برای|است|را|می)(?:\s|‌|$)", text))


def languages(row: dict) -> set[str]:
    values = row.get("languages", row.get("supported_languages", [])) or []
    if isinstance(values, str):
        values = [values]
    result = {str(v.get("language_id", v.get("language", "")) if isinstance(v, dict) else v).lower().replace("_", "-") for v in values}
    labels = row.get("labels") or {}
    result.add(str(labels.get("language", row.get("language", ""))).lower())
    result.update(str(v.get("language", "")).lower() for v in row.get("verified_languages", []) if isinstance(v, dict))
    return result


_FEMALE_ASKED = re.compile(r"(?:صدای|صدا|گوینده|راوی|نریشن|نریشین|voice|narrator)\s*(?:ی|ای)?\s*[:：-]?\s*(?:با\s+)?(?:یک\s+|یه\s+)?(?:صدای\s+)?(?:خانم|زن|زنانه|female|woman)")
_MALE_ASKED = re.compile(r"(?:صدای|صدا|گوینده|راوی|نریشن|نریشین|voice|narrator)\s*(?:ی|ای)?\s*[:：-]?\s*(?:با\s+)?(?:یک\s+|یه\s+)?(?:صدای\s+)?(?:آقا|مرد|مردانه|male|man)(?!\w)")


def explicit_gender(text: str) -> str:
    """'female' / 'male' when the request names the narrator's gender outright («با صدای خانم», «گوینده مرد», 'female voice'), else ''."""
    text = str(text or "").casefold()
    female = bool(_FEMALE_ASKED.search(text) or re.search(r"\b(?:female|woman'?s?|feminine)\s+(?:voice|narrator|narration|speaker)", text))
    male = bool(_MALE_ASKED.search(text) or re.search(r"\b(?:male|man'?s?|masculine)\s+(?:voice|narrator|narration|speaker)", text))
    return "female" if female and not male else "male" if male and not female else ""


def choose_voice(voices: list[dict], context: str = "", preferred: str = "") -> str:
    """Rank native Persian voices by explicit use-case metadata; never by name."""
    eligible = [v for v in voices if languages(v) & FA and (v.get("voice_id") or v.get("id"))
                and v.get("available", True) and v.get("enabled", True)]
    if not eligible:
        raise ValueError("هیچ صدای فارسیِ تأییدشده‌ای موجود نیست؛ یک گویندهٔ فارسی در تنظیمات صدا ثبت کنید.")
    context = context.casefold()
    raw_context = context                                  # the brief's own words (the tags added below must not decide the gender)
    for pattern, tags in ((r"product|commercial|تبلیغ|محصول|فروش", " advertisement commercial energetic"),
                          (r"explain|localiz|document|آموزش|توضیح|مستند", " narration educational informative calm"),
                          (r"female|زن|خانم", " female"), (r"male|مرد|آقا", " male")):
        if re.search(pattern, context):
            context += tags
    female_cues = ("female", "woman", "زن", "خانم", "بانو", "آرایش", "زیبایی", "پوست", "نوزاد", "بانوان", "مد ", "عطر")
    male_cues = ("مرد", "آقا", "صنعتی", "ابزار", "موتور", "خودرو", "فرز", "دریل", "مکانیک", "ماشین", "کارگاه")
    # A product of a workshop is not sold in a woman's voice by default: the narrator is male unless the brief says female or is plainly a woman's product.
    wanted_gender = "female" if (any(c in raw_context for c in female_cues) and not any(c in raw_context for c in male_cues)) else "male"
    # The person asked for a gender in so many words («با صدای خانم»): that beats the studio's preferred voice, which would otherwise outrank any gender match.
    asked = explicit_gender(raw_context)
    if asked:
        wanted_gender = asked
        preferred_gender = next((str((v.get("labels") or {}).get("gender", "")).lower() for v in eligible if (v.get("voice_id") or v.get("id")) == preferred), "")
        if preferred_gender and preferred_gender != asked:
            preferred = ""

    def score(v):
        labels = v.get("labels") or {}
        tags = " ".join(str(labels.get(k, "")) for k in ("use_case", "description", "accent", "gender")).casefold()
        # A user's explicit, language-compatible choice wins. Otherwise match
        # the creative brief without guessing the speaker's gender from a name.
        tokens = set(re.findall(r"\w+", context))
        return (int((v.get("voice_id") or v.get("id")) == preferred),
                int(str(labels.get("gender", "")).lower() == wanted_gender),
                sum(token in tags for token in tokens if len(token) > 2),
                int(any(str(x.get("language", "")).lower() in FA for x in v.get("verified_languages", []) if isinstance(x, dict))))
    selected = max(eligible, key=score)
    return str(selected.get("voice_id") or selected["id"])


def eleven_voices() -> list[dict]:
    """Read-only voice discovery via the existing mandatory relay, cached 5 min."""
    global _cache
    # An operator-reviewed catalog can be used when the relay does not expose
    # voice discovery. It contains public IDs/metadata only, never credentials.
    from app import lm_store
    configured = lm_store.records("settings").get("speech_casting", {}).get("voices", [])
    native = [v for v in configured if v.get("provider") == "elevenlabs"]
    if native:
        return native
    with _lock:
        import httpx
        from .elevenlabs_transport import url
        key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
        if not key:
            raise ValueError("برای کشف گویندهٔ فارسی، کلید و پراکسی ElevenLabs را تنظیم کنید.")
        endpoint = url("v1/voices")
        scope = hashlib.sha256(f"{endpoint}|{key}".encode()).hexdigest()
        if scope == _cache[0] and time.monotonic() < _cache[1]:
            return _cache[2]
        response = httpx.get(endpoint, headers={"xi-api-key": key}, timeout=20)
        if response.status_code == 404:
            raise ValueError("پراکسی فهرست صداها را ارائه نمی‌کند؛ کاتالوگ گویندگان فارسی را در تنظیمات AI ثبت کنید.")
        response.raise_for_status()
        voices = response.json().get("voices", [])
        if not isinstance(voices, list):
            raise ValueError("Invalid ElevenLabs voice catalog")
        _cache = (scope, time.monotonic() + 300, voices)
        return voices


def eleven_cast(text: str, voice: str = "", model: str = "", *, language: str = "", context: str = "") -> tuple[str, str]:
    if not persian(text, language):
        return voice, model
    # v2/Flash/Turbo do not support Persian. v3 and v4 read Persian and the delivery tags (v4 verified 2026-11-21); a voice that refuses v4 gets v3.
    from .localize import model_for
    model = model_for(voice, "eleven_v4")
    preferred = os.environ.get("PERSIAN_ELEVENLABS_VOICE_ID", "").strip() or voice
    return choose_voice(eleven_voices(), context, preferred), model


def gateway_cast(item: dict, text: str, voice: str, context: str = "", language: str = "") -> dict:
    """Return a provider-compatible voice only with explicit Persian evidence."""
    if not persian(text, language):
        return {"voice": voice}
    metadata = {**(item.get("metadata") or {}), **{k:v for k,v in item.items() if k != "metadata"}}
    provider = str(metadata.get("speech_provider", metadata.get("provider", ""))).lower()
    raw = str(metadata.get("id", "")).lower()
    raw_model = raw.removeprefix("custom:").split("#", 1)[0]
    if raw_model in {"tts_eleven_multilingual_v2", "eleven_multilingual_v2", "eleven_flash_v2_5", "eleven_turbo_v2_5"}:
        raise ValueError("این مدل ElevenLabs از فارسی پشتیبانی نمی‌کند؛ نسخهٔ فارسیِ تأییدشده را انتخاب کنید.")
    # Execution IDs are not capability evidence. Both provider and supported
    # language must come from registered metadata, except documented v3 IDs.
    eleven = provider == "elevenlabs" or raw in {"eleven_v3", "custom:eleven_v3#jarvis-all-models"}
    google = provider in {"google", "google_ai_studio", "gemini"}
    if not (eleven or google) or not (languages(metadata) & FA or raw in {"eleven_v3", "custom:eleven_v3#jarvis-all-models"}):
        raise ValueError("مدل صدا پشتیبانی تأییدشدهٔ فارسی از ElevenLabs یا Google ندارد؛ Routing نریشن را اصلاح کنید.")
    voices = metadata.get("voices") or []
    if not voices and eleven:
        voices = eleven_voices()
    if google:
        # Google prebuilt voices inherit the model's supported languages.
        voices = [{**v, "languages": ["fa"]} for v in voices if isinstance(v, dict)]
    selected = choose_voice(voices, context, voice)
    return {"voice": selected}


def gateway_choice(cfg: dict, catalog: dict, text: str, voice: str, context: str = "", language: str = "") -> tuple[str, dict]:
    """Filter incompatible routes BEFORE submission. This is not media fallback."""
    from .lm_gateway import capabilities, model_allowed
    from app import lm_store
    profiles = lm_store.records("settings").get("speech_casting", {})
    for mid in cfg.get("models", []):
        item = catalog.get(mid, {})
        if not model_allowed(mid) or not item.get("enabled") or not item.get("available", True) or "speech" not in capabilities(item):
            continue
        if persian(text, language) and "speech" not in item.get("verified", []):
            continue
        item = {**item, **profiles.get("models", {}).get(mid, {}), "id": mid}
        try:
            casting = gateway_cast(item, text, voice, context, language)
        except ValueError:
            continue
        return mid, {"model": mid, "input": text, **casting, "response_format": "mp3"}
    raise ValueError("در Routing نریشن، مدل و گویندهٔ فارسیِ تأییدشده از ElevenLabs یا Google موجود نیست؛ قبل از تولید، تنظیمات صدا را تکمیل کنید.")


def identity(text: str, voice: str, model: str, *, language: str = "", context: str = "") -> str:
    """Actual casting belongs in the cache key, not the old English default."""
    if not persian(text, language):
        return f"{voice}|{model}"
    from . import lm_gateway
    if lm_gateway.configured():
        from app import lm_store
        cfg = lm_gateway.defaults().get("narration", {})
        mid, body = gateway_choice(cfg, lm_store.records("models"), text, voice, context, language)
        return json.dumps(["casting-v1", mid, body["voice"], "fa"], ensure_ascii=False)
    selected, model = eleven_cast(text, voice, model, language=language, context=context)
    return json.dumps(["casting-v1", model, selected, "fa"], ensure_ascii=False)
