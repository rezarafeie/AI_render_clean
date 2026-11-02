import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {build} from 'esbuild';
import {JSDOM} from 'jsdom';

const require=createRequire(new URL('../package.json',import.meta.url));
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const compiled=await build({entryPoints:[new URL('../src/studio/RenderProgress.tsx',import.meta.url).pathname],bundle:true,write:false,format:'cjs',platform:'node',external:['react'],plugins:[{
  name:'view',setup(b){b.onResolve({filter:/^\.\/model$/},()=>({path:'model',namespace:'mock'}));b.onLoad({filter:/.*/,namespace:'mock'},()=>({contents:'export const renderView=()=>({phase:"rendering",progress:46,stageLabel:"تبدیل فایل"});'}));}
}]});
const mod={exports:{}};new Function('require','module','exports',compiled.outputFiles[0].text)(require,mod,mod.exports);
function render(metrics){return new JSDOM(renderToStaticMarkup(React.createElement(mod.exports.RenderProgress,{project:{updated_at:new Date().toISOString(),state:{last_observed:{stage:'conversion',render_metrics:metrics}}}})));}

test('stage percentage is measured separately from weighted overall progress',()=>{
  const now=Date.now()/1000;
  const dom=render({stage:'conversion',stage_percent:28.4,reported_at:now,stage_eta_at:now+180});
  assert.equal(dom.window.document.querySelector('[role="progressbar"]').getAttribute('aria-valuenow'),'28.4');
  assert.match(dom.window.document.body.textContent,/پایان تخمینی تبدیل فایل/);
  assert.doesNotMatch(dom.window.document.body.textContent,/پایان تخمینی رندر/);
  dom.window.close();
});

test('stale telemetry cannot display a stale end time',()=>{
  const now=Date.now()/1000;
  const dom=render({stage:'conversion',stage_percent:28.4,reported_at:now-90,render_eta_at:now+180});
  assert.doesNotMatch(dom.window.document.body.textContent,/پایان تخمینی/);
  dom.window.close();
});
