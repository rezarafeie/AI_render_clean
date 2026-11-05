import React from "react";
import { api, StudioFile, StudioFiles } from "../api";
import { ConfirmDelete, DeleteTarget } from "../components/ConfirmDelete";
import { Icon } from "../components/Icon";
import { formatBytes, parseTime } from "../format";
import { friendlyError } from "../ui";

const KINDS = [["", "All"], ["video", "Video"], ["audio", "Audio"], ["image", "Images"], ["output", "Made here"]] as const;
const SOURCE: Record<StudioFile["source"], string> = { upload: "Uploaded", cloud: "Google Drive", output: "Made here" };

/** Everything the person has stored, from any chat: choose files to use again without uploading them, or delete the ones they no longer need. */
export function FilesPicker({ onClose, onAttach }: { onClose: () => void; onAttach: (files: StudioFile[]) => Promise<void> | void }) {
  const [data, setData] = React.useState<StudioFiles | null>(null);
  const [error, setError] = React.useState("");
  const [query, setQuery] = React.useState("");
  const [kind, setKind] = React.useState<(typeof KINDS)[number][0]>("");
  const [picked, setPicked] = React.useState<Map<string, StudioFile>>(new Map());
  const [busy, setBusy] = React.useState(false);
  const [deleting, setDeleting] = React.useState<DeleteTarget | null>(null);

  const load = React.useCallback(() => api.studioFiles().then(value => { setData(value); setError(""); }).catch(e => setError(friendlyError(e, "load your files"))), []);
  React.useEffect(() => { void load(); }, [load]);
  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape" && !deleting) onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, deleting]);

  const shown = React.useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return (data?.files || []).filter(file => (!kind || (kind === "output" ? file.source === "output" : file.kind === kind)) && (!needle || `${file.name} ${file.conversation_title}`.toLocaleLowerCase().includes(needle)));
  }, [data, query, kind]);
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
  const used = data?.usage ?? 0, quota = data?.quota ?? 0;
  const percent = quota ? Math.min(100, (used / quota) * 100) : 0;

  return <div className="overlay" role="dialog" aria-modal="true" aria-label="Your files" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="dialog" style={{ width: "min(720px, 100%)", display: "grid", gap: 12, gridTemplateRows: "auto auto auto 1fr auto", maxHeight: "calc(100dvh - 32px)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}><h3 style={{ margin: 0, flex: 1 }}>Your files</h3>
        <button className="icon-btn" onClick={onClose} aria-label="Close"><Icon name="close" size={18}/></button></div>
      {data ? <div className="files-usage" role="group" aria-label="Storage used">
        <div className="files-usage-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(percent)}><span style={{ width: `${percent}%` }} data-high={percent > 90 || undefined}/></div>
        <small>{formatBytes(used)} of {formatBytes(quota)} used by uploads</small>
      </div> : <span/>}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <input className="input" style={{ flex: "1 1 200px" }} type="search" placeholder="Search your files" aria-label="Search your files" value={query} onChange={event => setQuery(event.target.value)}/>
        <select className="input" aria-label="File type" value={kind} onChange={event => setKind(event.target.value as typeof kind)}>{KINDS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
      </div>
      <div style={{ overflow: "auto", minHeight: 160, border: "1px solid var(--border)", borderRadius: "var(--radius-md)" }}>
        {error ? <p role="alert" style={{ padding: 12 }}>{error} <button className="btn btn-sm btn-secondary" onClick={() => void load()}>Try again</button></p> : null}
        {!data && !error ? <p role="status" style={{ padding: 12 }}><span className="spinner"/> Loading your files…</p> : null}
        {data && !shown.length && !error ? <p style={{ padding: 12 }}>{data.files.length ? "No file matches." : "Files you upload or make will be kept here, and you can use them again in any chat."}</p> : null}
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {shown.map(file => <li key={file.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", borderBottom: "1px solid var(--border-subtle)" }}>
            <input type="checkbox" checked={picked.has(file.id)} onChange={() => toggle(file)} aria-label={`Select ${file.name}`}/>
            <Icon name={file.kind === "video" ? "video" : file.kind === "audio" ? "music" : "image"} size={18}/>
            <label style={{ flex: 1, minWidth: 0 }}><span className="wrap-safe" dir="auto">{file.name}</span>
              <small style={{ display: "block" }} dir="auto">{[SOURCE[file.source], formatBytes(file.size), file.conversation_title, new Date(parseTime(file.created_at)).toLocaleDateString()].filter(Boolean).join(" · ")}</small></label>
            <button type="button" className="icon-btn trash-btn" aria-label={`Delete ${file.name}`} data-tip="Delete" onClick={() => ask(file)}><Icon name="trash" size={16}/></button>
          </li>)}
        </ul>
      </div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", justifyContent: "flex-end" }}>
        <small style={{ marginInlineEnd: "auto" }}>{picked.size ? `${picked.size} selected` : "Select files to use in this chat"}</small>
        <button className="btn btn-sm btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn btn-sm btn-primary" disabled={!picked.size || busy} onClick={() => void use()}>{busy ? "Adding…" : `Use ${picked.size || ""}`.trim()}</button>
      </div>
    </div>
    <ConfirmDelete target={deleting} onClose={() => setDeleting(null)}/>
  </div>;
}
