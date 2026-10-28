import { useCallback, useEffect, useMemo, useRef } from 'react';
import { Outlet } from 'react-router-dom';
import hermesApi from '../../services/hermesApi';
import { HermesContext } from './HermesContext';
import { useHermesData } from './hermesCache';
import './hermes.css';
import './hermes-shell.css';

/** Shares the agent's state with every Hermes page (cached, refreshed in the background); each page lays itself out like the Studio. */
export default function HermesLayout() {
  const agent = useHermesData('agent', () => hermesApi.getAgent());
  const connection = useHermesData('connection', () => hermesApi.getAgentConnection(), { enabled: !agent.data?.profile });
  const connected = agent.data?.profile ? true : connection.data ? connection.data.connected : null;
  const running = agent.data?.run?.status === 'running';
  const started = useRef(false);
  const reload = agent.reload;
  const runAgent = useCallback(async (steps) => { await hermesApi.runAgent(steps).catch(() => {}); await reload(); }, [reload]);
  useEffect(() => {
    if (!running) return undefined;
    const timer = setInterval(() => { void reload(); }, 3500);
    return () => clearInterval(timer);
  }, [running, reload]);
  useEffect(() => {          // a connected account with no analysis yet starts the first review by itself
    if (connected && agent.data && !agent.data.analysis && !running && !started.current) { started.current = true; void runAgent(); }
  }, [connected, agent.data, running, runAgent]);
  const value = useMemo(() => ({ agent: agent.data, reloadAgent: reload, runAgent, connected, updating: agent.refreshing || connection.refreshing }), [agent.data, reload, runAgent, connected, agent.refreshing, connection.refreshing]);
  return <HermesContext.Provider value={value}><Outlet /></HermesContext.Provider>;
}
