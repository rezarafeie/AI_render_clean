# 01 — Executive Summary

Audit of OpenMontage (commit `fecb9a1e3cc2`, shallow clone, 2285 files, AGPL-3.0) against EditorGPT (this repository, HEAD `0e9c667`). Read-only; nothing in EditorGPT was changed by this audit. Evidence is source inspection (docstrings, class metadata, imports, directory layout, greps). **No OpenMontage code or test was executed** (it needs provider keys and heavy dependencies); see `11_COVERAGE_REPORT.md` for what was and was not read.

## What OpenMontage actually is

An *instruction-driven* video production kit. Its own contract (`AGENT_GUIDE.md`, `PROJECT_CONTEXT.md`, `docs/ARCHITECTURE.md`) says Python is "tools + persistence" and that orchestration, creative decisions and review live in Markdown/YAML read by an external coding agent (Claude Code, Codex, Cursor…). There is no Python orchestrator, no Python reviewer, no runtime LLM client.

| Layer | What exists (verified by file listing) |
| --- | --- |
| Tools (`tools/`) | 140 `BaseTool` subclasses: 68 API-backed, 17 local, 15 local-GPU, 9 hybrid. Stability tags: **6 production, 56 beta, 75 experimental**. Families by capability: 28 video-generation, 21 image-generation, 16 TTS, 13 analysis, 10 video post, 7 music generation, 7 enhancement, plus avatar, subtitle, capture, 3D, stock sources (19 adapters). |
| Pipelines (`pipeline_defs/*.yaml`) | 13 manifests (talking-head, animated-explainer, cinematic, screen-demo, clip-factory, documentary-montage, localization-dub, podcast-repurpose, avatar-spokesperson, hybrid, animation, character-animation, framework-smoke). Stages: idea/research → proposal → script → scene_plan → assets → edit → compose → publish. |
| Instructions (`skills/`, 158 MD files) | Per-stage director skills, meta skills (reviewer, taste-direction, creative-intake, video-reference-analyst, voice-performance-director, checkpoint-protocol), creative skills (short-form, storytelling, sound-design, data-visualization, broll-planning…). |
| Layer-3 knowledge (`.agents/skills/`, 93 skill folders, 580 MD files) | Third-party/vendored provider and framework guides (HyperFrames, Remotion, GSAP, Three.js, ElevenLabs, FLUX, …). Not OpenMontage's own work; licences vary per skill. |
| Deterministic libs (`lib/`) | `slideshow_risk`, `variation_checker`, `delivery_promise`, `source_media_review`, `scoring` (provider ranking), `corpus` + `clip_embedder` (CLIP retrieval), `checkpoint`, `playbook_generator`, `hyperframes_style_bridge`. |
| Renderers | `remotion-composer/` (React compositions: StatCard, ComparisonCard, ProductReveal, charts, TerminalScene, captions) and `tools/video/hyperframes_compose.py` (1469 lines). |
| Extras | `backlot/` (local storyboard board UI), `ink-theater/` (puppet/mocap animation), 195 test files. |

## What it is not

* Not an application with users, jobs, storage or auth. It is a kit driven by an agent in a developer's terminal.
* Not Persian-aware: the only non-English text handling found is Thai segmentation (`pythainlp`) and generic provider TTS. No RTL/Persian shaping or Persian narration verification was found. EditorGPT's Persian-specific machinery (letter joining, Persian ASR checks, Persian voice policy) has no counterpart.
* Most of its breadth is *provider wrappers* (video/image/TTS APIs). EditorGPT deliberately routes every provider through its own router (`tests/test_no_router_bypass.py`), so those wrappers are not reusable.

## Key findings

1. **Most value is ideas and checks, not code.** The genuinely distinctive, deterministic pieces are small: slideshow-risk scorer (258 lines), scene-variation checker, delivery-promise classifier, source-media-review contract, CHAI-style reviewer rules. EditorGPT has weaker equivalents (`creative/checks.py` is 16 lines, `visual_gate.py` is blank/overlap only).
2. **EditorGPT already covers or exceeds OpenMontage in the areas that matter to its product**: HyperFrames motion with browser checks and a registry (594+ resources, 59 vendored skills, Motion Kit), Persian narration verification (`creative/audio/verify.py`), reference analysis (`creative/reference.py`), music/rhythm/mix (`creative/audio/*`, just built and measured), RunPod cloud render with budgets.
3. **AGPL-3.0 is the dominant constraint.** EditorGPT is a network service. Copying OpenMontage code *or its instruction text* into EditorGPT risks a derivative-work finding that would require offering EditorGPT's corresponding source to users. Recommendation: **clean-room reimplementation of concepts only; no code, prompt or YAML copying** until counsel says otherwise.
4. **Heavy or risky candidates should be skipped**: CLIP corpus retrieval (350 MB model, torch), provider scoring, 100+ provider wrappers, ink-theater, Backlot UI.

## Recommendation

Do not integrate OpenMontage as a dependency or service. Adopt a **small set of independently re-implemented quality checks** into existing modules behind feature flags, measured by a fixed benchmark:

1. Deterministic *slideshow-risk / variation* score for motion plans and storyboards (extend `creative/checks.py`; run before scene authoring and before render).
2. *Delivery promise* record at plan time, verified before render (extend `app/motion_graphic.py` plan notes; prevents silent downgrades).
3. Reviewer *findings contract* (every error carries a concrete fix) in `creative/review.py`.
4. Optional later: a *taste profile* (3 dials + anti-patterns) as planner guidance, authored from scratch.

Everything else is classified skip or investigate in `04_INTEGRATION_MATRIX.md`. First task: `10_CODEX_IMPLEMENTATION_TASKS.md` → T1.

Status vocabulary used throughout: **Installed** (files exist) → **Integrated** (invoked through a real EditorGPT path) → **Verified** (automated + e2e evidence). Nothing from OpenMontage is Installed, Integrated or Verified in EditorGPT today.
