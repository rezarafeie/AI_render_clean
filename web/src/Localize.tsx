import React from "react";
import { useSearchParams } from "react-router-dom";
import { api, LibraryAsset, LocalizeBoxColour, LocalizeLine, LocalizeProject, LocalizeSummary } from "./api";
import { AuthenticatedMedia } from "./AuthenticatedMedia";
import { LoadingState, friendlyError, notify } from "./ui";

const BUSY = new Set(["queued", "analyzing", "rendering"]);
const STATUS_LABELS: Record<LocalizeProject["status"], string> = {
  queued: "در صف",
  analyzing: "در حال تحلیل",
  ready: "آماده ویرایش",
  rendering: "در حال رندر",
  paused: "متوقف موقت",
  canceled: "لغو شد",
  done: "رندر شد",
  error: "خطا",
};
const STAGE_LABELS: Record<string, string> = {
  transcribing: "ترنسکریپت صدای انگلیسی",
  translating: "ترجمه به فارسی",
  "finding captions": "پیدا کردن جای زیرنویس‌ها",
  "generating voice": "ساخت صدای فارسی",
  rendering: "رندر ویدیو",
};
const KIND_LABELS: Record<LocalizeLine["kind"], string> = {
  speech: "دوبله",
  lyrics: "صدای اصلی",
  cta: "CTA",
};

function useMusicTracks() {
  const [tracks, setTracks] = React.useState<LibraryAsset[]>([]);
  React.useEffect(() => {
    api.getLibrary().then(data => setTracks(data.assets.filter(a => a.category === "music"))).catch(() => setTracks([]));
  }, []);
  return tracks;
}

const BOX_COLOURS: { value: LocalizeBoxColour; label: string }[] = [
  { value: "black", label: "مشکی" },
  { value: "white", label: "سفید (متن مشکی)" },
  { value: "red", label: "قرمز" },
  { value: "blue", label: "آبی" },
  { value: "green", label: "سبز" },
];

function BoxColourSelect({ value, onChange, auto, disabled }: {
  value?: LocalizeBoxColour | null; onChange: (v: LocalizeBoxColour | null) => void; auto: string; disabled?: boolean;
}) {
  return (
    <select value={value || ""} disabled={disabled} onChange={e => onChange((e.target.value || null) as LocalizeBoxColour | null)}>
      <option value="">{auto}</option>
      {BOX_COLOURS.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
    </select>
  );
}

function MusicSelect({ value, onChange, disabled }: { value: string | null; onChange: (v: string | null) => void; disabled?: boolean }) {
  const tracks = useMusicTracks();
  return (
    <select value={value || ""} onChange={e => onChange(e.target.value || null)} disabled={disabled}>
      <option value="">بدون موزیک</option>
      {tracks.map(t => <option key={t.path} value={t.path}>{t.filename}</option>)}
    </select>
  );
}

function NewProject({ onCreated }: { onCreated: (p: LocalizeProject) => void }) {
  const [file, setFile] = React.useState<File | null>(null);
  const [cta, setCta] = React.useState("31");
  const [music, setMusic] = React.useState<string | null>("assets/music/motivational_piano_beat.mp3");
  const [progress, setProgress] = React.useState<number | null>(null);
  const [error, setError] = React.useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) { setError("یک ویدیو انتخاب کنید."); return; }
    setError("");
    setProgress(0);
    try {
      onCreated(await api.createLocalize(file, cta, music, setProgress));
      setFile(null);
    } catch (err) {
      setError(friendlyError(err, "upload the video"));
    } finally { setProgress(null); }
  }

  return (
    <form className="card" onSubmit={submit} dir="rtl">
      <div className="section-header"><h2>ویدیوی جدید دراپشیپینگ</h2></div>
      <p className="muted">
        ویدیوی انگلیسی را آپلود کنید. صدا به فارسی دوبله می‌شود، زیرنویس و تیتر فارسی روی متن انگلیسی قرار می‌گیرد و آخر ویدیو CTA کامنت اضافه می‌شود.
      </p>
      <div className="row">
        <label>ویدیو <input type="file" accept="video/*" onChange={e => setFile(e.target.files?.[0] || null)} /></label>
      </div>
      <div className="row">
        <label>عدد کامنت <input value={cta} onChange={e => setCta(e.target.value)} style={{ width: 90 }} /></label>
        <label>موزیک زیر صدا <MusicSelect value={music} onChange={setMusic} /></label>
      </div>
      {error && <div className="errors">{error}</div>}
      <div className="action-bar">
        <button className="btn-primary" type="submit" disabled={progress !== null}>
          {progress !== null ? `در حال آپلود… ${progress}%` : "آپلود و تحلیل"}
        </button>
      </div>
    </form>
  );
}

function ProjectEditor({ id, onChanged }: { id: string; onChanged: () => void }) {
  const [project, setProject] = React.useState<LocalizeProject | null>(null);
  const [draft, setDraft] = React.useState<LocalizeProject | null>(null);
  const [voices, setVoices] = React.useState<Awaited<ReturnType<typeof api.localizeVoices>> | null>(null);
  React.useEffect(() => { api.localizeVoices().then(setVoices).catch(() => setVoices(null)); }, []);
  const [error, setError] = React.useState("");
  const [saving, setSaving] = React.useState(false);

  const load = React.useCallback(async () => {
    try {
      const p = await api.getLocalize(id);
      setProject(p);
      // Fields are read-only while busy; once idle, keep the user's unsaved edits.
      setDraft(d => (!d || BUSY.has(p.status) || d.status !== p.status ? p : d));
    } catch (err) { setError(friendlyError(err, "load the project")); }
  }, [id]);

  React.useEffect(() => { setProject(null); setDraft(null); load(); }, [load]);
  React.useEffect(() => {
    if (!project || !BUSY.has(project.status)) return;
    const timer = window.setInterval(load, 2000);
    return () => window.clearInterval(timer);
  }, [project?.status, load]);
  React.useEffect(() => { if (project?.status === "done" || project?.status === "ready") onChanged(); }, [project?.status]);

  if (!project || !draft) return <LoadingState label="Loading project" />;
  const busy = BUSY.has(project.status);

  function setLine(i: number, changes: Partial<LocalizeLine>) {
    setDraft(d => d && { ...d, lines: d.lines.map(l => (l.i === i ? { ...l, ...changes } : l)) });
  }

  async function save(): Promise<LocalizeProject | null> {
    if (!draft) return null;
    setSaving(true);
    setError("");
    try {
      const saved = await api.editLocalize(id, {
        title: draft.title, title_emojis: draft.title_emojis, cta_number: draft.cta_number, music: draft.music,
        voice_provider: draft.voice_provider, voice_id: draft.voice_id ?? "", voice_style: draft.voice_style ?? "",
        caption_box: draft.caption_box ?? null, title_box: draft.title_box ?? null,
        end_card: draft.end_card ?? true, end_card_seconds: draft.end_card_seconds ?? 3.5,
        lines: draft.lines.map(l => ({ i: l.i, fa: l.fa, kind: l.kind })),
      });
      setProject(saved); setDraft(saved);
      return saved;
    } catch (err) { setError(friendlyError(err, "save the changes")); return null; }
    finally { setSaving(false); }
  }

  async function render() {
    if (!(await save())) return;
    try { setProject(await api.renderLocalize(id)); notify("رندر شروع شد"); }
    catch (err) { setError(friendlyError(err, "start the render")); }
  }

  async function reanalyze() {
    try { setProject(await api.analyzeLocalize(id)); }
    catch (err) { setError(friendlyError(err, "analyze the video")); }
  }

  async function control(action: "pause" | "resume" | "cancel") {
    try {
      const next = action === "pause" ? await api.pauseLocalize(id)
        : action === "resume" ? await api.resumeLocalize(id)
          : await api.cancelLocalize(id);
      setProject(next); setDraft(next); onChanged();
    } catch (err) { setError(friendlyError(err, `${action} the project`)); }
  }

  return (
    <div className="card" dir="rtl">
      <div className="section-header">
        <h2>{project.name}</h2>
        <span className="tag">{STATUS_LABELS[project.status]}{(busy || project.status === "paused") && project.stage ? ` — ${STAGE_LABELS[project.stage] || project.stage}` : ""}{["analyzing", "rendering", "paused"].includes(project.status) && project.progress ? ` ${project.progress}%` : ""}</span>
      </div>
      {(busy || project.status === "paused") && <div className="action-bar">
        {project.status === "paused"
          ? <button className="btn-secondary" onClick={() => control("resume")}>ادامه</button>
          : <button className="btn-secondary" onClick={() => control("pause")}>توقف موقت</button>}
        <button className="btn-danger" onClick={() => control("cancel")}>لغو پردازش</button>
      </div>}
      {project.status === "error" && <div className="errors">{project.message}</div>}
      {error && <div className="errors">{error}</div>}

      {project.output && project.status === "done" && (
        <div className="row" style={{ alignItems: "flex-start" }}>
          <AuthenticatedMedia as="video" src={api.localizeOutputUrl(id)} controls style={{ maxHeight: 520, borderRadius: 8 }} />
          <button className="btn-secondary" onClick={() => api.downloadAuthenticated(api.localizeOutputUrl(id), `${project.name.replace(/\.[^.]+$/, "")}_fa.mp4`)}>
            دانلود ویدیو
          </button>
        </div>
      )}

      {draft.lines.length > 0 && (
        <>
          <div className="row">
            <label style={{ flex: 1 }}>تیتر بالای ویدیو
              <input value={draft.title} disabled={busy} onChange={e => setDraft({ ...draft, title: e.target.value })} style={{ width: "100%" }} />
            </label>
            <label>ایموجی <input value={draft.title_emojis} disabled={busy} onChange={e => setDraft({ ...draft, title_emojis: e.target.value })} style={{ width: 90 }} /></label>
          </div>
          <div className="row">
            <label>عدد کامنت <input value={draft.cta_number} disabled={busy} onChange={e => setDraft({ ...draft, cta_number: e.target.value })} style={{ width: 90 }} /></label>
            <label>موزیک زیر صدا <MusicSelect value={draft.music} disabled={busy} onChange={music => setDraft({ ...draft, music })} /></label>
            <label>صدای فارسی
              <select value={draft.voice_provider} disabled={busy} onChange={e => setDraft({ ...draft, voice_provider: e.target.value as LocalizeProject["voice_provider"] })}>
                <option value="elevenlabs">ElevenLabs</option>
              </select>
            </label>
            <label>گوینده
              <select value={draft.voice_id ?? ""} disabled={busy} onChange={e => setDraft({ ...draft, voice_id: e.target.value })}>
                {(voices?.voices ?? [{ id: "", name: "پیش‌فرض استودیو", note: "" }]).map(v => <option key={v.id} value={v.id}>{v.name}{v.note && v.id ? ` · ${v.note}` : ""}</option>)}
              </select>
            </label>
            <label>حالت صدا
              <select value={draft.voice_style ?? ""} disabled={busy} onChange={e => setDraft({ ...draft, voice_style: e.target.value })}>
                {(voices?.styles ?? [{ id: "", label: "طبیعی" }]).map(v => <option key={v.id} value={v.id}>{v.label}</option>)}
              </select>
            </label>
            <label>رنگ کادر متن‌ها
              <BoxColourSelect value={draft.caption_box} auto="هر رندر یه رنگ" disabled={busy} onChange={caption_box => setDraft({ ...draft, caption_box })} />
            </label>
            <label>رنگ کادر تیتر
              <BoxColourSelect value={draft.title_box} auto="مثل متن‌ها" disabled={busy} onChange={title_box => setDraft({ ...draft, title_box })} />
            </label>
            <label>
              <input type="checkbox" checked={draft.end_card ?? true} disabled={busy} onChange={e => setDraft({ ...draft, end_card: e.target.checked })} />
              صفحه‌ی پایانی CTA
            </label>
            <label>مدت صفحه‌ی پایانی (ثانیه)
              <input type="number" min={1} max={10} step={0.5} value={draft.end_card_seconds ?? 3.5} disabled={busy || draft.end_card === false}
                onChange={e => setDraft({ ...draft, end_card_seconds: Number(e.target.value) })} style={{ width: 70 }} />
            </label>
          </div>
          <table className="localize-lines" style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr><th>زمان</th><th>انگلیسی</th><th>فارسی</th><th>نوع</th></tr></thead>
            <tbody>
              {draft.lines.map(line => (
                <tr key={line.i} style={{ borderTop: "1px solid var(--border, #333)" }}>
                  <td className="muted" style={{ whiteSpace: "nowrap" }}>{line.start.toFixed(1)}–{line.end.toFixed(1)}</td>
                  <td dir="ltr" className="muted" style={{ fontSize: 13 }}>{line.en}</td>
                  <td style={{ width: "45%" }}>
                    {line.kind === "speech"
                      ? <textarea value={line.fa} disabled={busy} rows={2} style={{ width: "100%" }} onChange={e => setLine(line.i, { fa: e.target.value })} />
                      : <span className="muted">{line.kind === "cta" ? line.fa : "—"}</span>}
                  </td>
                  <td>
                    <select value={line.kind} disabled={busy} onChange={e => setLine(line.i, { kind: e.target.value as LocalizeLine["kind"] })}>
                      {(Object.keys(KIND_LABELS) as LocalizeLine["kind"][]).map(k => <option key={k} value={k}>{KIND_LABELS[k]}</option>)}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted">هزینه تقریبی تا الان: ${project.cost_usd.toFixed(3)} (بدون هزینه صدای ElevenLabs)</p>
        </>
      )}
      <div className="action-bar">
        <button className="btn-secondary" disabled={busy} onClick={reanalyze}>تحلیل دوباره</button>
        {draft.lines.length > 0 && <button className="btn-secondary" disabled={busy || saving} onClick={save}>ذخیره</button>}
        {draft.lines.length > 0 && <button className="btn-primary" disabled={busy || saving} onClick={render}>{project.output ? "رندر دوباره" : "رندر"}</button>}
      </div>
    </div>
  );
}

export default function Localize() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [projects, setProjects] = React.useState<LocalizeSummary[] | null>(null);
  const [selected, setSelected] = React.useState<string | null>(() => searchParams.get("project"));
  const [error, setError] = React.useState("");

  const refresh = React.useCallback(() => {
    api.listLocalize().then(setProjects).catch(err => setError(friendlyError(err, "load the projects")));
  }, []);
  React.useEffect(refresh, [refresh]);
  React.useEffect(() => { setSelected(searchParams.get("project")); }, [searchParams]);

  const selectProject = React.useCallback((id: string | null) => {
    setSelected(id);
    if (id) setSearchParams({ project: id });
    else setSearchParams({});
  }, [setSearchParams]);

  return (
    <div className="page">
      <h1>Dropshipping / دوبله فارسی</h1>
      {error && <div className="errors">{error}</div>}
      <NewProject onCreated={p => { selectProject(p.id); refresh(); }} />
      {selected && <ProjectEditor key={selected} id={selected} onChanged={refresh} />}
      <div className="card" dir="rtl">
        <div className="section-header"><h2>پروژه‌ها</h2></div>
        {projects === null ? <LoadingState label="Loading projects" /> : projects.length === 0 ? (
          <p className="muted">هنوز ویدیویی آپلود نشده.</p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0 }}>
            {projects.map(p => (
              <li key={p.id} className="row" style={{ justifyContent: "space-between" }}>
                <button className="secondary" onClick={() => selectProject(p.id)}>{p.title || p.name}</button>
                <span className="muted">{STATUS_LABELS[p.status]}</span>
                <button className="btn-sm btn-danger" onClick={async () => {
                  if (!window.confirm("این پروژه حذف شود؟")) return;
                  try { await api.deleteLocalize(p.id); if (selected === p.id) selectProject(null); refresh(); }
                  catch (err) { setError(friendlyError(err, "delete the project")); }
                }}>حذف</button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
