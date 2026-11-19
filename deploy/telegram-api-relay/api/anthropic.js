import { timingSafeEqual } from "node:crypto";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";

export const config = { api: { bodyParser: false } };

const MAX_BODY = 4 * 1024 * 1024;
const UPSTREAM = "https://api.anthropic.com/v1/messages";

function authorized(value, secret = process.env.RELAY_SECRET) {
  if (typeof value !== "string" || !secret || secret.length < 32) return false;
  const actual = Buffer.from(value);
  const expected = Buffer.from(secret);
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}

function error(res, status, type, message) {
  return res.status(status).json({ type: "error", error: { type, message } });
}

export default async function handler(req, res) {
  if (!authorized(req.headers["x-relay-secret"])) {
    return error(res, 401, "authentication_error", "Unauthorized relay request");
  }
  if (req.method !== "POST") {
    res.setHeader("allow", "POST");
    return error(res, 405, "invalid_request_error", "Method not allowed");
  }
  const key = req.headers["x-api-key"];
  if (typeof key !== "string" || !key.trim()) {
    return error(res, 401, "authentication_error", "Missing Anthropic API key");
  }
  const disconnect = new AbortController();
  const close = () => { if (!res.writableFinished) disconnect.abort(); };
  res.once("close", close);
  try {
    const chunks = [];
    let total = 0;
    for await (const chunk of req.iterator({ destroyOnReturn: false })) {
      total += chunk.length;
      if (total > MAX_BODY) return error(res, 413, "invalid_request_error", "Anthropic request exceeds the relay size limit");
      chunks.push(chunk);
    }

    const url = new URL(UPSTREAM);
    const incoming = new URL(req.url || "/", "https://relay.invalid");
    for (const value of incoming.searchParams.getAll("beta")) url.searchParams.append("beta", value);
    const headers = {
      "x-api-key": key,
      "anthropic-version": req.headers["anthropic-version"] || "2023-06-01",
      "content-type": "application/json",
    };
    if (typeof req.headers["anthropic-beta"] === "string") headers["anthropic-beta"] = req.headers["anthropic-beta"];
    const upstream = await fetch(url, {
      method: "POST", headers, body: Buffer.concat(chunks), redirect: "error",
      signal: AbortSignal.any([disconnect.signal, AbortSignal.timeout(290_000)]),
    });
    for (const name of ["content-type", "request-id", "retry-after"]) {
      const value = upstream.headers.get(name);
      if (value) res.setHeader(name, value);
    }
    res.setHeader("cache-control", "no-store, no-transform");
    res.status(upstream.status);
    res.flushHeaders();
    if (upstream.body) await pipeline(Readable.fromWeb(upstream.body), res);
    else res.end();
  } catch {
    if (!res.headersSent && !res.destroyed) {
      return error(res, 502, "api_error", "Anthropic upstream unavailable");
    }
    if (!res.destroyed) res.destroy();
  } finally {
    res.off("close", close);
  }
}
