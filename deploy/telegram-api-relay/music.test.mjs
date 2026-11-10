import test from 'node:test';
import assert from 'node:assert/strict';
import { Readable, Writable } from 'node:stream';
import { once } from 'node:events';
import fs from 'node:fs';

const load = async name => {
  const source = fs.readFileSync(new URL(`./api/${name}.js`, import.meta.url), 'utf8');
  return (await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`)).default;
};
const music = await load('elevenlabs-music');
const jamendo = await load('jamendo');

async function call(handler, {method='GET', url='/', key='test-relay-key', headers={}, body=''} = {}) {
  const req = Readable.from(body ? [Buffer.from(body)] : []);
  req.method = method; req.url = url; req.headers = {...(key ? {'xi-api-key': key} : {}), ...headers};
  const chunks = [];
  const res = new Writable({write(chunk, enc, done) { chunks.push(Buffer.from(chunk)); done(); }});
  res.headers = {}; res.code = 200;
  res.status = code => { res.code = code; return res; };
  res.setHeader = (name, value) => { res.headers[name] = value; };
  res.json = data => { res.end(JSON.stringify(data)); return res; };
  res.redirect = (code, to) => { res.code = code; res.headers.location = to; res.end(); return res; };
  const finished = once(res, 'finish');
  await handler(req, res);
  await finished;
  return {code: res.code, headers: res.headers, body: Buffer.concat(chunks)};
}
const withKey = async fn => { process.env.ELEVENLABS_API_KEY = 'test-relay-key'; try { await fn(); } finally { delete process.env.ELEVENLABS_API_KEY; } };

test('music: only an authenticated JSON POST reaches the music composer, with a checked output_format', async t => withKey(async () => {
  const seen = [];
  t.mock.method(globalThis, 'fetch', async (url, options) => { seen.push({url, options}); return new Response(Buffer.from('ID3audio'), {headers: {'content-type': 'audio/mpeg', 'song-id': 's1'}}); });
  const body = JSON.stringify({prompt: 'calm', music_length_ms: 20000});
  const ok = await call(music, {method: 'POST', url: '/api/elevenlabs-music?output_format=mp3_44100_128', headers: {'content-type': 'application/json', 'content-length': String(body.length)}, body});
  assert.equal(ok.code, 200); assert.equal(ok.headers['song-id'], 's1'); assert.equal(ok.headers['cache-control'], 'private, no-store');
  assert.equal(seen[0].url.origin + seen[0].url.pathname, 'https://api.elevenlabs.io/v1/music');
  assert.equal(seen[0].url.searchParams.get('output_format'), 'mp3_44100_128'); assert.equal(seen[0].options.headers['xi-api-key'], 'test-relay-key');
  const bad = await call(music, {method: 'POST', url: '/api/elevenlabs-music?output_format=../../x', headers: {'content-type': 'application/json', 'content-length': '2'}, body: '{}'});
  assert.equal(bad.code, 400);
  assert.equal((await call(music, {method: 'POST', key: 'wrong', headers: {'content-type': 'application/json', 'content-length': '2'}, body: '{}'})).code, 401);
  assert.equal((await call(music, {method: 'GET'})).code, 405);
  assert.equal((await call(music, {method: 'POST', headers: {'content-type': 'text/plain', 'content-length': '2'}, body: '{}'})).code, 415);
  assert.equal((await call(music, {method: 'POST', headers: {'content-type': 'application/json', 'content-length': String(1 << 20)}, body: '{}'})).code, 413);
  assert.equal(seen.length, 1);
}));

test('jamendo: tracks search forwards only allow-listed parameters; downloads only from jamendo.com over https', async t => withKey(async () => {
  const seen = [];
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    seen.push(String(url));
    return String(url).includes('/v3.0/tracks') ? Response.json({results: []}) : new Response(Buffer.from('ID3audio'), {headers: {'content-type': 'audio/mpeg', 'content-length': '8'}});
  });
  const search = await call(jamendo, {url: '/api/jamendo?client_id=cid&search=calm&limit=5&evil=1&url=http://x&xi-api-key=zzz'});
  assert.equal(search.code, 200);
  const sent = new URL(seen[0]);
  assert.equal(sent.origin + sent.pathname, 'https://api.jamendo.com/v3.0/tracks/'); assert.equal(sent.searchParams.get('search'), 'calm');
  assert.equal(sent.searchParams.has('evil'), false); assert.equal(sent.searchParams.has('url'), false); assert.equal(sent.searchParams.has('xi-api-key'), false);
  assert.equal((await call(jamendo, {url: '/api/jamendo?search=calm'})).code, 400);
  const good = await call(jamendo, {url: `/api/jamendo?download=${encodeURIComponent('https://prod-1.storage.jamendo.com/download/track/1/mp32/')}`});
  assert.equal(good.code, 200); assert.equal(good.headers['content-type'], 'audio/mpeg');
  for (const evil of ['http://prod-1.storage.jamendo.com/x', 'https://evil.com/x', 'https://jamendo.com.evil.com/x', 'https://user:pw@mp3d.jamendo.com/x', 'file:///etc/passwd', 'https://169.254.169.254/']) {
    const r = await call(jamendo, {url: `/api/jamendo?download=${encodeURIComponent(evil)}`});
    assert.equal(r.code, 400, evil);
  }
  assert.equal((await call(jamendo, {url: '/api/jamendo?client_id=x', key: 'wrong'})).code, 401);
  assert.equal((await call(jamendo, {method: 'POST', url: '/api/jamendo'})).code, 405);
}));
