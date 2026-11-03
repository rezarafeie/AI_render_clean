# Audio engine: configuration, directives, cost and limits

What is configured, what each directive does, and what costs money. Status of every feature is in `AUDIO_ENGINE_STATUS.md`; this file is
for the person running the installation. Nothing here lists a secret value.

## Providers

| Capability | Provider in use | Needs |
|---|---|---|
| Narration (TTS) | ElevenLabs, model `eleven_v3` (`LOCALIZE_TTS_MODEL`), through the LM gateway when `LMAPI_*` is configured, else directly | `ELEVENLABS_API_KEY`, a voice (`ELEVENLABS_VOICE_ID`; Persian: `PERSIAN_ELEVENLABS_VOICE_ID`), optional `ELEVENLABS_PROXY_URL` |
| Speech recognition | ElevenLabs Scribe, then the gateway providers, then local faster-whisper (`ASR_ENGINE`, `WHISPER_ENABLED`, `WHISPER_MODEL_SIZE`, `WHISPER_TIMEOUT_SECONDS`) | the same key; local Whisper needs CPU time and its model downloaded |
| Music | the local library (`assets/music`, uploads in the Media library) | files with tags/mood; **no licence is recorded for the bundled tracks** |
| Sound effects | the local library (`assets/sfx`) | licensed files tagged `impact`, `click`, `whoosh`, `hit`, each with a `license`; today the library holds none, so every cue is reported `no_licensed_asset` |
| Loudness, mixing, analysis | ffmpeg and numpy (no extra service) | nothing |

Not available: Fish Audio, Mubert or any music/SFX generation provider, voice cloning. They were not integrated; no claim is made about their API or licence.

## Environment variables read by the audio path

`ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `PERSIAN_ELEVENLABS_VOICE_ID`, `LOCALIZE_VOICE_ID`, `LOCALIZE_TTS_MODEL`, `ELEVENLABS_PROXY_URL`,
`ELEVENLABS_CONNECT_TIMEOUT` (20 s), `ELEVENLABS_READ_TIMEOUT` (200 s), `ELEVENLABS_SCRIBE_CONNECT_TIMEOUT` (10 s), `ELEVENLABS_SCRIBE_READ_TIMEOUT` (200 s),
`TTS_PROVIDER` (`disabled` turns narration off), `ASR_ENGINE`, `WHISPER_ENABLED`, `WHISPER_MODEL_SIZE`, `WHISPER_TIMEOUT_SECONDS`,
`AUDIO_VERIFY_NARRATION` (`0` skips the narration check; the check is already capped at 90 s). Keys stay on the server; the browser never sees them.

## Directives (plain lines in the request)

```
Narrator: Eric                     voice from the studio's narrator list
Voice style: calm                  calm | serious | energetic | reflective | natural (a description is searched for these words)
Music: library, calm piano         or: Music: attached  /  Music: off
Music level: -14 dB                or quiet | low | medium | loud   (default about -10 dB)
Ducking: strong                    off | light (6 dB) | medium (12, default) | strong (18) | a number up to 30
Rhythm: balanced                   speech first (default) | music first | balanced | cinematic
Loudness: youtube                  reels | tiktok | youtube | podcast | social (default) | off
Pronounce: EditorGPT = ادیتور جی‌پی‌تی     whole-word, longest first; never guessed
Narration (English, speak exactly):    a numbered script, kept word for word
1. "First line."
2. "Second line."
```

A value that is not understood is reported in the project's notes and the default is used.

## What costs money and what is bounded

- **ElevenLabs characters:** one request per narration (all lines together). The take and its timestamps are cached by text, voice and style, so a re-render of unchanged text spends nothing. Changing a few lines voices only those lines.
- **Speech recognition check:** at most 90 s of wall clock per build; after two failed recognitions the rest is skipped. It never blocks the video.
- **Retries:** narration is retried a few times on a provider error; a scene that fails the check is voiced at most once more.
- **Free:** loudness measurement, mixing, ducking, rhythm analysis, scene snapshots, the `audio_check` and `plan_audio_direction` agent tools.
- **Not measured:** no per-project cost report exists yet; cost per build is not tracked in the app.

## Performance on a 4 vCPU / 8 GB server

Motion builds run in the app container (one thread per build). Narration, mixing and analysis use ffmpeg and numpy only; local Whisper is the only
heavy model and is the last fallback. A first Whisper use after a deploy can take minutes (the model loads); this is why the check is time-capped.
Scene snapshots add a few seconds and are capped at 150 s.

## Tests

`tests/test_audio_intelligence.py`, `test_audio_rhythm.py`, `test_motion_voice_music.py` (tracked), plus local files `test_audio_direction.py`,
`test_audio_partial.py`, `test_motion_english_ltr.py` (the repository's `.gitignore` excludes new files under `tests/`). All use synthetic audio and
stand-in providers; no real provider test has been run.

## Known limits

Naturalness of voice and pronunciation of names cannot be judged by these checks. Persian number, date and time words have not been listened to
with a real voice. The three bundled music tracks have no recorded licence. Per-line emotion is carried only by ElevenLabs v3 audio tags.
