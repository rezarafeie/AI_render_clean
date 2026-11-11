# 10 — Codex Implementation Tasks (NOT to be executed until explicit approval)

Common rules for every task: clean-room (do not open OpenMontage source; use `docs/audits/openmontage/*` descriptions only); no new dependencies; no new provider origins; flag-guarded; keep `tests/test_no_router_bypass.py` green. Test python: the project venv. Test command base: `python -m pytest -q`.

## T1 — Plan quality score (first task)

* **Scope:** pure function `score_plan` + flag; wire in advisory mode (log only).
* **Inspect:** `creative/checks.py`, `creative/motion_graphic.py` (`MotionPlan`, `ScenePlan`, plan validators near `MIN_SECONDS/MAX_SECONDS`), `app/motion_graphic.py` (`_note`, plan step), `creative/director.py::enabled` (flag pattern).
* **Change:** add `creative/plan_checks.py`; add `quality` optional key to plan record; call after plan and after scene authoring; log one step row.
* **Steps:** (1) define dimensions from EditorGPT data: layout/skill repetition, text-only scene ratio, scene-length monotony, generic-copy phrases (Persian and English lists authored here), motion without callouts/stagger, narration beats unused; (2) implement scoring 0–5, verdict thresholds; (3) wrap in try/except → `ok` on error; (4) `PLAN_CHECKS` env flag, default off; (5) write golden-plan tests.
* **Integration requirement:** advisory only; never blocks render; no extra model call.
* **Tests:** `python -m pytest -q tests/test_plan_checks.py tests/test_motion_skills.py tests/test_no_router_bypass.py`.
* **Acceptance:** repetitive golden plan → `revise|fail`; varied plan → `ok|strong`; error path returns `ok`; flag off → byte-identical plan JSON.
* **Rollback:** unset flag or revert the commit.

## T2 — Act on `fail` with one planner retry

* **Scope:** when flag `PLAN_CHECKS=act` and verdict is `fail`, pass violations as `advice` to `plan()` once.
* **Inspect:** `creative/motion_graphic.py::plan(... advice=...)`, `app/motion_graphic.py` plan step.
* **Steps:** add retry with a cap of one; log both scores.
* **Tests:** `tests/test_plan_checks.py::test_retry_once`, existing planner tests.
* **Acceptance:** at most one extra planner call; second result stored even if still `fail`.
* **Rollback:** flag back to advisory/off.

## T3 — Fix-required review findings

* **Scope:** `creative/review.py::Finding.proposed_fix`.
* **Inspect:** `creative/review.py` (Finding at ~line 19, prompt at ~line 90, status logic ~line 109).
* **Steps:** add optional field default `''`; update the prompt's JSON shape; validator requiring text for `severity=='error'` when `REVIEW_REQUIRE_FIX=1`; update report rendering.
* **Tests:** `tests/test_review*.py` (add if absent): error without fix rejected under flag; old stored reviews still load.
* **Acceptance:** schema accepts old data; flag enforces new rule.
* **Rollback:** unset flag / revert.

## T4 — Delivery promise

* **Scope:** classify and keep the motion/still promise.
* **Inspect:** `app/motion_graphic.py` (`create`, render step), `creative/visual_gate.py`.
* **Steps:** classify at create; store `record['promise']`; before render compare against drafts (e.g. static-image scenes replacing designed motion); on violation set `needs_input` with a Persian explanation.
* **Tests:** unit for classifier and violation; e2e with a forced downgrade.
* **Acceptance:** no silent downgrade.
* **Rollback:** flag `DELIVERY_PROMISE` off.

## T5 — Duration honesty

* **Scope:** requested duration constrains plan/narration.
* **Inspect:** `creative/motion_graphic.py` planner prompt (narration "2.6 words per second" rule near line 655), `app/motion_graphic.py::_narrate` and the narration cap checks.
* **Steps:** parse requested seconds (Persian/Latin digits, "حدود", "seconds", "s"); add to planner prompt and trim narration to fit within ±15 %.
* **Tests:** parser variants; plan-fit unit.
* **Acceptance:** benchmark 5 within ±15 %.
* **Rollback:** revert.

## T6 — Reference workflow gap check (investigation)

* **Inspect:** `creative/reference.py`, `creative/schemas.py::ReferenceProfile`.
* **Deliverable:** a short markdown listing fields OpenMontage's workflow asks for that EditorGPT lacks; no code unless approved.

## T7 — Semantic retrieval benchmark (investigation, conditional)

* **Inspect:** `brain/asset_match.py::broll_match`, `engine/library.py`.
* **Deliverable:** labelled query set + recall@3 for tag baseline; implementation only if the gate in 08 is met.

Do not execute these tasks without explicit approval.
