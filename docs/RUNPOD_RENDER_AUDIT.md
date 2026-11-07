# RunPod render boundary audit — 2026-11-07

Baseline: `fafcf6e`. This is an integration, not a replacement timeline or agent.

## Actual execution paths

* `app/routers/render.py` authorizes through `app/job_access.py` and calls
  `app/jobs.py::start_render`; `app/tasks.py::task_run_render` calls `_run_job`.
  `engine/render.py::render` renders MLT with melt, FFmpeg/ASS/poster processing.
* `app/talking_reel.py::plan_render` prepares footage and existing style engines.
  Styles in `engine/talking_styles/` combine native FFmpeg, OpenCV tracking,
  tscaps captions and browser layers. Talking invokes
  `engine/hyperframes/renderer.py::render_project` after project construction.
* `app/motion_graphic.py` owns planning, paid narration, design, validation,
  retries and version publication. Only its already-materialized page belongs
  on the render worker: `engine/hyperframes/standalone.py::render`.
* `engine/remotion_renderer.py::render` validates existing typed scene config,
  stages owned media and invokes `remotion/render.mjs` with Chromium. Native
  Shotcraft compositions use this same path. Do not regenerate the scene plan.
* HyperFrames `0.8.161` uses Chromium and FFmpeg; renderer supports sparse
  layers, cached audits and cancellation. Its generated HTML contains executable
  scene code: a cloud worker must have no application/provider credentials,
  no production DB/Redis access and restrictive network/OS isolation.

## Dependencies and operations

`Dockerfile` already supplies Python 3.12, Node 22, Chromium, FFmpeg/FFprobe,
MLT/melt, fonts, Remotion, HyperFrames and tscaps. Python requirements include
OpenCV, Pillow, numpy and faster-whisper. PyTorch/CUDA are not universal render
requirements. Existing frames, subtitles, voice clips, music and approved
templates must be bundled without calling AI Gateway from cloud execution.
Audio mastering, timestamps, partial voicing and rhythm are in `creative/audio/`;
these are preparation, not reasons to repeat paid generation on retries.

## Queues, persistence and ownership

Celery (`app/celery_app.py`) uses Redis, late ack, bounded task retries and the
default queue; transfers have a separate worker. Studio uses owned conversations,
messages and activity events in `app/studio_store.py`; user cancellation and job
history must remain authoritative on the VPS. Render state is spread between
job/project stores: a provider execution ledger is subordinate, not a replacement.
Never move Studio orchestration or supply its database credentials to a Pod.

Uploads, outputs and generated projects mostly use local/shared filesystem paths.
`app/cloud_storage.py` imports Drive media through authorized Composio links; it
is NOT a general S3 artifact store. A remote filesystem is therefore not a drop-in
replacement. Resolve ownership first, hash/materialize dependencies, then sign
each object. Absolute paths/symlinks/external URLs in generated projects need a
portability gate; reject rather than silently rewrite the timeline.

## Integration sequence and limits

1. Strict shared manifest, offline execution adapters and cost/routing contracts.
2. Persistent compare-and-swap execution ledger and provider lifecycle client.
3. S3 staging, scoped worker authentication, reconciliation and engine hooks.
4. Real CPU benchmarks and parity checks; GPU only with a verified compatible
   profile, never because the job uses a browser. Serverless stays disabled until
   duration/timeout/startup economics are measured.
5. Administrator-only canary, then explicit rollout. Existing local code remains
   default. Do not silently retry locally while a Pod might still be billing.

No live Pod, paid API call, benchmark or production deployment has been performed
by this audit. Existing provider keys must not be copied into worker images.
Provider deletion failures remain financial liabilities until reconciled; no
application can guarantee shutdown during a provider outage.

## Implemented integration map

```text
Existing authenticated Studio / project job
  → app.jobs / app.motion_graphic / app.talking_reel (owned execution context)
  → existing engine boundary → render_cloud.hooks
  → prepared immutable manifest + measured-profile policy
  → SQLite reservation / lease / durable create intent
  → RunPod REST dedicated Pod
      ↔ private S3 scoped bootstrap / status / cancellation objects
      → runner: download → isolated original engine → upload candidate
  → VPS integrity + FFprobe validation → atomic existing output path
  → existing review / preview / download / notification workflow

Independent timer → ledger reconciliation → exact owned Pod deletion
Independent billing timer → provider buckets → measured costs (admin only)
Existing Settings / auth → admin controls bounded by environment ceilings
```

No new Studio state machine, timeline parser, AI gateway or creative agent is
introduced. The cloud ledger is an infrastructure execution/financial liability
record. Existing app progress callbacks consume real worker stages; missing
percentages remain unknown. New cloud SDK dependencies load only on enabled paths.
Engine-specific portability restrictions and all outstanding live acceptance
gates are documented in RUNPOD_RENDER_ROLLOUT.md.
