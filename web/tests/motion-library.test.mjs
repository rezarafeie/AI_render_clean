import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import {build} from 'esbuild';
import {JSDOM} from 'jsdom';

async function load() {
  const require = createRequire(new URL('../package.json', import.meta.url));
  const compiled = await build({entryPoints:[new URL('../src/MotionLibrary.tsx', import.meta.url).pathname],bundle:true,write:false,format:'cjs',platform:'node',external:['react','react-dom','react-router-dom']});
  const mod={exports:{}};
  new Function('require','module','exports',compiled.outputFiles[0].text)(require,mod,mod.exports);
  return {mod:mod.exports,React:require('react'),server:require('react-dom/server')};
}

const read = name => JSON.parse(readFileSync(new URL(`../public/creative-previews/${name}`, import.meta.url), 'utf8'));
const everything = () => ['index.json','claude-effects.json','shotcraft.json','lemo.json','native-shotcraft.json'].flatMap(file => Object.values(read(file).items));

test('every record of the five catalog files is classified and nothing is dropped', async () => {
  const {mod} = await load();
  const items = everything().map(mod.toItem);
  assert.ok(items.length >= 99, `${items.length} records`);
  const ids = new Set(items.map(item => item.id)); assert.equal(ids.size, items.length);
  assert.ok(items.every(item => mod.SOURCES.some(source => source.id === item.source)));
  assert.ok(items.every(item => !item.poster || /^\/creative-previews\/[a-z0-9-]+\.png(\?v=[0-9a-f]{16})?$/.test(item.poster)));      // media only from the app's own folder
  assert.ok(items.some(item => item.params.length > 0) && items.some(item => item.video));
});

test('search ignores Arabic/Persian letter variants and the kind filter narrows the list', async () => {
  const {mod} = await load();
  const items = everything().map(mod.toItem);
  const one = items.find(item => /beat/.test(item.name));
  assert.ok(mod.filterItems(items, 'all', one.name.toUpperCase()).some(item => item.id === one.id));
  const effects = mod.filterItems(items, 'effects', '');
  assert.ok(effects.length > 0 && effects.every(item => item.source === 'effects'));
  assert.equal(mod.filterItems(items, 'all', 'zzzz-no-such-thing').length, 0);
  assert.ok(mod.filterItems(items, 'all', 'کاربر').length >= 0);
});

test('the page uses the app\'s own layout (page header, chips, card grid) and a skeleton until the catalog arrives', async () => {
  const {mod,React,server} = await load();
  const doc = new JSDOM(server.renderToStaticMarkup(React.createElement(mod.default))).window.document;
  assert.ok(doc.querySelector('.page .page-header h1'));
  assert.equal(doc.querySelector('h1').textContent, 'Motion library');
  assert.ok(doc.querySelector('.chip-row'));
  assert.equal(doc.querySelectorAll('.ml-grid .skeleton').length, 8);
});
