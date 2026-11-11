# Creative Resource Registry — discovery and native EditPlan controls

## Architecture audit (2026-10-27)

This is an additive change, not a new editor or rendering backend. The actual
repository already has useful **partial catalogs**, but no shared creative
resource contract serving discovery, UI and tools together:

| Existing boundary | Evidence and decision |
| --- | --- |
| Web client | React 18 + TypeScript, Vite 5, relative authenticated `/api` calls; PWA build and private LAN proxy already present. Keep them. |
| Studio execution | `studio_orchestrator.py` (Lite), `agents/medium` (LangGraph), typed `studio_tools`, durable Studio events/store. Keep explicit mode selection and approval contracts. |
| Creative planning | `creative/director.py`, `script.py`, `capabilities.py` already separate briefs, concepts, script critique and tool capability descriptions. No additional agent runtime needed. |
| Motion | `engine/hyperframes/catalog_index.json` has 447 metadata entries pinned to CLI 0.8.161. `catalog_profiles.json` has 455 enriched profiles: not identical membership/version evidence. Index owns membership; matching profiles enrich metadata only. |
| HyperFrames execution | `registry_runtime.py` wires two specific external items; `motion_recipes.py` has 20 local recipes; builder/scenes have deterministic local implementations. Catalog membership does not imply a generic execution adapter. |
| Native editing | EditPlan, validated operations and `build_mlt.py` implement the legacy effects and four boundary transitions through **MLT**. Do not mislabel these as native FFmpeg xfade filters. |
| Rendering | Existing HyperFrames sparse/split-panel render, FFmpeg composition/audio, legacy Remotion rendering and browser export remain unchanged. No new Remotion Renderer dependency. |
| Jobs | Existing Celery/Redis where configured, thread fallback, job registry and Studio records are preserved. Discovery needs no queue. |
| Media and security | Existing upload ownership, media library and project documents remain untouched. New endpoints inherit app authentication. No paths, keys, user assets, downloads or executables enter the registry. |

## Implemented

`creative/resources/` normalizes committed metadata through provider adapters.
IDs are namespaced and stable (`hyperframes:…`, `editorgpt:…`,
`editorgpt-transition:…`, `editorgpt-recipe:…`). Legacy IDs are retained as references,
not rewritten in saved plans. This is an immutable, derived source index: no
additional database, no migration and no duplication of project storage.

Current snapshot: 594 entries (447 HyperFrames + 123 effects + four existing
transitions + 20 recipes). Of these, 445 are catalog-only, 144 are connected to
an existing context-specific pipeline, and five are explicitly unsupported.
"Connected" is **not** a new generic execution API, a license approval, a quality
certificate or a guarantee that the required runtime is installed on this host.

Manifests include provenance, engine, context, nullable capabilities, parameters,
usage/restraint hints, preview references, license status and unmeasured performance.
All new license approvals default false; RTL/alpha/vertical certification and
performance stay unknown until measured. Existing licenses and legal use of
existing pipelines are not changed by these discovery flags.

Authenticated, read-only API:

- `GET /creative-resources?q=kinetic&limit=12&offset=0`
- Filters: `engine`, `provider`, `kind`, `availability`.
- `GET /creative-resources/summary` (counts and content revision).
- `GET /creative-resources/hyperframes:data-chart` (exact resource).

Discovery is local and deterministic; there is no semantic-model request, network
call, package install, script execution, file mutation or AI usage. HTTP responses
use `Cache-Control: no-store`. Search limits are bounded. Preview URLs are restricted
to the known public HyperFrames CDN; clicking preview explicitly loads a native
video with `preload=none`, no autoplay. Imported preview is not proof of Persian QA.

`search_creative_resources` is available through the shared Studio tool contract
and Medium's read-only allowlist. It does not change agent mode or submit renders.
Lite's existing decision flow and prompts are unchanged; adding a shared tool
does not pretend Lite now independently searches it on every request.

My Effects adds one collapsed section using existing controls, pagination and
availability filters. Existing favorites, presets and editor selections remain
unchanged. No nonfunctional Apply/Render button is shown for catalog-only items.

The **Edit tab inside the Studio chat** now contains the collapsed effects/transitions
control for motion jobs using native EditPlan. There is no new Job plan page or
navigation out of the conversation. It loads the owned saved plan, selects a
segment, applies/replaces or removes its existing native effect, selects an adjacent
segment boundary and configures its native transition, then refreshes
the same Studio project. It blocks writes during active rendering and does not
start a render or change existing output files. Talking and Localize use different
plan schemas and do not receive these incompatible controls.

Typed `set_resource_effect`, `remove_effect` and `set_resource_transition` operations
reuse existing EditPlan validation, locks, history and Undo. Resource IDs must
resolve to native resources supported by that context. The owned
`GET /jobs/{id}/creative-resources` response includes the saved baseline and version;
writes use the existing operations endpoint with both. Stale baselines are rejected,
not silently retried. These checks do not claim transactional cross-process locking.
`creative/resources/instances.py` derives effect/transition instances and timing
from existing plans, without duplicating project storage. Transition parameter
validation is available at the operation layer and in the UI. The four existing
transition types are hard cut, crossfade, directional and zoom. Only parameters
consumed by the selected type are sent: frame duration, directional direction/
intensity or zoom mode/scale. Hard cut sets duration to zero; rendered transitions
require 2–30 frames. Invalid values block submission and are independently checked
by the backend. The UI discloses overlap shortening the output timeline. There are
still no arbitrary resource parameters or effect time-range controls.

### Chat Edit usability revision

- The motion.so card is visible only when the job has existing motion.so sessions;
  provider configuration or generic timeline support alone does not expose it.
  Empty inventories do not poll continuously. Active sessions are still polled,
  and project updates refresh the inventory.
- Checkbox targets select any subset or all segments/boundaries. Different effects
  may be staged on different clips; one save submits the complete operation batch
  through existing atomic validation/history. Removing an effect uses the same
  batch, not a separate save. Cancel makes no request. Failed/stale submissions
  preserve the draft and never auto-retry writes.
- A compact visual gallery replaces the large effect/segment dropdowns. Native
  motion/light names are translated, search supports those names, and exact
  transition controls are behind progressive disclosure. Samples are **schematic
  CSS demonstrations**, not rendered source footage or proof of exact native
  output. Reduced-motion is respected and previews fetch no private media. There
  is no per-project rendered effect-preview service in this revision.
- The Motion ProjectDocument now includes individual effect elements on an effect
  track and transition elements with native parameters on their own labelled row.
  Their timing uses the renderer's segment placement with overlap. The timeline
  translates names and displays matching track icons; short projects fit at a
  more usable initial zoom. Hard cuts have zero duration and are not invented as
  timed visual effects.
- Shared EditCard headers use RTL layout, related design-system icons and the
  same chevron/spacing for all existing engine settings. Advanced-editor links
  follow that direction too. The resource editor remains mounted while switching
  between Edit views, preserving its pending draft without falsely showing it as
  saved timeline content.

### Compact workspace header

On mobile, Preview and Edit both use the existing shell's top-bar fullscreen
action instead of the new-chat pencil. The duplicate Preview/header strip is
hidden; the project title/status row is removed from both workspace views at all
sizes. Status uses a 7px theme-coloured dot with an accessible label, no visible
copy. Desktop keeps its functional view tabs and puts the dot in that header.
Multiple-project selection remains available. The last mobile tab survives native
fullscreen's transient breakpoint changes, including the delayed exit resize.
Verified entering/exiting fullscreen in the actual QA browser and returning to
Preview rather than unexpectedly opening Chat. `workspace-topbar.test.mjs` tests
both tabs, status changes, fullscreen state and multi-project/desktop controls.
No iOS hardware test is claimed.

## Running and rollback

Run the normal backend/frontend after loading these sources. Backend restart is
required for new API/tool registration; don't interrupt active renders just to
activate discovery. Frontend HMR alone cannot register backend routes. No online
deployment or running-worker restart is performed by this increment.

Rollback: revert this increment and restart at an idle boundary. No project,
timeline or database migration needs reversal. The earlier Lite/Medium branch
remains in history. Catalog caches are process-local; a restart rebuilds them.

## Next increments and acceptance gates

1. Add pinned source/license receipts and audited per-item installation. Reconcile
   catalog versions before refresh; never install arbitrary client-supplied commands.
2. Extend the derived instances and typed native operations to the remaining
   contexts and connect reorder/preview through existing project operations.
   Do not graft Python effects on top of final burned-in captions.
3. Discover actual FFmpeg build/filter support; implement frame-accurate xfade
   composition before advertising its transitions as executable.
4. Benchmark native HyperFrames exemplars and the three Python VFX pilots with
   Persian mixed text, shared face/mask analysis cache and audio continuity.
5. Add on-demand skill discovery/reading and a visual beat plan above existing
   tools. Don't load all skills into every prompt or add automatic agent switching.
6. Integrate bounded, evidence-based pre/post QA, segment invalidation and render
   receipts. Black frames or intentional pinned titles alone are not style errors.

Still not implemented: arbitrary catalog execution, parameter editing in timeline,
external-code sandbox/install pipeline, new Python VFX, Lottie/GL ports, broader
asset sourcing, automated Remotion porting, new QA or performance claims. No live
provider, media generation, hardware iOS or production render tests were run.

## Verification record

- Backend: 119 passing tests across `test_creative_resources.py`, `test_resource_operations.py`,
  `test_studio_agents.py`, `test_hyperframes_cli.py`, `test_motion_pipeline.py`
  `test_script_engine.py`, `test_document_engines.py`, `test_project_document.py`
  and `test_motion_so.py`.
- Frontend: thirteen passing DOM tests across `creative-resources.test.mjs`,
  `resource-effect-editor.test.mjs`, `studio-creative-resources.test.mjs` and
  `agent-mode.test.mjs`, `edit-card-motion.test.mjs`, `workspace-topbar.test.mjs`; discovery, multi-target
  batching, distinct per-clip effects, a single double-click-protected save,
  draft preservation, explicit retry, engine/usage gating, shared RTL/icon
  design and Studio refresh. Backend tests validate parameter bounds.
- TypeScript: `tsc --noEmit` passed.
- Production frontend: `npm run build` passed (existing large-chunk warning).
- Real browser: separate Vite on loopback 5191 and full FastAPI on loopback 8021,
  with an empty temporary `JOBS_DIR`, no Redis and no database. Verified opening
  the gallery and the actual search request/200 response for `kinetic typography`.
  The registry displayed 594 entries. These were not mocked API responses.
- A generated three-second test source was probed through the existing backend.
  Native operations, saved history, dry run, stale rejection and Undo were tested.
  In the real mobile-width browser, the same temporary job was attached through
  `/studio/legacy/open`; its Chat → Edit tab successfully saved Slow Pull · Neutral
  on segment `a`. This did not render or consume an AI service. Screenshot:
  `/tmp/editorgpt-chat-edit-resources.png`.
- The same chat's Edit control saved an eight-frame zoom-out transition with
  scale 1.2 between `a` and `b`, using the real authenticated operations endpoint.
  API integration tests separately verified persistence and derived instance
  retrieval. No full MLT render or visual quality certification is claimed.
- Browser revision: saved three effects and two boundary transitions in one real
  API request in that same temporary chat. Verified all five timeline elements,
  hidden unused motion.so card, and pending-draft preservation across Edit view
  changes (then cancelled that unsaved test draft). Evidence:
  `/tmp/editorgpt-unified-edit-gallery.png`, `/tmp/editorgpt-unified-edit-timeline.png`.
- Existing `/style/plan-selection` returned 500 in that empty-data QA installation;
  the legacy page displayed its existing generic effects error independently of
  the working registry. This unrelated endpoint was not changed or represented as
  regression-free. No existing project state was used to hide that failure.

Changed files: `creative/resources/{__init__,models,providers,registry}.py`,
`app/routers/creative_resources.py`, `app/main.py`, `app/studio_tools.py`,
`app/agents/medium/tools.py`, `engine/hyperframes/registry_runtime.py`,
`web/src/api.ts`, `web/src/MyEffects.tsx`, `tests/test_creative_resources.py`,
`web/tests/creative-resources.test.mjs`, `.gitignore`, and this document.
Additional files: `creative/resources/instances.py`, `engine/operations.py`,
`app/jobs.py`, `app/routers/plans.py`, `tests/test_resource_operations.py`,
`web/src/ResourceEffectEditor.tsx`, `web/src/studio/CreativeResources.tsx`,
`web/src/studio/Workspace.tsx`, `web/tests/resource-effect-editor.test.mjs`,
`web/tests/studio-creative-resources.test.mjs`.
Usability revision also modifies `app/project_document.py`,
`web/src/studio/{EditCard,MotionScenes,TimelineView,timeline}.tsx` (`timeline.ts`
is the helper file), `web/src/styles/studio.css`, and adds
`web/tests/edit-card-motion.test.mjs`.

## Library completion and integration (2026-11-12)

Scope: complete and use the existing Registry, no new engine, registry, agent or UI. Everything below was verified against the running code and the live registry
(776 resources on the production image), not against earlier documents.

### 1. Registry inventory (production, `creative/resources/registry.py`)

| Type | Availability | Engine | Count |
| --- | --- | --- | --- |
| block (HyperFrames registry) | catalog-only (`adapter-required`) | hyperframes | 210 |
| component (HyperFrames registry) | catalog-only (`adapter-required`) | hyperframes | 190 |
| skill | existing-pipeline (offered to the planner / readable by agents) | skill | 124 |
| effect (MLT) | existing-pipeline | mlt | 118 |
| component | existing-pipeline (the panel library, assets/hyperframes_components) | hyperframes | 52 |
| face-effect | existing-pipeline | ffmpeg | 42 |
| motion-preset (recipes) | existing-pipeline | hyperframes | 20 |
| skill | catalog-only (needs a runtime or is agent-reference only) | skill | 8 |
| transition (MLT) | existing-pipeline | mlt | 4 |
| effect (MLT) | unsupported | mlt | 5 |
| motion-reference | catalog-only | hyperframes | 3 |

Licences: 168 MIT, 8 Apache-2.0, 6 AGPL-3.0 (OpenMontage skills, owner-accepted 2026-11-11, isolated in `vendor/motion-skills/openmontage/`), 594 without a declared type
(the HyperFrames catalog entries: provenance is the pinned registry, not a licence file). No resource is marked `verified` or `commercial_use_approved`; that stays the owner's decision.
Searches that find nothing: `.mogrt`, Locomotion. Lottie: 2 skills + 1 catalog block, no runtime. GL transitions: 15 catalog-only components + 2 executable.

### 2. Repository integration matrix (licences read from the GitHub API and the LICENSE files, 2026-11-12)

| # | Repository | Licence | Status before | Decision | Now |
| --- | --- | --- | --- | --- | --- |
| 1 | lemomo-ai/lemo-opuscar | MIT | missing | C Director skill (+ E reference for its canvas/WebGL film code) | **67 skills** (`lemo:<style>` + `lemo:director-method`): a digest of each STYLE.md for the scene designers, the full text as a reference file; planner offered only the best matches (retrieval). Executable as design language: verified in a render, see §5 |
| 2 | kajisho5/ffmpeg-skill | MIT | missing | E reference (agent know-how); its 42 Python tools overlap our FFmpeg/MLT code and are not copied | **1 skill** `ffmpegskill:ffmpeg-skill` (workflow digest + gotchas, workflow, timestamps, flags, process-pitfalls). Catalog-only: never offered to the motion planner, readable by agents |
| 3 | OpenMontageInc/OpenMontage (moved from calesthio) | AGPL-3.0 | audited 2026-11-11 | C Director skill (owner chose direct use) | 6 skills + `plan_checks` ideas (clean-room), `DELIVERY_PROMISE`; talking/product agents read them |
| 4 | blixvip/MotionClone | none (repository does not exist) | n/a | F skip | `codename-zen/motionclone` (MIT) stays catalog-only: needs the motionclone CLI |
| 5 | iart-ai/motion-skills (19 pack repos) | MIT | integrated | C | 35 skills |
| 6 | charlie947/motion-graphics-skills | MIT | integrated | C | 15 skills |
| 7 | bangtutorial/bang-motion | MIT | integrated | C | 1 skill (+ distilled anti-slide rules in the designer prompt) |
| 8 | Barty-Bart/motion-graphics | MIT (GitHub shows NOASSERTION; the LICENSE file is the MIT text) | integrated | C | 6 skills (two catalog-only: they need SAM 2 / a measuring script) |
| 9 | hughminhphan/motion-kit | MIT | integrated | B engine enhancement | skill + `motion-kit.js` loaded as `MotionKit` |
| 10 | nexu-io/open-design | Apache-2.0 | distilled | C/E | its motion-design craft rules live in the designer prompt; the 100k-star workspace itself is a competing agent UI: reference only |
| 11 | 0xsline/OpenChatCut | AGPL-3.0 | missing | E reference | overlaps the Studio orchestrator; AGPL was accepted only for the OpenMontage skill text: **not integrated**, needs an explicit decision |
| 12 | hypit-ai/hypit | NOASSERTION (restrictive commercial SaaS terms) | missing | F skip | not cloned, not read, no code or ideas derived |
| 13 | Autom8AI/Open-Higgsfield-AI | none | missing | E reference-only | no licence: nothing may be copied |

### 3. What was implemented (all behind existing seams, all reversible)

- **Skills** (`creative/skills_library.py`, `vendor/motion-skills/`): `lemo`, `openmontage` and `ffmpegskill` namespaces added by re-runnable scripts that touch only their own namespace
  (`scripts/vendor_lemo_styles.py`, `vendor_openmontage_skills.py`, `vendor_ffmpeg_skill.py`, each with `--remove`). **Targeted retrieval**: the planner is offered the 36 skills that fit the brief
  (keyword scoring with Persian to English synonyms, plus a core set), never the whole library (133 skills). Per-skill body length (`body_chars`), per-skill licence in the designer text and in `read_creative_skill`.
- **Agents**: the EditorGPT/orchestrator agent can read skills (`read_creative_skill`); the Instagram agent has `/api/hermes/content-tools/skills/{search,read}` (read-only).
- **Art-director pass** (`creative/design_critic.py`): a vision model scores every scene's still on hierarchy, phone legibility, density, polish and meaning; the weakest are redesigned from its concrete fixes
  (a poor ready-made component, score <= 4, is replaced by a scene designed for the film); a redesign is kept only if the same eye scores it higher. Used by the motion-graphic engine, the product reel and the talking 5 panels. `DESIGN_CRITIC=0` turns it off.
- **Talking 5 panels**: the curated panel library (48 HyperFrames components, 37 usable) is used first and the Motion Designer only where nothing fits (`TALKING5_PANELS=library|mixed|authored`).
  Two real defects were found and fixed by rendering every component with Persian content: components animated out after their own 3-5 s envelope and left a long panel EMPTY (now fitted to the panel's length; components that cannot stretch are only given to short panels,
  measured in `creative/panel_hold.json`), and a CDN `<script>` that a network-less render worker cannot load (removed; the page's GSAP is used).
- **Music director for the product reel and talking 5** (`creative/audio/film_music.py`): chosen/fitted track, beats for scene designers, sound effects, loudness mastering.
- **Cloud render reliability**: a worker that does not report within `RENDER_CLOUD_STARTUP_SECONDS` (300) is given up on, its pod deleted and the render continues on the server; after two such timeouts in 45 minutes the next renders skip the cloud (circuit breaker). Deploys refuse while a cloud or talking render is in flight.
- **Talking chats now have a step log** (`talking_notes.json`) with the panel previews before the render.

### 4. Not done (and why)

- 400 HyperFrames registry items (210 blocks, 190 components) remain `catalog-only`: each needs an adapter (variable mapping, Persian check, measured hold time) before it may be called executable. The panel library (48) shows the route and the two traps (envelope length, CDN script).
- No Lottie runtime, GL-transition port, `.aep`/`.mogrt` importer: none of these exist in the registry as executable resources and none was claimed.
- Lemo's films are tuned for Latin text and for Opus; their rules were taken as a design language, not as a Persian typography reference.
- OpenChatCut, Hypit, Open Higgsfield: see the matrix.
