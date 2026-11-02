import test from "node:test";
import assert from "node:assert/strict";
import { viewportFrame } from "../src/components/hooks.ts";
import { chatHomePath } from "../src/chatHome.ts";

test("the frame follows the visual viewport only while a field is focused and the keyboard is really up", () => {
  assert.deepEqual(viewportFrame({ innerHeight: 800, height: 480, offsetTop: 0, editing: true }), { keyboard: true, appHeight: 480, appTop: 0 });
  assert.deepEqual(viewportFrame({ innerHeight: 800, height: 480, offsetTop: 123.6, editing: true }), { keyboard: true, appHeight: 480, appTop: 124 });   // iOS scrolled the page: the frame moves with it
  assert.deepEqual(viewportFrame({ innerHeight: 800, height: 480, offsetTop: 0, editing: false }), { keyboard: false });          // nothing focused: back to 100dvh
  assert.deepEqual(viewportFrame({ innerHeight: 800, height: 760, offsetTop: 0, editing: true }), { keyboard: false });            // a browser toolbar is not a keyboard
  assert.equal(viewportFrame({ innerHeight: 800, height: 480, offsetTop: -5, editing: true }).appTop, 0);
});

test("the Home button of a chat leads to its own app", () => {
  assert.equal(chatHomePath("/studio/a2b0719d115b46e9b73ac599a9d95216"), "/studio");
  assert.equal(chatHomePath("/hermes/chat/42"), "/hermes");
  for (const other of ["/studio", "/", "/hermes", "/hermes/content", "/settings", "/projects"]) assert.equal(chatHomePath(other), null);
});
