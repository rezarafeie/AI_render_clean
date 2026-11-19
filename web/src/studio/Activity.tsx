import React from "react";
import { Icon } from "../components/Icon";
import { clock, faNumber, formatDuration } from "../format";
import { useFa } from "./locale";
import { toolIcon } from "./steps";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
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
const NarrationAudio = React.lazy(() => import("./NarrationAudio"));
function Assets({ assets, projectId }: { assets: PreparedAsset[]; projectId?: string }) {
  if (!assets.length || !projectId) return null;
  return <React.Suspense fallback={null}><AssetList assets={assets} projectId={projectId}/></React.Suspense>;
}

const latin = (text: string) => (text.match(/[A-Za-z]/g) || []).length > (text.match(/[\u0600-\u06FF]/g) || []).length;
/** What the two halves of a step are called, by the kind of work (a command and its output, a file and what was written, a thought). */
function inLabel(step: ActivityStep): string {
  const tool = String(step.tool || "");
  if (tool === "pro_Bash") return "فرمان";
  if (tool === "pro_Write") return "فایل و محتوا";
  if (tool === "pro_Edit" || tool === "pro_MultiEdit") return "تغییر";
  if (tool === "pro_Read") return "فایل";
  if (tool === "pro_think") return "فکر";
  if (tool === "pro_TodoWrite") return "فهرست کارها";
  return "درخواست";
}
function outLabel(step: ActivityStep): string {
  const tool = String(step.tool || "");
  if (tool === "pro_Bash") return "خروجی";
  if (tool === "pro_think") return "نتیجه";
  return "پاسخ";
}

function WorkLog({ step, details }: { step: ActivityStep; details: NonNullable<ReturnType<typeof stepDetails>> }) {
  const fa = useFa();
  const run = details.run;
  const num = (value: number) => (fa ? faNumber(value) : String(value));
  const facts: string[] = [`شروع ${clock(step.startedAt, fa)}`];
  const took = typeof run?.latencyMs === "number" ? run.latencyMs : details.durationMs;
  if (took >= 1000 && step.status !== "active") facts.push(`مدت ${formatDuration(took, fa)}`);        // while it runs, the one live timer sits under the progress bar
  if (details.updates > 1) facts.push(`${num(details.updates)} گزارش`);
  if (run?.model) facts.push(run.model);
  if (typeof run?.inputTokens === "number") facts.push(`${num(run.inputTokens)} توکن ورودی`);
  if (typeof run?.outputTokens === "number") facts.push(`${num(run.outputTokens)} توکن خروجی`);
  const waiting = step.status === "active" && !details.response && !run?.error;
  return <div className="act-work">
    <Assets assets={details.assets} projectId={details.projectId}/>
    {details.request ? <section className="act-io act-in"><h5>{inLabel(step)}</h5><pre dir={latin(details.request) ? "ltr" : "auto"}>{details.request}</pre></section> : null}
    {details.assets.length && !details.response && !run?.error ? null : <section className={`act-io act-out${/^خطا:/.test(details.response || "") ? " is-error" : ""}`}><h5>{outLabel(step)}</h5>
      {details.response ? <pre dir={latin(details.response) ? "ltr" : "auto"}>{details.response}</pre>
        : run?.error ? <pre dir="ltr" className="act-error">{run.error}</pre>
        : waiting ? <p className="act-waiting"><span className="spinner"/> در حال کار…</p>
        : <p className="act-none">پاسخ متنی ثبت نشده است.</p>}
    </section>}
    <p className="act-facts" dir="auto">{facts.join(" · ")}</p>
  </div>;
}

/** The picture a step looked at (an image the agent read): a small thumbnail at the end of its row, full size on click (like Claude Code). */
function StepImage({ attachmentId }: { attachmentId: string }) {
  const { conversationId } = useParams();
  const [url, setUrl] = React.useState<string | null>(null);
  const [big, setBig] = React.useState(false);
  React.useEffect(() => {
    if (!conversationId) return;
    let live = true, made: string | null = null;
    api.authenticatedObjectUrl(api.studioAttachmentUrl(conversationId, attachmentId)).then(value => { made = value; if (live) setUrl(value); else URL.revokeObjectURL(value); }).catch(() => {});
    return () => { live = false; if (made) URL.revokeObjectURL(made); };
  }, [conversationId, attachmentId]);
  React.useEffect(() => {
    if (!big) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") setBig(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [big]);
  if (!url) return null;
  // Only Pro steps carry a picture. The thumbnail keeps the picture's own proportions; full size opens like the render frames (centred, no card, dim scrim).
  return <>
    <button type="button" className="act-thumb-fit" onClick={event => { event.stopPropagation(); setBig(true); }} aria-label="نمایش تصویر">
      <img src={url} alt="" loading="lazy" draggable={false}/>
    </button>
    {big ? <div className="overlay" role="dialog" aria-modal="true" aria-label="تصویر" onMouseDown={event => { if (event.target === event.currentTarget) setBig(false); }}>
      <figure className="mg-lightbox">
        <img src={url} alt=""/>
        <button type="button" className="icon-btn mg-lightbox-close" onClick={() => setBig(false)} aria-label="بستن"><Icon name="close" size={18}/></button>
      </figure>
    </div> : null}
  </>;
}

function StepRow({ step, retryHref, onOpenEditor }: { step: ActivityStep; retryHref?: string; onOpenEditor?: () => void }) {
  const fa = useFa();
  const details = stepDetails(step);
  const [open, setOpen] = React.useState(false);
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
  const image = [...step.events].reverse().find(event => typeof event.data.image === "string")?.data.image as string | undefined;
  return <li className="act-step" data-status={step.status}>
    {details
      ? <button type="button" className="act-row" onClick={() => setOpen(value => !value)} aria-expanded={open}>{label}</button>
      : <div className="act-row">{label}</div>}
    {image ? <div className="act-thumb-row" style={{ marginInlineStart: 28, marginTop: 4 }}><StepImage attachmentId={image}/></div> : null}
    {step.audioSrc ? <div className="act-audio"><React.Suspense fallback={null}><NarrationAudio src={step.audioSrc}/></React.Suspense></div> : null}
    {failed ? <div className="act-failure" role="alert"><p dir="auto" className="bidi wrap-safe">{friendlyFailure(step.notes[step.notes.length - 1])}</p></div> : null}
    {active && typeof step.progress === "number" ? <div className="meter act-meter" style={{ ["--value" as string]: `${step.progress}%` }} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={step.progress} aria-label={step.label}><span/></div> : null}
    {active ? <div className="act-timing">
      {typeof step.progress === "number" ? <span className="act-pct" dir="ltr">{fa ? `${faNumber(step.progress)}٪` : `${step.progress}%`}</span> : null}
      <Elapsed since={step.startedAt}/>
    </div> : null}
    {active && !open && details?.notes.length && details.notes[details.notes.length - 1] !== step.label ? <div className="act-details"><p dir="auto" className="bidi wrap-safe">{details.notes[details.notes.length - 1]}</p></div> : null}
    {details && open ? <div className="act-details">
      {description && description !== step.label ? <p className="act-desc-text bidi wrap-safe" dir="auto">{description}</p> : null}
      <WorkLog step={step} details={details}/>
    </div> : null}
  </li>;
}

/**
 * Compact, secondary activity for one stretch of work. Finished history collapses
 * to a single summary line; the current step stays prominent while work is live.
 */
export function ActivityBlock({ steps, live, retryHref, onOpenEditor, initiallyExpanded = false }: { steps: ActivityStep[]; live: boolean; retryHref?: string; onOpenEditor?: () => void; initiallyExpanded?: boolean }) {
  const [expanded, setExpanded] = React.useState(initiallyExpanded);
  const failed = steps.some(step => step.status === "failed");
  const current = steps.filter(step => step.status === "active" || step.status === "failed");
  const history = steps.filter(step => step.status === "done");
  const total = steps[steps.length - 1].endedAt - steps[0].startedAt;
  const fa = useFa();
  const count = `${fa ? faNumber(history.length) : history.length} مرحله`;
  const summary = `${count} انجام شد${!live && total >= 1000 ? ` · ${formatDuration(total, fa)}` : ""}`;
  // Finished with a single step: just show it. Otherwise show the current step(s) and collapse history.
  const visible = expanded || (!live && !failed && history.length === steps.length && steps.length === 1) ? steps : current.length ? current : live ? history.slice(-1) : [];
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
