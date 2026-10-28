import React from "react";
import { api, TalkingReelSummary } from "./api";
import { TalkingReelCard } from "./TalkingReel";
import { friendlyError, notify } from "./ui";

const STATUS: Record<string, string> = { needs_review: "نیازمند بررسی خروجی", idle: "آماده‌ی تحلیل", running: "در حال تحلیل یا ساخت", ready: "آماده‌ی بازبینی", done: "آماده", error: "خطا" };

/** Talking-head videos: upload a podcast clip, get a styled vertical reel. */
export default function TalkingReels() {
  const [items, setItems] = React.useState<TalkingReelSummary[]>([]);
  const [selected, setSelected] = React.useState<string | null>(null);
  const [file, setFile] = React.useState<File | null>(null);
  const [progress, setProgress] = React.useState<number | null>(null);
  const [error, setError] = React.useState("");

  const refresh = React.useCallback(async () => {
    try {
      const list = await api.listTalkingReels();
      setItems(list);
      setSelected(s => s ?? list[0]?.job_id ?? null);
    } catch (err) { setError(friendlyError(err, "load talking videos")); }
  }, []);
  React.useEffect(() => { void refresh(); }, [refresh]);

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) { setError("یک ویدیو انتخاب کنید."); return; }
    setError("");
    setProgress(0);
    try {
      const { job } = await api.createJob(file, undefined, setProgress);
      await api.analyzeTalkingReel(job.id);
      notify("تحلیل ویدیو شروع شد؛ قبل از رندر تنظیمات را بازبینی کن");
      setFile(null);
      setSelected(job.id);
      await refresh();
    } catch (err) { setError(friendlyError(err, "upload the video")); }
    finally { setProgress(null); }
  }

  return (
    <div dir="rtl">
      <h1>ویدیو صحبتی</h1>
      <p className="muted">ویدیو را آپلود کن؛ سیستم ابتدا متن را درمی‌آورد، بهترین استایل را پیشنهاد می‌دهد و هوک و زیرنویس‌ها را برای بازبینی آماده می‌کند. رندر فقط بعد از تأیید تو شروع می‌شود.</p>
      <form className="card row" onSubmit={upload}>
        <input type="file" accept="video/*" onChange={e => setFile(e.target.files?.[0] || null)} disabled={progress !== null} />
        <button type="submit" disabled={!file || progress !== null}>
          {progress !== null ? `در حال آپلود ${progress}%` : "آپلود و تحلیل ویدیو"}
        </button>
      </form>
      {error && <div className="errors">{error}</div>}
      {items.length > 0 && (
        <div className="card">
          <h2>ویدیوهای صحبتی</h2>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {items.map(item => (
              <button key={item.job_id} className={item.job_id === selected ? "" : "btn-secondary"} onClick={() => setSelected(item.job_id)}>
                {item.name || item.job_id} — {STATUS[item.status] || item.status}
              </button>
            ))}
          </div>
        </div>
      )}
      {selected && <TalkingReelCard key={selected} jobId={selected} onChanged={() => { void refresh(); }} />}
    </div>
  );
}
