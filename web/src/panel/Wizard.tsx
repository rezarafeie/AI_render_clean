import React from "react";
import { api, type CloudFile, type StudioAttachment, type StudioFile } from "../api";
import { Icon } from "../components/Icon";
import { AuthenticatedMedia, useAuthenticatedMediaUrl } from "../AuthenticatedMedia";
import { friendlyError } from "../ui";
import { useProFonts, loadFontFaces } from "../studio/FontPicker";
import { engines } from "./Setup";
import { StylePreview, archetypeOf } from "./StylePreview";
import type { Capabilities, Engine, FilmStyleCard, Setup as SetupData, WizardCatalog } from "./types";

const FilesPicker = React.lazy(() => import("../studio/FilesPicker").then(m => ({ default: m.FilesPicker })));
const CloudPicker = React.lazy(() => import("../studio/CloudPicker").then(m => ({ default: m.CloudPicker })));

type StepId = "type" | "content" | "media" | "edit" | "style" | "font" | "color" | "voice" | "music" | "review";
const MOTION: Engine[] = ["motion", "vox", "story", "product", "storyboard"];
const SOURCE: Engine[] = ["talking", "localize", "clips", "discovery"];

function stepsFor(engine: Engine): StepId[] {
  if (MOTION.includes(engine)) return ["type", "content", "style", "font", "color", "voice", "music", "review"];
  if (engine === "talking") return ["type", "media", "edit", "review"];
  return ["type", "media", "review"];
}
const STEP_NAME: Record<StepId, string> = { type: "نوع ویدیو", content: "محتوا", media: "ویدیو", edit: "سبک تدوین", style: "سبک فیلم", font: "فونت",
  color: "رنگ", voice: "صدا", music: "موسیقی", review: "ساخت" };
const STEP_HINT: Record<StepId, string> = {
  type: "چه ویدیویی می‌خواهی بسازی؟", content: "دربارهٔ چیست و از چه چیزی ساخته شود؟", media: "ویدیوی خودت را اضافه کن",
  edit: "تدوین با چه حال‌وهوایی باشد؟", style: "زبان تصویری فیلم را انتخاب کن — هر کارت پیش‌نمایش زندهٔ همان سبک است",
  font: "تیترها با کدام فونت نوشته شوند؟", color: "رنگ‌های فیلم", voice: "چه کسی و با چه لحنی روایت کند؟", music: "موسیقی زمینه", review: "همه‌چیز آماده است",
};

/* ── the live mini-frame every preview uses ───────────────────────────────────── */
function Frame({ palette, title, font, motion = "slide", aspect = "vertical", big = false, playing = true }:
  { palette: string[]; title: string; font?: string; motion?: string; aspect?: string; big?: boolean; playing?: boolean }) {
  const [bg, surface, accent, ink] = [palette[0] || "#111318", palette[1] || "#1d2230", palette[2] || "#f2b84b", palette[3] || "#f5f1e8"];
  const ratio = aspect === "landscape" ? "16 / 9" : aspect === "square" ? "1 / 1" : "9 / 16";
  return <div className="wz-frame" data-motion={motion} data-big={big || undefined} data-playing={playing || undefined}
    style={{ aspectRatio: ratio, ["--f-bg" as string]: bg, ["--f-surface" as string]: surface, ["--f-accent" as string]: accent, ["--f-ink" as string]: ink }}>
    <span className="wz-f-blob a"/><span className="wz-f-blob b"/>
    <span className="wz-f-bar"/>
    <b className="wz-f-title" style={font ? { fontFamily: font } : undefined}>{title || "عنوان ویدیوی تو"}</b>
    <span className="wz-f-line"/><span className="wz-f-line short"/>
    <span className="wz-f-chip">{"●"}</span>
  </div>;
}

function MusicRow({ track, active, onPick }: { track: WizardCatalog["music"][number]; active: boolean; onPick: () => void }) {
  const [play, setPlay] = React.useState(false);
  const url = useAuthenticatedMediaUrl(play ? api.libraryMusicUrl(track.file) : null);
  const ref = React.useRef<HTMLAudioElement>(null);
  React.useEffect(() => { if (url && ref.current) void ref.current.play().catch(() => setPlay(false)); }, [url]);
  return <li className="wz-track" aria-selected={active}>
    <button type="button" className="wz-play" aria-label={play ? "توقف" : "پخش نمونه"} onClick={() => { if (play) { ref.current?.pause(); setPlay(false); } else setPlay(true); }}>
      <Icon name={play ? "close" : "play"} size={14}/></button>
    <button type="button" className="wz-track-pick" onClick={onPick}><b>{track.label || track.file}</b><small>{[track.mood, track.energy ? `انرژی ${track.energy}/۵` : ""].filter(Boolean).join(" · ")}</small></button>
    {play && url ? <audio ref={ref} src={url} onEnded={() => setPlay(false)}/> : null}
    {active ? <span className="wz-tick"><Icon name="check" size={14}/></span> : null}
  </li>;
}

type Props = { id: string; initial: SetupData; capabilities: Capabilities; onStarted: () => Promise<unknown> };

export function Wizard({ id, initial, capabilities, onStarted }: Props) {
  const [data, setData] = React.useState<SetupData>(initial);
  const [step, setStep] = React.useState<StepId>("type");
  const [dir, setDir] = React.useState<1 | -1>(1);
  const [catalog, setCatalog] = React.useState<WizardCatalog | null>(null);
  const [assets, setAssets] = React.useState<Record<string, StudioAttachment>>({});
  const [picker, setPicker] = React.useState<"files" | "cloud" | null>(null);
  const [busy, setBusy] = React.useState("");
  const [error, setError] = React.useState("");
  const [query, setQuery] = React.useState("");
  const [launch, setLaunch] = React.useState(false);
  const [sample, setSample] = React.useState("سلام! این یک نمونهٔ کوتاه از صدای گوینده برای ویدیوی توست.");
  const [playingVoice, setPlayingVoice] = React.useState<string | null>(null);
  const latest = React.useRef(initial);
  const persisted = React.useRef(JSON.stringify(initial));
  const queue = React.useRef(Promise.resolve());
  const fileRef = React.useRef<HTMLInputElement>(null);
  const { fonts } = useProFonts();
  const steps = stepsFor(data.engine);
  const index = Math.max(0, steps.indexOf(step));
  const style = catalog?.film_styles.find(s => s.id === data.film_style);
  const palette = data.palette?.length ? data.palette : style?.palette || ["#0f1115", "#1b1f2a", "#f2b84b", "#f6f1e7"];
  const font = fonts.find(f => f.id === data.title_font);
  const fontFamily = font ? `lib-${font.faces?.[0]?.css_family ?? font.id}` : undefined;
  const title = data.topic.trim().split(/\s+/).slice(0, 5).join(" ") || data.title || "";

  React.useEffect(() => { api.panelWizardCatalog().then(setCatalog).catch(e => setError(friendlyError(e, "load the choices"))); }, []);
  React.useEffect(() => { if (font) void loadFontFaces(font); }, [font]);
  React.useEffect(() => {
    let alive = true;
    api.panelDraftMedia(id).then(rows => { if (alive) setAssets(c => ({ ...Object.fromEntries(rows.map(r => [r.id, r])), ...c })); }).catch(() => {});
    return () => { alive = false; };
  }, [id]);

  const save = React.useCallback((value: SetupData) => {
    const key = JSON.stringify(value);
    const task = queue.current.catch(() => {}).then(async () => { if (key !== persisted.current) { await api.savePanelSetup(id, value); persisted.current = key; } });
    queue.current = task;
    return task;
  }, [id]);
  React.useEffect(() => {
    if (JSON.stringify(data) === persisted.current) return;
    const timer = setTimeout(() => void save(data).catch(e => setError(friendlyError(e, "save the draft"))), 450);
    return () => clearTimeout(timer);
  }, [data, save]);
  const titled = React.useRef("");
  React.useEffect(() => {
    if (step !== "review") return;
    const text = [data.topic, data.source_url, engines.find(e => e.id === data.engine)?.name].filter(Boolean).join(" — ");
    const generic = !data.title.trim() || /^(پروژهٔ? ?(جدید|دستی جدید)|New project)$/i.test(data.title.trim());
    if (!generic || text.trim().length < 3 || titled.current === text) return;
    titled.current = text;
    api.panelTitleIdea(text).then(r => { if (r.title && (!latest.current.title.trim() || /^(پروژهٔ? ?(جدید|دستی جدید)|New project)$/i.test(latest.current.title.trim()))) update({ title: r.title }); }).catch(() => {});
  }, [step]);
  const update = (next: Partial<SetupData>) => { latest.current = { ...latest.current, ...next }; setData(latest.current); };
  const go = (target: StepId) => { setDir(steps.indexOf(target) >= index ? 1 : -1); setStep(target); setError(""); window.scrollTo({ top: 0, behavior: "smooth" }); };
  const next = () => { if (index < steps.length - 1) go(steps[index + 1]); };
  const back = () => { if (index > 0) go(steps[index - 1]); };

  const add = (file: StudioAttachment) => { setAssets(c => ({ ...c, [file.id]: file })); update({ attachment_ids: [...new Set([...latest.current.attachment_ids, file.id])].slice(0, 16) }); };
  async function upload(file?: File) {
    if (!file) return;
    setBusy("در حال آپلود…"); setError("");
    try { add(await api.uploadStudioMedia(id, file, p => setBusy(`آپلود ${Math.round(p)}٪`))); }
    catch (e) { setError(friendlyError(e, "upload this file")); } finally { setBusy(""); }
  }
  async function attach(files: StudioFile[]) {
    setBusy("در حال افزودن فایل…");
    try { for (const f of files.slice(0, 16 - latest.current.attachment_ids.length)) add(await api.attachStudioFile(id, f.id)); } finally { setBusy(""); }
  }
  async function cloud(files: CloudFile[]) {
    setBusy("در حال دریافت از Drive…");
    try {
      const result = await api.cloudImport("googledrive", id, files.map(f => f.id));
      for (let t of result.transfers) {
        const limit = Date.now() + 10 * 60 * 1000;
        while (!["completed", "failed", "cancelled"].includes(t.state) && Date.now() < limit) { await new Promise(r => setTimeout(r, 1800)); t = await api.cloudTransfer(id, t.id); }
        if (t.attachment_id && t.state === "completed") add({ id: t.attachment_id, filename: t.filename, mime_type: "", size_bytes: t.size ?? 0, kind: t.kind === "video" || t.kind === "audio" ? t.kind : "image" });
        else setError(t.error || "انتقال کامل نشد.");
      }
    } finally { setBusy(""); }
  }
  async function start() {
    setLaunch(true); setBusy("در حال شروع ساخت…"); setError("");
    try { await save(latest.current); await new Promise(r => setTimeout(r, 900)); await api.startPanelWork(id); await onStarted(); }
    catch (e) { setLaunch(false); setError(friendlyError(e, "start this project")); } finally { setBusy(""); }
  }

  const sourceVideo = SOURCE.includes(data.engine);
  const canNext = step === "type" ? true : step === "content" ? Boolean(data.topic.trim() || data.source_url || data.attachment_ids.length)
    : step === "media" ? data.attachment_ids.length > 0 : true;
  const styles = (catalog?.film_styles || []).filter(s => !query.trim() || `${s.title} ${s.summary} ${s.mood} ${s.id}`.includes(query.trim()));
  const media = <>
    <div className="wz-drop" onClick={() => fileRef.current?.click()} role="button" tabIndex={0} onKeyDown={e => e.key === "Enter" && fileRef.current?.click()}
      onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); void upload(e.dataTransfer.files?.[0]); }}>
      <span className="wz-drop-orb"><Icon name="paperclip" size={22}/></span>
      <b>{sourceVideo ? "ویدیو را اینجا رها کن یا کلیک کن" : "عکس، ویدیو یا صدا (اختیاری)"}</b>
      <small>یا از <button type="button" className="link" onClick={e => { e.stopPropagation(); setPicker("files"); }}>فایل‌های حساب</button> و <button type="button" className="link" onClick={e => { e.stopPropagation(); setPicker("cloud"); }}>Google Drive</button></small>
      <input hidden type="file" ref={fileRef} accept={sourceVideo ? "video/*" : "image/*,audio/*,video/*"} onChange={e => { void upload(e.target.files?.[0]); e.target.value = ""; }}/>
    </div>
    {data.attachment_ids.length ? <ul className="wz-files">{data.attachment_ids.map(a => <li key={a}>
      {assets[a]?.kind === "image" ? <AuthenticatedMedia as="img" src={api.studioAttachmentUrl(id, a)} alt=""/> : <span className="wz-file-icon"><Icon name={assets[a]?.kind === "audio" ? "mic2" : "film"} size={18}/></span>}
      <span>{assets[a]?.filename || "فایل"}</span>
      <button type="button" className="icon-btn" aria-label="برداشتن" onClick={() => update({ attachment_ids: data.attachment_ids.filter(x => x !== a) })}><Icon name="close" size={15}/></button>
    </li>)}</ul> : null}
  </>;

  return <section className="wz" dir="rtl" data-launch={launch || undefined}>
    <div className="wz-sky" aria-hidden="true"><span/><span/><span/><span/><span/><span/></div>
    <nav className="wz-path" aria-label="مراحل ساخت">
      {steps.map((s, i) => <button key={s} type="button" className="wz-star" data-state={i < index ? "done" : i === index ? "now" : "next"}
        disabled={i > index && !canNext} onClick={() => i <= index || canNext ? go(s) : undefined} aria-current={i === index ? "step" : undefined}>
        <span className="wz-star-dot">{i < index ? <Icon name="check" size={12}/> : i + 1}</span><span className="wz-star-name">{STEP_NAME[s]}</span>
      </button>)}
      <span className="wz-path-glow" style={{ width: `${steps.length > 1 ? (index / (steps.length - 1)) * 100 : 0}%` }}/>
    </nav>

    <header className="wz-head" key={`h-${step}`}><h1>{STEP_HINT[step]}</h1></header>

    <div className="wz-stage" key={step} data-dir={dir}>
      {step === "type" && <div className="wz-types">{engines.map(e => {
        const off = e.claude && !capabilities.claude_motion;
        return <button key={e.id} type="button" className="wz-type" aria-pressed={data.engine === e.id} disabled={off}
          onClick={() => update({ engine: e.id, style: "", style_profile: null, motion_so: false })}>
          <span className="wz-type-art" data-engine={e.id}><Icon name={e.icon} size={26}/><i/><i/><i/></span>
          <b>{e.name}</b><small>{off ? "روی این سرور فعال نیست" : e.detail}</small>
        </button>;
      })}</div>}

      {step === "content" && <div className="wz-two">
        <div className="wz-form">
          <label>دربارهٔ چیست؟<textarea className="input bidi" dir="auto" rows={4} maxLength={1000} value={data.topic} onChange={e => update({ topic: e.target.value })}
            placeholder="مثلاً: معرفی اپ یادگیری زبان برای نوجوان‌ها، با لحن شاد و سه ویژگی اصلی"/></label>
          <label>لینک صفحهٔ منبع (اختیاری)<input type="url" dir="ltr" className="input" value={data.source_url} onChange={e => update({ source_url: e.target.value })} placeholder="https://"/></label>
          <div className="wz-pills" role="radiogroup" aria-label="مدت">{[15, 30, 45, 60].map(n => <button key={n} type="button" role="radio" aria-checked={data.seconds === n}
            onClick={() => update({ seconds: n as SetupData["seconds"] })}>{n} ثانیه</button>)}</div>
          <div className="wz-pills" role="radiogroup" aria-label="قطع">{([["vertical", "عمودی ۹:۱۶"], ["square", "مربع ۱:۱"], ["landscape", "افقی ۱۶:۹"]] as const).map(([v, l]) =>
            <button key={v} type="button" role="radio" aria-checked={(data.aspect === "source" ? "vertical" : data.aspect) === v} onClick={() => update({ aspect: v })}>{l}</button>)}</div>
          {media}
        </div>
        <aside className="wz-preview">{style ? <StylePreview archetype={archetypeOf(style.id, `${style.summary} ${style.title}`, style.archetype)} palette={palette} title={title} font={fontFamily} aspect={data.aspect} big/>
          : <Frame palette={palette} title={title} font={fontFamily} aspect={data.aspect} big/>}<small>پیش‌نمایش زنده — با هر انتخاب به‌روز می‌شود</small></aside>
      </div>}

      {step === "media" && <div className="wz-form wz-narrow">
        {media}
        {data.engine === "discovery" ? <label>محور کلیپ‌ها (اختیاری)<input className="input" maxLength={600} value={data.topic} onChange={e => update({ topic: e.target.value })} placeholder="مثلاً بخش‌هایی دربارهٔ جذب مشتری"/></label> : null}
        {data.engine === "clips" ? <div className="wz-pills" role="radiogroup" aria-label="قطع">{([["source", "همان منبع"], ["vertical", "عمودی"], ["square", "مربع"], ["landscape", "افقی"]] as const).map(([v, l]) =>
          <button key={v} type="button" role="radio" aria-checked={data.aspect === v} onClick={() => update({ aspect: v })}>{l}</button>)}</div> : null}
      </div>}

      {step === "edit" && <div className="wz-grid">
        <button type="button" className="wz-card" aria-pressed={!data.style} onClick={() => update({ style: "" })}>
          <span className="wz-card-art auto"><Icon name="spark" size={26}/></span><b>پیشنهاد موتور</b><small>بعد از تحلیل ویدیو بهترین سبک را خودش انتخاب می‌کند</small></button>
        {[...capabilities.talking_styles, { id: "premium", label: "پریمیوم تمام‌قاب" }].map((s, i) => <button key={s.id} type="button" className="wz-card" aria-pressed={data.style === s.id} onClick={() => update({ style: s.id })}>
          <Frame palette={(catalog?.palettes[i % (catalog?.palettes.length || 1)]?.colors) || palette} title={s.label} motion={["slide", "pop", "zoom", "drift"][i % 4]}/><b>{s.label}</b></button>)}
      </div>}

      {step === "style" && <>
        <div className="wz-toolbar"><input className="input" value={query} onChange={e => setQuery(e.target.value)} placeholder="جست‌وجوی سبک: کاغذی، نئون، مستند، مینیمال…"/>
          <span className="eg-muted">{styles.length} سبک</span></div>
        <div className="wz-grid wz-styles">
          <button type="button" className="wz-card" aria-pressed={!data.film_style} onClick={() => update({ film_style: "", palette: [] })}>
            <span className="wz-card-art auto"><Icon name="spark" size={26}/></span><b>انتخاب خودکار</b><small>کارگردان سبک مناسب موضوع را انتخاب می‌کند</small></button>
          {styles.map((s: FilmStyleCard) => <button key={s.id} type="button" className="wz-card" aria-pressed={data.film_style === s.id}
            onClick={() => update({ film_style: s.id, palette: [] })}>
            <StylePreview archetype={archetypeOf(s.id, `${s.summary} ${s.title}`, s.archetype)} palette={s.palette} title={title || s.title} font={fontFamily} playing/>
            <b>{s.title}</b><small>{s.summary}</small>{s.mood ? <span className="wz-mood">{s.mood}</span> : null}
          </button>)}
        </div>
      </>}

      {step === "font" && <div className="wz-two">
        <div className="wz-grid wz-fonts">
          <button type="button" className="wz-card wz-font" aria-pressed={!data.title_font} onClick={() => update({ title_font: "" })}><b className="wz-font-sample">خودکار</b><small>فونت متناسب با سبک</small></button>
          {fonts.slice(0, 40).map(f => <FontCard key={f.id} font={f} text={title || "عنوان ویدیوی تو"} active={data.title_font === f.id} onPick={() => update({ title_font: f.id })}/>)}
        </div>
        <aside className="wz-preview">{style ? <StylePreview archetype={archetypeOf(style.id, `${style.summary} ${style.title}`, style.archetype)} palette={palette} title={title} font={fontFamily} aspect={data.aspect} big/>
          : <Frame palette={palette} title={title} font={fontFamily} aspect={data.aspect} big/>}</aside>
      </div>}

      {step === "color" && <div className="wz-two">
        <div className="wz-form">
          {style ? <button type="button" className="wz-palette" aria-pressed={!data.palette?.length} onClick={() => update({ palette: [] })}>
            <span>{style.palette.map(c => <i key={c} style={{ background: c }}/>)}</span><b>رنگ‌های سبک «{style.title}»</b></button> : null}
          {(catalog?.palettes || []).map(p => <button key={p.name} type="button" className="wz-palette" aria-pressed={JSON.stringify(data.palette) === JSON.stringify(p.colors)}
            onClick={() => update({ palette: p.colors })}><span>{p.colors.map(c => <i key={c} style={{ background: c }}/>)}</span><b>{p.name}</b></button>)}
          <div className="wz-custom"><b>رنگ دلخواه</b>{["زمینه", "سطح", "تأکید", "متن"].map((label, i) => <label key={label}>
            <input type="color" value={palette[i] || "#000000"} onChange={e => { const next = [...palette]; next[i] = e.target.value.toUpperCase(); update({ palette: next.slice(0, 4) }); }}/>{label}</label>)}</div>
        </div>
        <aside className="wz-preview">{style ? <StylePreview archetype={archetypeOf(style.id, `${style.summary} ${style.title}`, style.archetype)} palette={palette} title={title} font={fontFamily} aspect={data.aspect} big/>
          : <Frame palette={palette} title={title} font={fontFamily} aspect={data.aspect} big/>}</aside>
      </div>}

      {step === "voice" && <div className="wz-form">
        <label className="wz-sample">متنی که در تست شنیده می‌شود<input className="input bidi" dir="auto" maxLength={300} value={sample} onChange={e => setSample(e.target.value)}/></label>
        <div className="wz-pills" role="radiogroup" aria-label="لحن">{(catalog?.voice_styles || []).map(s => <button key={s.id} type="button" role="radio" aria-checked={(data.voice_style || "natural") === s.id}
          onClick={() => update({ voice_style: s.id })}>{s.label}</button>)}</div>
        <div className="wz-grid wz-voices" role="radiogroup" aria-label="گوینده">
          <div role="radio" tabIndex={0} className="wz-voice" aria-checked={!data.narrator} aria-pressed={!data.narrator} onClick={() => update({ narrator: "" })}
            onKeyDown={e => (e.key === "Enter" || e.key === " ") && update({ narrator: "" })}><span className="wz-wave"><i/><i/><i/><i/></span><b>پیشنهاد استودیو</b><small>گوینده‌ای متناسب با موضوع</small></div>
          {(catalog?.voices || []).map(v => <VoiceCard key={v.id} voice={v} active={data.narrator === v.id} text={sample} styleId={data.voice_style === "natural" ? "" : data.voice_style || ""}
            playing={playingVoice === v.id} onPlaying={setPlayingVoice} onPick={() => update({ narrator: v.id })}/>)}
        </div>
      </div>}

      {step === "music" && <div className="wz-form wz-narrow">
        <div className="wz-pills" role="radiogroup" aria-label="موسیقی">
          <button type="button" role="radio" aria-checked={!data.music || data.music === "auto"} onClick={() => update({ music: "auto" })}>انتخاب خودکار</button>
          <button type="button" role="radio" aria-checked={data.music === "off"} onClick={() => update({ music: "off" })}>بدون موسیقی</button>
        </div>
        <ul className="wz-tracks">{(catalog?.music || []).map(t => <MusicRow key={t.file} track={t} active={data.music === `library:${t.file}`} onPick={() => update({ music: `library:${t.file}` })}/>)}</ul>
        {catalog && !catalog.music.length ? <p className="eg-muted">کتابخانهٔ موسیقی خالی است؛ موسیقی خودکار انتخاب می‌شود.</p> : null}
      </div>}

      {step === "review" && <div className="wz-two">
        <div className="wz-summary">
          <Row label="نوع" value={engines.find(e => e.id === data.engine)?.name} onEdit={() => go("type")}/>
          {MOTION.includes(data.engine) ? <>
            <Row label="موضوع" value={data.topic || data.source_url || "از فایل‌ها"} onEdit={() => go("content")}/>
            <Row label="مدت و قطع" value={`${data.seconds} ثانیه · ${data.aspect === "landscape" ? "افقی" : data.aspect === "square" ? "مربع" : "عمودی"}`} onEdit={() => go("content")}/>
            <Row label="سبک فیلم" value={style?.title || "خودکار"} onEdit={() => go("style")}/>
            <Row label="فونت" value={font?.label || "خودکار"} onEdit={() => go("font")}/>
            <Row label="رنگ" value={<span className="wz-mini-pal">{palette.map(c => <i key={c} style={{ background: c }}/>)}</span>} onEdit={() => go("color")}/>
            <Row label="گوینده" value={(catalog?.voices.find(v => v.id === data.narrator)?.name || "پیشنهاد استودیو") + (data.voice_style && data.voice_style !== "natural" ? ` · ${catalog?.voice_styles.find(s => s.id === data.voice_style)?.label}` : "")} onEdit={() => go("voice")}/>
            <Row label="موسیقی" value={data.music === "off" ? "بدون موسیقی" : data.music?.startsWith("library:") ? data.music.slice(8) : "خودکار"} onEdit={() => go("music")}/>
          </> : <Row label="فایل‌ها" value={`${data.attachment_ids.length} فایل`} onEdit={() => go("media")}/>}
          {data.engine === "talking" ? <Row label="سبک تدوین" value={capabilities.talking_styles.find(s => s.id === data.style)?.label || (data.style === "premium" ? "پریمیوم" : "پیشنهاد موتور")} onEdit={() => go("edit")}/> : null}
          <label className="wz-mode">نام پروژه (پیشنهاد خودکار — قابل تغییر)<input className="input" maxLength={100} value={data.title} onChange={e => update({ title: e.target.value })}/></label>
        </div>
        <aside className="wz-preview">{MOTION.includes(data.engine) ? (style ? <StylePreview archetype={archetypeOf(style.id, `${style.summary} ${style.title}`, style.archetype)} palette={palette} title={title} font={fontFamily} aspect={data.aspect} big/>
          : <Frame palette={palette} title={title} font={fontFamily} aspect={data.aspect} big/>) : <div className="wz-ready"><Icon name="spark" size={34}/></div>}</aside>
      </div>}
    </div>

    {error ? <p className="notice" data-tone="error" role="alert">{error}</p> : null}
    <footer className="wz-foot">
      <button type="button" className="btn btn-secondary" onClick={back} disabled={index === 0 || Boolean(busy)}>قبلی</button>
      <span className="wz-busy" role="status">{busy}</span>
      {step === "review"
        ? <button type="button" className="btn btn-primary wz-launch" onClick={() => void start()} disabled={Boolean(busy) || (sourceVideo && !data.attachment_ids.length)}>
            <Icon name="spark" size={16}/>{busy || "بساز"}</button>
        : <button type="button" className="btn btn-primary" onClick={next} disabled={!canNext || Boolean(busy)}>{index === 0 ? "شروع" : "بعدی"}</button>}
    </footer>
    <React.Suspense fallback={null}>
      {picker === "files" && <FilesPicker onClose={() => setPicker(null)} onAttach={attach}/>}
      {picker === "cloud" && <CloudPicker onClose={() => setPicker(null)} onImport={cloud}/>}
    </React.Suspense>
  </section>;
}

/** A narrator card with its own test button: one tap plays the sample text in this voice and delivery (made on the server, a few seconds). */
function VoiceCard({ voice, active, text, styleId, playing, onPlaying, onPick }: { voice: WizardCatalog["voices"][number]; active: boolean; text: string; styleId: string;
  playing: boolean; onPlaying: (id: string | null) => void; onPick: () => void }) {
  const [state, setState] = React.useState<"idle" | "loading" | "error">("idle");
  const audio = React.useRef<HTMLAudioElement | null>(null);
  const cache = React.useRef<{ key: string; url: string } | null>(null);
  React.useEffect(() => { if (!playing) audio.current?.pause(); }, [playing]);
  React.useEffect(() => () => { audio.current?.pause(); if (cache.current) URL.revokeObjectURL(cache.current.url); }, []);
  const test = async (event: React.MouseEvent) => {
    event.stopPropagation();
    if (playing) { audio.current?.pause(); onPlaying(null); return; }
    const key = `${text}|${styleId}`;
    try {
      setState("loading");
      if (cache.current?.key !== key) { if (cache.current) URL.revokeObjectURL(cache.current.url); cache.current = { key, url: await api.previewVoice(voice.id, text.trim() || "سلام", styleId) }; }
      audio.current?.pause();
      audio.current = new Audio(cache.current.url);
      audio.current.onended = () => onPlaying(null);
      onPlaying(voice.id); setState("idle");
      await audio.current.play();
    } catch { setState("error"); onPlaying(null); }
  };
  return <div role="radio" tabIndex={0} className="wz-voice" aria-checked={active} aria-pressed={active} onClick={onPick} onKeyDown={e => (e.key === "Enter" || e.key === " ") && onPick()}>
    <div className="wz-voice-top">
      <span className="wz-wave" data-on={playing || undefined}><i/><i/><i/><i/></span>
      <button type="button" className="wz-voice-play" data-state={playing ? "playing" : state} aria-label={playing ? "توقف" : `تست صدای ${voice.name}`} onClick={e => void test(e)}>
        {state === "loading" ? <span className="wz-spin"/> : <Icon name={playing ? "close" : "play"} size={13}/>}</button>
    </div>
    <b>{voice.name}</b><small>{state === "error" ? "تست صدا ناموفق بود؛ دوباره بزن" : voice.note}</small>
  </div>;
}

function Row({ label, value, onEdit }: { label: string; value: React.ReactNode; onEdit: () => void }) {
  return <div className="wz-row"><span>{label}</span><b>{value}</b><button type="button" className="link" onClick={onEdit}>تغییر</button></div>;
}

function FontCard({ font, text, active, onPick }: { font: ReturnType<typeof useProFonts>["fonts"][number]; text: string; active: boolean; onPick: () => void }) {
  const ref = React.useRef<HTMLButtonElement>(null);
  const [ready, setReady] = React.useState(false);
  React.useEffect(() => {
    const node = ref.current; if (!node) return;
    const io = new IntersectionObserver(entries => { if (entries[0]?.isIntersecting) { void loadFontFaces(font).then(() => setReady(true)); io.disconnect(); } });
    io.observe(node); return () => io.disconnect();
  }, [font]);
  const family = `lib-${font.faces?.[0]?.css_family ?? font.id}`;
  return <button ref={ref} type="button" className="wz-card wz-font" aria-pressed={active} onClick={onPick}>
    <b className="wz-font-sample" style={ready ? { fontFamily: family } : { opacity: .35 }}>{text}</b><small>{font.label}</small></button>;
}
