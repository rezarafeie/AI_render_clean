import React from "react";
import {Link} from "react-router-dom";
import {api, type DiscoveryAnalysis, type DiscoveryCandidate, type StudioEvent} from "../api";
import {AuthenticatedMedia} from "../AuthenticatedMedia";
import {friendlyError} from "../ui";
import {parseRange} from "../studio/discoveryModel";

export function PanelDiscovery({id, events}: {id: string; events: StudioEvent[]}) {
  const [analysis, setAnalysis] = React.useState<DiscoveryAnalysis | null>(null);
  const [playing, setPlaying] = React.useState("");
  const [editing, setEditing] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [busy, setBusy] = React.useState("");
  const [error, setError] = React.useState("");
  const [limit, setLimit] = React.useState(12);
  const [opened, setOpened] = React.useState<Record<string, string>>({});
  const pending = React.useRef(false);
  const recent = [...events].reverse().find(e => e.data?.analysis_id === id)?.seq;
  const load = React.useCallback(async () => {
    const value = await api.discoveryView(id);
    setAnalysis(value);
  }, [id]);
  React.useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const value = await api.discoveryView(id);
        if (!live) return;
        setAnalysis(value);
        if (value.running || value.candidates.some(item => !item.hidden && item.preview_ready === false)) {
          timer = setTimeout(() => {
            if (document.hidden) timer = setTimeout(poll, 12000);
            else void poll();
          }, 4500);
        }
      } catch (e) { if (live) setError(friendlyError(e, "open video discovery")); }
    }
    void poll();
    return () => { live = false; clearTimeout(timer); };
  }, [id, recent]);

  async function run(label: string, fn: () => Promise<unknown>) {
    if (pending.current) return;
    pending.current = true;
    setBusy(label);
    setError("");
    try { await fn(); await load(); }
    catch (e) { setError(friendlyError(e, label)); }
    finally { pending.current = false; setBusy(""); }
  }

  const canResume = analysis && !analysis.running && (analysis.interrupted || ["failed", "stopped"].includes(analysis.stage));
  const candidates = analysis?.candidates.filter(item => !item.hidden &&
    `${item.title} ${item.summary} ${item.hook}`.toLowerCase().includes(search.trim().toLowerCase())) ?? [];
  return <section className="mp-inspector" aria-label="کشف کلیپ از ویدیوی بلند">
    <div className="mp-section-head">
      <div><h2>کشف کلیپ از ویدیوی بلند</h2>{analysis && <p dir="auto">{analysis.filename}</p>}</div>
      <div className="mp-actions">
        {analysis?.running && <button className="btn btn-secondary btn-sm" disabled={Boolean(busy)}
          onClick={() => void run("توقف تحلیل", () => api.discoveryStop(id))}>توقف تحلیل</button>}
        {canResume && <button className="btn btn-secondary btn-sm" disabled={Boolean(busy)}
          onClick={() => void run("ادامهٔ تحلیل", () => api.discoveryResume(id))}>ادامهٔ تحلیل</button>}
      </div>
    </div>
    {(error || analysis?.error) && <p className="notice" role="alert" data-tone="error">{error || analysis?.error}</p>}
    {!analysis ? <p role="status">در حال خواندن وضعیت تحلیل…</p> : <>
      {analysis.running && <div className="mp-progress">
        <progress value={analysis.progress.percent} max={100} aria-label="پیشرفت تحلیل"/>
        <p role="status">{analysis.message || "در حال بررسی ویدیو…"}
          {analysis.progress.eta_s != null && ` · حدود ${Math.max(1, Math.ceil(analysis.progress.eta_s / 60))} دقیقه`}</p>
      </div>}
      {analysis.candidates.length ? <label>جستجوی کلیپ<input className="input" type="search" value={search}
        onChange={e => {setSearch(e.target.value); setLimit(12);}}/></label> : !analysis.running && <p>کلیپی در این تحلیل آماده نشده است.</p>}
      <div className="mp-gallery">
        {candidates.slice(0, limit).map(candidate => {
          const child = opened[candidate.id] || candidate.child_conversation_id;
          return <article className="mp-asset" key={candidate.id}>
            {playing === candidate.id && candidate.preview_ready !== false
              ? <AuthenticatedMedia as="video" src={api.discoveryPreviewUrl(id, candidate.id, candidate.revisions.length)}
                  controls playsInline preload="metadata"/>
              : candidate.preview_ready !== false && <AuthenticatedMedia as="img"
                  src={api.discoveryThumbUrl(id, candidate.id)} alt="" loading="lazy"/>}
            <div><b dir="auto">{candidate.title}</b><small>{candidate.estimated_duration.toFixed(1)} ثانیه</small></div>
            {candidate.hook && <p dir="auto">{candidate.hook}</p>}
            {candidate.summary && <details><summary>خلاصهٔ بخش</summary><p dir="auto">{candidate.summary}</p></details>}
            <div className="mp-actions">
              {candidate.preview_ready !== false && <button className="btn btn-secondary btn-sm" onClick={() => setPlaying(old => old === candidate.id ? "" : candidate.id)}>
                {playing === candidate.id ? "بستن" : "پیش‌نمایش"}</button>}
              <button className="btn btn-secondary btn-sm" aria-expanded={editing === candidate.id}
                onClick={() => setEditing(old => old === candidate.id ? "" : candidate.id)}>تنظیم کلیپ</button>
              {child && !candidate.child_stale ? <Link className="btn btn-primary btn-sm" to={`/panel/${child}`}>باز کردن در ادیتور</Link>
                : <button className="btn btn-primary btn-sm" disabled={Boolean(busy)} onClick={() => void run("شروع تدوین کلیپ", async () => {
                  const result = await api.startCandidate(id, candidate.id);
                  setOpened(old => ({...old, [candidate.id]: result.conversation_id}));
                })}>{candidate.child_stale ? "همگام‌سازی تدوین" : "شروع تدوین"}</button>}
            </div>
            {editing === candidate.id && <CandidateEdit candidate={candidate} duration={analysis.duration} busy={Boolean(busy)}
              onSave={changes => run("ذخیرهٔ کلیپ", async () => {
                await api.editCandidate(id, candidate.id, changes);
                setPlaying("");
                setEditing("");
              })}/>}
          </article>;
        })}
      </div>
      {candidates.length > limit && <button className="btn btn-secondary" onClick={() => setLimit(old => old + 12)}>کلیپ‌های بیشتر</button>}
    </>}
  </section>;
}


function CandidateEdit({candidate, duration, busy, onSave}: {
  candidate: DiscoveryCandidate; duration: number; busy: boolean;
  onSave: (changes: Parameters<typeof api.editCandidate>[2]) => Promise<void>;
}) {
  const [title, setTitle] = React.useState(candidate.title);
  const [hook, setHook] = React.useState(candidate.hook);
  const [start, setStart] = React.useState(String(candidate.ranges[0]?.[0] ?? 0));
  const [end, setEnd] = React.useState(String(candidate.ranges[0]?.[1] ?? 0));
  const single = candidate.ranges.length === 1;
  const bounds = single ? parseRange(start, end, duration) : {};
  return <fieldset className="mp-reset" disabled={busy}>
    <label>عنوان کلیپ<input className="input" value={title} maxLength={300} onChange={e => setTitle(e.target.value)}/></label>
    <label>هوک<input className="input" value={hook} maxLength={500} onChange={e => setHook(e.target.value)}/></label>
    {single && <div className="mp-form-grid">
      <label>شروع در فایل اصلی<input className="input" value={start} dir="ltr" onChange={e => setStart(e.target.value)}/></label>
      <label>پایان در فایل اصلی<input className="input" value={end} dir="ltr" onChange={e => setEnd(e.target.value)}/></label>
    </div>}
    {bounds.error && <p role="alert">{bounds.error}</p>}
    <button className="btn btn-secondary btn-sm" disabled={!title.trim() || Boolean(bounds.error)} onClick={() =>
      void onSave({title: title.trim(), hook: hook.trim(), ranges: bounds.range ? [bounds.range] : undefined})}>
      ذخیرهٔ کلیپ
    </button>
  </fieldset>;
}
