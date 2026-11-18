import assert from "node:assert/strict";
import {execFileSync} from "node:child_process";
import {mkdtempSync, rmSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {chromium} from "playwright";

const base = process.env.PANEL_TEST_URL || "http://127.0.0.1:5197";
const folder = mkdtempSync(join(tmpdir(), "editor-manual-browser-"));
const fixture = join(folder, "source.mp4");
execFileSync("ffmpeg", ["-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=640x480:d=3:r=30",
  "-c:v", "libx264", "-pix_fmt", "yuv420p", fixture]);

const broll = join(folder, "cutaway.mp4");
execFileSync("ffmpeg", ["-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=640x480:d=1.5:r=30",
  "-c:v", "libx264", "-pix_fmt", "yuv420p", broll]);
const customAudio = join(folder, "chime.wav");
execFileSync("ffmpeg", ["-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.7", customAudio]);

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
    await page.locator("[aria-label=\"قطعه‌های ویدیو\"] button").first().click();
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
    await page.locator("[aria-label=\"قطعه‌های ویدیو\"] button").first().click();
    await page.getByRole("button", {name: "تقسیم قطعه", exact: true}).click();
    await page.locator("[aria-label=\"قطعه‌های ویدیو\"] button").nth(1).waitFor();
    await page.locator("[aria-label=\"قطعه‌های ویدیو\"] button").last().click();
    await page.getByRole("button", {name: "تکثیر", exact: true}).click();
    await page.locator("[aria-label=\"قطعه‌های ویدیو\"] button").nth(2).waitFor();
    await page.locator("[aria-label=\"قطعه‌های ویدیو\"] button").first().click();
    await page.getByRole("button", {name: "یک قطعه جلوتر", exact: true}).click();
    await page.getByText("نسخهٔ جدید ذخیره شد", {exact: false}).waitFor();
    plan = await (await page.request.get(`${base}/api/panel/projects/${row.projects[0].id}/segments`)).json();
    assert.equal(plan.segments.length, 3);
    assert.equal(plan.segments[0].source_in, 1.5);
    assert.equal(plan.duration, 4.5);
    const scrubber = page.getByRole("slider", {name: "جابه‌جایی در تایم‌لاین"});
    await scrubber.focus();
    await scrubber.press("Home");
    await scrubber.press("ArrowRight");
    await page.waitForFunction(() => {
      const video = document.querySelector(".mp-monitor video");
      return video?.readyState >= 1 && Math.abs(video.currentTime - (1.5 + 1 / 30)) < .06;
    });
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
    await page.locator("summary").getByText("فونت زیرنویس", {exact: true}).click();
    const fontPicker = page.getByRole("combobox", {name: "فونت سازگار با رندر"});
    await fontPicker.getByRole("option", {name: "Vazirmatn · Regular", exact: true}).waitFor({state: "attached"});
    await fontPicker.selectOption("bundled:Vazirmatn");
    await page.locator(".mp-font-sample").waitFor();
    await page.getByRole("button", {name: "اعمال به زیرنویس‌ها", exact: true}).click();
    await page.getByText("نسخهٔ جدید ذخیره شد", {exact: false}).waitFor();
    plan = await (await page.request.get(`${base}/api/panel/projects/${row.projects[0].id}/segments`)).json();
    assert.equal(plan.caption_font, "Vazirmatn");
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2), true);
    assert.deepEqual(errors, []);
    await page.screenshot({path: join(folder, `panel-${width}.png`), fullPage: true});
    if (process.env.PANEL_TEST_RENDER === "1" && width === 1360) {
      const accepted = page.waitForResponse(response => response.request().method() === "POST" &&
        response.url().endsWith("/segments/render"));
      await page.getByRole("button", {name: "رندر خروجی", exact: true}).click();
      assert.equal((await accepted).status(), 202);
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
      assert.ok(probe.streams.some(stream => stream.codec_type === "video" && stream.width === 640));
      const countLightPixels = time => {
        const frame = execFileSync("ffmpeg", ["-nostdin", "-v", "error", "-ss", time, "-i", rendered, "-frames:v", "1",
          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], {maxBuffer: 1024 * 1024});
        let light = 0;
        for (let pixel = 0; pixel + 2 < frame.length; pixel += 3) {
          if (Math.min(frame[pixel], frame[pixel + 1], frame[pixel + 2]) > 120) light++;
        }
        return light;
      };
      assert.ok(countLightPixels("0.5") > 12, "caption must be visible over the solid blue source");
      assert.equal(countLightPixels("3.5"), 0, "caption must disappear after its editable interval");
    }
    await page.locator('[aria-label="قطعه‌های ویدیو"] button').first().click();
    await page.locator("summary").getByText("حرکت دوربین", {exact: true}).click();
    const camera = page.getByRole("slider", {name: /زوم پایان/});
    await camera.fill("1.5");
    await page.getByRole("button", {name: "ذخیرهٔ حرکت دوربین", exact: true}).click();
    await page.getByText("نسخهٔ جدید ذخیره شد", {exact: false}).waitFor();
    plan = await (await page.request.get(`${base}/api/panel/projects/${row.projects[0].id}/segments`)).json();
    assert.deepEqual(plan.segments[0].zoom, {from: 1, to: 1.5});
    assert.equal(plan.segments[0].splittable, false);
    await page.getByRole("button", {name: "کتابخانه", exact: true}).click();
    await page.getByRole("searchbox", {name: "جستجو در منابع", exact: true}).fill("Crossfade");
    await page.getByRole("button", {name: "اعمال Crossfade", exact: true}).click();
    const applyForm = page.getByRole("region", {name: "اعمال منبع"});
    await applyForm.getByRole("button", {name: "انتخاب همه", exact: true}).click();
    await applyForm.getByRole("button", {name: "اعمال به تایم‌لاین", exact: true}).click();
    await page.getByText("در تایم‌لاین ذخیره شد", {exact: false}).waitFor();
    const updated = await (await page.request.get(`${base}/api/jobs/${plan.job_id}/creative-resources`)).json();
    assert.equal(updated.plan.transitions.length, 2);
    assert.ok(updated.plan.transitions.every(row => row.type === "crossfade" && row.duration_frames === 6 && row.locked));
    await page.getByRole("searchbox", {name: "جستجو در منابع", exact: true}).fill("slow_push__neutral");
    const applyEffect = page.locator("article").filter({hasText: "Slow Push · Neutral"}).getByRole("button", {name: /اعمال/});
    await applyEffect.click();
    await applyForm.getByRole("checkbox").last().check();
    await applyForm.getByRole("button", {name: "اعمال به تایم‌لاین", exact: true}).click();
    await page.getByText("در تایم‌لاین ذخیره شد", {exact: false}).waitFor();
    const withEffect = await (await page.request.get(`${base}/api/jobs/${plan.job_id}/creative-resources`)).json();
    assert.deepEqual(withEffect.plan.visual_effects, [{segment_id: plan.segments[2].id, type: "slow_push__neutral", locked: true}]);
    await page.getByRole("button", {name: "تایم‌لاین", exact: true}).click();
    await page.getByRole("button", {name: "افزودن لایه", exact: true}).click();
    const kind = page.getByRole("combobox", {name: "نوع لایه", exact: true});
    await kind.selectOption("broll");
    await page.getByLabel("آپلود فایل لایه", {exact: true}).setInputFiles(broll);
    await page.getByText("cutaway.mp4", {exact: true}).waitFor();
    await page.getByLabel("پایان در خروجی (ثانیه)", {exact: true}).fill("4");
    await page.getByLabel("شروع در خروجی (ثانیه)", {exact: true}).fill("3");
    await page.getByLabel("شروع از فایل بی‌رول (ثانیه)", {exact: true}).fill("0.3");
    await page.getByRole("button", {name: "افزودن", exact: true}).click();
    await page.getByRole("button", {name: "cutaway.mp4", exact: true}).waitFor();
    await kind.selectOption("sfx");
    await page.getByLabel("آپلود فایل لایه", {exact: true}).setInputFiles(customAudio);
    await page.getByText("chime.wav", {exact: true}).waitFor();
    await page.getByLabel("شروع در خروجی (ثانیه)", {exact: true}).fill("2");
    await page.getByRole("button", {name: "افزودن", exact: true}).click();
    await page.getByRole("button", {name: "chime.wav", exact: true}).waitFor();
    plan = await (await page.request.get(`${base}/api/panel/projects/${row.projects[0].id}/segments`)).json();
    assert.equal(plan.layers.find(layer => layer.label === "cutaway.mp4").source_in, .3);
    assert.ok(plan.layers.find(layer => layer.label === "chime.wav").attachment_id);
    await page.locator('[aria-label="ترنزیشن‌های تایم‌لاین"]').getByText("محو نرم", {exact: true}).first().waitFor();
    await page.locator("summary").getByText("اندازه و کیفیت خروجی", {exact: true}).click();
    await page.getByRole("combobox", {name: "اندازهٔ خروجی", exact: true}).selectOption("480x480");
    await page.getByRole("combobox", {name: "کیفیت فایل", exact: true}).selectOption("16");
    await page.getByRole("button", {name: "ذخیرهٔ تنظیمات خروجی", exact: true}).click();
    await page.getByText("4.10 s · 480 × 480 · 30 fps", {exact: true}).waitFor();
    plan = await (await page.request.get(`${base}/api/panel/projects/${row.projects[0].id}/segments`)).json();
    assert.deepEqual([plan.width, plan.height, plan.crf, plan.fps], [480, 480, 16, 30]);
    if (process.env.PANEL_TEST_RENDER === "1" && width === 1360) {
      const accepted = page.waitForResponse(response => response.request().method() === "POST" &&
        response.url().endsWith("/segments/render"));
      await page.getByRole("button", {name: "رندر خروجی", exact: true}).click();
      assert.equal((await accepted).status(), 202);
      let state;
      for (let i = 0; i < 35; i++) {
        state = await (await page.request.get(`${base}/api/jobs/${plan.job_id}/render/status`)).json();
        if (["done", "error"].includes(state.status)) break;
        await new Promise(resolve => setTimeout(resolve, 850));
      }
      assert.equal(state.status, "done", JSON.stringify(state));
      const output = await page.request.get(`${base}/api/jobs/${plan.job_id}/exports/${encodeURIComponent(state.output)}`);
      assert.ok(output.ok());
      const rendered = join(folder, "rendered-effects.mp4");
      writeFileSync(rendered, await output.body());
      const duration = Number(execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", rendered], {encoding: "utf8"}));
      assert.ok(Math.abs(duration - 4.1) < .09, JSON.stringify(duration));
      const dimensions = execFileSync("ffprobe", ["-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
        "-of", "csv=p=0", rendered], {encoding: "utf8"}).trim();
      assert.equal(dimensions, "480,480");
      const pixels = execFileSync("ffmpeg", ["-nostdin", "-v", "error", "-ss", "3.6", "-i", rendered, "-frames:v", "1",
        "-vf", "scale=8:8", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]);
      const middle = (8 * 4 + 4) * 3;
      assert.ok(pixels[middle] > 200 && pixels[middle + 2] < 45, "uploaded red B-roll must replace the blue source in its interval");
      const sound = execFileSync("ffmpeg", ["-nostdin", "-v", "error", "-ss", "2.1", "-i", rendered, "-t", "0.2",
        "-vn", "-f", "s16le", "-ac", "1", "-"]);
      let peak = 0;
      for (let offset = 0; offset + 1 < sound.length; offset += 2) peak = Math.max(peak, Math.abs(sound.readInt16LE(offset)));
      assert.ok(peak > 700, "uploaded sound effect must be audible in the rendered output");
    }
    await page.close();
    console.log(`Manual panel at ${width}px: upload → persisted plan → trim → reload → restore → split → duplicate → reorder → caption → undo/redo → camera → library effect and transitions → uploaded B-roll and SFX`);
  }
  console.log(`Screenshots: ${folder}`);
} finally {
  for (const media of [fixture, broll, customAudio]) rmSync(media, {force: true});
  await browser.close();
}
