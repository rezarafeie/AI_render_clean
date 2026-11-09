import test from "node:test";
import assert from "node:assert/strict";
import { readChat, writeChat, forgetChat, peekChat } from "../src/studio/chatCache.ts";

const snap = id => ({ conversation: { id }, messages: [], hasMore: false, eventsFrom: 0, events: [], cursor: 0 });

test("a chat written to the cache comes back at once", () => {
  writeChat("a", snap("a"));
  assert.equal(readChat("a").conversation.id, "a");
  forgetChat("a");
  assert.equal(readChat("a"), undefined);
});

test("only the most recently used chats are kept", () => {
  for (let i = 0; i < 30; i++) writeChat(`c${i}`, snap(`c${i}`));
  assert.equal(peekChat("c0"), undefined);          // the oldest went
  assert.ok(peekChat("c29"));
  readChat("c20");                                  // using one keeps it
  for (let i = 30; i < 40; i++) writeChat(`c${i}`, snap(`c${i}`));
  assert.ok(peekChat("c20"));                    // the one just used survived ten newer chats
  assert.equal(peekChat("c21"), undefined);
  assert.ok(peekChat("c39"));
});
