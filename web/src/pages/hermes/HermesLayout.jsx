import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Outlet } from 'react-router-dom';
import hermesApi from '../../services/hermesApi';
import { api } from '../../api';
import { productionStatus, proposalStatus } from './ideaProduction';
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
  const [production, setProduction] = useState({});
  const previousRun = useRef(null);
  const [runError, setRunError] = useState('');
  const running = agent.data?.run?.status === 'running';
  const busy = running || starting;
  const started = useRef(false);
  const reload = agent.reload;
  // The button answers at once (starting), a refusal is shown instead of swallowed, and the review is followed until it ends.
  const runAgent = useCallback(async (steps) => {
    previousRun.current = agent.data?.run?.started_at;
    setStarting(true); setRunError('');
    try { await hermesApi.runAgent(steps); } catch (e) { setRunError(message(e)); setStarting(false); return; }
    await reload();
  }, [reload, agent.data?.run?.started_at]);
  useEffect(() => {
    const run = agent.data?.run;
    if (starting && (run?.status === 'running' || (run?.started_at && run.started_at !== previousRun.current))) setStarting(false);
  }, [agent.data?.run, starting]);
  useEffect(() => {
    const tick = () => { if (document.visibilityState !== 'hidden') void reload(); };
    const timer = setInterval(tick, busy ? 2000 : 10000);
    window.addEventListener('focus', tick);
    return () => { clearInterval(timer); window.removeEventListener('focus', tick); };
  }, [busy, reload]);
  useEffect(() => {
    if (!starting) return undefined;
    const timer = setTimeout(() => { setStarting(false); setRunError('وضعیت شروع بررسی هنوز دریافت نشده؛ پیگیری خودکار ادامه دارد.'); }, 30000);
    return () => clearTimeout(timer);
  }, [starting]);
  useEffect(() => { if (running) setRunError(''); }, [running]);
  const trackedProposals = JSON.stringify((agent.data?.proposals || []).filter(p => p.status === 'in_production' && p.conversation_id).map(p => ({id:p.id, conversation_id:p.conversation_id})));
  useEffect(() => {
    let alive = true, inFlight = false;
    const proposals = JSON.parse(trackedProposals);
    async function sync() {
      if (inFlight || document.visibilityState === 'hidden' || !proposals.length) return;
      inFlight = true;
      try {
        const next = {};
        // Bound simultaneous requests; every endpoint enforces current-user ownership.
        for (let i = 0; i < proposals.length; i += 3) {
          await Promise.all(proposals.slice(i, i + 3).map(async p => {
            try {
              const conversation = await api.getStudioConversation(p.conversation_id);
              const id = conversation.state?.motion?.motion_id;
              const motion = id ? await api.motionView(id) : null;
              next[p.id] = productionStatus(conversation, motion);
            } catch { /* Never claim completion when the project cannot be checked. */ }
          }));
          if (!alive) return;
        }
        if (alive) setProduction(next);
      } finally { inFlight = false; }
    }
    void sync();
    const timer = setInterval(sync, 10000);
    return () => { alive = false; clearInterval(timer); };
  }, [trackedProposals]);
  useEffect(() => {          // a connected account with no analysis yet starts the first review by itself
    if (connected && agent.data && !agent.data.analysis && !running && !started.current) { started.current = true; void runAgent(); }
  }, [connected, agent.data, running, runAgent]);
  const displayAgent = useMemo(() => agent.data ? {...agent.data, proposals:(agent.data.proposals || []).map(p => ({...p, status:proposalStatus(p, production[p.id])}))} : null, [agent.data, production]);
  const value = useMemo(() => ({ agent: displayAgent, reloadAgent: reload, runAgent, running: busy, runError, connected, updating: agent.refreshing || connection.refreshing }), [displayAgent, reload, runAgent, busy, runError, connected, agent.refreshing, connection.refreshing]);
  return <HermesContext.Provider value={value}><Outlet /></HermesContext.Provider>;
}
