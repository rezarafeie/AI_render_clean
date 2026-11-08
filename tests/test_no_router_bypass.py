"""Every model/media request goes through the AI router (the gateway's routes, with its own direct fallbacks). This guard fails when code outside the
sanctioned places names a provider's network origin, imports a provider SDK, or reads a provider's API key: a direct request would bypass the router.

Sanctioned places (each is part of the router or a call the router has no route for):
  brain/lm_direct.py          the gateway's own direct fallbacks (Gemini, OpenAI, ElevenLabs, ...), used only after a route fails
  brain/lm_gateway.py         the router itself
  app/config.py               settings (hostnames for the DNS cache, keys handed to the fallbacks)
  brain/elevenlabs_transport.py + brain/transcribe_elevenlabs.py   ElevenLabs speech-to-text, called only as the router's fallback
  brain/localize.py, brain/speech_policy.py                        ElevenLabs voice catalogue / subscription lookups (the router has no route for them)
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = ("app", "brain", "creative", "engine", "hermes")
SANCTIONED = {"brain/lm_direct.py", "brain/lm_gateway.py", "app/config.py", "brain/elevenlabs_transport.py", "brain/transcribe_elevenlabs.py",
              "brain/localize.py", "brain/speech_policy.py"}
ORIGINS = re.compile(r"api\.openai\.com|generativelanguage\.googleapis\.com|api\.elevenlabs\.io|aiapi\.rafiei\.co|ai-gateway\.vercel\.sh|"
                     r"api\.anthropic\.com|api\.jarvis\.you|api\.sarovi\.ir", re.I)
SDKS = re.compile(r"^\s*(?:import|from)\s+(?:openai|anthropic|google\.genai|google\.generativeai|elevenlabs|litellm|langchain_openai|langchain_anthropic)\b", re.M)
KEYS = re.compile(r"os\.environ(?:\.get)?\(?\[?\s*[\"'](?:OPENAI_API_KEY|ANTHROPIC_API_KEY|GEMINI_API_KEY|GOOGLE_API_KEY|ELEVENLABS_API_KEY|ARVAN_AI_API_KEY)[\"']")


def _files():
    for directory in CODE:
        for path in (ROOT / directory).rglob("*.py"):
            if "node_modules" in path.parts or "__pycache__" in path.parts:
                continue
            yield path, path.relative_to(ROOT).as_posix()


def test_no_provider_origin_sdk_or_key_outside_the_router():
    offenders = []
    for path, name in _files():
        if name in SANCTIONED:
            continue
        text = path.read_text(errors="ignore")
        for label, pattern in (("origin", ORIGINS), ("sdk", SDKS), ("key", KEYS)):
            match = pattern.search(text)
            if match:
                offenders.append((name, label, match.group(0)[:60]))
    assert not offenders, "a direct provider request would bypass the AI router: " + repr(offenders)


def test_no_arvan_transport_is_left():
    for path, name in _files():
        if name in {"brain/lm_tasks.py", "brain/lm_direct.py", "app/routers/lm_admin.py", "brain/lm_gateway.py"}:
            continue                       # provider tables and admin text, not transports
        assert not re.search(r"ArvanProvider|ArvanImageProvider|_arvan_|arvan_image|ARVAN_AI", path.read_text(errors="ignore")), name
