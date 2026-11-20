import { timingSafeEqual } from 'node:crypto';
import { TelegramClient, Api } from 'telegram';
import { StringSession } from 'telegram/sessions/index.js';
import bigInt from 'big-integer';
import { seal, unseal } from './download.js';

const PART = 512 * 1024;
const BATCH = PART * 8;
const origins = new Set(['https://editor.rafiei.co', 'https://editorgpt.ir']);
const identifier = /^[1-9][0-9]{0,18}$/;

function authorized(req) {
  const expected = Buffer.from(process.env.RELAY_SECRET || '');
  const supplied = Buffer.from(String(req.headers['x-relay-secret'] || ''));
  return expected.length >= 32 && expected.length === supplied.length && timingSafeEqual(expected, supplied);
}

export default async function handler(req, res) {
  if (!authorized(req)) return res.status(401).end();
  if (req.method !== 'POST') return res.status(405).end();
  if (!process.env.TELEGRAM_API_ID || !process.env.TELEGRAM_API_HASH || !process.env.TELEGRAM_BOT_TOKEN) return res.status(503).end();

  const { fileId, randomId, chatId, offset, size, session, source, name, caption, conversation } = req.body || {};
  let url;
  try {
    url = new URL(source);
  } catch {
    return res.status(400).end();
  }
  if (!origins.has(url.origin) || url.username || url.password || url.search || url.hash ||
      !/^\/api\/integrations\/telegram\/media\/[A-Za-z0-9_-]{43}$/.test(url.pathname) ||
      ![fileId, randomId, chatId].every(value => typeof value === 'string' && identifier.test(value)) ||
      !Number.isSafeInteger(size) || size < 18_000_001 || size > 1_950_000_000 ||
      !Number.isSafeInteger(offset) || offset < 0 || offset > size || (offset !== size && offset % BATCH !== 0) ||
      typeof name !== 'string' || name.length > 200 || !name || typeof caption !== 'string' ||
      typeof conversation !== 'string' || !/^[a-f0-9]{32}$/.test(conversation)) {
    return res.status(400).end();
  }
  let client;
  try {
    client = new TelegramClient(new StringSession(session ? unseal(session) : ''), Number(process.env.TELEGRAM_API_ID),
      process.env.TELEGRAM_API_HASH, { connectionRetries: 2, requestRetries: 2, autoReconnect: false, floodSleepThreshold: 0 });
    client.setLogLevel('none');
    await client.start({ botAuthToken: process.env.TELEGRAM_BOT_TOKEN, onError: () => {} });
    res.setHeader('cache-control', 'no-store');
    const total = Math.ceil(size / PART);
    const file = bigInt(fileId);
    if (offset < size) {
      const end = Math.min(size, offset + BATCH);
      const upstream = await fetch(url, { headers: { Range: `bytes=${offset}-${end - 1}` }, redirect: 'error',
        signal: AbortSignal.timeout(25000) });
      if (upstream.status !== 206 || upstream.headers.get('content-range') !== `bytes ${offset}-${end - 1}/${size}` ||
          Number(upstream.headers.get('content-length')) !== end - offset) {
        await upstream.body?.cancel();
        return res.status(502).json({ ok: false });
      }
      const data = Buffer.from(await upstream.arrayBuffer());
      if (data.length !== end - offset) return res.status(502).json({ ok: false });
      const pieces = [];
      for (let start = 0; start < data.length; start += PART) {
        pieces.push(client.invoke(new Api.upload.SaveBigFilePart({
          fileId: file, filePart: (offset + start) / PART, fileTotalParts: total, bytes: data.subarray(start, start + PART),
        })));
      }
      if (!(await Promise.all(pieces)).every(Boolean)) return res.status(502).json({ ok: false });
      return res.status(200).json({ offset: end, session: seal(client.session.save()) });
    }
    const userId = bigInt(chatId);
    const users = await client.invoke(new Api.users.GetUsers({ id: [new Api.InputUser({ userId, accessHash: bigInt.zero })] }));
    const user = users[0];
    if (!user?.accessHash) return res.status(422).json({ ok: false, code: 'peer_unavailable' });
    try {
      await client.invoke(new Api.messages.SendMedia({
        peer: new Api.InputPeerUser({ userId, accessHash: user.accessHash }), randomId: bigInt(randomId),
        message: caption.slice(0, 500),
        media: new Api.InputMediaUploadedDocument({
          file: new Api.InputFileBig({ id: file, parts: total, name }),
          mimeType: name.toLowerCase().endsWith('.mp4') ? 'video/mp4' : 'application/octet-stream',
          attributes: [new Api.DocumentAttributeFilename({ fileName: name })],
        }),
        replyMarkup: new Api.ReplyInlineMarkup({ rows: [new Api.KeyboardButtonRow({
          buttons: [new Api.KeyboardButtonUrl({ text: 'باز کردن در Studio', url: `${url.origin}/studio/${conversation}` })],
        })] }),
      }));
    } catch (error) {
      if (error?.errorMessage !== 'RANDOM_ID_DUPLICATE') throw error;
    }
    return res.status(200).json({ sent: true });
  } catch {
    return res.status(502).json({ ok: false });
  } finally {
    if (client) await client.destroy().catch(() => {});
  }
}
