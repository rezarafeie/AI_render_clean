import React from "react";
import { api, StudioProject } from "../api";
import { AuthenticatedMedia } from "../AuthenticatedMedia";
import { Icon } from "../components/Icon";
import { formatDuration } from "../format";
import { Link } from "react-router-dom";
import { friendlyFailure, renderView } from "./model";
import { RenderProgress } from './RenderProgress';
import { useProgressAge } from './ProgressNotice';

function useElapsed(startedAt: number, running: boolean) {
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [running]);
  return startedAt ? Math.max(0, now - startedAt) : 0;
}

/**
 * One inline card per project. It updates in place while rendering
 * (stage, percentage, elapsed time) and becomes the finished player: no new row per percent.
 */
export function RenderCard({ project, sourceUrl, startedAt, compact, onOpenPreview, onEditAgain, retryHref }: {
  project: StudioProject; sourceUrl?: string; startedAt: number;
  /** Desktop: the video lives in the Preview tab, so the chat shows only the status card. */
  compact?: boolean;
  onOpenPreview: () => void; onEditAgain: () => void; retryHref?: string;
}) {
  const view = renderView(project);
  const output = view.output ? `${api.studioOutputUrl(project.id)}?candidate=${Boolean(view.review)}&version=${encodeURIComponent(view.output)}` : undefined;
  const busy = view.phase === "queued" || view.phase === "rendering" || view.phase === "finalizing";
  const elapsed = useElapsed(startedAt, busy);
  const version = String(view.output || "").match(/\/v(\d+)(?:_preview)?\.mp4(?:$|\?)/)?.[1] || project.current_version;
  const percent = view.progress;
  const age = useProgressAge(busy, percent, view.stageLabel, project.state?.last_observed_at || project.updated_at);
  const shownPercent = age >= 30 ? undefined : percent;
  const title = view.review ? "ویدیو آمادهٔ بررسی شماست" : view.phase === "done" ? "Your video is ready" : view.phase === "failed" ? "Rendering didn’t finish" : view.phase === "finalizing" ? "Finalizing your video" : "Rendering your video";

  return <article className="render-card" data-phase={view.phase} data-compact={compact || undefined} aria-label={title}>
    <header className="rc-head">
      <h3>{title}</h3>
      {view.phase === "done" ? <span className="badge" data-tone="success"><i/>Version {version}</span> : busy && elapsed >= 1000 ? <span className="rc-elapsed">{formatDuration(elapsed)}</span> : null}
    </header>

    {compact && view.phase !== "failed" ? null : <div className="rc-frame">
      {output ? <AuthenticatedMedia as="video" controls playsInline preload="metadata" src={output} className="rc-video"/> : <>
        {sourceUrl ? <AuthenticatedMedia as="video" muted playsInline preload="metadata" src={sourceUrl} className="rc-backdrop" aria-hidden="true" tabIndex={-1}/> : <div className="rc-backdrop skeleton" aria-hidden="true"/>}
        <div className="rc-overlay">
          {view.phase === "failed" || view.review ? <Icon name="alert" size={28}/> : <span className="spinner rc-spinner" aria-hidden="true"/>}
          {view.phase !== "rendering" ? <strong>{view.stageLabel}</strong> : null}
          {view.phase === "failed" ? <p dir="auto" className="bidi wrap-safe">{friendlyFailure(view.message)}</p> : null}
          {busy && typeof shownPercent === "number" ? <span className="rc-pct" aria-hidden="true">{shownPercent}%</span> : null}
        </div>
      </>}
    </div>}

    {view.review ? <div className="notice" dir="rtl" role="status">{view.stageLabel}<p>{view.message}</p>
      {project.state?.technical_qc?.renderer ? <p>موتور رندر: {String(project.state.technical_qc.renderer)}</p> : null}
      {project.state?.technical_qc?.renderer_failure ? <p>دلیل تغییر موتور: {String(project.state.technical_qc.renderer_failure)}</p> : null}
    </div> : null}
    {busy ? <RenderProgress project={project} hideLabel={title}/> : null}

    {(view.phase === "done" || view.phase === "needs_review") && output ? <div className="rc-actions">
      {!view.review ? <button className="btn btn-sm" onClick={() => void api.downloadAuthenticated(output, `${project.title || "video"}.mp4`)}><Icon name="download" size={15}/>Download</button> : null}
      <button className="btn btn-sm btn-secondary" onClick={onOpenPreview}><Icon name="eye" size={15}/>Open in Preview</button>
      <button className="btn btn-sm btn-ghost" onClick={onEditAgain}><Icon name="edit" size={15}/>Edit again</button>
    </div> : null}
    {view.phase === "failed" && retryHref ? <div className="rc-actions"><Link className="btn btn-sm btn-secondary" to={retryHref}><Icon name="refresh" size={15}/>Open editor to retry</Link></div> : null}
  </article>;
}
