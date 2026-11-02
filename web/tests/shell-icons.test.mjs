import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const shell = readFileSync(new URL("../src/EditorShell.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/styles/shell.css", import.meta.url), "utf8");

test("the top-bar switch between EditorGPT and InstaGPT is an icon button like the others, with no text", () => {
  const bar = shell.slice(shell.indexOf('<header className="topbar">'), shell.indexOf("</header>", shell.indexOf('<header className="topbar">')));
  const start = bar.indexOf("Switch to InstaGPT");
  const block = bar.slice(bar.lastIndexOf("<NavLink", start), bar.indexOf("</NavLink>", start) + 10);
  assert.match(block, /className="icon-btn icon-btn-lg"/);
  assert.match(block, /aria-label=/);                                  // still named for screen readers
  assert.doesNotMatch(block, /<span>/);                                // no visible text
  assert.doesNotMatch(css, /\.switch-btn/);                            // the pill style is gone
});
