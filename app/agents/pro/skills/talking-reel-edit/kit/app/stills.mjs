import {bundle} from '@remotion/bundler';
import {renderStill, selectComposition} from '@remotion/renderer';
import path from 'path';
const times = process.argv.slice(2).map(Number);
const serveUrl = await bundle({entryPoint: path.resolve('src/index.ts'), publicDir: path.resolve('public')});
const opts = {serveUrl, id: 'Edit', browserExecutable: '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome', chromiumOptions: {gl: 'swangle'}};
const composition = await selectComposition(opts);
for (const t of times) {
  const frame = Math.round(t * 30);
  await renderStill({...opts, composition, frame, output: `stills/s_${String(t).replace('.', '_')}.jpg`, imageFormat: 'jpeg', jpegQuality: 85, scale: 0.5});
  console.log('ok', t);
}
