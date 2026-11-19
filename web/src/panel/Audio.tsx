import React from "react";
import { api, type StudioProject, type MusicMix } from "../api";
import { AuthenticatedMedia } from "../AuthenticatedMedia";
import { friendlyError } from "../ui";
import { currentVersion, planPhase } from "../studio/plan";
import { LocalizeEdit } from "../studio/LocalizeEdit";

export function Audio({project, refresh}: {project: StudioProject; refresh: () => Promise<unknown>}) {
  if (project.engine === "localize" && project.external_ref) {
    return <LocalizeEdit id={project.external_ref} onChanged={() => void refresh()}/>;
  }
  if (project.engine === "talking") return <TalkingAudio project={project} refresh={refresh}/>;
  return <p className="mp-muted">صدای صحنه‌ها و انتخاب راوی در ابزار ویرایش استوری‌بورد همین پروژه قرار دارد.</p>;
}

function TalkingAudio({project, refresh}: {project: StudioProject; refresh: () => Promise<unknown>}) {
  const version = currentVersion(project);
  const [rows, setRows] = React.useState<Awaited<ReturnType<typeof api.panelMusic>>>([]);
  const [query, setQuery] = React.useState("");
  const [sample, setSample] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const audio = version?.content.audio;
  const phase = planPhase(project);
  const disabled = !version || busy || ["analyzing", "rendering"].includes(phase);

  React.useEffect(() => {
    let live = true;
    api.panelMusic().then(value => { if (live) setRows(value); }).catch(e => { if (live) setError(friendlyError(e, "load music")); });
    return () => { live = false; };
  }, []);

  async function apply(music: string) {
    if (!version || disabled) return;
    setBusy(true); setError("");
    try { await api.editStudioPlan(project.id, version.id, {music}); await refresh(); }
    catch (e) { setError(friendlyError(e, "apply music")); }
    finally { setBusy(false); }
  }
  async function mix(music_mix: MusicMix) {
    if (!version || disabled) return;
    setBusy(true); setError("");
    try { await api.editStudioPlan(project.id, version.id, {music_mix}); await refresh(); }
    catch (e) { setError(friendlyError(e, "save audio mix")); }
    finally { setBusy(false); }
  }

  return <section className="mp-inspector">
    <div className="mp-section-head"><h2>موسیقی و میکس</h2><button className="btn btn-secondary btn-sm" onClick={() => void apply("")}
      disabled={disabled || !audio?.music_path}>برداشتن موسیقی</button></div>
    <label>جستجوی موسیقی<input type="search" className="input" value={query} onChange={e => setQuery(e.target.value)}/></label>
    {audio?.music && <p>موسیقی فعلی: <strong dir="auto">{audio.music}</strong></p>}
    {audio?.mix && <Mix key={version?.id} value={audio.mix} onSave={mix} disabled={disabled}/>}
    {error && <p className="notice" data-tone="error" role="alert">{error}</p>}
    <div className="mp-gallery">{rows.filter(row => `${row.name || row.label || ""} ${row.path}`.toLowerCase().includes(query.toLowerCase())).map(row =>
      <article className="mp-asset" key={row.path}>
        <b dir="auto">{row.label || row.name || row.path.split("/").pop()}</b>
        {sample === row.path && <AuthenticatedMedia as="audio" src={api.studioMusicUrl(row.path)} controls autoPlay preload="none"/>}
        <div className="mp-actions">
          <button className="btn btn-secondary btn-sm" onClick={() => setSample(sample === row.path ? "" : row.path)}>{sample === row.path ? "بستن" : "شنیدن"}</button>
          <button className="btn btn-secondary btn-sm" disabled={disabled || audio?.music_path === row.path}
            onClick={() => void apply(row.path)}>{audio?.music_path === row.path ? "انتخاب‌شده" : "اعمال"}</button>
        </div>
      </article>)}</div>
  </section>;
}

function Mix({value, disabled, onSave}: {value: MusicMix; disabled: boolean; onSave: (mix: MusicMix) => Promise<void>}) {
  const [draft, setDraft] = React.useState<MusicMix>({volume_db: value.volume_db, fade_in: value.fade_in, fade_out: value.fade_out, duck: value.duck});
  return <fieldset className="mp-reset" disabled={disabled}>
    <legend>میکس موسیقی زیر گفتار</legend>
    <div className="mp-form-grid">
      <label>شدت موسیقی ({draft.volume_db} dB)<input type="range" min={-42} max={-8} value={draft.volume_db}
        onChange={e => setDraft({...draft, volume_db: Number(e.target.value)})}/></label>
      <label>ورود تدریجی<input type="number" className="input" min={0} max={6} step={0.25} value={draft.fade_in}
        onChange={e => setDraft({...draft, fade_in: Number(e.target.value)})}/></label>
      <label>خروج تدریجی<input type="number" className="input" min={0} max={6} step={0.25} value={draft.fade_out}
        onChange={e => setDraft({...draft, fade_out: Number(e.target.value)})}/></label>
    </div>
    <label className="mp-check"><input type="checkbox" checked={draft.duck} onChange={e => setDraft({...draft, duck: e.target.checked})}/>کم‌شدن موسیقی هنگام گفتار</label>
    <button className="btn btn-secondary" onClick={() => void onSave(draft)}>ذخیرهٔ میکس</button>
  </fieldset>;
}
