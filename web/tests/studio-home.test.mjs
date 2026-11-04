import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {build} from 'esbuild';
import {JSDOM} from 'jsdom';

async function load() {
  const require = createRequire(new URL('../package.json', import.meta.url));
  const compiled = await build({entryPoints:[new URL('../src/studio/Home.tsx', import.meta.url).pathname],bundle:true,write:false,format:'cjs',platform:'node',
    external:['react','react-dom','react-router-dom'],define:{'import.meta.env':'{"DEV":false,"BASE_URL":"/"}','import.meta.env.DEV':'false'}});
  const mod={exports:{}};
  new Function('require','module','exports',compiled.outputFiles[0].text)(require,mod,mod.exports);
  return {mod:mod.exports,React:require('react'),server:require('react-dom/server'),router:require('react-router-dom')};
}

test('the start page shows a skeleton for suggestions and recent edits until they arrive, and has no card besides them', async () => {
  const {mod,React,server,router} = await load();
  const html = server.renderToStaticMarkup(React.createElement(router.MemoryRouter,null,React.createElement(mod.StudioHomePage,{composer:React.createElement('div',{id:'composer'}),authenticated:true,onPrompt:()=>{}})));
  const doc = new JSDOM(html).window.document;
  assert.ok(doc.querySelector('#composer'));
  assert.equal(doc.querySelectorAll('.home-skeleton').length,2);                       // suggestions and recent edits each wait with a skeleton
  assert.equal(doc.querySelector('a.home-insta'),null);                                 // InstaGPT keeps its button in the header only
  assert.ok(doc.querySelector('.home-recent-head h2'));
});

test('a signed-out visitor gets the composer and a login note, not a skeleton', async () => {
  const {mod,React,server,router} = await load();
  const html = server.renderToStaticMarkup(React.createElement(router.MemoryRouter,null,React.createElement(mod.StudioHomePage,{composer:React.createElement('div',{id:'composer'}),authenticated:false,onPrompt:()=>{}})));
  const doc = new JSDOM(html).window.document;
  assert.equal(doc.querySelector('.home-skeleton'),null);
  assert.match(doc.querySelector('.home-note').textContent,/Log in/);
});

test('every state of a piece of work has its own tone', async () => {
  const {mod} = await load();
  assert.deepEqual(['running','needs_input','failed','ready','draft'].map(mod.statusTone),['working','warning','error','success','idle']);
});
