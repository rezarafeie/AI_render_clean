# 06 — Integration Blueprint

## Principle

OpenMontage contributes **ideas and independently written deterministic checks** to existing EditorGPT modules. It is never a dependency, service, submodule, vendored directory or copy source. No new agent framework, orchestrator, renderer, database, registry, skill loader, router or queue.

```
EditorGPT UI → Creative Director / request_brief → studio_orchestrator / LangGraph
  → existing tools + Registry → HyperFrames / Remotion / FFmpeg → RunPod/local render
  → existing QC (visual_gate, review, quality) ← NEW: plan_checks (pure functions)
```

## New code (all small, all inside existing packages)

| Unit | File | Contract | Notes |
| --- | --- | --- | --- |
| Plan quality score | `creative/plan_checks.py` (new, ~150 lines) | `score_plan(plan, drafts=None, *, language='fa') -> PlanScore{score:0..5, verdict:'strong|ok|revise|fail', dimensions:{name:{score,reason}}, violations:[str], suggestions:[str]}` | Dimensions are **defined by EditorGPT's own failure data** (see 08), not copied: repetition of layout/skill/ease, text-only scenes, motion without purpose (no stagger/callout), scene-length monotony, generic-copy phrases (Persian + English list authored here), unused narration beats. Pure; no model call. |
| Delivery promise | same file or `creative/promise.py` | `classify_promise(brief) -> 'motion'|'still'|'mixed'`, `promise_kept(promise, plan, drafts) -> list[str]` | Stored under `record['promise']`. Violation = stop + ask via existing `needs_input` status, never silent substitution. |
| Fix-required findings | edit `creative/review.py` | `Finding.proposed_fix: str = ''`; validator: required when `severity=='error'` | Backward compatible default. |
| Composition checks | edit `creative/motion_graphic.py` validators | two extra checks | `music_shorter_than_film`, `overlapping_cuts`. |
| Flag | `creative/plan_checks.enabled()` reads `PLAN_CHECKS` env (default off → on after verification) | | Same pattern as `director.enabled()`. |

## Data contracts

* `PlanScore` is JSON-serialisable and stored in `plan.json` under `quality` (new optional key; absent for older plans).
* UI exposure: one step-log row via existing `_note(directory, 'plan_check', text, state, detail)`; no new endpoint.

## Not adopted (and why)

CLIP corpus (cost, size), provider scoring (router doctrine), provider wrappers (router doctrine), Remotion components (AGPL, duplicates), Backlot/ink-theater (out of scope), pipeline manifests (EditorGPT has its own orchestration), MiniCut tools (external CLI + credits).

## Conditional (needs evidence first)

* Semantic B-roll re-rank in `brain/asset_match.py::broll_match` — only if a labelled retrieval benchmark shows a gain large enough to justify a heavier runtime; the embedding model must be MIT-licensed (OpenAI CLIP is MIT) and loaded lazily, off the app image's critical path, or run on the RunPod worker.
* Reference workflow gap analysis — compare `creative/reference.py` outputs against what OpenMontage's workflow asks the agent to produce (hook structure, pacing metrics) and add missing fields if useful.
