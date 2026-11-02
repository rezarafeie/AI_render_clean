import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {build} from 'esbuild';
import {JSDOM} from 'jsdom';

test('long elapsed time is separate from the step label and unsplit percentage', async () => {
  const require = createRequire(new URL('../package.json', import.meta.url));
  const compiled = await build({entryPoints:[new URL('../src/studio/Activity.tsx', import.meta.url).pathname],bundle:true,write:false,format:'cjs',platform:'node',external:['react','react-dom','react-router-dom']});
  const mod={exports:{}};
  new Function('require','module','exports',compiled.outputFiles[0].text)(require,mod,mod.exports);
  const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
  const step={key:'active',status:'active',label:'دارم طرح کلی را می‌نویسم: صحنه‌ها، متن‌ها و رنگ‌ها',progress:6,startedAt:Date.now()-321*60000,endedAt:Date.now(),events:[],notes:[]};
  const dom=new JSDOM(renderToStaticMarkup(React.createElement(mod.exports.ActivityBlock,{steps:[step],live:true})));
  const doc=dom.window.document;
  assert.equal(doc.querySelector('.act-row .act-elapsed'),null);
  assert.equal(doc.querySelector('.act-row .act-pct'),null);
  assert.ok(doc.querySelector('.act-timing .act-pct'));
  assert.ok(doc.querySelector('.act-timing .act-elapsed'));
  assert.equal(doc.querySelector('.act-pct').textContent,'6%');
  assert.equal(doc.querySelector('.act-pct').getAttribute('dir'),'ltr');
  assert.equal(doc.querySelector('[role="progressbar"]').getAttribute('aria-valuenow'),'6');
  dom.window.close();
});
