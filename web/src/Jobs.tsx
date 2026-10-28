import React from "react";
import { NavLink } from "react-router-dom";
import { api, LocalizeSummary, StudioConversation, TalkingReelSummary } from "./api";
import { useJobCache } from "./JobCache";
import { AuthenticatedMedia } from "./AuthenticatedMedia";
import { Icon } from "./EditorShell";
import { friendlyError } from "./ui";
import { displayTitle, relativeTime } from "./format";

type ProjectView = {
  key: string; title: string; type: string; status: string; statusLabel: string; kind: "studio" | "legacy";
  progress?: number; updated: number; to: string; thumbnail?: string;
};

function humanStatus(status: string) {
  const value = status.toLowerCase();
  if (["done", "ready", "completed"].includes(value)) return ["Ready", "ready"] as const;
  if (["error", "failed"].includes(value)) return ["Failed", "failed"] as const;
  if (["paused", "awaiting_confirmation", "awaiting_input", "needs_review"].includes(value)) return ["Needs attention", "attention"] as const;
  if (value === "rendering") return ["Rendering", "working"] as const;
  if (["running", "processing", "generating", "analyzing", "queued", "transcribing"].includes(value)) return ["Editing", "working"] as const;
  return ["Draft", "draft"] as const;
}

export default function Projects() {
  const { jobs, loading, error, refetch } = useJobCache();
  const [conversations, setConversations] = React.useState<StudioConversation[]>([]);
  const [localize, setLocalize] = React.useState<LocalizeSummary[]>([]);
  const [talking, setTalking] = React.useState<TalkingReelSummary[]>([]);
  const [secondaryError, setSecondaryError] = React.useState<unknown>(null);
  const [query, setQuery] = React.useState("");
  const [filter, setFilter] = React.useState("all");
  const [sort, setSort] = React.useState("recent");

  const loadSources = React.useCallback(async () => {
    const results = await Promise.allSettled([api.listStudioConversations(), api.listLocalize(), api.listTalkingReels()]);
    if (results[0].status === "fulfilled") setConversations(results[0].value);
    if (results[1].status === "fulfilled") setLocalize(results[1].value);
    if (results[2].status === "fulfilled") setTalking(results[2].value);
    const rejected = results.find(item => item.status === "rejected");
    setSecondaryError(rejected?.status === "rejected" ? rejected.reason : null);
  }, []);

  React.useEffect(() => { void refetch(); void loadSources(); }, [refetch, loadSources]);

  const allItems = React.useMemo(() => {
    const items: ProjectView[] = [];
    const linkedRefs = new Set<string>();
    for (const conversation of conversations) {
      const project = conversation.projects?.find(item => item.id === conversation.state?.current_project_id) || conversation.projects?.[conversation.projects.length - 1];
      if (project?.external_ref) linkedRefs.add(project.external_ref);
      const [statusLabel, status] = humanStatus(project?.status || "draft");
      items.push({ key: `studio-${conversation.id}`, kind: "studio", title: conversation.title || "Untitled edit", type: project?.engine === "localize" ? "Localization" : project?.engine === "talking" ? "Talking Head" : project?.engine === "motion" ? "Motion video" : "AI edit", status, statusLabel, progress: project?.state?.last_observed?.progress, updated: Date.parse(conversation.updated_at), to: `/studio/${conversation.id}` });
    }
    const talkingIds = new Set(talking.map(item => item.job_id));
    for (const item of talking) if (!linkedRefs.has(item.job_id)) {
      const [statusLabel, status] = humanStatus(item.status);
      const title = item.name || item.hook || "Talking-head video";
      items.push({ key: `talking-${item.job_id}`, kind: "legacy", title, type: "Talking Head", status, statusLabel, updated: item.updated_at * 1000, to: `/studio?legacy=talking:${item.job_id}&title=${encodeURIComponent(title)}` });
    }
    for (const item of localize) if (!linkedRefs.has(item.id)) {
      const [statusLabel, status] = humanStatus(item.status);
      const title = item.title || item.name || "Localized video";
      items.push({ key: `localize-${item.id}`, kind: "legacy", title, type: "Localization", status, statusLabel, progress: item.progress, updated: (item.updated_at || item.created_at || 0) * 1000, to: `/studio?legacy=localize:${item.id}&title=${encodeURIComponent(title)}` });
    }
    for (const job of jobs) if (!linkedRefs.has(job.id) && !talkingIds.has(job.id)) {
      const active = job.render.status !== "idle" ? job.render.status : job.generate.status;
      const [statusLabel, status] = humanStatus(active);
      const title = job.raw_name || job.plan?.title || "Video edit";
      items.push({ key: `job-${job.id}`, kind: "legacy", title, type: job.plan?.content_type === "reel" ? "Social video" : "Video edit", status, statusLabel, progress: job.render.status === "running" ? job.render.progress : undefined, updated: 0, to: `/studio?legacy=motion:${job.id}&title=${encodeURIComponent(title)}`, thumbnail: job.render.status === "done" && job.render.output ? api.exportUrl(job.id, job.render.output.replace(/\.mp4$/, "_poster.jpg")) : undefined });
    }
    return items;
  }, [conversations, localize, talking, jobs]);
  const projects = React.useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return allItems.filter(item => (!normalized || `${item.title} ${item.type}`.toLocaleLowerCase().includes(normalized)) && (filter === "all" || item.status === filter)).sort((a, b) => sort === "oldest" ? a.updated - b.updated : b.updated - a.updated);
  }, [allItems, query, filter, sort]);

  const hasAnything = conversations.length + localize.length + talking.length + jobs.length > 0;
  const counts = React.useMemo(() => {
    const total: Record<string, number> = {};
    // Counts reflect the search, not the status filter.
    const normalized = query.trim().toLocaleLowerCase();
    for (const item of allItems) if (!normalized || `${item.title} ${item.type}`.toLocaleLowerCase().includes(normalized)) { total[item.status] = (total[item.status] || 0) + 1; total.all = (total.all || 0) + 1; }
    return total;
  }, [allItems, query]);
  const filters: [string, string][] = [["all", "All"], ["working", "In progress"], ["ready", "Ready"], ["attention", "Needs attention"], ["failed", "Failed"], ["draft", "Draft"]];
  const icons: Record<string, "film" | "globe" | "mic2" | "video"> = { Localization: "globe", "Talking Head": "mic2", "Motion video": "film" };
  return <div className="page">
    <header className="page-header">
      <div><h1>Projects</h1><p>Continue an edit, review progress or download a finished video.</p></div>
      <NavLink className="btn" to="/studio"><Icon name="edit" size={16}/>New edit</NavLink>
    </header>
    <div className="proj-toolbar">
      <label className="search-input"><span className="sr-only">Search projects</span><Icon name="search" size={16}/><input className="input" type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search projects"/></label>
      <select className="input proj-sort" value={sort} onChange={event => setSort(event.target.value)} aria-label="Sort projects"><option value="recent">Recently updated</option><option value="oldest">Oldest first</option></select>
    </div>
    <div className="chip-row" role="group" aria-label="Filter by status">
      {filters.map(([id, label]) => (id === "all" || counts[id]) ? <button key={id} className="chip" aria-pressed={filter === id} onClick={() => setFilter(id)}>{label}<span className="chip-count">{counts[id] || 0}</span></button> : null)}
    </div>
    {(loading && !hasAnything) ? <ul className="proj-grid" aria-busy="true" aria-label="Loading projects">{Array.from({ length: 6 }, (_, i) => <li key={i} className="proj-card"><span className="proj-thumb skeleton"/><span className="skeleton" style={{ height: 16, width: "70%" }}/><span className="skeleton" style={{ height: 12, width: "40%" }}/></li>)}</ul>
      : (error && !hasAnything) ? <div className="notice" data-tone="error" role="alert">{friendlyError(error, "load projects")}</div>
      : !hasAnything ? <div className="empty"><span className="empty-icon"><Icon name="projects" size={24}/></span><strong>No projects yet</strong><p>Start with a prompt, then add a video, image, audio file or product link.</p><NavLink className="btn" to="/studio">Start your first edit</NavLink></div>
      : projects.length === 0 ? <div className="empty"><span className="empty-icon"><Icon name="search" size={24}/></span><strong>No matching projects</strong><p>Try a different search or status.</p><button className="btn btn-secondary" onClick={() => { setQuery(""); setFilter("all"); }}>Clear filters</button></div>
      : <ul className="proj-grid">{projects.map(project => <li key={project.key}><NavLink to={project.to} className="proj-card" title={project.title}>
          <span className="proj-thumb">{project.thumbnail ? <AuthenticatedMedia as="img" src={project.thumbnail} alt="" loading="lazy"/> : <Icon name={icons[project.type] || "video"} size={28}/>}
            <span className="badge proj-status" data-tone={project.status === "ready" ? "success" : project.status === "failed" ? "error" : project.status === "attention" ? "warning" : project.status === "working" ? "working" : undefined}><i/>{project.statusLabel}</span>
          </span>
          <b className="proj-title bidi" dir="auto">{displayTitle(project.title, 70)}</b>
          {typeof project.progress === "number" && project.status === "working" ? <span className="meter" style={{ ["--value" as string]: `${project.progress}%` }} role="progressbar" aria-label="Progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={project.progress}><span/></span> : null}
          <span className="proj-meta"><span>{project.type}</span>{project.updated ? <span>{relativeTime(project.updated)}</span> : null}</span>
        </NavLink></li>)}</ul>}
    {(error || secondaryError) && hasAnything ? <p className="notice" data-tone="warning" style={{ marginTop: 16 }}>Some project sources could not refresh. <button className="link-btn" onClick={() => { void refetch(); void loadSources(); }}>Try again</button></p> : null}
  </div>;
}
