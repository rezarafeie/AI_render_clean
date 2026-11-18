# Whiteboard engine — reference implementation (Remotion + SVG, Persian RTL, vertical)

Pipeline:
1. voice_pipeline/tts.py      → ElevenLabs eleven_v3 with-timestamps per line (key via key.py / env; never print it)
2. voice_pipeline/proc_voice.py 1.2 → trim silences, atempo, map alignment → words.json
3. voice_pipeline/build_data.py → app/src/data.json (scene starts, words, split hold)
4. voice_pipeline/sfx.py, music.py → ElevenLabs SFX + music
5. app: npm i && node stills.mjs 2 10 20 ; node render.mjs  (renderMedia uses outputLocation; concurrency ≤ cores)
6. dump timeline (esbuild scenes.tsx → timeline.json), voice_pipeline/mix.py → mix_raw.wav → 2-pass loudnorm −14 LUFS → mux

Fonts: Marhey and Vazirmatn are OFL (SIL Open Font License). Doran is NOT included (licensed, add your own copy to app/public/fonts/DoranFaNum-*.woff2).
The voice files and music are not included.
