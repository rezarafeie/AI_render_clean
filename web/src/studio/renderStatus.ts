import React from "react";
import { StudioProject } from "../api";
import { renderView } from "./model";
import { useProgressAge } from "./ProgressNotice";

/**
 * ONE render status for every place that shows a render (the chat card, the Preview tab, the Edit tab, the panel): one label, one percentage, one hint.
 * It used to come from three sources at once (the engine's last report, the cloud ledger and the engine's message text), so the same card said 66%, 70% and 60%.
 *
 *  - while a cloud render (RunPod) is running, the cloud ledger is the only source: its stage names the label and its progress is the percentage;
 *  - otherwise the engine's own report is the only source.
 */

const CLOUD_LABEL: Record<string, string> = {
  queued: "در صف رندر ابری", provisioning: "در حال راه‌اندازی سرور ابری", preparing: "آماده‌سازی فایل‌ها روی سرور ابری",
  downloading: "ارسال فایل‌ها به سرور ابری", rendering: "در حال رندر روی سرور ابری", uploading: "دریافت خروجی از سرور ابری",
};
const CLOUD_REASON: Record<string, string> = {
  "400": "درخواست ساخت سرور ابری پذیرفته نشد", "401": "کلید رن‌پاد معتبر نیست", "402": "اعتبار حساب رن‌پاد کافی نیست",
  "403": "رن‌پاد دسترسی نداد", "404": "تصویر یا منبع کانتینر در رن‌پاد پیدا نشد", "422": "تنظیمات سرور ابری رد شد",
};

export const faNumber = (n: number) => Math.round(n).toLocaleString("fa-IR");
export function faDuration(seconds: number): string {
  const s = Math.max(1, Math.round(seconds));
  const m = Math.floor(s / 60), r = s % 60;
  if (m >= 60) return `${faNumber(Math.floor(m / 60))} ساعت و ${faNumber(m % 60)} دقیقه`;
  if (m === 0) return `${faNumber(r)} ثانیه`;
  return r < 5 ? `${faNumber(m)} دقیقه` : `${faNumber(m)} دقیقه و ${faNumber(r)} ثانیه`;
}

export interface RenderStatus {
  /** What is happening, one sentence. */
  label: string;
  /** 0-100, or undefined while the stage has no measurable progress (the bar then moves on its own). */
  percent?: number;
  /** One short line under the bar: the time left, a note that no report arrived, or the reason a cloud render fell back. */
  hint?: string;
  tone: "normal" | "warn";
  cloud: boolean;
}

/** Time left from how fast the percentage moved, never from a clock that merely runs (needs two readings at least 10 seconds apart). */
function useEta(percent: number | undefined, active: boolean): number | undefined {
  const first = React.useRef<{ p: number; t: number } | null>(null);
  const [eta, setEta] = React.useState<number>();
  React.useEffect(() => {
    if (!active || typeof percent !== "number") { first.current = null; setEta(undefined); return; }
    const now = Date.now();
    if (!first.current || percent < first.current.p) { first.current = { p: percent, t: now }; setEta(undefined); return; }
    const dt = (now - first.current.t) / 1000, dp = percent - first.current.p;
    if (dt >= 10 && dp > 0) setEta(((100 - percent) / dp) * dt);
  }, [percent, active]);
  return eta;
}

export function useRenderStatus(project: StudioProject): RenderStatus | null {
  const view = renderView(project);
  const busy = view.phase === "queued" || view.phase === "rendering" || view.phase === "finalizing";
  const observed = (project.state?.last_observed || {}) as Record<string, any>;
  const cloud = project.state?.cloud_render?.latest;
  const cloudActive = !!cloud && !!CLOUD_LABEL[cloud.state];
  const age = useProgressAge(busy, view.progress, view.stageLabel, project.state?.last_observed_at || project.updated_at);

  const cloudPercent = cloudActive && (cloud.state === "rendering" || cloud.state === "uploading") && typeof cloud.progress === "number" && cloud.progress > 0
    ? Math.min(100, Math.round(cloud.progress)) : undefined;
  const enginePercent = !cloudActive && typeof view.progress === "number" ? view.progress : undefined;
  const percent = cloudActive ? cloudPercent : enginePercent;
  const eta = useEta(percent, busy);
  if (!busy) return null;

  if (cloudActive) {
    return { label: CLOUD_LABEL[cloud.state], percent, tone: "normal", cloud: true,
             hint: eta !== undefined && eta > 3 ? `حدود ${faDuration(eta)} مانده` : undefined };
  }
  // On the server's own engine. A cloud attempt that failed a moment ago is said once, as the reason this render is slower.
  const failed = cloud && cloud.state === "failed" && Date.now() / 1000 - Number(cloud.updated || 0) < 20 * 60 ? cloud : null;
  const status = String(failed?.error || "").match(/runpod_http_(\d+)/)?.[1];
  const why = failed ? (status ? (CLOUD_REASON[status] || `رن‌پاد خطا داد (${faNumber(Number(status))})`) : "رن‌پاد ساخت سرور را نپذیرفت") : "";
  const stale = age >= 30;
  const hint = failed ? `رندر ابری انجام نشد (${why})؛ رندر روی سرور ادیتور ادامه دارد و کندتر است.`
    : stale ? "گزارش تازه‌ای نرسیده؛ کار ادامه دارد." : eta !== undefined && eta > 3 ? `حدود ${faDuration(eta)} مانده` : undefined;
  return { label: view.stageLabel || "در حال رندر ویدیو", percent, hint, tone: failed ? "warn" : "normal", cloud: false };
}
