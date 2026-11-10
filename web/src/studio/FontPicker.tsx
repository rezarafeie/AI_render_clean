import React from "react";
import { api, ProFont } from "../api";
import { AuthenticatedMedia } from "../AuthenticatedMedia";

let catalog: Promise<ProFont[]> | null = null;
const loadedFaces = new Set<string>();

/** The font library as the server lists it (cached for the page). */
export function useProFonts(): { fonts: ProFont[]; error: string } {
  const [state, setState] = React.useState<{ fonts: ProFont[]; error: string }>({ fonts: [], error: "" });
  React.useEffect(() => {
    let alive = true;
    catalog ??= api.proFonts().then(out => out.fonts);
    catalog.then(fonts => { if (alive) setState({ fonts, error: "" }); }).catch(() => { catalog = null; if (alive) setState({ fonts: [], error: "فهرست فونت‌ها خوانده نشد." }); });
    return () => { alive = false; };
  }, []);
  return state;
}

/** Make a font drawable in this page: its files are fetched with the person's own session (the library is not public) and registered with the browser. */
export async function loadFontFaces(font: ProFont): Promise<void> {
  await Promise.all(font.faces.map(async face => {
    const key = `${face.css_family}|${face.weight}|${face.url}`;
    if (loadedFaces.has(key)) return;
    loadedFaces.add(key);
    try {
      const url = await api.authenticatedObjectUrl(face.url);
      const loaded = await new FontFace(`lib-${face.css_family}`, `url(${url})`, { weight: face.weight, style: "normal" }).load();
      document.fonts.add(loaded);
    } catch { loadedFaces.delete(key); }
  }));
}

const SAMPLE = "ثبت شرکت جهانی بدون مهاجرت ۱۴۰۴";

function Card({ font, selected, text, onPick, disabled }: { font: ProFont; selected: boolean; text: string; onPick?: () => void; disabled?: boolean }) {
  const [ready, setReady] = React.useState(false);
  React.useEffect(() => { let alive = true; void loadFontFaces(font).then(() => { if (alive) setReady(true); }); return () => { alive = false; }; }, [font]);
  const top = font.weights.length ? font.weights[font.weights.length - 1] : 400;
  const style: React.CSSProperties = { fontFamily: `'lib-${font.family}', system-ui`, fontWeight: Math.min(top, 700) };
  return <button type="button" className="fp-card" aria-pressed={selected} disabled={disabled} onClick={onPick} data-pickable={onPick ? "" : undefined}>
    <span className="fp-head"><b dir="auto">{font.label}</b><small dir="ltr">{font.family}</small></span>
    <span className="fp-live" dir="rtl" style={style} data-ready={ready || undefined}>{text || SAMPLE}</span>
    <AuthenticatedMedia as="img" className="fp-specimen" src={api.fontSpecimenUrl(font.id)} alt="" loading="lazy" draggable={false}/>
    <span className="fp-tags" dir="rtl">{font.mood.slice(0, 3).join(" · ")}</span>
    <span className="fp-note" dir="rtl">{font.best_for.slice(0, 3).join("، ")}{font.latin ? "" : " — بدون حروف لاتین"}</span>
  </button>;
}

/** Choose a font: every family with its real letters (live, in the text the person types) and its specimen. `onPick` omitted = just browsing the library. */
export function FontPicker({ value, onPick, allowed, disabled }: { value?: string; onPick?: (id: string) => void; allowed?: string[]; disabled?: boolean }) {
  const { fonts, error } = useProFonts();
  const [text, setText] = React.useState("");
  const [open, setOpen] = React.useState(!value);
  const list = fonts.filter(font => !allowed || allowed.includes(font.id));
  const current = list.find(font => font.id === value);
  return <div className="fp" dir="rtl">
    {value && current ? <div className="fp-current"><span>انتخاب‌شده: <b>{current.label}</b> <small dir="ltr">{current.family}</small></span>
      <button type="button" className="btn btn-sm btn-secondary" onClick={() => setOpen(v => !v)} disabled={disabled}>{open ? "بستن فهرست" : "تغییر فونت"}</button></div> : null}
    {open || !value ? <>
      <input className="input" dir="auto" value={text} onChange={e => setText(e.target.value)} placeholder="متن خودتان را بنویسید تا با هر فونت دیده شود" aria-label="متن پیش‌نمایش"/>
      {error ? <p className="field-hint" role="alert">{error}</p> : null}
      <div className="fp-grid">{list.map(font => <Card key={font.id} font={font} text={text} selected={font.id === value} disabled={disabled}
        onPick={onPick ? () => { onPick(font.id); setOpen(false); } : undefined}/>)}</div>
    </> : null}
    {current && !current.latin ? <p className="field-hint">این فونت حروف لاتین ندارد؛ نوشته‌های انگلیسی صحنه‌ها با فونت جایگزین دیده می‌شوند.</p> : null}
  </div>;
}
