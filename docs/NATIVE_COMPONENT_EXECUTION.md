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
| HyperFrames vendored components | 45 HTML files, manifest + Apache-2.0 notice | 45 bounded portrait adapters execute pinned original code; sampled browser checks pass |
| HyperFrames registry catalog | Metadata index and profiles | Existing talking_2 context adapters remain unchanged; catalog is not execution |
| EditorGPT effects/transitions | Existing MLT implementations | Already executable via EditPlan; not interchangeable with HTML components |
| EditorGPT motion recipes | Existing recipe adapters | Already connected in talking_2, not generic motion-graphic templates |
| Shotcraft | Eight pinned recipes, ten TSX demos and five original shared fixtures | Ten original-code Remotion stills verified. Production remains reference-guided: typed user-content binding and format adaptation pending |
| Claude Video Effects | Existing 42 implementations in engine/face_effects | Existing talking-reel execution preserved, all 42 exposed in shared registry; synthetic-frame previews, not video-tracker certification |
| Lemo Opuscar | Pinned Swiss Canvas source, score, MIT license, local OFL fonts | Original demo executed, backward seek pixel equality checked. Fixed demo story is NOT an editable production template; remaining styles pending |

## Adapter parameters (portrait; encoded-output certification pending)

Example ScenePlan field:

```json
{"native_component":{"resource_id":"hyperframes:headline-slam","text":"یک شروع متفاوت","accent":"blue"}}
```

`cta-close` additionally accepts `button_label`. Text is bounded, escaped as data,
and whole-word spans preserve Persian joining characters. Unknown resource IDs,
unknown parameter fields, altered source hashes, output path escapes and
unapproved script dependencies fail closed. No arbitrary paths or JS are accepted.

These initial three are title/CTA/stat components, **not** substitutes for explanatory visuals.
The shared motion planner now receives their executable catalog separately from
Shotcraft references. It may choose them only for their stated role. Count-up
requires factual user/source numbers, not invented statistics. Non-portrait plans
are rejected if they select these adapters. Integrity receipts say
`render_verified: false`; successful materialization is not a successful render.

Native failures must not enter legacy plain-title isolation/replacement. Existing
legacy fallback behavior is preserved for old generated scenes only.

## Verification so far

Update, 2026-10-30:

- 45/45 local HyperFrames sources checked with the existing pinned 0.8.161 runtime
  at 0.5, 1, 2 and 3 seconds. No remaining reported lint/runtime/layout/contrast
  errors for those demonstration inputs. This is sampled browser evidence only.
- Generic adapters use each source's actual typed parameter schema. All content
  parameters must be explicitly supplied in production: English demo defaults must
  not silently enter a user's video. Unknown fields, HTML content, invalid enum
  values, non-finite numbers and altered source hashes fail closed.
- Fixed a real ID isolation regression: namespacing must not change a CSS class
  with the same spelling as an ID. Repeated IDs, marker-generated row references,
  local font dependencies and color-token collisions are covered.
- 42 Claude effects execute their existing compositor on a synthetic fixture;
  no new face effect implementation or competing execution backend was created.
- Ten Shotcraft original TSX stills execute through existing Remotion packages.
  Their original demo branding and fictional statistics are retained only in the
  clearly labelled public demonstration gallery, never certified as user content.
- Swiss Lemo demo uses original Canvas code and local licensed fonts. Seeking
  12 → 27 → 32 → 12 seconds produced identical pixels for both 12-second captures.
- 110 focused automated tests passed before additional gallery regression tests.
  See test output for the latest count. Two existing deprecation warnings remain.
- No production deployment, paid provider request or full MP4 certification in
  this update. The local static gallery is not proof that the running API reloaded.

### Persistent visual gallery

Open `/creative-previews/gallery.html` on the application's frontend. The Media
Library has a link to it. Every item has an individually stored PNG plus its
source revision, actual verification class, compatibility and limitations. Search
works on mobile. Files live in `web/public/creative-previews/`; none contain user
media, credentials or private project data.

Reproduce offline/source verification:

```sh
python -m pytest tests/test_component_gallery.py tests/test_native_motion.py tests/test_creative_resources.py
python scripts/build_component_gallery.py --work NEW_DIRECTORY --gsap EXISTING_GSAP --cli PINNED_CLI
python scripts/build_face_effect_gallery.py
node remotion/shotcraft-gallery.mjs
node scripts/build_lemo_gallery.mjs
```

The last two are isolated demo audits, not production job entrypoints. Browser
installation and the existing Node dependencies must be available. Gallery
generation never changes the execution allowlist automatically.

Earlier incremental verification (retained for audit):

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
