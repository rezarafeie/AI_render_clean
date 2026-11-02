# Audio Intelligence — repository audit and status

Branch `feat/audio-intelligence-foundation`, built on the latest teammate branch (`fix/studio-render-hermes-20261102` + voice/music directives).

## Audit: what already exists (read from the code)

| Area | Where | State |
|---|---|---|
| TTS | `brain/tts.py`, `brain/localize.py` (`synthesize_narration`, `_elevenlabs_with_timestamps`, `NARRATORS`, `VOICE_STYLES`), gateway TTS via `brain/speech_policy.py` | ElevenLabs (eleven_v3, v3 audio tags as style), Edge TTS fallback, LMAPI gateway casting. Word timestamps come from ElevenLabs. Fish Audio is **not** integrated. |
| Voice choice | `brain/speech_policy.py::choose_voice`, `eleven_cast` | Chooses from the account's voices; Persian-aware. |
| STT | `brain/transcribe.py` (faster-whisper), `brain/transcribe_elevenlabs.py`, `brain/long_transcribe.py` | Word-level transcripts, Persian normalization, caching. WhisperX / forced alignment: not present. |
| Pauses / silence | `brain/silence.py`, `engine/denoise.py`, `brain/denoise_manager.py` | Silence ranges, word gaps, denoise with approval flow. |
| Music | `brain/music.py` (mix with fades/loudness target), `engine/music_mix.py`, `engine/library.py` (tags, mood, energy), `app/routers/music.py` | Library + upload + mixing for reels. No beat/BPM analysis, no provider search or generation (no Mubert). |
| SFX | `engine/sfx.py` | Cue placement for a fixed set of effects; no generation. |
| Motion | `creative/motion_graphic.py`, `app/motion_graphic.py`, HyperFrames | Voiced motion graphics (narration clips with measured timing), music bed with ducking (this branch). |
| Libraries | `librosa`, `pyloudnorm`, `whisperx`, `torch` | **Not in requirements.** Only `faster-whisper`, `numpy`, `elevenlabs`. |
| Loudness | `brain/music.py::music_target_lufs`, ffmpeg `loudnorm` in `engine/render.py` | Used in renders; no standalone measurement or reports. |

## Implemented in this slice (tested)

- `creative/audio/contracts.py` — `AudioTimingEvent`, `VoiceDirection`, `VoiceGenerationRequest`, `MixSettings`, `AudioDirectionPlan`; integer-millisecond timebase with explicit rounding (`ms()` half-up, `frame()` floor).
- `creative/audio/persian.py` — Persian letter unification, digits (any script) and percentages spelled out, explicit pronunciation dictionary (whole-word, longest first). English text untouched. The script is never overwritten; the speakable text is derived.
- `creative/audio/loudness.py` — EBU R128 measure and two-pass normalize with configurable presets (reels/TikTok/YouTube/podcast/social); no peak normalization.
- `creative/audio/quality.py` — objective report: missing/unreadable file, clipping, silence ratio, duration mismatch, loudness/true-peak vs preset, word-level completeness against a supplied transcript; states what it cannot judge.
- Motion-graphic narration now speaks the normalized text, reads `Pronounce: Written = Spoken` lines from the request, and checks every narrated clip (problems reported, never fatal).

## Added in the second slice (tested with synthetic audio and mocked recognition)

- `creative/audio/rhythm.py` - tempo, beats, onsets, energy peaks, section changes and (only when distinguishable) downbeats from the audio itself. **numpy only**: no librosa, no new dependency, nothing to install on the server. Verified on click tracks (70-160 BPM) to within ~1 BPM. Known limitation: tempo is ambiguous by a factor of two, and a 140 BPM track can be reported as 70 (the beat grid still lands on real beats, every second one).
- `snap_starts` and the `Rhythm:` directive (`speech first` default, `music first`, `balanced`, `cinematic`): in balanced / music-first a scene start waits for a near beat (0.35 s / 0.9 s), never moves earlier, and carries its narration with it; the 60 s cap is respected.
- `creative/audio/verify.py` - narration is recognised by the existing speech-recognition path and compared with the script (word error, wrong script); a failed scene is voiced once more; a check that cannot run is reported as not checked. Bounded by a 120 s budget; switch off with `AUDIO_VERIFY_NARRATION=0`. The report is stored as `audio_report.json` in the motion folder.
- `pyloudnorm` was not added: ffmpeg's EBU R128 implementation already measures and normalizes loudness.

## Not implemented (needs decisions or dependencies)

Fish Audio and other TTS providers, emotion-per-sentence controls beyond ElevenLabs v3 tags, partial re-generation of a sentence, STT-based language/pronunciation verification wired into every render, WhisperX alignment, librosa beat/BPM/downbeat analysis, rhythm modes, music generation/search providers (Mubert), license tracking, SFX generation, per-track mixer and mastering, HyperFrames timing adapter, Hermes/LangGraph audio tools, Audio Studio UI, persistent audio project tables and cost budgets.

## Honest limits

- Whether Persian narration sounds natural, and whether a brand name is pronounced well, cannot be established by these checks; the report lists them under `not_checked`.
- Spelled-out digits and dictionary entries have not been listened to with a real Persian voice yet.
