# 05 — Execution Flows

## A. OpenMontage (as designed; traced from `AGENT_GUIDE.md`, `PROJECT_CONTEXT.md`, `pipeline_defs/*.yaml`, `lib/pipeline_loader.py`, `tools/tool_registry.py`)

```
developer prompt (in Claude Code / Codex / Cursor)
 → agent reads AGENT_GUIDE.md (Rule Zero: every production goes through a pipeline)
 → pipeline selected from pipeline_defs/*.yaml (loaded by lib/pipeline_loader.py)
 → preflight: tools/tool_registry.py discovers BaseTool subclasses, reports status → capability menu
 → per stage (idea/research → proposal → script → scene_plan → assets → edit → compose → publish):
      agent reads skills/pipelines/<pipeline>/<stage>-director.md
      agent calls tools (BaseTool.execute) — selector tools choose providers (tts_selector, video_selector, image_selector)
      agent self-reviews with skills/meta/reviewer.md (advisory, ≤2 rounds)
      artifact written + validated against schemas/artifacts/*.schema.json
      lib/checkpoint.py persists; human approval per manifest `human_approval_default`
 → compose: tools/video/video_compose.py (Remotion/FFmpeg) or hyperframes_compose.py
 → publish: tools/publishers/export_bundle.py
```

Where "intelligence" lives: Markdown/YAML read by the host agent. Where deterministic code sits: `lib/slideshow_risk.py`, `lib/variation_checker.py`, `lib/delivery_promise.py`, schemas, `CostTracker`. Nothing in Python calls an LLM; the host agent does. **Consequence: there is no OpenMontage runtime to embed.** Any integration is either (a) rewriting a deterministic check, or (b) adopting an idea in EditorGPT's own prompts.

Reference-driven path: `AGENT_GUIDE.md` → `skills/meta/video-reference-analyst.md` → tools `video_analyzer`, `transcriber`, `scene_detect`, `frame_sampler` → grounded summary → 2–3 concepts. (Not executed; analyzer internals only partly read.)

## B. EditorGPT motion path (verified, this project's code)

```
chat message → app/studio_orchestrator.py (_understand_request via app/request_brief.py → _brief_intent)
 → app/motion_graphic.py create()/start()
   plan (creative/motion_graphic.py plan(): MotionPlan, skills, fonts)
   → _narrate (continuous take, Persian voice) → _sync_rhythm → _add_music → _add_sfx → _attach_beats → _master_audio
   → scenes authored in parallel (creative/motion_graphic.py author_scene, validators incl. svg_problems)
   → still check (creative/visual_gate.py) → redesign loop → browser check
   → render (app/render_cloud on RunPod `hyperframes_page` profile, local fallback)
   → creative/audio/quality + technical_qc → finished record, thumb.jpg
```

Talking path: `app/talking_reel.py` → `brain/talking_reel*.py` → `engine/talking_styles/*` → MLT/FFmpeg (`engine/build_mlt.py`) → `brain/qc_pipeline.py` (sample → review → patch → re-render).

Creative direction: `creative/director.py::_direct` (understand → concepts → critique → plan) → `creative/script.py`.

## C. Precise introduction points (no duplicated orchestration)

| Idea | Insert at | Call shape |
| --- | --- | --- |
| Slideshow/variation score | after `plan()` returns and again after scenes are authored, inside `app/motion_graphic.py` just before the still check; storyboard flow: `creative/checks.py::output_issues` callers in `studio_orchestrator.py` | `score_plan(plan) -> {score, verdict, violations}`; `revise` verdict feeds the existing planner repair loop (`repairs=` parameter of `plan()`) |
| Delivery-promise lock | record in `plan.json`/record at plan time; verify in `_run_render` before render | `promise = classify(brief, plan)`; `assert_kept(promise, plan, drafts)` |
| Reviewer fix contract | `creative/review.py::Finding` + the JSON schema in its prompt | `Finding.proposed_fix: str` required when `severity=='error'` |
| Composition checks | `creative/motion_graphic.py` validators | add "music shorter than film", "overlapping cuts" |

## D. Sequence for the proposed check (P1)

```
planner → MotionPlan
   └→ creative.plan_checks.score_plan(plan)           # pure, no model, <10 ms
        ├ verdict ok          → continue
        └ verdict revise/fail → planner.plan(..., advice={'violations': [...]})   # existing repair path, max 1 retry
scenes authored → score_plan(plan, drafts)             # same function, adds markup-derived signals
→ still check → render → review
```

Failure mode: the check is advisory behind a flag; on any exception it logs and returns `ok` (never blocks a render).
