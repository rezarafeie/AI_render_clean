# Intro engines — reference implementation (Story / Reel / Presenter / Film3D)

See EDITORGPT_INTRO_ENGINES.md for the full spec and the Claude Code prompt.

NOT included (add your own):
- Licensed fonts: RokhFaNum-{Black,Bold,Regular}.ttf, PaykanFaNum-{ExtraBlack,Regular}.ttf, typokar-2.ttf, DoranFaNum-*.woff2 → app/public/fonts/
- Presenter footage: app/public/talk/graded.mp4 (1920x1080) and talk/fg3.webm (VP9 alpha cut-out, 812x1080)
- Voice files (audio/voice/*.mp3 + *.al.json) — generate with audio_pipeline/tts.py
- ElevenLabs key: audio_pipeline/key.py must expose key(); never commit or print it

Build order: tts.py → proc_voice.py → sfx.py/music.py → (b3d/batch.sh for Film) → node stills.mjs <Id> <t…> → node render.mjs <Id> → dump.ts → mix.py → ffmpeg mux.
Compositions: Story (1080x1920@30), Reel (1920x1080@60), Talk (1920x1080@30), Film (1920x1080@24).
