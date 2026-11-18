---
name: motion-explainer
description: A narrated vertical Persian motion graphic (explainer, story, idea) built in Remotion with an SVG art library, every element on its spoken word, sound design and music. Use for «موشن گرافیک»، explainers, remaking a reference motion video.
---
# motion-explainer

## In EditorGPT Pro (read before the reference)
The reference below was written for a hand-built pipeline on a laptop. Here every outside service is an editorgpt tool and you have no internet:
- ElevenLabs voice → `mcp__editorgpt__tts` (one natural take, per-line wavs with each word's start/end); Scribe → `mcp__editorgpt__stt`
- ElevenLabs music / sound effects → `mcp__editorgpt__music_generate` / `mcp__editorgpt__sfx` (or `music_library`)
- a product or reference page → `mcp__editorgpt__web_read`; the person's files → `assets_list` / `assets_fetch`
- cutting a person out of video → `mcp__editorgpt__person_matte`; generated pictures → `mcp__editorgpt__image_generate`
- fonts (Doran, Rokh, Peyda, ...) → `mcp__editorgpt__fonts` (licensed: only for this film); the person's brand → `mcp__editorgpt__brand_profile`
- the FINAL Remotion render → `mcp__editorgpt__render_cloud` + `render_status` (1080x1920, 1920x1080, 1080x1080 or 1080x1350 at 30 fps; muted, mix sound after with ffmpeg);
  other formats render in the container. Check with `mcp__editorgpt__qc_report`, then `deliver`.
- The kit/ folder next to this file holds the reference project's code (no fonts or big media): copy what you need into your project, adapt it, never paste
  another brand's content. `node_modules`: link `/app/remotion/node_modules` (see remotion-kit).

## The full guide
Read `reference.md` in this folder (Persian; the complete method, design system, storyboard and QA of the reference film).

## The reference code
`kit/` (15 files from motion_source.zip): read it to see exactly how the reference film was built.
