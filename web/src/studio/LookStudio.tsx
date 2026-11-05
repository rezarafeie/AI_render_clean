import React from "react";
import { api } from "../api";
import { AuthenticatedMedia } from "../AuthenticatedMedia";
import { EditSwitch } from "./EditCard";

export interface LookValues {
  brightness: number; contrast: number; saturation: number; temperature: number;
  gradeAuto: boolean; framingAuto: boolean; shiftX: number; shiftY: number;
  zoomEnabled: boolean; zoomBase: number; zoomClose: number; zoomAmount: number;
}
export type LookPatch = Partial<{
  brightness: number; contrast: number; saturation: number; temperature: number; grade_auto: boolean; framing_auto: boolean;
  shift_x: number; shift_y: number; zoom_enabled: boolean; zoom_base: number; zoom_close: number; zoom: number;
}>;
type Controls = { values: LookValues; disabled: boolean; onChange: (patch: LookPatch) => void };

const DEFAULTS = { brightness: 0, contrast: 100, saturation: 100, temperature: 0 };

function slider(disabled: boolean, id: string, label: string, min: number, max: number, step: number, current: number, send: (v: number) => void, suffix = "") {
  return <div className="field" key={id}><label htmlFor={`look-${id}`}>{label}: <b>{current}{suffix}</b></label>
    <input id={`look-${id}`} type="range" min={min} max={max} step={step} value={current} disabled={disabled} onChange={event => send(Number(event.target.value))}/></div>;
}

/** The footage with the person's own light, colour, frame and zoom drawn on it while they move a slider (the renderer's maths, in CSS). It stays on screen
 *  while a tool's controls are open, like the preview of a phone editor. */
export function LookStage({ jobId, values, close }: { jobId: string; values: LookValues; close: boolean }) {
  const moved = values.shiftX !== 0 || values.shiftY !== 0;
  const base = values.zoomEnabled ? (close ? values.zoomClose : values.zoomBase) / 100 : 1;
  const scale = Math.max(base, moved ? 1.12 : 1);
  const tx = -(values.shiftX / 100) * (scale - 1) / 2 * 100;
  const ty = -(values.shiftY / 100) * (scale - 1) / 2 * 100;
  const filter = `brightness(${100 + values.brightness * 1.4}%) contrast(${values.contrast}%) saturate(${values.saturation}%)`;
  return <div className="look-stage-wrap">
    <div className="look-stage" aria-label="پیش‌نمایش زندهٔ تغییرات">
      <AuthenticatedMedia as="video" src={api.rawUrl(jobId)} controls muted playsInline preload="metadata"
        style={{ width: "100%", height: "100%", objectFit: "cover", filter, transform: `translate(${tx}%, ${ty}%) scale(${scale})`, transition: "transform .12s" }}/>
      {values.temperature !== 0 ? <div aria-hidden className="look-tint" style={{ background: values.temperature > 0 ? "#ff8a3d" : "#4b8dff", opacity: Math.abs(values.temperature) / 160 }}/> : null}
    </div>
  </div>;
}

export function LightControls({ values, disabled, onChange }: Controls) {
  return <div className="look-panel">
    <EditSwitch label="تصحیح خودکار نور و رنگ" hint="نور کم یا رنگ زرد و آبی فیلم را از روی خودش اندازه می‌گیرد و ملایم درست می‌کند؛ هنگام رندر اعمال می‌شود و در پیش‌نمایش بالا نیست." disabled={disabled} checked={values.gradeAuto} onChange={checked => onChange({ grade_auto: checked })}/>
    {slider(disabled, "brightness", "روشنایی", -30, 30, 1, values.brightness, v => onChange({ brightness: v }))}
    {slider(disabled, "contrast", "کنتراست", 50, 160, 1, values.contrast, v => onChange({ contrast: v }), "٪")}
    {slider(disabled, "saturation", "اشباع رنگ", 0, 180, 1, values.saturation, v => onChange({ saturation: v }), "٪")}
    {slider(disabled, "temperature", "گرمی رنگ", -50, 50, 1, values.temperature, v => onChange({ temperature: v }))}
    <button type="button" className="btn btn-sm" disabled={disabled} onClick={() => onChange(DEFAULTS)}>برگرداندن نور و رنگ</button>
  </div>;
}

export function FrameControls({ values, disabled, onChange }: Controls) {
  return <div className="look-panel">
    <EditSwitch label="کادربندی خودکار روی چهره" hint="گوینده‌ای که به یک سمت قاب رفته به وسط برمی‌گردد و بالای سرش جا می‌ماند؛ هنگام رندر اعمال می‌شود." disabled={disabled} checked={values.framingAuto} onChange={checked => onChange({ framing_auto: checked })}/>
    {slider(disabled, "shiftx", "جابه‌جایی چپ ↔ راست", -100, 100, 5, values.shiftX, v => onChange({ shift_x: v }))}
    {slider(disabled, "shifty", "جابه‌جایی بالا ↔ پایین", -100, 100, 5, values.shiftY, v => onChange({ shift_y: v }))}
    <button type="button" className="btn btn-sm" disabled={disabled} onClick={() => onChange({ shift_x: 0, shift_y: 0 })}>وسط‌چین</button>
  </div>;
}

export function ZoomControls({ values, disabled, onChange, close, setClose }: Controls & { close: boolean; setClose: (value: boolean) => void }) {
  return <div className="look-panel">
    <EditSwitch label="زوم‌های دوربین روی گوینده" disabled={disabled} checked={values.zoomEnabled} onChange={checked => onChange({ zoom_enabled: checked })}/>
    {values.zoomEnabled ? <>
      <div className="segmented" role="group" aria-label="نمای پیش‌نمایش">
        <button type="button" aria-pressed={!close} onClick={() => setClose(false)}>قاب اصلی</button>
        <button type="button" aria-pressed={close} onClick={() => setClose(true)}>قاب نزدیک</button></div>
      {slider(disabled, "zbase", "زوم قاب اصلی", 100, 180, 5, values.zoomBase, v => onChange({ zoom_base: v }), "٪")}
      {slider(disabled, "zclose", "زوم قاب نزدیک", 100, 220, 5, values.zoomClose, v => onChange({ zoom_close: v }), "٪")}
      {slider(disabled, "zamount", "حرکت آهستهٔ نزدیک‌شدن", 0, 200, 10, values.zoomAmount, v => onChange({ zoom: v }), "٪")}</> : null}
  </div>;
}
