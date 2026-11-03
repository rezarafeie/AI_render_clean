import React from "react";
import { api, MotionEditable, MotionField, MotionGraphic, StudioEvent } from "../api";
import { AuthenticatedMedia } from "../AuthenticatedMedia";
import { Icon } from "../components/Icon";
import { useFullscreen } from "../components/useFullscreen";
import { friendlyError } from "../ui";
import { EditCard, EditGrid } from "./EditCard";

/** The chat's motion graphic, kept fresh: the newest state, refreshed as events arrive and while a version is being made. */
function useMotion(motionId: string, events: StudioEvent[]) {
  const [motion, setMotion] = React.useState<MotionGraphic | null>(null);
  const [error, setError] = React.useState("");
  const last = React.useMemo(() => { const mine = events.filter(e => e.data?.motion_id === motionId); return mine.length ? mine[mine.length - 1].seq : 0; }, [events, motionId]);
  const refresh = React.useCallback(() => api.motionView(motionId).then(value => { setMotion(value); setError(""); }).catch(e => setError(friendlyError(e, "load the motion graphic"))), [motionId]);
  React.useEffect(() => { void refresh(); }, [refresh, last]);
  React.useEffect(() => {
    if (!motion?.active) return;
    const timer = window.setInterval(() => void refresh(), 2500);
    return () => window.clearInterval(timer);
  }, [motion?.active, refresh]);
  return { motion, error, refresh };
}

const FORMATS = { vertical: "9:16", horizontal: "16:9", square: "1:1" } as const;

/**
 * Preview of a motion graphic, laid out exactly like the Preview of every other kind of video (version buttons, player with full screen,
 * version line, Download): the same classes, the same order, so the tab reads the same whichever engine made the video.
 */
export function MotionPreviewPane({ motionId, events, onCancel }: { motionId: string; events: StudioEvent[]; onCancel?: () => void }) {
  const { motion, error } = useMotion(motionId, events);
  const [selected, setSelected] = React.useState<number | null>(null);
  const playerRef = React.useRef<HTMLDivElement>(null);
  const videoRef = React.useRef<HTMLVideoElement>(null);
  const fullscreen = useFullscreen(playerRef, videoRef);
  React.useEffect(() => { setSelected(null); }, [motion?.current]);                      // a new version replaces what was shown
  if (!motion) return <div className="ws-empty" dir="rtl">{error ? <div className="notice" data-tone="error" role="alert">{error}</div> : <div className="tl-loading" role="status"><span className="spinner"/>در حال بارگذاری…</div>}</div>;
  const shown = motion.versions.find(v => v.n === (selected ?? motion.current)) ?? motion.versions[motion.versions.length - 1];
  if (!shown) return <div className="ws-preview"><div className="ws-player"><div className="ws-placeholder">{motion.active ? <><span className="spinner"/><span>{motion.message || "Preparing preview"}</span></> : <span>No video yet</span>}</div></div></div>;
  const video = api.motionMediaUrl(motionId, "video", shown.n);
  return <div className="ws-preview">
    {motion.versions.length > 1 ? <div className="ws-actions" role="group" aria-label="نسخه‌های خروجی">{motion.versions.map(item => <button key={item.n} className="btn btn-sm btn-secondary" aria-pressed={item.n === shown.n} onClick={() => setSelected(item.n)}>v{item.n}</button>)}</div> : null}
    <div className="ws-player" ref={playerRef} style={{ aspectRatio: `${shown.width} / ${shown.height}` }}>
      <AuthenticatedMedia as="video" ref={videoRef} key={`p-${motionId}-${shown.n}`} controls playsInline preload="metadata" src={video} posterSrc={api.motionMediaUrl(motionId, "thumb", shown.n)}/>
      <button type="button" className="ws-fs" onClick={() => void fullscreen.toggle()} aria-pressed={fullscreen.active} aria-label={fullscreen.active ? "Exit fullscreen" : "Fullscreen"}
        data-tip={fullscreen.active ? "Exit fullscreen" : "Fullscreen"}><Icon name={fullscreen.active ? "fullscreenExit" : "fullscreen"} size={18}/></button>
    </div>
    {motion.active ? <p className="field-hint" role="status" dir="rtl">{motion.message || "نسخهٔ تازه در حال ساخت است؛ با تمام‌شدن، همین‌جا جایگزین می‌شود."}</p> : null}
    <div className="ws-meta">
      <span>Version {shown.n}{shown.n === motion.current ? " (latest)" : ""}</span>
      <span>{Math.round(shown.duration * 10) / 10}s · {FORMATS[shown.format]} · {shown.title || "Motion graphic"}</span>
    </div>
    <div className="ws-actions">
      <button className="btn btn-sm" onClick={() => void api.downloadAuthenticated(video, `${shown.title || "motion-graphic"}.mp4`)}><Icon name="download" size={15}/>Download video</button>
      {motion.active && onCancel ? <button className="btn btn-sm btn-secondary" onClick={onCancel}>Cancel</button> : null}
    </div>
  </div>;
}

function FieldInput({ field, value, disabled, onChange }: { field: MotionField; value: string | number; disabled: boolean; onChange: (next: string | number) => void }) {
  const id = `mf-${field.key}`;
  const common = { id, disabled: disabled || field.disabled, "aria-describedby": field.help ? `${id}-h` : undefined };
  return <div className="field" data-wide={field.type === "textarea" || undefined}>
    <label htmlFor={id}>{field.label}</label>
    {field.type === "textarea" ? <textarea {...common} className="input bidi" dir="auto" rows={3} maxLength={field.maxlength} value={String(value)} onChange={e => onChange(e.target.value)}/>
      : field.type === "select" ? <select {...common} className="input" value={String(value)} onChange={e => onChange(e.target.value)}>{(field.options || []).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
      : field.type === "color" ? <input {...common} className="input" style={{ padding: 4, height: 40 }} type="color" value={String(value)} onChange={e => onChange(e.target.value.toUpperCase())}/>
      : field.type === "number" ? <input {...common} className="input" type="number" min={field.min} max={field.max} step={field.step} value={String(value)} onChange={e => onChange(e.target.value === "" ? "" : Number(e.target.value))}/>
      : <input {...common} className="input bidi" dir="auto" type="text" maxLength={field.maxlength} value={String(value)} onChange={e => onChange(e.target.value)}/>}
    {field.help ? <small id={`${id}-h`} className="field-hint">{field.help}</small> : null}
  </div>;
}

/** What a field's change costs, in words (the server names the kind of impact for each field). */
const IMPACT: Record<string, string> = { text: "بازسازی متن همین صحنه", voice: "صدای همین خط دوباره ساخته می‌شود", scene: "همین صحنه دوباره طراحی می‌شود", assemble: "فقط رندر دوباره", colours: "رنگ‌ها در همهٔ صحنه‌ها عوض می‌شود", audio: "صدا و میکس دوباره ساخته می‌شود" };

/** The groups of settings (one card per group) with every field the server listed; nothing here is decided by the browser. */
export function MotionEditForm({ schema, draft, disabled, onChange }: { schema: MotionEditable; draft: Record<string, string | number>; disabled: boolean; onChange: (field: MotionField, next: string | number) => void }) {
  return <>{schema.groups.map(group => {
    const edited = group.fields.filter(f => f.key in draft).length;
    return <EditCard key={group.id} title={group.title} icon={group.id === "scenes" ? "film" : group.id === "colours" ? "image" : group.id === "voice" ? "mic2" : "music"}
      summary={edited ? `${edited} تغییر اعمال‌نشده` : `${group.fields.length} مورد`}>
      <EditGrid>{group.fields.map(field => <FieldInput key={field.key} field={field} value={field.key in draft ? draft[field.key] : field.value} disabled={disabled} onChange={next => onChange(field, next)}/>)}</EditGrid>
    </EditCard>;
  })}</>;
}

/**
 * The Edit tab of a motion graphic. Every field, its current value and the options it accepts come from the server (read from the project itself),
 * the same groups-of-settings cards every other video type uses; applying creates a new version and rebuilds only what the changes touch.
 */
export function MotionEditPane({ motionId, events }: { motionId: string; events: StudioEvent[] }) {
  const { motion } = useMotion(motionId, events);
  const [schema, setSchema] = React.useState<MotionEditable | null>(null);
  const [draft, setDraft] = React.useState<Record<string, string | number>>({});
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [done, setDone] = React.useState<string[] | null>(null);
  const version = motion?.current ?? 0;
  React.useEffect(() => {
    let live = true;
    setSchema(null);
    api.motionEditable(motionId).then(value => { if (live) { setSchema(value); setDraft({}); } }).catch(e => { if (live) setError(friendlyError(e, "load the editable settings")); });
    return () => { live = false; };
  }, [motionId, version]);
  if (!schema) return <div className="ws-empty" dir="rtl">{error ? <div className="notice" data-tone="error" role="alert">{error}</div> : <div className="tl-loading" role="status"><span className="spinner"/>در حال بارگذاری…</div>}</div>;
  if (!schema.groups.length) return <div className="ws-empty" dir="rtl"><p className="field-hint">{schema.reason || "ویرایش وقتی ممکن می‌شود که طرح ساخته شده باشد."}</p></div>;
  const working = schema.busy || Boolean(motion?.active);
  const changed = Object.entries(draft);
  const set = (field: MotionField, next: string | number) => { setDone(null); setDraft(current => { const copy = { ...current }; if (next === field.value || next === "") delete copy[field.key]; else copy[field.key] = next; return copy; }); };
  async function apply() {
    setBusy(true); setError(""); setDone(null);
    try { const result = await api.motionEdit(motionId, draft); setDone(result.summary); setDraft({}); }
    catch (e) { setError(friendlyError(e, "apply the changes")); }
    finally { setBusy(false); }
  }
  const effects = [...new Set(changed.map(([key]) => schema.groups.flatMap(g => g.fields).find(f => f.key === key)?.impact || "").filter(Boolean))].map(impact => IMPACT[impact] || impact);
  return <div className="ws-edit">
    <header className="ws-edit-intro" dir="rtl"><h2>ویرایش این ویدیو</h2><p>هر چیزی که این پروژه دارد اینجا قابل تغییر است. با اعمال تغییر، نسخهٔ تازه‌ای ساخته می‌شود و نسخهٔ فعلی می‌ماند؛ فقط بخش‌های مربوط دوباره ساخته می‌شوند.</p></header>
    <MotionEditForm schema={schema} draft={draft} disabled={busy || working} onChange={set}/>
    {error ? <p className="notice" data-tone="error" role="alert" dir="rtl">{error}</p> : null}
    {done ? <p className="notice" role="status" dir="rtl">تغییرات ثبت شد و نسخهٔ تازه در حال ساخت است: {done.join("؛ ")}.</p> : null}
    {working && !done ? <p className="field-hint" role="status" dir="rtl">تا پایان ساخت فعلی، ویرایش بسته است.</p> : null}
    <div className="ws-edit-footer" dir="rtl"><div className="ws-actions">
      <button className="btn" disabled={!changed.length || busy || working} onClick={() => void apply()}>{busy ? "در حال ثبت…" : changed.length ? `اعمال ${new Intl.NumberFormat("fa-IR").format(changed.length)} تغییر` : "تغییری انجام نشده"}</button>
      {changed.length ? <button className="btn btn-secondary" disabled={busy} onClick={() => { setDraft({}); setDone(null); }}>لغو تغییرها</button> : null}
    </div>{changed.length && effects.length ? <p className="field-hint">{effects.join(" · ")}</p> : null}</div>
  </div>;
}
