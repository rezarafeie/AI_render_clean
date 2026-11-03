import React from "react";
import { api, MotionGraphic, StudioEvent } from "../api";
import { AuthenticatedMedia } from "../AuthenticatedMedia";
import { friendlyError } from "../ui";
import { etaText, motionSteps } from "./motionModel";
import { Icon } from "../components/Icon";
import { formatDuration } from "../format";
import type { ActivityStep } from "./model";

const FORMAT_LABEL = { vertical: "عمودی ۹:۱۶", horizontal: "افقی ۱۶:۹", square: "مربعی ۱:۱" } as const;
const secondsText = (n: number) => `${new Intl.NumberFormat("fa-IR").format(Math.round(n * 10) / 10)} ثانیه`;

/** Whether this chat's motion graphic is being made right now (drives the composer's Stop button). */
export function useMotionActive(motionId: string | undefined, events: StudioEvent[]): boolean {
  const [active, setActive] = React.useState(false);
  const last = React.useMemo(() => { const mine = events.filter(e => motionId && e.data?.motion_id === motionId); return mine.length ? mine[mine.length - 1].seq : 0; }, [events, motionId]);
  const refresh = React.useCallback(() => { if (motionId) api.motionView(motionId).then(m => setActive(m.active)).catch(() => setActive(false)); else setActive(false); }, [motionId]);
  React.useEffect(() => { refresh(); }, [refresh, last]);
  React.useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(refresh, 2500);
    return () => window.clearInterval(timer);
  }, [active, refresh]);
  return active;
}

/** The scenes as a small album: one row of thumbnails (scrolls sideways), a click opens one larger with the arrow keys to move along. It stays
 * compact so the steps above it remain in view. */
function ShotStrip({ motionId, shots, stamp }: { motionId: string; shots: { n: number; headline: string; t: number }[]; stamp: number }) {
  const [open, setOpen] = React.useState<number | null>(null);
  React.useEffect(() => {
    if (open === null) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(null);
      else if (event.key === "ArrowLeft") setOpen(value => value === null ? value : Math.min(shots.length - 1, value + 1));
      else if (event.key === "ArrowRight") setOpen(value => value === null ? value : Math.max(0, value - 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, shots.length]);
  const current = open === null ? null : shots[open];
  return <>
    <ul className="mg-album" aria-label="صحنه‌ها">
      {shots.map((shot, index) => <li key={`${shot.n}-${stamp}`}>
        <button type="button" className="mg-thumb" onClick={() => setOpen(index)} aria-label={`صحنهٔ ${shot.n}: ${shot.headline}`} title={`${shot.n}. ${shot.headline}`}>
          <AuthenticatedMedia as="img" src={api.motionSnapshotUrl(motionId, shot.n)} alt="" loading="lazy" draggable={false}/>
          <span className="mg-thumb-n" aria-hidden="true">{shot.n}</span>
        </button>
      </li>)}
    </ul>
    {current ? <div className="overlay" role="dialog" aria-modal="true" aria-label={`صحنهٔ ${current.n}`} onMouseDown={event => { if (event.target === event.currentTarget) setOpen(null); }}>
      <figure className="mg-lightbox">
        <AuthenticatedMedia as="img" src={api.motionSnapshotUrl(motionId, current.n)} alt={`صحنهٔ ${current.n}: ${current.headline}`}/>
        <figcaption dir="auto">{current.n}. {current.headline}</figcaption>
        <button type="button" className="icon-btn mg-lightbox-close" onClick={() => setOpen(null)} aria-label="بستن"><Icon name="close" size={18}/></button>
      </figure>
    </div> : null}
  </>;
}

/** What each stage of the build uses, so the person sees which tool is working (the keys are the server's log keys). */
const STEP_TOOLS: [RegExp, string[]][] = [
  [/^image$/, ["مدل بینایی"]], [/^plan$/, ["مدل برنامه‌ریز"]], [/^voice$/, ["ElevenLabs"]], [/^verify$/, ["تشخیص گفتار"]], [/^music$/, ["کتابخانهٔ موسیقی", "ffmpeg"]],
  [/^scene\d+$/, ["طراح صحنه"]], [/^check$/, ["HyperFrames check"]], [/^snapshots$/, ["HyperFrames snapshot"]], [/^render$/, ["HyperFrames render"]],
];

/** A percentage that is seen to move: the server's whole-number progress plus a slow, capped creep between its updates (never past the next
 * whole number), shown with one decimal. It is an estimate of motion, not a measurement; the next server update replaces it. */
function useCreep(base: number | undefined, active: boolean, now: number): number | undefined {
  const seen = React.useRef<{ base: number; at: number } | null>(null);
  if (typeof base === "number" && (!seen.current || seen.current.base !== base)) seen.current = { base, at: now };
  if (typeof base !== "number" || !active || !seen.current) return base;
  const seconds = Math.max(0, (now - seen.current.at) / 1000);
  return base + 0.95 * (1 - Math.exp(-seconds / 30));
}

function StepItem({ step, now, summary }: { step: ActivityStep; now: number; summary?: string }) {
  const [open, setOpen] = React.useState(false);
  const tools = STEP_TOOLS.find(([pattern]) => pattern.test(step.key))?.[1] || [];
  const active = step.status === "active";
  const ms = Math.max(0, (active ? now : step.endedAt) - step.startedAt);
  const percent = useCreep(step.progress, active, now);
  const canOpen = Boolean(step.detail || tools.length);
  const body = <>
    <span className="mg-step-mark" aria-hidden="true">{active ? <span className="spinner"/> : <Icon name={step.status === "failed" ? "alert" : "check"} size={14}/>}</span>
    <div className="mg-step-body">
      <div className="mg-step-line"><span className={active ? "act-shimmer" : undefined} dir="auto">{step.label}</span>
        {ms >= 1000 ? <span className="mg-step-time" dir="ltr">{formatDuration(ms)}</span> : null}
        {active && typeof percent === "number" ? <span className="mg-step-time" dir="ltr">{percent.toFixed(1)}%</span> : null}
        {canOpen ? <Icon name="chevronDown" size={14} className={`act-chevron${open ? " is-open" : ""}`}/> : null}</div>
      {tools.length ? <div className="mg-step-tools">{tools.map(tool => <span key={tool} className="mg-tool">{tool}</span>)}</div> : null}
      {summary ? <p className="mg-step-summary" dir="auto">{summary}</p> : null}
      {open && step.detail ? <pre className="mg-step-detail" dir="auto">{step.detail}</pre> : null}
    </div>
  </>;
  return <li className="mg-step" data-status={step.status}>
    {canOpen ? <button type="button" className="mg-step-row" onClick={() => setOpen(value => !value)} aria-expanded={open}>{body}</button> : <div className="mg-step-row">{body}</div>}
  </li>;
}

/** The build's steps, all visible: the step's own line, the tools it used, how long it took (live while it runs), a live percentage, the agent's
 * summary where there is one, and (opened by a click on the step) the exact material of that step. */
export function MotionSteps({ steps, live, now, summaries }: { steps: ActivityStep[]; live: boolean; now: number; summaries?: { plan?: string; ready?: string } }) {
  return <ol className="mg-steps" aria-label="مراحل ساخت">
    {steps.map(step => <StepItem key={step.key} step={step} now={now} summary={step.key === "plan" ? summaries?.plan : undefined}/>)}
    {summaries?.ready && !live ? <li className="mg-step mg-step-ready"><div className="mg-step-body"><p className="mg-step-summary" dir="auto">{summaries.ready}</p></div></li> : null}
  </ol>;
}

/** The clip made from the chat request: live stages while it is made, then the player, downloads and versions. Part of the conversation, not a panel. */
export function MotionGraphicCard({ motionId, events, version: fixedVersion, latest = true, summaries }: { motionId: string; events: StudioEvent[]; version?: number; latest?: boolean; summaries?: { plan?: string; ready?: string } }) {
  const [motion, setMotion] = React.useState<MotionGraphic | null>(null);
  const [error, setError] = React.useState("");
  const [version, setVersion] = React.useState<number | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [now, setNow] = React.useState(() => Date.now() / 1000);
  React.useEffect(() => { const timer = window.setInterval(() => setNow(Date.now() / 1000), 1000); return () => window.clearInterval(timer); }, []);
  const lastEvent = React.useMemo(() => {
    const mine = events.filter(e => e.data?.motion_id === motionId);
    return mine.length ? mine[mine.length - 1].seq : 0;
  }, [events, motionId]);

  const refresh = React.useCallback(() => api.motionView(motionId).then(value => { setMotion(value); setError(""); }).catch(e => setError(friendlyError(e, "load the motion graphic"))), [motionId]);
  const loaded = React.useRef(false);
  React.useEffect(() => { if (latest || !loaded.current) { loaded.current = true; void refresh(); } }, [refresh, lastEvent, latest]);
  const [watching, setWatching] = React.useState(false);          // after a retry/change: poll until the new run shows up, even if the stream is late
  React.useEffect(() => { if (motion?.active) setWatching(false); }, [motion?.active]);
  React.useEffect(() => {
    if (!watching || !latest) return;
    const timer = window.setInterval(() => void refresh(), 1200);
    const stop = window.setTimeout(() => setWatching(false), 30000);
    return () => { window.clearInterval(timer); window.clearTimeout(stop); };
  }, [watching, refresh]);
  React.useEffect(() => {
    if (!motion?.active || !latest) return;
    const timer = window.setInterval(() => void refresh(), 2500);
    return () => window.clearInterval(timer);
  }, [motion?.active, refresh, latest]);
  React.useEffect(() => { setVersion(null); }, [motion?.current]);

  if (!motion) return <section className="mg" dir="rtl">{error ? <div className="notice" data-tone="error" role="alert">{error}</div> : <div className="tl-loading" role="status"><span className="spinner"/>در حال بارگذاری موشن‌گرافیک…</div>}</section>;

  // A finished run shows its own version, whatever newer versions exist. A run still being made shows its progress, and its video only once it is done.
  const wanted = fixedVersion ?? version ?? motion.current;
  const found = motion.versions.find(v => v.n === wanted) ?? (fixedVersion === undefined ? motion.versions[motion.versions.length - 1] : undefined);
  const shown = found && (fixedVersion !== undefined || (!motion.active && motion.status === "completed")) ? found : undefined;
  const ownsProgress = fixedVersion === undefined;
  const act = async (task: () => Promise<unknown>) => { setBusy(true); try { await task(); setWatching(true); await refresh(); } catch (e) { setError(friendlyError(e, "update the motion graphic")); } finally { setBusy(false); } };
  const ratio = shown ? `${shown.width} / ${shown.height}` : "9 / 16";

  return <section className="mg assistant-body" dir="rtl" aria-label="موشن‌گرافیک">
    {ownsProgress && (motion.active || motion.status === "failed" || motion.status === "needs_input" || (!shown && motion.log?.length)) ? <div className="mg-progress">
      <MotionSteps steps={motionSteps(motion, now * 1000)} live={motion.active} now={now * 1000} summaries={summaries}/>
      {motion.snapshots?.length ? <ShotStrip motionId={motionId} shots={motion.snapshots} stamp={motion.updated_at}/> : null}
      {motion.active && motion.eta_s !== null && motion.eta_at !== null ? <p className="mg-eta" aria-live="off">{etaText(motion.eta_at + motion.eta_s, now)}</p> : null}
      {motion.status === "needs_input" ? <div className="notice" data-tone="info">منتظر پاسخ شما هستم؛ جواب را همین‌جا در چت بنویسید.</div> : null}
      {motion.status === "failed" ? <div className="notice" data-tone="error" role="alert">{motion.error === "stopped" ? "ساخت متوقف شد." : motion.error || "ساخت کامل نشد."}</div> : null}
      {motion.status === "failed" ? <div className="mg-actions"><button className="btn btn-sm" disabled={busy} onClick={() => void act(() => api.motionRetry(motionId))}>تلاش دوباره</button></div> : null}
    </div> : null}

    {shown ? <div className="mg-result">
      <div className="mg-player" style={{ aspectRatio: ratio }} data-format={shown.format}>
        <AuthenticatedMedia as="video" key={`v-${motionId}-${shown.n}`} src={api.motionMediaUrl(motionId, "video", shown.n)} posterSrc={api.motionMediaUrl(motionId, "thumb", shown.n)} controls playsInline preload="metadata"/>
      </div>
      <div className="mg-info">
        <h3 className="bidi" dir="auto">{shown.title || "موشن‌گرافیک"}</h3>
        <p className="mg-meta">{secondsText(shown.duration)} · {FORMAT_LABEL[shown.format]} · نسخهٔ {new Intl.NumberFormat("fa-IR").format(shown.n)}</p>
        {shown.change ? <p className="mg-change bidi" dir="auto">تغییر: {shown.change}</p> : null}
        {fixedVersion === undefined && motion.versions.length > 1 ? <label className="mg-versions">نسخه‌ها
          <select value={shown.n} onChange={e => setVersion(Number(e.target.value))}>{motion.versions.map(v => <option key={v.n} value={v.n}>نسخهٔ {new Intl.NumberFormat("fa-IR").format(v.n)}{v.n === motion.current ? " (آخرین)" : ""}</option>)}</select>
        </label> : null}
        <div className="mg-actions">
          <a className="btn btn-sm" href={api.motionMediaUrl(motionId, "video", shown.n)} download="motion-graphic.mp4" onClick={e => { e.preventDefault(); void api.authenticatedObjectUrl(api.motionMediaUrl(motionId, "video", shown.n)).then(url => { const a = document.createElement("a"); a.href = url; a.download = "motion-graphic.mp4"; a.click(); }); }}>دانلود MP4</a>
          <a className="btn btn-sm btn-secondary" href={api.motionMediaUrl(motionId, "source", shown.n)} onClick={e => { e.preventDefault(); void api.authenticatedObjectUrl(api.motionMediaUrl(motionId, "source", shown.n)).then(url => { const a = document.createElement("a"); a.href = url; a.download = "motion-graphic.html"; a.click(); }); }}>فایل HTML</a>
        </div>
        {shown.notes?.length ? <details className="mg-notes"><summary>نکات بررسی خودکار ({new Intl.NumberFormat("fa-IR").format(shown.notes.length)})</summary><ul>{shown.notes.map(n => <li key={n} dir="ltr">{n}</li>)}</ul></details> : null}
        {latest && motion.status === "completed" ? <p className="field-hint">برای تغییر، همین‌جا بنویسید: متن، رنگ، زمان‌بندی، اندازه…</p> : null}
      </div>
    </div> : null}
    {error ? <div className="notice" data-tone="error" role="alert">{error}</div> : null}
  </section>;
}


/** The newest render of this chat's motion graphic for the Preview and Edit tabs (the chat itself keeps every render as its own message). */
export function MotionPanel({ motionId, events }: { motionId: string; events: StudioEvent[] }) {
  const [motion, setMotion] = React.useState<MotionGraphic | null>(null);
  const [version, setVersion] = React.useState<number | null>(null);
  const [error, setError] = React.useState("");
  const lastEvent = React.useMemo(() => { const mine = events.filter(e => e.data?.motion_id === motionId); return mine.length ? mine[mine.length - 1].seq : 0; }, [events, motionId]);
  const refresh = React.useCallback(() => api.motionView(motionId).then(value => { setMotion(value); setError(""); }).catch(e => setError(friendlyError(e, "load the motion graphic"))), [motionId]);
  React.useEffect(() => { void refresh(); }, [refresh, lastEvent]);
  React.useEffect(() => { setVersion(null); }, [motion?.current]);                      // a new render replaces what was shown
  React.useEffect(() => {
    if (!motion?.active) return;
    const timer = window.setInterval(() => void refresh(), 2500);
    return () => window.clearInterval(timer);
  }, [motion?.active, refresh]);
  if (!motion) return <div className="ws-empty" dir="rtl">{error ? <div className="notice" data-tone="error" role="alert">{error}</div> : <div className="tl-loading" role="status"><span className="spinner"/>در حال بارگذاری…</div>}</div>;
  const shown = motion.versions.find(v => v.n === (version ?? motion.current)) ?? motion.versions[motion.versions.length - 1];
  if (!shown) return <div className="ws-empty" dir="rtl"><p className="field-hint">{motion.active ? "ویدیو در حال ساخت است؛ همین‌که آماده شد اینجا نمایش داده می‌شود." : "هنوز ویدیویی ساخته نشده است."}</p></div>;
  return <section className="mg-panel" dir="rtl" aria-label="آخرین رندر">
    <div className="mg-player" style={{ aspectRatio: `${shown.width} / ${shown.height}` }} data-format={shown.format}>
      <AuthenticatedMedia as="video" key={`p-${motionId}-${shown.n}`} src={api.motionMediaUrl(motionId, "video", shown.n)} posterSrc={api.motionMediaUrl(motionId, "thumb", shown.n)} controls playsInline preload="metadata"/>
    </div>
    <h3 className="bidi" dir="auto">{shown.title || "موشن‌گرافیک"}</h3>
    <p className="mg-meta">{secondsText(shown.duration)} · {FORMAT_LABEL[shown.format]} · نسخهٔ {new Intl.NumberFormat("fa-IR").format(shown.n)}{shown.n === motion.current ? " (آخرین)" : ""}</p>
    {motion.active ? <p className="field-hint" role="status">نسخهٔ تازه در حال ساخت است؛ با تمام‌شدن، همین‌جا جایگزین می‌شود.</p> : null}
    {motion.versions.length > 1 ? <label className="mg-versions">نسخه‌ها
      <select value={shown.n} onChange={e => setVersion(Number(e.target.value))}>{motion.versions.map(v => <option key={v.n} value={v.n}>نسخهٔ {new Intl.NumberFormat("fa-IR").format(v.n)}{v.n === motion.current ? " (آخرین)" : ""}</option>)}</select>
    </label> : null}
    <p className="field-hint">برای تغییر، همین‌جا در چت بنویسید: متن، نریشن، رنگ، زمان‌بندی…</p>
  </section>;
}
