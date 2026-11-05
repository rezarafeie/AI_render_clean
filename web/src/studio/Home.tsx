import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { api, HomeStatus, HomeSuggestion, StudioHome } from "../api";
import { Icon, IconName } from "../components/Icon";
import { ConfirmDelete, DeleteTarget } from "../components/ConfirmDelete";
import { ScrollRow } from "../components/ScrollRow";
import { AuthenticatedMedia } from "../AuthenticatedMedia";
import { displayTitle, relativeTime } from "../format";
import { parseTime } from "./model";

/** The chrome of the app is English; only a person's own titles are in their language, so a row never mixes two scripts in its labels. */
const KIND_LABEL: Record<string, string> = { motion: "Motion graphic", motion_graphic: "Motion graphic", talking: "Talking reel", localize: "Dub & subtitles", chat: "Chat" };
const STATUS_LABEL: Record<HomeStatus, string> = { running: "Working", needs_input: "Needs you", failed: "Failed", ready: "", draft: "" };

const KIND_ICON: Record<string, IconName> = { motion: "motion", talking: "video", localize: "captions", chat: "thinking" };

/** The word and tone of a piece of work's state, so an unfinished or failed edit is never mistaken for a finished one. */
let remembered: HomeSuggestion[] | null = null;       // the model's last suggestions: shown at once on the next visit

export function statusTone(status: HomeStatus): "working" | "warning" | "error" | "success" | "idle" {
  return status === "running" ? "working" : status === "needs_input" ? "warning" : status === "failed" ? "error" : status === "ready" ? "success" : "idle";
}

function ChipsSkeleton() {
  return <div className="home-skeleton home-skeleton-chips" role="status" aria-label="Loading"><span className="skeleton"/><span className="skeleton"/><span className="skeleton"/></div>;
}

function RowsSkeleton() {
  return <div className="home-skeleton home-skeleton-rows" role="status" aria-label="Loading">
    {[0, 1, 2].map(i => <div key={i} className="home-skeleton-row"><span className="skeleton"/><span className="home-skeleton-lines"><span className="skeleton"/><span className="skeleton"/></span></div>)}
  </div>;
}

/**
 * The start page under the composer: up to three suggestions made from the person's own edits (and InstaGPT chats) and the latest three edits each
 * with its real state (InstaGPT has its own button in the header). Everything arrives in one request and shows a skeleton until it does.
 */
export function StudioHomePage({ composer, authenticated, onPrompt }: { composer: React.ReactNode; authenticated: boolean; onPrompt: (prompt: string) => void }) {
  const navigate = useNavigate();
  const [home, setHome] = React.useState<StudioHome | null>(null);
  const [better, setBetter] = React.useState<HomeSuggestion[] | null>(remembered);
  const [failed, setFailed] = React.useState(false);
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    if (!authenticated) { remembered = null; setBetter(null); return; }
    const controller = new AbortController();
    setFailed(false);
    api.studioHome(controller.signal).then(value => {
      if (controller.signal.aborted) return;
      setHome(value);
      if (value.suggestions_ready === false) {         // the page is already shown with the plain suggestions; the model's replace them when they arrive
        api.studioHomeSuggestions(controller.signal).then(better => { if (!controller.signal.aborted && better.suggestions?.length) { remembered = better.suggestions; setBetter(better.suggestions); } }).catch(() => undefined);
      }
    }).catch(() => { if (!controller.signal.aborted) setFailed(true); });
    const tick = window.setInterval(() => setNow(Date.now()), 30000);
    return () => { controller.abort(); window.clearInterval(tick); };
  }, [authenticated]);
  const [deleting, setDeleting] = React.useState<DeleteTarget | null>(null);
  const loading = authenticated && !home && !failed;
  const running = home?.recent.some(item => item.status === "running");
  // While something is being made, its card should not go stale: ask again every ten seconds.
  React.useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => void api.studioHome().then(setHome).catch(() => undefined), 10000);
    return () => window.clearInterval(timer);
  }, [running]);

  return <div className="studio-home">
    <div className="home-inner">
      <h1>What would you like to create?</h1>
      {composer}
      {authenticated ? <>
        <section className="home-suggest" aria-label="Suggestions">
          {loading ? <ChipsSkeleton/> : <ScrollRow>
            {(better || home?.suggestions || []).slice(0, 3).map(item => <button key={`${item.kind}-${item.label}`} className="chip home-chip"
              onClick={() => item.kind === "open" ? navigate(`/studio/${item.conversation_id}`) : onPrompt(item.prompt)}>
              <span dir="auto">{item.label}</span></button>)}
          </ScrollRow>}
        </section>
        <section className="home-recent" aria-label="Recent edits">
          <div className="home-recent-head"><h2>Recent edits</h2><NavLink to="/projects">All</NavLink></div>
          {loading ? <RowsSkeleton/> : failed ? <p className="home-note">Recent edits could not be loaded.</p> : home?.recent.length ? <ul>
            {home.recent.slice(0, 3).map(item => <li key={item.id}><NavLink to={`/studio/${item.id}`} title={item.title}>
              <span className="home-thumb" aria-hidden="true">{item.thumb ? <AuthenticatedMedia as="img" src={api.motionMediaUrl(item.thumb.split("/")[3], "thumb")} alt="" loading="lazy" draggable={false}/> : <Icon name={KIND_ICON[item.kind] || "thinking"} size={18}/>}</span>
              <span className="home-recent-copy"><span className="home-title" dir="auto">{displayTitle(item.title, 60) || "New edit"}</span>
                <span className="home-meta"><span>{KIND_LABEL[item.kind] || "Chat"}</span><span>{relativeTime(parseTime(item.updated_at), now)}</span></span></span>
              {STATUS_LABEL[item.status] ? <span className="home-status" data-tone={statusTone(item.status)}><i aria-hidden="true"/>{STATUS_LABEL[item.status]}</span> : null}
            </NavLink>
              <button type="button" className="icon-btn trash-btn home-recent-del" aria-label={`Delete chat: ${displayTitle(item.title, 40) || "New edit"}`} data-tip="Delete" onClick={() => setDeleting({
                title: "Delete this chat?", what: displayTitle(item.title, 80) || "New edit",
                detail: "Its messages, uploads and projects are removed with it, and so are the videos made in it. This cannot be undone.",
                run: async () => { await api.deleteStudioConversation(item.id); setHome(value => value ? { ...value, recent: value.recent.filter(row => row.id !== item.id) } : value); window.dispatchEvent(new Event("editorgpt:conversations-updated")); } })}><Icon name="trash" size={16}/></button></li>)}
          </ul> : <p className="home-note">No edits yet. Describe your first video above.</p>}
        </section>
      </> : <p className="home-note">Log in to save projects and start creating.</p>}
      <ConfirmDelete target={deleting} onClose={() => setDeleting(null)}/>
    </div>
  </div>;
}
