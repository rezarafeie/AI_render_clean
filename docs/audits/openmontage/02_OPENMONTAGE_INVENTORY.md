# 02 — OpenMontage Inventory

Source: `/private/tmp/claude-501/audit/OpenMontage` @ `fecb9a1e3cc2`. Maturity vocabulary: **implemented** (code path exists and is self-contained), **beta/experimental** (the tool's own `stability` tag), **doc-only** (instructions with no code behind them), **third-party** (vendored knowledge). Maturity of a tool is *the tool's declared tag*; I did not run any of them.

Method: class and metadata greps over `tools/**/*.py` (`stability =`, `runtime =`, `tier =`, `capability =`), docstring and `def`/`class` extraction for the modules below, listing of `pipeline_defs`, `skills`, `schemas`, `styles`, `remotion-composer/src`.

## 1. Counts (verified)

| Item | Count | Notes |
| --- | ---: | --- |
| `BaseTool` subclasses | 140 | one file may hold several; `tools/base_tool.py` defines the contract |
| stability | 6 production / 56 beta / 75 experimental | only 6 tools claim production |
| runtime | 68 API / 17 local / 15 local-GPU / 9 hybrid | |
| pipelines | 13 | `pipeline_defs/*.yaml` |
| artifact schemas | 21 | `schemas/artifacts/*.schema.json` |
| style playbooks | 5 YAML + `styles/custom/` | `styles/*.yaml` |
| OpenMontage skills | 158 MD | `skills/**` |
| vendored layer-3 skills | 93 folders / 580 MD | `.agents/skills`, mirrored in `.claude/skills` |
| tests | 195 `test_*.py` | not executed in this audit |
| Remotion components | 17 + charts | `remotion-composer/src/components` |

## 2. Executable capabilities (grouped; every row is a tool family)

| Capability | Source paths | Entry point | Maturity | Needs | Paid? |
| --- | --- | --- | --- | --- | --- |
| Video generation (28 tools: Veo, Sora, Kling, Runway, Pika, MiniMax, Seedance, Wan, Hunyuan, LTX, Grok, HeyGen, Higgsfield, Jimeng, …) | `tools/video/*_video.py`, selector `video_selector.py` | `BaseTool.execute` | mostly beta/experimental | per-provider keys / GPUs | yes (API) |
| Image generation (21: FLUX, Imagen, OpenAI, Recraft, Ideogram, Seedream, local diffusion, …) | `tools/graphics/*_image.py`, `image_selector.py` | same | beta/experimental | keys | yes |
| TTS (16: ElevenLabs, Google, OpenAI, Azure, Cartesia, Fish, Piper local, …) | `tools/audio/*_tts.py`, `tts_selector.py` | same | beta/experimental; Piper local | keys | mostly |
| Music generation/search (Suno, Lyria, ElevenLabs soundtrack, Freesound, Pixabay, ComfyUI, MiniCut fit) | `tools/audio/{suno_music,google_music,fal_elevenlabs_music,freesound_music,pixabay_music,music_gen,music_library,minicut_music*}.py` | same | beta/experimental | keys / external `minicut` CLI | partly |
| Audio analysis: energy offset | `tools/analysis/audio_energy.py` (311 lines, ffmpeg ebur128, **production**) | `AudioEnergy` | implemented | ffmpeg | no |
| Audio mixing | `tools/audio/audio_mixer.py` (822 lines; ffmpeg, optional pydub) | `AudioMixer` | implemented | ffmpeg | no |
| STT/analysis | `tools/analysis/{transcriber,azure_stt,dashscope_asr,mistral_stt,scene_detect,frame_sampler,video_analyzer,video_understand,face_tracker,visual_qa,composition_validator,video_downloader,transcript_fetcher}.py` | same | mixed | ffmpeg, PySceneDetect, MediaPipe, keys | partly |
| Video post (silence cutter, auto-reframe with face tracking, stitch, trim, green-screen, caption burn, clip search/cache, corpus builder) | `tools/video/{silence_cutter,auto_reframe,video_stitch,video_trimmer,green_screen_*,remotion_caption_burn,clip_search,direct_clip_search,clip_cache,corpus_builder}.py` | same | beta/experimental | ffmpeg, OpenCV/MediaPipe, npx remotion | no (local) |
| Composition | `tools/video/video_compose.py` (3041 lines, Remotion/FFmpeg), `hyperframes_compose.py` (1469 lines) | `VideoCompose`, `HyperframesCompose` | implemented, large | node, npx | no |
| Stock sources (19 adapters: Pexels, Pixabay, Unsplash, Openverse, NASA, Wikimedia, Internet Archive, …) | `tools/video/stock_sources/*.py` | `base.py` interface | beta | keys/free | mostly free |
| Enhancement (upscale, face restore/enhance, bg-remove, colour grade) | `tools/enhancement/*.py` | same | experimental, local-GPU | GPUs/models | no |
| Avatar/lip-sync (HeyGen, Kling, talking head) | `tools/avatar/*.py` | same | beta | keys | yes |
| 3D / world (Atlas, fal 3D, Blender, three.js) | `tools/graphics/{atlas_3d,fal_3d,blender_world,threejs_*}.py` | same | experimental | blender/keys | partly |
| Subtitles | `tools/subtitle/subtitle_gen.py` | `SubtitleGen` | implemented | — | no |
| Publish | `tools/publishers/export_bundle.py` | same | implemented | — | no |
| Budget | `tools/cost_tracker.py` (`CostTracker`: estimate → reserve → reconcile; modes) | library | implemented | — | no |
| Registry | `tools/tool_registry.py` (538 lines): discovery, status, preflight capability menu | library | implemented | — | no |

## 3. Deterministic libraries (the part most relevant to EditorGPT)

| Module | Purpose | Lines | Maturity |
| --- | --- | ---: | --- |
| `lib/slideshow_risk.py` | six 0–5 dimensions (repetition, decorative visuals, weak motion, weak shot intent, typography over-reliance, unsupported "cinematic" claims) → verdict strong/acceptable/revise/fail | 258 | implemented, heuristic over scene-plan fields |
| `lib/variation_checker.py` | structural check: shot-size mix, consecutive same-size runs, generic phrases list | ~ | implemented, heuristic |
| `lib/delivery_promise.py` | classify what the brief promises (motion-led vs still-led) and lock it so compose cannot silently downgrade | 247 | implemented |
| `lib/source_media_review.py` | required inspection of user media using real probes before planning | 414 | implemented |
| `lib/scoring.py` | weighted provider/production-path ranking | 594 | implemented, provider-centric |
| `lib/corpus.py` + `lib/clip_embedder.py` | project-local clip corpus; CLIP ViT-B/32 embeddings for text→frame similarity | 431 + — | implemented, heavy (350 MB model) |
| `lib/verify_scene_pacing.py` | assert terminal-scene steps align with narration cues | — | narrow (TerminalScene only) |
| `lib/checkpoint.py` | checkpoint writer/reader with schema validation | 660 | implemented |
| `lib/hyperframes_style_bridge.py` | playbook → CSS variables + DESIGN.md for HyperFrames | 194 | implemented |
| `lib/playbook_generator.py` | generate schema-valid custom playbooks | 225 | implemented |
| `lib/pipeline_loader.py`, `lib/media_profiles.py`, `lib/asset_cache.py`, `lib/config_model.py`, `lib/env_loader.py`, `lib/events.py`, `lib/paths.py`, `lib/shot_prompt_builder.py` | infrastructure | — | implemented |

## 4. Instruction assets (doc-only: they do nothing without an agent reading them)

* Pipeline manifests and 100+ stage director skills (`skills/pipelines/<pipeline>/<stage>-director.md`).
* Meta skills: `reviewer.md` (CHAI "accurate/complete/constructive" rules, severities critical/suggestion/nitpick/investigation, max two rounds), `taste-direction.md` (taste-profile contract with 1–10 dials), `creative-intake.md`, `video-reference-analyst.md`, `voice-performance-director.md`, `bespoke-composition.md`, `animation-runtime-selector.md`, `checkpoint-protocol.md`, `capability-extension.md`, `skill-creator.md`, `onboarding.md`.
* Creative skills: `short-form.md` (platform facts: 9:16, safe zones, −14 LUFS/−1 dBTP, 120–140 BPM), `storytelling`, `sound-design`, `data-visualization`, `broll-planning`, `commercial-product-video`, `typography`, `video-editing`, `screen-recording`, provider prompting guides.
* Style playbooks: clean-professional, flat-motion-graphics, minimalist-diagram, premium-minimalist, anime-ghibli (+ custom).

## 5. Other components

* `backlot/` — local FastAPI storyboard board (watches project files). Developer tool, not multi-user.
* `ink-theater/` — JS puppet/mocap renderer; has `THIRD_PARTY_NOTICES.md`.
* `remotion-composer/` — React compositions; `SCENE_TYPES.md` documents the scene vocabulary.

## 6. Dependencies (`requirements.txt`)

pyyaml, pydantic, jsonschema, python-dotenv, Pillow, numpy, requests, certifi, google-auth, google-genai, openai, fastapi, uvicorn, watchfiles, websockets, pythainlp; GPU extras in `requirements-gpu.txt`. Node: Remotion and HyperFrames packages. `tools/base_tool.py` loads a project `.env` into `os.environ` at import time (security note in 09).

## 7. Not verified

Per-tool behaviour, real output quality, provider contracts, and any claim in README/guide prose about results. Items in rows marked "mixed" were classified from metadata and docstrings only. See `11_COVERAGE_REPORT.md`.
