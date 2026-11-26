import { StudioProject } from "../api";
import { AuthenticatedMedia } from "../AuthenticatedMedia";
import { renderView } from "./model";
import { ProgressNotice, useProgressAge } from "./ProgressNotice";

const CLOUD_ACTIVE: Record<string, string> = { queued: "در صف رندر ابری", provisioning: "در حال ساخت سرور ابری", preparing: "آماده‌سازی فایل‌ها روی سرور ابری",
  downloading: "دریافت فایل‌ها روی سرور ابری", rendering: "در حال رندر روی سرور ابری", uploading: "ارسال خروجی از سرور ابری" };
const CLOUD_REASON: Record<string, string> = { "400": "درخواست ساخت سرور ابری پذیرفته نشد", "401": "کلید رن‌پاد معتبر نیست", "402": "اعتبار حساب رن‌پاد کافی نیست",
  "403": "رن‌پاد دسترسی نداد", "404": "منبع یا تصویر کانتینر در رن‌پاد پیدا نشد", "422": "تنظیمات سرور ابری (پردازنده، دیسک یا تصویر) رد شد" };
/** Where the render runs, from the cloud ledger (state.cloud_render): on RunPod, on the server after a cloud failure, or on the server only. */
function whereLine(project: StudioProject): { text: string; tone: "cloud" | "server" | "warn" } {
  const cloud = project.state?.cloud_render;
  const latest = cloud?.latest;
  if (!latest) return { text: "رندر روی سرور خودِ ادیتور انجام می‌شود", tone: "server" };
  if (CLOUD_ACTIVE[latest.state]) return { text: `${CLOUD_ACTIVE[latest.state]} (RunPod)${typeof latest.progress === "number" ? ` · ${Math.round(latest.progress)}٪` : ""}`, tone: "cloud" };
  if (latest.state === "completed") return { text: "رندر ابری تمام شد؛ در حال دریافت و آماده‌سازی خروجی", tone: "cloud" };
  const code = String(latest.error || "");
  const status = code.match(/runpod_http_(\d+)/)?.[1];
  const why = status ? (CLOUD_REASON[status] || `رن‌پاد خطا داد (${status})`) : code.startsWith("provisioning_rejected") ? "رن‌پاد ساخت سرور را رد کرد" :
    code.startsWith("provisioning_uncertain") ? "جواب رن‌پاد مشخص نبود" : code ? `خطا: ${code}` : "رندر ابری کامل نشد";
  const tries = (cloud?.attempts || []).filter((a: any) => a.state === "failed").length;
  return { text: `رندر ابری انجام نشد: ${why}${tries > 1 ? ` (${tries} تلاش)` : ""} · رندر روی سرور ادامه دارد`, tone: "warn" };
}

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
  const motion = metrics?.stage === project.state?.last_observed?.stage && stagePercent === undefined ? metrics : undefined;
  const motionDetail: string | undefined = motion?.detail || (motion ? "در حال رندر ویدیو" : undefined);
  return <div className="rc-progress" role="status" dir="rtl">
    <div className="meter" data-indeterminate={typeof percent === "number" && !stale ? undefined : ""} style={{ ["--value" as string]: `${percent ?? 0}%` }}
      role="progressbar" aria-label="Render progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={typeof percent === "number" ? percent : undefined}/>
    <div className="rc-meta"><span>{view.stageLabel === hideLabel ? "" : view.stageLabel}</span>{typeof percent === "number" ? <span dir="auto">{stale ? "در حال انجام، گزارش تازه‌ای نرسیده · " : ""}{stagePercent !== undefined ? "این مرحله: " : ""}<bdi dir="ltr">{percent}%</bdi></span> : null}</div>
    {(() => { const w = whereLine(project); return <p className="rc-where" data-tone={w.tone} dir="rtl">{w.text}</p>; })()}
    {motionDetail ? <p className="rc-detail" dir="rtl">{motionDetail}</p> : null}
    {(project.state?.live_frames?.length || 0) > 0 ? <div className="rc-frames" dir="ltr" aria-label="فریم‌های ساخته‌شده از ریلز">
      {project.state.live_frames.slice(-8).map((name: string) => <figure key={name}>
        <AuthenticatedMedia as="img" src={`/api/studio/projects/${project.id}/live-frames/${name}`} alt="" loading="lazy"/>
        <figcaption>{name.replace(/^s_/, "").replace(/\.jpg$/, "")}s</figcaption></figure>)}
    </div> : null}
    <ProgressNotice project={project}/>
  </div>;
}
