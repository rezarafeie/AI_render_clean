import React from "react";
import { api } from "../api";
import { friendlyError } from "../ui";

type Voice = { id: string; name: string; note: string; clone?: boolean };
const READING = "سلام، من دارم برای ساخت صدای دیجیتال خودم صحبت می‌کنم. امروز هوا خوب است و من دوست دارم با آرامش و طبیعی بخوانم، بدون عجله و بدون مکث‌های طولانی. "
  + "صدای من باید در ویدیوها هم همین‌قدر روشن و گرم شنیده شود؛ پس هر جمله را کامل می‌گویم، گاهی تند و گاهی آهسته، همان‌طور که در یک گفتگوی دوستانه حرف می‌زنم. "
  + "اگر سؤالی بپرسم، لحنم کمی بالا می‌رود؛ و اگر خبر خوبی بدهم، با انرژی بیشتری می‌خوانم. این متن را تا آخر ادامه می‌دهم تا صدایم به‌خوبی ثبت شود.";
const MIN_RECORD = 30;

const SAMPLE = "سلام! این یک آزمایش کوتاه است تا ببینم صدای من در ویدیوها چطور شنیده می‌شود.";

/** One cloned voice: its name (editable), a text of the person's own to hear it read, and removal. */
function VoiceRow({ voice, onChange, onError }: { voice: Voice; onChange: () => void; onError: (message: string) => void }) {
  const [name, setName] = React.useState(voice.name);
  const [editing, setEditing] = React.useState(false);
  const [text, setText] = React.useState(SAMPLE);
  const [busy, setBusy] = React.useState(false);
  const [audio, setAudio] = React.useState("");
  React.useEffect(() => { setName(voice.name); }, [voice.name]);
  React.useEffect(() => () => { if (audio) URL.revokeObjectURL(audio); }, [audio]);
  async function save() {
    if (!name.trim() || name.trim() === voice.name) { setEditing(false); setName(voice.name); return; }
    try { await api.renameVoice(voice.id, name.trim()); setEditing(false); onChange(); } catch (e) { onError(friendlyError(e, "rename the voice")); }
  }
  async function play() {
    setBusy(true); onError("");
    try { setAudio(await api.previewVoice(voice.id, text)); } catch (e) { onError(e instanceof Error ? e.message : "ساخت صدای آزمایشی ناموفق بود"); } finally { setBusy(false); }
  }
  return <li className="set-voice">
    <div className="set-row">
      {editing ? <><input className="input" dir="auto" value={name} maxLength={40} autoFocus onChange={e => setName(e.target.value)} onKeyDown={e => { if (e.key === "Enter") void save(); if (e.key === "Escape") { setEditing(false); setName(voice.name); } }}/>
        <button type="button" className="btn btn-sm" onClick={() => void save()}>ذخیره</button></>
        : <><b dir="auto">{voice.name}</b><button type="button" className="btn btn-sm btn-ghost" onClick={() => setEditing(true)}>تغییر نام</button></>}
      <button type="button" className="btn btn-sm btn-ghost" onClick={() => { if (window.confirm(`صدای «${voice.name}» از برنامه حذف شود؟ برای آزادشدن جا در حساب ElevenLabs، همین صدا را در پنل ElevenLabs هم پاک کنید.`)) void api.deleteVoice(voice.id).then(onChange).catch(e => onError(friendlyError(e, "delete the voice"))); }}>حذف</button>
    </div>
    <label className="set-field">متن آزمایشی (حداکثر ۴۰۰ نویسه)<textarea className="input" dir="auto" rows={2} maxLength={400} value={text} onChange={e => setText(e.target.value)}/></label>
    <div className="set-actions">
      <button type="button" className="btn btn-sm" disabled={busy || text.trim().length < 3} onClick={() => void play()}>{busy ? "در حال ساخت…" : "شنیدن صدا"}</button>
      {audio ? <audio controls autoPlay src={audio}/> : null}
    </div>
  </li>;
}

export function VoiceCloneSettings() {
  const [voices, setVoices] = React.useState<Voice[]>([]);
  const [mode, setMode] = React.useState<"record" | "file">("record");
  const [name, setName] = React.useState("");
  const [consent, setConsent] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [message, setMessage] = React.useState("");
  const [error, setError] = React.useState("");
  const [recording, setRecording] = React.useState(false);
  const [seconds, setSeconds] = React.useState(0);
  const [blob, setBlob] = React.useState<Blob | null>(null);
  const recorder = React.useRef<MediaRecorder | null>(null);
  const chunks = React.useRef<Blob[]>([]);
  const timer = React.useRef<number | undefined>(undefined);
  const reload = React.useCallback(() => { api.localizeVoices().then(r => setVoices(r.voices.filter(v => v.clone))).catch(() => undefined); }, []);
  React.useEffect(() => { reload(); return () => window.clearInterval(timer.current); }, [reload]);

  async function startRecording() {
    setError(""); setBlob(null); setSeconds(0);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: true, channelCount: 1 } });
      const media = new MediaRecorder(stream);
      chunks.current = [];
      media.ondataavailable = event => { if (event.data.size) chunks.current.push(event.data); };
      media.onstop = () => { stream.getTracks().forEach(track => track.stop()); setBlob(new Blob(chunks.current, { type: media.mimeType || "audio/webm" })); };
      media.start();
      recorder.current = media;
      setRecording(true);
      timer.current = window.setInterval(() => setSeconds(value => value + 1), 1000);
    } catch { setError("دسترسی به میکروفون ممکن نشد؛ اجازهٔ میکروفون را در مرورگر بدهید."); }
  }
  function stopRecording() { recorder.current?.stop(); window.clearInterval(timer.current); setRecording(false); }

  async function submit(file: Blob, filename: string, kind: "recording" | "file") {
    setBusy(true); setError(""); setMessage("در حال ارسال…");
    try {
      const { job } = await api.cloneVoice(file, filename, name.trim() || "صدای من", kind, percent => setMessage(`در حال ارسال… ${Math.round(percent)}٪`));
      for (;;) {
        await new Promise(resolve => window.setTimeout(resolve, 2500));
        const state = await api.cloneVoiceStatus(job);
        setMessage(state.message);
        if (state.status === "failed") { setError(state.error || "ساخت صدا ناموفق بود"); break; }
        if (state.status === "done") { setMessage(`صدای «${state.voice?.name}» ساخته شد و برای نریشن آماده است.`); setBlob(null); setName(""); reload(); break; }
      }
    } catch (e) { setError(friendlyError(e, "clone the voice")); } finally { setBusy(false); }
  }

  const ready = consent && !busy && !recording;
  return <section className="set-section" aria-labelledby="set-clone" dir="rtl">
    <h2 id="set-clone">کلون صدا</h2>
    <p className="set-hint">صدای خودتان را بسازید و در نریشن ویدیوها استفاده کنید. فقط صدایی را کلون کنید که مال خودتان است یا اجازهٔ استفاده از آن را دارید.</p>
    {voices.length ? <ul className="set-list" aria-label="صداهای کلون‌شدهٔ شما">{voices.map(voice => <VoiceRow key={voice.id} voice={voice} onChange={reload} onError={setError}/>)}</ul> : null}
    <div className="chip-row" role="tablist">
      <button type="button" role="tab" className="chip" aria-pressed={mode === "record"} onClick={() => setMode("record")}>ضبط با میکروفون</button>
      <button type="button" role="tab" className="chip" aria-pressed={mode === "file"} onClick={() => setMode("file")}>از روی فایل (صدا یا ویدیو)</button>
    </div>
    <label className="set-field">نام صدا<input className="input" dir="auto" value={name} maxLength={40} onChange={e => setName(e.target.value)} placeholder="مثلاً: صدای من"/></label>
    {mode === "record" ? <>
      <p className="set-hint">این متن را با لحن طبیعی بخوانید؛ دست‌کم {MIN_RECORD} ثانیه، بدون موسیقی و در جای ساکت.</p>
      <blockquote className="set-reading" dir="rtl">{READING}</blockquote>
      <div className="set-actions">
        {recording ? <button type="button" className="btn" onClick={stopRecording}>پایان ضبط · {seconds} ثانیه</button> : <button type="button" className="btn" disabled={busy} onClick={() => void startRecording()}>{blob ? "ضبط دوباره" : "شروع ضبط"}</button>}
        {blob && !recording ? <>
          <audio controls src={URL.createObjectURL(blob)} />
          <button type="button" className="btn" disabled={!ready || seconds < MIN_RECORD} onClick={() => void submit(blob, "recording.webm", "recording")}>ساخت صدا</button>
          {seconds < MIN_RECORD ? <span className="set-hint">ضبط شما {seconds} ثانیه است؛ دست‌کم {MIN_RECORD} ثانیه لازم است.</span> : null}
        </> : null}
      </div>
    </> : <>
      <p className="set-hint">فایل صدا یا ویدیو، از ۳۰ ثانیه تا ۲ ساعت. بهترین بخش گفتار تمیز خودکار انتخاب می‌شود؛ بهتر است فقط یک نفر صحبت کند و موسیقی نداشته باشد.</p>
      <input type="file" accept="audio/*,video/*" disabled={!ready} onChange={event => { const file = event.target.files?.[0]; if (file) void submit(file, file.name, "file"); event.target.value = ""; }} />
    </>}
    <label className="set-check"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)}/> تأیید می‌کنم این صدا مال خودم است یا اجازهٔ کلون‌کردن و استفاده از آن را دارم.</label>
    {message && !error ? <p className="set-hint" role="status">{message}</p> : null}
    {error ? <div className="notice" data-tone="error" role="alert">{error}</div> : null}
  </section>;
}
