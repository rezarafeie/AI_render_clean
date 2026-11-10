import test from 'node:test';
import assert from 'node:assert/strict';
import { Readable, Writable } from 'node:stream';
import { once } from 'node:events';
import fs from 'node:fs';

const source = fs.readFileSync(new URL('./api/elevenlabs-clone.js', import.meta.url), 'utf8');
const { default: handler } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

async function request({method='POST', key='test-relay-key', type='multipart/form-data; boundary=xyz', body='--xyz--', length} = {}) {
  const req = Readable.from(body ? [Buffer.from(body)] : []);
  req.method=method;
  req.headers={'xi-api-key':key,'content-type':type,'content-length':String(length ?? Buffer.byteLength(body))};
  const chunks=[];
  const res=new Writable({write(chunk, encoding, done) {chunks.push(Buffer.from(chunk));done();}});
  res.headers={};
  res.status=code=>{res.code=code;return res;};
  res.setHeader=(name,value)=>{res.headers[name]=value;};
  res.json=data=>{res.end(JSON.stringify(data));return res;};
  const finished=once(res,'finish');
  await handler(req,res);
  await finished;
  return {code:res.code,body:Buffer.concat(chunks).toString()};
}

test('only an authenticated multipart POST reaches the voice-add upstream route', async t=>{
  const calls=[];
  t.mock.method(globalThis,'fetch',async (url,options)=>{ calls.push([String(url),options.method,options.headers['xi-api-key']]); return Response.json({voice_id:'v1'}); });
  const before=process.env.ELEVENLABS_API_KEY;
  process.env.ELEVENLABS_API_KEY='test-relay-key';
  try {
    assert.equal((await request()).code,200);
    assert.deepEqual(calls,[['https://api.elevenlabs.io/v1/voices/add','POST','test-relay-key']]);
    assert.equal((await request({key:'wrong'})).code,401);
    assert.equal((await request({method:'GET'})).code,405);
    assert.equal((await request({type:'application/json'})).code,415);
    assert.equal((await request({length:5_000_000})).code,413);
    assert.equal(calls.length,1);                                   // nothing else contacted the provider
  } finally {
    if (before===undefined) delete process.env.ELEVENLABS_API_KEY; else process.env.ELEVENLABS_API_KEY=before;
  }
});
