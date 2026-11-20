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


@observe_specialized("audio", "elevenlabs-vercel-relay")
def _generate_elevenlabs(
    text: str, output_path: str, voice_id: str = "", model_id: str = "",
    *, language: str = "", context: str = "",
) -> None:
    """Generate one MP3 through the AI router (its speech route: Jarvis TTS models; the gateway's own fallbacks apply there)."""
    from . import gemini_tts
    if gemini_tts.is_gemini(voice_id):                     # a Gemini narrator is read by Gemini, not by the router's ElevenLabs route
        gemini_tts.speak(text, voice_id, Path(output_path))
        return
    from . import lm_gateway
    if not lm_gateway.configured():
        raise RuntimeError("The AI router is not configured; no speech request was sent")
    extra = {"language": language, "context": context} if language or context else {}
    Path(output_path).write_bytes(lm_gateway.speech('narration',text,voice_id or os.environ.get('ELEVENLABS_VOICE_ID',''), **extra))


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
