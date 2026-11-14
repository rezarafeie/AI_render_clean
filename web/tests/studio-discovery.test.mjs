import test from "node:test";
import assert from "node:assert/strict";
import { clock, rangeText, etaText, visibleCandidates, categoriesOf, liveLines, parseRange, isActive } from "../src/studio/discoveryModel.ts";

const c = (id, start, score, category = "آموزشی", hidden = false, status = "discovered") => ({ id, ranges: [[start, start + 40]], score, category, hidden, status });

test("clock and range text", () => {
  assert.equal(clock(75), "01:15");
  assert.equal(clock(3725), "1:02:05");
  assert.equal(rangeText({ ranges: [[750, 798], [1320, 1350]] }), "12:30 – 13:18 + 22:00 – 22:30");
});

test("ETA wording", () => {
  assert.equal(etaText(40), "حدود 40 ثانیه مانده");
  assert.equal(etaText(600), "حدود 10 دقیقه مانده");
  assert.equal(etaText(null), "");
});

test("cards are filtered by category, hidden ones stay out, and the order follows the request", () => {
  const items = [c("a", 300, 6), c("b", 100, 9, "داستان"), c("d", 50, 7, "آموزشی", true), c("e", 200, 8)];
  assert.deepEqual(visibleCandidates(items, null, "time").map(x => x.id), ["b", "e", "a"]);
  assert.deepEqual(visibleCandidates(items, null, "score").map(x => x.id), ["b", "e", "a"]);
  assert.deepEqual(visibleCandidates(items, "آموزشی", "score").map(x => x.id), ["e", "a"]);
  assert.deepEqual(visibleCandidates(items, null, "time", true).map(x => x.id), ["d", "b", "e", "a"]);
  assert.deepEqual(categoriesOf(items), [{ name: "آموزشی", count: 2 }, { name: "داستان", count: 1 }]);
});

test("live transcript shows only real saved and published segments, newest last, without duplicates", () => {
  const tail = [{ id: "0000-001", start: 10, end: 20, text: "اول" }, { id: "0000-002", start: 20, end: 30, text: "دوم" }];
  const events = [
    { type: "transcription.segment.completed", data: { analysis_id: "x", segments: [{ id: "0000-002", start: 20, end: 30, text: "دوم" }, { id: "0001-000", start: 300, end: 310, text: "سوم" }] } },
    { type: "transcription.segment.completed", data: { analysis_id: "other", segments: [{ id: "9", start: 999, end: 1000, text: "نه" }] } },
    { type: "tool.started", data: {} },
  ];
  assert.deepEqual(liveLines(tail, events, "x").map(l => l.text), ["اول", "دوم", "سوم"]);
  assert.equal(liveLines(tail, events, "x", 2).length, 2);
});

test("a time edit is validated", () => {
  assert.deepEqual(parseRange("12:30", "13:18", 3600).range, [750, 798]);
  assert.deepEqual(parseRange("۱۲:۳۰", "۱۳:۱۸", 3600).range, [750, 798]);
  assert.match(parseRange("abc", "10", 100).error, /زمان/);
  assert.match(parseRange("10", "12", 100).error, /۵ ثانیه/);
  assert.match(parseRange("0", "400", 1000).error, /۵ دقیقه/);
  assert.match(parseRange("90", "120", 100).error, /از مدت ویدیو/);
  assert.ok(isActive("editing") && !isActive("completed") && !isActive("discovered"));
});

import { discoverySteps, logText, stepsSummary } from "../src/studio/discoveryModel.ts";

const rec = (key, state, at, extra = {}) => ({ key, label: key, state, at, log: [], ...extra });

test("steps: the server's record becomes live steps only while someone is really working", () => {
  const steps = [rec("file", "done", 100, { done_at: 102 }), rec("transcribe", "active", 102, { progress: 40, note: "۴۰٪", log: [{ at: 150, text: "تکه ۱" }] }), rec("cards", "active", 300)];
  const live = discoverySteps(steps, { running: true, interrupted: false, mediaPending: false }, 160_000);
  assert.deepEqual(live.map(s => s.status), ["done", "active", "active"]);
  assert.equal(live[0].elapsedMs, 2000);
  assert.equal(live[1].elapsedMs, 160_000 - 102_000);
  assert.equal(live[1].percent, 40);
  // the worker died: an active step is «interrupted», its clock stops at the last thing it logged
  const dead = discoverySteps(steps, { running: false, interrupted: true, mediaPending: false }, 999_000);
  assert.equal(dead[1].status, "interrupted");
  assert.equal(dead[1].elapsedMs, 48_000);
  assert.equal(dead[1].percent, undefined);
  // the cards' previews are made after the analysis ended: that step stays live while previews are pending
  const after = discoverySteps(steps, { running: false, interrupted: false, mediaPending: true }, 400_000);
  assert.equal(after[2].status, "active");
  assert.equal(after[1].status, "interrupted");
});

test("steps: stopped and failed stay as they are, with their own clock", () => {
  const views = discoverySteps([rec("transcribe", "stopped", 10, { done_at: 70 }), rec("find", "failed", 70, { done_at: 75 })], { running: false, interrupted: false, mediaPending: false }, 1e9);
  assert.deepEqual(views.map(s => [s.status, s.elapsedMs]), [["stopped", 60000], ["failed", 5000]]);
  assert.deepEqual(stepsSummary(views), { done: 0, total: 2, failed: true, ms: 65000 });
});

test("steps: the log has a time on every line, oldest first", () => {
  const text = logText([{ at: 1_700_000_000, text: "اول" }, { at: 1_700_000_065, text: "دوم" }], "en-GB");
  const lines = text.split("\n");
  assert.equal(lines.length, 2);
  assert.match(lines[0], /^\d\d:\d\d:\d\d {2}اول$/);
  assert.match(lines[1], / {2}دوم$/);
});

test("live transcript: published sentences newer than what the server returned are added; ones it already holds are not repeated under another id", () => {
  const tail = [{ id: "live-1", start: 10, end: 20, text: "الف" }, { id: "live-2", start: 20, end: 30, text: "ب" }];
  const events = [{ type: "transcription.segment.completed", data: { analysis_id: "x", segments: [{ id: "p000-001", start: 20, end: 30, text: "ب" }, { id: "p001-000", start: 310, end: 320, text: "ج" }] } }];
  assert.deepEqual(liveLines(tail, events, "x").map(l => l.text), ["الف", "ب", "ج"]);
  assert.equal(liveLines(tail, [], "x", 12).length, 2);
  const many = Array.from({ length: 30 }, (_, i) => ({ id: `s${i}`, start: i, end: i + 1, text: String(i) }));
  assert.equal(liveLines(many, [], "x").length, 12);
  assert.equal(liveLines(many, [], "x").at(-1).text, "29");
});
