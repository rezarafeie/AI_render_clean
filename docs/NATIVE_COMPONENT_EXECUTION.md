# Native component execution migration

## Contract

Catalog presence, source availability, executable adapter and visual certification
are separate facts. Never mark an item native merely because its HTML/TSX exists.
Existing provider/context permissions are unchanged by this migration.

`ScenePlan.native_component` selects a bounded adapter. `author_scene` returns its
typed reference without an LLM call. `assemble_scenes` mounts a timed, uniquely
named subcomposition. `write_project` verifies the vendored SHA-256, binds
script-safe data, supplies existing local GSAP/fonts and copies upstream notices.
The original component's animation code executes inside the existing HyperFrames
renderer. No additional service or rendering backend is introduced.

Both Studio modes share this pipeline. Agent selection and model configuration do
not change. Existing plans default to generated authoring as before.

## Current inventory / migration ledger

| Source | Actual local source | Execution status |
| --- | --- | --- |
| HyperFrames vendored components | 45 HTML files, manifest + Apache-2.0 notice | Three bounded portrait motion adapters: headline-slam, cta-close, count-up |
| HyperFrames registry catalog | Metadata index and profiles | Existing talking_2 context adapters remain unchanged; catalog is not execution |
| EditorGPT effects/transitions | Existing MLT implementations | Already executable via EditPlan; not interchangeable with HTML components |
| EditorGPT motion recipes | Existing recipe adapters | Already connected in talking_2, not generic motion-graphic templates |
| Shotcraft | Eight pinned recipe/TSX references | Reference-guided authoring; native Remotion execution/ports pending |
| Claude Video Effects | No matching executable vendor tree identified in this checkout | Locate installed server source, audit licenses/runtime and map individual items before enabling |
| Lemo Opuscar | External upstream reviewed, not vendored in this checkout | Swiss pack / other styles pending; do not advertise 66 executable templates |

## Initial adapters (portrait; encoded-output certification pending)

Example ScenePlan field:

```json
{"native_component":{"resource_id":"hyperframes:headline-slam","text":"یک شروع متفاوت","accent":"blue"}}
```

`cta-close` additionally accepts `button_label`. Text is bounded, escaped as data,
and whole-word spans preserve Persian joining characters. Unknown resource IDs,
unknown parameter fields, altered source hashes, output path escapes and
unapproved script dependencies fail closed. No arbitrary paths or JS are accepted.

These are title/CTA/stat components, **not** substitutes for explanatory visuals.
The shared motion planner now receives their executable catalog separately from
Shotcraft references. It may choose them only for their stated role. Count-up
requires factual user/source numbers, not invented statistics. Non-portrait plans
are rejected if they select these adapters. Integrity receipts say
`render_verified: false`; successful materialization is not a successful render.

Native failures must not enter legacy plain-title isolation/replacement. Existing
legacy fallback behavior is preserved for old generated scenes only.

## Verification so far

- 62 automated tests passed (native adapter, existing motion reliability, repair,
  creative resource registry); two pre-existing deprecation warnings.
- Real HyperFrames 0.8.161 browser check on one Persian portrait headline:
  browser ran with Apple M1 hardware GPU; zero runtime/layout/contrast errors,
  eight contrast checks passed. Initial missing host-ID warning corrected in code.
- Not yet certified: out-of-order seeks, long Persian copy, landscape/square,
  encoded output, mobile preview.
- A second real browser check mounted headline + CTA together in portrait:
  zero lint/runtime/layout/contrast findings at 0.5, 2, 4.5 and 6 seconds;
  13 contrast checks passed. CTA snapshot was inspected. Its enum color collided
  with the runtime CSS-variable defaults; adapter palette tokens now explicitly
  bind to color values.
- Third browser check: four scenes with repeated headline component, Persian
  count-up and CTA. Zero lint/runtime/layout/contrast findings across eight seek
  timestamps; all 14 sampled contrast checks passed. Persian ۳۲۰ نفر and blue CTA
  snapshots inspected after the palette fix. This is not an encoded MP4 test.
- Reproduce with `scripts/verify_native_motion.py NEW_DIRECTORY --gsap EXISTING_GSAP`
  and the installed pinned HyperFrames check/snapshot commands. The fixture uses
  no model, provider request, service or paid media generation.
- No production deployment, provider requests or paid media generation performed.
  Planner discovery is wired in source; no live AI planning request was run.

## Next acceptance gates, per item

1. Pin complete code and license; enumerate dependency and asset restrictions.
2. Validate parameters and match the actual existing renderer contract.
3. Execute original code (or explicitly named/versioned native port), not an LLM
   reconstruction. Record source and adapter hashes.
4. Test repeated instances, short/long durations, first/last frame, backward and
   random seeks, RTL and every advertised aspect ratio.
5. Inspect snapshots and decoded output; only then expose through resource
   selection and planner with truthful compatibility constraints.
6. Keep unsupported items discoverable but non-executable, with a specific reason.
