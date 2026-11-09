import { api } from "../api";
import { FRESH_WINDOW_MS, MESSAGE_WINDOW, peekChat, writeChat } from "./chatCache";

const inflight = new Map<string, Promise<void>>();

/** Fetch a chat's newest window into the cache (no-op while a fresh copy or a request for it exists). */
export function prefetchChat(id: string): Promise<void> {
  const hit = peekChat(id);
  if (hit && Date.now() - hit.at < FRESH_WINDOW_MS) return Promise.resolve();
  const running = inflight.get(id);
  if (running) return running;
  const job = api.getStudioConversation(id, { messages: MESSAGE_WINDOW }).then(value => {
    const known = peekChat(id);
    if (known && Date.now() - known.at < 1000) return;
    writeChat(id, {
      conversation: value, messages: value.messages || [], hasMore: Boolean(value.messages_has_more),
      eventsFrom: value.events_from || 0, events: known?.events || [], cursor: Math.max(known?.cursor || 0, value.events_from || 0),
    });
  }).catch(() => undefined).finally(() => { inflight.delete(id); });
  inflight.set(id, job);
  return job;
}
