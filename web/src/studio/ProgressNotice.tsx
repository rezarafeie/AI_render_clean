import React from 'react';

/** A wall clock is not a progress estimate. Never advance the engine's percentage. */
export function useProgressAge(running: boolean, progress: number | undefined, stage: string, serverTimestamp?: string | number) {
  const [reportedAt, setReportedAt] = React.useState(() => Date.now());
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    const persisted = typeof serverTimestamp === 'number' ? serverTimestamp : Date.parse(serverTimestamp || '');
    setReportedAt(Number.isFinite(persisted) ? persisted : Date.now()); setNow(Date.now());
  }, [progress, stage, running, serverTimestamp]);
  React.useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [running]);
  return running ? Math.max(0, Math.floor((now - reportedAt) / 1000)) : 0;
}

export function ProgressNotice({project}: {seconds?: number; project?: {state?: any}}) {
  const observed = project?.state?.last_observed;
  const detail = typeof observed?.message === 'string' ? observed.message.trim() : '';
  const metrics = observed?.render_metrics;
  const fresh = typeof metrics?.reported_at === 'number' && Date.now() / 1000 - metrics.reported_at < 30;
  const wholeRender = typeof metrics?.render_eta_at === 'number';
  const eta = wholeRender ? metrics.render_eta_at : metrics?.stage_eta_at;
  const end = fresh && typeof eta === 'number' && eta * 1000 > Date.now()
    ? new Date(eta * 1000).toLocaleTimeString('fa-IR', {hour:'2-digit', minute:'2-digit'}) : null;
  // Only engine facts: no mount-time clock or invented ETA.
  return <>
    {detail ? <p className="ws-hint" role="status" dir="auto">{detail}</p> : null}
    {end ? <p className="ws-hint" dir="rtl">{wholeRender ? 'پایان تخمینی رندر' : 'پایان تخمینی تبدیل فایل'}: {end}
      {!wholeRender ? ' · زمان مراحل بعد هنوز قابل تخمین نیست.' : ' · بر پایهٔ رندرهای قبلی؛ با سرعت پردازش تغییر می‌کند.'}</p> : null}
  </>;
}
