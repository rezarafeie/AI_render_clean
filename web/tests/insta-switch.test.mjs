import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {build} from 'esbuild';
import {JSDOM} from 'jsdom';

async function load() {
  const require = createRequire(new URL('../package.json', import.meta.url));
  const compiled = await build({entryPoints:[new URL('../src/components/InstaSwitch.tsx', import.meta.url).pathname],bundle:true,write:false,format:'cjs',platform:'node',
    external:['react','react-dom','react-router-dom'],define:{'import.meta.env':'{"DEV":false,"BASE_URL":"/"}','import.meta.env.DEV':'false'}});
  const mod={exports:{}};
  new Function('require','module','exports',compiled.outputFiles[0].text)(require,mod,mod.exports);
  return {mod:mod.exports,React:require('react'),server:require('react-dom/server'),router:require('react-router-dom')};
}

test('counts are short and a missing number is left out', async () => {
  const {mod} = await load();
  assert.equal(mod.compactCount(12400),'12.4K');
  assert.equal(mod.compactCount(980),'980');
  assert.equal(mod.compactCount(null),'');
});

test('before the page is known the button is only the Instagram mark, with no label and no "not connected"', async () => {
  const {mod,React,server,router} = await load();
  const html = server.renderToStaticMarkup(React.createElement(router.MemoryRouter,null,React.createElement(mod.InstaSwitch,{enabled:true})));
  const link = new JSDOM(html).window.document.querySelector('a.switch-btn');
  assert.equal(link.getAttribute('href'),'/hermes');
  assert.equal(link.textContent.trim(),'');
  assert.match(link.getAttribute('aria-label'),/InstaGPT/);
  assert.equal(link.querySelector('.switch-avatar'),null);
});
