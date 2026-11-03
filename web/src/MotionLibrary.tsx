import React from "react";
import { Icon } from "./components/Icon";

type Param = { id: string; type?: string; role?: string; label?: string; description?: string; default?: unknown; min?: number; max?: number; options?: unknown[] };
type Raw = Record<string, any>;
export type LibraryItem = {
  id: string; name: string; source: SourceId; status: string; format: string; use: string; poster: string | null; video: string | null;
  params: Param[]; raw: Raw;
};
type SourceId = "components" | "effects" | "recipes" | "parametric" | "styles";

const FILES = ["index.json", "claude-effects.json", "shotcraft.json", "lemo.json", "native-shotcraft.json"];
export const SOURCES: { id: SourceId; label: string; hint: string }[] = [
  { id: "components", label: "Components", hint: "Animated building blocks checked in a browser" },
  { id: "effects", label: "Effects", hint: "Face and frame effects" },
  { id: "recipes", label: "Shot recipes", hint: "Reference shots from upstream demos" },
  { id: "parametric", label: "Parametric", hint: "Components with editable parameters, checked end to end" },
  { id: "styles", label: "Style packs", hint: "Complete visual styles" },
];
/** What each checked status means, in the words the old gallery used. */
export const STATUS: Record<string, { label: string; tone: "ok" | "info" | "warn"; note: string }> = {
  "native-component-checked": { label: "Parametric", tone: "ok", note: "خروجی واقعی و اتصال ترکیبی بررسی شد" },
  "browser-checked": { label: "Browser-checked", tone: "ok", note: "بررسی مرورگر انجام شد" },
  "synthetic-frame-checked": { label: "Synthetic test", tone: "info", note: "اجرای افکت روی ورودی هندسی؛ رهگیری چهره و ویدیوی کامل آزمون نشده" },
  "upstream-demo-checked": { label: "Upstream demo", tone: "info", note: "اجرای مستقیم نمونهٔ اصلی؛ اتصال محتوای کاربر و فارسی/عمودی هنوز تکمیل نشده" },
};
const FORMAT: Record<string, string> = { vertical: "9:16", horizontal: "16:9", square: "1:1" };

export function sourceOf(id: string): SourceId {
  if (id.startsWith("hyperframes:")) return "components";
  if (id.startsWith("claude-effects:")) return "effects";
  if (id.startsWith("shotcraft:")) return "parametric";
  if (id.startsWith("lemo:")) return "styles";
  return "recipes";
}
const normalize = (value: string) => value.toLowerCase().replace(/ي/g, "ی").replace(/ك/g, "ک");
const safe = (url: unknown, pattern: RegExp) => typeof url === "string" && pattern.test(url) ? url : null;
const versioned = (url: string, hash?: string) => url + (/^[0-9a-f]{64}$/.test(hash || "") ? `?v=${hash!.slice(0, 16)}` : "");

/** One entry of the five catalog files as the page shows it; links to media are accepted only from this app's own preview folder. */
export function toItem(raw: Raw): LibraryItem {
  const poster = safe(raw.poster, /^\/creative-previews\/[a-z0-9-]+\.png$/);
  const video = safe(raw.preview_video, /^\/creative-previews\/[a-z0-9-]+\.mp4$/);
  return { id: String(raw.id), name: String(raw.name || raw.id), source: sourceOf(String(raw.id)), status: String(raw.status || ""), format: String(raw.format || ""),
    use: String(raw.use || raw.description || ""), poster: poster ? versioned(poster, raw.poster_sha256) : null, video: video ? versioned(video, raw.video_sha256) : null,
    params: Array.isArray(raw.parameters) ? raw.parameters : [], raw };
}

export function filterItems(items: LibraryItem[], source: SourceId | "all", query: string): LibraryItem[] {
  const needle = normalize(query.trim());
  return items.filter(item => (source === "all" || item.source === source) && (!needle || normalize([item.name, item.id, item.use].join(" ")).includes(needle)));
}

function ParamTable({ params }: { params: Param[] }) {
  if (!params.length) return <p className="ml-empty">No editable parameters.</p>;
  return <table className="ml-params"><thead><tr><th>Parameter</th><th>Type</th><th>Default</th></tr></thead><tbody>
    {params.map(param => <tr key={param.id}><td><b>{param.label || param.id}</b>{param.description ? <small>{param.description}</small> : null}</td>
      <td dir="ltr">{param.type}{typeof param.min === "number" || typeof param.max === "number" ? ` ${param.min ?? ""}–${param.max ?? ""}` : ""}</td>
      <td dir="ltr">{param.default === undefined || param.default === "" ? "—" : String(param.default)}</td></tr>)}
  </tbody></table>;
}

function Card({ item, onOpen }: { item: LibraryItem; onOpen: (item: LibraryItem) => void }) {
  const status = STATUS[item.status] || { label: "Needs work", tone: "warn" as const, note: "نیازمند اصلاح؛ آمادهٔ انتخاب موتور نیست" };
  const [video, setVideo] = React.useState(false);
  const ratio = item.format === "horizontal" ? "16 / 9" : item.format === "square" ? "1 / 1" : "9 / 16";
  return <li className="ml-card">
    <div className="ml-media" style={{ aspectRatio: ratio }} data-format={item.format || undefined}>
      {video && item.video ? <video controls playsInline autoPlay preload="none" src={item.video} aria-label={`Sample motion of ${item.name}`}/>
        : item.poster ? <button type="button" className="ml-poster" onClick={() => onOpen(item)} aria-label={`Enlarge ${item.name}`}><img src={item.poster} alt="" loading="lazy" draggable={false}/></button>
        : <span className="ml-noposter"><Icon name="motion" size={26}/></span>}
      {item.video && !video ? <button type="button" className="ml-play" onClick={() => setVideo(true)} aria-label={`Play ${item.name}`}><Icon name="play" size={16}/></button> : null}
      {item.format ? <span className="ml-format">{FORMAT[item.format] || item.format}</span> : null}
    </div>
    <div className="ml-body">
      <b dir="ltr" className="ml-name">{item.name}</b>
      <span className="ml-status" data-tone={status.tone} title={status.note}><i aria-hidden="true"/>{status.label}</span>
      {item.use ? <p className="ml-use" dir="auto">{item.use}</p> : null}
      <details className="ml-more"><summary>Parameters &amp; details<Icon name="chevronDown" size={14}/></summary>
        <div className="ml-more-body">
          <p className="ml-note" dir="auto">{status.note}</p>
          <ParamTable params={item.params}/>
          <details className="ml-tech"><summary>Technical data</summary><pre dir="ltr">{JSON.stringify({ id: item.id, status: item.status, ...pick(item.raw) }, null, 2)}</pre></details>
        </div>
      </details>
    </div>
  </li>;
}
const pick = (raw: Raw) => Object.fromEntries(["fixture", "tracking_verified", "production_template_ready", "source_revision", "backward_seek_verified", "source_sha256", "encoded_output_verified", "findings"]
  .filter(key => raw[key] !== undefined).map(key => [key, raw[key]]));

const PAGE = 24;

export default function MotionLibrary() {
  const [items, setItems] = React.useState<LibraryItem[] | null>(null);
  const [failed, setFailed] = React.useState(false);
  const [source, setSource] = React.useState<SourceId | "all">("all");
  const [query, setQuery] = React.useState("");
  const [shown, setShown] = React.useState(PAGE);
  const [open, setOpen] = React.useState<LibraryItem | null>(null);
  React.useEffect(() => {
    let live = true;
    Promise.all(FILES.map(file => fetch(`/creative-previews/${file}`, { cache: "no-cache" }).then(r => r.ok ? r.json() : { items: {} }).catch(() => ({ items: {} }))))
      .then(groups => { if (live) setItems(groups.flatMap((data: Raw) => Object.values(data.items || {}) as Raw[]).map(toItem)); })
      .catch(() => { if (live) setFailed(true); });
    return () => { live = false; };
  }, []);
  React.useEffect(() => { setShown(PAGE); }, [source, query]);
  React.useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  const filtered = React.useMemo(() => filterItems(items || [], source, query), [items, source, query]);
  const counts = React.useMemo(() => Object.fromEntries(SOURCES.map(s => [s.id, (items || []).filter(item => item.source === s.id).length])), [items]);
  return <div className="page ml-page">
    <header className="page-header">
      <div><h1>Motion library</h1><p>Previews of the animated components, effects and shot recipes the editor can use. They are demonstrations, not your project's video; each shows how far it has been checked.</p></div>
    </header>
    <div className="ml-toolbar">
      <div className="ml-search"><Icon name="search" size={16}/><input className="input" type="search" value={query} maxLength={120} placeholder="Search by name or purpose" aria-label="Search the motion library" onChange={event => setQuery(event.target.value)}/></div>
      <div className="chip-row" role="group" aria-label="Filter by kind">
        <button className="chip" aria-pressed={source === "all"} onClick={() => setSource("all")}>All{items ? ` · ${items.length}` : ""}</button>
        {SOURCES.map(item => counts[item.id] ? <button key={item.id} className="chip" aria-pressed={source === item.id} title={item.hint} onClick={() => setSource(item.id)}>{item.label} · {counts[item.id]}</button> : null)}
      </div>
    </div>
    {!items && !failed ? <ul className="ml-grid" aria-label="Loading">{Array.from({ length: 8 }, (_, index) => <li key={index} className="ml-card"><span className="skeleton ml-skel"/></li>)}</ul> : null}
    {failed ? <p className="ml-empty" role="alert">The library could not be loaded. Try again in a moment.</p> : null}
    {items ? <>
      <p className="ml-count" role="status">{filtered.length} {filtered.length === 1 ? "item" : "items"}</p>
      {filtered.length ? <ul className="ml-grid">{filtered.slice(0, shown).map(item => <Card key={item.id} item={item} onOpen={setOpen}/>)}</ul> : <p className="ml-empty">Nothing matches. Try another word or clear the filter.</p>}
      {filtered.length > shown ? <div className="ml-more-row"><button className="btn btn-secondary" onClick={() => setShown(value => value + PAGE)}>Show more ({filtered.length - shown})</button></div> : null}
    </> : null}
    {open && open.poster ? <div className="overlay" role="dialog" aria-modal="true" aria-label={open.name} onMouseDown={event => { if (event.target === event.currentTarget) setOpen(null); }}>
      <figure className="mg-lightbox"><img src={open.poster} alt={`Sample of ${open.name}`}/><figcaption dir="ltr">{open.name}</figcaption>
        <button type="button" className="icon-btn mg-lightbox-close" onClick={() => setOpen(null)} aria-label="Close"><Icon name="close" size={18}/></button></figure>
    </div> : null}
  </div>;
}
