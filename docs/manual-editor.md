# Manual editor

`/panel` loads the editor on demand. `/panel/:conversationId` opens an existing
Studio conversation and its project records. Panel drafts use the same
authenticated attachments and Studio repository. Creating or cutting a clip
does not send a user message to the Studio orchestrator. The optional assistant
uses that conversation's existing agent and credit accounting.

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
| Native clip editing | Ready | `app/jobs.py`, `engine/schema.py`, `engine/operations.py`. An owned video seeds a real EditPlan. Set source/vertical/square/landscape canvas at setup. A trim or output-range cut reduces source spans, retimes dependent elements, and creates a version. Native EditPlan preview/final render, explicit history restore, undo/redo, and timed captions, B-roll, music and SFX are exposed. Plain plans also allow split, duplication and reorder by touch controls or desktop drag. |
| Motion and Vox | Requires configuration | `app/motion_graphic.py`, `creative/claude_motion/`, `creative/claude_vox/`, `creative/claude_intro/`. Structured selections plus topic, URL or owned media go through existing source inspection and authoring. Output is previewable. The descriptor in `motion_edit.py` defines editable fields. Claude, image and speech routes depend on project; style availability alone does not certify a provider or estimate a price. |
| HyperFrames | Requires configuration | Classic motion and picture/talking overlays in `creative/motion_graphic.py`, `engine/hyperframes/` and engine adapters. CLI/Chromium and fonts are runtime dependencies. Rendering of a generated composition does not imply its internals are editable by the panel. |
| Remotion | Requires configuration | `remotion/`, the Claude film builders and `brain/content_creator.py`. Composition, validated bundle and assets produce an MP4. Product browser renderer imports its runtime only when asked and reuses the existing compatibility check. Arbitrary generated Remotion scene source is not exposed as a structured timeline. |
| FFmpeg, MLT and render targets | Ready / requires configuration | Native jobs use the existing `/jobs/:id/render` pipeline, FFmpeg and MLT where applicable. Browser export uses `app/browser_render.py` and WebCodecs for verified compositions. Cloud routing is still determined by `app/render_cloud/` and project/deployment settings; credentials, object storage and worker health are operational requirements. |
| Lite, Medium and Pro | Requires configuration | `app/agents/dispatcher.py`, Medium worker, `app/agents/pro/`. Optional panel actions call the same Studio endpoint and keep the selected mode. Model availability and credit gates remain authoritative. |
| Transcription and alignment | Requires configuration | `brain/transcribe.py`, `app/talking_reel.py` and `app/routers/plans.py`. Supported engines produce source-timed words and sentences. The panel seeks to source words and uses the genuine Talking 1 sentence cut operation for audio and video; other styles and captions-only expose read-only speech timings. Caption corrections are a separate operation. |
| Narration and voice | Requires configuration | `brain/localize.py`, `creative/narration_take.py`, Studio voice-preview endpoints. Localize and storyboard inspectors reuse available voices, narration previews and voice settings. The API and provider policies govern account voices and billing. |
| Music and SFX | Ready / requires configuration | `app/routers/music.py`, `app/talking_reel.py`, `engine/music_mix.py`, `creative/audio/`. Browse library assets and hear previews. Talking exposes actual per-plan music replacement/removal, ducking, level and fades. Generating new music may use credits. Generic hand-placing audio/SFX is not exposed on every engine. |
| Image and video generation | Requires configuration | `brain/ai_provider.py`, `brain/media_provider.py`, `brain/content_creator.py`, `brain/motion_so.py`, `app/routers/motion_so.py`. The approved storyboard/scene path controls job credentials, paid clips and scene assets. A missing adapter or credential does not imply a runnable tile. |
| Creative resource registry | Ready / catalog only | `creative/resources/registry.py` and `app/routers/creative_resources.py` provide search, stable IDs, licensing and compatibility. Registry search paginates; the motion gallery loads its existing local verified manifests. “Catalog only” rows are browseable references. Native effect/transition application uses the existing operations editor and registered live IDs. |
| Templates, reusable components and skills | Ready / catalog only | `web/src/templateData.ts`, `presets/`, `creative/skills_library.py`, Shotcraft and the component manifests. The available templates and motion gallery are reachable from the panel. Source recipes without a compatible runtime are references. Templates that only launch a prefilled chat are not wired as native one-click assemblies. |
| Typography | Ready / requires configuration | `app/routers/fonts.py`, `engine/font_library.py`, `FontLibrary` and `studio/FontPicker`. Browse the real font catalog. Plan and motion inspectors pass compatible font IDs and preserve caption placement, color and sizing where those parameters exist. Rendering depends on the corresponding font files being installed. |
| Motion animation | Ready / unsupported | `app/motion_edit.py`, `creative/motion_graphic.py`. Parameter-editable generated motion uses its native schema to set style, text, layout and supported timing. Arbitrary layer extraction from an MP4 and general-purpose keyframes are unsupported. |
| Visual effects | Ready / catalog only | `engine/effects_v4.py`, `studio/EffectsEditor.tsx`. Supported effects use real IDs, versioned writes and frame previews where provided. Native resource visibility and render compatibility are separate flags. |
| Transitions | Ready / catalog only | `engine/schema.py`, `engine/operations.py`, `ResourceEffectEditor.tsx`. The renderer uses validated adjacent segment IDs and computes frame overlaps. Extendable recipes without an adapter remain catalog references. |
| B-roll and media | Ready / requires configuration | `app/broll_edits.py`, `app/studio_ingest.py`, `app/project_document.py`, media pickers. Existing picture/B-roll editors apply compatible assets to mapped slots. Local uploads and account reuse validate ownership. Drive requires a connected account. |
| Color, framing and zoom | Ready | `app/creative_plan.py` and `studio/LookStudio.tsx` apply renderer-bound plan parameters together with the plan approver. The monitor can compare source and actual output. Live overlays do not stand in for rendered pixels. |
| Script, storyboard and QC | Requires configuration | `creative/`, `brain/content_creator.py`, `app/routers/qc.py` and Studio review panes. Existing generated storyboard and approvals are reachable. The optional assistant can suggest hooks and rhythm. Delivery-facing QC stays in the engine's current review infrastructure. |
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
  media upload, trim, split, duplication, reorder, source-time scrubbing, caption add, undo/redo and version restore at mobile and desktop widths.
  `PANEL_TEST_RENDER=1` additionally runs and downloads a local native render and checks that the caption appears only in its intended time range.
