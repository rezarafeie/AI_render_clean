# 04 — Integration Matrix

Classes: **A** directly reusable · **B** adapt into existing engine · **C** registry asset · **D** improve existing implementation · **E** replace only if proven superior · **F** skip · **G** requires investigation.

Licensing note applying to every row: OpenMontage is AGPL-3.0. "Reuse" below always means **independent reimplementation of the idea** unless stated; **no row is class A** because no OpenMontage code or text may be copied without legal sign-off (09). Priority: P1 high value/low cost … P4 skip-level.

| Capability | OpenMontage source | EditorGPT equivalent | Class | Integration point | Dependencies | Risk | Priority | Verification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Slideshow-risk scoring (6 dimensions) | `lib/slideshow_risk.py` | none for motion plans; `creative/checks.py` (storyboard only) | **B** (reimplement) | new pure function beside `creative/checks.py`, called from `creative/motion_graphic.py` plan validation and storyboard flow | none | low (heuristic; false positives) | P1 | unit tests on fixed plans + benchmark rubric (08 §3) |
| Scene variation checker (shot-size runs, generic phrases) | `lib/variation_checker.py` | none | **B** | same module; Persian generic-phrase list written from scratch | none | low | P1 | tests + blind review |
| Delivery-promise lock (motion-led vs still-led) | `lib/delivery_promise.py` | partial: narrator notes, `visual_gate` | **D** | record at plan in `app/motion_graphic.py` record; verify before render | none | low | P2 | e2e: forced downgrade must stop/ask |
| Source-media-review contract ("never claim reviewed without a real probe") | `lib/source_media_review.py` | `app/request_brief.py` + `creative/reference.py` + analysis in talking engines | **D** | audit that every planning path logs real probes; add missing | none | low | P3 | log assertions |
| Reviewer findings contract (accurate/complete/constructive; fix required for criticals) | `skills/meta/reviewer.md` | `creative/review.py::Finding` | **D** | add `proposed_fix` to `Finding`, require for `error` | none | low | P2 | schema test + review replay |
| Taste profile (3 dials + anti-patterns) | `skills/meta/taste-direction.md` | `creative/design_styles.py`, `style_packs.py`, directives | **C/B** | optional directive → planner prompt; own wording | none | low | P3 | A/B rubric |
| Short-form facts (safe zones, −14 LUFS, pacing 1–3 s, BPM) | `skills/creative/short-form.md` | hyperframes-studio safe zones, `creative/audio/loudness.py`, music director | **F** (already covered; facts not copyrightable) | — | — | — | P4 | existing tests |
| Provider scoring | `lib/scoring.py` | router (`brain/lm_*`) | **F** | — | — | policy conflict | P4 | — |
| Cost tracker (estimate/reserve/reconcile) | `tools/cost_tracker.py` | RunPod `Ledger`, music daily counters | **G** | investigate a thin shared view over existing ledgers (not a new tracker) | none | medium | P4 | design review |
| CLIP corpus retrieval | `lib/corpus.py`, `lib/clip_embedder.py`, `tools/video/corpus_builder.py` | `brain/asset_match.py` (tags only) | **G → E if proven** | optional semantic re-rank inside `broll_match` | torch/transformers + 350 MB weights | high (cost, image size, GPU) | P3 | retrieval A/B on a labelled set; skip if gain < threshold |
| Silence cutter | `tools/video/silence_cutter.py` | `brain/silence.py` | **F** | — | — | — | P4 | existing |
| Auto-reframe + face tracker | `tools/video/auto_reframe.py`, `tools/analysis/face_tracker.py` | `tools/face_track/`, face effects | **G** | compare on landscape→vertical sample | MediaPipe/OpenCV | medium | P3 | measured crop jitter |
| Scene detection | `tools/analysis/scene_detect.py` | `creative/reference.py::cut_times` (ffmpeg) | **F** | — | — | — | P4 | — |
| Audio energy offset | `tools/analysis/audio_energy.py` | `creative/audio/rhythm.py` + `music_fit.py` (measured superior in this repo) | **F** | — | — | — | P4 | existing tests |
| Audio mixer | `tools/audio/audio_mixer.py` | `creative/audio/mixer.py` (ducking, loudness) | **F** | — | — | — | P4 | existing tests |
| Music generation/search tools | `tools/audio/*music*.py` | `creative/audio/music_providers.py` | **F** (router doctrine; EditorGPT has Eleven Music/Stable/Jamendo/Epidemic) | — | — | — | P4 | — |
| MiniCut music fit / SFX | `tools/audio/minicut_*.py`, `tools/minicut_cli.py` | `music_fit.py`, `engine/sfx.py` | **F** | external CLI, credits | — | — | P4 | — |
| TTS provider tools (16) | `tools/audio/*_tts.py` | `brain/tts.py`, voice router | **F** | — | — | — | P4 | — |
| Video/image generation provider tools (49) | `tools/video/*_video.py`, `tools/graphics/*_image.py` | router + policy | **F** | — | — | policy | P4 | — |
| Composition validator (missing assets, narration > video, music shorter) | `tools/analysis/composition_validator.py` | `creative/checks.py`, `visual_gate`, `app/motion_graphic.py` validations | **D** | add "music shorter than film", "overlapping cuts" if missing | none | low | P3 | unit tests |
| Visual QA (caption occlusion, transition similarity) | `tools/analysis/visual_qa.py` | `visual_gate.py` (`TEXT_OVERLAP`), `review.py` | **F/D** | covered | — | — | P4 | — |
| Style playbooks + HyperFrames style bridge | `styles/*.yaml`, `lib/hyperframes_style_bridge.py` | `app/style_bridge.py`, `creative/style_packs.py`, fonts catalog | **D** | compare output fields only | none | low | P4 | — |
| Reference-video workflow | `skills/meta/video-reference-analyst.md`, `tools/analysis/video_analyzer.py` | `creative/reference.py` | **D/G** | read analyzer outputs for missing fields (hook structure, pacing metrics) | — | low | P3 | compare on 3 references |
| Pipeline manifests + stage director skills | `pipeline_defs/*.yaml`, `skills/pipelines/**` | `creative/director.py`, `app/studio_orchestrator.py`, `agents/medium` | **F** (as code) / **C** (ideas) | idea mining only; no copying | — | licence | P4 | — |
| Layer-3 vendored skills (HyperFrames, Remotion, GSAP…) | `.agents/skills/**` | `vendor/motion-skills`, `creative/skills_library.py` | **G** | each skill has its own upstream licence; consume upstream directly (not via OpenMontage) | — | licence | P4 | licence check |
| `music-to-video` skill + templates | `.agents/skills/music-to-video/**` | music director + motion engine | **G** | review upstream licence and templates for ideas | — | licence | P4 | — |
| Remotion components (StatCard, ComparisonCard, ProductReveal, charts) | `remotion-composer/src/components/**` | `remotion/`, Shotcraft, HyperFrames registry (594+ entries) | **F** (AGPL code; EditorGPT has equivalents) | — | — | licence | P4 | — |
| Backlot storyboard UI | `backlot/**` | Edit tab / studio chat | **F** | — | — | — | P4 | — |
| Ink-theater / character animation | `ink-theater/**`, `tools/character/**` | none, out of product scope | **F** | — | — | — | P4 | — |
| Checkpoint/approval protocol | `lib/checkpoint.py`, `skills/meta/checkpoint-protocol.md` | studio approvals, plan versions (`app/plan_versions.py`) | **F** | — | — | — | P4 | — |
| 3D / avatar / lip-sync tools | `tools/graphics/*3d*`, `tools/avatar/**` | none; paid providers | **F** | — | — | — | P4 | — |
| Stock source adapters (19) | `tools/video/stock_sources/*.py` | `brain/media_provider.py`, library | **G** | check licence/attribution handling; EditorGPT may add free sources via the router | — | licence/attribution | P3 | rights tests |
| Persian/RTL handling | none found | `creative/audio/persian.py`, MOTION_CRAFT | — | OpenMontage offers nothing here | — | — | — | — |

## Summary counts (matrix rows)

Counted by first-listed class over the 31 capability rows above: B 2 · C/B 1 · D 6 (delivery promise, source-media review, reviewer contract, composition validator, style playbooks, reference workflow) · G 6 (cost tracker, CLIP corpus, auto-reframe, layer-3 skills, music-to-video, stock sources) · F 16 (the rest; the Persian/RTL row is "none found" and is not counted). No A. No E accepted; E is only a conditional outcome for CLIP retrieval.

## Not claimed

Nothing in this table is "integrated". All rows are proposals; statuses are Installed=no, Integrated=no, Verified=no.
