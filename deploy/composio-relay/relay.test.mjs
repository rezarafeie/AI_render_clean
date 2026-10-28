import test from "node:test";
import assert from "node:assert/strict";
import handler from "./api/composio.js";

function call(overrides = {}, upstream = async () => new Response('{"ok":true}', { status: 200, headers: { "content-type": "application/json" } })) {
  process.env.RELAY_SECRET = "s3cret";
  const seen = {};
  globalThis.fetch = async (url, init) => { seen.url = String(url); seen.init = init; return upstream(); };
  const req = { method: "GET", url: "/api/composio?path=api%2Fv3%2Ftools&limit=1", query: { path: "api/v3/tools" }, headers: { "x-relay-secret": "s3cret", "x-api-key": "k" }, ...overrides };
  const out = { code: 0, body: null, headers: {} };
  const res = { status(c) { out.code = c; return this; }, setHeader(k, v) { out.headers[k] = v; }, json(b) { out.body = b; return this; }, send(b) { out.body = b; return this; } };
  return handler(req, res).then(() => ({ out, seen }));
}

test("forwards an allowed call with the caller's own key and the query", async () => {
  const { out, seen } = await call();
  assert.equal(out.code, 200);
  assert.equal(seen.url, "https://backend.composio.dev/api/v3/tools?limit=1");
  assert.equal(seen.init.headers["x-api-key"], "k");
  assert.equal(out.headers["cache-control"], "private, no-store");
});

test("rejects a wrong secret, a missing key, other paths and traversal", async () => {
  assert.equal((await call({ headers: { "x-relay-secret": "no", "x-api-key": "k" } })).out.code, 401);
  assert.equal((await call({ headers: { "x-relay-secret": "s3cret" } })).out.code, 401);
  assert.equal((await call({ query: { path: "admin/users" } })).out.code, 400);
  assert.equal((await call({ query: { path: "api/v3/../admin" } })).out.code, 400);
  assert.equal((await call({ method: "TRACE" })).out.code, 405);
});

test("an unreachable provider is a 502 without details", async () => {
  const { out } = await call({}, async () => { throw new Error("socket hang up"); });
  assert.equal(out.code, 502);
  assert.equal(JSON.stringify(out.body).includes("socket"), false);
});
