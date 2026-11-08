import { createHash, timingSafeEqual } from 'node:crypto';

const origin = 'https://rest.runpod.io/v1/';
const catalog = 'https://api.runpod.io/v2/';
const canaryName = /^editorgpt-containment-[a-f0-9]{16}$/;
const podFields = ['id', 'name', 'image', 'imageName', 'costPerHr', 'adjustedCostPerHr', 'memoryInGb', 'vcpuCount'];
const createFields = ['name', 'imageName', 'computeType', 'cloudType', 'interruptible', 'containerDiskInGb',
  'volumeInGb', 'ports', 'env', 'cpuFlavorIds', 'vcpuCount', 'gpuTypeIds', 'gpuCount', 'containerRegistryAuthId'];
const fields = (value, keys) => Object.fromEntries(keys.filter(k =>
  ['string', 'number'].includes(typeof value?.[k])).map(k => [k, value[k]]));

function hostCapabilities(data) {
  const result = {};
  for (const key of ['user_namespace', 'network_namespace']) {
    if (['ok', 'permission_denied', 'failed'].includes(data?.[key])) result[key] = data[key];
  }
  for (const key of ['process_vm_readv', 'pidfd_getfd', 'seccomp_listener']) {
    if (typeof data?.[key] === 'boolean') result[key] = data[key];
  }
  if (Number.isInteger(data?.landlock_abi) && data.landlock_abi >= 0 && data.landlock_abi <= 100)
    result.landlock_abi = data.landlock_abi;
  return result;
}

function canaryRejection(data) {
  const parts = [data?.code, data?.message, data?.detail, data?.error?.code, data?.error?.message];
  const reason = parts.filter(value => typeof value === 'string').join(' ').toLowerCase();
  if (/balance|funds|credit|payment|billing/.test(reason)) return 'billing';
  if (/capacity|stock|no available|no machine|no instance/.test(reason)) return 'capacity';
  if (/digest|sha256|image|docker/.test(reason)) return 'container_image';
  if (/registry|credential/.test(reason)) return 'registry';
  if (/v.?cpu|cpu|disk|flavor/.test(reason)) return 'resource_configuration';
  return 'unclassified';
}

function upstreamRequest(input) {
  const { method, path, payload, query } = input ?? {};
  if (method === 'GET' && path === 'canary/cpus')
    return [new URL('catalog/cpus?include=AVAILABILITY&product=POD&vcpuCount=2', catalog), { method }];
  if (method === 'GET' && typeof path === 'string' && /^canary\/registries\/[\w-]{1,128}$/.test(path))
    return [new URL(path.slice('canary/'.length), catalog), { method }];
  if (method === 'GET' && path === 'pods') return [new URL('pods', origin), { method }];
  if (method === 'DELETE' && typeof path === 'string' && /^pods\/[\w-]{1,100}$/.test(path))
    return [new URL(path, origin), { method }];
  if (method === 'GET' && path === 'billing/pods' && typeof query?.startTime === 'string' &&
      query.startTime.length <= 40 && Number.isFinite(Date.parse(query.startTime))) {
    const url = new URL(path, origin);
    url.search = new URLSearchParams({ grouping: 'podId', bucketSize: 'day', startTime: query.startTime });
    return [url, { method }];
  }
  const canary = path === 'canary/pods';
  if (method === 'POST' && (path === 'pods' || canary) && payload && typeof payload === 'object' &&
      Object.keys(payload).every(key => createFields.includes(key)) &&
      (payload.containerRegistryAuthId === undefined ||
        (typeof payload.containerRegistryAuthId === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(payload.containerRegistryAuthId))) &&
      typeof payload.name === 'string' && /^editorgpt-[\w-]{1,190}$/.test(payload.name) &&
      typeof payload.imageName === 'string' && /^[^\s]+@sha256:[a-f0-9]{64}$/.test(payload.imageName) &&
      ['CPU', 'GPU'].includes(payload.computeType) && payload.cloudType === 'SECURE' &&
      payload.interruptible === false && payload.volumeInGb === 0 &&
      Array.isArray(payload.ports) && !payload.ports.length &&
      Number.isInteger(payload.containerDiskInGb) && payload.containerDiskInGb >= 10 &&
      payload.containerDiskInGb <= 200) {
    if (canary) {
      if (!canaryName.test(payload.name) || payload.computeType !== 'CPU' || payload.vcpuCount !== 2 ||
          payload.env !== undefined || !payload.containerRegistryAuthId ||
          !Array.isArray(payload.cpuFlavorIds) || payload.cpuFlavorIds.length !== 1 ||
          !/^cpu[0-9]+[a-z]+$/.test(payload.cpuFlavorIds[0])) return null;
      return [new URL('pods', catalog), { method, body: JSON.stringify({
        name: payload.name, image: payload.imageName, cloud: 'SECURE',
        cpu: { id: payload.cpuFlavorIds[0], vcpuCount: 2 },
        disk: payload.containerDiskInGb, registry: payload.containerRegistryAuthId,
        entrypoint: ['python'], cmd: ['-m', 'app.render_cloud.containment_probe'],
      }) }];
    }
    return [new URL(path, origin), { method, body: JSON.stringify(payload) }];
  }
  return null;
}

async function probeResult(body, headers, signal) {
  const { path, query } = body;
  const match = /^canary\/pods\/([a-z0-9-]{1,100})\/result$/i.exec(path);
  if (!match || !canaryName.test(query?.name)) return { status: 403, error: 'operation_not_allowed' };
  const id = match[1];
  const request = { headers, signal, redirect: 'error' };
  const pod = await fetch(new URL('pods/' + id, catalog), request);
  if (!pod.ok || (await pod.json()).name !== query.name) return { status: 404, error: 'canary_not_found' };
  const logs = await fetch(new URL('pods/' + id + '/logs?source=container&tail=30', catalog), {
    ...request, headers: { ...headers, accept: 'text/event-stream' }, signal: AbortSignal.timeout(4500),
  });
  if (!logs.ok) return { status: 200, result: null, upstream_status: logs.status };
  const stream = logs.body.pipeThrough(new TextDecoderStream());
  let buffer = '';
  try {
    for await (const chunk of stream) {
      buffer += chunk;
      if (buffer.length > 64_000) break;
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data:')) continue;
        try {
          const event = JSON.parse(line.slice(5));
          if (event.source !== 'container') continue;
          const probe = JSON.parse(event.line);
          if (typeof probe.network_containment_passed === 'boolean' && probe.sandbox_certified === false)
            return { status: 200, upstream_status: 200, result: {
              network_containment_passed: probe.network_containment_passed,
              ...(typeof probe.socketless_containment_passed === 'boolean'
                ? { socketless_containment_passed: probe.socketless_containment_passed } : {}),
              ...(probe.host_capabilities ? { host_capabilities: hostCapabilities(probe.host_capabilities) } : {}),
            } };
        } catch { /* Ignore unrelated log entries. */ }
      }
    }
  } catch (error) {
    if (error.name !== 'AbortError' && error.name !== 'TimeoutError') throw error;
  }
  return { status: 200, upstream_status: 200, result: null };
}

// Standalone /api Node function, like the other EditorGPT relays.
export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  if (req.method !== 'POST') return res.status(405).json({ error: 'method_not_allowed' });
  const key = process.env.RUNPOD_RELAY_TOKEN || '';
  const presented = req.headers.authorization;
  const digest = value => createHash('sha256').update(value).digest();
  if (key.length < 32 || typeof presented !== 'string' ||
      !timingSafeEqual(digest(presented), digest('Bearer ' + key)))
    return res.status(401).json({ error: 'unauthorized' });
  const apiKey = process.env.RUNPOD_API_KEY;
  if (!apiKey) return res.status(503).json({ error: 'provider_unconfigured' });
  let body;
  try { body = typeof req.body === 'string' ? JSON.parse(req.body) : req.body; }
  catch { return res.status(400).json({ error: 'invalid_json' }); }
  const headers = { authorization: 'Bearer ' + apiKey, 'content-type': 'application/json' };
  try {
    if (body?.method === 'GET' && typeof body.path === 'string' && body.path.endsWith('/result')) {
      const { status, ...value } = await probeResult(body, headers, AbortSignal.timeout(9000));
      return res.status(status).json(value);
    }
    const target = upstreamRequest(body);
    if (!target) return res.status(403).json({ error: 'operation_not_allowed' });
    const [url, options] = target;
    const upstream = await fetch(url, {
      ...options, headers,
      redirect: 'error', signal: AbortSignal.timeout(22_000),
    });
    if (body.path === 'canary/pods' && upstream.status >= 400 && upstream.status < 500) {
      const error = await upstream.json().catch(() => null);
      return res.status(200).json({
        upstream_status: upstream.status, result: { rejection: canaryRejection(error) },
      });
    }
    let result = null;
    if (upstream.ok && options.method !== 'DELETE') {
      const data = await upstream.json();
      if (body.path === 'canary/cpus') return res.status(200).json({
        upstream_status: upstream.status, result: data.cpus.map(cpu => ({
          ...fields(cpu, ['id', 'availability']), ...fields(cpu.price, ['securePerVcpu']),
        })),
      });
      if (body.path.startsWith('canary/registries/'))
        return res.status(200).json({ upstream_status: upstream.status, result: fields(data, ['id']) });
      if (body.path === 'canary/pods') return res.status(200).json({
        upstream_status: upstream.status, result: fields(data, [...podFields, 'cost']),
      });
      if (options.method === 'GET' && !Array.isArray(data)) throw new Error('Unexpected result');
      result = options.method === 'POST' ? fields(data, podFields) :
        data.map(item => fields(item, url.pathname.endsWith('/billing/pods') ? ['podId', 'amount', 'time'] : podFields));
    }
    return res.status(200).json({ upstream_status: upstream.status, result });
  } catch {
    // No body, credentials, signed URLs or upstream error strings in logs.
    console.error('runpod_relay_upstream_failed');
    return res.status(502).json({ error: 'upstream_uncertain' });
  }
}
