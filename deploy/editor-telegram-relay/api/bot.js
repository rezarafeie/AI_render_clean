import {timingSafeEqual} from 'node:crypto';

const methods = new Set(['getMe', 'getFile', 'sendMessage', 'editMessageText', 'sendVideo', 'sendAudio', 'sendPhoto', 'sendMediaGroup', 'sendDocument', 'answerCallbackQuery', 'setWebhook', 'getWebhookInfo']);

export default async function handler(req, res) {
  const expected = Buffer.from(process.env.RELAY_SECRET || '');
  const supplied = Buffer.from(String(req.headers['x-relay-secret'] || ''));
  if (expected.length < 32 || expected.length !== supplied.length || !timingSafeEqual(expected, supplied)) return res.status(401).end();
  if (req.method !== 'POST') return res.status(405).end();
  const {method, payload} = req.body || {};
  if (!methods.has(method) || !process.env.TELEGRAM_BOT_TOKEN) return res.status(400).end();
  try {
    const upstream = await fetch(`https://api.telegram.org/bot${process.env.TELEGRAM_BOT_TOKEN}/${method}`, {
      method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify(payload || {}),
      signal: AbortSignal.timeout(20000),
    });
    res.setHeader('cache-control', 'no-store');
    return res.status(upstream.status).json(await upstream.json());
  } catch {
    return res.status(502).json({ok: false});
  }
}
