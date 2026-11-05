import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {build} from 'esbuild';
import {JSDOM} from 'jsdom';

test('plan approval locks immediately, rejects double clicks and waits for refreshed state', async () => {
  const dom = new JSDOM('<div id="root"></div>', {url:'http://localhost/'});
  const previous = {window:globalThis.window, document:globalThis.document};
  Object.assign(globalThis, {window:dom.window, document:dom.window.document});
  const require = createRequire(new URL('../package.json', import.meta.url));
  const React = require('react');
  const {createRoot} = require('react-dom/client');
  const {flushSync} = require('react-dom');
  let finishRequest, finishRefresh, calls = 0;
  globalThis.__planTestApi = {rawUrl:()=>'/raw',studioOutputUrl:()=>'/output',approveStudioPlan:()=>{calls++;return new Promise(resolve=>{finishRequest=resolve;});}};
  const compiled = await build({entryPoints:[new URL('../src/studio/PlanReview.tsx',import.meta.url).pathname],bundle:true,write:false,format:'cjs',platform:'node',external:['react','react-dom'],plugins:[{
    name:'test-boundaries',setup(b){
      b.onResolve({filter:/^\.\.\/(api|AuthenticatedMedia|ui)$/},args=>({path:args.path,namespace:'test'}));
      b.onLoad({filter:/.*/,namespace:'test'},args=>({contents:args.path.endsWith('/api')?'export const api=globalThis.__planTestApi;':args.path.endsWith('/ui')?'export const friendlyError=String;':'export const AuthenticatedMedia=()=>null;'}));
    }
  }]});
  const mod = {exports:{}};
  new Function('require','module','exports',compiled.outputFiles[0].text)(require,mod,mod.exports);
  const content = {
    goal:'',audience:'',message:'',tone:'',concept:{name:'',angle:''},concepts:[],style_options:[],structure:[],
    hook:{text:'آزمایش',highlight:[]},style:{id:'talking_1',label:'صحبتی',summary:''},
    look:{preset:'default',accent_color:'#FFFFFF',caption_font:'default',zoom:100,key_moments:true},
    brand:{name:'',tagline:'',cta:'',logo:{enabled:false,motion:'pop',has_logo:false}},
    pictures:[],audio:{voice:'',sfx:'',music:''},format:{aspect:'9:16',resolution:'1080p',fps:30},
    engines:[],estimate:{note:'',render:null},duration_s:30,
  };
  const project={id:'p',state:{workflow:'awaiting_approval',plan:{versions:[{id:'v1',n:1,content}],approved_id:null}}};
  const root=createRoot(document.getElementById('root'));
  try {
    flushSync(()=>root.render(React.createElement(mod.exports.PlanReview,{project,onChanged:()=>new Promise(resolve=>{finishRefresh=resolve;})})));
    const button=[...document.querySelectorAll('button')].find(b=>b.textContent.includes('تأیید و شروع رندر'));
    button.click(); button.click();
    assert.equal(calls,1);
    assert.equal(button.disabled,true);
    assert.match(button.textContent,/در حال شروع/);
    assert.equal(document.querySelector('.plan').getAttribute('aria-busy'),'true');
    finishRequest(); await new Promise(resolve=>setTimeout(resolve,0));
    assert.equal(button.disabled,true,'must stay busy while refreshed project is pending');
    finishRefresh(); await new Promise(resolve=>setTimeout(resolve,20));
    assert.equal(document.querySelector('.plan').getAttribute('aria-busy'),'false');
  } finally {
    flushSync(()=>root.unmount()); dom.window.close();
    Object.assign(globalThis,previous); delete globalThis.__planTestApi;
  }
});
