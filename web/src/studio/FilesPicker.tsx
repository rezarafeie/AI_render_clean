import React from "react";
import { api, StudioFile, StudioFiles } from "../api";
import { ConfirmDelete, DeleteTarget } from "../components/ConfirmDelete";
import { Icon } from "../components/Icon";
import { formatBytes, parseTime } from "../format";
import { friendlyError } from "../ui";

const KINDS = [["", "همه"], ["video", "ویدیو"], ["audio", "صدا"], ["image", "تصویر"], ["output", "ساخته‌شده"]] as const;

// The library, kept for the session: it opens at once with what was loaded before (prefetched when the studio opens) and refreshes behind it.
let cached: StudioFiles | null = null;
let inflight: Promise<StudioFiles> | null = null;
export function prefetchLibrary(): Promise<StudioFiles> {
  if (!inflight) inflight = api.studioFiles().then(value => { cached = value; return value; }).finally(() => { inflight = null; });
  return inflight;
}

/** Everything the person has stored, from any chat: choose files to use again without uploading them, or delete the ones they no longer need. */
export function FilesPicker({ onClose, onAttach, embedded }: { onClose: () => void; onAttach: (files: StudioFile[]) => Promise<void> | void;
  /** Inside the "add files" dialog: no frame of its own. */ embedded?: boolean }) {
  const [data, setData] = React.useState<StudioFiles | null>(cached);
  const [error, setError] = React.useState("");
  const [query, setQuery] = React.useState("");
  const [kind, setKind] = React.useState<(typeof KINDS)[number][0]>("");
  const [showClips, setShowClips] = React.useState(false);
  const [picked, setPicked] = React.useState<Map<string, StudioFile>>(new Map());
  const [busy, setBusy] = React.useState(false);
  const [deleting, setDeleting] = React.useState<DeleteTarget | null>(null);

  const load = React.useCallback(() => prefetchLibrary().then(value => { setData(value); setError(""); }).catch(e => { if (!cached) setError(friendlyError(e, "load your files")); }), []);
  React.useEffect(() => { void load(); }, [load]);
  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape" && !deleting && !embedded) onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, deleting, embedded]);

  const clipCount = data?.files.filter(file => file.folder === "discovery").length ?? 0;
  const shown = React.useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return (data?.files || []).filter(file => (showClips === (file.folder === "discovery")) && (showClips || !kind || (kind === "output" ? file.source === "output" : file.kind === kind)) && (!needle || `${file.name} ${file.conversation_title}`.toLocaleLowerCase().includes(needle)));
  }, [data, query, kind, showClips]);
  const toggle = (file: StudioFile) => setPicked(current => { const next = new Map(current); if (next.has(file.id)) next.delete(file.id); else next.set(file.id, file); return next; });
  async function use() {
    setBusy(true); setError("");
    try { await onAttach([...picked.values()]); onClose(); } catch (e) { setError(friendlyError(e, "add these files")); setBusy(false); }
  }
  const ask = (file: StudioFile) => setDeleting({
    title: "Delete this file?", what: file.name,
    detail: `${formatBytes(file.size)} will be freed. Chats and projects that already used it keep working, and nothing else is deleted.`,
    run: async () => { await api.deleteStudioFile(file.id); setPicked(current => { const next = new Map(current); next.delete(file.id); return next; }); await load(); },
  });
  const preparingClips = busy && Array.from(picked.keys()).some(id => id.startsWith("clip:"));
  const used = data?.usage ?? 0, quota = data?.quota ?? 0;
  const percent = quota ? Math.min(100, (used / quota) * 100) : 0;

  const KIND_FA: Record<string, string> = { video: "ویدیو", audio: "صدا", image: "تصویر" };
  const SOURCE_FA: Record<StudioFile["source"], string> = { upload: "آپلود", cloud: "گوگل درایو", output: "ساخته‌شده", discovery: "کلیپ کشف‌شده" };
  const FILTERS = [["", "همه"], ["video", "ویدیو"], ["audio", "صدا"], ["image", "تصویر"], ["output", "ساخته‌شده"]] as const;
  const chosen = [...picked.values()];
  const chosenBytes = chosen.reduce((sum, file) => sum + (file.size || 0), 0);
  const allPicked = shown.length > 0 && shown.every(file => picked.has(file.id));
  const togglePage = () => setPicked(current => {
    const next = new Map(current);
    if (allPicked) shown.forEach(file => next.delete(file.id)); else shown.forEach(file => next.set(file.id, file));
    return next;
  });
  // The same layout as the Google Drive tab (cloud-* classes): search, a segmented filter, a folder row, rows with chips, a footer.
  const body = <>
      {embedded ? null : <header className="cloud-head"><h3>فایل‌های شما</h3>
        <button className="icon-btn" onClick={onClose} aria-label="بستن"><Icon name="close" size={18}/></button></header>}
      <div className="cloud-tools">
        <input className="input cloud-search" type="search" placeholder="جست‌وجو در فایل‌های شما" aria-label="جست‌وجو در فایل‌های شما" value={query} onChange={event => setQuery(event.target.value)}/>
      </div>
      <div className="cloud-filters">
        {showClips ? <span/> : <div className="cloud-seg" role="group" aria-label="نوع فایل">
          {FILTERS.map(([value, label]) => <button key={value || "all"} type="button" className="cloud-seg-btn" aria-pressed={kind === value} onClick={() => setKind(value)}>{label}</button>)}
        </div>}
        {data ? <small className="cloud-date" title="فضای استفاده‌شده">{quota ? `${formatBytes(used)} از ${formatBytes(quota)}` : `${formatBytes(used)} · بدون محدودیت`}</small> : null}
      </div>
      <div className="cloud-list" aria-busy={!data}>
        <nav className="cloud-crumbs" aria-label="مسیر">
          {showClips ? <><button className="btn btn-sm btn-ghost" onClick={() => { setShowClips(false); setQuery(""); }}>فایل‌های شما</button><span className="cloud-sep" aria-hidden="true">‹</span><button className="btn btn-sm btn-ghost" disabled>کلیپ‌های کشف‌شده</button></>
            : <button className="btn btn-sm btn-ghost" disabled>فایل‌های شما</button>}
          {!data && !error ? <span className="cloud-loading" role="status"><span className="spinner"/> در حال بارگذاری…</span> : null}
        </nav>
        {error ? <p role="alert" className="cloud-pad">{error} <button className="btn btn-sm btn-secondary" onClick={() => void load()}>دوباره امتحان کنید</button></p> : null}
        {!data && !error ? <ul className="cloud-rows" aria-hidden="true">{Array.from({ length: 6 }, (_, i) => <li key={i} className="cloud-row cloud-skel"><span className="cloud-thumb"/><span className="cloud-skel-lines"><i/><i/></span></li>)}</ul> : null}
        {data && !showClips && clipCount ? <ul className="cloud-rows"><li>
          <button type="button" className="cloud-row cloud-folder" onClick={() => { setShowClips(true); setQuery(""); }}>
            <span className="cloud-thumb" data-kind="folder"><Icon name="projects" size={20}/></span>
            <span className="cloud-name wrap-safe">کلیپ‌های کشف‌شده ({clipCount.toLocaleString("fa-IR")})</span><span className="cloud-sep" aria-hidden="true">›</span>
          </button></li></ul> : null}
        {data && !shown.length && !error ? <p className="cloud-pad cloud-empty">{showClips ? (query ? "کلیپی پیدا نشد." : "هنوز کلیپی از ویدیوهای بلند کشف نشده.") : data.files.length ? "فایلی با این جست‌وجو پیدا نشد." : "فایل‌هایی که آپلود می‌کنید یا می‌سازید اینجا می‌مانند و در هر چتی دوباره قابل استفاده‌اند."}</p> : null}
        {shown.length ? <>
          <div className="cloud-selectbar"><label><input type="checkbox" checked={allPicked} onChange={togglePage}/> انتخاب همه‌ی این فهرست ({shown.length.toLocaleString("fa-IR")})</label></div>
          <ul className="cloud-rows">{shown.map(file => <li key={file.id} className="cloud-row" data-picked={picked.has(file.id)}>
            <input type="checkbox" checked={picked.has(file.id)} onChange={() => toggle(file)} aria-label={`انتخاب ${file.name}`}/>
            <span className="cloud-thumb" style={{ width: 78, height: 56 }} data-kind={file.kind}><Icon name={file.kind === "video" ? "video" : file.kind === "audio" ? "music" : "image"} size={20}/></span>
            <label className="cloud-info" onClick={() => toggle(file)}><span className="cloud-name wrap-safe" dir="auto">{file.name}</span>
              <span className="cloud-meta">
                <span className="cloud-chip" data-kind={file.kind}>{KIND_FA[file.kind] || file.kind}</span>
                {file.size ? <span className="cloud-chip"><bdi dir="ltr">{formatBytes(file.size)}</bdi></span> : null}
                <span className="cloud-chip">{SOURCE_FA[file.source] || file.source}</span>
                {file.conversation_title ? <span className="cloud-date wrap-safe" dir="auto">{file.conversation_title}</span> : null}
                <span className="cloud-date">{new Date(parseTime(file.created_at)).toLocaleDateString("fa-IR")}</span>
              </span></label>
            {file.source !== "discovery" && <button type="button" className="icon-btn trash-btn" aria-label={`حذف ${file.name}`} data-tip="حذف" onClick={() => ask(file)}><Icon name="trash" size={16}/></button>}
          </li>)}</ul></> : null}
      </div>
      <footer className="cloud-foot">
        <small className="cloud-summary" role="status">{preparingClips ? "برش با وضوح منبع آماده و خودکار پیوست می‌شود."
          : chosen.length ? <>{chosen.length.toLocaleString("fa-IR")} فایل انتخاب شد{chosenBytes ? <> · <bdi dir="ltr">{formatBytes(chosenBytes)}</bdi></> : null}</> : "ویدیو، صدا یا تصویر انتخاب کنید"}</small>
        <button className="btn btn-sm btn-secondary" onClick={onClose}>انصراف</button>
        <button className="btn btn-sm btn-primary" disabled={!picked.size || busy} onClick={() => void use()}>{busy ? (preparingClips ? <><span className="spinner"/> آماده‌سازی کلیپ…</> : "در حال افزودن…") : picked.size ? `افزودن ${picked.size.toLocaleString("fa-IR")} فایل` : "افزودن"}</button>
      </footer>
      <ConfirmDelete target={deleting} onClose={() => setDeleting(null)}/>
  </>;
  if (embedded) return <div className="addmedia-pane cloud-embedded">{body}</div>;
  return <div className="overlay" role="dialog" aria-modal="true" aria-label="فایل‌های شما" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="dialog cloud-dialog">{body}</div>
  </div>;
}
