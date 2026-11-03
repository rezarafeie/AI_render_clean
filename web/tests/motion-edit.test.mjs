import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {build} from 'esbuild';
import {JSDOM} from 'jsdom';

async function load() {
  const require = createRequire(new URL('../package.json', import.meta.url));
  const compiled = await build({entryPoints:[new URL('../src/studio/MotionWorkspace.tsx', import.meta.url).pathname],bundle:true,write:false,format:'cjs',platform:'node',
    external:['react','react-dom','react-router-dom'],define:{'import.meta.env':'{"DEV":false,"BASE_URL":"/"}','import.meta.env.DEV':'false'}});
  const mod={exports:{}};
  new Function('require','module','exports',compiled.outputFiles[0].text)(require,mod,mod.exports);
  return {mod:mod.exports,React:require('react'),server:require('react-dom/server')};
}

const schema = { busy: false, version: 2, groups: [
  { id: 'scenes', title: 'Scenes', fields: [
    { key: 'scene.1.headline', group: 'scenes', label: 'Scene 1 · on-screen text', type: 'text', value: 'You have an idea.', impact: 'text', maxlength: 90 },
    { key: 'scene.1.narration', group: 'scenes', label: 'Scene 1 · narration', type: 'textarea', value: 'x', impact: 'voice', disabled: true, help: 'This scene has no narration.' },
    { key: 'scene.2.transition', group: 'scenes', label: 'Scene 2 · how it enters', type: 'select', value: 'iris', impact: 'assemble', options: [{ value: '', label: 'Auto' }, { value: 'iris', label: 'iris — reveal' }, { value: 'slice', label: 'slice — fast' }] } ] },
  { id: 'colours', title: 'Colours', fields: [{ key: 'palette.accent', group: 'colours', label: 'Accent', type: 'color', value: '#3B82F6', impact: 'colours' }] },
  { id: 'voice', title: 'Voice', fields: [{ key: 'voice.narrator', group: 'voice', label: 'Narrator', type: 'select', value: '', impact: 'audio', options: [{ value: '', label: 'Default' }, { value: 'eric', label: 'Eric' }] }] },
  { id: 'audio', title: 'Music & sound', fields: [{ key: 'music.level_db', group: 'audio', label: 'Music level (dB)', type: 'number', value: -10, impact: 'audio', min: -40, max: 0, step: 1 }] },
] };

test('the edit form is built entirely from what the server lists', async () => {
  const {mod,React,server} = await load();
  const html = server.renderToStaticMarkup(React.createElement(mod.MotionEditForm, { schema, draft: { 'scene.1.headline': 'New text' }, disabled: false, onChange: () => {} }));
  const doc = new JSDOM(html).window.document;
  assert.equal(doc.querySelectorAll('details.ec').length, 4);                                  // one card per group, the same card every other video type uses
  assert.equal(doc.querySelector('#mf-scene\\.1\\.headline').value, 'New text');             // an unsaved edit shows instead of the saved value
  assert.equal(doc.querySelector('#mf-scene\\.1\\.narration').disabled, true);               // a field the project cannot change is shown but locked, with its reason
  assert.match(doc.body.textContent, /This scene has no narration/);
  assert.deepEqual([...doc.querySelectorAll('#mf-scene\\.2\\.transition option')].map(o => o.value), ['', 'iris', 'slice']);   // options are the server's, not the browser's
  assert.equal(doc.querySelector('#mf-music\\.level_db').getAttribute('min'), '-40');
  assert.equal(doc.querySelector('#mf-palette\\.accent').getAttribute('type'), 'color');
  assert.match(doc.body.textContent, /1 تغییر اعمال‌نشده/);
});

test('everything is locked while a version is being made', async () => {
  const {mod,React,server} = await load();
  const doc = new JSDOM(server.renderToStaticMarkup(React.createElement(mod.MotionEditForm, { schema, draft: {}, disabled: true, onChange: () => {} }))).window.document;
  assert.ok([...doc.querySelectorAll('input,select,textarea')].every(node => node.disabled));
});
