// Visual regression run: node tests/visual/run.mjs [--only=name] 
// Starts nothing itself: expects `npm run dev` on :5173 (see package.json "test:visual").
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { makeConversation, makeEvents, projectsList } from "./fixtures.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const out = process.env.SHOT_DIR || path.join(here, "shots");
fs.mkdirSync(out, { recursive: true });
const video = fs.readFileSync(path.join(here, "fixture.mp4"));
const only = (process.argv.find(a => a.startsWith("--only=")) || "").slice(7);
const ORIGIN_AUTH = process.env.ORIGIN || "http://localhost:5173";
const ORIGIN_GUEST = process.env.GUEST_ORIGIN || "http://guest.localhost:5173";

async function mock(page, { kind = "empty", guest = false } = {}) {
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    const p = url.pathname.replace(/^\/api/, "");
    const json = (body, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (p === "/auth/refresh") return json({ detail: "no session" }, 401);
    if (p === "/studio/conversations") return json(guest ? [] : projectsList);
    if (/^\/studio\/conversations\/[^/]+\/events$/.test(p)) {
      const after = Number(url.searchParams.get("after") || 0);
      const body = makeEvents(kind).filter(e => e.seq > after).map(e => `id: ${e.seq}\ndata: ${JSON.stringify(e)}\n\n`).join("");
      return route.fulfill({ status: 200, contentType: "text/event-stream", body });
    }
    if (/^\/studio\/conversations\/[^/]+$/.test(p)) return json(makeConversation(kind));
    if (/^\/studio\/projects\/[^/]+\/output$/.test(p)) return route.fulfill({ status: 200, contentType: "video/mp4", body: video });
    if (p === "/jobs") return json([]);
    if (p === "/library") return json({ counts: { broll: 2, music: 1, sfx: 0 }, assets: [{ filename: "city-night.mp4", category: "broll", path: "b/city-night.mp4", tags: ["city", "night"], duration_sec: 8 }, { filename: "street.mp4", category: "broll", path: "b/street.mp4", tags: ["street"], duration_sec: 5 }, { filename: "calm-piano.mp3", category: "music", path: "m/calm.mp3", tags: ["calm"], mood: "calm", energy: 2, duration_sec: 92 }] });
    if (p === "/style-library") return json({ drafts: [], profiles: [], candidates: [] });
    if (p === "/my-effects") return json({ preferred_effects: [], rules: [], effects: [], rafiei: { preferred_effects: [] } });
    if (p === "/font-library") return json({ version: 1, candidates: [], approved: [] });
    if (p === "/style/analyses") return json({ analyses: [], items: [] });
    if (p === "/style/profile") return json({ exists: false, active: false, enabled: false, sample_count: 0, metrics: {}, confidence: {}, preset_overrides: {} });
    if (p === "/style/examples" || p === "/fonts") return json([]);
    if (p === "/jobs/job1") return json({ id: "job1", dir: "x", raw_name: "interview.mp4", plan_name: "plan", render: { status: "done", progress: 100, message: "", output: "v1.mp4", preview: false }, generate: { status: "done", stage: "", message: "", cost_usd: 0, input_tokens: 0, output_tokens: 0, model: "m" }, versions: ["v1.mp4"], plan: { title: "Interview", segments: [] } });
    if (/\/premiere\/status|\/premiere$/.test(p)) return json({ capability: { available: false, local_launch_supported: false, version: null, bundle_id: null, app_path: null }, editable_plan: "missing", final_render: "final", saved_project: "not_linked", project_state: "not_linked", render_name: null, xml_name: "a.xml", srt_name: "a.srt", warnings: [] });
    if (p.startsWith("/localize")) return json([]);
    if (p.includes("talking-reel")) return json([]);
    if (p === "/ai/access" || p.endsWith("/access")) return json({ allowed: false });
    return json({});
  });
}

const sizes = { "320": [320, 640], "360": [360, 740], "375": [375, 812], "390": [390, 844], "430": [430, 932], "768": [768, 1024], "1024": [1024, 768], "1280": [1280, 800], "1440": [1440, 900], "1920": [1920, 1080] };
const results = [];
async function shot(browser, name, { url, size, kind, guest, setup, theme }) {
  if (only && !name.includes(only)) return;
  const [width, height] = sizes[size] || size;
  const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1, hasTouch: width < 700, isMobile: width < 700 });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", e => errors.push(String(e)));
  page.on("console", m => { if (m.type() === "error" && !/Failed to load resource|favicon|fonts\.g/.test(m.text())) errors.push(m.text()); });
  await mock(page, { kind, guest });
  if (theme) await page.addInitScript(t => localStorage.setItem("editorgpt.theme", t), theme);
  await page.goto((guest ? ORIGIN_GUEST : ORIGIN_AUTH) + url, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(700);
  if (setup) await setup(page);
  await page.waitForTimeout(400);
  // Layout assertions: no horizontal overflow of the document.
  const metrics = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth, bodyOverflow: document.body.scrollWidth > document.documentElement.clientWidth + 1 }));
  const overflow = metrics.sw > metrics.cw + 1;
  await page.screenshot({ path: path.join(out, `${name}.png`) });
  results.push({ name, overflow, errors });
  await context.close();
}

const browser = await chromium.launch({ channel: "chrome" });
const S = (name, o) => shot(browser, name, o);

for (const [label, size] of [["desktop", "1440"], ["mobile", "390"]]) {
  await S(`home-${label}`, { url: "/studio", size });
  await S(`login-${label}`, { url: "/login", size, guest: true });
  await S(`signup-${label}`, { url: "/signup", size, guest: true });
  await S(`projects-${label}`, { url: "/projects", size });
  await S(`templates-${label}`, { url: "/templates", size });
  await S(`settings-${label}`, { url: "/settings", size });
  await S(`studio-processing-${label}`, { url: "/studio/c1", size, kind: "processing" });
  await S(`studio-rendering-${label}`, { url: "/studio/c1", size, kind: "rendering" });
  await S(`studio-done-${label}`, { url: "/studio/c1", size, kind: "done" });
  await S(`studio-approve-${label}`, { url: "/studio/c1", size, kind: "approve" });
}
await S("home-guest-desktop", { url: "/studio", size: "1440", guest: true });
await S("home-guest-mobile", { url: "/studio", size: "390", guest: true });
await S("sidebar-collapsed-desktop", { url: "/studio/c1", size: "1440", kind: "done", setup: p => p.getByRole("button", { name: "Close sidebar" }).click() });
await S("sidebar-drawer-mobile", { url: "/studio/c1", size: "390", kind: "done", setup: p => p.getByRole("button", { name: "Open navigation" }).click() });
await S("auth-sheet-mobile", { url: "/studio", size: "390", guest: true, setup: async p => { await p.getByRole("button", { name: "Open navigation" }).click(); await p.getByRole("button", { name: "Log in" }).first().click(); } });
await S("studio-tablet-768", { url: "/studio/c1", size: "768", kind: "done" });
await S("studio-tablet-768-workspace", { url: "/studio/c1", size: "768", kind: "done", setup: p => p.locator(".chat-head button", { hasText: "Preview" }).click() });
await S("studio-mobile-preview", { url: "/studio/c1", size: "390", kind: "done", setup: p => p.locator('nav[aria-label="Studio views"] button', { hasText: "Preview" }).click() });
await S("studio-mobile-edit", { url: "/studio/c1", size: "390", kind: "approve", setup: p => p.locator('nav[aria-label="Studio views"] button', { hasText: "Edit" }).click() });
await S("studio-desktop-edit", { url: "/studio/c1", size: "1440", kind: "approve", setup: p => p.getByRole("tab", { name: "Edit" }).click() });
await S("studio-light", { url: "/studio/c1", size: "1440", kind: "done", theme: "light" });
for (const [name, route] of [["render", "/jobs/job1/render"], ["new", "/new"], ["my-effects", "/my-effects"], ["library", "/library"], ["style-library", "/style-library"], ["style-learner", "/style-learner"], ["content", "/content"], ["localize", "/localize"], ["talking", "/talking"], ["hermes", "/insta"], ["forgot", "/forgot-password"]]) {
  await S(`legacy-${name}-desktop`, { url: route, size: "1440", guest: name === "forgot" });
  await S(`legacy-${name}-mobile`, { url: route, size: "390", guest: name === "forgot" });
}
for (const size of Object.keys(sizes)) {
  await S(`sweep-studio-${size}`, { url: "/studio/c1", size, kind: "rendering" });
  await S(`sweep-home-${size}`, { url: "/studio", size });
  await S(`sweep-projects-${size}`, { url: "/projects", size });
}
await browser.close();
fs.writeFileSync(path.join(out, "report.json"), JSON.stringify(results, null, 2));
const bad = results.filter(r => r.overflow || r.errors.length);
console.log(`${results.length} screenshots → ${out}`);
for (const r of bad) console.log(`${r.overflow ? "OVERFLOW " : ""}${r.errors.length ? "ERRORS " : ""}${r.name}`, r.errors.slice(0, 2).join(" | "));
