# Manual editor

`/panel` loads the editor on demand. `/panel/:conversationId` opens an existing
Studio conversation and its project records. Panel drafts use the same
authenticated attachments and Studio repository. Creating or cutting a clip
does not send a user message to the Studio orchestrator. The optional assistant
uses that conversation's existing agent and credit accounting. Panel workflow and explicit agent selections persist separately in the project’s owned Studio storage. Visiting the chat still uses its own preference until a user sends an assisted action.

The application registers one router and one lazy client route. Rendering,
the existing renderer selection policy, agent dispatch, Studio chat, and the
underlying project formats stay on their existing code paths. The panel has no
new worker or database and does not install a new render engine.

## Capability inventory

The following describes the implementation found in the repository and the
controls reachable from the panel. “Ready” identifies an existing code path.
Provider-dependent status still needs verification in the target environment.
“Requires configuration” covers an installed path whose availability depends
on service credentials, worker binaries, or a compatible project. Library
entries keep each registry's own availability values.

| Capability | Status | Source, supported input → result, and panel access |
| --- | --- | --- |
| Talking Reel | Ready / requires configuration | `app/studio_tools.py` → `app/talking_reel.py` → `engine/talking_styles/`. An owned video, optional style ID and analysis settings yield a reviewable plan and approved render. Talking 4 is deprecated for new work but loads for existing jobs. ASR and AI planning consume configured credits. |
| Dubbing and localization | Requires configuration | `app/localize.py`, `app/routers/localize.py`, `studio/LocalizeEdit.tsx`. An owned original video yields translated lines, voice selection, overlays and MP4 after explicit rendering. An ASR, translation and voice provider must be available. |
| Native clip editing | Ready | `app/jobs.py`, `engine/schema.py`, `engine/operations.py`. An owned video seeds a real EditPlan. Set source/vertical/square/landscape canvas at setup. A trim or output-range cut reduces source spans, retimes dependent elements, and creates a version. Native EditPlan preview/final render, explicit history restore, undo/redo, and timed captions, B-roll, music and SFX are exposed. Layer sources can use library media or a Studio attachment uploaded or reused through the user’s account. Still JPEG, PNG and WebP sources are adapted to the existing B-roll contract for a bounded display interval. The native plan keeps a job-owned media reference for history and rerenders. Frame-preserving splits can keep output-timed layers in place. Duplication, copy/paste within the same project, clip deletion, and reorder are available when no dependent layers would change timing. The camera inspector edits the native start and end zoom values. Native export presets edit the versioned canvas and H.264 quality settings without retiming the clips. Effects and transition overlaps are marked on the timeline. |
| Motion and Vox | Requires configuration | `app/motion_graphic.py`, `creative/claude_motion/`, `creative/claude_vox/`, `creative/claude_intro/`. Structured selections plus topic, URL or owned media go through existing source inspection and authoring. Output is previewable. The descriptor in `motion_edit.py` defines editable fields. Claude, image and speech routes depend on project; style availability alone does not certify a provider or estimate a price. |
| HyperFrames | Requires configuration | Classic motion and picture/talking overlays in `creative/motion_graphic.py`, `engine/hyperframes/` and engine adapters. CLI/Chromium and fonts are runtime dependencies. Rendering of a generated composition does not imply its internals are editable by the panel. |
| Remotion | Requires configuration | `remotion/`, the Claude film builders and `brain/content_creator.py`. Composition, validated bundle and assets produce an MP4. Product browser renderer imports its runtime only when asked and reuses the existing compatibility check. Arbitrary generated Remotion scene source is not exposed as a structured timeline. |
| FFmpeg, MLT and render targets | Ready / requires configuration | Native jobs use the existing `/jobs/:id/render` pipeline, FFmpeg and MLT where applicable. Browser export uses `app/browser_render.py` and WebCodecs for verified compositions. Cloud routing is still determined by `app/render_cloud/` and project/deployment settings; credentials, object storage and worker health are operational requirements. |
| Lite, Medium and Pro | Requires configuration | `app/agents/dispatcher.py`, Medium worker, `app/agents/pro/`. Optional panel actions call the same Studio endpoint and keep the selected mode. Model availability and credit gates remain authoritative. |
| Transcription and alignment | Requires configuration | `brain/transcribe.py`, `app/talking_reel.py` and `app/routers/plans.py`. Supported engines produce source-timed words and sentences. The panel seeks to source words and uses the genuine Talking 1 sentence cut operation for audio and video; other styles and captions-only expose read-only speech timings. Caption corrections are a separate operation. |
| Narration and voice | Requires configuration | `brain/localize.py`, `creative/narration_take.py`, Studio voice-preview endpoints. Localize and storyboard inspectors reuse available voices, narration previews and voice settings. The API and provider policies govern account voices and billing. |
| Music and SFX | Ready / requires configuration | `app/routers/music.py`, `app/talking_reel.py`, `engine/music_mix.py`, `creative/audio/`. Browse library assets and hear previews. Talking exposes actual per-plan music replacement/removal, ducking, level and fades. Generating new music may use credits. Native EditPlans support placing uploaded sound effects and using uploaded audio as the music bed. Other engines retain their existing audio controls. |
| Image and video generation | Requires configuration | `brain/ai_provider.py`, `brain/media_provider.py`, `brain/content_creator.py`, `brain/motion_so.py`, `app/routers/motion_so.py`. The approved storyboard/scene path controls job credentials, paid clips and scene assets. A missing adapter or credential does not imply a runnable tile. |
| Creative resource registry | Ready / catalog only | `creative/resources/registry.py` and `app/routers/creative_resources.py` provide search, stable IDs, licensing and compatibility. Registry search paginates; the motion gallery loads its existing local verified manifests. “Catalog only” rows are browseable references. Compatible registry cards can apply to one or more EditPlan segments or transitions directly. The panel validates the saved version and applies one atomic batch through the existing resource adapters. |
| Templates, reusable components and skills | Ready / catalog only | `web/src/templateData.ts`, `presets/`, `creative/skills_library.py`, Shotcraft and the component manifests. The available templates and motion gallery are reachable from the panel. During native project setup, a profile from the approved Style Library can be pinned by ID and version and previewed from its actual reference evidence. Source recipes without a compatible runtime are references. Templates that only launch a prefilled chat are not wired as native one-click assemblies. |
| Typography | Ready / requires configuration | `app/routers/fonts.py`, `engine/font_library.py`, `FontLibrary` and `studio/FontPicker`. Browse bundled and approved fonts with a real sample and a Persian-glyph filter. Native projects can select a renderer-bound font for all captions and restore the style default in version history. Plan and motion inspectors pass compatible font IDs and preserve caption placement, color and sizing where those parameters exist. Rendering depends on the corresponding font files being installed. |
| Motion animation | Ready / unsupported | `app/motion_edit.py`, `creative/motion_graphic.py`. Parameter-editable generated motion uses its native schema to set style, text, layout and supported timing. Arbitrary layer extraction from an MP4 and general-purpose keyframes are unsupported. |
| Visual effects | Ready / catalog only | `engine/effects_v4.py`, `studio/EffectsEditor.tsx`. Supported effects use real IDs, versioned writes and frame previews where provided. Native resource visibility and render compatibility are separate flags. |
| Transitions | Ready / catalog only | `engine/schema.py`, `engine/operations.py`, `ResourceEffectEditor.tsx`. The renderer uses validated adjacent segment IDs and computes frame overlaps. Extendable recipes without an adapter remain catalog references. |
| B-roll and media | Ready / requires configuration | `app/broll_edits.py`, `app/studio_ingest.py`, `app/project_document.py`, media pickers. Existing picture/B-roll editors apply compatible assets to mapped slots. Local uploads and account reuse validate ownership. Drive requires a connected account. |
| Color, framing and zoom | Ready | `app/creative_plan.py` and `studio/LookStudio.tsx` apply renderer-bound plan parameters together with the plan approver. The monitor can compare source and actual output. Live overlays do not stand in for rendered pixels. |
| Script, storyboard and QC | Requires configuration | `creative/`, `brain/content_creator.py`, `app/routers/qc.py` and Studio review panes. The storyboard creation path uses the existing source analysis and action approval before media production. Configured Motion.so is available as a separate scene-generation choice. The panel also starts the existing long-video discovery worker, shows its progress and candidate previews, and opens child edits in the same panel. The optional assistant can suggest hooks and rhythm. Delivery-facing QC stays in the engine's current review infrastructure. |
| Export and interchange | Ready / requires configuration | `app/routers/render.py`, `app/routers/premiere.py`, `PremiereCard.tsx`. Preview, MP4 and available output versions reuse existing files. Native Premiere interchange uses the existing connector; the desktop bridge is required only for app-specific actions. |
| External integrations | Requires configuration | Cloud and media routers use existing auth, resumable ingest and provider authorization. Studio, projects and conversation IDs are shared. Panel does not introduce a new third-party account store. |
| Editing limits | Unsupported | The underlying formats have different operations. Moving and duplicating arbitrary tracks, universal drag/drop and keyframe editing, generic multi-source ripple edits, and frame-accurate edits of every generated MP4 are not promised. Native trims move downstream events with the engine; the regular timeline's existing per-engine editing surfaces remain intact. |

## Interaction references

The compact mobile tool strip, visible preview, and contextual selection follow
common interaction patterns reviewed in CapCut, InShot and VEED. The speech
tab uses click-to-seek and source-timed selection patterns from Descript and
Riverside. The desktop inspector and versioned edits take cues from Premiere
and Resolve. The preview-before-use library is informed by Canva. Optional
assisted actions follow the progressive disclosure used in Captions and
Runway. The visual system uses EditorGPT's own theme tokens, components and
icons.

- [CapCut video editor](https://www.capcut.com/tools/online-video-editor)
- [InShot](https://inshot.com/)
- [VEED timeline](https://support.veed.io/en/articles/10804541-what-you-need-to-know-about-veeds-timeline)
- [Descript features](https://www.descript.com/features)
- [Riverside Editor](https://riverside.com/blog/how-to-edit-video-audio)
- [Adobe Premiere timeline](https://helpx.adobe.com/premiere-pro/using/creating-changing-sequences.html)
- [DaVinci Resolve Edit](https://www.blackmagicdesign.com/products/davinciresolve/edit)
- [Canva video editor](https://www.canva.com/video-editor/)
- [Captions AI Edit](https://help.captions.ai/docs/project/ai-edit)
- [Runway Edit Studio](https://help.runwayml.com/hc/en-us/articles/51683104370451-Creating-with-Edit-Studio)

## Validation

- `python -m pytest -q tests/test_manual_panel.py` exercises the real Studio
  repository, account scoping, explicit engine selection, no synthetic chat
  message, idempotent start, and stale-plan rejection.
- `npm run build` verifies TypeScript and the production build.
- `node tests/manual-panel.browser.mjs` from `web/` targets an isolated local
  frontend and API at port 5197 by default. It checks actual draft persistence,
  media upload, trim, split, duplication, reorder, source-time scrubbing, caption add, font selection, undo/redo, version restore, clip zoom, and direct application of effects and transitions at mobile and desktop widths.
  `PANEL_TEST_RENDER=1` additionally runs and downloads native renders and checks the caption interval, transition overlap, uploaded video and still-image B-roll pixels, and non-silent uploaded sound effects.

## Integration boundaries

The branch adds a separate visual entry point. It does not change the chat
components, worker queues or render engine implementations. Existing Studio
routes continue to own editing and rendering for their respective job types.

- Native clip arrangement works over a single primary video. Timed cutaways,
  stills, captions and audio use the layers already understood by EditPlan.
  Clip reorder and paste are gated when an attached layer or transition
  would become misaligned. The camera control edits the existing two zoom
  endpoints. Arbitrary animation keyframes and simultaneous video overlays
  are outside that engine's editing contract.
- A gallery item is directly usable only when a compatible adapter exists.
  Upstream templates, styles and skill documents may still be reference-only
  or editable only through their own engine. The panel does not run arbitrary
  component code submitted through the gallery.
- Speech editing supports the existing Talking 1 sentence cut and the timeline
  caption correction API. Word timing inspection is available. Changing source
  word timings across already-approved plans, reordering speech, and
  remapping arbitrary tracks need a compatible renderer operation.
- The native render test runs FFmpeg and MLT without external generation.
  Storyboard approval and discovery controls use fixtures for provider
  output. Live paid generation, connected Drive transfers, browser and
  cloud render parity, and proprietary template outputs need validation in
  an environment configured for each service.
