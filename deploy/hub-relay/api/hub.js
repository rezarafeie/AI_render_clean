// EditorGPT Hub relay: Rafiei Hub's servers (outside Iran) cannot reach the EditorGPT server in Iran directly. This function, outside Iran,
// passes each /api/hub-api request on unchanged (method, path, query, body, and only the headers the Hub API reads) and returns the answer as is.
// It holds no secret and checks nothing itself: the EditorGPT server checks the hub's shared secret on every request.
export const config = { api: { bodyParser: false } };

const ORIGINS = (process.env.EDITOR_ORIGINS || "https://editorgpt.ir/api,https://editor.rafiei.co/api").split(",").map(s => s.trim()).filter(Boolean);
const PASS = ["authorization", "x-hub-user", "idempotency-key", "content-type", "range", "accept"];

async function readBody(req) {
  if (req.method === "GET" || req.method === "HEAD") return undefined;
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  return Buffer.concat(chunks);
}

export default async function handler(req, res) {
  const url = new URL(req.url, "http://relay");
  const sub = url.searchParams.get("p") || "";
  url.searchParams.delete("p");
  if (sub && !/^[A-Za-z0-9._\/-]{1,300}$/.test(sub)) return res.status(400).json({ error: "درخواست نامعتبر است." });
  const path = "/hub-api" + (sub ? "/" + sub : "") + (url.searchParams.toString() ? "?" + url.searchParams : "");
  const headers = {};
  for (const name of PASS) if (req.headers[name]) headers[name] = req.headers[name];
  const body = await readBody(req);
  let last;
  for (const origin of ORIGINS) {
    try {
      const upstream = await fetch(origin + path, { method: req.method, headers, body, redirect: "manual", signal: AbortSignal.timeout(55000) });
      res.status(upstream.status);
      for (const name of ["content-type", "content-length", "content-range", "accept-ranges", "content-disposition", "cache-control"]) {
        const value = upstream.headers.get(name);
        if (value) res.setHeader(name, value);
      }
      res.setHeader("x-relay-origin", new URL(origin).hostname);
      const reader = upstream.body?.getReader();
      if (!reader) return res.end();
      for (;;) { const { done, value } = await reader.read(); if (done) break; res.write(Buffer.from(value)); }
      return res.end();
    } catch (error) { last = error; }
  }
  return res.status(502).json({ error: "ارتباط با سرور ادیتور برقرار نشد؛ کمی بعد دوباره امتحان کنید." });
}
