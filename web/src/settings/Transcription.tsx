import React from "react";
import { api, TranscriptionPrefs } from "../api";
import { friendlyError } from "../ui";

const ENGINES = [
  { id: "auto" as const, name: "Automatic", hint: "Videos of 15 minutes or more are heard by Whisper on the server and then checked by a model; shorter ones use ElevenLabs." },
  { id: "elevenlabs" as const, name: "ElevenLabs", hint: "Best Persian accuracy and fast, even for hours of audio. Paid by the hour of audio." },
  { id: "whisper" as const, name: "Whisper on the server", hint: "Free. Slower, and less accurate in Persian; the server is shared, so a long video can take hours." },
];
const MODELS = [
  { id: "", name: "Chosen for the video" }, { id: "base", name: "base · fastest, roughest" }, { id: "small", name: "small · balanced" },
  { id: "medium", name: "medium · better, slow" }, { id: "large-v3", name: "large-v3 · best, very slow" },
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
  return <section className="set-section" aria-labelledby="set-transcribe">
    <h2 id="set-transcribe">Transcription</h2>
    <p className="set-hint">How the speech in your videos is turned into text. This applies when processing runs online, on the server.</p>
    <div className="set-row" style={{ alignItems: "start" }}><span><b>Engine</b><small>ElevenLabs costs about ${rate.toFixed(2)} per hour of audio: a 50-minute video is about ${fifty}.</small></span>
      <div style={{ display: "grid", gap: 8, minWidth: 0 }} role="radiogroup" aria-label="Transcription engine">
        {ENGINES.map(item => <label key={item.id} className="set-choice" style={{ display: "flex", gap: 10, alignItems: "start", cursor: "pointer" }}>
          <input type="radio" name="transcribe-engine" checked={prefs?.engine === item.id} disabled={!prefs || saving} onChange={() => void save(item.id, prefs?.whisper_model || "")}/>
          <span><b>{item.name}</b><small style={{ display: "block" }}>{item.hint}</small></span></label>)}
      </div></div>
    {prefs && prefs.engine !== "elevenlabs" ? <div className="set-row"><span><b>Whisper model</b><small>Bigger models read Persian better but are much slower on this server.</small></span>
      <select className="input" aria-label="Whisper model" value={prefs.whisper_model} disabled={saving} onChange={event => void save(prefs.engine, event.target.value)}>
        {MODELS.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></div> : null}
    {error ? <p className="notice" data-tone="error" role="alert">{error}</p> : null}
  </section>;
}
