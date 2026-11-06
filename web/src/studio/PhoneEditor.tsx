import React from "react";
import { AuthenticatedMedia } from "../AuthenticatedMedia";
import { Icon, type IconName } from "../components/Icon";
import type { LookPatch, LookValues } from "./LookStudio";

export type EditorTool = "light" | "frame" | "zoom" | "text" | "style" | "hook" | "brand" | "details" | "fx" | "moments";
const SLIDER_TOOLS: EditorTool[] = ["light", "frame", "zoom"];
type Param = { id: string; label: string; icon: IconName; min: number; max: number; step: number; value: number; suffix?: string; send: (v: number) => void; neutral: number };

/** Frames of the video taken in the page (a hidden copy is seeked to a handful of times), so the scrubber shows the picture instead of a bar. They are kept per video. */
const strips = new Map<string, string[]>();
function useFilmstrip(url: string, count = 10) {
  const [frames, setFrames] = React.useState<string[]>(() => strips.get(url) || []);
  React.useEffect(() => {
    if (!url) return;
    const kept = strips.get(url);
    if (kept) { setFrames(kept); return; }
    let live = true;
    const video = document.createElement("video");
    video.muted = true; video.playsInline = true; video.preload = "auto"; video.crossOrigin = "anonymous";
    const canvas = document.createElement("canvas");
    const out: string[] = [];
    const finish = () => { video.removeAttribute("src"); video.load(); };
    const grab = (n: number) => {
      if (!live) return finish();
      if (n >= count) { strips.set(url, out); setFrames(out); return finish(); }
      video.onseeked = () => {
        try {
          const h = 72, w = Math.max(1, Math.round(h * video.videoWidth / Math.max(video.videoHeight, 1)));
          canvas.width = w; canvas.height = h;
          canvas.getContext("2d")!.drawImage(video, 0, 0, w, h);
          out.push(canvas.toDataURL("image/jpeg", 0.6));
          grab(n + 1);
        } catch { finish(); }
      };
      video.currentTime = Math.min(video.duration - 0.05, (video.duration * (n + 0.5)) / count);
    };
    video.onloadedmetadata = () => { if (Number.isFinite(video.duration) && video.duration > 0) grab(0); else finish(); };
    video.onerror = finish;
    video.src = url;
    return () => { live = false; finish(); };
  }, [url]);
  return frames;
}

const clock = (seconds: number) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;

/** The Edit tab of a Talking reel laid out like a phone video editor: a big picture that follows every change, play / undo under it, a row of tools,
 *  and (after tapping one) a bottom sheet with a tick to confirm. Light, frame and zoom use one slider and a row of parameters; the other tools keep
 *  their forms, which the page passes in as children. */
export function PhoneEditor({ src, base, values, disabled, onChange, tools, open, setOpen, onUndo, canUndo, presets, trailing, children }: {
  /** the video shown, and the settings it was made with: when it is a finished render, only the change from them is drawn on it (null: the original footage, drawn from scratch) */
  src: string; base: LookValues | null; values: LookValues; disabled: boolean; onChange: (patch: LookPatch) => void;
  tools: [EditorTool, string, IconName][]; open: EditorTool | null; setOpen: (tool: EditorTool | null) => void;
  onUndo: () => void; canUndo: boolean; presets?: React.ReactNode; /** more tools that open somewhere else (a link), shown at the end of the row */ trailing?: React.ReactNode; children?: React.ReactNode;
}) {
  const video = React.useRef<HTMLVideoElement | null>(null);
  const [playing, setPlaying] = React.useState(false);
  const [time, setTime] = React.useState({ now: 0, total: 0 });
  const [playUrl, setPlayUrl] = React.useState("");
  const frames = useFilmstrip(playUrl);
  const [closeShot, setCloseShot] = React.useState(false);
  const [lightTab, setLightTab] = React.useState<"adjust" | "presets">("adjust");
  const [param, setParam] = React.useState<Record<string, string>>({ light: "brightness", frame: "shiftx", zoom: "zbase" });

  const look = (v: LookValues) => {
    const moved = v.shiftX !== 0 || v.shiftY !== 0;
    const zoom = v.zoomEnabled ? (closeShot ? v.zoomClose : v.zoomBase) / 100 : 1;
    const scale = Math.max(zoom, moved ? 1.12 : 1);
    return { scale, tx: -(v.shiftX / 100) * (scale - 1) / 2 * 100, ty: -(v.shiftY / 100) * (scale - 1) / 2 * 100 };
  };
  const now = look(values), was = base ? look(base) : { scale: 1, tx: 0, ty: 0 };
  const ref = base ?? { brightness: 0, contrast: 100, saturation: 100, temperature: 0 };
  const filter = `brightness(${(100 + values.brightness * 1.4) / (100 + ref.brightness * 1.4) * 100}%) contrast(${values.contrast / Math.max(ref.contrast, 1) * 100}%) saturate(${ref.saturation ? values.saturation / ref.saturation * 100 : values.saturation}%)`;
  const scale = now.scale / was.scale, tx = now.tx - was.tx, ty = now.ty - was.ty;
  const warmth = values.temperature - ref.temperature;

  const params: Record<string, Param[]> = {
    light: [
      { id: "brightness", label: "روشنایی", icon: "sun", min: -30, max: 30, step: 1, value: values.brightness, send: v => onChange({ brightness: v }), neutral: 0 },
      { id: "contrast", label: "کنتراست", icon: "contrast", min: 50, max: 160, step: 1, value: values.contrast, suffix: "٪", send: v => onChange({ contrast: v }), neutral: 100 },
      { id: "temperature", label: "گرمی", icon: "warmth", min: -50, max: 50, step: 1, value: values.temperature, send: v => onChange({ temperature: v }), neutral: 0 },
      { id: "saturation", label: "اشباع", icon: "drop", min: 0, max: 180, step: 1, value: values.saturation, suffix: "٪", send: v => onChange({ saturation: v }), neutral: 100 }],
    frame: [
      { id: "shiftx", label: "چپ و راست", icon: "moveH", min: -100, max: 100, step: 5, value: values.shiftX, send: v => onChange({ shift_x: v }), neutral: 0 },
      { id: "shifty", label: "بالا و پایین", icon: "moveV", min: -100, max: 100, step: 5, value: values.shiftY, send: v => onChange({ shift_y: v }), neutral: 0 }],
    zoom: [
      { id: "zbase", label: "قاب اصلی", icon: "search", min: 100, max: 180, step: 5, value: values.zoomBase, suffix: "٪", send: v => { setCloseShot(false); onChange({ zoom_base: v }); }, neutral: 100 },
      { id: "zclose", label: "قاب نزدیک", icon: "search", min: 100, max: 220, step: 5, value: values.zoomClose, suffix: "٪", send: v => { setCloseShot(true); onChange({ zoom_close: v }); }, neutral: 100 },
      { id: "zamount", label: "حرکت آهسته", icon: "motion", min: 0, max: 200, step: 10, value: values.zoomAmount, suffix: "٪", send: v => onChange({ zoom: v }), neutral: 100 }],
  };
  const sliderOpen = open && SLIDER_TOOLS.includes(open);
  const active = sliderOpen ? (params[open!].find(item => item.id === param[open!]) || params[open!][0]) : null;
  const title = tools.find(([id]) => id === open)?.[1] || "";

  return <div className="pe" dir="rtl">
    <div className="pe-top">
      <div className="pe-stage" aria-label="پیش‌نمایش زندهٔ تغییرات">
        <AuthenticatedMedia as="video" ref={video} src={src} muted playsInline preload="metadata"
          onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onLoadedMetadata={(e: any) => { setTime(t => ({ ...t, total: e.currentTarget.duration || 0 })); setPlayUrl((e.currentTarget.currentSrc || "").split("#")[0]); }}
          onTimeUpdate={(e: any) => setTime({ now: e.currentTarget.currentTime, total: e.currentTarget.duration || 0 })}
          style={{ width: "100%", height: "100%", objectFit: "cover", filter, transform: `translate(${tx}%, ${ty}%) scale(${scale})`, transition: "transform .12s" }}/>
        {warmth !== 0 ? <div aria-hidden className="pe-tint" style={{ background: warmth > 0 ? "#ff8a3d" : "#4b8dff", opacity: Math.min(Math.abs(warmth) / 160, 0.5) }}/> : null}
      </div>
      <div className="pe-transport">
        <button type="button" className="pe-icon" aria-label="برگرداندن آخرین تغییر" disabled={!canUndo || disabled} onClick={onUndo}><Icon name="undo" size={22}/></button>
        <button type="button" className="pe-play" aria-label={playing ? "توقف" : "پخش"} onClick={() => { const el = video.current; if (!el) return; if (el.paused) void el.play().catch(() => {}); else el.pause(); }}><Icon name={playing ? "pause" : "play"} size={26}/></button>
        <span className="pe-time" dir="ltr">{clock(time.now)} / {clock(time.total)}</span>
      </div>
      <div className="pe-strip" style={frames.length ? { backgroundImage: frames.map(f => `url(${f})`).join(","), backgroundSize: `${100 / frames.length}% 100%`,
        backgroundPosition: frames.map((_, i) => `${frames.length > 1 ? (i / (frames.length - 1)) * 100 : 0}% 0`).join(","), backgroundRepeat: "no-repeat" } : undefined}>
        <span className="pe-head" style={{ insetInlineStart: `${time.total ? Math.min(time.now / time.total, 1) * 100 : 0}%` }} aria-hidden/>
        <input className="pe-scrub" type="range" min={0} max={Math.max(time.total, 0.1)} step={0.05} value={Math.min(time.now, time.total || 0)} aria-label="جابه‌جایی در ویدیو"
          onChange={event => { const el = video.current; if (el) el.currentTime = Number(event.target.value); }}/>
      </div>
      <small className="pe-source">{base ? "ویدیوی ساخته‌شدهٔ فعلی + تغییرات شما" : "فیلم اصلی (هنوز رندر نشده)"}</small>
    </div>

    {open === null ? <nav className="pe-tools" aria-label="ابزارهای ویرایش">{tools.map(([id, label, icon]) =>
      <button key={id} type="button" className="pe-tool" onClick={() => setOpen(id)}><Icon name={icon} size={24}/><span>{label}</span></button>)}{trailing}</nav>
    : <div className="pe-sheet">
      <div className="pe-sheet-head">
        {open === "light" ? <div className="segmented" role="tablist" aria-label="نور و رنگ">
          <button type="button" aria-pressed={lightTab === "presets"} onClick={() => setLightTab("presets")}>پیش‌تنظیم</button>
          <button type="button" aria-pressed={lightTab === "adjust"} onClick={() => setLightTab("adjust")}>تنظیم</button></div> : <b>{title}</b>}
        <button type="button" className="pe-done" aria-label="تأیید و بستن" onClick={() => setOpen(null)}><Icon name="check" size={24}/></button>
      </div>
      {open === "light" && lightTab === "presets" ? <div className="pe-presets">{presets}</div> : null}
      {sliderOpen && active && !(open === "light" && lightTab === "presets") ? <>
        <div className="pe-slider">
          <output className="pe-value">{active.value}{active.suffix || ""}</output>
          <input type="range" min={active.min} max={active.max} step={active.step} value={active.value} disabled={disabled} aria-label={active.label}
            onChange={event => active.send(Number(event.target.value))} onDoubleClick={() => active.send(active.neutral)}/>
        </div>
        <div className="pe-params" role="tablist" aria-label="پارامتر">
          {open === "light" ? <button type="button" className="pe-param" aria-pressed={values.gradeAuto} disabled={disabled} onClick={() => onChange({ grade_auto: !values.gradeAuto })}><Icon name="wand" size={22}/><span>خودکار</span></button> : null}
          {open === "frame" ? <button type="button" className="pe-param" aria-pressed={values.framingAuto} disabled={disabled} onClick={() => onChange({ framing_auto: !values.framingAuto })}><Icon name="wand" size={22}/><span>خودکار</span></button> : null}
          {open === "zoom" ? <button type="button" className="pe-param" aria-pressed={values.zoomEnabled} disabled={disabled} onClick={() => onChange({ zoom_enabled: !values.zoomEnabled })}><Icon name="check" size={22}/><span>روشن</span></button> : null}
          {params[open!].map(item => <button key={item.id} type="button" className="pe-param" aria-pressed={item.id === active.id} onClick={() => setParam(current => ({ ...current, [open!]: item.id }))}><Icon name={item.icon} size={22}/><span>{item.label}</span></button>)}
        </div>
        <p className="pe-note">{open === "frame" ? "دو بار روی اسلایدر بزنید تا به حالت پیش‌فرض برگردد. کادربندی خودکار هنگام رندر اعمال می‌شود." : open === "light" ? "دو بار روی اسلایدر بزنید تا به حالت پیش‌فرض برگردد. تصحیح خودکار هنگام رندر اعمال می‌شود." : "دو بار روی اسلایدر بزنید تا به حالت پیش‌فرض برگردد."}</p>
      </> : null}
      {!sliderOpen ? <div className="pe-form">{children}</div> : null}
    </div>}
  </div>;
}
