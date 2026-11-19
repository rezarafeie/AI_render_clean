import assert from "node:assert/strict";
import { chromium } from "playwright";

const base = process.env.PANEL_TEST_URL || "http://127.0.0.1:5197";
const chrome = process.env.CHROME_PATH || (process.platform === "darwin" ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" : undefined);
const browser = await chromium.launch({ headless: true, executablePath: chrome });
const fixture = "aaaa1111aaaa1111aaaa1111aaaa1111";
const pid = "bbb2222";
const dates = n => new Date(Date.now() - 300_000 + n * 1000).toISOString();
const step = (seq, type, data = {}) => ({ seq, type, data, created_at: dates(seq) });
try {
  for (const width of [375, 1360]) {
    const page = await browser.newPage({ viewport: { width, height: 850 } });
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    let ready = false, replyLive;
    const release = new Promise(resolve => { replyLive = resolve; });
    await page.route(`**/api/studio/conversations/${fixture}?*`, route => route.fulfill({json: {
      id: fixture, title: "پروژهٔ آزمایشی", state: {}, language: "fa", messages: [], actions: [], busy: !ready,
      projects: [{ id: pid, title: "کلیپ", engine: "talking", status: ready ? "awaiting_confirmation" : "running", state: ready ? {plan: {segments: []}} :
        {last_observed: {stage: "directing the edit", progress: 12}, last_observed_at: dates(55)}, updated_at: dates(55) }],
    }}));
    await page.route(`**/api/studio/conversations/${fixture}/event-history?*`, route => route.fulfill({json: [
      step(1, "tool.progress", {stage: "transcribing", project_id: pid}),
      ...Array.from({length: 45}, (_, index) => step(index + 2, "work.state", {busy: true})),
      step(47, "tool.started", {tool: "creative_brief", stage: "creative_brief"}),
      step(48, "tool.completed", {tool: "creative_brief", stage: "creative_brief"}),
      step(49, "tool.progress", {stage: "directing the edit", progress: 12, project_id: pid}),
    ]}));
    await page.route(`**/api/studio/conversations/${fixture}/events?*`, async route => {
      await release;
      await route.fulfill({ contentType: "text/event-stream", body: `data: ${JSON.stringify(step(50, "plan.ready", {project_id: pid}))}\n\n` });
    });
    await page.goto(`${base}/panel/${fixture}`, {waitUntil: "domcontentloaded"});
    const flow = page.getByRole("region", {name: "مراحل کار"});
    const active = flow.locator(".act-step[data-status=active]");
    await active.getByText("طراحی ایدهٔ تدوین", {exact: true}).waitFor();
    assert.equal(await flow.getByRole("progressbar", {name: "Render progress"}).count(), 0);
    await flow.getByRole("button", {name: /مرحله انجام شد/}).click();
    await flow.getByText("استخراج متن گفتار", {exact: true}).waitFor();
    ready = true;
    replyLive();
    await flow.getByRole("button", {name: "بررسی برنامه"}).waitFor();
    await flow.getByText("منتظر شما").waitFor();
    assert.equal(await flow.locator(".act-step[data-status=active]").count(), 0);
    await flow.getByRole("button", {name: "بررسی برنامه"}).click();
    await page.getByRole("button", {name: "ویرایش", exact: true}).waitFor();
    assert.equal(await page.getByRole("button", {name: "ویرایش", exact: true}).getAttribute("aria-current"), "true");
    assert.deepEqual(errors, []);
    console.log(`${width}px: active phase and full history → live plan-ready → review tab`);
    await page.close();
  }
} finally {
  await browser.close();
}
