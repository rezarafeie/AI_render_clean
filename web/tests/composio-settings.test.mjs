import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';

test('connected apps requires server setup and never asks for browser credentials', async () => {
  const dom = new JSDOM('<div id="root"></div>', {url:'http://localhost/'});
  const previous = {window:globalThis.window,document:globalThis.document};
  Object.assign(globalThis,{window:dom.window,document:dom.window.document});
  const require=createRequire(new URL('../package.json',import.meta.url));
  const React=require('react'), {createRoot}=require('react-dom/client'), {flushSync}=require('react-dom');
  const built=await build({entryPoints:[new URL('../src/settings/Integrations.tsx',import.meta.url).pathname],bundle:true,write:false,format:'cjs',platform:'node',external:['react'],plugins:[{
    name:'mock-connected-apps-api', setup(b){
      b.onResolve({filter:/services\/hermesApi$/},()=>({path:'api',namespace:'mock'}));
      b.onLoad({filter:/.*/,namespace:'mock'},()=>({contents:`export default {
        getComposioSettings: async()=>({configured:false,enabled:false,applications:['instagram','googledrive']}),
        getAgent: async()=>({}), getAccounts: async()=>[], getInstagramSettings: async()=>({configured:false,instagram_user_id:null})
      };`}));
    }
  }]});
  const mod={exports:{}};
  new Function('require','module','exports',built.outputFiles[0].text)(require,mod,mod.exports);
  const root=createRoot(document.getElementById('root'));
  try {
    flushSync(()=>root.render(React.createElement(mod.exports.IntegrationsSettings)));
    await new Promise(resolve=>setTimeout(resolve,30));
    assert.match(document.body.textContent,/Server setup required/);
    // Nothing can be connected until the server is configured, and no credential is asked for outside the optional advanced block.
    assert.ok(![...document.querySelectorAll('button')].some(button=>/Connect|Reconnect/.test(button.textContent)&&!button.disabled));
    assert.equal(document.querySelectorAll('section > input, .set-row input[type=password]').length,0);
    assert.match(document.body.textContent,/Publishing and messaging stay disabled/);
  } finally {
    flushSync(()=>root.unmount()); dom.window.close(); Object.assign(globalThis,previous);
  }
});
