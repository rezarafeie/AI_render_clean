import {bundle} from '@remotion/bundler';
import {renderMedia, selectComposition} from '@remotion/renderer';
import path from 'path';
const serveUrl = await bundle({entryPoint: path.resolve('src/index.ts'), publicDir: path.resolve('public')});
const opts = {serveUrl, id: 'WB', browserExecutable: '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome', chromiumOptions: {gl: 'swangle'}};
const composition = await selectComposition(opts);
const fr = process.argv[2] ? process.argv[2].split('-').map(Number) : null;
let last=0;
await renderMedia({...opts, composition, codec: 'h264', crf: 17, outputLocation: process.argv[3] || 'out/video.mp4', concurrency: 2, muted: true, frameRange: fr || undefined,
  onProgress: ({progress}) => { if (progress - last > 0.05) { last = progress; console.log((progress*100).toFixed(0)+'%'); } }});
console.log('done');
