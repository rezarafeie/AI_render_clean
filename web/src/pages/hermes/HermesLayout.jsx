import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Outlet } from 'react-router-dom';
import hermesApi from '../../services/hermesApi';
import { HermesContext } from './HermesContext';
import { useHermesData } from './hermesCache';
import { message } from './hermesUtils';
import './hermes.css';
import './hermes-shell.css';

/** Shares the agent's state with every Hermes page (cached, refreshed in the background); each page lays itself out like the Studio. */
export default function HermesLayout() {
  const agent = useHermesData('agent', () => hermesApi.getAgent());
  const connection = useHermesData('connection', () => hermesApi.getAgentConnection(), { enabled: !agent.data?.profile });
  const connected = agent.data?.profile ? true : connection.data ? connection.data.connected : null;
  const [starting, setStarting] = useState(false);
  const [runError, setRunError] = useState('');
  const running = agent.data?.run?.status === 'running';
  const busy = running || starting;
  const started = useRef(false);
  const reload = agent.reload;
  // The button answers at once (starting), a refusal is shown instead of swallowed, and the review is followed until it ends.
  const runAgent = useCallback(async (steps) => {
    setStarting(true); setRunError('');
    try { await hermesApi.runAgent(steps); } catch (e) { setRunError(message(e)); setStarting(false); return; }
    await reload();
    setStarting(false);
  }, [reload]);
  useEffect(() => {
    if (!busy) return undefined;
    const timer = setInterval(() => { void reload(); }, 2000);
    return () => clearInterval(timer);
  }, [busy, reload]);
  useEffect(() => {          // a connected account with no analysis yet starts the first review by itself
    if (connected && agent.data && !agent.data.analysis && !running && !started.current) { started.current = true; void runAgent(); }
  }, [connected, agent.data, running, runAgent]);
  const value = useMemo(() => ({ agent: agent.data, reloadAgent: reload, runAgent, running: busy, runError, connected, updating: agent.refreshing || connection.refreshing }), [agent.data, reload, runAgent, busy, runError, connected, agent.refreshing, connection.refreshing]);
  return <HermesContext.Provider value={value}><Outlet /></HermesContext.Provider>;
}
