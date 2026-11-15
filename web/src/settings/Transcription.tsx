import React from "react";
import { api, TranscriptionPrefs } from "../api";
import { friendlyError } from "../ui";

const ENGINES = [
  { id: "auto" as const, name: "خودکار", hint: "ویدیوهای ۱۵ دقیقه یا بیشتر روی سرور با Whisper شنیده و بعد با یک مدل بررسی می‌شوند؛ کوتاه‌ترها با ElevenLabs." },
  { id: "elevenlabs" as const, name: "ElevenLabs", hint: "بهترین دقت برای فارسی و سریع، حتی برای ساعت‌ها صدا. پرداخت بر اساس ساعتِ صدا." },
  { id: "whisper" as const, name: "Whisper روی سرور", hint: "رایگان. کندتر و برای فارسی کم‌دقت‌تر؛ سرور مشترک است و ویدیوی طولانی ممکن است ساعت‌ها طول بکشد." },
];
const MODELS = [
  { id: "", name: "انتخاب خودکار برای هر ویدیو" }, { id: "base", name: "base · سریع‌ترین، خام‌ترین" }, { id: "small", name: "small · متعادل" },
  { id: "medium", name: "medium · بهتر، کند" }, { id: "large-v3", name: "large-v3 · بهترین، بسیار کند" },
];

/** Which speech-to-text hears the person's videos. Works in online mode (the server does the work). */
export function TranscriptionSettings() {
  const [prefs, setPrefs] = React.useState<TranscriptionPrefs | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState("");
  React.useEffect(() => {
    let live = true;
    api.transcriptionPreferences().then(value => { if (live) setPrefs(value); }).catch(e => { if (live) setError(friendlyError(e, "load the transcription settings")); });
    return () => { live = false; };
  }, []);
  async function save(engine: TranscriptionPrefs["engine"], whisper_model: string) {
    setSaving(true); setError("");
    try { setPrefs(await api.saveTranscriptionPreferences(engine, whisper_model)); }
    catch (e) { setError(friendlyError(e, "save the transcription setting")); }
    finally { setSaving(false); }
  }
  const rate = prefs?.elevenlabs_usd_per_hour ?? 0.4;
  const fifty = (50 / 60 * rate).toFixed(2);
  return <section className="set-section" aria-labelledby="set-transcribe" dir="rtl">
    <h2 id="set-transcribe">پیاده‌سازی متن گفتار</h2>
    <p className="set-hint">گفتار ویدیوهای شما چگونه به متن تبدیل شود. وقتی پردازش آنلاین و روی سرور انجام می‌شود اعمال می‌شود.</p>
    <div className="set-controls">
      <div className="set-choices" role="radiogroup" aria-label="موتور پیاده‌سازی">
        {ENGINES.map(item => <label key={item.id} className="set-choice" data-selected={prefs?.engine === item.id || undefined}>
          <input type="radio" name="transcribe-engine" checked={prefs?.engine === item.id} disabled={!prefs || saving} onChange={() => void save(item.id, prefs?.whisper_model || "")}/>
          <span><b>{item.name}</b><small>{item.hint}</small></span></label>)}
      </div>
      <p className="set-control-note">هزینه‌ی ElevenLabs حدود ${rate.toFixed(2)} برای هر ساعت صدا است؛ یک ویدیوی ۵۰ دقیقه‌ای حدود ${fifty}.</p>
      {prefs && prefs.engine !== "elevenlabs" ? <div className="set-control"><label htmlFor="whisper-model"><b>مدل Whisper</b><small>مدل بزرگ‌تر فارسی را بهتر می‌خواند ولی روی این سرور خیلی کندتر است.</small></label>
        <select id="whisper-model" className="input" aria-label="مدل Whisper" value={prefs.whisper_model} disabled={saving} onChange={event => void save(prefs.engine, event.target.value)}>
          {MODELS.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></div> : null}
    </div>
    {error ? <p className="notice" data-tone="error" role="alert">{error}</p> : null}
  </section>;
}
