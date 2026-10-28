import React from "react";
import { api, TalkingReelState, TalkingRenderSettings } from "./api";
import { AuthenticatedMedia } from "./AuthenticatedMedia";
import { friendlyError, notify } from "./ui";

const DEFAULT_MUSIC = "assets/music/motivational_piano_beat.mp3";
const STAGES: Record<string, string> = {
  queued: "در صف", transcribing: "تشخیص گفتار", "editing text": "اصلاح متن و تیتر",
  "choosing style": "انتخاب هوشمند استایل", "tracking the face": "تشخیص صورت",
  "finding pictures": "پیدا کردن و ساختن تصویرها", rendering: "رندر",
  "planning visual beats": "طراحی استوری‌لاین", "building motion graphics": "ساخت موشن‌ها",
  "rendering motion graphics": "رندر موشن‌ها", "reviewing motion graphics": "بازبینی خروجی",
  "improving motion graphics": "بهبود خودکار", "reviewing improved render": "بازبینی نسخه بهبودیافته",
};

/** Talking-head reel (podcast clip -> styled vertical reel) for one job. */
export function TalkingReelCard({ jobId, onChanged }: { jobId: string; onChanged?: () => void }) {
  const [state, setState] = React.useState<TalkingReelState | null>(null);
  const [draft, setDraft] = React.useState<TalkingReelState | null>(null);
  const [error, setError] = React.useState("");
  const running = state?.status === "running";
  const paused = state?.status === "paused";
  const busy = running || paused;
  const [styles, setStyles] = React.useState<{ id: string; label: string }[]>([]);
  const [media, setMedia] = React.useState<string[]>([]);
  React.useEffect(() => { api.talkingReelStyles().then(setStyles).catch(() => setStyles([])); }, []);
  React.useEffect(() => { api.talkingReelMedia(jobId).then(setMedia).catch(() => setMedia([])); }, [jobId]);

  React.useEffect(() => {
    let active = true;
    async function poll() {
      try {
        const next = await api.getTalkingReel(jobId);
        if (!active) return;
        setState(prev => { if (prev && prev.status !== next.status) onChanged?.(); return next; });
        setDraft(d => (d && ["running", "paused"].includes(next.status) ? d : next));
      } catch (err) { if (active) setError(friendlyError(err, "load the talking reel")); }
    }
    void poll();
    const iv = setInterval(() => { if (running || paused) void poll(); }, 2000);
    return () => { active = false; clearInterval(iv); };
  }, [jobId, running, paused]);

  if (!state || !draft) return null;
  const enhanced = ["talking_2", "talking_3", "talking_4"].includes(draft.style || "talking_1");
  const hasVisuals = ["talking_2", "talking_3"].includes(draft.style || "talking_1");
  const SOURCES: Record<string, string> = { upload: "آپلود خودت", library: "کتابخونه", ai: "هوش مصنوعی", card: "کارت متنی" };

  async function addMedia(files: FileList | null) {
    if (!files || !files.length) return;
    try { setMedia((await api.uploadTalkingReelMedia(jobId, Array.from(files))).media); notify("تصویرها آپلود شدن"); }
    catch (err) { setError(friendlyError(err, "upload the pictures")); }
  }

  async function render(regenerate: boolean) {
    if (!draft) return;
    setError("");
    try {
      if (!regenerate) {
        await api.editTalkingReel(jobId, {
          hook: draft.hook, hook_highlight: draft.hook_highlight, name: draft.name, title: draft.title, music: draft.music,
          cta: draft.cta ?? "", style: draft.style || "talking_1", hook2: draft.hook2 ?? "", captions: draft.captions ?? [],
          storyboard: draft.storyboard ?? [],
          render_settings: draft.render_settings,
        });
      }
      setState(await api.renderTalkingReel(jobId, regenerate));
      notify("ساخت ویدیوی صحبتی شروع شد");
    } catch (err) { setError(friendlyError(err, "start the talking reel")); }
  }

  async function analyze(style?: string) {
    setError("");
    try {
      if (style) await api.editTalkingReel(jobId, { style });
      setState(await api.analyzeTalkingReel(jobId, style));
      notify("تحلیل و پیشنهادهای قبل از رندر شروع شد");
    } catch (err) { setError(friendlyError(err, "analyze the talking reel")); }
  }

  async function chooseStyle(style: string) {
    setDraft({ ...draft!, style });
    await analyze(style);
  }

  async function control(action: "pause" | "resume" | "cancel") {
    try {
      const next = action === "pause" ? await api.pauseTalkingReel(jobId) : action === "resume"
        ? await api.resumeTalkingReel(jobId) : await api.cancelTalkingReel(jobId);
      setState(next); onChanged?.();
    } catch (err) { setError(friendlyError(err, `${action} the talking reel`)); }
  }

  return (
    <div className="card" dir="rtl">
      <div className="section-header">
        <h2>ویدیوی صحبتی (پادکست ← ریل عمودی)</h2>
        <span className="tag">
          {running ? `${STAGES[state.stage] || state.stage} ${state.progress}%` : paused ? `متوقف موقت — ${STAGES[state.stage] || state.stage} ${state.progress}%` : state.status === "canceled" ? "لغو شد" : state.status === "ready" ? "آماده‌ی بازبینی" : state.status === "done" ? "آماده" : state.status === "needs_review" ? "نیازمند بررسی خروجی" : state.status === "error" ? "خطا" : ""}
        </span>
      </div>
      {busy && <div className="action-bar">
        {paused ? <button className="btn-secondary" onClick={() => control("resume")}>ادامه</button> : <button className="btn-secondary" onClick={() => control("pause")}>توقف موقت</button>}
        <button className="btn-danger" onClick={() => control("cancel")}>لغو پردازش</button>
      </div>}
      <p className="muted">اول ترنسکریب و تحلیل انجام می‌شود. استایل پیشنهادی، تیتر قلاب، کلمات برجسته و زیرنویس‌ها را بازبینی کن؛ سپس رندر را شروع کن.</p>
      {["error", "needs_review"].includes(state.status) && <div className="errors">{state.message}</div>}
      {error && <div className="errors">{error}</div>}
      {state.output && state.status === "done" && (
        <div className="row" style={{ alignItems: "flex-start" }}>
          <AuthenticatedMedia as="video" src={`${api.talkingReelOutputUrl(jobId)}?v=${encodeURIComponent(state.output)}`} controls style={{ maxHeight: 520, borderRadius: 8 }} />
          <button className="btn-secondary" onClick={() => api.downloadAuthenticated(api.talkingReelOutputUrl(jobId), `${jobId}_talking_reel.mp4`)}>دانلود ویدیو</button>
        </div>
      )}
      {state.visual_qc && <p className="muted">کنترل کیفیت موشن: {state.visual_qc.passed ? "تأیید شد" : "نیازمند بازبینی"} • {state.visual_qc.samples} فریم نمونه • تغییر صحنه {state.visual_qc.mean_scene_change}</p>}
      <div className="row">
        <label>استایل تدوین
          <select value={draft.style || "talking_1"} disabled={running} onChange={e => { void chooseStyle(e.target.value); }}>
            {styles.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </label>
        {state.suggested_style && <span className="tag">پیشنهاد سیستم: {styles.find(s => s.id === state.suggested_style)?.label || state.suggested_style}</span>}
      </div>
      {state.suggested_style_reason && <p className="muted">دلیل پیشنهاد: {state.suggested_style_reason}</p>}
      {state.analysis_ready && draft.render_settings && (
        <TimelineReview jobId={jobId} state={draft} disabled={running}
          onChange={render_settings => setDraft({ ...draft, render_settings })} />
      )}
      {enhanced ? (
        <>
          <div className="row">
            <label style={{ flex: 1 }}>هوک ۳ ثانیه‌ی اول (۲ تا ۴ کلمه)
              <input value={draft.hook2 ?? ""} disabled={running} placeholder="بعد از اولین ساخت، هوش مصنوعی پیشنهاد می‌ده"
                onChange={e => setDraft({ ...draft, hook2: e.target.value })} style={{ width: "100%" }} />
            </label>
          </div>
          {hasVisuals && <div className="row" style={{ alignItems: "flex-start" }}>
              <label>تصویرهای بی‌رول خودت (اختیاری، هوش مصنوعی هر کدوم رو سر جای مناسبش می‌ذاره)
                <input type="file" accept="image/*" multiple disabled={running} onChange={e => { void addMedia(e.target.files); e.target.value = ""; }} />
              </label>
              {media.length > 0 && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {media.map(name => (
                    <span key={name} className="tag">{name}
                      <button className="btn-secondary" disabled={running} style={{ marginInlineStart: 6, padding: "0 6px" }}
                        onClick={() => { api.deleteTalkingReelMedia(jobId, name).then(() => setMedia(m => m.filter(x => x !== name))).catch(err => setError(friendlyError(err, "remove the picture"))); }}>×</button>
                    </span>
                  ))}
                </div>
              )}
            </div>}
          {hasVisuals && state.slots && state.slots.length > 0 && (
            <div className="muted" style={{ fontSize: 13 }}>
              بی‌رول‌ها: {state.slots.map(slot => `${slot.label || `جمله‌ی ${slot.i + 1}`} ← ${SOURCES[slot.source] || slot.source}`).join("  •  ")}
            </div>
          )}
        </>
      ) : (
        <div className="row">
          <label style={{ flex: 1 }}>تیتر قلاب (ثابت روی ویدیو)
            <input value={draft.hook} disabled={running} placeholder="بعد از اولین ساخت، هوش مصنوعی پیشنهاد می‌ده"
              onChange={e => setDraft({ ...draft, hook: e.target.value })} style={{ width: "100%" }} />
          </label>
          <label>کلمه‌های زرد (با , جدا کن)
            <input value={draft.hook_highlight.join(", ")} disabled={running}
              onChange={e => setDraft({ ...draft, hook_highlight: e.target.value.split(/[,،]/).map(v => v.trim()).filter(Boolean) })} />
          </label>
        </div>
      )}
      {draft.captions && draft.captions.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <h3>بازبینی زیرنویس‌ها قبل از رندر</h3>
          <div style={{ display: "grid", gap: 8, maxHeight: 360, overflowY: "auto" }}>
            {draft.captions.map((caption, index) => (
              <label key={caption.i} className="row" style={{ alignItems: "center" }}>
                <span className="tag">{caption.i + 1}</span>
                <input value={caption.text} disabled={running} style={{ flex: 1 }}
                  onChange={e => setDraft({ ...draft, captions: draft.captions!.map((item, i) => i === index ? { ...item, text: e.target.value } : item) })} />
              </label>
            ))}
          </div>
        </div>
      )}
      {draft.style === "talking_2" && draft.storyboard && draft.storyboard.length > 0 && (
        <div style={{ marginTop: 18 }}>
          <h3>استوری‌لاین پیشنهادی قبل از رندر</h3>
          <p className="muted">هر ردیف یک لحظه‌ی بصری کوتاه و مرتبط با حرف گوینده است. کاتالوگ HyperFrames برای طراحی بررسی می‌شود، اما فقط موشنی اجرا می‌شود که واقعاً در رندر پیاده‌سازی شده باشد.</p>
          <div style={{ display: "grid", gap: 10 }}>
            {draft.storyboard.map((beat, index) => (
              <div key={`${beat.i}-${index}`} className="row" style={{ alignItems: "center", padding: 10, border: "1px solid var(--border)", borderRadius: 10 }}>
                <span className="tag">{String(index + 1).padStart(2, "0")}</span>
                <input value={beat.title} disabled={running} style={{ flex: 1 }}
                  onChange={e => setDraft({ ...draft, storyboard: draft.storyboard!.map((item, i) => i === index ? { ...item, title: e.target.value } : item) })} />
                <select value={beat.visual_type} disabled={running}
                  onChange={e => setDraft({ ...draft, storyboard: draft.storyboard!.map((item, i) => i === index ? { ...item, visual_type: e.target.value } : item) })}>
                  <option value="kinetic_type">تایپوگرافی کوبشی</option><option value="concept">استعاره تصویری</option>
                  <option value="comparison">مقایسه</option><option value="media_collage">کلاژ</option>
                  <option value="ui_showcase">نمایش محصول</option><option value="stat">آمار</option>
                  <option value="chat">گفتگو</option><option value="before_after">قبل/بعد</option>
                  <option value="steps">مراحل</option>
                </select>
                <span className="tag">{beat.motion_style || "motion"}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="row">
        <label>اسم <input dir="ltr" value={draft.name} disabled={running} onChange={e => setDraft({ ...draft, name: e.target.value })} /></label>
        <label>سمت <input dir="ltr" value={draft.title} disabled={running} onChange={e => setDraft({ ...draft, title: e.target.value })} /></label>
        <label>
          <input type="checkbox" checked={!!draft.music} disabled={running} onChange={e => setDraft({ ...draft, music: e.target.checked ? DEFAULT_MUSIC : null })} />
          موزیک ملایم زیر صدا
        </label>
      </div>
      <div className="row">
        <label style={{ flex: 1 }}>کال تو اکشن آخر ویدیو (خالی = فقط موشن لوگو)
          <input value={draft.cta ?? ""} disabled={running} placeholder="برای اینکه یاد بگیری چطور محصول بفروشی عدد ۲۰ رو کامنت کن"
            onChange={e => setDraft({ ...draft, cta: e.target.value })} style={{ width: "100%" }} />
        </label>
      </div>
      <div className="row">
        <button disabled={running || !state.analysis_ready} onClick={() => { void render(false); }}>{state.output ? "رندر دوباره با این تنظیمات" : "تأیید تنظیمات و شروع رندر"}</button>
        <button className="btn-secondary" disabled={running} onClick={() => { void analyze(draft.style || "talking_1"); }}>پیشنهاد دوباره‌ی تیتر و زیرنویس (بدون رندر)</button>
      </div>
    </div>
  );
}

function TimelineReview({ jobId, state, disabled, onChange }: {
  jobId: string; state: TalkingReelState; disabled: boolean;
  onChange: (settings: TalkingRenderSettings) => void;
}) {
  const videoRef = React.useRef<HTMLVideoElement | null>(null);
  const settings = state.render_settings!;
  const [logoUploaded, setLogoUploaded] = React.useState(!!state.logo_uploaded);
  const [logoNonce, setLogoNonce] = React.useState(0);
  const [logoError, setLogoError] = React.useState("");
  const [previewClose, setPreviewClose] = React.useState(false);
  const moments = state.timeline || [];
  const setGrade = (key: keyof TalkingRenderSettings["grade"], value: number) =>
    onChange({ ...settings, grade: { ...settings.grade, [key]: value } });
  const toggleMoment = (id: string) => {
    const off = new Set(settings.disabled_moments);
    off.has(id) ? off.delete(id) : off.add(id);
    onChange({ ...settings, disabled_moments: [...off] });
  };
  const filter = `brightness(${100 + settings.grade.brightness}%) contrast(${settings.grade.contrast}%) saturate(${settings.grade.saturation}%)`;
  const previewScale = settings.zoom.enabled
    ? (previewClose ? settings.zoom.close_scale : settings.zoom.base_scale) / 100 : 1;
  const ranges: { key: keyof TalkingRenderSettings["grade"]; label: string; min: number; max: number; suffix: string }[] = [
    { key: "brightness", label: "نور", min: -30, max: 30, suffix: "" },
    { key: "contrast", label: "کنتراست", min: 50, max: 160, suffix: "%" },
    { key: "saturation", label: "رنگ", min: 0, max: 180, suffix: "%" },
    { key: "temperature", label: "دمای رنگ", min: -50, max: 50, suffix: "" },
    { key: "vignette", label: "وینیت", min: 0, max: 100, suffix: "%" },
  ];
  return <section style={{ marginTop: 20, padding: 16, border: "1px solid var(--border)", borderRadius: 14, background: "rgba(255,255,255,.025)" }}>
    <div className="section-header"><h3>Timeline Review — تنظیم تدوین قبل از رندر</h3><span className="tag">Pre-render</span></div>
    <p className="muted">رنگ، زوم، لحظه‌های کلیدی، تیتر و لوگوی پایان را همین‌جا کنترل کن. همه‌ی تغییرها با دکمه رندر ذخیره و روی خروجی اعمال می‌شوند.</p>
    <div style={{ display: "grid", gridTemplateColumns: "minmax(220px, 340px) 1fr", gap: 18, alignItems: "start" }}>
      <div style={{ position: "relative", overflow: "hidden", borderRadius: 12, background: "#111", aspectRatio: "9 / 16", maxHeight: 480 }}>
        <AuthenticatedMedia as="video" ref={videoRef} src={api.rawUrl(jobId)} controls preload="metadata"
          style={{ width: "100%", height: "100%", objectFit: "cover", filter, transform: `scale(${previewScale})`, transition: "filter .15s, transform .2s" }} />
        {settings.grade.temperature !== 0 && <div aria-hidden style={{ position: "absolute", inset: 0, pointerEvents: "none",
          background: settings.grade.temperature > 0 ? "#ff8a3d" : "#4b8dff", mixBlendMode: "soft-light",
          opacity: Math.abs(settings.grade.temperature) / 250 }} />}
        <div aria-hidden style={{ position: "absolute", inset: 0, pointerEvents: "none", boxShadow: `inset 0 0 ${settings.grade.vignette * 1.4}px rgba(0,0,0,${settings.grade.vignette / 125})` }} />
        <div aria-hidden style={{ position: "absolute", inset: "72% 0 0", pointerEvents: "none",
          background: `linear-gradient(to bottom, transparent, rgba(0,0,0,${(settings.bottom_shade ?? 0) / 100}))` }} />
      </div>
      <div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 10 }}>
          {ranges.map(item => <label key={item.key} style={{ display: "grid", gap: 4 }}>{item.label} <span className="muted">{settings.grade[item.key]}{item.suffix}</span>
            <input type="range" min={item.min} max={item.max} value={settings.grade[item.key]} disabled={disabled}
              onChange={e => setGrade(item.key, Number(e.target.value))} />
          </label>)}
        </div>
        <label style={{ display: "grid", gap: 4, marginTop: 14 }}>شدت فید مشکی پایین: {settings.bottom_shade ?? 0}%
          <input aria-label="شدت فید مشکی پایین" type="range" min="0" max="60" step="1"
            value={settings.bottom_shade ?? 0} disabled={disabled}
            onChange={e => onChange({ ...settings, bottom_shade: Number(e.target.value) })} />
          <span className="muted">پیش‌نمایش زنده؛ برای اعمال روی فایل نهایی، رندر را بزنید.</span>
        </label>
        <div className="row" style={{ marginTop: 14 }}>
          <label><input type="checkbox" checked={settings.zoom.enabled} disabled={disabled}
            onChange={e => onChange({ ...settings, zoom: { ...settings.zoom, enabled: e.target.checked } })} /> زوم‌های دوربین</label>
          <label style={{ flex: 1 }}>حرکت زوم داخل شات: {settings.zoom.amount}%
            <input type="range" min="0" max="200" value={settings.zoom.amount} disabled={disabled || !settings.zoom.enabled}
              onChange={e => onChange({ ...settings, zoom: { ...settings.zoom, amount: Number(e.target.value) } })} style={{ width: "100%" }} />
          </label>
        </div>
        <div className="row" style={{ marginTop: 10 }}>
          <label style={{ flex: 1 }}>زوم قاب اصلی: {settings.zoom.base_scale}%
            <input type="range" min="100" max="180" value={settings.zoom.base_scale} disabled={disabled || !settings.zoom.enabled}
              onChange={e => { const base_scale = Number(e.target.value); onChange({ ...settings, zoom: { ...settings.zoom, base_scale, close_scale: Math.max(base_scale, settings.zoom.close_scale) } }); }} style={{ width: "100%" }} />
          </label>
          <label style={{ flex: 1 }}>زوم قاب نزدیک: {settings.zoom.close_scale}%
            <input type="range" min={settings.zoom.base_scale} max="220" value={settings.zoom.close_scale} disabled={disabled || !settings.zoom.enabled}
              onChange={e => onChange({ ...settings, zoom: { ...settings.zoom, close_scale: Number(e.target.value) } })} style={{ width: "100%" }} />
          </label>
          <label><input type="checkbox" checked={previewClose} disabled={!settings.zoom.enabled}
            onChange={e => setPreviewClose(e.target.checked)} /> نمایش قاب نزدیک در پیش‌نمایش</label>
        </div>
        <div className="row" style={{ marginTop: 10 }}>
          <label><input type="checkbox" checked={settings.key_moments_enabled} disabled={disabled}
            onChange={e => onChange({ ...settings, key_moments_enabled: e.target.checked })} /> افکت لحظه‌های کلیدی</label>
          <label><input type="checkbox" checked={settings.first_key_moment_enabled} disabled={disabled}
            onChange={e => onChange({ ...settings, first_key_moment_enabled: e.target.checked })} /> لحظه کلیدی اول / Cold open</label>
          {moments.length > 0 && <label>انتخاب لحظه اول <select value={settings.first_key_moment_sentence ?? ""}
            disabled={disabled || !settings.first_key_moment_enabled}
            onChange={e => onChange({ ...settings, first_key_moment_sentence: e.target.value === "" ? null : Number(e.target.value) })}>
            <option value="">پیشنهاد هوش مصنوعی</option>
            {moments.map((m, i) => <option key={`${m.id}-first`} value={m.sentence}>{i + 1}. {m.title}</option>)}
          </select></label>}
          <label>نوع افکت <select value={settings.key_moment_effect} disabled={disabled || !settings.key_moments_enabled}
            onChange={e => onChange({ ...settings, key_moment_effect: e.target.value as TalkingRenderSettings["key_moment_effect"] })}>
            <option value="grayscale_title">سیاه‌وسفید + تیتر کامل</option><option value="title_only">فقط تیتر</option>
            <option value="grayscale">فقط سیاه‌وسفید</option><option value="none">بدون افکت</option>
          </select></label>
        </div>
        <div className="row" style={{ marginTop: 10 }}>
          <label>رنگ تیتر <input type="color" value={settings.title_color} disabled={disabled}
            onChange={e => onChange({ ...settings, title_color: e.target.value.toUpperCase() })} /></label>
          <label><input type="checkbox" checked={settings.outro_logo.enabled} disabled={disabled}
            onChange={e => onChange({ ...settings, outro_logo: { ...settings.outro_logo, enabled: e.target.checked } })} /> لوگوی پایان</label>
          <label>موشن لوگو <select value={settings.outro_logo.motion} disabled={disabled || !settings.outro_logo.enabled}
            onChange={e => onChange({ ...settings, outro_logo: { ...settings.outro_logo, motion: e.target.value as TalkingRenderSettings["outro_logo"]["motion"] } })}>
            <option value="pop">Pop + glow</option><option value="fade">Fade</option><option value="slide">Slide</option><option value="none">ثابت</option>
          </select></label>
        </div>
        <div style={{ marginTop: 12, padding: 10, border: "1px solid var(--border)", borderRadius: 10 }}>
          <strong>تصویر لوگوی پایان</strong>
          <div className="row" style={{ marginTop: 8, alignItems: "center" }}>
            {logoUploaded && <AuthenticatedMedia as="img" src={`${api.talkingReelLogoUrl(jobId)}?v=${logoNonce}`} alt="لوگوی پایان"
              style={{ width: 74, height: 74, objectFit: "contain", background: "#171717", borderRadius: 8 }} />}
            <label className="btn-secondary" style={{ cursor: disabled ? "default" : "pointer" }}>انتخاب PNG جدید
              <input hidden type="file" accept="image/png" disabled={disabled} onChange={e => {
                const file = e.target.files?.[0]; e.target.value = ""; if (!file) return;
                setLogoError(""); api.uploadTalkingReelLogo(jobId, file).then(() => { setLogoUploaded(true); setLogoNonce(n => n + 1); notify("لوگوی پایان عوض شد"); })
                  .catch(err => setLogoError(friendlyError(err, "upload the outro logo")));
              }} />
            </label>
            {logoUploaded && <button type="button" className="btn-secondary" disabled={disabled} onClick={() => {
              api.deleteTalkingReelLogo(jobId).then(() => setLogoUploaded(false)).catch(err => setLogoError(friendlyError(err, "remove the outro logo")));
            }}>برگشت به لوگوی اصلی</button>}
          </div>
          <div className="muted">PNG شفاف پیشنهاد می‌شود. این فایل فقط برای همین پروژه ذخیره می‌شود.</div>
          {logoError && <div className="errors">{logoError}</div>}
        </div>
      </div>
    </div>
    <div style={{ marginTop: 16 }}>
      <div className="muted" style={{ marginBottom: 7 }}>لایه لحظه‌های کلیدی — روی هر کلیپ بزن تا خاموش/روشن شود</div>
      <div style={{ display: "flex", gap: 4, minHeight: 64, padding: 6, borderRadius: 10, background: "rgba(0,0,0,.2)", overflowX: "auto" }}>
        {moments.length ? moments.map((moment, index) => {
          const active = settings.key_moments_enabled && !settings.disabled_moments.includes(moment.id);
          return <button key={moment.id} type="button" disabled={disabled} onClick={() => toggleMoment(moment.id)}
            title={moment.title} style={{ minWidth: 130, flex: 1, border: `1px solid ${active ? settings.title_color : "#555"}`, opacity: active ? 1 : .42,
              background: active ? `${settings.title_color}22` : "transparent", borderRadius: 7, padding: "7px 9px", color: "inherit", cursor: "pointer" }}>
            <small>{String(index + 1).padStart(2, "0")}</small><br />{moment.title || "لحظه کلیدی"}
          </button>;
        }) : <span className="muted" style={{ padding: 14 }}>برای این استایل لحظه کلیدی جداگانه‌ای پیشنهاد نشده؛ کنترل‌های عمومی همچنان اعمال می‌شوند.</span>}
      </div>
    </div>
  </section>;
}
