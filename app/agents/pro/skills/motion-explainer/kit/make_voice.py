#!/usr/bin/env python3
# Generates Persian voice clips with ElevenLabs (per line + char timestamps).
# Usage: ELEVENLABS_API_KEY=sk_... python3 make_voice.py
import json, os, base64, urllib.request, urllib.error, sys
HERE = os.path.dirname(os.path.abspath(__file__))
VOICE = os.environ.get("EL_VOICE", "wEMHmIPIdyXK6OkgkB03")
MODEL = os.environ.get("EL_MODEL", "eleven_v4")        # v4 reads Persian and the [tone] tags; a voice that refuses it falls back to v3
KEY = os.environ.get("ELEVENLABS_API_KEY") or sys.exit("set ELEVENLABS_API_KEY")
out = os.path.join(HERE, "public", "voice"); os.makedirs(out, exist_ok=True)
lines = json.load(open(os.path.join(HERE, "lines.json"), encoding="utf-8"))
for lid, text in lines:
    mp3 = os.path.join(out, lid + ".mp3")
    if os.path.exists(mp3) and os.path.getsize(mp3) > 0: print("skip", lid); continue
    body = {"text": text, "model_id": MODEL, "language_code": "fa",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}}
    req = urllib.request.Request(f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}/with-timestamps?output_format=mp3_44100_128",
        data=json.dumps(body).encode(), headers={"xi-api-key": KEY, "Content-Type": "application/json"})
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=180).read())
    except urllib.error.HTTPError as e:
        if e.code not in (400, 422) or body["model_id"] == "eleven_v3":
            sys.exit(f"ERROR {lid} {e.code}: {e.read()[:300]}")
        body["model_id"] = "eleven_v3"
        req = urllib.request.Request(req.full_url, data=json.dumps(body).encode(), headers={"xi-api-key": KEY, "Content-Type": "application/json"})
        r = json.loads(urllib.request.urlopen(req, timeout=180).read())
    audio = base64.b64decode(r["audio_base64"])
    open(mp3, "wb").write(audio)
    json.dump(r["alignment"], open(os.path.join(out, lid + ".json"), "w", encoding="utf-8"), ensure_ascii=False)
    print("ok", lid)
