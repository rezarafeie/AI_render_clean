import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { createRequire } from 'node:module';

test('Persian translation never throws on any text, including names Object.prototype has', async () => {
  const require = createRequire(new URL('../package.json', import.meta.url));
  const out = await build({ stdin: { contents: `export { translateText } from "./src/i18n/translate"; export * as fa from "./src/i18n/fa";`, resolveDir: new URL('..', import.meta.url).pathname, loader: 'ts' },
    bundle: true, write: false, format: 'cjs', platform: 'node', define: { 'import.meta.env': '{}' } });
  const mod = { exports: {} };
  globalThis.localStorage = { getItem: () => 'fa', setItem() {} };
  globalThis.document = { documentElement: { dataset: {}, setAttribute() {} } };
  new Function('require', 'module', 'exports', out.outputFiles[0].text)(require, mod, mod.exports);
  const { translateText } = mod.exports;
  for (const text of ['constructor', 'toString', '__proto__', 'valueOf', 'hasOwnProperty', 'isPrototypeOf', 'Version 1', '12', 'a'.repeat(20000), 'Delete idea: x', '  ']) {
    assert.doesNotThrow(() => translateText(text), text.slice(0, 20));
  }
  assert.equal(translateText('constructor'), 'constructor');          // not in the dictionary: it stays as written
});
