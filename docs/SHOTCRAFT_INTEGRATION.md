# Shotcraft explainer references

Source: https://github.com/Vincentwei1021/video-shotcraft

Pinned revision: `5a2e98daade313c4f376120f38427eb19a108e8c`.
Upstream Apache-2.0 license and unchanged reference files are retained in
`creative/shotcraft_data`. No upstream executable code is imported or run.

## Actual integration

The existing motion planner receives eight named explanatory mechanisms from
`creative.shotcraft.catalog()`. A scene can select an exact `shotcraft_id`.
Its authoring request receives that card's complete recipe and matching TSX
demo sources, verified against the committed SHA-256 manifest. The author
adapts the mechanism to EditorGPT's existing HM/GSAP renderer and shared
design direction. Each resulting page records reference/revision receipts.
No provider selection, rendering backend, UI, or authentication is replaced.

Included cards: bezier-source-converge-merge, text-column-converge, card-stack,
title-demote-to-label, card-flip-reveal, before-after-slider-scrub,
chart-live-moves, circle-match-iris.

These are **reference-guided authoring**, not certified native Remotion ports.
The existing resource registry marks them `port-required` / `catalog-only`.
Selection does not guarantee a faithful rendering or professional quality.
The remaining upstream gallery is installed as a local Codex skill, not
advertised as supported EditorGPT runtime components.

## Timing reliability

New scene drafts use local time starting at zero. `HM._scene` adds the global
offset once and rejects invalid local positions, unbounded repeats and tweens
extending beyond the scene window. Existing saved drafts retain absolute-time
behavior. `HM.rise` explicitly reveals opacity; `HM.pop.from` must be a numeric
scale. Approved handoffs no longer silently discard the seventh scene; more
than eight scenes or excessive total duration produce an explicit error.

## Updating and deploying

Install the pinned upstream skill locally, then run:

```sh
python scripts/vendor_shotcraft.py /absolute/path/to/video-shotcraft
python -m pytest tests/test_motion_design_reliability.py tests/test_motion_repair.py tests/test_creative_resources.py -q
```

Review upstream changes and license before changing the revision, catalog and
hash manifest together. The normal application image already copies
`creative/`, so no network download or extra service is needed at runtime.
Use the normal release process; this change does not deploy or restart servers.
Existing drafts are not migrated or automatically regenerated. New planning
cache keys prevent reusing old timing drafts for newly authored work.

Rollback with the normal previous application image. The new fields have
defaults, and this change does not require a database migration. Keep original
media and existing outputs. Browser-rendered visual and voice quality review
is still required before approving a production film; automated tests are not
a substitute for that review.
