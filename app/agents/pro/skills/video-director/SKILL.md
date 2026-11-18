---
name: video-director
description: How EditorGPT Pro directs any video job end to end (read first, every time) - understanding the request and the files, one plan, sound before picture, stills before the render, self-review, honest delivery.
---
# Video director

## 1. Understand
- List the person's files (mcp__editorgpt__assets_list) and fetch the ones you need (assets_fetch → in/).
- Probe every video/audio: `ffprobe -v error -show_entries format=duration:stream=width,height,r_frame_rate,codec_type -of json in/<file>`.
- Look at pictures: Read the image files; for a video extract a contact sheet first
  (`ffmpeg -i in/v.mp4 -vf "fps=1/2,scale=320:-1,tile=4x3" -frames:v 1 out/sheet.jpg`) and Read it.
- Decide the format: vertical 1080x1920 unless the person or the source says otherwise; 30 fps.

## 2. Plan once
Write `plan.md` in the folder: the idea in one line, the beats with their seconds, every text on screen (Persian, short), the look (ground, palette,
type, motion), what each beat shows. Tell the person the idea in one or two sentences with `say`. Do not ask for approval unless the request is unclear.

## 3. Build
- Remotion for motion graphics and titles (skill `remotion-kit`); ffmpeg for cutting, scaling, mixing and simple overlays.
- Timing: if there is a voice or music, cut on it (words or beats), not on round numbers.
- Persian text: never letter by letter; whole words or a wipe from the right; Persian digits (۰-۹); keep 60 px margins; no text over faces.

## Cost discipline (every picture you Read stays in the context and is paid again on every later call)
- Look at stills as ONE contact sheet: `ffmpeg -i stills/s_%*.jpg ...` or python/PIL to tile 4-9 stills into one image (max ~1600 px wide), then Read
  that single image. Never Read the same image twice; never Read every still one by one.
- Read only the part of a file you need (offset/limit); do not re-read files you just wrote.
- Show the person stills with show_stills from their paths (you do not need to Read them first).

## 4. Check before the full render
- Render 4-8 stills at the key moments, Read them yourself and fix: cut text, overlaps, empty frames, low contrast, wrong numbers.
- Show the best 3-6 to the person (`show_stills`, one Persian caption).

## 5. Render, verify, deliver
- Render to out/. Verify with ffprobe (duration, size, fps, audio stream when there should be one).
- If there is sound: loudness about -14 LUFS (`ffmpeg -i out/x.mp4 -af loudnorm=I=-14:TP=-1:LRA=11:print_format=summary -f null -`).
- `deliver` the file with a title and a short honest note (what it is, length, frame, limits).
