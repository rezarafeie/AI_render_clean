import React from "react";
import { useTheme, setTheme } from "./theme";
import { DeviceSettings, InstallationSettings } from "./local/AppFeatures";
import { NavLink, useLocation } from "react-router-dom";
import { Icon, IconName } from "./components/Icon";
import { aiAdminRequest } from "./api";
import { useAuth } from "./auth/AuthContext";
import { isLocalDevelopment } from "./auth";
import { AgentSettings } from "./studio/AgentMode";
import { IntegrationsSettings } from "./settings/Integrations";

type Tool = { label: string; description: string; to: string; icon: IconName };
const groups: { title: string; hint: string; tools: Tool[] }[] = [
  { title: "Editing tools", hint: "Specialist editors. Your projects and data are unchanged.", tools: [
    { label: "Advanced reel editor", description: "Manual reel editing with plan review and timeline.", to: "/new", icon: "film" },
    { label: "Content creator", description: "Storyboards from a prompt, images or a product link.", to: "/content", icon: "wand" },
    { label: "Talking reels", description: "Talking-head analysis, captions and render settings.", to: "/talking", icon: "mic2" },
    { label: "Localization", description: "Persian dubbing, subtitles and voice for existing video.", to: "/localize", icon: "globe" },
    { label: "Effects", description: "Review and tune the effects the editor prefers.", to: "/my-effects", icon: "spark" },
    { label: "Motion library", description: "Preview every motion component, effect and shot recipe the editor can use.", to: "/motion-library", icon: "motion" },
  ] },
  { title: "Libraries", hint: "Reusable assets and learned looks.", tools: [
    { label: "Styles & fonts", description: "Approved visual styles and the font library.", to: "/style-library", icon: "captions" },
    { label: "Style learning", description: "Learn a style from reference videos.", to: "/style-learner", icon: "eye" },
    { label: "Media library", description: "Music, B-roll, sound effects and brand assets.", to: "/library", icon: "library" },
  ] },
  { title: "Workspaces", hint: "Agents that use your connected services.", tools: [
    { label: "Hermes", description: "Plan, schedule and analyse social publishing.", to: "/hermes", icon: "link" },
  ] },
];

type TabId = "general" | "editing" | "connections" | "tools";
const TABS: { id: TabId; label: string; hint: string; icon: IconName }[] = [
  { id: "general", label: "General", hint: "Appearance, account and the app on this device.", icon: "user" },
  { id: "editing", label: "Editing & processing", hint: "How the assistant works, where media is processed, storage and notifications.", icon: "wand" },
  { id: "connections", label: "Connections", hint: "Instagram, Google Drive and other connected services.", icon: "link" },
  { id: "tools", label: "Tools & libraries", hint: "Specialist editors, reusable assets and administration.", icon: "library" },
];
const isTab = (value: string): value is TabId => TABS.some(tab => tab.id === value);

export default function Settings() {
  const { user, authenticated, logout } = useAuth();
  const [admin, setAdmin] = React.useState(false);
  const theme = useTheme();
  const location = useLocation();
  React.useEffect(() => { aiAdminRequest<{ allowed: boolean }>("/access").then(r => setAdmin(r.allowed)).catch(() => setAdmin(false)); }, []);
  // The tab lives in the URL hash (#editing, #connections …) so a link such as /settings#integrations opens the right place and Back works.
  const wanted = location.hash.replace(/^#/, "");
  const tab: TabId = wanted === "integrations" ? "connections" : isTab(wanted) ? wanted : "general";
  const visible = TABS.filter(item => authenticated || item.id === "general" || item.id === "editing" || item.id === "tools");
  const current = TABS.find(item => item.id === tab) || TABS[0];
  const paneRef = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => { paneRef.current?.scrollIntoView({ block: "start", behavior: "auto" }); if (wanted === "integrations") document.getElementById("integrations")?.scrollIntoView({ block: "start" }); }, [tab, wanted]);

  return <div className="page set-page">
    <header className="page-header"><div><h1>Settings</h1><p>Everything in one place, grouped by what you are trying to do.</p></div></header>
    <div className="set-layout">
      <nav className="set-nav" aria-label="Settings sections">
        {visible.map(item => <NavLink key={item.id} to={{ pathname: "/settings", hash: `#${item.id}` }} replace className="set-nav-item" aria-current={tab === item.id ? "page" : undefined}>
          <Icon name={item.icon} size={17}/><span>{item.label}</span></NavLink>)}
      </nav>
      <div className="set-pane" ref={paneRef}>
        <div className="set-pane-head"><h2>{current.label}</h2><p>{current.hint}</p></div>

        {tab === "general" ? <>
          <section className="set-section" aria-labelledby="set-appearance">
            <h2 id="set-appearance">Appearance</h2>
            <div className="set-row"><span><b>Theme</b><small>System follows your device automatically.</small></span>
              <div className="segmented" role="group" aria-label="Theme">
                <button aria-pressed={theme === "system"} onClick={() => setTheme("system")}>System</button>
                <button aria-pressed={theme === "dark"} onClick={() => setTheme("dark")}><Icon name="moon" size={14}/> Dark</button>
                <button aria-pressed={theme === "light"} onClick={() => setTheme("light")}><Icon name="sun" size={14}/> Light</button>
              </div></div>
          </section>
          {authenticated ? <section className="set-section" aria-labelledby="set-account">
            <h2 id="set-account">Account</h2>
            <div className="set-row"><span><b>{user?.name || "Editor"}</b><small>{isLocalDevelopment ? "Local workspace" : user?.email}</small></span>
              {!isLocalDevelopment ? <button className="btn btn-sm btn-secondary" onClick={() => void logout()}><Icon name="logout" size={15}/>Log out</button> : null}</div>
          </section> : null}
          <InstallationSettings/>
        </> : null}

        {tab === "editing" ? <>
          {authenticated ? <AgentSettings/> : null}
          <DeviceSettings/>
        </> : null}

        {tab === "connections" && authenticated ? <IntegrationsSettings/> : null}

        {tab === "tools" ? <>
          {admin ? <section className="set-section" aria-labelledby="set-admin"><h2 id="set-admin">Administration</h2>
            <NavLink className="set-link" to="/settings/ai"><Icon name="settings" size={20}/><span><b>AI models &amp; logs</b><small>Routing, priorities and request history.</small></span><Icon name="chevron" size={16}/></NavLink></section> : null}
          {groups.map((group, index) => <section className="set-section" key={group.title} aria-labelledby={`set-g${index}`}>
            <h2 id={`set-g${index}`}>{group.title}</h2><p className="set-hint">{group.hint}</p>
            <div className="set-links">{group.tools.map(tool => <NavLink key={tool.to} className="set-link" to={tool.to}><Icon name={tool.icon} size={20}/><span><b>{tool.label}</b><small>{tool.description}</small></span><Icon name="chevron" size={16}/></NavLink>)}</div>
          </section>)}
        </> : null}
      </div>
    </div>
  </div>;
}
