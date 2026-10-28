import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import hermesApi from '../../services/hermesApi';
import AgentPanel from './AgentPanel';
import HermesOnboarding from './HermesOnboarding';
import { HermesContext } from './HermesContext';
import { useHermesData } from './hermesCache';
import './hermes.css';
import './hermes-shell.css';

const TABS = [['/hermes', 'Overview'], ['/hermes/content', 'Content'], ['/hermes/analytics', 'Analytics'], ['/hermes/settings', 'Settings']];

export default function HermesLayout() {
  const location = useLocation();
  const [panel, setPanel] = useState(() => { try { return localStorage.getItem('hermes:panel') !== '0'; } catch { return true; } });
  const agent = useHermesData('agent', () => hermesApi.getAgent());
  const connection = useHermesData('connection', () => hermesApi.getAgentConnection(), { enabled: !agent.data?.profile });
  const connected = agent.data?.profile ? true : connection.data ? connection.data.connected : null;
  const running = agent.data?.run?.status === 'running';
  const started = useRef(false);
  const reload = agent.reload;

  const runAgent = useCallback(async (steps) => { await hermesApi.runAgent(steps).catch(() => {}); await reload(); }, [reload]);
  useEffect(() => {                                    // while a run is going, follow it; a connected account with no analysis yet starts one
    if (!running) return undefined;
    const timer = setInterval(() => { void reload(); }, 3500);
    return () => clearInterval(timer);
  }, [running, reload]);
  useEffect(() => {
    if (connected && agent.data && !agent.data.analysis && !running && !started.current) { started.current = true; void runAgent(); }
  }, [connected, agent.data, running, runAgent]);
  const toggle = () => setPanel((value) => { try { localStorage.setItem('hermes:panel', value ? '0' : '1'); } catch { /* optional */ } return !value; });
  const value = useMemo(() => ({ agent: agent.data, reloadAgent: reload, runAgent, openAgent: () => setPanel(true), connected }), [agent.data, reload, runAgent, connected]);
  const updating = agent.refreshing || connection.refreshing;

  return <HermesContext.Provider value={value}>
    <div className={`hs-shell ${connected && panel ? 'has-panel' : ''}`}>
      <div className="hs-main-col">
        <header className="hs-head">
          <div className="hs-title"><h1>Instagram</h1>{updating && <span className="hs-updating" role="status">Updating…</span>}</div>
          <nav className="hs-tabs" aria-label="Instagram sections">
            {TABS.map(([to, label]) => <NavLink key={to} to={to} end={to === '/hermes'} className={({ isActive }) => `hs-tab ${isActive ? 'is-on' : ''}`}>{label}</NavLink>)}
          </nav>
          {connected && <button className={`btn btn-secondary btn-sm hs-agent-toggle ${panel ? 'is-on' : ''}`} type="button" onClick={toggle} aria-pressed={panel}>{panel ? 'Hide agent' : 'Agent'}</button>}
        </header>
        <main className="hs-main" data-hermes-main key={location.pathname.split('/')[2] || 'overview'}>
          {connected === false && location.pathname === '/hermes' ? <HermesOnboarding /> : <Outlet />}
        </main>
      </div>
      {connected && panel && <AgentPanel onClose={toggle} />}
    </div>
  </HermesContext.Provider>;
}
