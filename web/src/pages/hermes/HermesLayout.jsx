import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import hermesApi from '../../services/hermesApi';
import { Icon } from '../../components/Icon';
import { Resizer, usePanelWidth } from '../../components/Resizer';
import { useStudioLayout } from '../../components/hooks';
import { usePanelFullscreen } from '../../studio/Workspace';
import AgentChat from './AgentChat';
import AgentIdeas from './AgentIdeas';
import AgentInsights from './AgentInsights';
import HermesOnboarding from './HermesOnboarding';
import { HermesContext } from './HermesContext';
import { useHermesData } from './hermesCache';
import { array } from './hermesUtils';
import './hermes.css';
import './hermes-shell.css';

const TABS = [['/hermes', 'Overview'], ['/hermes/content', 'Content'], ['/hermes/analytics', 'Analytics'], ['/hermes/settings', 'Settings']];
const AGENT_TABS = [['chat', 'Agent', 'spark'], ['ideas', 'Ideas', 'wand'], ['insights', 'Insights', 'eye']];
const BOUNDS = { min: 340, max: 900 };
const MIN_CONTENT = 520;
const lsGet = (key, fallback) => { try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; } };
const lsSet = (key, value) => { try { localStorage.setItem(key, value); } catch { /* optional */ } };
const TITLES = { '/hermes': 'Overview', '/hermes/content': 'Content', '/hermes/analytics': 'Analytics', '/hermes/settings': 'Settings' };

export default function HermesLayout() {
  const location = useLocation();
  const layout = useStudioLayout();
  const mode = layout === 'mobile' ? 'tablet' : layout;                 // small screens get the overlay behaviour of the tablet layout
  const [desktopOpen, setDesktopOpen] = useState(() => lsGet('editorgpt.hermes.agent', 'open') !== 'closed');
  const [overlay, setOverlay] = useState(false);
  const [tab, setTab] = useState('chat');
  const agent = useHermesData('agent', () => hermesApi.getAgent());
  const connection = useHermesData('connection', () => hermesApi.getAgentConnection(), { enabled: !agent.data?.profile });
  const connected = agent.data?.profile ? true : connection.data ? connection.data.connected : null;
  const running = agent.data?.run?.status === 'running';
  const started = useRef(false);
  const reload = agent.reload;

  const studioRef = useRef(null);
  const panelRef = useRef(null);
  const [saved, setSaved] = usePanelWidth('editorgpt.hermes.agent.width', BOUNDS);
  const [live, setLive] = useState(null);
  const [resizing, setResizing] = useState(false);
  const fullscreen = usePanelFullscreen();
  const setNode = useCallback((element) => { panelRef.current = element; fullscreen.node.current = element; }, [fullscreen.node]);

  const runAgent = useCallback(async (steps) => { await hermesApi.runAgent(steps).catch(() => {}); await reload(); }, [reload]);
  useEffect(() => {
    if (!running) return undefined;
    const timer = setInterval(() => { void reload(); }, 3500);
    return () => clearInterval(timer);
  }, [running, reload]);
  useEffect(() => {          // a connected account with no analysis yet starts the first review by itself
    if (connected && agent.data && !agent.data.analysis && !running && !started.current) { started.current = true; void runAgent(); }
  }, [connected, agent.data, running, runAgent]);

  const visible = Boolean(connected) && (mode === 'desktop' ? desktopOpen : overlay);
  const openAgent = useCallback((next) => { if (next) setTab(next); if (mode === 'desktop') { setDesktopOpen(true); lsSet('editorgpt.hermes.agent', 'open'); } else setOverlay(true); }, [mode]);
  const closeAgent = () => { if (mode === 'desktop') { setDesktopOpen(false); lsSet('editorgpt.hermes.agent', 'closed'); } else setOverlay(false); };
  const value = useMemo(() => ({ agent: agent.data, reloadAgent: reload, runAgent, openAgent, connected }), [agent.data, reload, runAgent, openAgent, connected]);
  const width = live ?? saved;
  const updating = agent.refreshing || connection.refreshing;
  const title = TITLES[location.pathname] || 'Hermes';
  const pending = array(agent.data?.proposals).filter((p) => p.status === 'proposed').length;

  return <HermesContext.Provider value={value}>
    <div className="studio hermes" ref={studioRef} data-layout={mode} data-ws={visible ? 'open' : 'closed'} data-resizing={resizing || undefined}
      style={mode === 'desktop' && visible && width ? { '--ws-w': `${width}px` } : undefined}>
      <section className="chat-col" aria-label={title}>
        <header className="chat-head">
          <nav className="tabs-bar hs-nav" aria-label="Sections">
            {TABS.map(([to, label]) => <NavLink key={to} to={to} end={to === '/hermes'} role="tab" className="tab"
              aria-selected={to === '/hermes' ? location.pathname === '/hermes' : location.pathname.startsWith(to)}>{label}</NavLink>)}
          </nav>
          <span className="grow"/>
          {updating ? <span className="hs-updating" role="status">Updating…</span> : null}
          {connected && !visible ? <button type="button" className="btn btn-sm btn-secondary" onClick={() => openAgent()}><Icon name="panelRight" size={16}/>Agent{pending ? ` · ${pending}` : ''}</button> : null}
        </header>
        <div className="chat-scroll">
          <div className="hs-content" data-hermes-main key={location.pathname.split('/')[2] || 'overview'}>
            {connected === false && location.pathname === '/hermes' ? <HermesOnboarding /> : <Outlet />}
          </div>
        </div>
      </section>
      {mode === 'tablet' && overlay ? <button className="ws-backdrop" onClick={() => setOverlay(false)} aria-label="Close agent" tabIndex={-1}/> : null}
      {connected ? <section className="workspace" ref={setNode} data-max={fullscreen.active || undefined} aria-label="Agent">
        {mode === 'desktop' && visible ? <Resizer panel={panelRef} edge="start" label="عرض پنل ایجنت" width={width}
          bounds={() => ({ min: BOUNDS.min, max: Math.min(BOUNDS.max, (studioRef.current?.clientWidth ?? 1400) - MIN_CONTENT) })}
          onResize={setLive} onDragState={setResizing} onCommit={(next) => { setSaved(next); setLive(null); }}/> : null}
        <header className="ws-head">
          <div className="tabs-bar" role="tablist" aria-label="Agent">
            {AGENT_TABS.map(([id, label, icon]) => <button key={id} role="tab" aria-selected={tab === id} className="tab" onClick={() => setTab(id)}>
              <Icon name={icon} size={15}/>{label}{id === 'ideas' && pending ? ` · ${pending}` : ''}</button>)}
          </div>
          <span className="grow"/>
          <button className="icon-btn" onClick={() => runAgent()} disabled={running} aria-label="New review" data-tip={running ? 'Reviewing…' : 'New review'}><Icon name="refresh" size={19}/></button>
          <button className="icon-btn" onClick={() => void fullscreen.toggle()} aria-pressed={fullscreen.active} aria-label={fullscreen.active ? 'Exit full screen' : 'Full screen'}
            data-tip={fullscreen.active ? 'Exit full screen' : 'Full screen'}><Icon name={fullscreen.active ? 'fullscreenExit' : 'fullscreen'} size={19}/></button>
          {!fullscreen.active ? <button className="icon-btn" onClick={closeAgent} aria-label="Hide agent" data-tip="Hide agent"><Icon name="panelRight" size={19}/></button> : null}
        </header>
        <div className="ws-body hs-agent-body">
          {tab === 'chat' ? <AgentChat title={title} /> : tab === 'ideas' ? <AgentIdeas /> : <AgentInsights />}
        </div>
      </section> : null}
    </div>
  </HermesContext.Provider>;
}
