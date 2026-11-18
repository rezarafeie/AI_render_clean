import {bundle} from '@remotion/bundler';
import {renderMedia, selectComposition} from '@remotion/renderer';
import path from 'path';
const id = process.argv[2];
const serveUrl = await bundle({entryPoint: path.resolve('src/index.ts'), publicDir: path.resolve('public')});
const opts = {serveUrl, id, browserExecutable: '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome', chromiumOptions: {gl: 'swangle'}};
const composition = await selectComposition(opts);
let last = 0;
await renderMedia({...opts, composition, codec: 'h264', crf: 16, outputLocation: path.resolve(`out/${id}.mp4`), concurrency: 2, muted: true,
  onProgress: ({progress}) => { if (progress - last > 0.1) { last = progress; console.log((progress * 100).toFixed(0) + '%'); } }});
console.log('done');
