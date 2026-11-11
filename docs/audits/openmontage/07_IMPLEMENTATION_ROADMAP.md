# 07 — Implementation Roadmap (proposal only; nothing here is started)

Each phase is independently deployable, flag-guarded, reversible. Cost/time/token effects are estimates from the design, not measurements; the verification plan (08) replaces them with evidence.

## Phase 0 — Baseline (no code)
* Objective: freeze a benchmark set (6 test types in 08) with current outputs and metrics so later phases can be compared.
* Rollback: none needed. Impact: none.

## Phase 1 — Plan quality score (P1)
* Objective: deterministic monotony/slideshow score on motion plans and storyboards.
* Capabilities: `score_plan` (06). OpenMontage reference: concept of `lib/slideshow_risk.py` / `lib/variation_checker.py` (read, not copied).
* Files: new `creative/plan_checks.py`; call sites in `app/motion_graphic.py` (after plan, after scenes) and the storyboard path that calls `creative/checks.py::output_issues`; tests `tests/test_plan_checks.py`.
* Data contract: `plan.json.quality`. Flag: `PLAN_CHECKS` (off by default; on after verification).
* Dependencies: none. Complexity: low.
* Regression risk: a false `revise` triggers one extra planner call (token cost). Mitigation: only act on `fail`, log `revise`.
* Rollback: unset flag. Quality impact: expected to catch repetitive plans before authoring; **unproven**. Render time: unchanged. Tokens: +0 (check) / +1 planner call on `fail` only. Infra cost: none.

## Phase 2 — Fix-required reviewer findings (P2)
* Files: `creative/review.py` (`Finding.proposed_fix`), prompt text in the same file, `tests` for schema.
* Flag: none needed (backward compatible default); add `REVIEW_REQUIRE_FIX` to enforce.
* Rollback: revert the field. Impact: review output becomes actionable; token +~5 %.

## Phase 3 — Delivery promise (P2)
* Files: `app/motion_graphic.py` (record key `promise`, check before render), `creative/plan_checks.py`.
* Flag: `DELIVERY_PROMISE`. Acceptance: a forced downgrade (still scene replaces motion) halts with `needs_input`.
* Rollback: unset flag.

## Phase 4 — Composition checks and duration honesty (P3, also fixes a live defect)
* Files: `creative/motion_graphic.py` validators, `app/motion_graphic.py`.
* Includes the open defect from the real render: a requested duration ("حدود ۴۵ ثانیه") must constrain plan/narration (not an OpenMontage feature; scheduled here because it belongs to the same validation seam).

## Phase 5 — Reference workflow gap check (P3, investigation → possible small change)
* Compare `creative/reference.py` outputs to OpenMontage's reference-analysis expectations; add missing measured fields only.

## Phase 6 — Optional semantic retrieval (P3, gated by evidence)
* Run a labelled retrieval benchmark first. If a gain is not demonstrated, stop. If it is, implement as lazy re-rank in `brain/asset_match.py` with the model on the RunPod side or off the critical path.
* Risks: image size, startup time, GPU; rollback: flag off.

## Order and dependencies

0 → 1 → 2 → 3 → 4 (4 independent of 2/3) → 5 → 6. Each phase ships alone.

## Explicitly out of the roadmap

Provider wrappers, provider scoring, Backlot, ink-theater, MiniCut, Remotion component code, pipeline manifests.
