import { Readable } from "node:stream";

// Music generation only: one authenticated POST to ElevenLabs' music composer (POST /v1/music, the audio is the response body). It is a separate function on purpose,
// like elevenlabs-clone.js: the shared speech route (api/elevenlabs.js) keeps its strict allow-list and nothing else becomes reachable.
export const config = {
  api: { bodyParser: false },
};

const MAX_BODY_BYTES = 64 * 1024;
const FORMAT = /^(?:mp3|pcm|opus|ulaw|alaw)_\d{4,6}(?:_\d{1,3})?$/;

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
    if (!/^application\/json\b/i.test(type)) return res.status(415).json({ error: { message: "application/json is required" } });
    const length = Number(req.headers["content-length"] || 0);
    if (!length || length > MAX_BODY_BYTES) return res.status(413).json({ error: { message: "The request is too large" } });

    const target = new URL("https://api.elevenlabs.io/v1/music");
    const query = new URL(req.url || "/", "https://relay.invalid").searchParams;
    const format = query.get("output_format");
    if (format !== null) {
      if (!FORMAT.test(format)) return res.status(400).json({ error: { message: "Unsupported output_format" } });
      target.searchParams.set("output_format", format);
    }

    const upstream = await fetch(target, {
      method: "POST",
      headers: { "xi-api-key": serverKey, "content-type": "application/json", "content-length": String(length), accept: "audio/*, application/json" },
      body: Readable.toWeb(req),
      duplex: "half",
      signal: AbortSignal.timeout(290_000),
    });
    for (const name of ["content-type", "content-length", "request-id", "song-id"]) {
      const value = upstream.headers.get(name);
      if (value) res.setHeader(name, value);
    }
    res.setHeader("cache-control", "private, no-store");
    res.status(upstream.status);
    if (!upstream.body) return res.end();
    Readable.fromWeb(upstream.body).pipe(res);
  } catch (error) {
    console.error("elevenlabs_music_error", error instanceof Error ? error.message : "unknown");
    if (!res.headersSent) return res.status(502).json({ error: { message: "ElevenLabs upstream failed" } });
    res.end();
  }
}
