"""Put the account's own ElevenLabs (My Voices, through the Vercel relay) first on the narration route, so every engine's speech goes through the router
(its logs, its audit) with the voices the person added, instead of Jarvis' own ElevenLabs account.

Data only: one model record, the narration route's model order, and the casting profile (the voice catalogue is discovered from the account instead of a fixed list).
No speech is requested. Run with --apply; a backup of what it changes is written first.
"""
import argparse
import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from app import lm_store
from app.config import settings
from brain.lm_gateway import defaults

MODEL = "elevenlabs:eleven_v3"


def plan() -> dict:
    routes, models, settings_rows = defaults(), lm_store.records("models"), lm_store.records("settings")
    route = copy.deepcopy(routes["narration"])
    route["models"] = [MODEL] + [m for m in route.get("models", []) if m != MODEL]
    model = {"id": MODEL, "name": "ElevenLabs eleven_v3 (own account, Vercel relay)", "provider": "elevenlabs", "enabled": True, "available": True,
             "declared": ["tts"], "verified": ["speech"], "status": "Untested", "scope_registered": True,
             "metadata": {"id": MODEL, "speech_provider": "elevenlabs", "supported_languages": ["fa"], "registration_source": "scripts/configure_elevenlabs_tts.py"}}
    casting = copy.deepcopy(settings_rows.get("speech_casting", {}))
    casting["voices"] = []                                       # discovered from the account (its Persian voices), not a fixed list of one
    casting.setdefault("models", {})[MODEL] = {"speech_provider": "elevenlabs", "supported_languages": ["fa"]}
    return {"routes": {"narration": route}, "models": {MODEL: model}, "settings": {"speech_casting": casting},
            "before": {"route": routes["narration"], "model": models.get(MODEL), "casting": settings_rows.get("speech_casting")}}


def main(apply: bool) -> None:
    result = plan()
    if apply:
        backup = Path(settings.JOBS_DIR).expanduser() / f"routes_backup_elevenlabs_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}.json"
        backup.write_text(json.dumps(result["before"], ensure_ascii=False, indent=1))
        lm_store.save("models", result["models"])
        lm_store.save("routes", result["routes"])
        lm_store.save("settings", result["settings"])
        print("applied; backup", backup)
    print(json.dumps({"narration_models": result["routes"]["narration"]["models"], "casting_models": list(result["settings"]["speech_casting"]["models"])}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    main(parser.parse_args().apply)
