# 08 — Verification Plan

Statuses: **Installed** (exists) → **Integrated** (invoked through a real EditorGPT execution path) → **Verified** (automated + e2e evidence meeting the targets). A capability is reported "integrated" only after Verified.

## 1. Benchmark set (frozen in Phase 0)

| # | Type | Input | Engine path |
| --- | --- | --- | --- |
| 1 | Persian talking-head reel | fixed 60 s clip with speech | `app/talking_reel.py` |
| 2 | Product introduction | fixed product URL + images | product reel path (`creative/reel_designer.py`) |
| 3 | Motion-graphics explainer | fixed Persian brief | `app/motion_graphic.py` |
| 4 | Data-driven animated video | brief with 4 given numbers | motion path with data scenes |
| 5 | Music-synchronized edit | brief + 45 s target + accent on reveal | motion path + music director |
| 6 | Reference-style edit | one reference file (local) | `creative/reference.py` + motion/talking |

Each is run N=3 per configuration (baseline vs flag-on), same seeds/config where possible.

## 2. Measurable criteria

| Dimension | Metric | Target |
| --- | --- | --- |
| Correctness | job completes; no placeholder text; claims only from the brief | 100 % |
| Narration accuracy | ASR-vs-script completeness (`creative/audio/verify.py`) | ≥ 0.95 per scene |
| Timing | |actual − requested duration| / requested | ≤ 15 % |
| Audio | integrated loudness −14 ±1.5 LU, true peak ≤ −1 dBTP (`creative/audio/loudness.py`) | pass |
| Music sync (type 5) | cuts within ±80 ms of a beat; reveal within ±0.8 s of drop/accent | ≥ 60 % cuts, reveal pass |
| Visual | blank-frame/overlap gate pass (`visual_gate`), zero browser errors | pass |
| Reliability | render success without manual retry | ≥ 95 % over 20 runs |
| Latency | wall-clock plan→mp4 | no regression > 10 % vs baseline |
| Cost | tokens and provider spend per film | no increase > 5 % (Phase 1/2), logged |

## 3. Creative quality rubric (reproducible)

Seven criteria scored 1–5 by at least two blind reviewers (Persian speakers) on randomised A/B pairs (baseline vs treated), order hidden: hook strength (first 2 s), narrative clarity, visual variety (no repeated layout), motion purpose, typography legibility (Persian shaping intact), audio–visual sync, polish/pacing. Report mean difference and a paired sign test; claim improvement only if ≥ 0.4 mean gain with p < 0.1 over ≥ 12 pairs. Reviewers see no flags or file names.

## 4. Per-capability verification

| Capability | Automated | End-to-end | Pass condition |
| --- | --- | --- | --- |
| `score_plan` | golden plans: repetitive plan → `revise/fail`; varied plan → `ok/strong`; Persian generic-phrase list; exception → `ok` | benchmark 3, 5 with flag on/off | catches ≥ 80 % of hand-labelled bad plans, ≤ 10 % false positives on good ones; blind rubric visual-variety gain |
| Delivery promise | unit: still replaces motion → violation | forced downgrade run stops at `needs_input` | stops, never silently substitutes |
| Fix-required findings | schema test: error without fix rejected | review replay on 10 stored reviews | 100 % of errors carry fix text |
| Duration honesty | parse "حدود ۴۵ ثانیه" variants; clamp tests | benchmark 5 | within ±15 % |
| Semantic retrieval (conditional) | recall@3 on 50 labelled queries vs tag baseline | benchmark 2 | gain ≥ 15 points recall@3, else drop |

## 5. Reporting

Each phase ships a short evidence file (`docs/audits/openmontage/evidence/<phase>.md`) with the run IDs, metrics table, rubric scores. Without it the capability stays "Installed/Integrated".

## 6. Limits of this plan

Rubric reviewers and the labelled retrieval set must be provided by the owner; automated metrics alone do not establish creative quality.
