import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

test('cloud infrastructure controls are lazy loaded and administrator-only',()=>{
  const settings=readFileSync(new URL('../src/Settings.tsx',import.meta.url),'utf8');
  assert.match(settings,/React\.lazy\(\(\) => import\("\.\/settings\/CloudRender"\)/);
  assert.match(settings,/tab === "admin" && admin[\s\S]*?<React\.Suspense[\s\S]*?<CloudRenderSettings\/>/);
});

test('cloud controls use authenticated requests and distinguish unknown provider bills',()=>{
  const api=readFileSync(new URL('../src/api.ts',import.meta.url),'utf8');
  const component=readFileSync(new URL('../src/settings/CloudRender.tsx',import.meta.url),'utf8');
  assert.match(api,/renderCloudAdminRequest[\s\S]*?authFetch\(`\$\{BASE\}\/admin\/render-cloud/);
  assert.match(component,/provider_charge_usd == null \? "not reported"/);
  assert.doesNotMatch(component,/RUNPOD_API_KEY|AWS_SECRET_ACCESS_KEY|presigned/);
  assert.match(component,/max=\{data\.ceilings\[field\.key\]\}/);
  assert.match(component,/controller\.abort\(\)/);
});
