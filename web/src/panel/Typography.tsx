import React from "react";
import {api} from "../api";
import {friendlyError} from "../ui";
import type {CaptionFont} from "./types";

function Specimen({font, text}: {font: CaptionFont; text: string}) {
  const [status, setStatus] = React.useState<"loading" | "ready" | "failed">("loading");
  const id = React.useId().replace(/[^a-zA-Z0-9-]/g, "");
  const url = font.caption_font_id ? api.fontFileUrl(font.caption_font_id) : api.panelCaptionFontFile(font.family);
  React.useEffect(() => {
    let active = true;
    let objectUrl: string | undefined;
    let face: FontFace | undefined;
    async function load() {
      try {
        objectUrl = await api.authenticatedObjectUrl(url);
        if (!active) { URL.revokeObjectURL(objectUrl); return; }
        face = await new FontFace(`panel-font-${id}`, `url("${objectUrl}")`).load();
        if (active) { document.fonts.add(face); setStatus("ready"); }
      } catch { if (active) setStatus("failed"); }
    }
    void load();
    return () => {
      active = false;
      if (face) document.fonts.delete(face);
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [url, id]);
  return status === "ready"
    ? <p className="mp-font-sample" style={{fontFamily: `panel-font-${id}`}} dir="auto">{text}</p>
    : <p className="mp-muted" role="status">{status === "failed" ? "نمونهٔ فونت باز نشد." : "در حال خواندن نمونهٔ فونت…"}</p>;
}

export function Typography({family, approvedId, disabled, onSave}: {
  family?: string | null; approvedId?: string | null; disabled?: boolean; onSave?: (font: CaptionFont | null) => Promise<boolean>;
}) {
  const [fonts, setFonts] = React.useState<CaptionFont[]>([]);
  const [selected, setSelected] = React.useState("");
  const [query, setQuery] = React.useState("");
  const [text, setText] = React.useState("نمونهٔ فارسی ۱۴۰۵ · EditorGPT");
  const [persian, setPersian] = React.useState(false);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");
  const id = (font: CaptionFont) => font.caption_font_id ? `library:${font.caption_font_id}` : `bundled:${font.family}`;
  const activeFont = fonts.find(font => id(font) === selected);
  React.useEffect(() => {
    const abort = new AbortController();
    setLoading(true);
    setError("");
    api.panelCaptionFonts(persian, abort.signal).then(result => {
      if (!abort.signal.aborted) setFonts(result);
    }).catch(e => {
      if (!abort.signal.aborted) setError(friendlyError(e, "load available caption fonts"));
    }).finally(() => {
      if (!abort.signal.aborted) setLoading(false);
    });
    return () => abort.abort();
  }, [persian]);

  return <section className="mp-inspector" aria-label="فونت زیرنویس">
    {onSave && <p>فونت همهٔ زیرنویس‌ها · <b dir="auto">{family || "پیش‌فرض سبک"}</b></p>}
    <div className="mp-form-grid">
      <label>جستجوی فونت<input type="search" className="input" dir="auto" value={query}
        onChange={e => setQuery(e.target.value)}/></label>
      <label>فونت سازگار با رندر<select className="input" value={activeFont ? selected : ""} disabled={loading}
        onChange={e => setSelected(e.target.value)}>
        <option value="">انتخاب فونت</option>
        {fonts.filter(font => id(font) === selected || `${font.family} ${font.style}`.toLowerCase().includes(query.trim().toLowerCase()))
          .map(font => <option key={id(font)} value={id(font)}>{font.family} · {font.style}</option>)}
      </select></label>
    </div>
    <label className="mp-check"><input type="checkbox" checked={persian} onChange={e => {setPersian(e.target.checked); setSelected("");}}/>فقط فونت با حروف فارسی</label>
    {error && <p role="alert">{error}</p>}
    {activeFont && <>
      <label>متن نمونه<input className="input" value={text} maxLength={160} dir="auto" onChange={e => setText(e.target.value)}/></label>
      <Specimen key={selected} font={activeFont} text={text}/>
    </>}
    {onSave && <div className="mp-actions">
      <button className="btn btn-primary" disabled={disabled || !activeFont ||
        (activeFont.family === family && (activeFont.caption_font_id || null) === (approvedId || null))}
        onClick={() => activeFont && void onSave(activeFont)}>اعمال به زیرنویس‌ها</button>
      <button className="btn btn-secondary" disabled={disabled || !family} onClick={() => void onSave(null)}>فونت پیش‌فرض</button>
    </div>}
  </section>;
}
