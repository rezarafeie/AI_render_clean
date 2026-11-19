import React from "react";
import { api } from "../api";
import { AuthenticatedMedia } from "../AuthenticatedMedia";
import { Icon } from "../components/Icon";
import { formatDuration } from "../format";

const STYLE_NAME: Record<string, string> = { premium: "تدوین پریمیوم تمام‌قاب", split: "تاکینگ دوتکه", render: "رندر ابری پروژهٔ Pro" };
const CLOUD_STAGE: Record<string, string> = {
  queued: "در صف سرور ابری", provisioning: "آماده‌سازی سرور ابری", preparing: "آماده‌سازی پروژه روی سرور ابری", uploading: "ارسال پروژه به سرور ابری",
  downloading: "دریافت ویدیو از سرور ابری", rendering: "رندر روی سرور ابری", done: "رندر ابری تمام شد", failed: "رندر ابری متوقف شد",
};

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
 * The render card of a studio engine job the Pro agent started (`pro.job` events): the same card as Lite's render (the same classes), with the
 * engine's stage and percent, the render cloud's own report while it renders, and the finished video with a download button.
 */
export function ProJobCard({ data, startedAt, conversationId, sourceUrl }: { data: Record<string, any>; startedAt: number; conversationId?: string;
  /** The chat's own video, dimmed behind the progress like Lite's render card. */ sourceUrl?: string }) {
  const state = String(data.state || "queued");
  const busy = ["queued", "transcribing", "running", "rendering"].includes(state);
  const done = state === "done";
  const failed = state === "failed";
  const elapsed = useElapsed(startedAt, busy);
  const cloud = (data.cloud || {}) as { progress?: number; stage?: string; detail?: string };
  const cloudActive = busy && state === "rendering" && (cloud.stage || typeof cloud.progress === "number");
  const percent = cloudActive && typeof cloud.progress === "number" ? cloud.progress : typeof data.progress === "number" ? data.progress : undefined;
  const stage = cloudActive ? (CLOUD_STAGE[String(cloud.stage || "rendering")] || String(cloud.stage)) : String(data.stage || (state === "transcribing" ? "دارم متن صدا را درمی‌آورم" : data.style === "render" ? "ارسال پروژه به سرور ابری" : "در صف موتور")).replace(/\s*\(.*\)\s*$/, "");
  const video = done && data.attachment_id && conversationId ? api.studioAttachmentUrl(conversationId, String(data.attachment_id)) : undefined;
  const title = done ? "ویدیو آماده است" : failed ? (data.error === "stopped" ? "ساخت متوقف شد" : "ساخت ویدیو کامل نشد") : cloudActive ? "در حال رندر ویدیو" : "در حال ساخت ویدیو";
  const phase = done ? "done" : failed ? "failed" : cloudActive ? "rendering" : "queued";

  return <article className="render-card" data-phase={phase} aria-label={title} dir="rtl">
    <header className="rc-head">
      <h3>{title} <small style={{ color: "var(--text-3)", fontWeight: 400 }}>· {STYLE_NAME[String(data.style)] || "موتور استودیو"}</small></h3>
      {done && data.duration ? <span className="badge" data-tone="success"><i/>{Number(data.duration).toLocaleString("fa-IR", { maximumFractionDigits: 1 })} ثانیه</span>
        : busy && elapsed >= 1000 ? <span className="rc-elapsed">{formatDuration(elapsed)}</span> : null}
    </header>

    <div className="rc-frame">
      {video ? <AuthenticatedMedia as="video" controls playsInline preload="metadata" src={video} className="rc-video"/> : <>
        {sourceUrl ? <AuthenticatedMedia as="video" muted playsInline preload="metadata" src={sourceUrl} className="rc-backdrop" aria-hidden="true" tabIndex={-1}/>
          : <div className="rc-backdrop" aria-hidden="true" style={{ background: "#141416" }}/>}
        <div className="rc-overlay">
          {failed ? <Icon name="alert" size={28}/> : <span className="spinner rc-spinner" aria-hidden="true"/>}
          <strong>{failed ? (data.error === "stopped" ? "متوقف شد" : "خطا") : stage}</strong>
          {failed && data.error && data.error !== "stopped" ? <p dir="auto" className="bidi wrap-safe">موتور نتوانست کار را تمام کند؛ ایجنت راه دیگری را امتحان می‌کند.</p> : null}
          {busy && typeof percent === "number" ? <span className="rc-pct" aria-hidden="true">{percent}%</span> : null}
        </div>
      </>}
    </div>

    {busy ? <div className="rc-progress" role="status">
      <div className="meter" data-indeterminate={typeof percent === "number" ? undefined : ""} style={{ ["--value" as string]: `${percent ?? 0}%` }}
        role="progressbar" aria-label="پیشرفت ساخت" aria-valuemin={0} aria-valuemax={100} aria-valuenow={typeof percent === "number" ? percent : undefined}/>
      <div className="rc-meta"><span>{stage}</span>{typeof percent === "number" ? <span dir="auto">{cloudActive ? "رندر ابری: " : "کل کار: "}<bdi dir="ltr">{percent}%</bdi></span> : null}</div>
      {cloudActive && cloud.detail ? <p className="rc-detail" dir="auto">{cloud.detail}</p> : null}
      {cloudActive && data.style !== "render" && typeof data.progress === "number" ? <p className="ws-hint" dir="rtl">کل کار موتور: {data.progress}٪</p> : null}
    </div> : null}

    {video ? <div className="rc-actions">
      <button className="btn btn-sm" onClick={() => void api.downloadAuthenticated(video, `editorgpt-pro-${data.job_id || "video"}.mp4`)}><Icon name="download" size={15}/>دانلود</button>
    </div> : null}
  </article>;
}
