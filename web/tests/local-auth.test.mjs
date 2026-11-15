import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';

test('isolated Hermes preview requires JWT auth without changing ordinary localhost defaults', async () => {
  const before = globalThis.window;
  globalThis.window = { location: {hostname:'127.0.0.1',pathname:'/insta/settings'} };
  try {
    for (const requireAuth of [false,true]) {
      const compiled=await build({entryPoints:[new URL('../src/auth.ts',import.meta.url).pathname],bundle:true,write:false,
        format:'cjs',platform:'node',define:{'import.meta.env':JSON.stringify({DEV:true,VITE_REQUIRE_LOCAL_AUTH:requireAuth?'1':undefined})}});
      const mod={exports:{}};
      new Function('module','exports',compiled.outputFiles[0].text)(mod,mod.exports);
      assert.equal(mod.exports.isLocalDevelopment,!requireAuth);
      assert.equal(mod.exports.isAuthenticated(),!requireAuth);
    }
  } finally {globalThis.window=before;}
});
