import test from 'node:test';
import assert from 'node:assert/strict';
import handler from './api/runpod.mjs';

test('relay refuses unauthorized traffic, arbitrary paths, and never returns upstream secrets', async t => {
  const oldToken = process.env.RUNPOD_RELAY_TOKEN, oldKey = process.env.RUNPOD_API_KEY;
  const token = 'test-relay-token'.repeat(3);
  process.env.RUNPOD_RELAY_TOKEN = token;
  process.env.RUNPOD_API_KEY = 'test-provider-key';
  t.after(() => {
    for (const [key, old] of [['RUNPOD_RELAY_TOKEN', oldToken], ['RUNPOD_API_KEY', oldKey]]) {
      if (old === undefined) delete process.env[key]; else process.env[key] = old;
    }
  });
  let calls = 0;
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls++;
    if (url.pathname === '/v2/catalog/cpus') {
      return Response.json({ cpus: [{ id: 'cpu3c', availability: 'HIGH', price: { securePerVcpu: .04 } }] });
    }
    if (url.pathname === '/v2/pods/created')
      return Response.json({ name: 'editorgpt-containment-0123456789abcdef' });
    if (url.pathname === '/v2/registries/registry-test-id')
      return Response.json({ id: 'registry-test-id', password: 'must-not-return' });
    if (url.pathname === '/v2/pods') {
      const payload = JSON.parse(options.body);
      assert.equal(payload.registry, 'registry-test-id');
      assert.deepEqual(payload.cpu, { id: 'cpu3c', vcpuCount: 2 });
      assert.deepEqual(payload.entrypoint, ['python']);
      assert.deepEqual(payload.cmd, ['-m', 'app.render_cloud.containment_probe']);
      assert.equal(payload.env, undefined);
      if (payload.disk === 45)
        return Response.json({ message: 'Insufficient balance, private trace: example' }, { status: 400 });
      return Response.json({ id: 'created', cost: .06 }, { status: 201 });
    }
    if (url.pathname === '/v2/pods/created/logs') {
      const line = JSON.stringify({
        network_containment_passed: false, socketless_containment_passed: true, sandbox_certified: false,
        host_capabilities: { user_namespace: 'permission_denied', landlock_abi: 6, seccomp_listener: true,
          pidfd_getfd: false, leaked_detail: 'must-not-return' },
      });
      return new Response('data: ' + JSON.stringify({ source: 'container', line }) + '\n\n');
    }
    assert.equal(url.href, 'https://rest.runpod.io/v1/pods');
    assert.equal(options.headers.authorization, 'Bearer test-provider-key');
    assert.equal(options.redirect, 'error');
    if (options.method === 'POST') {
      const payload = JSON.parse(options.body);
      assert.equal(payload.containerRegistryAuthId, 'registry-test-id');
      return Response.json({ id: 'created' }, { status: 201 });
    }
    return Response.json([{ id: 'one', name: 'editorgpt-test', env: { SECRET: 'must-not-return' } }]);
  });
  async function call(body, auth = token) {
    const res = { setHeader() {}, status(code) { this.code = code; return this; },
      json(value) { return [this.code, value]; } };
    return handler({ method: 'POST', headers: { authorization: 'Bearer ' + auth }, body }, res);
  }
  assert.equal((await call({ method: 'GET', path: 'pods' }, 'wrong'))[0], 401);
  assert.equal((await call({ method: 'GET', path: 'https://example.com' }))[0], 403);
  assert.equal((await call({ method: 'DELETE', path: 'pods/../billing/pods' }))[0], 403);
  assert.equal(calls, 0);
  assert.deepEqual(await call({ method: 'GET', path: 'pods' }),
    [200, { upstream_status: 200, result: [{ id: 'one', name: 'editorgpt-test' }] }]);
  const payload = { name: 'editorgpt-test', imageName: 'ghcr.io/example/worker@sha256:' + 'a'.repeat(64),
    computeType: 'CPU', cloudType: 'SECURE', interruptible: false, volumeInGb: 0,
    ports: [], containerDiskInGb: 40, containerRegistryAuthId: 'registry-test-id' };
  assert.equal((await call({ method: 'POST', path: 'pods',
    payload: { ...payload, containerRegistryAuthId: 'https://invalid' } }))[0], 403);
  assert.deepEqual(await call({ method: 'POST', path: 'pods', payload }),
    [200, { upstream_status: 201, result: { id: 'created' } }]);
  assert.deepEqual(await call({ method: 'GET', path: 'canary/cpus' }),
    [200, { upstream_status: 200, result: [{ id: 'cpu3c', availability: 'HIGH', securePerVcpu: .04 }] }]);
  const name = 'editorgpt-containment-0123456789abcdef';
  const canary = { ...payload, name, vcpuCount: 2, cpuFlavorIds: ['cpu3c'] };
  assert.equal((await call({ method: 'POST', path: 'canary/pods', payload: { ...canary, env: {} } }))[0], 403);
  assert.deepEqual(await call({ method: 'POST', path: 'canary/pods', payload: canary }),
    [200, { upstream_status: 201, result: { id: 'created', cost: .06 } }]);
  assert.deepEqual(await call({ method: 'POST', path: 'canary/pods', payload: { ...canary, containerDiskInGb: 45 } }),
    [200, { upstream_status: 400, result: { rejection: 'billing' } }]);
  assert.deepEqual(await call({ method: 'GET', path: 'canary/registries/registry-test-id' }),
    [200, { upstream_status: 200, result: { id: 'registry-test-id' } }]);
  assert.deepEqual(await call({ method: 'GET', path: 'canary/pods/created/result', query: { name } }),
    [200, { upstream_status: 200, result: {
      network_containment_passed: false, socketless_containment_passed: true,
      host_capabilities: { user_namespace: 'permission_denied', landlock_abi: 6,
        seccomp_listener: true, pidfd_getfd: false },
    } }]);
});
