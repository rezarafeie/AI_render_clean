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
| Shotcraft | Eight pinned recipes, ten TSX demos and five original shared fixtures | Two bounded native adapters (source convergence and text-column convergence) execute user content through existing Remotion → HyperFrames; eight other demos remain reference-only |
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
- 130 focused automated tests passed, including frozen gallery and dependency
  integrity, required content, chart label consistency and Persian splitting.
  Two existing deprecation warnings remain.
- Production validates complete content during planning and before scene
  execution. Incomplete row lists cannot fall back to English "Beat"/"Guest"
  labels. The task-surround adapter binds explicit task labels instead of the
  upstream demo's fixed English tasks. Its corrected Persian example passed the
  same browser checks and its retained image was replaced.
- A complete second pass supplied explicit Persian content for all 45 sources.
  All 45 now pass sampled browser checks with those inputs. Persian fixtures are
  in `scripts/component_examples.py`, separated from production defaults; their
  numerical values are explicitly synthetic. Do not reuse them as user facts.
- Notes typing now reveals whole Persian words, preserving joins and the original
  timing/caret mechanism. The 12-second example is sampled at 0.5, 3, 7 and 11s.
- Persian text selection uses spaced whole-word boxes. Both normal/bold geometry
  are measured once after fonts load; timeline callbacks no longer measure DOM.
  The original layout-measurement warning was removed by fixing the measurement,
  not by suppressing a check. The composition-size warning remains.
- All ten Shotcraft demos additionally passed first/middle/final/repeated-frame
  checks. A transient repeat-frame failure prompted an explicit font/CSS SVG
  decode fence; the full suite then passed again. This verifies sampled fresh-page
  frame repeatability, NOT same-page backward seeking or encoded-video playback.
- Frontend build passes; existing bundle-size warnings remain. Mobile-sized
  Chrome loaded all 98 gallery entries, filtered correctly and decoded images
  without page errors. React review keeps the gallery entry separate from the
  production bundle and its readiness wrappers outside render functions.
- Shared native instructions are emitted once, not once per entry. The measured
  minimal planning request decreased from 76,203 to 47,279 characters while
  preserving all 45 IDs, parameter descriptions/types, bounds and enum options.
  No live AI request was used to claim a latency improvement.
- Auditing static HTML found supporting demo claims absent from upstream schemas
  (including Retention 94% and Teams 48). Adapter-owned typed slots now cover
  those labels, focus/workspace/community kickers, match-cut captions, station
  labels, tracing-step kickers and timing labels. They are required explicitly in
  production, may be deliberately empty, and bind via text nodes. Synthetic
  Persian examples passed browser checks again after those changes.
- Source helper limits are validated in advance: approved copy cannot silently
  truncate or fall back to English. Adapter receipts include source hash, adapter
  hash/version and materialized HTML hash. QA scripts fail nonzero on failed
  checks, while retaining evidence and distinguishing failures from passes.
- No production deployment, paid provider request or full MP4 certification in
  this update. The local static gallery is not proof that the running API reloaded.

### Persistent visual gallery

#### Text-column integration (2026-10-31)

`shotcraft:text-column-converge` has a separate discriminated input model, not a
bag of optional parameters: `caption`, `prefix`, two to six unique `features`,
`subtitle`, `locale`. Caption must equal the approved scene headline. All copy is
plain bounded text; Persian ZWNJ is preserved. It is **horizontal only**. Backend
planning, authoring, saved mounts and renderer all reject other formats.

The exact pinned original TSX executes through a fixed webpack alias and a
source-specific binding loader. Opposing edges stay fixed while phrases rotate;
there is one 36-frame cubic convergence after a 10-frame final-phrase delay, then
an 18-frame subtitle delay and 4-frame reveal. Per-phrase reading time and a final
hold are budgeted before execution. Demo branding/copy is replaced explicitly.
The adapter intentionally changes the original 42px specification typography to
72px main / 48px supporting copy for readability, and uses shaped local-font
measurement rather than a monospace character-count approximation. Oversized
copy fails; it is not clipped or silently shrunk. Persian reverses the physical
opposing edges while retaining whole shaped phrases.

Independent review caught a black first frame in the hybrid assembly. Native
scenes retain hidden pre-runtime CSS for the static contract and use instantaneous
timed visibility sets, instead of a 0.001s opacity tween that was zero on frame zero.
Existing generated-scene transitions are unchanged.

An all-frame regression also reproduced intermittent missing foreground layers
in the convergence component under the default local Chromium capture profile.
Raster-mode changes and an added paint wait did not resolve it and were reverted.
The isolated native v3 renderer now uses one capture worker with supported
`swangle` software GL. This is slower than the previous local GPU profile; native
clips remain bounded to 4–12s / 600s execution. It does not change existing v1/v2
jobs, AI modes, models or providers. See the official [Remotion GL options](https://www.remotion.dev/docs/options/gl).

The one-job Node process logs completed encoding/cleanup and gets a one-second
successful-shutdown grace bound after `renderMedia` resolves and owned temporary
files are removed. SDK failures still exit nonzero. This prevents idle SDK handles
from holding a completed isolated CLI alive until the Python deadline; it never
terminates the API or another job.

`creative/native_video_checks.py` is reused by production `write_project` and the
gallery builder. Before referencing a native artifact, production decodes its
entire bounded sequence and rejects missing foreground or an unexpected frame
count. This is specific to these two fixed light/dark designs, not universal
quality grading. Foreground presence, not a minimum text area, is checked so a
short valid phrase is not mistaken for an empty frame. Gallery publication additionally checks the actual hybrid's
opening frame, not merely the standalone child or DOM boxes. Synthetic preview
data and real production defaults remain separate.

Rollback: stop submitting new native jobs, then revert the integration commit as
a unit and restart only idle owned workers. Preserve completed MP4s/project data;
do not run destructive Git resets or delete persisted outputs. Existing saved
projects using the new `shotcraft_component` require its adapter to regenerate;
older projects and existing rendered MP4s do not need migration. No database,
provider or account configuration is changed by this integration.

Final local verification for this stage: 203 applicable tests pass (two existing
deprecation warnings); frontend build passes (existing large-bundle warnings).
Both six-second native MP4s pass complete 180-frame checks. Both nine-second
hybrids pass actual browser/static checks and an encoded-opening-frame gate.
Independent sampled-pixel follow-up confirms text hybrid frame zero and the
previously empty convergence frames 153/159 are now visible. Motion analysis in
the HyperFrames browser check remains disabled; no audio or full-film aesthetic
certification is inferred. Mobile Chrome at 390×844 loads 100 gallery entries
without page errors or horizontal overflow; neither native MP4 is requested
before a play gesture. No production deployment or API restart was performed.

Native Shotcraft update: `shotcraft:bezier-source-converge-merge` now accepts
explicit approved caption, exactly four allowlisted source icons, output icon,
accent and locale through `ScenePlan.shotcraft_component`. The original source
is hash-verified, not rewritten by a model. Existing Remotion renders a bounded
4–12-second child artifact; HyperFrames mounts it as framework-owned video.
No arbitrary script, path, URL or agent-authored video markup is admitted.
Failures do not silently substitute a title. Receipts and cache keys bind source,
adapter, content, duration and dimensions; corrupt artifacts are not reused.

A real six-second Persian portrait child and nine-second mixed HyperFrames film
were encoded. The child is H.264/yuv420p/BT.709 with maximum one-second keyframe
interval. Sampled browser checks passed; automatic motion analysis was disabled.
Landscape/square are not visually certified. Only this one Shotcraft component
is production-bound; other recipes and Lemo's fixed demo are not upgraded by this
result. The gallery now retains 99 entries including this actual MP4, loaded only
after a user's play gesture. Existing audio generation remains unchanged.

Focused regression suite: 182 passed before the additional frozen native-gallery
test; two existing deprecation warnings. No paid provider call, production deploy
or running API restart was performed. Existing versions 1/2 Remotion contracts
are regression-tested; only native version 3 uses the added binding adapter.

Follow-up opening-frame gate: inspecting the encoded first frame exposed empty
pre-roll in the original convergence source, which middle-frame browser checks
had missed. The adapter trims its empty 0–0.2 normalized phase, retaining the
original convergence/pan/erase and final reading hold. A fresh child and nine-
second hybrid were encoded; browser samples now include 0 and 0.1 seconds.
All 180 decoded child frames pass a fixture-specific light-background foreground
gate at 288×512 (minimum 28 dark pixels; threshold 12), while the old encoded
fixture fails at frame zero. This is not a universal visual-quality classifier.
Black and white middle-frame rejection is unit-tested, rather than checking only
the first frame. The frozen gallery MP4, PNG and source/adapter hashes were updated.

Open `/creative-previews/gallery.html` on the application's frontend. The Media
Library has a link to it. Every item has an individually stored PNG plus its
source revision, actual verification class, compatibility and limitations. Search
works on mobile. Files live in `web/public/creative-previews/`; none contain user
media, credentials or private project data.

Reproduce offline/source verification:

```sh
python -m pytest tests/test_component_gallery.py tests/test_native_motion.py tests/test_creative_resources.py
python scripts/build_component_gallery.py --work NEW_DIRECTORY --gsap EXISTING_GSAP --cli PINNED_CLI --persian
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
# Card-flip adapter preparation (not enabled)

`creative/shotcraft_card_flip.py` and `remotion/shotcraft-card-loader.cjs` now
define and bind explicit three-card content into the pinned upstream TSX.
They are deliberately **not** registered in `NativeSpec`, the renderer allowlist,
or the planner catalog yet. Existing completed capability counts are unchanged.

All copy and before/after numbers are required inputs; no demonstration claims
are production defaults. Bars use the actual numeric ratio, including zero/zero.
The required evidence string records a reference, not independently verified
truth. Existing user approval remains required by the surrounding workflow.
Front copy is an abstract three-line feature summary, not a claimed screenshot
of an actual product UI. The original perspective, flip curve, spring, staggering,
lighting, reflections and contact shadows are retained. Front reading time and
result hold are bounded from explicit copy. Negative Persian letter spacing and
fixed English demo copy are removed.

Preparation tests cover Python validation, source binding, unchanged vendor
bytes, preserved motion constants, zero comparisons, changed-source rejection,
insufficient reading holds and TypeScript transpilation. These tests do **not**
certify text fit, RTL geometry, encoded frames, audio or production availability.
Before promotion: add shaped-font geometry limits, complete an actual native and
hybrid render audit, review sampled front/flip/back frames independently, retain
the approved visual in the gallery, and only then expose the typed catalog entry.
