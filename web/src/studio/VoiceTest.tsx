import React from "react";
import { api } from "../api";
import { Icon } from "../components/Icon";
import AudioPlayer from "./AudioPlayer";

const SAMPLE = "سلام! این یک نمونهٔ کوتاه از صدای گوینده است تا قبل از ساخت ویدیو آن را بشنوید.";

/** Under a narrator picker: the person's own sample text read by the chosen narrator (ElevenLabs or Gemini) in the chosen delivery, to hear it before
 *  the film is voiced. Nothing is saved; each test spends a little of the provider's characters (at most 400). */
export default function VoiceTest({ voice, style = "", disabled = false }: { voice: string; style?: string; disabled?: boolean }) {
  const [text, setText] = React.useState(SAMPLE);
  const [busy, setBusy] = React.useState(false);
  const [url, setUrl] = React.useState("");
  const [error, setError] = React.useState("");
  React.useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);
  React.useEffect(() => { setUrl(""); setError(""); }, [voice, style]);
  const run = async () => {
    setBusy(true); setError("");
    try { setUrl(await api.previewVoice(voice, text.trim(), style)); }
    catch (e) { setError(e instanceof Error ? e.message : "ساخت صدای آزمایشی ناموفق بود"); }
    finally { setBusy(false); }
  };
  const gemini = voice.startsWith("gemini:");
  return <div className="voice-test field" data-wide>
    <label htmlFor="voice-test-text">تست صدا {voice ? <small className="field-hint">({gemini ? "Gemini" : "ElevenLabs"})</small> : null}</label>
    <div className="voice-test-row">
      <input id="voice-test-text" className="input bidi" dir="auto" maxLength={400} value={text} disabled={disabled || busy} onChange={e => setText(e.target.value)}/>
      <button type="button" className="btn btn-sm" disabled={disabled || busy || !voice || text.trim().length < 3} onClick={() => void run()}>
        <Icon name="mic2" size={15}/>{busy ? "در حال ساخت…" : "تست"}</button>
    </div>
    {!voice ? <small className="field-hint">برای تست، یک گوینده انتخاب کنید (پیش‌فرض استودیو تست نمی‌شود).</small> : null}
    {error ? <small className="field-hint" role="alert" data-tone="error">{error}</small> : null}
    {url ? <AudioPlayer src={url} authenticated={false} title="تست صدا" filename="voice-test.mp3"/> : null}
  </div>;
}
