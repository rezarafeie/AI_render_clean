import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {build} from 'esbuild';
import {JSDOM} from 'jsdom';

test('each build step shows its tools, its duration and the agent summary', async () => {
  const require = createRequire(new URL('../package.json', import.meta.url));
  const compiled = await build({entryPoints:[new URL('../src/studio/MotionGraphic.tsx', import.meta.url).pathname],bundle:true,write:false,format:'cjs',platform:'node',external:['react','react-dom','react-router-dom'],define:{'import.meta.env':'{"DEV":false,"BASE_URL":"/"}','import.meta.env.DEV':'false'}});
  const mod={exports:{}};
  new Function('require','module','exports',compiled.outputFiles[0].text)(require,mod,mod.exports);
  const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
  const t=Date.now();
  const steps=[
    {key:'plan',label:'طرح آماده شد',status:'done',startedAt:t-90000,endedAt:t-60000,events:[],notes:[]},
    {key:'voice',label:'دارم نریشن را می‌سازم',status:'active',startedAt:t-12000,endedAt:t,progress:7,events:[],notes:[]},
  ];
  const html=renderToStaticMarkup(React.createElement(mod.exports.MotionSteps,{steps,live:true,now:t,summaries:{plan:'طرح حرکت: شش صحنه.',ready:'تمام شد'}}));
  const doc=new JSDOM(html).window.document;
  const rows=[...doc.querySelectorAll('.mg-step')];
  assert.equal(rows.length,2);                                                   // the "ready" summary waits until the work is done
  assert.deepEqual([...rows[0].querySelectorAll('.mg-tool')].map(n=>n.textContent),['مدل برنامه‌ریز']);
  assert.deepEqual([...rows[1].querySelectorAll('.mg-tool')].map(n=>n.textContent),['ElevenLabs']);
  assert.equal(rows[0].querySelector('.mg-step-summary').textContent,'طرح حرکت: شش صحنه.');
  assert.ok(rows[0].querySelector('.mg-step-time'));
  assert.ok(rows[1].querySelector('.spinner'));
  const done=new JSDOM(renderToStaticMarkup(React.createElement(mod.exports.MotionSteps,{steps:[steps[0]],live:false,now:t,summaries:{ready:'تمام شد'}}))).window.document;
  assert.equal(done.querySelector('.mg-step-ready .mg-step-summary').textContent,'تمام شد');
});
