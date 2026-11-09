import type { StudioConversation, StudioEvent, StudioMessage } from "../api";

/**
 * Chats already opened (or about to be: hovered, touched) are kept in memory, so switching to one shows it at once and only re-checks it in the
 * background. Nothing here is the truth: a chat is always re-read after it is shown, this only removes the wait.
 */
export type ChatSnapshot = {
  conversation: StudioConversation;
  messages: StudioMessage[];
  hasMore: boolean;
  eventsFrom: number;
  events: StudioEvent[];
  cursor: number;
  at: number;
};

const LIMIT = 14;
const FRESH_MS = 20_000;
export const FRESH_WINDOW_MS = FRESH_MS;
const store = new Map<string, ChatSnapshot>();
export const MESSAGE_WINDOW = 40;
export const peekChat = (id: string): ChatSnapshot | undefined => store.get(id);

export function readChat(id: string): ChatSnapshot | undefined {
  const hit = store.get(id);
  if (hit) { store.delete(id); store.set(id, hit); }          // most recently used last
  return hit;
}

export function writeChat(id: string, snapshot: Omit<ChatSnapshot, "at">) {
  store.delete(id);
  store.set(id, { ...snapshot, at: Date.now() });
  while (store.size > LIMIT) store.delete(store.keys().next().value as string);
}

export function forgetChat(id: string) { store.delete(id); }
