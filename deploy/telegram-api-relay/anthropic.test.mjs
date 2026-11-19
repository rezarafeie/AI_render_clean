import assert from "node:assert/strict";
import { once } from "node:events";
import { createServer } from "node:http";
import test from "node:test";
import handler from "./api/anthropic.js";

test("Anthropic relay authenticates, streams immediately and keeps upstream status", async () => {
  const nativeFetch = globalThis.fetch;
  const secret = "local-test-secret".repeat(3);
  const previous = process.env.RELAY_SECRET;
  process.env.RELAY_SECRET = secret;
  let data;
  let next;
  let fail = false;
  globalThis.fetch = async (url, request) => {
    data = { url: String(url), request };
    if (fail) return new Response('{"type":"error"}', { status: 429, headers: { "retry-after": "2" } });
    const body = new ReadableStream({ start(controller) {
      controller.enqueue(Buffer.from("event: message_start\n\n"));
      next = () => { controller.enqueue(Buffer.from("event: message_stop\n\n")); controller.close(); };
    } });
    return new Response(body, { headers: { "content-type": "text/event-stream", "request-id": "req_1" } });
  };
  const server = createServer((req, res) => {
    res.status = code => { res.statusCode = code; return res; };
    res.json = value => { res.setHeader("content-type", "application/json"); res.end(JSON.stringify(value)); };
    void handler(req, res);
  }).listen(0, "127.0.0.1");
  await once(server, "listening");
  const url = `http://127.0.0.1:${server.address().port}/api/anthropic?beta=true&host=ignore`;
  const headers = { "x-relay-secret": secret, "x-api-key": "test-api-key", "anthropic-beta": "beta-test" };
  try {
    assert.equal((await nativeFetch(url, { method: "POST" })).status, 401);
    assert.equal((await nativeFetch(url, { headers })).status, 405);
    assert.equal(data, undefined);
    const result = await nativeFetch(url, { method: "POST", headers, body: '{"stream":true}' });
    assert.equal(result.headers.get("content-type"), "text/event-stream");
    assert.equal(result.headers.get("request-id"), "req_1");
    const reader = result.body.getReader();
    assert.equal(Buffer.from((await reader.read()).value).toString(), "event: message_start\n\n");
    assert.equal(data.url, "https://api.anthropic.com/v1/messages?beta=true");
    assert.equal(data.request.headers["x-api-key"], "test-api-key");
    assert.equal(data.request.headers["anthropic-beta"], "beta-test");
    assert.equal(data.request.headers["x-relay-secret"], undefined);
    assert.equal(data.request.body.toString(), '{"stream":true}');
    next();
    assert.equal(Buffer.from((await reader.read()).value).toString(), "event: message_stop\n\n");
    assert.equal((await reader.read()).done, true);
    fail = true;
    const limited = await nativeFetch(url, { method: "POST", headers, body: "{}" });
    assert.equal(limited.status, 429);
    assert.equal(limited.headers.get("retry-after"), "2");
    assert.equal(await limited.text(), '{"type":"error"}');
  } finally {
    globalThis.fetch = nativeFetch;
    if (previous === undefined) delete process.env.RELAY_SECRET;
    else process.env.RELAY_SECRET = previous;
    server.closeAllConnections();
    server.close();
  }
});
