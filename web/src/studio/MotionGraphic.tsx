import React from "react";
import { api, MotionGraphic, StudioEvent } from "../api";
import { AuthenticatedMedia } from "../AuthenticatedMedia";
import { friendlyError } from "../ui";
import { etaText, motionSteps } from "./motionModel";
import { ActivityBlock } from "./Activity";

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

/** The clip made from the chat request: live stages while it is made, then the player, downloads and versions. Part of the conversation, not a panel. */
export function MotionGraphicCard({ motionId, events }: { motionId: string; events: StudioEvent[] }) {
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
  React.useEffect(() => { void refresh(); }, [refresh, lastEvent]);
  React.useEffect(() => {
    if (!motion?.active) return;
    const timer = window.setInterval(() => void refresh(), 2500);
    return () => window.clearInterval(timer);
  }, [motion?.active, refresh]);
  React.useEffect(() => { setVersion(null); }, [motion?.current]);

  if (!motion) return <section className="mg" dir="rtl">{error ? <div className="notice" data-tone="error" role="alert">{error}</div> : <div className="tl-loading" role="status"><span className="spinner"/>در حال بارگذاری موشن‌گرافیک…</div>}</section>;

  const shown = motion.versions.find(v => v.n === (version ?? motion.current)) ?? motion.versions[motion.versions.length - 1];
  const act = async (task: () => Promise<unknown>) => { setBusy(true); try { await task(); await refresh(); } catch (e) { setError(friendlyError(e, "update the motion graphic")); } finally { setBusy(false); } };
  const ratio = shown ? `${shown.width} / ${shown.height}` : "9 / 16";

  return <section className="mg assistant-body" dir="rtl" aria-label="موشن‌گرافیک">
    <div className="notice" role="status">ساخت موشن‌گرافیک در چت فعلاً در دسترس نیست؛ این مسیر باید به قالب‌های تأییدشده متصل شود.</div>
    {motion.active || motion.status === "failed" || motion.status === "needs_input" || (!shown && motion.log?.length) ? <div className="mg-progress">
      <ActivityBlock steps={motionSteps(motion, now * 1000)} live={motion.active}/>
      {motion.active && motion.eta_s !== null && motion.eta_at !== null ? <p className="mg-eta" aria-live="off">{etaText(motion.eta_at + motion.eta_s, now)}</p> : null}
      {motion.status === "needs_input" ? <div className="notice" data-tone="info">منتظر پاسخ شما هستم؛ جواب را همین‌جا در چت بنویسید.</div> : null}
      {motion.status === "failed" ? <div className="notice" data-tone="error" role="alert">{motion.error === "stopped" ? "ساخت متوقف شد." : motion.error || "ساخت کامل نشد."}</div> : null}
    </div> : null}

    {shown ? <div className="mg-result">
      <div className="mg-player" style={{ aspectRatio: ratio }} data-format={shown.format}>
        <AuthenticatedMedia as="video" key={`v-${motionId}-${shown.n}`} src={api.motionMediaUrl(motionId, "video", shown.n)} posterSrc={api.motionMediaUrl(motionId, "thumb", shown.n)} controls playsInline preload="metadata"/>
      </div>
      <div className="mg-info">
        <h3 className="bidi" dir="auto">{shown.title || "موشن‌گرافیک"}</h3>
        <p className="mg-meta">{secondsText(shown.duration)} · {FORMAT_LABEL[shown.format]} · نسخهٔ {new Intl.NumberFormat("fa-IR").format(shown.n)}</p>
        {shown.change ? <p className="mg-change bidi" dir="auto">تغییر: {shown.change}</p> : null}
        {motion.versions.length > 1 ? <label className="mg-versions">نسخه‌ها
          <select value={shown.n} onChange={e => setVersion(Number(e.target.value))}>{motion.versions.map(v => <option key={v.n} value={v.n}>نسخهٔ {new Intl.NumberFormat("fa-IR").format(v.n)}{v.n === motion.current ? " (آخرین)" : ""}</option>)}</select>
        </label> : null}
        <div className="mg-actions">
          <a className="btn btn-sm" href={api.motionMediaUrl(motionId, "video", shown.n)} download="motion-graphic.mp4" onClick={e => { e.preventDefault(); void api.authenticatedObjectUrl(api.motionMediaUrl(motionId, "video", shown.n)).then(url => { const a = document.createElement("a"); a.href = url; a.download = "motion-graphic.mp4"; a.click(); }); }}>دانلود MP4</a>
          <a className="btn btn-sm btn-secondary" href={api.motionMediaUrl(motionId, "source", shown.n)} onClick={e => { e.preventDefault(); void api.authenticatedObjectUrl(api.motionMediaUrl(motionId, "source", shown.n)).then(url => { const a = document.createElement("a"); a.href = url; a.download = "motion-graphic.html"; a.click(); }); }}>فایل HTML</a>
        </div>
        {shown.notes?.length ? <details className="mg-notes"><summary>نکات بررسی خودکار ({new Intl.NumberFormat("fa-IR").format(shown.notes.length)})</summary><ul>{shown.notes.map(n => <li key={n} dir="ltr">{n}</li>)}</ul></details> : null}
        {motion.status === "completed" ? <p className="field-hint">برای تغییر، همین‌جا بنویسید: متن، رنگ، زمان‌بندی، اندازه…</p> : null}
      </div>
    </div> : null}
    {error ? <div className="notice" data-tone="error" role="alert">{error}</div> : null}
  </section>;
}
