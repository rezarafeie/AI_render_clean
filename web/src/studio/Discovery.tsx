import React from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, DiscoveryAnalysis, DiscoveryCandidate, StudioEvent } from "../api";
import { AuthenticatedMedia } from "../AuthenticatedMedia";
import { Icon } from "../components/Icon";
import { Menu } from "../components/Menu";
import { friendlyError } from "../ui";
import { STAGE_LABEL, STATUS_LABEL, STATUS_TONE, SortKey, categoriesOf, clock, etaText, isActive, liveLines, parseRange, rangeText, visibleCandidates } from "./discoveryModel";

/** Refresh while something is running: not while the tab is hidden, and less and less often the longer nothing new comes (a preview that never becomes ready must not keep the server busy). */
function usePoll(active: boolean, refresh: () => unknown, base: number, reset: unknown) {
  React.useEffect(() => {
    if (!active) return;
    let delay = base, timer = 0, stopped = false;
    const tick = () => {
      if (stopped) return;
      if (!document.hidden) void refresh();
      delay = Math.min(delay * 1.4, 20000);
      timer = window.setTimeout(tick, delay);
    };
    const visible = () => { if (!document.hidden) { delay = base; window.clearTimeout(timer); tick(); } };
    timer = window.setTimeout(tick, delay);
    document.addEventListener("visibilitychange", visible);
    return () => { stopped = true; window.clearTimeout(timer); document.removeEventListener("visibilitychange", visible); };
  }, [active, refresh, base, reset]);
}

/** Whether this chat's long-video analysis is running right now (drives the composer's Stop button). */
export function useDiscoveryActive(analysisId: string | undefined, events: StudioEvent[]): boolean {
  const [active, setActive] = React.useState(false);
  const last = React.useMemo(() => { const mine = events.filter(e => analysisId && e.data?.analysis_id === analysisId); return mine.length ? mine[mine.length - 1].seq : 0; }, [events, analysisId]);
  const refresh = React.useCallback(() => { if (analysisId) api.discoveryView(analysisId).then(a => setActive(Boolean(a.running) && !a.interrupted)).catch(() => setActive(false)); else setActive(false); }, [analysisId]);
  React.useEffect(() => { refresh(); }, [refresh, last]);
  usePoll(active, refresh, 4000, last);
  return active;
}

/** The parent chat's workspace: live transcription, progress, and one card per independent piece of content found in the long video. */
export function DiscoveryPanel({ analysisId, events }: { analysisId: string; events: StudioEvent[] }) {
  const [analysis, setAnalysis] = React.useState<DiscoveryAnalysis | null>(null);
  const [error, setError] = React.useState("");
  const [category, setCategory] = React.useState<string | null>(null);
  const [sort, setSort] = React.useState<SortKey>("time");
  const [showHidden, setShowHidden] = React.useState(false);
  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  const [focus, setFocus] = React.useState("");
  const [busy, setBusy] = React.useState("");
  const mine = React.useMemo(() => events.filter(e => e.data?.analysis_id === analysisId), [events, analysisId]);
  const lastEvent = mine.length ? mine[mine.length - 1].seq : 0;

  const refresh = React.useCallback(() => api.discoveryView(analysisId).then(setAnalysis).catch(e => setError(friendlyError(e, "load the analysis"))), [analysisId]);
  React.useEffect(() => { void refresh(); }, [refresh, lastEvent]);
  const active = analysis ? (analysis.running || analysis.interrupted || analysis.candidates.some(c => isActive(c.status) || (!c.hidden && c.preview_ready === false))) : true;
  usePoll(active, refresh, 3000, lastEvent);

  if (!analysis) return <section className="dv" dir="rtl">{error ? <div className="notice" data-tone="error" role="alert">{error}</div> : <div className="tl-loading" role="status"><span className="spinner"/>در حال بارگذاری…</div>}</section>;

  const run = async (name: string, action: () => Promise<unknown>) => {
    setBusy(name); setError("");
    try { await action(); await refresh(); } catch (e) { setError(friendlyError(e, name)); } finally { setBusy(""); }
  };
  const lines = liveLines(analysis.transcript_tail, mine, analysisId);
  const transcribing = analysis.transcription_status === "running";
  const working = analysis.running && analysis.discovery_status !== "completed";
  const failed = analysis.stage === "failed" || Boolean(analysis.error);
  const cards = visibleCandidates(analysis.candidates, category, sort, showHidden);
  const categories = categoriesOf(analysis.candidates);
  const startMany = () => run("start editing", async () => { for (const id of selected) await api.startCandidate(analysisId, id); setSelected(new Set()); });

  return <section className="dv assistant-body" dir="rtl" aria-label="کشف محتوا از ویدیوی بلند">
    <header className="dv-head">
      <div><h3>کشف محتوا از ویدیوی بلند</h3><p className="bidi" dir="auto">{analysis.filename} · {clock(analysis.duration)}{analysis.language ? ` · زبان: ${analysis.language === "fa" ? "فارسی" : analysis.language === "en" ? "انگلیسی" : analysis.language}` : ""}</p></div>
      <span className="badge" data-tone={failed ? "error" : working ? "working" : analysis.discovery_status === "completed" ? "success" : "warning"}><i/>{failed ? "ناموفق" : STAGE_LABEL[analysis.interrupted ? "interrupted" : analysis.stage] || analysis.stage}</span>
    </header>

    {working || analysis.interrupted || failed || analysis.stage === "stopped" ? <div className="dv-progress">
      <div className="meter" role="progressbar" aria-valuenow={Math.round(analysis.progress.percent)} aria-valuemin={0} aria-valuemax={100} style={{ ["--value" as string]: `${analysis.progress.percent}%` }}><i/></div>
      <div className="dv-meta"><span>{analysis.message || STAGE_LABEL[analysis.stage]}</span>
        <span dir="ltr">{clock(analysis.progress.processed_s)} / {clock(analysis.progress.duration_s || analysis.duration)}{transcribing ? ` · ${etaText(analysis.progress.eta_s)}` : ""}</span></div>
      {analysis.estimate && analysis.progress.percent < 1 ? <small className="field-hint">زمان تقریبی روی این سرور: حدود {Math.max(1, Math.round(analysis.estimate.total_s / 60))} دقیقه (مدل {analysis.estimate.model}). می‌توانید همین‌جا نتیجه را زنده ببینید.</small> : null}
      <div className="dv-actions">
        {analysis.interrupted || analysis.stage === "stopped" || failed ? <button className="btn btn-sm" disabled={Boolean(busy)} onClick={() => void run("resume", () => api.discoveryResume(analysisId))}>ادامه از همان‌جا</button> : null}
        {working && !analysis.interrupted ? <button className="btn btn-sm btn-secondary" disabled={Boolean(busy)} onClick={() => void run("stop", () => api.discoveryStop(analysisId))}>توقف</button> : null}
      </div>
      {failed && analysis.error ? <div className="notice" data-tone="error" role="alert">{analysis.error}</div> : null}
    </div> : null}

    {lines.length && (transcribing || working || !analysis.candidates.length) ? <div className="dv-live" aria-live="polite">
      <b>{transcribing ? "متن زنده" : "آخرین بخش متن"}</b>
      <ol>{lines.map(line => <li key={line.id}><time dir="ltr">{clock(line.start)}</time><span className="bidi" dir="auto">{line.text}</span></li>)}</ol>
    </div> : null}

    {error ? <div className="notice" data-tone="error" role="alert">{error}</div> : null}

    {analysis.candidates.length ? <>
      <div className="dv-toolbar">
        <div className="chip-row" role="group" aria-label="دسته‌بندی">
          <button className="chip" aria-pressed={category === null} onClick={() => setCategory(null)}>همه ({analysis.candidates.filter(c => !c.hidden).length})</button>
          {categories.map(item => <button key={item.name} className="chip" aria-pressed={category === item.name} onClick={() => setCategory(item.name)}>{item.name} ({item.count})</button>)}
        </div>
        <div className="dv-tools">
          <div className="segmented" role="group" aria-label="مرتب‌سازی"><button aria-pressed={sort === "time"} onClick={() => setSort("time")}>به ترتیب زمان</button><button aria-pressed={sort === "score"} onClick={() => setSort("score")}>بهترین‌ها</button></div>
          {analysis.candidates.some(c => c.hidden) ? <label className="check"><input type="checkbox" checked={showHidden} onChange={e => setShowHidden(e.target.checked)}/> نمایش مخفی‌ها</label> : null}
        </div>
      </div>
      {selected.size ? <div className="dv-bulk"><span>{selected.size} کارت انتخاب شده</span><button className="btn btn-sm" disabled={Boolean(busy)} onClick={() => void startMany()}>شروع تدوین انتخاب‌شده‌ها</button><button className="btn btn-sm btn-ghost" onClick={() => setSelected(new Set())}>لغو انتخاب</button></div> : null}
      <ol className="dv-cards">{cards.map((candidate, position) => <li key={candidate.id}>
        <CandidateCard analysis={analysis} candidate={candidate} number={analysis.candidates.filter(c => !c.hidden).findIndex(c => c.id === candidate.id) + 1 || position + 1}
          selected={selected.has(candidate.id)} onSelect={on => setSelected(current => { const next = new Set(current); on ? next.add(candidate.id) : next.delete(candidate.id); return next; })} onChanged={refresh}/>
      </li>)}</ol>
    </> : analysis.discovery_status === "completed" ? <p className="field-hint">هیچ محتوای مستقلی با کیفیت کافی پیدا نشد.</p> : null}

    {analysis.discovery_status === "completed" ? <form className="dv-more" onSubmit={event => { event.preventDefault(); void run("more", () => api.discoveryMore(analysisId, focus).then(() => setFocus(""))); }}>
      <input className="input bidi" dir="auto" value={focus} maxLength={300} placeholder="دنبال نوع خاصی از محتوا بگردم؟ مثلاً: داستان‌ها و تجربه‌های شخصی" onChange={event => setFocus(event.target.value)} aria-label="درخواست محتوای بیشتر"/>
      <button className="btn btn-sm btn-secondary" disabled={Boolean(busy)}>درخواست محتوای بیشتر</button>
    </form> : null}
  </section>;
}

function CandidateCard({ analysis, candidate, number, selected, onSelect, onChanged }: { analysis: DiscoveryAnalysis; candidate: DiscoveryCandidate; number: number; selected: boolean; onSelect: (on: boolean) => void; onChanged: () => void }) {
  const navigate = useNavigate();
  const [playing, setPlaying] = React.useState(false);
  const [editing, setEditing] = React.useState(false);
  const [form, setForm] = React.useState({ title: candidate.title, hook: candidate.hook, start: clock(candidate.ranges[0][0]), end: clock(candidate.ranges[candidate.ranges.length - 1][1]) });
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const version = candidate.revisions.length;
  const act = async (work: () => Promise<unknown>, name: string) => { setBusy(true); setError(""); try { await work(); onChanged(); } catch (e) { setError(friendlyError(e, name)); } finally { setBusy(false); } };
  const save = () => {
    const changes: Parameters<typeof api.editCandidate>[2] = { title: form.title, hook: form.hook };
    if (candidate.ranges.length === 1) {
      const parsed = parseRange(form.start, form.end, analysis.duration);
      if (parsed.error) { setError(parsed.error); return; }
      if (parsed.range && (parsed.range[0] !== candidate.ranges[0][0] || parsed.range[1] !== candidate.ranges[0][1])) changes.ranges = [parsed.range];
    }
    void act(async () => { await api.editCandidate(analysis.id, candidate.id, changes); setEditing(false); setPlaying(false); }, "save the card");
  };
  const child = candidate.child_conversation_id;
  return <article className="dv-card" data-status={candidate.status} data-selected={selected || undefined}>
    <div className="dv-media">
      {playing ? <AuthenticatedMedia as="video" key={`p-${version}`} src={api.discoveryPreviewUrl(analysis.id, candidate.id, version)} controls autoPlay playsInline/>
        : <button type="button" className="dv-thumb" onClick={() => { if (candidate.preview_ready !== false) setPlaying(true); }} aria-label={`پیش‌نمایش ${candidate.title}`} aria-disabled={candidate.preview_ready === false || undefined}>
            <AuthenticatedMedia as="img" key={`t-${version}`} src={api.discoveryThumbUrl(analysis.id, candidate.id)} alt="" loading="lazy"/>
            {candidate.preview_ready === false ? <span className="dv-wait" role="status"><span className="spinner"/>در حال آماده‌سازی پیش‌نمایش…</span> : <span className="dv-play"><Icon name="play" size={20}/></span>}
            <span className="dv-dur" dir="ltr">{clock(candidate.estimated_duration)}</span>
          </button>}
      <label className="dv-pick"><input type="checkbox" checked={selected} disabled={Boolean(child) && !candidate.child_stale} onChange={event => onSelect(event.target.checked)} aria-label="انتخاب"/></label>
    </div>
    <div className="dv-body">
      <b className="dv-title bidi" dir="auto">{number}. {candidate.title}</b>
      <p className="dv-line">
        <span dir="ltr">{rangeText(candidate)}</span><span>{candidate.category}</span><span>{candidate.score}/10</span>
        {candidate.ranges.length > 1 ? <span>چندبخشی</span> : null}
        {candidate.status !== "discovered" ? <span className="badge" data-tone={STATUS_TONE[candidate.status]}><i/>{STATUS_LABEL[candidate.status]}</span> : null}
      </p>
      {candidate.hook ? <p className="dv-hook bidi" dir="auto">«{candidate.hook}»</p> : null}
      <details className="dv-why"><summary>جزئیات</summary>
        <p className="bidi" dir="auto">{candidate.summary}</p>
        {candidate.rationale ? <p className="bidi" dir="auto">{candidate.rationale}</p> : null}
        {candidate.problems?.length ? <small>{candidate.problems.join("؛ ")}</small> : null}</details>
      {editing ? <div className="dv-edit">
        <div className="field"><label>عنوان</label><input className="input bidi" dir="auto" value={form.title} onChange={e => setForm({ ...form, title: e.target.value })}/></div>
        <div className="field"><label>هوک</label><textarea className="input bidi" dir="auto" rows={2} value={form.hook} onChange={e => setForm({ ...form, hook: e.target.value })}/></div>
        {candidate.ranges.length === 1 ? <div className="ec-grid"><div className="field"><label>شروع</label><input className="input" dir="ltr" value={form.start} onChange={e => setForm({ ...form, start: e.target.value })}/></div>
          <div className="field"><label>پایان</label><input className="input" dir="ltr" value={form.end} onChange={e => setForm({ ...form, end: e.target.value })}/></div></div>
          : <small className="field-hint">این کارت از چند بازه ساخته شده؛ زمان‌ها را از روی همان بازه‌ها در تدوین تنظیم کنید.</small>}
        <div className="dv-actions"><button className="btn btn-sm" disabled={busy} onClick={save}>ذخیره</button><button className="btn btn-sm btn-ghost" onClick={() => { setEditing(false); setError(""); }}>انصراف</button></div>
      </div> : null}
      {error ? <div className="notice" data-tone="error" role="alert">{error}</div> : null}
      {candidate.child_stale ? <small className="field-hint">این کارت بعد از ساخت چت تدوین عوض شده؛ «شروع تدوین» یک چت تازه با نسخهٔ جدید می‌سازد.</small> : null}
      <div className="dv-actions">
        {child && !candidate.child_stale
          ? <Link className="btn btn-sm" to={`/studio/${child}`}>{candidate.status === "completed" ? "دیدن خروجی و چت" : candidate.status === "failed" ? "بازکردن چت و تلاش دوباره" : "ادامهٔ تدوین"}</Link>
          : <button className="btn btn-sm" disabled={busy} onClick={() => void act(() => api.startCandidate(analysis.id, candidate.id).then(result => { navigate(`/studio/${result.conversation_id}`); }), "start editing")}>{busy ? "در حال ساختن…" : "شروع تدوین"}</button>}
        <Menu label="گزینه‌های بیشتر" align="end" trigger={props => <button type="button" className="icon-btn" {...props} aria-label="گزینه‌های بیشتر"><Icon name="thinking" size={18}/></button>}>
          {close => <>
            <button type="button" role="menuitem" className="menu-item" disabled={candidate.preview_ready === false} onClick={() => { close(); setPlaying(value => !value); }}><Icon name="play" size={16}/><span>{playing ? "بستن پیش‌نمایش" : "پیش‌نمایش"}</span></button>
            <button type="button" role="menuitem" className="menu-item" onClick={() => { close(); setEditing(value => !value); }}><Icon name="edit" size={16}/><span>ویرایش</span></button>
            <button type="button" role="menuitem" className="menu-item" disabled={busy} onClick={() => { close(); void act(() => api.editCandidate(analysis.id, candidate.id, { hidden: !candidate.hidden }), "hide"); }}><Icon name="trash" size={16}/><span>{candidate.hidden ? "نمایش" : "حذف از فهرست"}</span></button>
          </>}
        </Menu>
      </div>
    </div>
  </article>;
}
