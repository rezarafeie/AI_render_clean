import test from "node:test";
import assert from "node:assert/strict";
import { mergeMessages, mergeEvents, nearTop, keepPosition } from "../src/studio/windowing.ts";

const m = (id, content = "x") => ({ id, role: "user", content, attachments: [], created_at: "2026-11-01T10:00:00Z" });
const e = seq => ({ id: seq, seq, type: "tool.progress", data: {}, created_at: "2026-11-01T10:00:00Z" });

test("messages accumulate across windows without gaps or duplicates", () => {
  let shown = mergeMessages([], [m(11), m(12), m(13)]);                 // the newest window
  shown = mergeMessages(shown, [m(14, "new")]);                         // a live refresh brings more
  shown = mergeMessages(shown, [m(12, "edited"), m(13), m(14, "newer"), m(15)]);   // the next window overlaps and slides forward
  assert.deepEqual(shown.map(x => x.id), [11, 12, 13, 14, 15]);          // the oldest of the first window is not lost
  assert.equal(shown.find(x => x.id === 12).content, "edited");
  shown = mergeMessages(shown, [m(8), m(9), m(10)]);                    // an older page is put in front
  assert.deepEqual(shown.map(x => x.id), [8, 9, 10, 11, 12, 13, 14, 15]);
  assert.equal(mergeMessages(shown, []), shown);
});

test("events are ordered by sequence and an older page goes in front", () => {
  const live = [e(40), e(41), e(42)];
  const merged = mergeEvents(live, [e(30), e(31), e(41)]);
  assert.deepEqual(merged.map(x => x.seq), [30, 31, 40, 41, 42]);
  assert.equal(mergeEvents(live, [e(41)]), live);                         // nothing new: the same array, so nothing re-renders
  assert.deepEqual(mergeEvents(live, [e(43)]).map(x => x.seq), [40, 41, 42, 43]);
});

test("the next older page is asked for near the top and the reader keeps their place", () => {
  assert.equal(nearTop(40), true); assert.equal(nearTop(900), false);
  assert.equal(keepPosition(2000, 30, 3500), 1530);                       // 1500 px were added above: the reader's 30 px becomes 1530
  assert.equal(keepPosition(2000, 0, 2000), 0);
});
