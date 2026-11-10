import { Readable } from "node:stream";

export const config = {
  api: { bodyParser: false },
};

const ALLOWED = [
  { method: "GET", pattern: /^v1\/voices$/ },
  { method: "GET", pattern: /^v2\/voices$/ },
  { method: "GET", pattern: /^v1\/models$/ },
  { method: "GET", pattern: /^v1\/user\/subscription$/ },
  { method: "POST", pattern: /^v1\/speech-to-text$/ },
  { method: "POST", pattern: /^v1\/text-to-speech\/[A-Za-z0-9_-]{3,100}$/ },
  { method: "POST", pattern: /^v1\/text-to-speech\/[A-Za-z0-9_-]{3,100}\/with-timestamps$/ },
  // Voice cloning: creating an Instant Voice Clone from the person's own recording. Editing or deleting voices stays blocked (the account's voices cannot be removed through the relay).
  { method: "POST", pattern: /^v1\/voices\/add$/ },
];

const VOICE_QUERY = new Set([
  "page_size", "next_page_token", "search", "language", "accent", "gender",
  "age", "category", "voice_type", "sort", "sort_direction", "use_cases",
  "high_quality", "include_total_count", "voice_ids", "collection_id",
  "fine_tuning_state", "include_custom_rates", "include_live_moderated",
  "min_notice_period_days",
]);

function upstreamUrl(req, path) {
  const target = new URL(`https://api.elevenlabs.io/${path}`);
  const query = new URL(req.url || "/", "https://relay.invalid").searchParams;
  const allowed = path === "v2/voices" ? VOICE_QUERY
    : path === "v1/voices" ? new Set(["show_legacy"]) : new Set();
  for (const [key, value] of query) {
    if (allowed.has(key)) target.searchParams.append(key, value);
  }
  return target;
}
function requestKey(req) {
  const value = req.headers["xi-api-key"];
  return Array.isArray(value) ? value[0] : value;
}

function requestedPath(req) {
  const raw = req.query?.path;
  const value = Array.isArray(raw) ? raw.join("/") : typeof raw === "string" ? raw : "";
  return decodeURIComponent(value).replace(/^\/+/, "");
}

function copyResponseHeaders(upstream, res) {
  for (const name of ["content-type", "content-length", "request-id", "character-cost"]) {
    const value = upstream.headers.get(name);
    if (value) res.setHeader(name, value);
  }
}

export default async function handler(req, res) {
  try {
    const serverKey = process.env.ELEVENLABS_API_KEY;
    if (!serverKey) {
      return res.status(503).json({ error: { message: "ElevenLabs relay is not configured" } });
    }
    if (requestKey(req) !== serverKey) {
      return res.status(401).json({ error: { message: "Unauthorized" } });
    }

    const path = requestedPath(req);
    const method = String(req.method || "GET").toUpperCase();
    if (!ALLOWED.some((rule) => rule.method === method && rule.pattern.test(path))) {
      return res.status(404).json({ error: { message: "ElevenLabs route is not allowed" } });
    }

    const headers = { "xi-api-key": serverKey };
    for (const name of ["accept", "content-type", "content-length"]) {
      const value = req.headers[name];
      if (typeof value === "string") headers[name] = value;
    }

    const options = { method, headers, signal: AbortSignal.timeout(290_000) };
    if (method === "POST") {
      options.body = Readable.toWeb(req);
      options.duplex = "half";
    }

    const upstream = await fetch(upstreamUrl(req, path), options);
    copyResponseHeaders(upstream, res);
    if (method === "GET") res.setHeader("cache-control", "private, no-store");
    res.status(upstream.status);
    if (!upstream.body) return res.end();
    Readable.fromWeb(upstream.body).pipe(res);
  } catch (error) {
    console.error("elevenlabs_relay_error", error instanceof Error ? error.message : "unknown");
    if (!res.headersSent) return res.status(502).json({ error: { message: "ElevenLabs upstream failed" } });
    res.end();
  }
}
