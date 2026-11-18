import React from "react";
import {api, type LibraryAsset} from "../api";
import {AuthenticatedMedia} from "../AuthenticatedMedia";
import {friendlyError} from "../ui";
import type {LayerKind, NativeTimeline, LayerChange} from "./types";

const labels: Record<LayerKind, string> = {caption: "متن و زیرنویس", broll: "بی‌رول", music: "موسیقی", sfx: "افکت صوتی"};
type Layer = NativeTimeline["layers"][number];
type Draft = {kind: LayerKind; index?: number; text: string; filename: string; start: string; end: string; volume: number; position: "top" | "bottom"};
const empty = (kind: LayerKind, duration: number): Draft => ({kind, text: "", filename: "", start: "0",
  end: String(Math.min(duration, 3)), volume: kind === "sfx" ? -6 : -14, position: "bottom"});

export function NativeLayers({data, blocked, width, cursor, onChange, children}: {
  data: NativeTimeline; blocked: boolean; width: number; cursor: number; onChange: (edit: LayerChange) => Promise<boolean>; children: React.ReactNode;
}) {
  const [open, setOpen] = React.useState(false);
  const [draft, setDraft] = React.useState(() => empty("caption", data.duration));
  const [assets, setAssets] = React.useState<LibraryAsset[] | null>(null);
  const [error, setError] = React.useState("");
  const [preview, setPreview] = React.useState(false);

  React.useEffect(() => {
    if (!open || draft.kind === "caption" || assets) return;
    let live = true;
    api.getLibrary().then(value => { if (live) setAssets(value.assets); })
      .catch(e => { if (live) setError(friendlyError(e, "load media")); });
    return () => { live = false; };
  }, [open, draft.kind, assets]);

  function choose(layer: Layer) {
    setOpen(true);
    setPreview(false);
    setDraft({kind: layer.kind, index: layer.index, text: layer.kind === "caption" ? layer.label : "",
              filename: layer.kind === "caption" ? "" : layer.label, start: layer.start.toFixed(3), end: layer.end.toFixed(3),
              volume: layer.volume_db, position: layer.position});
  }

  async function apply() {
    const ok = await onChange({version: data.version, kind: draft.kind, operation: draft.index === undefined ? "add" : "replace", index: draft.index,
      text: draft.text, filename: draft.filename, start: Number(draft.start), end: Number(draft.end),
      position: draft.position, volume_db: draft.volume});
    if (ok) { setDraft(empty(draft.kind, data.duration)); setPreview(false); }
  }

  const selected = draft.index === undefined ? undefined : data.layers.find(layer => layer.kind === draft.kind && layer.index === draft.index);
  const filters = assets?.filter(asset => asset.category === draft.kind) ?? [];
  const mediaUrl = draft.kind !== "caption" && draft.filename ? api.libraryPreviewUrl(draft.kind, draft.filename) : "";
  const hasRange = draft.kind === "caption" || draft.kind === "broll";
  const hasVolume = draft.kind === "music" || draft.kind === "sfx";
  return <div className="mp-layer-tools">
    <div className="mp-native-scroll" dir="ltr">
      <div className="mp-lanes" style={{width}}>
        {children}
        {(Object.keys(labels) as LayerKind[]).map(kind => {
          const layers = data.layers.filter(layer => layer.kind === kind);
          if (!layers.length) return null;
          return <div key={kind} className="mp-lane">
            <span className="mp-lane-label" dir="rtl">{labels[kind]}</span>
            <div className="mp-native-track" aria-label={labels[kind]}>
              {layers.map(layer => <button type="button" key={layer.index}
                aria-pressed={selected === layer} aria-label={layer.label} title={layer.label}
                style={{left: `${layer.start / data.duration * 100}%`,
                        width: `${Math.max(0, layer.end - layer.start) / data.duration * 100}%`}}
                onClick={() => choose(layer)}><span dir="auto">{layer.label}</span></button>)}
              <span className="mp-playhead" aria-hidden="true" style={{left: `${cursor / data.duration * 100}%`}}/>
            </div>
          </div>;
        })}
      </div>
    </div>
    <div className="mp-chips">
      <button type="button" className="btn btn-secondary btn-sm" aria-expanded={open} onClick={() => {
        setOpen(v => !v);
        if (!open) setDraft(empty("caption", data.duration));
      }}>{open ? "بستن ابزار لایه" : "افزودن لایه"}</button>
    </div>
    {open && <fieldset className="mp-reset" disabled={blocked}>
      <legend>{selected ? "ویرایش لایه" : "لایهٔ جدید"}</legend>
      <label>نوع لایه<select className="input" value={draft.kind} onChange={e => {
        setDraft(empty(e.target.value as LayerKind, data.duration)); setPreview(false); setError("");
      }}>{Object.entries(labels).map(([kind, name]) => <option key={kind} value={kind}>{name}</option>)}</select></label>
      {draft.kind === "caption" ? <>
        <label>متن<input className="input" maxLength={400} value={draft.text} onChange={e => setDraft({...draft, text: e.target.value})}/></label>
        <label>موقعیت<select className="input" value={draft.position} onChange={e => setDraft({...draft, position: e.target.value as Draft["position"]})}>
          <option value="bottom">پایین</option><option value="top">بالا</option>
        </select></label>
      </> : <>
        <label>فایل کتابخانه<select className="input" value={draft.filename} onChange={e => {setDraft({...draft, filename: e.target.value}); setPreview(false);}}>
          <option value="">انتخاب فایل</option>
          {draft.filename && !filters.some(asset => asset.filename === draft.filename) && <option value={draft.filename}>{draft.filename}</option>}
          {filters.map(asset => <option key={asset.filename} value={asset.filename}>{asset.filename}</option>)}
        </select></label>
        {mediaUrl && <button className="btn btn-secondary btn-sm" onClick={() => setPreview(v => !v)}>{preview ? "بستن پیش‌نمایش" : "پیش‌نمایش فایل"}</button>}
        {preview && mediaUrl && <AuthenticatedMedia as={draft.kind === "broll" ? "video" : "audio"} src={mediaUrl} controls playsInline preload="none"/>}
      </>}
      {draft.kind !== "music" && <div className="mp-form-grid">
        <label>شروع در خروجی (ثانیه)<input className="input" type="number" min={0} max={data.duration} step={1 / data.fps} value={draft.start}
          onChange={e => setDraft({...draft, start: e.target.value})}/></label>
        {hasRange && <label>پایان در خروجی (ثانیه)<input className="input" type="number" min={0} max={data.duration} step={1 / data.fps} value={draft.end}
          onChange={e => setDraft({...draft, end: e.target.value})}/></label>}
      </div>}
      {hasVolume && <label>بلندی صدا ({draft.volume} dB)<input type="range" min={-60} max={6} value={draft.volume}
        onChange={e => setDraft({...draft, volume: Number(e.target.value)})}/></label>}
      <div className="mp-actions">
        <button className="btn btn-primary" disabled={(draft.kind === "caption" ? !draft.text.trim() : !draft.filename) ||
          (hasRange && Number(draft.end) <= Number(draft.start))} onClick={() => void apply()}>{selected ? "ذخیرهٔ لایه" : "افزودن"}</button>
        {selected && <button className="btn btn-secondary" onClick={() => {
          void onChange({version: data.version, kind: selected.kind, index: selected.index, operation: "remove"}).then(ok => {
            if (ok) { setDraft(empty(draft.kind, data.duration)); setPreview(false); }
          });
        }}>برداشتن لایه</button>}
      </div>
    </fieldset>}
    {error && <p className="notice" role="alert" data-tone="error">{error}</p>}
  </div>;
}
