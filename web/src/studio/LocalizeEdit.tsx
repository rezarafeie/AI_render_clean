import React from "react";
import { api, LibraryAsset, LocalizeBoxColour, LocalizeLine, LocalizeProject } from "../api";
import { friendlyError, notify } from "../ui";
import { EditCard, EditGrid, EditSwitch } from "./EditCard";

const BUSY = new Set(["queued", "analyzing", "rendering"]);
const STATUS: Record<LocalizeProject["status"], [string, "success" | "error" | "warning" | "working" | undefined]> = {
  queued: ["در صف", "working"], analyzing: ["در حال تحلیل", "working"], ready: ["آماده ویرایش", "warning"], rendering: ["در حال رندر", "working"],
  paused: ["متوقف موقت", "warning"], canceled: ["لغو شد", undefined], done: ["رندر شد", "success"], error: ["خطا", "error"],
};
const STAGE: Record<string, string> = {
  transcribing: "ترنسکریپت صدای انگلیسی", translating: "ترجمه به فارسی", "finding captions": "پیدا کردن جای زیرنویس‌ها",
  "generating voice": "ساخت صدای فارسی", rendering: "رندر ویدیو",
};
const KIND: Record<LocalizeLine["kind"], string> = { speech: "دوبله", lyrics: "صدای اصلی", cta: "CTA" };
const BOX: [LocalizeBoxColour, string][] = [["black", "مشکی"], ["white", "سفید (متن مشکی)"], ["red", "قرمز"], ["blue", "آبی"], ["green", "سبز"]];

function useMusicTracks() {
  const [tracks, setTracks] = React.useState<LibraryAsset[]>([]);
  React.useEffect(() => { api.getLibrary().then(data => setTracks(data.assets.filter(a => a.category === "music"))).catch(() => setTracks([])); }, []);
  return tracks;
}

function useNarrators() {
  const [voices, setVoices] = React.useState<Awaited<ReturnType<typeof api.localizeVoices>> | null>(null);
  React.useEffect(() => { api.localizeVoices().then(setVoices).catch(() => setVoices(null)); }, []);
  return voices;
}

/** Localize settings and Persian lines for the studio's Edit tab (the standalone page keeps its own editor). */
export function LocalizeEdit({ id, onChanged }: { id: string; onChanged: () => void }) {
  const [project, setProject] = React.useState<LocalizeProject | null>(null);
  const [draft, setDraft] = React.useState<LocalizeProject | null>(null);
  const [error, setError] = React.useState("");
  const [busyAction, setBusyAction] = React.useState("");
  const tracks = useMusicTracks();
  const voices = useNarrators();

  const load = React.useCallback(async () => {
    try {
      const value = await api.getLocalize(id);
      setProject(value);
      setDraft(current => (!current || BUSY.has(value.status) || current.status !== value.status ? value : current));
    } catch (e) { setError(friendlyError(e, "load the project")); }
  }, [id]);
  React.useEffect(() => { setProject(null); setDraft(null); void load(); }, [load]);
  React.useEffect(() => {
    if (!project || !BUSY.has(project.status)) return;
    const timer = window.setInterval(() => void load(), 2000);
    return () => window.clearInterval(timer);
  }, [project?.status, load]);
  React.useEffect(() => { if (project?.status === "done" || project?.status === "ready") onChanged(); }, [project?.status]);

  if (!project || !draft) return error ? <div className="notice" data-tone="error" role="alert">{error}</div> : <div className="tl-loading" role="status"><span className="spinner"/>در حال بارگذاری…</div>;
  const busy = BUSY.has(project.status);
  const locked = busy || Boolean(busyAction);
  const [statusLabel, tone] = STATUS[project.status];
  const set = (changes: Partial<LocalizeProject>) => setDraft(current => current && { ...current, ...changes });
  const setLine = (i: number, changes: Partial<LocalizeLine>) => setDraft(current => current && { ...current, lines: current.lines.map(line => line.i === i ? { ...line, ...changes } : line) });
  const dirty = JSON.stringify(draft) !== JSON.stringify(project);

  const save = async (): Promise<boolean> => {
    setBusyAction("save"); setError("");
    try {
      const saved = await api.editLocalize(id, {
        title: draft.title, title_emojis: draft.title_emojis, cta_number: draft.cta_number, music: draft.music, voice_provider: draft.voice_provider, voice_id: draft.voice_id ?? "", voice_style: draft.voice_style ?? "",
        caption_box: draft.caption_box ?? null, title_box: draft.title_box ?? null, end_card: draft.end_card ?? true, end_card_seconds: draft.end_card_seconds ?? 3.5,
        lines: draft.lines.map(line => ({ i: line.i, fa: line.fa, kind: line.kind })),
      });
      setProject(saved); setDraft(saved);
      return true;
    } catch (e) { setError(friendlyError(e, "save the changes")); return false; }
    finally { setBusyAction(""); }
  };
  const render = async () => {
    if (!(await save())) return;
    setBusyAction("render");
    try { setProject(await api.renderLocalize(id)); notify("رندر شروع شد"); }
    catch (e) { setError(friendlyError(e, "start the render")); }
    finally { setBusyAction(""); }
  };
  const control = async (action: "pause" | "resume" | "cancel") => {
    try {
      const next = action === "pause" ? await api.pauseLocalize(id) : action === "resume" ? await api.resumeLocalize(id) : await api.cancelLocalize(id);
      setProject(next); setDraft(next); onChanged();
    } catch (e) { setError(friendlyError(e, `${action} the project`)); }
  };
  const reanalyze = async () => {
    if (!window.confirm("متن و ترجمه دوباره ساخته می‌شود و ویرایش‌های فعلی خط‌ها از بین می‌رود. ادامه می‌دهید؟")) return;
    try { setProject(await api.analyzeLocalize(id)); } catch (e) { setError(friendlyError(e, "analyze the video")); }
  };

  return <div className="loc-edit" dir="rtl">
    <div className="ec-status">
      <span className="badge" data-tone={tone}><i/>{statusLabel}{(busy || project.status === "paused") && project.stage ? ` · ${STAGE[project.stage] || project.stage}` : ""}</span>
      {busy || project.status === "paused" ? <span className="action-buttons">
        <button className="btn btn-sm btn-secondary" onClick={() => void control(project.status === "paused" ? "resume" : "pause")}>{project.status === "paused" ? "ادامه" : "توقف موقت"}</button>
        <button className="btn btn-sm btn-secondary" onClick={() => void control("cancel")}>لغو</button></span> : null}
    </div>
    {project.status === "error" ? <div className="notice" data-tone="error" role="alert">{project.message}</div> : null}
    {error ? <div className="notice" data-tone="error" role="alert">{error}</div> : null}

    {draft.lines.length ? <>
      <EditCard title="تیتر و برند" open summary={[draft.title, draft.title_emojis].filter(Boolean).join(" ")}>
        <div className="field"><label htmlFor="loc-title">تیتر بالای ویدیو</label>
          <input id="loc-title" className="input bidi" dir="auto" disabled={locked} value={draft.title} onChange={event => set({ title: event.target.value })}/></div>
        <EditGrid>
          <div className="field"><label htmlFor="loc-emoji">ایموجی تیتر</label>
            <input id="loc-emoji" className="input" disabled={locked} value={draft.title_emojis} onChange={event => set({ title_emojis: event.target.value })}/></div>
          <div className="field"><label htmlFor="loc-cta">عدد کامنت</label>
            <input id="loc-cta" className="input" inputMode="numeric" disabled={locked} value={draft.cta_number} onChange={event => set({ cta_number: event.target.value })}/></div>
        </EditGrid>
      </EditCard>

      <EditCard title="صدا و موسیقی" summary={`${draft.music ? draft.music.split("/").pop() : "بدون موسیقی"} · ${voices?.voices.find(voice => voice.id === (draft.voice_id ?? ""))?.name ?? "ElevenLabs"}`}>
        <div className="field"><label htmlFor="loc-music">موسیقی زیر صدا</label>
          <select id="loc-music" className="input" disabled={locked} value={draft.music || ""} onChange={event => set({ music: event.target.value || null })}>
            <option value="">بدون موسیقی</option>{tracks.map(track => <option key={track.path} value={track.path}>{track.filename}</option>)}</select></div>
        <div className="field"><label htmlFor="loc-voice">صدای فارسی</label>
          <select id="loc-voice" className="input" disabled={locked} value={draft.voice_provider} onChange={event => set({ voice_provider: event.target.value as LocalizeProject["voice_provider"] })}>
            <option value="elevenlabs">ElevenLabs</option></select></div>
        <EditGrid>
          <div className="field"><label htmlFor="loc-narrator">گوینده</label>
            <select id="loc-narrator" className="input" disabled={locked} value={draft.voice_id ?? ""} onChange={event => set({ voice_id: event.target.value })}>
              {(voices?.voices ?? [{ id: "", name: "پیش‌فرض استودیو", note: "" }]).map(voice => <option key={voice.id} value={voice.id}>{voice.name}{voice.note && voice.id ? ` · ${voice.note}` : ""}</option>)}</select></div>
          <div className="field"><label htmlFor="loc-voice-style">حالت صدا</label>
            <select id="loc-voice-style" className="input" disabled={locked} value={draft.voice_style ?? ""} onChange={event => set({ voice_style: event.target.value })}>
              {(voices?.styles ?? [{ id: "", label: "طبیعی" }]).map(style => <option key={style.id} value={style.id}>{style.label}</option>)}</select></div>
        </EditGrid>
      </EditCard>

      <EditCard title="ظاهر کادرها و صفحهٔ پایانی" summary={draft.end_card === false ? "بدون صفحهٔ پایانی" : `صفحهٔ پایانی ${draft.end_card_seconds ?? 3.5} ثانیه`}>
        <EditGrid>
          <div className="field"><label htmlFor="loc-capbox">رنگ کادر متن‌ها</label>
            <select id="loc-capbox" className="input" disabled={locked} value={draft.caption_box || ""} onChange={event => set({ caption_box: (event.target.value || null) as LocalizeBoxColour | null })}>
              <option value="">هر رندر یک رنگ</option>{BOX.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
          <div className="field"><label htmlFor="loc-titlebox">رنگ کادر تیتر</label>
            <select id="loc-titlebox" className="input" disabled={locked} value={draft.title_box || ""} onChange={event => set({ title_box: (event.target.value || null) as LocalizeBoxColour | null })}>
              <option value="">مثل متن‌ها</option>{BOX.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
        </EditGrid>
        <EditSwitch label="صفحهٔ پایانی CTA" hint="کارت دعوت به کامنت در انتهای ویدیو" disabled={locked} checked={draft.end_card ?? true} onChange={checked => set({ end_card: checked })}/>
        {draft.end_card === false ? null : <div className="field"><label htmlFor="loc-endsec">مدت صفحهٔ پایانی: {draft.end_card_seconds ?? 3.5} ثانیه</label>
          <input id="loc-endsec" type="range" min={1} max={10} step={0.5} disabled={locked} value={draft.end_card_seconds ?? 3.5} onChange={event => set({ end_card_seconds: Number(event.target.value) })}/></div>}
      </EditCard>

      <EditCard title="متن فارسی" open summary={`${draft.lines.length} خط`} hint="متن انگلیسی مرجع است؛ ترجمهٔ فارسی را اینجا اصلاح کنید و نوع هر خط را مشخص کنید.">
        {draft.lines.map(line => <div className="ec-line" key={line.i}>
          <div className="ec-line-head"><span dir="ltr">{line.start.toFixed(1)}–{line.end.toFixed(1)}s</span>
            <select className="input" aria-label="نوع خط" disabled={locked} value={line.kind} onChange={event => setLine(line.i, { kind: event.target.value as LocalizeLine["kind"] })} style={{ width: "auto", minHeight: 32 }}>
              {(Object.keys(KIND) as LocalizeLine["kind"][]).map(kind => <option key={kind} value={kind}>{KIND[kind]}</option>)}</select></div>
          <div className="ec-line-en" dir="ltr">{line.en}</div>
          {line.kind === "speech" ? <textarea className="input bidi" dir="auto" rows={2} aria-label="ترجمهٔ فارسی" disabled={locked} value={line.fa} onChange={event => setLine(line.i, { fa: event.target.value })}/>
            : <small className="field-hint">{line.kind === "cta" ? line.fa : "صدای اصلی ویدیو پخش می‌شود."}</small>}
        </div>)}
        <small className="field-hint">هزینهٔ تقریبی تا اینجا: ${project.cost_usd.toFixed(3)} (بدون هزینهٔ صدای ElevenLabs)</small>
      </EditCard>

      <div className="ec-actions">
        <button className="btn" disabled={locked || !dirty} onClick={() => void save()}>{busyAction === "save" ? "در حال ذخیره…" : "ذخیره"}</button>
        <button className="btn btn-secondary" disabled={locked} onClick={() => void render()}>{busyAction === "render" ? "در حال شروع…" : "ذخیره و رندر دوباره"}</button>
        <button className="btn btn-ghost" disabled={locked} onClick={() => void reanalyze()}>تحلیل دوباره</button>
        <small>رندر دوبارهٔ دوبله ممکن است هزینهٔ صدا داشته باشد.</small>
      </div>
    </> : <div className="ec-status"><small className="field-hint">متن ویدیو هنوز آماده نیست.</small>
      <button className="btn btn-sm btn-secondary" disabled={locked} onClick={() => void reanalyze()}>تحلیل ویدیو</button></div>}
  </div>;
}
