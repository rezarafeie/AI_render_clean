import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const main = readFileSync(new URL('../src/main.tsx', import.meta.url), 'utf8');

test('the InstaGPT workspace is routed at /insta and the old /hermes address redirects there', () => {
  assert.match(main, /<Route path="insta" element=\{<RequireAuth><HermesLayout\/>/);
  assert.doesNotMatch(main, /<Route path="hermes" element=\{<RequireAuth>/);
  assert.match(main, /<Route path="hermes\/\*" element=\{<FromHermes\/>\}/);
});
