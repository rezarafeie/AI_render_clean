import { Readable } from "node:stream";

// Jamendo for the music search: GET only, two shapes, both behind the same shared key as the ElevenLabs functions (the server cannot reach jamendo.com directly).
//   /api/jamendo?client_id=...&search=...            the tracks method of the Jamendo API v3.0, allow-listed query parameters only
//   /api/jamendo?download=https://*.jamendo.com/...  an audio file from a jamendo.com host (never another host), audio responses only, size-capped
export const config = {
  api: { bodyParser: false },
};

const PARAMS = new Set([
  "client_id", "format", "limit", "offset", "search", "tags", "fuzzytags", "vocalinstrumental", "speed", "durationbetween", "include", "audioformat",
  "audiodlformat", "order", "boost", "type", "id", "namesearch", "featured", "groupby", "acousticelectric", "lang", "prolicensing", "probackground", "ccnc", "ccnd", "ccsa",
]);
const HOST = /^(?:[a-z0-9-]+\.)*jamendo\.com$/i;
const MAX_AUDIO_BYTES = 100 * 1024 * 1024;

function requestKey(req) {
  const value = req.headers["xi-api-key"];
  return Array.isArray(value) ? value[0] : value;
}

export default async function handler(req, res) {
  try {
    const serverKey = process.env.ELEVENLABS_API_KEY;
    if (!serverKey) return res.status(503).json({ error: { message: "The relay is not configured" } });
    if (requestKey(req) !== serverKey) return res.status(401).json({ error: { message: "Unauthorized" } });
    if (String(req.method || "").toUpperCase() !== "GET") return res.status(405).json({ error: { message: "Method not allowed" } });
    const query = new URL(req.url || "/", "https://relay.invalid").searchParams;

    const download = query.get("download");
    if (download !== null) {
      let source;
      try { source = new URL(download); } catch { return res.status(400).json({ error: { message: "Invalid download URL" } }); }
      if (source.protocol !== "https:" || source.username || source.password || !HOST.test(source.hostname) || (source.port && source.port !== "443")) {
        return res.status(400).json({ error: { message: "Only https jamendo.com audio can be downloaded" } });
      }
      const upstream = await fetch(source, { method: "GET", redirect: "manual", headers: { accept: "audio/*" }, signal: AbortSignal.timeout(110_000) });
      if (upstream.status >= 300 && upstream.status < 400) {
        const next = upstream.headers.get("location");
        let target;
        try { target = new URL(next, source); } catch { return res.status(502).json({ error: { message: "Bad redirect" } }); }
        if (target.protocol !== "https:" || !HOST.test(target.hostname)) return res.status(502).json({ error: { message: "Redirect to a foreign host refused" } });
        return res.redirect(307, `/api/jamendo?download=${encodeURIComponent(target.toString())}`);
      }
      const type = upstream.headers.get("content-type") || "";
      const length = Number(upstream.headers.get("content-length") || 0);
      if (!upstream.ok || !/^audio\//i.test(type) || length > MAX_AUDIO_BYTES) {
        return res.status(upstream.ok ? 415 : upstream.status).json({ error: { message: "Not an acceptable audio file" } });
      }
      res.setHeader("content-type", type);
      if (length) res.setHeader("content-length", String(length));
      res.setHeader("cache-control", "private, no-store");
      res.status(200);
      if (!upstream.body) return res.end();
      Readable.fromWeb(upstream.body).pipe(res);
      return;
    }

    const target = new URL("https://api.jamendo.com/v3.0/tracks/");
    for (const [key, value] of query) {
      if (PARAMS.has(key) && value.length <= 500) target.searchParams.append(key, value);
    }
    if (!target.searchParams.get("client_id")) return res.status(400).json({ error: { message: "client_id is required" } });
    const upstream = await fetch(target, { method: "GET", headers: { accept: "application/json" }, signal: AbortSignal.timeout(25_000) });
    res.setHeader("content-type", upstream.headers.get("content-type") || "application/json");
    res.setHeader("cache-control", "private, no-store");
    res.status(upstream.status);
    if (!upstream.body) return res.end();
    Readable.fromWeb(upstream.body).pipe(res);
  } catch (error) {
    console.error("jamendo_relay_error", error instanceof Error ? error.message : "unknown");
    if (!res.headersSent) return res.status(502).json({ error: { message: "Jamendo upstream failed" } });
    res.end();
  }
}
