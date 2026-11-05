import React from "react";
import { createPortal, flushSync } from "react-dom";
import { EditCard, EditSwitch } from "./EditCard";
import { FrameControls, LightControls, LookStage, ZoomControls, type LookValues } from "./LookStudio";
import { api, PlanContent, PlanEdits, PlanVersion, StudioProject } from "../api";
import { AuthenticatedMedia } from "../AuthenticatedMedia";
import { Icon, type IconName } from "../components/Icon";
import { friendlyError } from "../ui";
import { PHASE_LABEL, SOURCE_LABEL, estimateText, planPhase, restoreEdits, roleLabel, toggleHighlight } from "./plan";

const LOOKS: [string, string][] = [["default", "پیش‌فرض سبک"], ["natural", "طبیعی"], ["warm", "گرم"], ["cool", "سرد و ملایم"], ["cinematic", "سینمایی"]];
const ACCENTS = ["#F5B800", "#FFFFFF", "#A8CF80", "#FF6B4A", "#4DA3FF"];
const FONTS: [string, string][] = [["default", "Ray (فونت سبک)"], ["Vazirmatn", "وزیرمتن"]];
const PICTURE_SOURCE: Record<string, string> = { upload: "فایل شما", library: "کتابخانه", ai: "ساخته‌شده", ai_planned: "ساخته می‌شود", motion_so: "کلیپ موشن هوشمند", card: "کارت متنی" };
const KEY_EFFECTS: [string, string][] = [["grayscale_title", "سیاه‌وسفید + تیتر"], ["title_only", "فقط تیتر"], ["grayscale", "فقط سیاه‌وسفید"], ["none", "بدون افکت"]];
const LOGO_MOTIONS: [string, string][] = [["pop", "پاپ"], ["fade", "محو"], ["slide", "حرکت نرم"]];

/** A style preview: one frame of the upload drawn with the style's own text, boxes and colours (engine/style_frames.py). */
function Mockup({ project, frame, label }: { project: StudioProject; frame?: string; label: string }) {
  return <div className="plan-frame">
    {frame ? <AuthenticatedMedia as="img" src={api.studioPlanFrameUrl(project.id, frame)} alt={label} loading="lazy"/> : <span className="plan-frame-empty">بدون پیش‌نمایش</span>}
    {frame ? <span className="plan-frame-tag">پیش‌نمایش</span> : null}
  </div>;
}

function Section({ tool, current, title, children, hint, summary }: { tool: Tool; current: Tool; title: string; children: React.ReactNode; hint?: string; summary?: React.ReactNode }) {
  if (tool !== current) return null;
  return <section className="tool-panel" dir="rtl" aria-label={title}>
    {hint ? <p className="ec-hint">{hint}</p> : null}
    {children}
  </section>;
}

export type Tool = "style" | "hook" | "light" | "frame" | "zoom" | "text" | "brand" | "details";
const TOOLS: [Tool, string, IconName, boolean][] = [   // [id, label, icon, only for Talking 1]
  ["light", "نور و رنگ", "sun", true], ["frame", "کادر", "image", true], ["zoom", "زوم", "search", false], ["text", "متن", "captions", false],
  ["style", "سبک", "wand", false], ["hook", "هوک", "spark", false], ["brand", "برند", "user", false], ["details", "جزئیات", "list", false]];

export function PlanReview({ project, onChanged, superseding = false, footerSlot = null }: { project: StudioProject; onChanged: () => void | Promise<unknown>; superseding?: boolean; footerSlot?: HTMLElement | null }) {
  const versions: PlanVersion[] = project.state?.plan?.versions || [];
  const latest = versions[versions.length - 1];
  const phase = planPhase(project);
  const [viewing, setViewing] = React.useState<string | null>(null);
  const [draft, setDraft] = React.useState<PlanEdits>({});
  const [busy, setBusy] = React.useState("");
  const actionInFlight = React.useRef(false);
  const [error, setError] = React.useState("");
  const [tool, setTool] = React.useState<Tool>("light");
  const [previewClose, setPreviewClose] = React.useState(false);
  React.useEffect(() => { setDraft({}); setViewing(null); setError(""); }, [latest?.id]);
  if (!latest) return <div className="plan" dir="rtl"><div className="notice" role="status">برنامهٔ تدوین در حال ساخته‌شدن است؛ ویدیو تحلیل می‌شود و چند ایده سنجیده می‌شود. وقتی آماده شد همین‌جا نمایش داده می‌شود.</div></div>;

  const shown = versions.find(item => item.id === viewing) || latest;
  const isLatest = shown.id === latest.id;
  const locked = phase === "analyzing" || phase === "rendering" || Boolean(busy) || superseding;
  const editable = isLatest && !locked;
  const plan: PlanContent = shown.content;
  const value = <K extends keyof PlanEdits>(key: K, fallback: PlanEdits[K]) => (key in draft ? draft[key] : fallback) as NonNullable<PlanEdits[K]>;
  const set = (patch: PlanEdits) => setDraft(current => ({ ...current, ...patch }));
  const dirty = Object.keys(draft).length > 0;
  const hook = value("hook", plan.hook.text);
  const highlight = value("hook_highlight", plan.hook.highlight);
  const t1 = plan.style.id === "talking_1" && Boolean(project.external_ref);
  const lookValues: LookValues = { brightness: value("brightness", plan.look.grade?.brightness ?? 0), contrast: value("contrast", plan.look.grade?.contrast ?? 100),
    saturation: value("saturation", plan.look.grade?.saturation ?? 100), temperature: value("temperature", plan.look.grade?.temperature ?? 0),
    gradeAuto: value("grade_auto", plan.look.grade_auto ?? true), framingAuto: value("framing_auto", plan.look.framing?.auto ?? true),
    shiftX: value("shift_x", plan.look.framing?.shift_x ?? 0), shiftY: value("shift_y", plan.look.framing?.shift_y ?? 0),
    zoomEnabled: value("zoom_enabled", plan.look.zoom_enabled ?? true), zoomBase: value("zoom_base", plan.look.zoom_base ?? 100),
    zoomClose: value("zoom_close", plan.look.zoom_close ?? 125), zoomAmount: value("zoom", plan.look.zoom) };
  const lookControls = { values: lookValues, disabled: !editable, onChange: (patch: PlanEdits) => set(patch) };
  const visibleTools = TOOLS.filter(([, , , only]) => t1 || !only);
  const activeTool: Tool = visibleTools.some(([id]) => id === tool) ? tool : "style";

  async function act(label: string, task: () => Promise<unknown>) {
    if (actionInFlight.current) return;
    actionInFlight.current = true;
    flushSync(() => { setBusy(label); setError(""); });
    try { await task(); await onChanged(); setDraft({}); }
    catch (e) { setError(friendlyError(e, label)); }
    finally { actionInFlight.current = false; setBusy(""); }
  }
  const save = () => act("save the plan", () => api.editStudioPlan(project.id, latest.id, draft));
  const approve = () => act("approve the plan", () => api.approveStudioPlan(project.id, latest.id));
  const reanalyze = (edits: PlanEdits, what: string) => {
    if (!window.confirm(`${what}\nتصمیم‌های تدوین برای این انتخاب دوباره ساخته می‌شود (یک درخواست به مدل هوش مصنوعی). برنامهٔ تازه دوباره برای تأیید شما می‌آید.`)) return;
    void act("change the plan", () => api.editStudioPlan(project.id, latest.id, edits));
  };
  const restore = () => {
    const edits = restoreEdits(latest.content, shown.content);
    if (!Object.keys(edits).length) { setViewing(null); return; }
    if (edits.style && !window.confirm("بازگرداندن این نسخه سبک تدوین را عوض می‌کند و تصمیم‌ها دوباره ساخته می‌شوند. ادامه می‌دهید؟")) return;
    void act("restore the plan", () => api.editStudioPlan(project.id, latest.id, edits));
  };
  const words = hook.split(/\s+/).filter(Boolean);

  const actions = isLatest && phase !== "rendering" && !superseding ? <footer className="plan-actions">
      {dirty ? <>
        <button className="btn" disabled={locked} onClick={() => void save()}>{busy === "save the plan" ? "در حال ذخیره…" : "ذخیرهٔ تغییرات"}</button>
        <button className="btn btn-secondary" disabled={locked} onClick={() => setDraft({})}>لغو</button>
        <small>تغییرات یک نسخهٔ جدید از برنامه می‌سازند و دوباره تأیید شما لازم است.</small>
      </> : phase === "awaiting" ? <>
        <button className="btn" disabled={locked} onClick={() => void approve()}><Icon name="check" size={16}/>{busy === "approve the plan" ? "در حال شروع…" : "تأیید و شروع رندر"}</button>
        <small>رندر فقط با همین نسخه از برنامه انجام می‌شود.</small>
      </> : null}
    </footer> : null;

  return <div className="plan" dir="rtl" aria-busy={Boolean(busy)}>
    {busy ? <div className="notice" role="status" aria-live="polite"><span className="act-dot" aria-hidden="true"/> {busy === "approve the plan" ? "در حال ارسال تأیید و شروع رندر…" : "در حال ذخیره و به‌روزرسانی برنامه…"}</div> : null}
    <header className="plan-head">
      <div>
        <h2>برنامهٔ تدوین</h2>
        <p>نسخهٔ {shown.n}{shown.note ? ` · ${shown.note}` : ""} · {SOURCE_LABEL[shown.source] || shown.source}</p>
      </div>
      {PHASE_LABEL[phase] ? <span className="badge" data-tone={phase === "awaiting" ? "warning" : phase === "failed" ? "error" : phase === "done" || phase === "approved" ? "success" : "working"}><i/>{PHASE_LABEL[phase]}</span> : null}
    </header>
    {versions.length > 1 ? <div className="plan-history">
      <label htmlFor="plan-version">نسخه‌ها</label>
      <select id="plan-version" className="input" value={shown.id} onChange={event => setViewing(event.target.value === latest.id ? null : event.target.value)}>
        {[...versions].reverse().map(item => <option key={item.id} value={item.id}>نسخهٔ {item.n} · {SOURCE_LABEL[item.source] || item.source}{item.id === latest.id ? " (فعلی)" : ""}</option>)}
      </select>
      {!isLatest ? <button className="btn btn-sm btn-secondary" disabled={locked} onClick={restore}>بازگرداندن این نسخه</button> : null}
    </div> : null}
    {phase === "analyzing" ? <div className="notice" role="status">برنامه در حال ساخته‌شدن است؛ وقتی آماده شد همین‌جا نمایش داده می‌شود.</div> : null}
    {phase === "rendering" ? <div className="notice" role="status">این برنامه تأیید شده و در حال رندر است. برای تغییر بعدی، بعد از پایان رندر همین‌جا یا در چت اقدام کنید.</div> : null}
    {!isLatest ? <div className="notice" data-tone="warning">نسخهٔ قدیمی را می‌بینید؛ فقط نسخهٔ فعلی قابل ویرایش و تأیید است.</div> : null}
    {error ? <div className="notice" data-tone="error" role="alert">{error}</div> : null}

    <div className="editor-top">
      {t1 ? <LookStage jobId={project.external_ref!} values={lookValues} close={previewClose}/> : null}
      <nav className="editor-tools" aria-label="ابزارهای ویرایش">{visibleTools.map(([id, label, icon]) =>
        <button key={id} type="button" className="editor-tool" aria-pressed={activeTool === id} onClick={() => setTool(id)}><Icon name={icon} size={20}/><span>{label}</span></button>)}</nav>
    </div>

    {plan.concepts.length ? <Section tool="style" current={activeTool} title="ایده‌های خلاقانه" summary={plan.concepts.find(c => c.selected)?.name} hint="ایده‌ها از محتوای واقعی ویدیوی شما ساخته شده‌اند. پیش‌نمایش‌ها یک فریم از ویدیوی شما با متن، کادر و رنگ واقعی هر سبک‌اند؛ تصویر بالای سبک‌های ۲ و ۳ فقط نمونه است و در ویدیو برای هر بخش تصویر مخصوص ساخته می‌شود.">
      <div className="plan-cards">{plan.concepts.map(concept => <article key={concept.id} className="plan-card" data-selected={concept.selected || undefined}>
        <Mockup project={project} frame={plan.frames?.[`concept-${concept.id}`]} label={concept.name}/>
        <div className="plan-card-body">
          <div className="plan-card-title"><b>{concept.name}</b>{concept.selected ? <span className="badge" data-tone="success"><i/>انتخاب فعلی</span> : null}</div>
          <p>{concept.angle}</p>
          {concept.hook ? <p className="plan-quote" title={concept.hook}>شروع: {concept.hook}</p> : null}
          <small>{plan.style_options.find(item => item.id === concept.style)?.label}</small>
          {!concept.selected && editable ? <button className="btn btn-sm btn-secondary" onClick={() => reanalyze({ concept_id: concept.id }, `ایدهٔ «${concept.name}» انتخاب شود؟`)}>انتخاب این ایده</button> : null}
        </div>
      </article>)}</div>
    </Section> : null}

    <Section tool="style" current={activeTool} title="سبک تدوین" summary={plan.style.label} hint={plan.style.summary}>
      <div className="plan-cards plan-cards-styles">{plan.style_options.map(option => <article key={option.id} className="plan-card" data-selected={option.id === plan.style.id || undefined}>
        <Mockup project={project} frame={plan.frames?.[`style-${option.id}`]} label={option.label}/>
        <div className="plan-card-body">
          <div className="plan-card-title"><b>{option.label}</b><small>{option.complexity}</small></div>
          <p>{option.summary}</p>
          {option.id === plan.style.id ? <span className="badge" data-tone="success"><i/>سبک فعلی</span>
            : editable ? <button className="btn btn-sm btn-secondary" onClick={() => reanalyze({ style: option.id }, `سبک «${option.label}» انتخاب شود؟`)}>انتخاب این سبک</button> : null}
        </div>
      </article>)}</div>
    </Section>

    <Section tool="details" current={activeTool} title="هدف و پیام" summary={plan.goal || plan.message}>
      <dl className="plan-facts">
        {plan.goal ? <><dt>هدف</dt><dd>{plan.goal}</dd></> : null}
        {plan.audience ? <><dt>مخاطب</dt><dd>{plan.audience}</dd></> : null}
        {plan.message ? <><dt>پیام اصلی</dt><dd>{plan.message}</dd></> : null}
        {plan.tone ? <><dt>لحن</dt><dd>{plan.tone}</dd></> : null}
        {plan.concept.angle ? <><dt>ایده</dt><dd>{plan.concept.angle}</dd></> : null}
      </dl>
    </Section>

    <Section tool="hook" current={activeTool} title="هوک ابتدایی" summary={hook} hint="جملهٔ ثانیه‌های اول. روی هر کلمه بزنید تا رنگی شود (حداکثر دو کلمه).">
      <textarea className="input bidi" dir="auto" rows={2} value={hook} disabled={!editable} maxLength={120}
        onChange={event => set({ hook: event.target.value, hook_highlight: highlight.filter(word => event.target.value.includes(word)) })}/>
      <div className="chip-row plan-words">{words.map((word, index) => <button key={`${word}-${index}`} type="button" className="chip" disabled={!editable}
        aria-pressed={highlight.includes(word)} onClick={() => set({ hook_highlight: toggleHighlight(highlight, word) })}>{word}</button>)}</div>
    </Section>

    {plan.structure.length ? <Section tool="details" current={activeTool} title="ساختار روایت" summary={`${plan.structure.length} بخش`}>
      <ol className="plan-beats">{plan.structure.map((beat, index) => <li key={index}>
        <span className="plan-beat-at">{beat.at || "—"}</span>
        <div><b>{roleLabel(beat.role, index)}</b>{beat.text ? <p className="bidi" dir="auto">«{beat.text}»</p> : null}
          {beat.visual ? <details className="plan-beat-visual"><summary>ایدهٔ تصویری</summary><small>{beat.visual}</small></details> : null}</div>
      </li>)}</ol>
    </Section> : null}

    <Section tool="light" current={activeTool} title="نور و رنگ" summary={LOOKS.find(([key]) => key === value("look", plan.look.preset))?.[1] || "رنگ سفارشی"}>
      <div className="field"><span className="field-label">رنگ و نور</span>
        <div className="segmented" role="group" aria-label="رنگ و نور">{LOOKS.map(([key, label]) => <button key={key} type="button" disabled={!editable}
          aria-pressed={value("look", plan.look.preset) === key} onClick={() => set({ look: key })}>{label}</button>)}</div>
        {plan.look.preset === "custom" && !("look" in draft) ? <small className="field-hint">رنگ‌بندی فعلی دستی تنظیم شده است.</small> : null}
      </div>
      {t1 ? <LightControls {...lookControls}/> : null}
    </Section>
    {t1 ? <Section tool="frame" current={activeTool} title="کادر" summary={`${value("shift_x", plan.look.framing?.shift_x ?? 0)} · ${value("shift_y", plan.look.framing?.shift_y ?? 0)}`}>
      <FrameControls {...lookControls}/>
    </Section> : null}
    <Section tool="zoom" current={activeTool} title="زوم" summary={`زوم ${value("zoom", plan.look.zoom)}٪`}>
      {t1 ? <ZoomControls {...lookControls} close={previewClose} setClose={setPreviewClose}/> : <>
      {plan.style.id === 'talking_1' ? null : <>
      <div className="field"><label htmlFor="plan-zoom">زوم روی گوینده: {value("zoom", plan.look.zoom)}٪</label>
        <input id="plan-zoom" type="range" min={0} max={200} step={10} disabled={!editable} value={value("zoom", plan.look.zoom)} onChange={event => set({ zoom: Number(event.target.value) })}/></div>
      </>}
      {plan.style.id === 'talking_1' ? null : <>
      <EditSwitch label="زوم‌های دوربین روی گوینده" disabled={!editable} checked={value("zoom_enabled", plan.look.zoom_enabled ?? true)} onChange={checked => set({ zoom_enabled: checked })}/>
      {value("zoom_enabled", plan.look.zoom_enabled ?? true) ? <div className="plan-grid">
        <div className="field"><label htmlFor="plan-zbase">زوم قاب اصلی: {value("zoom_base", plan.look.zoom_base ?? 100)}٪</label>
          <input id="plan-zbase" type="range" min={100} max={180} step={5} disabled={!editable} value={value("zoom_base", plan.look.zoom_base ?? 100)} onChange={event => set({ zoom_base: Number(event.target.value) })}/></div>
        <div className="field"><label htmlFor="plan-zclose">زوم قاب نزدیک: {value("zoom_close", plan.look.zoom_close ?? 125)}٪</label>
          <input id="plan-zclose" type="range" min={100} max={220} step={5} disabled={!editable} value={value("zoom_close", plan.look.zoom_close ?? 125)} onChange={event => set({ zoom_close: Number(event.target.value) })}/></div>
      </div> : null}
      </>}
      </>}
    </Section>
    <Section tool="text" current={activeTool} title="متن و تأکید" summary={value("accent_color", plan.look.accent_color)}>
      <div className="field"><span className="field-label">رنگ تأکیدی (هوک و کلیدواژه‌ها)</span>
        <div className="plan-swatches">{ACCENTS.map(colour => <button key={colour} type="button" className="plan-swatch" style={{ background: colour }} disabled={!editable}
          aria-pressed={value("accent_color", plan.look.accent_color).toUpperCase() === colour} aria-label={colour} onClick={() => set({ accent_color: colour })}/>)}
          <input type="color" aria-label="رنگ دلخواه" disabled={!editable} value={value("accent_color", plan.look.accent_color)} onChange={event => set({ accent_color: event.target.value.toUpperCase() })}/></div>
      </div>
      <div className="field"><span className="field-label">فونت کپشن</span>
        <div className="segmented" role="group" aria-label="فونت کپشن">{FONTS.map(([key, label]) => <button key={key} type="button" disabled={!editable}
          aria-pressed={value("caption_font", plan.look.caption_font) === key} onClick={() => set({ caption_font: key })}>{label}</button>)}</div>
        <small className="field-hint">{plan.captions}</small>
      </div>
      {plan.style.id === 'talking_1' ? <div className="field"><label htmlFor="plan-bottom-shade">شدت فید مشکی پایین: {value('bottom_shade', plan.look.bottom_shade ?? 0)}٪</label>
        <input id="plan-bottom-shade" type="range" min={0} max={60} step={1} disabled={!editable} value={value('bottom_shade',plan.look.bottom_shade ?? 0)} onChange={event=>set({bottom_shade:Number(event.target.value)})}/></div> : null}
      <EditSwitch label="تأکید بصری روی لحظه‌های کلیدی" disabled={!editable} checked={value("key_moments", plan.look.key_moments)} onChange={checked => set({ key_moments: checked })}/>
      <div className="field"><span className="field-label">افکت لحظه‌های کلیدی</span>
        <div className="segmented" role="group" aria-label="نوع افکت">{KEY_EFFECTS.map(([key, label]) => <button key={key} type="button" disabled={!editable || !value("key_moments", plan.look.key_moments)}
          aria-pressed={value("key_moment_effect", plan.look.key_moment_effect ?? "grayscale_title") === key} onClick={() => set({ key_moment_effect: key })}>{label}</button>)}</div></div>
      <EditSwitch label="لحظهٔ کلیدی اول (Cold open): تیزر کوتاه قبل از شروع" disabled={!editable} checked={value("cold_open", plan.look.cold_open ?? true)} onChange={checked => set({ cold_open: checked })}/>
      {(plan.look.moments?.length ?? 0) > 0 && value("cold_open", plan.look.cold_open ?? true) ? <div className="field"><label htmlFor="plan-cold">انتخاب لحظهٔ اول</label>
        <select id="plan-cold" className="input" disabled={!editable} value={String(value("cold_open_sentence", plan.look.cold_open_sentence ?? null) ?? "")} onChange={event => set({ cold_open_sentence: event.target.value === "" ? null : Number(event.target.value) })}>
          <option value="">پیشنهاد هوش مصنوعی</option>{(plan.look.moments ?? []).map((m, i) => <option key={`${m.sentence}-${i}`} value={m.sentence}>{i + 1}. {m.title}</option>)}</select></div> : null}
    </Section>

    <Section tool="brand" current={activeTool} title="هویت و برند" summary={[value("name", plan.brand.name), value("cta", plan.brand.cta)].filter(Boolean).join(" · ")} hint="این موارد در پروفایل شما ذخیره می‌شوند تا در پروژه‌های بعدی دوباره پرسیده نشوند.">
      <div className="plan-grid">
        <div className="field"><label htmlFor="plan-name">نام گوینده</label><input id="plan-name" className="input bidi" dir="auto" disabled={!editable} value={value("name", plan.brand.name)} onChange={event => set({ name: event.target.value })} placeholder="بدون نام"/></div>
        <div className="field"><label htmlFor="plan-tagline">سمت یا تگ‌لاین</label><input id="plan-tagline" className="input bidi" dir="auto" disabled={!editable} value={value("tagline", plan.brand.tagline)} onChange={event => set({ tagline: event.target.value })} placeholder="بدون تگ‌لاین"/></div>
      </div>
      <div className="field"><label htmlFor="plan-cta">دعوت به اقدام پایانی</label><input id="plan-cta" className="input bidi" dir="auto" disabled={!editable} value={value("cta", plan.brand.cta)} onChange={event => set({ cta: event.target.value })} placeholder="بدون CTA"/></div>
      <EditSwitch label="لوگوی متحرک در پایان ویدیو" disabled={!editable} checked={value("logo_enabled", plan.brand.logo.enabled)} onChange={checked => set({ logo_enabled: checked })}/>
      {value("logo_enabled", plan.brand.logo.enabled) ? <div className="segmented" role="group" aria-label="حرکت لوگو">{LOGO_MOTIONS.map(([key, label]) => <button key={key} type="button" disabled={!editable}
        aria-pressed={value("logo_motion", plan.brand.logo.motion) === key} onClick={() => set({ logo_motion: key })}>{label}</button>)}</div> : null}
      {value("logo_enabled", plan.brand.logo.enabled) && !plan.brand.logo.has_logo ? <small className="field-hint">لوگویی ثبت نشده؛ لوگوی پیش‌فرض استفاده می‌شود. می‌توانید فایل لوگو را در چت بفرستید.</small> : null}
    </Section>

    <Section tool="details" current={activeTool} title="جزئیات تولید" summary={estimateText(plan)}>
      <dl className="plan-facts">
        <dt>حرکت و موشن</dt><dd>{plan.motion}</dd>
        <dt>تصاویر مکمل</dt><dd>{plan.broll}{plan.pictures.length ? <ul>{plan.pictures.map((item, index) => <li key={index}>{item.title || `جملهٔ ${(item.sentence ?? 0) + 1}`}{" · "}{PICTURE_SOURCE[item.source] || item.source}</li>)}</ul> : null}
          {plan.estimate.new_images ? <small className="field-hint">{plan.estimate.new_images} تصویر تازه بعد از تأیید همین نسخه ساخته می‌شود؛ تأیید برنامه، تأیید یک‌جای همهٔ آن‌هاست. هر تصویر را می‌توانید در تایم‌لاین عوض یا حذف کنید.</small> : null}</dd>
        <dt>صدا</dt><dd>{plan.audio.voice} · {plan.audio.sfx}{plan.audio.music ? ` · موسیقی: ${plan.audio.music}` : ""}</dd>
        <dt>قالب</dt><dd>{plan.format.aspect} · {plan.format.resolution} · {plan.format.fps}fps · حدود {Math.round(plan.duration_s)} ثانیه منبع</dd>
        <dt>موتورها</dt><dd>{plan.engines.join("، ")}</dd>
        <dt>زمان رندر</dt><dd>{estimateText(plan)}</dd>
        <dt>هزینه</dt><dd>{plan.estimate.note}</dd>
      </dl>
    </Section>

    {actions && footerSlot ? createPortal(actions, footerSlot) : actions}
  </div>;
}
