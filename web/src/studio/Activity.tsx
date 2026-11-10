import React from "react";
import { Icon } from "../components/Icon";
import { clock, faNumber, formatDuration } from "../format";
import { useFa } from "./locale";
import { toolIcon } from "./steps";
import { Link } from "react-router-dom";
import { ActivityStep, PreparedAsset, WORKING_NOTE, friendlyFailure, stepDetails } from "./model";

/** How long this step has been running, counted live (like a coding agent's status line). */
function Elapsed({ since }: { since: number }) {
  const fa = useFa();
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer); }, []);
  const ms = Math.max(0, now - since);
  return ms >= 1000 ? <span className="act-elapsed" aria-hidden="true">{formatDuration(ms, fa)}</span> : null;
}

/** The step's work log, like a tool call in a coding agent: what it asked and what came back (or that it is still working), and one line of facts. */
const AssetList = React.lazy(() => import("./AssetList"));
function Assets({ assets, projectId }: { assets: PreparedAsset[]; projectId?: string }) {
  if (!assets.length || !projectId) return null;
  return <React.Suspense fallback={null}><AssetList assets={assets} projectId={projectId}/></React.Suspense>;
}

function WorkLog({ step, details }: { step: ActivityStep; details: NonNullable<ReturnType<typeof stepDetails>> }) {
  const fa = useFa();
  const run = details.run;
  const num = (value: number) => (fa ? faNumber(value) : String(value));
  const facts: string[] = [`شروع ${clock(step.startedAt, fa)}`];
  const took = typeof run?.latencyMs === "number" ? run.latencyMs : details.durationMs;
  if (took >= 1000) facts.push(`مدت ${formatDuration(took, fa)}`);
  if (details.updates > 1) facts.push(`${num(details.updates)} گزارش`);
  if (run?.model) facts.push(run.model);
  if (typeof run?.inputTokens === "number") facts.push(`${num(run.inputTokens)} توکن ورودی`);
  if (typeof run?.outputTokens === "number") facts.push(`${num(run.outputTokens)} توکن خروجی`);
  const waiting = step.status === "active" && !details.response && !run?.error;
  return <div className="act-work">
    <Assets assets={details.assets} projectId={details.projectId}/>
    {details.request ? <section className="act-io"><h5>درخواست</h5><pre dir="auto">{details.request}</pre></section> : null}
    {details.assets.length && !details.response && !run?.error ? null : <section className="act-io"><h5>پاسخ</h5>
      {details.response ? <pre dir="auto">{details.response}</pre>
        : run?.error ? <pre dir="ltr" className="act-error">{run.error}</pre>
        : waiting ? <p className="act-waiting"><span className="spinner"/> در حال کار… <Elapsed since={step.startedAt}/></p>
        : <p className="act-none">پاسخ متنی ثبت نشده است.</p>}
    </section>}
    <p className="act-facts" dir="auto">{facts.join(" · ")}</p>
  </div>;
}

function StepRow({ step, retryHref, onOpenEditor }: { step: ActivityStep; retryHref?: string; onOpenEditor?: () => void }) {
  const fa = useFa();
  const details = stepDetails(step);
  const [open, setOpen] = React.useState(false);
  const [logOpen, setLogOpen] = React.useState(false);                    // the log is closed until the description is clicked
  // What this step is, in a sentence: its own description (the working / done boilerplate is not a description).
  const description = (details?.notes || []).find(note => note !== WORKING_NOTE && !/^پاسخ این مرحله دریافت شد/.test(note)) || step.label;
  const failed = step.status === "failed";
  const active = step.status === "active";
  const icon = <Icon name={failed ? "alert" : toolIcon(step.tool, step.stage)} size={14}/>;
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
    {failed ? <div className="act-failure" role="alert"><p dir="auto" className="bidi wrap-safe">{friendlyFailure(step.notes[step.notes.length - 1])}</p></div> : null}
    {active && typeof step.progress === "number" ? <div className="meter act-meter" style={{ ["--value" as string]: `${step.progress}%` }} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={step.progress} aria-label={step.label}><span/></div> : null}
    {active ? <div className="act-timing">
      {typeof step.progress === "number" ? <span className="act-pct" dir="ltr">{fa ? `${faNumber(step.progress)}٪` : `${step.progress}%`}</span> : null}
      <Elapsed since={step.startedAt}/>
    </div> : null}
    {active && !open && details?.notes.length ? <div className="act-details"><p dir="auto" className="bidi wrap-safe">{details.notes[details.notes.length - 1]}</p></div> : null}
    {details && open ? <div className="act-details">
      <button type="button" className="act-desc" onClick={() => setLogOpen(value => !value)} aria-expanded={logOpen}>
        <span dir="auto" className="bidi wrap-safe">{description}</span>
        <Icon name="chevronDown" size={13} className={`act-chevron${logOpen ? " is-open" : ""}`}/>
      </button>
      {logOpen ? <WorkLog step={step} details={details}/> : null}
    </div> : null}
  </li>;
}

/**
 * Compact, secondary activity for one stretch of work. Finished history collapses
 * to a single summary line; the current step stays prominent while work is live.
 */
export function ActivityBlock({ steps, live, retryHref, onOpenEditor }: { steps: ActivityStep[]; live: boolean; retryHref?: string; onOpenEditor?: () => void }) {
  const [expanded, setExpanded] = React.useState(false);
  const failed = steps.some(step => step.status === "failed");
  const current = steps.filter(step => step.status === "active" || step.status === "failed");
  const history = steps.filter(step => step.status === "done");
  const total = steps[steps.length - 1].endedAt - steps[0].startedAt;
  const fa = useFa();
  const count = `${fa ? faNumber(history.length) : history.length} مرحله`;
  const summary = `${count} انجام شد${!live && total >= 1000 ? ` · ${formatDuration(total, fa)}` : ""}`;
  // Finished with a single step: just show it. Otherwise show the current step(s) and collapse history.
  const visible = expanded || (!live && !failed && history.length === steps.length && steps.length === 1) ? steps : current.length ? current : history.slice(-1);
  const canCollapse = steps.length > 1 && (expanded || visible.length < steps.length || history.length > 1);
  return <section className="act" aria-label="Activity">
    {canCollapse ? <button type="button" className="act-summary" onClick={() => setExpanded(value => !value)} aria-expanded={expanded}>
      <Icon name="check" size={14}/><span>{summary}</span><Icon name="chevronDown" size={14} className={`act-chevron${expanded ? " is-open" : ""}`}/>
    </button> : null}
    <ul className="act-list">{visible.map(step => <StepRow key={step.key} step={step} retryHref={retryHref} onOpenEditor={onOpenEditor}/>)}</ul>
  </section>;
}

export function ThinkingRow({ label }: { label: string }) {
  return <div className="act"><ul className="act-list"><li className="act-step" data-status="active"><div className="act-row">
    <span className="act-icon" data-status="active"><span className="act-dot" aria-hidden="true"/></span>
    <span className="act-label is-active"><span className="act-shimmer">{label}</span></span>
  </div></li></ul></div>;
}
