import { StudioProject } from "../api";
import { renderView } from "./model";
import { ProgressNotice, useProgressAge } from "./ProgressNotice";

/**
 * The one render progress block: the chat card, the Preview tab and the Edit tab all show exactly this (same label, same percentage,
 * same bar, same note), read from the same project state, so the three never disagree.
 */
export function RenderProgress({ project, hideLabel }: { project: StudioProject; hideLabel?: string }) {
  const view = renderView(project);
  const busy = view.phase === "queued" || view.phase === "rendering" || view.phase === "finalizing";
  const age = useProgressAge(busy, view.progress, view.stageLabel, project.state?.last_observed_at || project.updated_at);
  if (!busy) return null;
  const stale = age >= 30;
  const metrics = project.state?.last_observed?.render_metrics;
  const stagePercent = metrics?.stage === project.state?.last_observed?.stage && typeof metrics?.stage_percent === 'number' ? metrics.stage_percent : undefined;
  const percent = stagePercent ?? view.progress;
  return <div className="rc-progress" role="status" dir="rtl">
    <div className="meter" data-indeterminate={typeof percent === "number" && !stale ? undefined : ""} style={{ ["--value" as string]: `${percent ?? 0}%` }}
      role="progressbar" aria-label="Render progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={typeof percent === "number" ? percent : undefined}/>
    <div className="rc-meta"><span>{view.stageLabel === hideLabel ? "" : view.stageLabel}</span>{typeof percent === "number" ? <span dir="auto">{stale ? "آخرین گزارش: " : ""}{stagePercent !== undefined ? "این مرحله: " : ""}<bdi dir="ltr">{percent}%</bdi></span> : null}</div>
    <ProgressNotice project={project}/>
  </div>;
}
