// node render.mjs stills <t> <t>...   -> stills/s_<t>.jpg (half size)        node render.mjs video <out.mp4>   -> a muted H.264 video
// Errors are printed as one line "RENDER_ERROR <message>" so the engine can hand them back to the author.
import {bundle} from '@remotion/bundler';
import {renderMedia, renderStill, selectComposition} from '@remotion/renderer';
import path from 'path';
import fs from 'fs';
const [mode, ...rest] = process.argv.slice(2);
const browserExecutable = process.env.REMOTION_BROWSER_EXECUTABLE || undefined;
try {
  const serveUrl = await bundle({entryPoint: path.resolve('src/index.ts'), publicDir: path.resolve('public'), onProgress: () => {}});
  const composition = await selectComposition({serveUrl, id: 'Main', browserExecutable});
  if (mode === 'stills') {
    fs.mkdirSync('stills', {recursive: true});
    for (const t of rest.map(Number)) {
      const frame = Math.min(composition.durationInFrames - 1, Math.max(0, Math.round(t * composition.fps)));
      await renderStill({serveUrl, composition, frame, output: `stills/s_${t}.jpg`, imageFormat: 'jpeg', jpegQuality: 85, scale: 0.5, browserExecutable});
      console.log('STILL', t);
    }
  } else {
    let last = -1;
    await renderMedia({composition, serveUrl, codec: 'h264', crf: 18, pixelFormat: 'yuv420p', muted: true, outputLocation: rest[0] || 'out/video.mp4', browserExecutable,
      concurrency: Number(process.env.REMOTION_CONCURRENCY || 2),
      onProgress: ({progress}) => { const p = Math.floor(progress * 20) * 5; if (p !== last) { last = p; console.log('PROGRESS', p); } }});
    console.log('DONE');
  }
} catch (error) {
  console.log('RENDER_ERROR ' + String(error && (error.stack || error.message) || error).replace(/\s+/g, ' ').slice(0, 3000));
  process.exit(2);
}
