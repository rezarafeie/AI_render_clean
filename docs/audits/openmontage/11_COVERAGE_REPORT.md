# 11 — Coverage Report

**Coverage is partial. This audit does not claim full source-level coverage of OpenMontage.**

Discovered inventory (verified by listing): 2285 files; 140 tool classes; 13 pipelines; 158 own skills; 93 vendored skill folders (580 MD); 21 artifact schemas; 5 playbooks; 195 test files.

| Area | Discovered | Depth reached | Gap and reason |
| --- | --- | --- | --- |
| Repo structure, licence, guides (`AGENT_GUIDE`, `PROJECT_CONTEXT`, README head, `docs/ARCHITECTURE` headings) | all | **read** (guides partly: first sections) | later sections of guides not read |
| Tool classes (140) | 140 | **metadata only** for all (stability, runtime, tier, capability via greps); **docstring + defs** for ~12; **head of file** for `base_tool.py`, `audio_energy.py`, `tool_registry.py` | bodies not read; provider contracts, retry/cost logic unverified; no tool executed (needs keys/GPUs/CLIs) |
| Deterministic libs (`lib/`, 20 files) | 20 | **docstring + defs** for 12 (`scoring`, `variation_checker`, `verify_scene_pacing`, `slideshow_risk`, `delivery_promise`, `source_media_review`, `hyperframes_style_bridge`, `playbook_generator`, `clip_embedder`, `corpus`, plus `variation_checker` first 60 lines, `slideshow_risk` head) | scoring dimensions' internal formulas not read; `checkpoint.py`, `asset_cache.py`, `media_profiles.py` not read |
| Pipelines (13) | 13 | **stage lists** extracted from YAML | per-stage tool lists, gates, success criteria not read |
| Skills (158) | 158 | **read in part**: `reviewer.md` (first 60 lines), `taste-direction.md` (first 30), `short-form.md` (first 25); **listed** all | creative-intake, video-reference-analyst, storytelling, sound-design, data-visualization etc. not read |
| Vendored layer-3 skills (93) | 93 | **listed**; frontmatter of 2 HyperFrames skills read | per-skill licences and content not audited |
| Remotion composer | files listed | **listed only** | no component source read |
| Backlot, ink-theater | listed | **listed only** (ink-theater notices existence seen) | not read |
| Tests (195) | counted | **not read, not run** | needs dependencies; cannot judge actual pass rate |
| Security | whole tree | **greps only** (`shell=True`, `eval/exec`, network imports, npm/npx) | `eval/exec` hits not opened; no dependency CVE scan |
| EditorGPT side | targeted | **docstrings + defs** for director, review, visual_gate, checks, native checks, qc_pipeline, asset_match, library_scout, reference, registry, audio quality/verify; docs registry file head | `hermes/`, `web/`, most of `engine/`, `studio_orchestrator.py` internals not re-read for this audit; claims about LangGraph/Hermes are "present", not "working" |

## Unverified claims (explicit)

* That any OpenMontage tool marked beta/experimental works as described.
* Output quality of OpenMontage pipelines (no run, no sample).
* Internals of `video_analyzer`, `video_understand`, `video_compose`, `hyperframes_compose`.
* Whether EditorGPT's equivalents are *better* in every case; comparisons rest on docstrings and on this project's own measured results for music/motion.

## Other caveats

* The clone is shallow (`git log` shows one commit); history and activity were not assessed.
* Only the audit documents were created. The working tree already contained an uncommitted one-line import fix in `app/motion_graphic.py` from earlier work (missing `svg_problems` import), unrelated to this audit and not deployed.

## What would raise coverage

Read the bodies of the 12 deterministic modules, run OpenMontage's `tests/lib` and `tests/contracts` in a throwaway venv, read the remaining meta skills, and review each vendored skill's upstream licence.
