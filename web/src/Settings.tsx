import React from "react";
import { useTheme, setTheme } from "./theme";
import { DeviceSettings, InstallationSettings } from "./local/AppFeatures";
import { NavLink } from "react-router-dom";
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

export default function Settings() {
  const { user, authenticated, logout } = useAuth();
  const [admin, setAdmin] = React.useState(false);
  const theme = useTheme();
  React.useEffect(() => { aiAdminRequest<{ allowed: boolean }>("/access").then(r => setAdmin(r.allowed)).catch(() => setAdmin(false)); }, []);
  return <div className="page page-narrow">
    <header className="page-header"><div><h1>Settings</h1><p>Appearance, account, connected services and specialist tools.</p></div></header>

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
    {authenticated ? <AgentSettings/> : null}
    {authenticated ? <IntegrationsSettings/> : null}
    <DeviceSettings/>
    {admin ? <section className="set-section" aria-labelledby="set-admin"><h2 id="set-admin">Administration</h2>
      <NavLink className="set-link" to="/settings/ai"><Icon name="settings" size={20}/><span><b>AI models &amp; logs</b><small>Routing, priorities and request history.</small></span><Icon name="chevron" size={16}/></NavLink></section> : null}

    {groups.map((group, index) => <section className="set-section" key={group.title} aria-labelledby={`set-g${index}`}>
      <h2 id={`set-g${index}`}>{group.title}</h2><p className="set-hint">{group.hint}</p>
      <div className="set-links">{group.tools.map(tool => <NavLink key={tool.to} className="set-link" to={tool.to}><Icon name={tool.icon} size={20}/><span><b>{tool.label}</b><small>{tool.description}</small></span><Icon name="chevron" size={16}/></NavLink>)}</div>
    </section>)}
  </div>;
}
