import React from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api, StudioConversation } from "./api";
import hermesApi from "./services/hermesApi";
import { peekCache, writeCache } from "./pages/hermes/hermesCache";
import { Icon } from "./components/Icon";
import { ProjectStatusDot } from "./components/ProjectStatusDot";
import { Resizer, usePanelWidth } from "./components/Resizer";
import { ShellContext, TopbarAction } from "./components/ShellContext";
import { useFocusTrap, useMediaQuery, useVisualViewportHeight } from "./components/hooks";
import { useAuth } from "./auth/AuthContext";
import { isLocalDevelopment } from "./auth";
import { displayTitle, parseTime } from "./format";
import PaneSkeleton from "./components/PaneSkeleton";
import { preloadEditor, preloadHermes } from "./routeLoaders";

const SIDEBAR_BOUNDS = { min: 200, max: 420 };

// Kept so older screens that import { Icon } from "./EditorShell" keep working.
export { Icon } from "./components/Icon";
export type { IconName } from "./components/Icon";

type RouteKind = "studio" | "page" | "legacy" | "workspace";
function routeKind(pathname: string): RouteKind {
  if (pathname === "/" || pathname.startsWith("/studio")) return "studio";
  if (pathname === "/hermes" || pathname.startsWith("/hermes/")) return "workspace";   // laid out like the Studio chat: a page column and a side panel
  if (/^\/(projects|templates|settings)(\/|$)/.test(pathname) && !pathname.startsWith("/settings/ai")) return "page";
  return "legacy";
}
const ROUTE_TITLES: Record<string, string> = { "/projects": "Projects", "/templates": "Templates", "/settings": "Settings" };

export default function EditorShell() {
  const { authenticated, user, openAuth, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const isMobile = useMediaQuery("(max-width: 820px)");
  const [collapsed, setCollapsed] = React.useState(() => { try { return localStorage.getItem("editorgpt.sidebar") === "collapsed"; } catch { return false; } });
  const [drawer, setDrawer] = React.useState(false);
  const [searching, setSearching] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [conversations, setConversations] = React.useState<StudioConversation[]>([]);
  const [hermesChats, setHermesChats] = React.useState<{ id: string; title: string; updated_at: string }[]>(() => (peekCache("chats") as any) || []);
  const [pageTitle, setPageTitle] = React.useState("");
  const [topbarAction, setTopbarAction] = React.useState<TopbarAction | null>(null);
  const sidebarRef = React.useRef<HTMLElement>(null);
  const [sidebarWidth, setSidebarWidth] = usePanelWidth("editorgpt.sidebar.width", SIDEBAR_BOUNDS);
  const [liveWidth, setLiveWidth] = React.useState<number | null>(null);
  const [resizing, setResizing] = React.useState(false);
  const searchRef = React.useRef<HTMLInputElement>(null);
  const kind = routeKind(location.pathname);

  useVisualViewportHeight();
  useFocusTrap(drawer && isMobile, sidebarRef);

  React.useEffect(() => { try { localStorage.setItem("editorgpt.sidebar", collapsed ? "collapsed" : "open"); } catch { /* storage unavailable */ } }, [collapsed]);

  const refreshChats = React.useCallback(() => {
    if (authenticated) void api.listStudioConversations().then(setConversations).catch(() => undefined);
    else setConversations([]);
  }, [authenticated]);
  const hermesMode = routeKind(location.pathname) === "workspace";
  const refreshHermes = React.useCallback(() => {
    if (!authenticated || !hermesMode) return;
    void hermesApi.listChats().then((out: any) => { const list = out?.chats || []; writeCache("chats", list); setHermesChats(list); }).catch(() => undefined);
  }, [authenticated, hermesMode]);
  React.useEffect(() => { refreshHermes(); }, [refreshHermes, location.pathname]);
  React.useEffect(() => { window.addEventListener("hermes:chats-updated", refreshHermes); return () => window.removeEventListener("hermes:chats-updated", refreshHermes); }, [refreshHermes]);
  React.useEffect(() => {   // both apps are fetched in the background, so the switch between them is instant
    if (!authenticated) return;
    const run = () => { void preloadHermes(); void preloadEditor(); };
    const idle = (window as any).requestIdleCallback as undefined | ((cb: () => void, opts?: object) => number);
    const id = idle ? idle(run, { timeout: 3000 }) : window.setTimeout(run, 1200);
    return () => { if (idle) (window as any).cancelIdleCallback?.(id); else window.clearTimeout(id); };
  }, [authenticated]);
  React.useEffect(() => { setDrawer(false); }, [location.pathname]);
  React.useEffect(() => { refreshChats(); }, [refreshChats, location.pathname]);
  React.useEffect(() => {
    const open = () => setDrawer(true);
    window.addEventListener("editorgpt:open-nav", open);
    window.addEventListener("editorgpt:conversations-updated", refreshChats);
    return () => { window.removeEventListener("editorgpt:open-nav", open); window.removeEventListener("editorgpt:conversations-updated", refreshChats); };
  }, [refreshChats]);
  React.useEffect(() => {
    if (!drawer) return;
    const key = (event: KeyboardEvent) => { if (event.key === "Escape") setDrawer(false); };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [drawer]);
  React.useEffect(() => { if (!isMobile) setDrawer(false); }, [isMobile]);
  React.useEffect(() => { if (searching) searchRef.current?.focus(); }, [searching]);

  const shellValue = React.useMemo(() => ({ openNav: () => setDrawer(true), setTitle: setPageTitle, setAction: setTopbarAction }), []);
  const visible = React.useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return [...conversations].sort((a, b) => parseTime(b.updated_at) - parseTime(a.updated_at)).filter(item => !needle || (item.title || "").toLocaleLowerCase().includes(needle));
  }, [conversations, query]);

  const visibleHermes = React.useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return [...hermesChats].sort((a, b) => parseTime(b.updated_at) - parseTime(a.updated_at)).filter(item => !needle || (item.title || "").toLocaleLowerCase().includes(needle));
  }, [hermesChats, query]);

  const startSearch = () => { if (collapsed && !isMobile) setCollapsed(false); setSearching(true); };
  const rail = collapsed && !isMobile;
  const tip = (label: string) => rail ? { "data-tip": label, className: "nav-item rail-tip" } : { className: "nav-item" };
  const topTitle = ROUTE_TITLES[location.pathname] || pageTitle || (routeKind(location.pathname) === "workspace" ? "InstaGPT" : "EditorGPT");
  const initial = user?.name?.trim()?.[0]?.toUpperCase();
  const settingsActive = /^\/(settings|new|my-effects|library|style-library|style-learner|fonts|hermes|content|localize|talking)/.test(location.pathname);

  return <ShellContext.Provider value={shellValue}>
    <div className="app" data-collapsed={collapsed || undefined} data-resizing={resizing || undefined}
      style={!collapsed && !isMobile && (liveWidth ?? sidebarWidth) ? { ["--sb" as string]: `${liveWidth ?? sidebarWidth}px` } : undefined} data-bare={kind === "studio" || undefined} data-hide-bottom-nav={/^\/studio\/[^/]+/.test(location.pathname) || undefined}>
      <a className="skip-link" href="#main-content">Skip to content</a>

      <aside ref={sidebarRef} className="sidebar" data-open={drawer || undefined} aria-label="Main navigation" tabIndex={-1}>
        <div className="sb-head">
          <NavLink to={hermesMode ? "/hermes" : "/studio"} className="brand" aria-label={hermesMode ? "InstaGPT home" : "EditorGPT home"}><span className="brand-mark"><Icon name="spark" size={18}/></span><span className="brand-name">{hermesMode ? "InstaGPT" : "EditorGPT"}</span></NavLink>
          <button className="icon-btn sb-collapse rail-tip" data-tip={collapsed ? "Open sidebar" : "Close sidebar"} onClick={() => setCollapsed(value => !value)} aria-label={collapsed ? "Open sidebar" : "Close sidebar"} aria-expanded={!collapsed}><Icon name="panel" size={19}/></button>
          {isMobile ? <button className="icon-btn" onClick={() => setDrawer(false)} aria-label="Close navigation"><Icon name="close" size={19}/></button> : null}
        </div>

        <nav className="sb-nav" aria-label="Primary">
          {hermesMode ? <>
            <NavLink to="/studio" {...tip("Switch to EditorGPT")} aria-label="Switch to EditorGPT" onPointerEnter={() => void preloadEditor()}><Icon name="video"/><span>EditorGPT</span></NavLink>
            <NavLink to="/hermes" end {...tip("New chat")} aria-label="New chat"><Icon name="edit"/><span>New chat</span></NavLink>
            <button type="button" {...tip("Search chats")} aria-label="Search chats" onClick={startSearch}><Icon name="search"/><span>Search chats</span></button>
            <NavLink to="/hermes/content" {...tip("Content")}><Icon name="film"/><span>Content</span></NavLink>
            <NavLink to="/hermes/analytics" {...tip("Analytics")}><Icon name="list"/><span>Analytics</span></NavLink>
          </> : <>
          <NavLink to="/hermes" {...tip("Switch to InstaGPT")} aria-label="Switch to InstaGPT" onPointerEnter={() => void preloadHermes()}><Icon name="instagram"/><span>InstaGPT</span></NavLink>
          <NavLink to="/studio" end {...tip("New edit")} aria-label="New edit"><Icon name="edit"/><span>New edit</span></NavLink>
          <button type="button" {...tip("Search chats")} aria-label="Search chats" onClick={startSearch}><Icon name="search"/><span>Search chats</span></button>
          <NavLink to="/projects" {...tip("Projects")}><Icon name="projects"/><span>Projects</span></NavLink>
          <NavLink to="/templates" {...tip("Templates")}><Icon name="templates"/><span>Templates</span></NavLink>
          </>}
        </nav>

        <section className="sb-history" aria-label="Chat history">
          {authenticated ? <>
            <div className="sb-section-title">Recent</div>
            {searching ? <div className="sb-search"><input ref={searchRef} className="input" type="search" value={query} onChange={event => setQuery(event.target.value)} onKeyDown={event => { if (event.key === "Escape") { setSearching(false); setQuery(""); } }} placeholder="Search chats" aria-label="Search chats"/></div> : null}
            <div className="sb-list">
              {(hermesMode ? visibleHermes : visible).map(chat => <NavLink key={chat.id} to={hermesMode ? `/hermes/chat/${chat.id}` : `/studio/${chat.id}`} className="sb-chat" title={chat.title}>{displayTitle(chat.title, 48)}</NavLink>)}
              {!(hermesMode ? visibleHermes : visible).length ? <p className="sb-empty">{query ? "No chats match your search." : "Your chats will appear here."}</p> : null}
            </div>
          </> : <div className="sb-guest">
            <p>Log in to save your chats and keep projects in sync.</p>
            <button className="btn btn-sm" onClick={() => { setDrawer(false); openAuth("login"); }}>Log in</button>
            <button className="btn btn-sm btn-secondary" onClick={() => { setDrawer(false); openAuth("signup"); }}>Sign up</button>
          </div>}
        </section>
        <div className="sb-spacer"/>

        <div className="sb-foot">
          {hermesMode ? <NavLink to="/hermes/settings" {...tip("Settings")}><Icon name="settings"/><span>Settings</span></NavLink> : <NavLink to="/settings" {...tip("Settings")} aria-current={settingsActive ? "page" : undefined}><Icon name="settings"/><span>Settings</span></NavLink>}
          {authenticated ? <div className="account">
            <span className="avatar" aria-hidden="true">{initial || <Icon name="user" size={16}/>}</span>
            <span className="account-copy"><b>{user?.name || "Editor"}</b><small>{isLocalDevelopment ? "Local workspace" : user?.email}</small></span>
            {!isLocalDevelopment ? <button className="icon-btn account-out" onClick={() => void logout()} aria-label="Log out" data-tip="Log out" data-tip-pos="top"><Icon name="logout" size={18}/></button> : null}
          </div> : null}
        </div>
        {!rail && !isMobile ? <Resizer panel={sidebarRef} edge="end" bounds={() => SIDEBAR_BOUNDS} width={liveWidth ?? sidebarWidth} label="عرض نوار کناری"
          onResize={setLiveWidth} onDragState={setResizing} onCommit={value => { setSidebarWidth(value); setLiveWidth(null); }}/> : null}
      </aside>

      {drawer && isMobile ? <button className="drawer-backdrop" onClick={() => setDrawer(false)} aria-label="Close navigation" tabIndex={-1}/> : null}

      <div className="content-col" {...(drawer && isMobile ? { inert: "" as unknown as boolean } : {})}>
        <header className="topbar">
          <button className="icon-btn icon-btn-lg" onClick={() => setDrawer(true)} aria-label="Open navigation" aria-expanded={drawer}><Icon name="menu"/></button>
          <div className="topbar-title">{topTitle}</div>
          {topbarAction?.status ? <ProjectStatusDot status={topbarAction.status}/> : null}
          {topbarAction ? <button className="icon-btn icon-btn-lg" onClick={topbarAction.onClick} aria-pressed={topbarAction.active} aria-label={topbarAction.active ? "Exit full screen" : "Full screen"}><Icon name={topbarAction.active ? "fullscreenExit" : "fullscreen"}/></button> : null}
          <NavLink to={hermesMode ? "/studio" : "/hermes"} className="switch-btn" aria-label={hermesMode ? "Switch to EditorGPT" : "Switch to InstaGPT"} onPointerEnter={() => void (hermesMode ? preloadEditor() : preloadHermes())} onTouchStart={() => void (hermesMode ? preloadEditor() : preloadHermes())}>
            <Icon name={hermesMode ? "video" : "instagram"} size={17}/><span>{hermesMode ? "EditorGPT" : "InstaGPT"}</span></NavLink>
        </header>
        <main id="main-content" className={`main${kind === "legacy" ? " eg-legacy" : ""}`} data-route={kind} tabIndex={-1}>
          <React.Suspense fallback={<PaneSkeleton/>}>{kind === "legacy" ? <div className="legacy-frame"><Outlet/></div> : <Outlet/>}</React.Suspense>
        </main>
        <nav className="bottom-nav" aria-label="Mobile navigation" style={{ ["--tabs" as string]: 3 }}>
          {hermesMode ? <>
            <NavLink to="/hermes" end><Icon name="edit"/><span>New chat</span></NavLink>
            <NavLink to="/hermes/content"><Icon name="film"/><span>Content</span></NavLink>
            <NavLink to="/hermes/analytics"><Icon name="list"/><span>Analytics</span></NavLink>
          </> : <>
            <NavLink to="/studio" end><Icon name="edit"/><span>New edit</span></NavLink>
            <NavLink to="/projects"><Icon name="projects"/><span>Projects</span></NavLink>
            <NavLink to="/templates"><Icon name="templates"/><span>Templates</span></NavLink>
          </>}
        </nav>
      </div>
    </div>
  </ShellContext.Provider>;
}
