import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';

async function mount(providers, files) {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/' });
  const previous = { window: globalThis.window, document: globalThis.document };
  Object.assign(globalThis, { window: dom.window, document: dom.window.document });
  const require = createRequire(new URL('../package.json', import.meta.url));
  const React = require('react'), { createRoot } = require('react-dom/client'), { flushSync } = require('react-dom');
  const { MemoryRouter } = require('react-router-dom');
  const built = await build({ entryPoints: [new URL('../src/studio/CloudPicker.tsx', import.meta.url).pathname], bundle: true, write: false, format: 'cjs', platform: 'node',
    external: ['react', 'react-router-dom'], plugins: [{ name: 'mock-api', setup(b) {
      b.onResolve({ filter: /^\.\.\/api$/ }, () => ({ path: 'api', namespace: 'mock' }));
      b.onLoad({ filter: /.*/, namespace: 'mock' }, () => ({ contents: `export const api = {
        cloudProviders: async () => (${JSON.stringify({ providers })}),
        cloudFiles: async () => (${JSON.stringify({ files, next_page_token: null })}) };` }));
    } }] });
  const mod = { exports: {} };
  new Function('require', 'module', 'exports', built.outputFiles[0].text)(require, mod, mod.exports);
  const root = createRoot(document.getElementById('root'));
  const imported = [];
  flushSync(() => root.render(React.createElement(MemoryRouter, null, React.createElement(mod.exports.CloudPicker, { onClose() {}, onImport: async list => { imported.push(...list); } }))));
  await new Promise(resolve => setTimeout(resolve, 50));
  return { dom, document, imported, flushSync, cleanup() { flushSync(() => root.unmount()); dom.window.close(); Object.assign(globalThis, previous); } };
}

test('a disconnected Drive sends the person to Settings instead of listing files', async () => {
  const view = await mount([{ id: 'googledrive', name: 'Google Drive', enabled: true, connected: false, status: 'NOT_CONNECTED', capabilities: {} }], []);
  try {
    assert.match(view.document.body.textContent, /Google Drive is not connected/);
    assert.ok(view.document.querySelector('a[href="/settings#integrations"]'));
    assert.equal(view.document.querySelectorAll('input[type=checkbox]').length, 0);
  } finally { view.cleanup(); }
});

test('only media files can be selected, and the chosen files are handed over for import', async () => {
  const files = [
    { id: 'd1', name: 'Shoots', mime_type: 'application/vnd.google-apps.folder', is_folder: true, native: false, kind: null, size: null },
    { id: 'v1', name: 'clip.mp4', mime_type: 'video/mp4', is_folder: false, native: false, kind: 'video', size: 2048, duration: 4 },
    { id: 'g1', name: 'Plan', mime_type: 'application/vnd.google-apps.document', is_folder: false, native: true, kind: null, size: null },
  ];
  const view = await mount([{ id: 'googledrive', name: 'Google Drive', enabled: true, connected: true, status: 'ACTIVE', capabilities: {} }], files);
  try {
    const boxes = view.document.querySelectorAll('input[type=checkbox]');
    assert.equal(boxes.length, 1);                       // the folder and the Google document have none
    assert.match(view.document.body.textContent, /Google document · cannot be imported/);
    const importButton = [...view.document.querySelectorAll('button')].find(button => /^Import/.test(button.textContent));
    assert.equal(importButton.disabled, true);
    boxes[0].click();
    await new Promise(resolve => setTimeout(resolve, 20));
    assert.equal([...view.document.querySelectorAll('button')].find(button => /^Import/.test(button.textContent)).disabled, false);
    [...view.document.querySelectorAll('button')].find(button => /^Import/.test(button.textContent)).click();
    await new Promise(resolve => setTimeout(resolve, 20));
    assert.deepEqual(view.imported.map(file => file.id), ['v1']);
  } finally { view.cleanup(); }
});
