import { StudioProject } from "../api";
import { AuthenticatedMedia } from "../AuthenticatedMedia";
import { faNumber, useRenderStatus } from "./renderStatus";

/**
 * The one render progress block (the chat card, the Preview tab, the Edit tab and the panel all show exactly this): one label, one percentage, one bar,
 * one hint. Everything comes from useRenderStatus, so two places never disagree. The reel's own frames, when the engine has made some, sit under it.
 */
export function RenderProgress({ project }: { project: StudioProject; hideLabel?: string }) {
  const status = useRenderStatus(project);
  if (!status) return null;
  const frames: string[] = project.state?.live_frames || [];
  const percent = status.percent;
  return <div className="rc-progress" role="status" dir="rtl" data-tone={status.tone}>
    <div className="rc-line"><span className="rc-label">{status.label}</span>{typeof percent === "number" ? <bdi className="rc-percent" dir="ltr">{faNumber(percent)}٪</bdi> : null}</div>
    <div className="meter" data-indeterminate={typeof percent === "number" ? undefined : ""} style={{ ["--value" as string]: `${percent ?? 0}%` }}
      role="progressbar" aria-label="Render progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={typeof percent === "number" ? percent : undefined}/>
    {status.hint ? <p className="rc-hint" data-tone={status.tone}>{status.hint}</p> : null}
    {frames.length > 0 ? <div className="rc-frames" dir="ltr" aria-label="فریم‌های ساخته‌شده از ریلز">
      {frames.slice(-6).map(name => <AuthenticatedMedia key={name} as="img" src={`/api/studio/projects/${project.id}/live-frames/${name}`} alt="" loading="lazy"/>)}
    </div> : null}
  </div>;
}
