# 03 — EditorGPT Architecture (verified from this repository)

Verified by directory listing, `wc -l`, greps and reading module docstrings at HEAD `0e9c667` (1352 tracked files). Where a component was not opened beyond its docstring, it says so.

## Components and evidence

| Component | Evidence | Status |
| --- | --- | --- |
| Backend API | `app/main.py`, `app/routers/*`, FastAPI | verified present |
| Studio orchestration (Lite) | `app/studio_orchestrator.py` (2587 lines), typed tools in `app/studio_tools.py`, request analyst `app/request_brief.py` | verified |
| LangGraph (Medium agent) | `app/agents/{planner,dispatcher}.py`, `app/agents/medium/{nodes,state,tools,checkpoints}.py`; `langgraph` in `requirements-prod.txt` | verified present; not exercised in this audit |
| Hermes | `hermes/` (own service: routers, services, security), `integrations/hermes` | present; internals not read |
| Creative Director | `creative/director.py` (230 lines): understand → concepts → critique → plan; `script.py`, `capabilities.py`, `prompts.py`, `schemas.py` | verified |
| Creative Resource Registry | `creative/resources/{registry,providers,models}.py`; docs `docs/CREATIVE_RESOURCE_REGISTRY.md` (594 entries at 2026-10-27; skills library adds 59 vendored skills since) | verified |
| Motion engine (HyperFrames) | `app/motion_graphic.py`, `creative/motion_graphic.py`, `creative/reel_designer.py`, `creative/{library_scout,visual_gate,skills_library,shotcraft*}.py`, `creative/motion_kit/*`, `vendor/motion-skills` | verified (built and run in this project) |
| Remotion | `remotion/` (render.mjs, shotcraft loaders); legacy path per registry doc | present |
| FFmpeg / MLT editing | `engine/build_mlt.py`, `engine/*` (captions, effects, denoise, long_transcribe…) | verified present |
| Talking engines | `app/talking_reel.py`, `brain/talking_reel*.py`, `engine/talking_styles/*` | verified |
| Reference analysis | `creative/reference.py` (431 lines): ffmpeg scene cuts, palette, vision description, honest `unavailable` status | verified |
| Audio | `creative/audio/{rhythm,music_fit,music_director,music_providers,music_select,mixer,loudness,quality,verify,persian,sound_design,timing…}.py`, `brain/{tts,voice_clone,elevenlabs_transport}.py` | verified; music stack measured on a real render |
| Quality control | `brain/qc_pipeline.py` (sample → review → patch → re-render), `brain/qc_review.py`, `creative/review.py` (evidence-bound visual review; severities error/warning), `creative/checks.py` (16 lines, storyboard facts), `creative/visual_gate.py` (blank/overlap stills), `creative/audio/verify.py` (ASR vs script), `engine/technical_qc.py` | verified |
| Asset matching | `brain/asset_match.py` — **tag overlap only, "No embeddings yet"** per its docstring | verified |
| Model routing | `brain/{llm,lm_gateway,lm_direct,lm_adapters,ai_provider}.py`; guard `tests/test_no_router_bypass.py` | verified |
| Cloud render | `app/render_cloud/*`, RunPod ledger with budgets and local fallback | verified (live) |
| Jobs | `app/celery_app.py`, `app/jobs.py`, `jobs/`, thread fallback | present |
| Frontend | `web/` (React/Vite, PWA), Edit tab, chat studio | present; not re-read |
| Persian specifics | `creative/audio/persian.py`, `engine/*captions*`, Persian MOTION_CRAFT rules, fonts catalog | verified |

## Extension points (where new capabilities should attach)

1. **Pre-render deterministic checks** — `creative/checks.py` (`output_issues`) and `creative/motion_graphic.py` plan validators (`validate_plan` near the `MIN/MAX_SECONDS` checks). Both are pure functions over plan dicts; ideal for scorers.
2. **Review findings** — `creative/review.py::Finding` (`severity` is `error|warning`; no required fix text).
3. **Planner guidance** — `creative/prompts.py`, `MOTION_CRAFT` text in `creative/motion_graphic.py`, directives in `creative/directives.py`.
4. **Registry** — `creative/resources/providers.py` adapters (`skill_resources`, `shotcraft_resources`, …).
5. **Plan notes/log** — `_note(directory, key, text, state, detail)` in `app/motion_graphic.py` is how the UI shows steps.
6. **Feature flags** — `app/studio_flags.py` and `creative/directors.py::enabled()` patterns.

## Known limitations relevant to this audit

* `creative/checks.py` covers only storyboard source repetition, missing music and Persian voice; nothing scores motion plans for monotony.
* `brain/asset_match.py` is tag-only; no semantic retrieval.
* `creative/review.py` findings carry no mandatory "proposed fix".
* No unified cost estimate/reserve/reconcile across providers (RunPod ledger and music counters are separate).
* Open defects from the latest real render (not OpenMontage-related): requested ~45 s produced 63 s; library track without a drop; fixed locally but undeployed missing import in `app/motion_graphic.py`.

## Existing guardrails an integration must respect

* `tests/test_no_router_bypass.py` (provider origins/keys only in sanctioned files).
* Skill/resource licence doctrine: entries carry licence notices but never `verified`/`commercial_use_approved` without owner decision.
* Deploys are layered images guarded by "no ffmpeg / no active motion record".
