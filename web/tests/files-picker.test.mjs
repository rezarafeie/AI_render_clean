import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';

const FILES = { files: [
  { id: 'att:a1', name: 'podcast.mp4', kind: 'video', size: 627216154, created_at: '2026-11-05T08:50:00Z', source: 'upload', conversation_id: 'c1', conversation_title: 'Podcast' },
  { id: 'out:p1:final.mp4', name: 'Reel — final.mp4', kind: 'video', size: 9000000, created_at: '2026-11-04T08:50:00Z', source: 'output', conversation_id: 'c2', conversation_title: 'Reel' },
], usage: 627216154, quota: 5 * 1024 ** 3 };

async function mount() {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/' });
  const previous = { window: globalThis.window, document: globalThis.document };
  Object.assign(globalThis, { window: dom.window, document: dom.window.document });
  const require = createRequire(new URL('../package.json', import.meta.url));
  const React = require('react'), { createRoot } = require('react-dom/client'), { flushSync } = require('react-dom');
  const deleted = [];
  globalThis.__deleted = deleted; globalThis.__files = JSON.parse(JSON.stringify(FILES));
  const built = await build({ entryPoints: [new URL('../src/studio/FilesPicker.tsx', import.meta.url).pathname], bundle: true, write: false, format: 'cjs', platform: 'node',
    external: ['react', 'react-dom', 'react-router-dom'], plugins: [{ name: 'mock', setup(b) {
      b.onResolve({ filter: /^\.\.\/api$/ }, () => ({ path: 'api', namespace: 'mock' }));
      b.onResolve({ filter: /^\.\.\/ui$/ }, () => ({ path: 'ui', namespace: 'mock' }));
      b.onLoad({ filter: /^api$/, namespace: 'mock' }, () => ({ contents: `export const api = {
        studioFiles: async () => JSON.parse(JSON.stringify(globalThis.__files)),
        deleteStudioFile: async (id) => { globalThis.__deleted.push(id); globalThis.__files.files = globalThis.__files.files.filter(f => f.id !== id); } };` }));
      b.onLoad({ filter: /^ui$/, namespace: 'mock' }, () => ({ contents: `export const friendlyError = (e, what) => 'Could not ' + what;` }));
    } }] });
  const mod = { exports: {} };
  new Function('require', 'module', 'exports', built.outputFiles[0].text)(require, mod, mod.exports);
  const root = createRoot(document.getElementById('root'));
  const attached = [];
  flushSync(() => root.render(React.createElement(mod.exports.FilesPicker, { onClose() {}, onAttach: async list => { attached.push(...list); } })));
  await new Promise(resolve => setTimeout(resolve, 60));
  return { document, attached, deleted, cleanup() { flushSync(() => root.unmount()); dom.window.close(); Object.assign(globalThis, previous); } };
}

test('every stored file is listed with its source and the space used, and the chosen ones are handed over', async () => {
  const view = await mount();
  try {
    assert.match(view.document.body.textContent, /podcast\.mp4/);
    assert.match(view.document.body.textContent, /Reel — final\.mp4/);
    assert.match(view.document.body.textContent, /Uploaded · .*Podcast/);
    assert.match(view.document.body.textContent, /Made here/);
    assert.match(view.document.body.textContent, /of 5\.00 GB used by uploads/);
    const use = () => [...view.document.querySelectorAll('button')].find(button => /^Use/.test(button.textContent));
    assert.equal(use().disabled, true);
    view.document.querySelector('input[aria-label="Select podcast.mp4"]').click();
    await new Promise(resolve => setTimeout(resolve, 20));
    use().click();
    await new Promise(resolve => setTimeout(resolve, 20));
    assert.deepEqual(view.attached.map(file => file.id), ['att:a1']);
  } finally { view.cleanup(); }
});

test('deleting a file asks first, names the file, and removes it from the list only after the confirmation', async () => {
  const view = await mount();
  try {
    view.document.querySelector('button[aria-label="Delete podcast.mp4"]').click();
    await new Promise(resolve => setTimeout(resolve, 40));
    const dialog = view.document.querySelector('[role=dialog][aria-label="Delete this file?"]');
    assert.ok(dialog, 'a confirmation opens');
    assert.match(dialog.textContent, /podcast\.mp4/);
    assert.deepEqual(view.deleted, []);                                   // nothing is deleted before the confirmation
    [...dialog.querySelectorAll('button')].find(button => button.textContent === 'Delete').click();
    await new Promise(resolve => setTimeout(resolve, 120));
    assert.deepEqual(view.deleted, ['att:a1']);
    assert.doesNotMatch(view.document.body.textContent, /podcast\.mp4/);
  } finally { view.cleanup(); }
});
