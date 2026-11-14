import React from "react";
import { Link } from "react-router-dom";
import type { Job } from "./api";

export function Breadcrumbs({ items }: { items: { label: string; to?: string }[] }) {
  return <nav className="breadcrumbs" aria-label="Breadcrumb"><ol>{items.map((item, index) =>
    <li key={`${item.label}-${index}`}>{item.to ? <Link to={item.to}>{item.label}</Link> : <span aria-current="page">{item.label}</span>}</li>
  )}</ol></nav>;
}

type StepStatus = "pending" | "active" | "completed" | "failed";
const workflow = ["Upload", "Plan", "Review", "Render", "Export"] as const;

export function JobWorkflow({ job, current, renderStatus }: { job?: Job | null; current: number; renderStatus?: string }) {
  const generated = !!job?.plan || job?.generate?.status === "done";
  const generationFailed = job?.generate?.status === "error";
  const rendering = renderStatus || job?.render?.status || "idle";
  const renderDone = rendering === "done";
  const renderFailed = rendering === "error" || rendering === "failed";
  const statuses: StepStatus[] = workflow.map((_, index) => {
    if (index === 0) return job ? "completed" : "active";
    if (index === 1) return generationFailed ? "failed" : generated ? "completed" : job ? "active" : "pending";
    if (index === 2) return generated ? current > 2 ? "completed" : "active" : "pending";
    if (index === 3) return renderFailed ? "failed" : renderDone ? "completed" : current >= 3 ? "active" : "pending";
    return renderDone ? current === 4 ? "active" : "completed" : "pending";
  });
  const id = job?.id;
  const links = ["/new", id ? `/jobs/${id}` : "", id ? `/jobs/${id}` : "", id ? `/jobs/${id}/render` : "", id && renderDone ? `/jobs/${id}/render#export` : ""];
  return <div className="workflow" aria-label="Job progress"><ol>{workflow.map((label, index) => {
    const status = statuses[index];
    const content = <><span className="workflow-number" aria-hidden="true">{status === "completed" ? "✓" : index + 1}</span><span>{label}</span><small>{status}</small></>;
    return <li key={label} className={`workflow-${status}`}>{links[index] && status !== "pending" && status !== "failed" ?
      <Link to={links[index]} aria-current={index === current ? "step" : undefined}>{content}</Link> : <span aria-current={index === current ? "step" : undefined}>{content}</span>}</li>;
  })}</ol></div>;
}

export function NextStep({ children }: { children: React.ReactNode }) {
  return <div className="next-step"><strong>What’s next?</strong><div>{children}</div></div>;
}

export function notify(message: string) { window.dispatchEvent(new CustomEvent<string>("ai-render:toast", { detail: message })); }

export function ToastHost() {
  const [items, setItems] = React.useState<{ id: number; text: string }[]>([]);
  React.useEffect(() => {
    const onToast = (event: Event) => {
      const id = Date.now() + Math.random();
      setItems(current => [...current, { id, text: (event as CustomEvent<string>).detail }]);
      window.setTimeout(() => setItems(current => current.filter(item => item.id !== id)), 6000);
    };
    window.addEventListener("ai-render:toast", onToast);
    return () => window.removeEventListener("ai-render:toast", onToast);
  }, []);
  return <div className="toast-stack" aria-live="polite" aria-atomic="false">{items.map(item =>
    <div className="toast" key={item.id}><span>{item.text}</span><button className="toast-close" onClick={() => setItems(current => current.filter(i => i.id !== item.id))} aria-label="Dismiss notification">×</button></div>
  )}</div>;
}

/** Keep operational details in logs while giving people a useful next step. */
export function friendlyError(error: unknown, action = "complete this action"): string {
  const message = error instanceof Error ? error.message : String(error ?? "");
  if (/^402 /.test(message) && /اعتبار/.test(message)) return "اعتبار شما تمام شده است. برای ادامه، اعتبار بخرید یا افزایش دهید.";
  if (/^409 Provider lm_gateway is not configured/.test(message)) return "ادامهٔ تولید انجام نشد: مسیر تولید تصویر (photorealistic_image) در تنظیمات AI فعال نیست یا کلید Gateway در دسترس نیست. کلید مدل متنی به‌تنهایی کافی نیست. استوری‌بورد شما حفظ شده است؛ مسیر تصویر را تنظیم کنید یا از تصاویر واقعی محصول استفاده کنید.";
  if (/^503 EditorGPT Medium/.test(message)) return "EditorGPT Medium در این نصب در دسترس نیست. برای ادامه، خودتان EditorGPT Lite را از منوی کنار + انتخاب کنید؛ موتور خودکار تغییر نکرده است.";
  if (/^409 Medium در همین گفتگو/.test(message)) return "Medium در این گفتگو اجرای ناتمام دارد. برنامهٔ قبلی را تأیید، ادامه یا لغو کنید؛ انتخاب موتور پیام بعدی محفوظ است.";
  if (/^409 (حداکثر چهار اجرای|درخواست‌های Medium)/.test(message)) return "تعداد درخواست‌های Medium به حد مجاز رسیده است؛ یکی از اجراهای قبلی را تمام کنید یا کمی بعد دوباره تلاش کنید.";
  if (/401|unauthori[sz]ed|session expired/i.test(message)) return "Your session has expired. Sign in again and retry.";
  if (/403|forbidden/i.test(message)) return "You do not have access to this item. Check your account and try again.";
  if (/413|too large|file size/i.test(message)) return "This file is too large. Choose a smaller file and try again.";
  if (/network|failed to fetch|timeout|timed out|502|503|504/i.test(message)) return "We could not reach the server. Check your connection and try again.";
  if (/invalid credentials|invalid email or password|incorrect password/i.test(message)) return "The email or password is incorrect. Check both and try again. Accounts on a local installation may differ from the online service.";
  if (/already exists|already registered/i.test(message)) return "This account already exists. Sign in or use another email.";
  if (/^invalid json$/i.test(message)) return "The edit plan is not valid JSON. Check its formatting and try again.";
  if (/upload was cancelled|upload was canceled/i.test(message)) return "Upload cancelled. Your video is still selected; select Retry upload when you're ready.";
  return `We could not ${action}. Please try again. If it keeps happening, contact support.`;
}

export function LoadingState({ label, rows = 3 }: { label: string; rows?: number }) {
  return <div className="ui-state ui-loading" role="status" aria-live="polite" aria-label={label}>
    <span className="ui-spinner" aria-hidden="true" />
    <span>{label}</span>
    <div className="ui-skeleton" aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => <span key={i} />)}
    </div>
  </div>;
}

export function EmptyState({ icon = "✦", title, description, action }: {
  icon?: string; title: string; description: string; action?: React.ReactNode;
}) {
  return <div className="empty-state ui-empty">
    <div className="empty-state-icon" aria-hidden="true">{icon}</div>
    <strong>{title}</strong><p>{description}</p>{action}
  </div>;
}
