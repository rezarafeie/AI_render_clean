import React from "react";
import { NavLink } from "react-router-dom";
import { api, CloudFile, CloudProvider } from "../api";
import { Icon } from "../components/Icon";
import { formatBytes } from "../format";
import { friendlyError } from "../ui";

type Crumb = { id: string; name: string };
const PROVIDER = "googledrive";
const MEDIA = [["", "همه"], ["video", "ویدیو"], ["audio", "صدا"], ["image", "تصویر"]] as const;
const SORTS = [["name", "نام"], ["modified", "جدیدترین"], ["size", "حجم"]] as const;

function reconnectNeeded(text: string) { return /reconnect_required|COMPOSIO_(?:CONNECTION|POLICY)|not connected/i.test(text); }

/** 2823 s -> "47:03", 3725 s -> "1:02:05". */
function clock(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const h = Math.floor(total / 3600), m = Math.floor((total % 3600) / 60), s = total % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
}
/** Drive's thumbnail links end with =s220: ask for another size. */
function thumb(url: string, size: number): string { return /=s\d+(?:-[\w-]+)?$/i.test(url) ? url.replace(/=s\d+(?:-[\w-]+)?$/i, `=s${size}`) : url; }
const when = (value: string | null) => { try { return value ? new Date(value).toLocaleDateString("fa-IR") : ""; } catch { return ""; } };
const kindName = (kind: CloudFile["kind"]) => kind === "video" ? "ویدیو" : kind === "audio" ? "صدا" : kind === "image" ? "تصویر" : "";
const kindIcon = (file: CloudFile) => file.is_folder ? "projects" : file.kind === "video" ? "video" : file.kind === "audio" ? "music" : file.kind === "image" ? "image" : "alert";

/** The small picture of a file (Drive's own thumbnail), or its icon while it loads or when there is none. */
function Preview({ file, size = 56, onOpen }: { file: CloudFile; size?: number; onOpen?: () => void }) {
  const [failed, setFailed] = React.useState(false);
  const box = <span className="cloud-thumb" style={{ width: size * 1.4, height: size }} data-kind={file.kind || "other"}>
    {file.thumbnail && !failed
      ? <img src={thumb(file.thumbnail, 220)} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)}/>
      : <Icon name={kindIcon(file)} size={20}/>}
    {file.kind === "video" && file.duration ? <b className="cloud-thumb-time" dir="ltr">{clock(file.duration)}</b> : null}
  </span>;
  return onOpen && file.kind
    ? <button type="button" className="cloud-thumb-btn" onClick={onOpen} aria-label={`پیش‌نمایش ${file.name}`}>{box}</button> : box;
}

function Meta({ file }: { file: CloudFile }) {
  const parts: React.ReactNode[] = [];
  if (kindName(file.kind)) parts.push(<span key="k" className="cloud-chip" data-kind={file.kind}>{kindName(file.kind)}</span>);
  if (file.size) parts.push(<span key="s" className="cloud-chip"><bdi dir="ltr">{formatBytes(file.size)}</bdi></span>);
  if (file.duration) parts.push(<span key="d" className="cloud-chip"><Icon name="clock" size={12}/> <bdi dir="ltr">{clock(file.duration)}</bdi></span>);
  if (file.width && file.height) parts.push(<span key="r" className="cloud-chip"><bdi dir="ltr">{file.width}×{file.height}</bdi></span>);
  const date = when(file.modified);
  if (date) parts.push(<span key="m" className="cloud-date">{date}</span>);
  return <span className="cloud-meta">{parts}</span>;
}

/** Browse Google Drive and choose files to import. Importing itself is started by the caller, which also tracks progress. */
// Whether Drive is connected, kept for the session (the first check can take a while): prefetched when the studio opens.
let providerCache: CloudProvider | null | undefined;
let providerInflight: Promise<CloudProvider | null> | null = null;
// Every Drive listing seen this session (folder + search + filter + sort): shown at once next time, then refreshed behind it.
const listings = new Map<string, { files: CloudFile[]; next: string | null }>();
const listingKey = (folder: string, q: string, media: string, sort: string) => `${folder}|${q}|${media}|${sort}`;

export function prefetchDrive(): Promise<CloudProvider | null> {
  if (!providerInflight) providerInflight = api.cloudProviders().then(result => (providerCache = result.providers.find(item => item.id === PROVIDER) || null))
    .then(found => {
      const key = listingKey("root", "", "", "name");
      if (found?.connected && !listings.has(key)) {         // the root folder, ready before the person opens the tab
        void api.cloudFiles(PROVIDER, { folder: "root", q: "", media: "", sort: "name", page_token: null })
          .then(result => { listings.set(key, { files: result.files, next: result.next_page_token }); }).catch(() => {});
      }
      return found;
    })
    .finally(() => { providerInflight = null; });
  return providerInflight;
}

export function CloudPicker({ onClose, onImport, embedded }: { onClose: () => void; onImport: (files: CloudFile[]) => Promise<void> | void;
  /** Inside the "add files" dialog: no frame of its own. */ embedded?: boolean }) {
  const [provider, setProvider] = React.useState<CloudProvider | null | undefined>(providerCache);
  const [path, setPath] = React.useState<Crumb[]>([{ id: "root", name: "درایو من" }]);
  const [query, setQuery] = React.useState("");
  const [applied, setApplied] = React.useState("");
  const [media, setMedia] = React.useState<(typeof MEDIA)[number][0]>("");
  const [sort, setSort] = React.useState<(typeof SORTS)[number][0]>("name");
  const [files, setFiles] = React.useState<CloudFile[]>([]);
  const [next, setNext] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState("");
  const [picked, setPicked] = React.useState<Map<string, CloudFile>>(new Map());
  const [busy, setBusy] = React.useState(false);
  const [preview, setPreview] = React.useState<CloudFile | null>(null);
  const [playing, setPlaying] = React.useState(false);
  const [showOther, setShowOther] = React.useState(false);
  const request = React.useRef(0);
  const folder = path[path.length - 1].id;

  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") { if (preview) { setPreview(null); setPlaying(false); } else if (!embedded) onClose(); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, preview, embedded]);

  React.useEffect(() => {
    let live = true;
    if (providerCache?.connected) return () => { live = false; };            // known connected: no wait (a lost connection shows when the list loads)
    prefetchDrive().then(found => { if (live) setProvider(found); })
      .catch(e => { if (live) { setProvider(null); setError(friendlyError(e, "check Google Drive")); } });
    return () => { live = false; };
  }, []);

  const key = listingKey(folder, applied, media, sort);
  const load = React.useCallback(async (more: string | null, quiet = false) => {
    const id = ++request.current;
    if (!quiet) setLoading(true);
    setError("");
    try {
      const result = await api.cloudFiles(PROVIDER, { folder, q: applied, media, sort, page_token: more });
      if (id !== request.current) return;
      setFiles(current => {
        const value = more ? [...current, ...result.files] : result.files;
        if (!more) listings.set(key, { files: value, next: result.next_page_token });
        return value;
      });
      setNext(result.next_page_token);
    } catch (e) {
      if (id === request.current && !quiet) setError(friendlyError(e, "load Google Drive") + (reconnectNeeded(String(e)) ? " اتصال گوگل درایو را در تنظیمات دوباره برقرار کنید." : ""));
    } finally { if (id === request.current) setLoading(false); }
  }, [folder, applied, media, sort, key]);

  // A listing seen before is shown at once and refreshed quietly behind it; a new one starts empty with a visible loading state, so another
  // folder's files never sit there looking like this one's.
  React.useEffect(() => {
    if (!provider?.connected) return;
    setShowOther(false);
    const seen = listings.get(key);
    if (seen) { setFiles(seen.files); setNext(seen.next); void load(null, true); }
    else { setFiles([]); setNext(null); void load(null); }
  }, [provider, load, key]);

  const toggle = (file: CloudFile) => setPicked(current => {
    const copy = new Map(current);
    if (copy.has(file.id)) copy.delete(file.id); else copy.set(file.id, file);
    return copy;
  });
  const open = (file: CloudFile) => { setApplied(""); setQuery(""); setPath(current => [...current, { id: file.id, name: file.name }]); };
  const search = (event: React.FormEvent) => { event.preventDefault(); setApplied(query.trim()); };
  const importable = (file: CloudFile) => !file.is_folder && !file.native && !!file.kind;
  const folders = files.filter(file => file.is_folder);
  const usable = files.filter(importable);
  const other = files.filter(file => !file.is_folder && !importable(file));
  const allPicked = usable.length > 0 && usable.every(file => picked.has(file.id));
  const togglePage = () => setPicked(current => {
    const copy = new Map(current);
    if (allPicked) usable.forEach(file => copy.delete(file.id)); else usable.forEach(file => copy.set(file.id, file));
    return copy;
  });
  const chosen = [...picked.values()];
  const chosenBytes = chosen.reduce((sum, file) => sum + (file.size || 0), 0);
  const chosenSeconds = chosen.reduce((sum, file) => sum + (file.duration || 0), 0);
  const opening = loading && !files.length;
  async function start() {
    setBusy(true);
    try { await onImport(chosen); onClose(); } catch (e) { setError(friendlyError(e, "start the import")); setBusy(false); }
  }

  const body = <>
      {embedded ? null : <header className="cloud-head"><h3>وارد کردن از گوگل درایو</h3>
        <button className="icon-btn" onClick={onClose} aria-label="بستن"><Icon name="close" size={18}/></button></header>}

      {provider === undefined ? <p role="status"><span className="spinner"/> در حال بررسی گوگل درایو… بررسی اول ممکن است تا یک دقیقه طول بکشد.</p>
        : !provider?.connected ? <div className="notice" role="status" style={{ display: "grid", gap: 8 }}>
          <b>{provider && !provider.enabled ? "گوگل درایو روی این سرور فعال نیست." : "گوگل درایو وصل نیست."}</b>
          {error ? <span>{error}</span> : <span>حساب خود را در تنظیمات وصل کنید و دوباره برگردید. فایل‌های شما تا وقتی انتخابشان نکنید در درایو می‌مانند.</span>}
          <NavLink className="btn btn-sm btn-primary" to="/settings#integrations" onClick={onClose}>باز کردن اتصال‌ها</NavLink></div>
        : <>
          <form onSubmit={search} className="cloud-tools">
            <input className="input cloud-search" type="search" placeholder="جستجو در درایو" aria-label="جستجو در گوگل درایو" value={query} onChange={event => setQuery(event.target.value)}/>
            <button className="btn btn-sm btn-secondary" type="submit">جستجو</button>
          </form>
          <div className="cloud-filters">
            <div className="cloud-seg" role="group" aria-label="نوع فایل">
              {MEDIA.map(([value, label]) => <button key={value || "all"} type="button" className="cloud-seg-btn" aria-pressed={media === value} onClick={() => setMedia(value)}>{label}</button>)}
            </div>
            <label className="cloud-sort">مرتب‌سازی
              <select className="input" value={sort} onChange={event => setSort(event.target.value as typeof sort)}>{SORTS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          </div>

          <div className="cloud-list" aria-busy={loading}>
            <nav aria-label="مسیر پوشه" className="cloud-crumbs">
              {applied ? <span>نتایج «{applied}» <button className="btn btn-sm btn-ghost" onClick={() => { setApplied(""); setQuery(""); }}>پاک کردن</button></span>
                : path.map((crumb, index) => <React.Fragment key={crumb.id}>
                  {index ? <span className="cloud-sep" aria-hidden="true">‹</span> : null}
                  <button className="btn btn-sm btn-ghost" disabled={index === path.length - 1} onClick={() => setPath(path.slice(0, index + 1))}>{crumb.name}</button>
                </React.Fragment>)}
              {loading ? <span className="cloud-loading" role="status"><span className="spinner"/> {opening ? `در حال باز کردن «${applied || path[path.length - 1].name}»…` : "در حال بارگذاری…"}</span> : null}
            </nav>
            {error ? <p role="alert" className="cloud-pad">{error} <button className="btn btn-sm btn-secondary" onClick={() => void load(null)}>دوباره امتحان کنید</button></p> : null}
            {opening ? <ul className="cloud-rows" aria-hidden="true">{Array.from({ length: 6 }, (_, i) => <li key={i} className="cloud-row cloud-skel"><span className="cloud-thumb"/><span className="cloud-skel-lines"><i/><i/></span></li>)}</ul> : null}
            {!loading && !error && !files.length ? <p className="cloud-pad cloud-empty">اینجا چیزی برای نمایش نیست.</p> : null}

            {folders.length ? <ul className="cloud-rows">{folders.map(file => <li key={file.id}>
              <button type="button" className="cloud-row cloud-folder" onClick={() => open(file)} disabled={loading}>
                <span className="cloud-thumb" data-kind="folder"><Icon name="projects" size={20}/></span>
                <span className="cloud-name wrap-safe">{file.name}</span><span className="cloud-sep" aria-hidden="true">›</span>
              </button></li>)}</ul> : null}

            {usable.length ? <>
              <div className="cloud-selectbar"><label><input type="checkbox" checked={allPicked} onChange={togglePage}/> انتخاب همه‌ی این فهرست ({usable.length.toLocaleString("fa-IR")})</label></div>
              <ul className="cloud-rows">{usable.map(file => <li key={file.id} className="cloud-row" data-picked={picked.has(file.id)}>
                <input type="checkbox" checked={picked.has(file.id)} onChange={() => toggle(file)} aria-label={`انتخاب ${file.name}`}/>
                <Preview file={file} onOpen={() => { setPreview(file); setPlaying(file.kind === "video" || file.kind === "audio"); }}/>
                <label className="cloud-info"><span className="cloud-name wrap-safe">{file.name}</span><Meta file={file}/></label>
              </li>)}</ul></> : null}

            {other.length ? <div className="cloud-other">
              <button type="button" className="btn btn-sm btn-ghost" aria-expanded={showOther} onClick={() => setShowOther(value => !value)}>{showOther ? "پنهان‌کردن" : "نمایش"} فایل‌های قابل‌وارد‌کردن‌نشده ({other.length.toLocaleString("fa-IR")})</button>
              {showOther ? <ul className="cloud-rows">{other.map(file => <li key={file.id} className="cloud-row cloud-disabled">
                <Preview file={file}/>
                <span className="cloud-info"><span className="cloud-name wrap-safe">{file.name}</span>
                  <span className="cloud-meta"><span className="cloud-chip">{file.native ? "سند گوگل؛ قابل‌وارد‌کردن نیست" : "نوع فایل پشتیبانی نمی‌شود"}</span></span></span>
              </li>)}</ul> : null}</div> : null}

            {next ? <div className="cloud-pad"><button className="btn btn-sm btn-secondary" disabled={loading} onClick={() => void load(next)}>{loading ? "در حال بارگذاری…" : "نمایش بیشتر"}</button></div> : null}
          </div>
        </>}

      {preview ? <div className="cloud-preview" role="dialog" aria-label={`پیش‌نمایش ${preview.name}`} onMouseDown={event => { if (event.target === event.currentTarget) { setPreview(null); setPlaying(false); } }}>
        <div className="cloud-preview-card">
          {playing && (preview.kind === "video" || preview.kind === "audio")
            // Google's own player straight from Drive: nothing is downloaded to this server and the file does not pass through it.
            ? <iframe className="cloud-player" data-kind={preview.kind} title={preview.name} src={`https://drive.google.com/file/d/${encodeURIComponent(preview.id)}/preview`}
                allow="autoplay; fullscreen" allowFullScreen referrerPolicy="no-referrer"/>
            : preview.thumbnail ? <img src={thumb(preview.thumbnail, 800)} alt={preview.name} referrerPolicy="no-referrer"/> : <div className="cloud-noimg"><Icon name={kindIcon(preview)} size={40}/></div>}
          <b className="wrap-safe">{preview.name}</b><Meta file={preview}/>
          <div className="set-actions">
            {preview.kind === "video" || preview.kind === "audio"
              ? <button className="btn btn-sm btn-secondary" onClick={() => setPlaying(value => !value)}>{playing ? "توقف پخش" : `پخش ${preview.kind === "audio" ? "صدا" : "ویدیو"} از گوگل درایو`}</button> : null}
            <a className="btn btn-sm btn-ghost" href={`https://drive.google.com/file/d/${encodeURIComponent(preview.id)}/view`} target="_blank" rel="noopener noreferrer">باز کردن در گوگل درایو</a>
            <button className="btn btn-sm btn-primary" onClick={() => { if (!picked.has(preview.id)) toggle(preview); setPreview(null); setPlaying(false); }}>{picked.has(preview.id) ? "انتخاب شده ✓" : "انتخاب این فایل"}</button>
            <button className="btn btn-sm btn-secondary" onClick={() => { setPreview(null); setPlaying(false); }}>بستن</button>
          </div>
          {playing ? <small className="cloud-note">پخش با حساب گوگلِ همین مرورگر انجام می‌شود. اگر «دسترسی ندارید» دیدید یا ویدیو بالا نیامد، با همان حسابی که درایو را وصل کرده‌اید در گوگل وارد شوید یا فایل را در گوگل درایو باز کنید.</small> : null}
        </div></div> : null}

      <footer className="cloud-foot">
        <small className="cloud-summary">{chosen.length
          ? <>{chosen.length.toLocaleString("fa-IR")} فایل انتخاب شد{chosenBytes ? <> · <bdi dir="ltr">{formatBytes(chosenBytes)}</bdi></> : null}{chosenSeconds ? <> · <bdi dir="ltr">{clock(chosenSeconds)}</bdi></> : null}</>
          : "ویدیو، صدا یا تصویر انتخاب کنید"}</small>
        <button className="btn btn-sm btn-secondary" onClick={onClose}>انصراف</button>
        <button className="btn btn-sm btn-primary" disabled={!chosen.length || busy} onClick={() => void start()}>{busy ? "در حال شروع…" : chosen.length ? `وارد کردن ${chosen.length.toLocaleString("fa-IR")} فایل` : "وارد کردن"}</button>
      </footer>
  </>;
  if (embedded) return <div className="addmedia-pane cloud-embedded">{body}</div>;
  return <div className="overlay" role="dialog" aria-modal="true" aria-label="وارد کردن از گوگل درایو" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="dialog cloud-dialog">{body}</div></div>;
}
