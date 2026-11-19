import React from "react";
import {api, type CreativeResource} from "../api";
import type {ResourceChange} from "./types";
import {friendlyError} from "../ui";

export function canApplyResource(item: CreativeResource) {
  return item.provider === "editorgpt-existing" && item.engine === "mlt" &&
    item.availability === "existing-pipeline" && item.contexts.includes("edit-plan") &&
    (item.type === "effect" || item.type === "transition");
}

type Context = Awaited<ReturnType<typeof api.planCreativeResources>>;

export function ResourceApply({job, projectId, item, onClose, onSaved}: {
  job: string; projectId: string; item: CreativeResource; onClose: () => void; onSaved: () => Promise<unknown>;
}) {
  const dialog = React.useRef<HTMLElement>(null);
  const [context, setContext] = React.useState<Context | null>(null);
  const [selected, setSelected] = React.useState<string[]>([]);
  const [settings, setSettings] = React.useState<Required<ResourceChange["settings"]>>({
    duration_frames: 6, direction: "left", intensity: 1, zoom_mode: "zoom_in", zoom_scale: 1.15,
  });
  const frames = settings.duration_frames;
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const segments: {id: string}[] = context?.plan.segments ?? [];
  const transition = item.type === "transition";
  const directional = item.id === "editorgpt-transition:directional";
  const zoom = item.id === "editorgpt-transition:zoom";
  const hardCut = item.id === "editorgpt-transition:hard_cut";
  const targets = transition ? segments.slice(0, -1) : segments;
  const available = transition ? context?.transitions : context?.effects;
  const supported = available?.some(entry => entry.id === item.id);

  React.useEffect(() => {
    const abort = new AbortController();
    dialog.current?.focus();
    api.planCreativeResources(job, abort.signal).then(result => {
      if (!abort.signal.aborted) setContext(result);
    }).catch(e => {
      if (!abort.signal.aborted) setError(friendlyError(e, "load timeline targets"));
    });
    return () => abort.abort();
  }, [job]);

  async function apply() {
    if (!context || !supported || !selected.length || busy) return;
    setBusy(true);
    setError("");
    try {
      await api.applyPanelResource(projectId, {version: context.version, kind: transition ? "transition" : "effect",
        resource_id: item.id, targets: selected, settings: {...settings, duration_frames: hardCut ? 0 : frames}});
    } catch (e) {
      setError(friendlyError(e, "apply this resource"));
      setBusy(false);
      return;
    }
    await onSaved();
  }

  return <section ref={dialog} tabIndex={-1} className="mp-resource-apply mp-inspector" aria-label="اعمال منبع">
    <div className="mp-section-head">
      <h2 dir="auto">{item.name}</h2>
      <button className="btn btn-secondary btn-sm" disabled={busy} onClick={onClose}>بستن</button>
    </div>
    {!context && !error && <p role="status">در حال خواندن تایم‌لاین…</p>}
    {context && (!supported || !targets.length) && <p role="status">{supported
      ? "برای ترنزیشن حداقل دو قطعه لازم است." : "این منبع برای برنامهٔ فعلی قابل اعمال نیست."}</p>}
    {supported && targets.length > 0 && <fieldset className="mp-reset" disabled={busy}>
      <legend>{transition ? "اتصال‌های هدف" : "قطعه‌های هدف"}</legend>
      <button className="btn btn-secondary btn-sm" onClick={() => setSelected(selected.length === targets.length ? [] : targets.map(s => s.id))}>
        {selected.length === targets.length ? "لغو انتخاب" : "انتخاب همه"}
      </button>
      <div className="mp-resource-targets">
        {targets.map(({id}, i) => <label className="mp-check" key={id}>
          <input type="checkbox" checked={selected.includes(id)} onChange={event => {
            setSelected(old => event.target.checked ? [...old, id] : old.filter(value => value !== id));
          }}/>{transition ? `قطعهٔ ${i + 1} به ${i + 2}` : `قطعهٔ ${i + 1}`}
        </label>)}
      </div>
      {transition && !hardCut && <label>مدت هم‌پوشانی · {frames} فریم
        <input type="range" min={2} max={30} value={frames} onChange={event => setSettings({...settings, duration_frames: Number(event.target.value)})}/>
      </label>}
      {directional && <div className="mp-form-grid">
        <label>جهت حرکت<select className="input" value={settings.direction} onChange={event =>
          setSettings({...settings, direction: event.target.value as typeof settings.direction})}>
          <option value="left">چپ</option><option value="right">راست</option><option value="up">بالا</option><option value="down">پایین</option>
        </select></label>
        <label>شدت · {settings.intensity.toFixed(2)}<input type="range" min={.5} max={1} step={.05} value={settings.intensity}
          onChange={event => setSettings({...settings, intensity: Number(event.target.value)})}/></label>
      </div>}
      {zoom && <div className="mp-form-grid">
        <label>مسیر زوم<select className="input" value={settings.zoom_mode} onChange={event =>
          setSettings({...settings, zoom_mode: event.target.value as typeof settings.zoom_mode})}>
          <option value="zoom_in">نزدیک‌شدن</option><option value="zoom_out">دورشدن</option>
        </select></label>
        <label>ضریب زوم · {settings.zoom_scale.toFixed(2)}<input type="range" min={1.02} max={1.5} step={.01} value={settings.zoom_scale}
          onChange={event => setSettings({...settings, zoom_scale: Number(event.target.value)})}/></label>
      </div>}
      <button className="btn btn-primary" disabled={!selected.length} onClick={() => void apply()}>
        {busy ? "در حال ثبت…" : "اعمال به تایم‌لاین"}
      </button>
    </fieldset>}
    {error && <p className="notice" data-tone="error" role="alert">{error}</p>}
  </section>;
}
