import {bundle} from '@remotion/bundler';
import {renderStill, selectComposition} from '@remotion/renderer';
import path from 'path';
const id = process.argv[2]; const times = process.argv.slice(3).map(Number);
const serveUrl = await bundle({entryPoint: path.resolve('src/index.ts'), publicDir: path.resolve('public')});
const opts = {serveUrl, id, browserExecutable: '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome', chromiumOptions: {gl: 'swangle'}};
const composition = await selectComposition(opts);
for (const t of times) {
  await renderStill({...opts, composition, frame: Math.round(t * composition.fps), output: `stills/${id}_${String(t).replace('.', '_')}.jpg`, imageFormat: 'jpeg', jpegQuality: 85, scale: 0.5});
  console.log('ok', t);
}
