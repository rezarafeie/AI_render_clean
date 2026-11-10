import { Readable } from "node:stream";

// Voice cloning only: one authenticated POST that creates an Instant Voice Clone from a recording. It is a separate function on purpose, so the shared
// speech/voice-catalogue route (api/elevenlabs.js) keeps its strict allow-list and no other voice change (edit, delete) is reachable.
export const config = {
  api: { bodyParser: false },
};

const MAX_BYTES = 4_000_000;

function requestKey(req) {
  const value = req.headers["xi-api-key"];
  return Array.isArray(value) ? value[0] : value;
}

export default async function handler(req, res) {
  try {
    const serverKey = process.env.ELEVENLABS_API_KEY;
    if (!serverKey) return res.status(503).json({ error: { message: "ElevenLabs relay is not configured" } });
    if (requestKey(req) !== serverKey) return res.status(401).json({ error: { message: "Unauthorized" } });
    if (String(req.method || "").toUpperCase() !== "POST") return res.status(405).json({ error: { message: "Method not allowed" } });
    const type = String(req.headers["content-type"] || "");
    if (!/^multipart\/form-data;\s*boundary=/i.test(type)) return res.status(415).json({ error: { message: "multipart/form-data is required" } });
    const length = Number(req.headers["content-length"] || 0);
    if (!length || length > MAX_BYTES) return res.status(413).json({ error: { message: "The sample is too large" } });

    const upstream = await fetch("https://api.elevenlabs.io/v1/voices/add", {
      method: "POST",
      headers: { "xi-api-key": serverKey, "content-type": type, "content-length": String(length), accept: "application/json" },
      body: Readable.toWeb(req),
      duplex: "half",
      signal: AbortSignal.timeout(110_000),
    });
    for (const name of ["content-type", "request-id"]) {
      const value = upstream.headers.get(name);
      if (value) res.setHeader(name, value);
    }
    res.setHeader("cache-control", "private, no-store");
    res.status(upstream.status);
    if (!upstream.body) return res.end();
    Readable.fromWeb(upstream.body).pipe(res);
  } catch (error) {
    console.error("elevenlabs_clone_error", error instanceof Error ? error.message : "unknown");
    if (!res.headersSent) return res.status(502).json({ error: { message: "ElevenLabs upstream failed" } });
    res.end();
  }
}
