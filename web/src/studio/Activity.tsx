import React from "react";
import { Icon, IconName } from "../components/Icon";
import { clock, formatDuration } from "../format";
import { Link } from "react-router-dom";
import { ActivityStep, friendlyFailure, stepDetails } from "./model";

function toolIcon(step: ActivityStep): IconName {
  const name = `${step.tool || ""} ${step.stage || ""}`.toLowerCase();
  if (/storyboard|concept/.test(name)) return "storyboard";
  if (/render/.test(name)) return "film";
  if (/motion/.test(name)) return "motion";
  if (/review|critic|qc|visual_analysis/.test(name)) return "eye";
  if (/creative|direction|planning/.test(name)) return "wand";
  if (/url|page/.test(name)) return "globe";
  if (/voice|narration|audio/.test(name)) return "mic2";
  if (/caption|transcript|translat|localize/.test(name)) return "captions";
  if (/image|asset|picture/.test(name)) return "image";
  if (/script|text/.test(name)) return "edit";
  if (/video|talking/.test(name)) return "video";
  return "thinking";
}

/** How long this step has been running, counted live (like a coding agent's status line). */
function Elapsed({ since }: { since: number }) {
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer); }, []);
  const ms = Math.max(0, now - since);
  return ms >= 1000 ? <span className="act-elapsed" aria-hidden="true">{formatDuration(ms)}</span> : null;
}

function StepRow({ step, retryHref }: { step: ActivityStep; retryHref?: string }) {
  const details = stepDetails(step);
  const [open, setOpen] = React.useState(false);
  const failed = step.status === "failed";
  const active = step.status === "active";
  const icon = <Icon name={failed ? "alert" : toolIcon(step)} size={14}/>;
  const thinking = active && step.events[step.events.length - 1]?.data.thinking === true;
  const label = <>
    <span className="act-icon" data-status={step.status}>{icon}</span>
    <span className={`act-label${active ? " is-active" : ""}`}><span className={active ? "act-shimmer" : undefined}>{step.label}</span></span>
    {details ? <Icon name="chevronDown" size={14} className={`act-chevron${open ? " is-open" : ""}`}/> : null}
  </>;
  return <li className="act-step" data-status={step.status}>
    {details
      ? <button type="button" className="act-row" onClick={() => setOpen(value => !value)} aria-expanded={open}>{label}</button>
      : <div className="act-row">{label}</div>}
    {failed ? <div className="act-failure" role="alert"><p dir="auto" className="bidi wrap-safe">{friendlyFailure(step.notes[step.notes.length - 1])}</p>{retryHref ? <Link className="btn btn-sm btn-secondary" to={retryHref}><Icon name="refresh" size={14}/>Open editor to retry</Link> : null}</div> : null}
    {active && typeof step.progress === "number" ? <div className="meter act-meter" style={{ ["--value" as string]: `${step.progress}%` }} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={step.progress} aria-label={step.label}><span/></div> : null}
    {active ? <div className="act-timing">
      {typeof step.progress === "number" ? <span className="act-pct" dir="ltr">{step.progress}%</span> : null}
      <Elapsed since={step.startedAt}/>
    </div> : null}
    {active && !open && details?.notes.length ? <div className="act-details"><p dir="auto" className="bidi wrap-safe">{details.notes[details.notes.length - 1]}</p></div> : null}
    {details && open ? <div className="act-details">
      {details.request ? <div className="act-request"><span>درخواست این مرحله</span><pre dir="auto">{details.request}</pre></div> : null}
      {details.notes.map((note, index) => <p key={index} dir="auto" className="bidi wrap-safe">{note}</p>)}
      <dl>
        <div><dt>شروع</dt><dd>{clock(step.startedAt)}</dd></div>
        {details.durationMs >= 1000 ? <div><dt>مدت</dt><dd>{formatDuration(details.durationMs)}</dd></div> : null}
        {details.updates > 1 ? <div><dt>گزارش‌ها</dt><dd>{details.updates}</dd></div> : null}
      </dl>
    </div> : null}
  </li>;
}

/**
 * Compact, secondary activity for one stretch of work. Finished history collapses
 * to a single summary line; the current step stays prominent while work is live.
 */
export function ActivityBlock({ steps, live, retryHref }: { steps: ActivityStep[]; live: boolean; retryHref?: string }) {
  const [expanded, setExpanded] = React.useState(false);
  const failed = steps.some(step => step.status === "failed");
  const current = steps.filter(step => step.status === "active" || step.status === "failed");
  const history = steps.filter(step => step.status === "done");
  const total = steps[steps.length - 1].endedAt - steps[0].startedAt;
  const count = `${history.length} مرحله`;
  const summary = `${count} انجام شد${!live && total >= 1000 ? ` · ${formatDuration(total)}` : ""}`;
  // Finished with a single step: just show it. Otherwise show the current step(s) and collapse history.
  const visible = expanded || (!live && !failed && history.length === steps.length && steps.length === 1) ? steps : current.length ? current : history.slice(-1);
  const canCollapse = steps.length > 1 && (expanded || visible.length < steps.length || history.length > 1);
  return <section className="act" aria-label="Activity">
    {canCollapse ? <button type="button" className="act-summary" onClick={() => setExpanded(value => !value)} aria-expanded={expanded}>
      <Icon name="check" size={14}/><span>{summary}</span><Icon name="chevronDown" size={14} className={`act-chevron${expanded ? " is-open" : ""}`}/>
    </button> : null}
    <ul className="act-list">{visible.map(step => <StepRow key={step.key} step={step} retryHref={retryHref}/>)}</ul>
  </section>;
}

export function ThinkingRow({ label }: { label: string }) {
  return <div className="act"><ul className="act-list"><li className="act-step" data-status="active"><div className="act-row">
    <span className="act-icon" data-status="active"><span className="act-dot" aria-hidden="true"/></span>
    <span className="act-label is-active"><span className="act-shimmer">{label}</span></span>
  </div></li></ul></div>;
}
