---
name: remotion-kit
description: Building and rendering a Remotion film in this container - project layout, the render script, stills, fonts, Persian text and performance limits.
---
# Remotion in EditorGPT Pro

## Project
```bash
mkdir -p project && cd project
cp /app/creative/claude_motion/kit/render.mjs /app/creative/claude_motion/kit/tsconfig.json .
mkdir -p src public/fonts && ln -sfn /app/remotion/node_modules node_modules
cp /app/presets/fonts/RAY*.TTF public/fonts/     # Persian display/text family (RAY, RAY-BOLD, RAY-BLACK ...)
```
`src/index.ts` must register ONE composition with id `Main`:
```ts
import {registerRoot, Composition} from 'remotion';
import {Film} from './Film';
registerRoot(() => <Composition id="Main" component={Film} durationInFrames={300} fps={30} width={1080} height={1920}/>);
```
(write it as index.tsx if you use JSX, or use React.createElement in index.ts). Files the film uses go in `public/` and are loaded with
`staticFile('name.png')`; fonts with an `@font-face` in a `<style>` tag using `staticFile('fonts/RAY-BOLD.TTF')`.

## Render
- Stills (half size, to look at): `node render.mjs stills 1.5 4 7.2` → `stills/s_1.5.jpg` ... then Read them.
- Video (muted H.264): `node render.mjs video ../out/video.mp4` (prints PROGRESS n). Add sound afterwards with ffmpeg.
- An error prints one line `RENDER_ERROR ...`: read it, fix the code, render again.

## Craft and limits
- Everything animates from `useCurrentFrame()` (no CSS animations, no timers, no Math.random: use `random('seed')` from remotion).
- Persian: `direction: 'rtl'`, never split into letters; reveal whole words or wipe with a clip-path from the right.
- This machine is small: keep films short (≤ 60 s), avoid big blur filters and thousands of SVG nodes; a 30 s 1080x1920 render takes several minutes.
