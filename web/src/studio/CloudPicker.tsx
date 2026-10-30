import React from "react";
import { NavLink } from "react-router-dom";
import { api, CloudFile, CloudProvider } from "../api";
import { Icon } from "../components/Icon";
import { formatBytes } from "../format";
import { friendlyError } from "../ui";

type Crumb = { id: string; name: string };
const PROVIDER = "googledrive";
const MEDIA = [["", "All media"], ["video", "Video"], ["audio", "Audio"], ["image", "Images"]] as const;
const SORTS = [["name", "Name"], ["modified", "Modified"], ["size", "Size"]] as const;

function reconnectNeeded(text: string) { return /reconnect_required|COMPOSIO_(?:CONNECTION|POLICY)|not connected/i.test(text); }

/** Browse Google Drive and choose files to import. Importing itself is started by the caller, which also tracks progress. */
export function CloudPicker({ onClose, onImport }: { onClose: () => void; onImport: (files: CloudFile[]) => Promise<void> | void }) {
  const [provider, setProvider] = React.useState<CloudProvider | null | undefined>(undefined);
  const [path, setPath] = React.useState<Crumb[]>([{ id: "root", name: "My Drive" }]);
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
  const request = React.useRef(0);
  const folder = path[path.length - 1].id;

  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  React.useEffect(() => {
    let live = true;
    api.cloudProviders().then(result => { if (live) setProvider(result.providers.find(item => item.id === PROVIDER) || null); })
      .catch(e => { if (live) { setProvider(null); setError(friendlyError(e, "check Google Drive")); } });
    return () => { live = false; };
  }, []);

  const load = React.useCallback(async (more: string | null) => {
    const id = ++request.current;
    setLoading(true); setError("");
    try {
      const result = await api.cloudFiles(PROVIDER, { folder, q: applied, media, sort, page_token: more });
      if (id !== request.current) return;
      setFiles(current => more ? [...current, ...result.files] : result.files);
      setNext(result.next_page_token);
    } catch (e) {
      if (id === request.current) setError(friendlyError(e, "load Google Drive") + (reconnectNeeded(String(e)) ? " Reconnect Google Drive in Settings." : ""));
    } finally { if (id === request.current) setLoading(false); }
  }, [folder, applied, media, sort]);

  React.useEffect(() => { if (provider?.connected) void load(null); }, [provider, load]);

  const toggle = (file: CloudFile) => setPicked(current => {
    const copy = new Map(current);
    if (copy.has(file.id)) copy.delete(file.id); else copy.set(file.id, file);
    return copy;
  });
  const open = (file: CloudFile) => { setApplied(""); setQuery(""); setPath(current => [...current, { id: file.id, name: file.name }]); };
  const search = (event: React.FormEvent) => { event.preventDefault(); setApplied(query.trim()); };
  const importable = (file: CloudFile) => !file.is_folder && !file.native && !!file.kind;
  async function start() {
    setBusy(true);
    try { await onImport([...picked.values()]); onClose(); } catch (e) { setError(friendlyError(e, "start the import")); setBusy(false); }
  }

  return <div className="overlay" role="dialog" aria-modal="true" aria-label="Import from Google Drive" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="dialog" style={{ width: "min(720px, 100%)", display: "grid", gap: 12, gridTemplateRows: "auto auto 1fr auto", maxHeight: "calc(100dvh - 32px)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}><h3 style={{ margin: 0, flex: 1 }}>Import from Google Drive</h3>
        <button className="icon-btn" onClick={onClose} aria-label="Close"><Icon name="close" size={18}/></button></div>

      {provider === undefined ? <p role="status"><span className="spinner"/> Checking Google Drive… the first check can take up to a minute.</p>
        : !provider?.connected ? <div className="notice" role="status" style={{ display: "grid", gap: 8 }}>
          <b>{provider && !provider.enabled ? "Google Drive is not enabled on this server." : "Google Drive is not connected."}</b>
          {error ? <span>{error}</span> : <span>Connect your account in Settings, then come back here. Your files stay in Drive until you choose them.</span>}
          <NavLink className="btn btn-sm btn-primary" to="/settings#integrations" onClick={onClose}>Open Connected services</NavLink></div>
        : <>
          <form onSubmit={search} style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <input className="input" style={{ flex: "1 1 200px" }} type="search" placeholder="Search in Drive" aria-label="Search Google Drive" value={query} onChange={event => setQuery(event.target.value)}/>
            <select className="input" aria-label="File type" value={media} onChange={event => setMedia(event.target.value as typeof media)}>{MEDIA.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
            <select className="input" aria-label="Sort by" value={sort} onChange={event => setSort(event.target.value as typeof sort)}>{SORTS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
            <button className="btn btn-sm btn-secondary" type="submit">Search</button>
          </form>
          <div style={{ overflow: "auto", minHeight: 160, border: "1px solid var(--border)", borderRadius: "var(--radius-md)" }}>
            <nav aria-label="Folder path" style={{ display: "flex", gap: 6, flexWrap: "wrap", padding: "8px 10px", borderBottom: "1px solid var(--border-subtle)" }}>
              {applied ? <span>Results for “{applied}” <button className="btn btn-sm btn-ghost" onClick={() => { setApplied(""); setQuery(""); }}>Clear</button></span>
                : path.map((crumb, index) => <button key={crumb.id} className="btn btn-sm btn-ghost" disabled={index === path.length - 1} onClick={() => setPath(path.slice(0, index + 1))}>{index ? "/ " : ""}{crumb.name}</button>)}
            </nav>
            {error ? <p role="alert" style={{ padding: 12 }}>{error} <button className="btn btn-sm btn-secondary" onClick={() => void load(null)}>Try again</button></p> : null}
            {loading && !files.length ? <p role="status" style={{ padding: 12 }}><span className="spinner"/> Loading from Google Drive… this can take up to a minute.</p> : null}
            {!loading && !error && !files.length ? <p style={{ padding: 12 }}>Nothing to show here.</p> : null}
            <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {files.map(file => <li key={file.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", borderBottom: "1px solid var(--border-subtle)" }}>
                {importable(file)
                  ? <input type="checkbox" checked={picked.has(file.id)} onChange={() => toggle(file)} aria-label={`Select ${file.name}`}/>
                  : <span style={{ width: 16 }}/>}
                <Icon name={file.is_folder ? "library" : file.kind === "video" ? "video" : file.kind === "audio" ? "music" : file.kind === "image" ? "image" : "alert"} size={18}/>
                {file.is_folder
                  ? <button className="btn btn-ghost" style={{ flex: 1, justifyContent: "flex-start", textAlign: "start" }} onClick={() => open(file)}><span className="wrap-safe">{file.name}</span></button>
                  : <label style={{ flex: 1, minWidth: 0, opacity: importable(file) ? 1 : 0.55 }}><span className="wrap-safe">{file.name}</span>
                    <small style={{ display: "block" }}>{file.native ? "Google document · cannot be imported" : !file.kind ? "Unsupported file type" : [file.size ? formatBytes(file.size) : "", file.duration ? `${Math.round(file.duration)}s` : "", file.modified ? new Date(file.modified).toLocaleDateString() : ""].filter(Boolean).join(" · ")}</small></label>}
              </li>)}
            </ul>
            {next ? <div style={{ padding: 10 }}><button className="btn btn-sm btn-secondary" disabled={loading} onClick={() => void load(next)}>{loading ? "Loading…" : "Load more"}</button></div> : null}
          </div>
        </>}

      <div style={{ display: "flex", gap: 8, alignItems: "center", justifyContent: "flex-end" }}>
        <small style={{ marginInlineEnd: "auto" }}>{picked.size ? `${picked.size} selected` : "Select videos, audio or images"}</small>
        <button className="btn btn-sm btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn btn-sm btn-primary" disabled={!picked.size || busy} onClick={() => void start()}>{busy ? "Starting…" : `Import ${picked.size || ""}`.trim()}</button>
      </div>
    </div></div>;
}
