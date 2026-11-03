import type { StudioEvent, StudioMessage } from "../api";

/** The messages loaded so far, newest window plus any older pages: unique by id, oldest first. A later copy of a message replaces an earlier one. */
export function mergeMessages(current: StudioMessage[], incoming: StudioMessage[]): StudioMessage[] {
  if (!incoming.length) return current;
  const byId = new Map<string, StudioMessage>();
  for (const message of current) byId.set(String(message.id), message);
  for (const message of incoming) byId.set(String(message.id), message);
  return [...byId.values()].sort((a, b) => Number(a.id) - Number(b.id));
}

/** Events by sequence, unique, oldest first (an older page is prepended without disturbing what is already shown). */
export function mergeEvents(current: StudioEvent[], incoming: StudioEvent[]): StudioEvent[] {
  if (!incoming.length) return current;
  const seen = new Set(current.map(event => event.seq));
  const fresh = incoming.filter(event => !seen.has(event.seq));
  if (!fresh.length) return current;
  const merged = [...current, ...fresh];
  const ordered = merged.every((event, index) => index === 0 || merged[index - 1].seq < event.seq);
  return ordered ? merged : merged.sort((a, b) => a.seq - b.seq);
}

/** Whether the reader is close enough to the top for the next older page to be fetched. */
export function nearTop(scrollTop: number, threshold = 160): boolean {
  return scrollTop < threshold;
}

/** Where to put scrollTop after older content was added above, so the reader keeps looking at the same message. */
export function keepPosition(heightBefore: number, scrollTopBefore: number, heightAfter: number): number {
  return Math.max(0, heightAfter - heightBefore + scrollTopBefore);
}
