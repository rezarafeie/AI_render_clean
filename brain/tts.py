"""Text-to-speech providers for generated narration."""
from __future__ import annotations

import logging
import os
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)
from .lm_gateway import observe_specialized


@dataclass
class TTSResult:
    file_path: str
    duration_s: float
    cost_usd: float | None = None
    provider: str = ""


_ELEVENLABS_TIMEOUT_SECONDS = 200


def _get_audio_duration(path: str) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=10,
        )
        return float(out.stdout.strip())
    except Exception:
        return 0.0


def _configured_provider(provider: str | None = None) -> str:
    """Installation policy: never silently switch speech providers."""
    return "disabled" if provider == "disabled" else "elevenlabs"


def _audit_direct(text: str, voice: str, model: str, started: float, error: Exception | None, size: int = 0) -> None:
    """The call goes straight to ElevenLabs (the account's own voices), so the studio records it itself: voice, model, latency and the outcome."""
    try:
        import time
        import uuid as _uuid
        from datetime import datetime, timezone
        from . import lm_gateway
        lm_gateway._audit({"id": str(_uuid.uuid4()), "timestamp": datetime.now(timezone.utc).isoformat(), "user_id": lm_gateway.user_context.get(),
                           "job_id": lm_gateway.job_context.get(), "conversation_id": lm_gateway.conversation_context.get(), "route": "narration",
                           "endpoint": "v1/text-to-speech", "requested_model": model, "actual_model": model, "provider": "elevenlabs", "transport": "direct-elevenlabs",
                           "status": "failed" if error else "success", "latency_ms": round((time.monotonic() - started) * 1000), "input_tokens": None, "output_tokens": None,
                           "cost": None, "http_status": None, "retry_count": 0, "fallback_history": [], "error": str(error)[:300] if error else None,
                           "request_message": f"voice={voice}; {len(text)} characters", "response_message": f"{size} bytes of audio" if not error else None})
    except Exception:
        log.debug("narration audit could not be written", exc_info=True)


def _generate_elevenlabs(
    text: str, output_path: str, voice_id: str = "", model_id: str = "",
    *, language: str = "", context: str = "",
) -> None:
    """One MP3 from ElevenLabs with the account's own voice (My Voices), through the studio's ElevenLabs relay: the chosen voice is the voice that speaks.

    Only when no ElevenLabs key is configured does the speech route of the AI router answer instead; a failing ElevenLabs request is reported, never replaced silently."""
    import time
    voice = voice_id or os.environ.get("ELEVENLABS_VOICE_ID", "")
    from .localize import elevenlabs_configured
    if not elevenlabs_configured():
        from . import lm_gateway
        if not lm_gateway.configured():
            raise RuntimeError("Neither an ElevenLabs key nor the AI router is configured; no speech request was sent")
        extra = {"language": language, "context": context} if language or context else {}
        Path(output_path).write_bytes(lm_gateway.speech('narration', text, voice, **extra))
        return
    from .localize import elevenlabs_speak
    started, error, size, model = time.monotonic(), None, 0, model_id
    try:
        audio, model = elevenlabs_speak(text, voice, model_id, language, _ELEVENLABS_TIMEOUT_SECONDS)
        Path(output_path).write_bytes(audio)
        size = len(audio)
    except Exception as exc:
        error = exc
        raise
    finally:
        _audit_direct(text, voice, model, started, error, size)


def generate_narration(
    text: str,
    output_dir: Path,
    voice_id: str = "",
    model_id: str = "",
    rate: str = "+0%",
    provider: str | None = None,
    fallback_voice_id: str = "",
    language: str = "",
    context: str = "",
) -> TTSResult:
    """Generate narration using the requested provider without silent substitution."""
    if not text.strip():
        raise ValueError("narration text is empty")

    provider = _configured_provider(provider)
    if provider == "disabled":
        log.info("narration skipped because TTS_PROVIDER=disabled")
        return TTSResult(file_path="", duration_s=0.0, cost_usd=0.0, provider="disabled")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"narration_{uuid.uuid4().hex[:12]}.mp3"
    from .localize import tts_voice, tts_model
    try:
        extra = {"language": language, "context": context} if language or context else {}
        _generate_elevenlabs(text, str(out_file), voice_id=voice_id or tts_voice(), model_id=model_id or tts_model(), **extra)
    except Exception:
        out_file.unlink(missing_ok=True)
        raise

    if not out_file.exists() or out_file.stat().st_size == 0:
        raise RuntimeError(f"{provider} returned empty audio")

    duration = _get_audio_duration(str(out_file))
    if duration <= 0:
        out_file.unlink(missing_ok=True)
        raise RuntimeError(f"{provider} returned audio with no playable duration")
    log.info("TTS generated with %s: %s (%.1fs)", provider, out_file.name, duration)
    return TTSResult(
        file_path=str(out_file), duration_s=duration,
        cost_usd=None, provider=provider,
    )
