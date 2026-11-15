import React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { adminManageRequest, setAdminViewAs } from "../api";
import { AuthenticatedMedia } from "../AuthenticatedMedia";
import { Icon } from "../components/Icon";
import { currentLang } from "../i18n/lang";
import { LoadingState, friendlyError } from "../ui";

const BASE = "/api/admin/manage";
type UserRow = { id: number; email: string; name: string; created_at: string; is_active: boolean; chats: number; projects: number; jobs: number; files: number; storage_bytes: number; last_active: string | null };
type Chat = { id: string; title: string; language: string; messages: number; status?: string; created_at: string; updated_at: string };
type ChatRow = { id: string; title: string; user: { id: string; name: string; email: string }; status: string; messages: number; projects: number; files: number; created_at: string; updated_at: string };
type GlobalFile = { id: string; conversation_id: string; chat_title: string; name: string; kind: string; mime: string; size: number; created_at: string; user: { id: string; name: string } };
type Project = { id: string; conversation_id: string; title: string; engine: string; status: string; job: string | null; version: number; created_at: string; updated_at: string };
type FileRow = { id: string; conversation_id: string; name: string; kind: string; mime: string; size: number; created_at: string };
type JobRow = { id: string; title: string | null; status: string; stage: string | null; progress: number; message: string; created_at: string; updated_at: string | null };
type Detail = { user: Omit<UserRow, "chats" | "projects" | "jobs" | "files" | "storage_bytes" | "last_active">; conversations: Chat[]; projects: Project[]; files: FileRow[]; jobs: JobRow[]; storage_bytes: number };

const bytes = (value: number) => value >= 1e9 ? `${(value / 1e9).toFixed(2)} GB` : value >= 1e6 ? `${(value / 1e6).toFixed(1)} MB` : value >= 1e3 ? `${Math.round(value / 1e3)} KB` : `${value} B`;
const when = (value?: string | null) => {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString(currentLang() === "fa" ? "fa-IR" : undefined, { dateStyle: "medium", timeStyle: "short" });
};
const tone = (status: string) => ["done", "completed", "ready"].includes(status) ? "ok" : ["error", "failed", "canceled", "cancelled"].includes(status) ? "bad" : ["running", "queued", "waiting", "awaiting_input", "awaiting_confirmation"].includes(status) ? "warn" : "idle";

function Status({ value, label }: { value: string; label?: string }) { return <span className="adm-status" data-tone={tone(value)}><i/>{label || value}</span>; }

const STATUS_LABEL: Record<string, string> = { running: "Working", waiting: "Waiting", done: "Done", failed: "Failed", stopped: "Stopped", idle: "No project" };

/** A chat in the lists is only a link, its title, its owner, the time and its status: the chat itself is opened in the chat page (read-only for an administrator). */
function ChatLink({ id, user, children }: { id: string; user: string; children: React.ReactNode }) {
  return <Link className="adm-chat-link" to={`/studio/${id}`} onClick={() => setAdminViewAs(user)} dir="auto">{children}</Link>;
}

function ChatTable({ rows, showUser }: { rows: { id: string; title: string; user: string; userName?: string; status: string; updated_at: string; messages: number }[]; showUser: boolean }) {
  return <div className="adm-chats" role="table" aria-label="Chats">
    <div className="adm-chat-head" role="row"><span>Chat</span><span>{showUser ? "User" : "Messages"}</span><span>Last activity</span><span>Status</span></div>
    {rows.map(chat => <div key={chat.id} className="adm-chat-row" role="row">
      <span className="adm-chat-title"><ChatLink id={chat.id} user={chat.user}>{chat.title || chat.id}</ChatLink></span>
      <span>{showUser ? <Link to={`/settings/users/${chat.user}`} data-no-translate><small>{chat.userName || `#${chat.user}`}</small></Link> : <small>{chat.messages} messages</small>}</span>
      <span><small>{when(chat.updated_at)}</small></span>
      <span><Status value={chat.status || "idle"} label={STATUS_LABEL[chat.status || "idle"] || chat.status}/></span>
    </div>)}
  </div>;
}

function AllChats({ query }: { query: string }) {
  const [rows, setRows] = React.useState<ChatRow[]>([]);
  const [total, setTotal] = React.useState(0);
  const [status, setStatus] = React.useState("");
  const [loaded, setLoaded] = React.useState(false);
  const [error, setError] = React.useState("");
  const load = React.useCallback((offset: number, replace: boolean) => {
    adminManageRequest<{ total: number; chats: ChatRow[] }>(`/chats?query=${encodeURIComponent(query)}&status=${status}&limit=50&offset=${offset}`)
      .then(r => { setRows(prev => replace ? r.chats : [...prev, ...r.chats]); setTotal(r.total); setLoaded(true); setError(""); }).catch(e => setError(friendlyError(e, "load chats")));
  }, [query, status]);
  React.useEffect(() => { setLoaded(false); const handle = window.setTimeout(() => load(0, true), query ? 250 : 0); return () => window.clearTimeout(handle); }, [load, query]);
  return <>
    <div className="segmented adm-tabs" role="tablist" aria-label="Chat status">{["", "running", "waiting", "done", "failed"].map(item => <button key={item || "all"} role="tab" aria-selected={status === item} aria-pressed={status === item} onClick={() => setStatus(item)}>{item ? STATUS_LABEL[item] : "All"}</button>)}</div>
    {error ? <p className="notice" data-tone="error" role="alert">{error}</p> : null}
    {!loaded && !error ? <LoadingState label="Loading chats" rows={4}/> : null}
    {loaded ? <>
      <p className="adm-count">{total} chats</p>
      <ChatTable showUser rows={rows.map(r => ({ id: r.id, title: r.title, user: r.user.id, userName: r.user.name || r.user.email, status: r.status, updated_at: r.updated_at, messages: r.messages }))}/>
      {!rows.length ? <p className="adm-empty">No chat matches.</p> : null}
      {rows.length < total ? <button className="btn btn-sm btn-secondary adm-more-btn" onClick={() => load(rows.length, false)}>Show more</button> : null}
    </> : null}
  </>;
}

function AllFiles({ query }: { query: string }) {
  const [rows, setRows] = React.useState<GlobalFile[]>([]);
  const [total, setTotal] = React.useState(0);
  const [kind, setKind] = React.useState("");
  const [loaded, setLoaded] = React.useState(false);
  const [error, setError] = React.useState("");
  const load = React.useCallback((offset: number, replace: boolean) => {
    adminManageRequest<{ total: number; files: GlobalFile[] }>(`/files?query=${encodeURIComponent(query)}&kind=${kind}&limit=60&offset=${offset}`)
      .then(r => { setRows(prev => replace ? r.files : [...prev, ...r.files]); setTotal(r.total); setLoaded(true); setError(""); }).catch(e => setError(friendlyError(e, "load files")));
  }, [query, kind]);
  React.useEffect(() => { setLoaded(false); const handle = window.setTimeout(() => load(0, true), query ? 250 : 0); return () => window.clearTimeout(handle); }, [load, query]);
  return <>
    <div className="segmented adm-tabs" role="tablist" aria-label="File kind">{["", "video", "image", "audio"].map(item => <button key={item || "all"} role="tab" aria-selected={kind === item} aria-pressed={kind === item} onClick={() => setKind(item)}>{item ? item[0].toUpperCase() + item.slice(1) : "All"}</button>)}</div>
    {error ? <p className="notice" data-tone="error" role="alert">{error}</p> : null}
    {!loaded && !error ? <LoadingState label="Loading files" rows={4}/> : null}
    {loaded ? <>
      <p className="adm-count">{total} files</p>
      <div className="adm-files">{rows.map(file => <div key={file.id} className="adm-file">
        <div className="adm-file-media">{file.kind === "image" ? <AuthenticatedMedia as="img" src={`${BASE}/files/${file.id}`} alt={file.name} loading="lazy"/>
          : file.kind === "video" ? <AuthenticatedMedia as="video" controls preload="none" src={`${BASE}/files/${file.id}`}/>
          : file.kind === "audio" ? <AuthenticatedMedia as="audio" controls preload="none" src={`${BASE}/files/${file.id}`}/> : <Icon name="library" size={22}/>}</div>
        <b className="wrap-safe" data-no-translate>{file.name}</b>
        <small>{file.kind} · <span data-no-translate>{bytes(file.size)}</span> · {when(file.created_at)}</small>
        <small><Link to={`/settings/users/${file.user.id}`} data-no-translate>{file.user.name || `#${file.user.id}`}</Link> · <ChatLink id={file.conversation_id} user={file.user.id}>{file.chat_title || "Open the chat"}</ChatLink></small>
      </div>)}</div>
      {!rows.length ? <p className="adm-empty">No file matches.</p> : null}
      {rows.length < total ? <button className="btn btn-sm btn-secondary adm-more-btn" onClick={() => load(rows.length, false)}>Show more</button> : null}
    </> : null}
  </>;
}

export function AdminUsers() {
  const [rows, setRows] = React.useState<UserRow[] | null>(null);
  const [total, setTotal] = React.useState(0);
  const [query, setQuery] = React.useState("");
  const [error, setError] = React.useState("");
  const [section, setSection] = React.useState<"users" | "chats" | "files">("users");
  React.useEffect(() => {
    const handle = window.setTimeout(() => {
      adminManageRequest<{ total: number; users: UserRow[] }>(`/users?query=${encodeURIComponent(query)}`).then(r => { setRows(r.users); setTotal(r.total); setError(""); })
        .catch(e => setError(friendlyError(e, "load users")));
    }, query ? 250 : 0);
    return () => window.clearTimeout(handle);
  }, [query]);
  return <div className="page adm-page">
    <header className="page-header"><div><h1>Users &amp; projects</h1><p>Everyone who uses the app, with their chats, projects, renders and files.</p></div>
      <Link className="btn btn-sm btn-secondary" to="/settings#admin"><Icon name="chevron" size={14}/>Settings</Link></header>
    <div className="segmented adm-tabs" role="tablist" aria-label="Sections">{(["users", "chats", "files"] as const).map(item => <button key={item} role="tab" aria-selected={section === item} aria-pressed={section === item} onClick={() => setSection(item)}>{item === "users" ? "Users" : item === "chats" ? "All chats" : "All files"}</button>)}</div>
    <div className="search-input adm-search"><Icon name="search" size={16}/><input className="input" type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder={section === "users" ? "Search by name or email" : section === "chats" ? "Search chat titles" : "Search file names"} aria-label="Search"/></div>
    {section === "chats" ? <AllChats query={query}/> : section === "files" ? <AllFiles query={query}/> : <>
    {error ? <p className="notice" data-tone="error" role="alert">{error}</p> : null}
    {!rows && !error ? <LoadingState label="Loading users" rows={4}/> : null}
    {rows ? <>
      <p className="adm-count">{total} users</p>
      <div className="adm-list">{rows.map(user => <Link key={user.id} className="adm-user" to={`/settings/users/${user.id}`}>
        <span className="adm-avatar" aria-hidden="true" data-no-translate>{(user.name || user.email || "?").slice(0, 1).toUpperCase()}</span>
        <span className="adm-user-main"><b data-no-translate>{user.name || user.email}</b><small data-no-translate>{user.email}</small></span>
        <span className="adm-user-stats"><span><b>{user.chats}</b><small>Chats</small></span><span><b>{user.projects}</b><small>Projects</small></span><span><b>{user.jobs}</b><small>Renders</small></span><span><b>{user.files}</b><small>Files</small></span><span><b data-no-translate>{bytes(user.storage_bytes)}</b><small>Storage</small></span></span>
        <span className="adm-user-meta"><small>Last active</small><span>{when(user.last_active)}</span>{user.is_active ? null : <span className="adm-status" data-tone="bad"><i/>Inactive</span>}</span>
      </Link>)}</div>
      {!rows.length ? <p className="adm-empty">No user matches this search.</p> : null}
    </> : null}
    </>}
  </div>;
}

type Tab = "chats" | "projects" | "renders" | "files";

export function AdminUserDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = React.useState<Detail | null>(null);
  const [tab, setTab] = React.useState<Tab>("chats");
  const [error, setError] = React.useState("");
  const [open, setOpen] = React.useState<string | null>(null);
  React.useEffect(() => {
    setData(null); setOpen(null);
    adminManageRequest<Detail>(`/users/${id}`).then(setData).catch(e => setError(friendlyError(e, "load this user")));
  }, [id]);
  if (error) return <div className="page adm-page"><p className="notice" data-tone="error" role="alert">{error}</p><button className="btn btn-sm btn-secondary" onClick={() => navigate("/settings/users")}>Back to users</button></div>;
  if (!data) return <div className="page adm-page"><LoadingState label="Loading user" rows={4}/></div>;
  const counts: Record<Tab, number> = { chats: data.conversations.length, projects: data.projects.length, renders: data.jobs.length, files: data.files.length };
  const labels: Record<Tab, string> = { chats: "Chats", projects: "Projects", renders: "Renders", files: "Files" };
  return <div className="page adm-page">
    <header className="page-header"><div><h1 data-no-translate>{data.user.name || data.user.email}</h1><p data-no-translate>{data.user.email} · #{data.user.id}</p></div>
      <Link className="btn btn-sm btn-secondary" to="/settings/users"><Icon name="chevron" size={14}/>All users</Link></header>
    <div className="adm-summary">
      <div><small>Joined</small><b>{when(data.user.created_at)}</b></div>
      <div><small>Status</small><b>{data.user.is_active ? "Active" : "Inactive"}</b></div>
      <div><small>Storage</small><b data-no-translate>{bytes(data.storage_bytes)}</b></div>
    </div>
    <div className="segmented adm-tabs" role="tablist" aria-label="Sections">{(Object.keys(labels) as Tab[]).map(item => <button key={item} role="tab" aria-selected={tab === item} aria-pressed={tab === item} onClick={() => { setTab(item); setOpen(null); }}>{labels[item]} <span className="adm-badge">{counts[item]}</span></button>)}</div>

    {tab === "chats" ? <ChatTable showUser={false} rows={data.conversations.map(chat => ({ id: chat.id, title: chat.title, user: String(data.user.id), status: chat.status || "idle", updated_at: chat.updated_at, messages: chat.messages }))}/> : null}

    {tab === "projects" ? <div className="adm-rows">{data.projects.map(project => <div key={project.id} className="adm-item">
      <button className="adm-row" aria-expanded={open === project.id} onClick={() => setOpen(open === project.id ? null : project.id)}><span className="adm-row-main"><b dir="auto">{project.title}</b><small>{project.engine} · {when(project.updated_at)}</small></span><Status value={project.status}/><Icon name="chevron" size={14}/></button>
      {open === project.id ? <ProjectDetail id={project.id}/> : null}</div>)}</div> : null}

    {tab === "renders" ? <div className="adm-rows">{data.jobs.map(job => <div key={job.id} className="adm-item adm-job">
      <span className="adm-row-main"><b dir="auto">{job.title || job.id}</b><small>{when(job.created_at)}{job.stage ? ` · ${job.stage}` : ""}{job.message ? ` · ${job.message}` : ""}</small></span>
      <span className="adm-job-end"><Status value={job.status}/><span className="adm-pct" data-no-translate>{job.progress}%</span></span></div>)}</div> : null}

    {tab === "files" ? <div className="adm-files">{data.files.map(file => <div key={file.id} className="adm-file">
      <div className="adm-file-media">{file.kind === "image" ? <AuthenticatedMedia as="img" src={`${BASE}/files/${file.id}`} alt={file.name} loading="lazy"/>
        : file.kind === "video" ? <AuthenticatedMedia as="video" controls preload="metadata" src={`${BASE}/files/${file.id}`}/>
        : file.kind === "audio" ? <AuthenticatedMedia as="audio" controls preload="none" src={`${BASE}/files/${file.id}`}/> : <Icon name="library" size={22}/>}</div>
      <b className="wrap-safe" data-no-translate>{file.name}</b><small>{file.kind} · <span data-no-translate>{bytes(file.size)}</span> · {when(file.created_at)}</small></div>)}</div> : null}
    {counts[tab] === 0 ? <p className="adm-empty">Nothing here yet.</p> : null}
  </div>;
}

function ChatDetail({ id }: { id: string }) {
  const [data, setData] = React.useState<any>(null);
  const [error, setError] = React.useState("");
  React.useEffect(() => { adminManageRequest(`/conversations/${id}`).then(setData).catch(e => setError(friendlyError(e, "load this chat"))); }, [id]);
  if (error) return <p className="notice" data-tone="error">{error}</p>;
  if (!data) return <LoadingState label="Loading chat" rows={2}/>;
  return <div className="adm-detail">
    <p className="adm-meta">{data.messages.length} messages · {data.conversation.events} events · {data.projects.length} projects · {data.files.length} files</p>
    <ol className="adm-messages">{data.messages.map((message: any) => <li key={message.id} data-role={message.role}><small>{message.role} · {when(message.created_at)}{message.attachments?.length ? ` · ${message.attachments.length} attachments` : ""}</small><p dir="auto">{message.content}</p></li>)}</ol>
  </div>;
}

function ProjectDetail({ id }: { id: string }) {
  const [data, setData] = React.useState<any>(null);
  const [error, setError] = React.useState("");
  React.useEffect(() => { adminManageRequest(`/projects/${id}`).then(setData).catch(e => setError(friendlyError(e, "load this project"))); }, [id]);
  if (error) return <p className="notice" data-tone="error">{error}</p>;
  if (!data) return <LoadingState label="Loading project" rows={2}/>;
  const job = data.job;
  return <div className="adm-detail">
    <dl className="adm-facts">
      <div><dt>Engine</dt><dd data-no-translate>{data.project.engine}</dd></div>
      <div><dt>Status</dt><dd><Status value={data.project.status}/></dd></div>
      <div><dt>Version</dt><dd data-no-translate>{data.project.version}</dd></div>
      <div><dt>Created</dt><dd>{when(data.project.created_at)}</dd></div>
      {job ? <div><dt>Render</dt><dd><Status value={job.status}/> <span data-no-translate>{job.progress}%</span></dd></div> : null}
      {job ? <div><dt>Job storage</dt><dd data-no-translate>{bytes(job.storage_bytes)}</dd></div> : null}
      {data.design_choice ? <div><dt>Design look</dt><dd data-no-translate>{data.design_choice.name || data.design_choice.key}</dd></div> : null}
    </dl>
    {data.request ? <><h4>Request</h4><p className="adm-text" dir="auto">{data.request}</p></> : null}
    {job?.message ? <><h4>Render message</h4><p className="adm-text" dir="auto">{job.message}</p></> : null}
    {job?.creative_review ? <><h4>Review</h4><p className="adm-text" dir="auto">{job.creative_review}</p></> : null}
    {data.exports.length ? <><h4>Outputs</h4><div className="adm-exports">{data.exports.map((file: any) => /\.mp4$/i.test(file.name)
      ? <figure key={file.name}><AuthenticatedMedia as="video" controls preload="metadata" src={`${BASE}/projects/${id}/exports/${file.name}`}/><figcaption data-no-translate>{file.name} · {bytes(file.size)}</figcaption></figure>
      : <span key={file.name} data-no-translate>{file.name} · {bytes(file.size)}</span>)}</div></> : null}
    {job?.technical_qc && Object.keys(job.technical_qc).length ? <details className="adm-more"><summary>Technical checks</summary><pre dir="ltr" data-no-translate>{JSON.stringify(job.technical_qc, null, 1)}</pre></details> : null}
    <details className="adm-more"><summary>Activity ({data.events.length})</summary><ol className="adm-events">{data.events.map((event: any) => <li key={event.seq}><span data-no-translate>{event.type}</span><small>{when(event.at)}</small>{event.message ? <p dir="auto">{event.message}</p> : null}</li>)}</ol></details>
  </div>;
}
