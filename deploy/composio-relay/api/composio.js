// Vercel relay for the Composio API: the server (Iran) reaches backend.composio.dev unreliably, Vercel reaches it fast.
// The relay holds no Composio key: the caller sends its own x-api-key, which is only passed through.
// A shared secret (RELAY_SECRET) keeps strangers from using the relay; only /api/v3/* of backend.composio.dev is forwarded.
import { Readable } from "node:stream";

export const config = { api: { bodyParser: false }, maxDuration: 60 };

const ALLOWED_METHODS = new Set(["GET", "POST", "PATCH", "PUT", "DELETE"]);
const PATH = /^api\/v3(?:\.\d+)?\/[A-Za-z0-9._~!$&'()*+,;=:@%\/-]*$/;
const PASS_HEADERS = ["x-api-key", "content-type", "accept", "user-agent"];

function requestedPath(req) {
  const raw = req.query?.path;
  const value = Array.isArray(raw) ? raw.join("/") : typeof raw === "string" ? raw : "";
  return decodeURIComponent(value).replace(/^\/+/, "");
}

function header(req, name) {
  const value = req.headers[name];
  return Array.isArray(value) ? value[0] : value;
}

export default async function handler(req, res) {
  try {
    const secret = process.env.RELAY_SECRET;
    if (!secret) return res.status(503).json({ error: { message: "Composio relay is not configured" } });
    if (header(req, "x-relay-secret") !== secret) return res.status(401).json({ error: { message: "Unauthorized" } });
    if (!ALLOWED_METHODS.has(req.method)) return res.status(405).json({ error: { message: "Method not allowed" } });
    const path = requestedPath(req);
    if (!PATH.test(path) || path.includes("..")) return res.status(400).json({ error: { message: "Path not allowed" } });
    if (!header(req, "x-api-key")) return res.status(401).json({ error: { message: "Missing API key" } });

    const target = new URL(`https://backend.composio.dev/${path}`);
    const incoming = new URL(req.url || "/", "https://relay.invalid").searchParams;
    for (const [key, value] of incoming) if (key !== "path") target.searchParams.append(key, value);
    const headers = {};
    for (const name of PASS_HEADERS) { const value = header(req, name); if (value) headers[name] = value; }
    const hasBody = !["GET", "DELETE"].includes(req.method);
    const upstream = await fetch(target, {
      method: req.method, headers, redirect: "manual",
      body: hasBody ? Readable.toWeb(req) : undefined, duplex: hasBody ? "half" : undefined,
      signal: AbortSignal.timeout(55_000),
    });
    res.status(upstream.status);
    for (const name of ["content-type", "retry-after", "x-request-id"]) {
      const value = upstream.headers.get(name);
      if (value) res.setHeader(name, value);
    }
    res.setHeader("cache-control", "private, no-store");
    res.send(Buffer.from(await upstream.arrayBuffer()));
  } catch (error) {
    res.status(502).json({ error: { message: "Composio relay could not reach the provider" } });
  }
}
