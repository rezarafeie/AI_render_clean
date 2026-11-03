# Audio Intelligence Engine — status

Audited from the code (branch `feat/audio-direction`, on top of `fix/motion-inter-font`). Existing infrastructure is reused; nothing is replaced.

| Area | State | Where |
|---|---|---|
| Timing contract (ms timebase, `AudioTimingEvent`) | implemented, tested | `creative/audio/contracts.py` |
| Persian normalisation, numbers, pronunciation dictionary (script kept apart from spoken text) | implemented, tested | `creative/audio/persian.py` |
| Voice request contract + provider capability reduction (unsupported wishes dropped and reported, no language fallback) | implemented, tested (new) | `creative/audio/providers.py` |
| Audio Direction Plan from brief + directives, per-line emotion arc | implemented, tested (new) | `creative/audio/direction.py` |
| Word/pause timing from provider timestamps | implemented, tested | `creative/audio/timing.py` |
| Rhythm: tempo, beats, downbeats, onsets, energy peaks, beat-snapped scene starts | implemented, tested | `creative/audio/rhythm.py` |
| Sound design: intensity presets, purpose-based cues, provenance, unfilled-cue reporting | implemented, tested (new) | `creative/audio/sound_design.py` |
| Loudness (EBU R128 via ffmpeg), presets, final master mix | implemented, tested | `loudness.py`, `mixer.py` |
| Quality gate: completeness (WER), clipping, silence, duration, loudness; ASR-based verify with one bounded repair | implemented, tested | `quality.py`, `verify.py` |
| Music bed: library pick, trim, fade, ducking | implemented (basic) | `creative/music_bed.py` |

Not done yet (do not treat as available):
- Wiring `direction.plan`, `providers.prepare` and `sound_design.plan` into the motion pipeline and `brain/tts.py` (new modules are not called yet).
- SFX: the library holds no licensed SFX (one test file), so every cue is reported `no_licensed_asset`. Needs a licensed pack or a generation provider.
- Music: provider search/generation (Mubert etc.), licence tracking, key/instrumentation analysis, loop and crossfade editing.
- Fish Audio and other voice providers; word-level partial regeneration; separate forced alignment.
- Agent tools (`audio.*`) in the Medium graph, persistence tables and migration, Audio Studio UI, cost tracking.
- Not run: real provider calls, end-to-end acceptance scenarios A–D.
