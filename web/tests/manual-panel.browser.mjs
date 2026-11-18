import assert from "node:assert/strict";
import {execFileSync} from "node:child_process";
import {mkdtempSync, rmSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {chromium} from "playwright";

const base = process.env.PANEL_TEST_URL || "http://127.0.0.1:5197";
const folder = mkdtempSync(join(tmpdir(), "editor-manual-browser-"));
const fixture = join(folder, "source.mp4");
execFileSync("ffmpeg", ["-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=3:r=30",
  "-c:v", "libx264", "-pix_fmt", "yuv420p", fixture]);

const chrome = process.env.CHROME_PATH || (process.platform === "darwin" ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" : undefined);
const browser = await chromium.launch({headless: true, executablePath: chrome});
try {
  for (const width of [375, 1360]) {
    const page = await browser.newPage({viewport: {width, height: width < 400 ? 800 : 900}, isMobile: width < 400, hasTouch: width < 400});
    const errors = [];
    page.on("pageerror", e => errors.push(e.message));
    await page.goto(`${base}/panel`);
    await page.getByRole("button", {name: "پروژهٔ جدید", exact: true}).click();
    await page.getByRole("button", {name: /برش و تدوین دستی/}).click();
    await page.getByLabel("نام پروژه", {exact: true}).fill(`Manual test ${width}`);
    await page.locator('input[type=file]').setInputFiles(fixture);
    await page.getByRole("button", {name: "source.mp4", exact: true}).waitFor();
    await page.getByRole("button", {name: "باز کردن تایم‌لاین", exact: true}).click();
    await page.getByRole("button", {name: "تایم‌لاین", exact: true}).click();
    await page.getByRole("heading", {name: "برش‌های تدوین"}).waitFor({timeout: 20000});
    await page.locator(".mp-native-track button").first().click();
    await page.getByLabel("از", {exact: true}).fill("0.5");
    await page.getByRole("button", {name: "ذخیرهٔ برش", exact: true}).click();
    await page.getByText("نسخهٔ جدید ذخیره شد", {exact: false}).waitFor();
    const cid = new URL(page.url()).pathname.split("/").pop();
    const row = await (await page.request.get(`${base}/api/studio/conversations/${cid}?messages=1`)).json();
    assert.equal(row.title, `Manual test ${width}`);
    assert.equal(row.messages.length, 0);
    assert.equal(row.projects.length, 1);
    let plan = await (await page.request.get(`${base}/api/panel/projects/${row.projects[0].id}/segments`)).json();
    assert.ok(Math.abs(plan.segments[0].source_in - .5) < .035);
    await page.reload();
    await page.getByRole("button", {name: "تایم‌لاین", exact: true}).click();
    await page.getByRole("heading", {name: "برش‌های تدوین"}).waitFor();
    await page.getByLabel("بازگردانی برنامه").selectOption("1");
    await page.getByRole("button", {name: "بازگردانی به‌عنوان نسخهٔ جدید", exact: true}).click();
    await page.getByText("نسخهٔ جدید ذخیره شد", {exact: false}).waitFor();
    plan = await (await page.request.get(`${base}/api/panel/projects/${row.projects[0].id}/segments`)).json();
    assert.equal(plan.segments[0].source_in, 0);
    assert.ok(plan.version >= 3);
    await page.locator(".mp-native-track button").first().click();
    await page.getByRole("button", {name: "تقسیم قطعه", exact: true}).click();
    await page.locator(".mp-native-track button").nth(1).waitFor();
    await page.locator(".mp-native-track button").last().click();
    await page.getByRole("button", {name: "تکثیر", exact: true}).click();
    await page.locator(".mp-native-track button").nth(2).waitFor();
    await page.locator(".mp-native-track button").first().click();
    await page.getByRole("button", {name: "یک قطعه جلوتر", exact: true}).click();
    await page.getByText("نسخهٔ جدید ذخیره شد", {exact: false}).waitFor();
    plan = await (await page.request.get(`${base}/api/panel/projects/${row.projects[0].id}/segments`)).json();
    assert.equal(plan.segments.length, 3);
    assert.equal(plan.segments[0].source_in, 1.5);
    assert.equal(plan.duration, 4.5);
    const versionBeforeCaption = plan.version;
    await page.getByRole("button", {name: "افزودن لایه", exact: true}).click();
    await page.getByLabel("متن", {exact: true}).fill("Panel verified");
    await page.getByRole("button", {name: "افزودن", exact: true}).click();
    await page.getByRole("button", {name: "Panel verified", exact: true}).waitFor();
    await page.getByRole("button", {name: "واگرد", exact: true}).click();
    await page.getByRole("button", {name: "Panel verified", exact: true}).waitFor({state: "hidden"});
    await page.getByRole("button", {name: "انجام دوباره", exact: true}).click();
    await page.getByRole("button", {name: "Panel verified", exact: true}).waitFor();
    plan = await (await page.request.get(`${base}/api/panel/projects/${row.projects[0].id}/segments`)).json();
    assert.equal(plan.layers[0].label, "Panel verified");
    assert.ok(plan.version > versionBeforeCaption);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2), true);
    assert.deepEqual(errors, []);
    await page.screenshot({path: join(folder, `panel-${width}.png`), fullPage: true});
    if (process.env.PANEL_TEST_RENDER === "1" && width === 1360) {
      await page.getByRole("button", {name: "رندر خروجی", exact: true}).click();
      let state;
      for (let i = 0; i < 35; i++) {
        state = await (await page.request.get(`${base}/api/jobs/${plan.job_id}/render/status`)).json();
        if (["done", "error"].includes(state.status)) break;
        await new Promise(resolve => setTimeout(resolve, 850));
      }
      assert.equal(state.status, "done", JSON.stringify(state));
      const output = await page.request.get(`${base}/api/jobs/${plan.job_id}/exports/${encodeURIComponent(state.output)}`);
      const bytes = await output.body();
      assert.ok(output.ok() && bytes.length > 1000);
      const rendered = join(folder, "rendered.mp4");
      writeFileSync(rendered, bytes);
      const probe = JSON.parse(execFileSync("ffprobe", ["-v", "error", "-show_format", "-show_streams", "-of", "json", rendered], {encoding: "utf8"}));
      assert.ok(Math.abs(Number(probe.format.duration) - 4.5) < .15, JSON.stringify(probe.format.duration));
      assert.ok(probe.streams.some(stream => stream.codec_type === "video" && stream.width === 320));
      const frame = execFileSync("ffmpeg", ["-nostdin", "-v", "error", "-ss", "0.5", "-i", rendered, "-frames:v", "1",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], {maxBuffer: 1024 * 1024});
      let white = 0;
      for (let pixel = 0; pixel + 2 < frame.length; pixel += 3) {
        if (Math.min(frame[pixel], frame[pixel + 1], frame[pixel + 2]) > 180) white++;
      }
      assert.ok(white > 12, "white caption pixels must be visible over the solid blue source");
    }
    await page.close();
    console.log(`Manual panel at ${width}px: upload → persisted plan → trim → reload → restore → split → duplicate → reorder → caption → undo/redo`);
  }
  console.log(`Screenshots: ${folder}`);
} finally {
  rmSync(fixture, {force: true});
  await browser.close();
}
