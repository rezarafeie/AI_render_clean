import test from 'node:test';
import assert from 'node:assert/strict';
import { Readable, Writable } from 'node:stream';
import { once } from 'node:events';
import fs from 'node:fs';

// package.json belongs to the unchanged production deployment. Import the ESM
// function without changing that shared project's module/build settings.
const source = fs.readFileSync(new URL('./api/elevenlabs.js', import.meta.url), 'utf8');
const { default: handler } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

async function request(path, {method='GET', query='', key='test-relay-key', body=''} = {}) {
  const req = Readable.from(body ? [Buffer.from(body)] : []);
  req.method=method;
  req.headers={'xi-api-key':key};
  req.query={path};
  req.url=`/api/elevenlabs/${path}${query}`;
  const chunks=[];
  const res=new Writable({write(chunk, encoding, done) {chunks.push(Buffer.from(chunk));done();}});
  res.headers={};
  res.status=code=>{res.code=code;return res;};
  res.setHeader=(name,value)=>{res.headers[name]=value;};
  res.json=data=>{res.end(JSON.stringify(data));return res;};
  const finished=once(res,'finish');
  await handler(req,res);
  await finished;
  return {code:res.code,headers:res.headers,body:Buffer.concat(chunks).toString()};
}

test('voice catalogs and models use authenticated read-only upstream paths', async t=>{
  t.mock.method(globalThis,'fetch',async (url,options)=>{
    assert.equal(url.origin,'https://api.elevenlabs.io');
    assert.equal(options.method,'GET');
    assert.equal(options.headers['xi-api-key'],'test-relay-key');
    assert.equal(options.body,undefined);
    return Response.json({voices:[]});
  });
  t.mock.method(process,'emitWarning',()=>{});
  const before=process.env.ELEVENLABS_API_KEY;
  process.env.ELEVENLABS_API_KEY='test-relay-key';
  try {
    for(const path of ['v1/voices','v2/voices','v1/models','v1/user/subscription']) {
      const r=await request(path);
      assert.equal(r.code,200);
      assert.equal(r.headers['cache-control'],'private, no-store');
    }
  } finally {if(before===undefined) delete process.env.ELEVENLABS_API_KEY; else process.env.ELEVENLABS_API_KEY=before;}
});

test('voice search/pagination survives rewriting but route/key/URL injection does not',async t=>{
  process.env.ELEVENLABS_API_KEY='test-relay-key';
  t.after(()=>delete process.env.ELEVENLABS_API_KEY);
  t.mock.method(globalThis,'fetch',async url=>{
    assert.equal(url.pathname,'/v2/voices');
    assert.deepEqual(url.searchParams.getAll('language'),['fa','en']);
    assert.equal(url.searchParams.get('page_size'),'100');
    assert.equal(url.searchParams.get('next_page_token'),'next+page');
    assert.equal(url.searchParams.has('path'),false);
    assert.equal(url.searchParams.has('url'),false);
    assert.equal(url.searchParams.has('xi-api-key'),false);
    return Response.json({voices:[],has_more:false});
  });
  const r=await request('v2/voices',{query:'?path=v2/voices&language=fa&language=en&page_size=100&next_page_token=next%2Bpage&url=https://evil.invalid&xi-api-key=wrong'});
  assert.equal(r.code,200);
});

test('missing/wrong authentication and disallowed methods never contact upstream',async t=>{
  process.env.ELEVENLABS_API_KEY='test-relay-key';
  t.after(()=>delete process.env.ELEVENLABS_API_KEY);
  t.mock.method(globalThis,'fetch',()=>assert.fail('forbidden upstream request'));
  assert.equal((await request('v2/voices',{key:''})).code,401);
  assert.equal((await request('v2/voices',{key:'wrong'})).code,401);
  assert.equal((await request('v2/voices',{method:'POST'})).code,404);
  assert.equal((await request('v1/voices/voice123',{method:'DELETE'})).code,404);
  assert.equal((await request('https://evil.invalid/v2/voices')).code,404);
  assert.equal((await request('../v2/voices')).code,404);
});

test('existing TTS, timestamp and STT POST bodies remain unchanged',async t=>{
  process.env.ELEVENLABS_API_KEY='test-relay-key';
  t.after(()=>delete process.env.ELEVENLABS_API_KEY);
  t.mock.method(globalThis,'fetch',async (url,options)=>{
    assert.equal(options.method,'POST');
    assert.equal(options.duplex,'half');
    assert.equal(await new Response(options.body).text(),'original-body');
    return new Response('existing-response',{headers:{'content-type':'audio/mpeg'}});
  });
  for(const path of ['v1/text-to-speech/voice123','v1/text-to-speech/voice123/with-timestamps','v1/speech-to-text']) {
    const r=await request(path,{method:'POST',body:'original-body'});
    assert.equal(r.code,200);
    assert.equal(r.body,'existing-response');
  }
});

test('upstream error status/body is preserved',async t=>{
  process.env.ELEVENLABS_API_KEY='test-relay-key';
  t.after(()=>delete process.env.ELEVENLABS_API_KEY);
  t.mock.method(globalThis,'fetch',async()=>Response.json({detail:{status:'missing_permissions'}},{status:403}));
  const r=await request('v2/voices');
  assert.equal(r.code,403);
  assert.equal(JSON.parse(r.body).detail.status,'missing_permissions');
});


test('a voice clone can be created, and no other voice change is allowed', async t=>{
  const seen=[];
  t.mock.method(globalThis,'fetch',async (url,options)=>{
    seen.push([options.method,url.pathname,options.headers['content-type']||'']);
    return Response.json({voice_id:'abc123'});
  });
  t.mock.method(process,'emitWarning',()=>{});
  const before=process.env.ELEVENLABS_API_KEY;
  process.env.ELEVENLABS_API_KEY='test-relay-key';
  try {
    const added=await request('v1/voices/add',{method:'POST',body:'--b--'});
    assert.equal(added.code,200);
    assert.deepEqual(seen.map(x=>x.slice(0,2)),[['POST','/v1/voices/add']]);
    for (const [method,path] of [['DELETE','v1/voices/abc123'],['DELETE','v1/voices'],['POST','v1/voices/abc123/edit'],['POST','v1/voices/add/extra'],['PATCH','v1/voices/abc123'],['DELETE','v1/voices/abc123/settings']]) {
      const blocked=await request(path,{method});
      assert.equal(blocked.code,404,`${method} ${path}`);
    }
    assert.equal((await request('v1/voices/add',{method:'POST',key:'wrong'})).code,401);
  } finally {
    if (before===undefined) delete process.env.ELEVENLABS_API_KEY; else process.env.ELEVENLABS_API_KEY=before;
  }
});
