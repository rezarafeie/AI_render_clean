import { Suspense, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import PaneSkeleton from '../../components/PaneSkeleton';
import { Icon } from '../../components/Icon';
import { array } from './hermesUtils';
import { useHermes } from './HermesContext';
import { useAgentPanel } from './useAgentPanel';
import AgentWorkspace from './AgentWorkspace';
import AgentChat from './AgentChat';
import AgentIdeas from './AgentIdeas';
import AgentInsights from './AgentInsights';
import HermesOnboarding from './HermesOnboarding';

const TITLES = { content: 'Content', analytics: 'Analytics', settings: 'Settings', post: 'Post' };

/** Content, Analytics and Settings (a layout route, so the agent panel stays put while only the page changes): the page on the left, the agent in the Studio's side panel on the right. */
export default function HermesFrame() {
  const title = TITLES[useLocation().pathname.split('/')[2]] || 'Instagram';
  const { agent, runAgent, running, connected, updating } = useHermes();
  const panel = useAgentPanel('frame');
  const [tab, setTab] = useState('chat');
  const pending = array(agent?.proposals).filter((p) => p.status === 'proposed').length;
  const open = Boolean(connected) && panel.visible;
  return <div className="studio hermes" ref={panel.studioRef} data-layout={panel.layout} data-ws={open ? 'open' : 'closed'} data-resizing={panel.resizing || undefined}
    style={panel.layout === 'desktop' && open && panel.width ? { '--ws-w': `${panel.width}px` } : undefined}>
    <section className="chat-col" aria-label={title}>
      <header className="chat-head">
        <h1 className="chat-title">{title}</h1>
        {updating ? <span className="hs-updating" role="status">Updating…</span> : null}
        {connected && !open ? <button type="button" className="btn btn-sm btn-secondary" onClick={panel.open}><Icon name="panelRight" size={16}/>Agent{pending ? ` · ${pending}` : ''}</button> : null}
      </header>
      <div className="chat-scroll"><div className="hs-content" data-hermes-main>{connected === false ? <HermesOnboarding /> : <Suspense fallback={<PaneSkeleton />}><Outlet /></Suspense>}</div></div>
    </section>
    {panel.layout !== 'desktop' && panel.overlay ? <button className="ws-backdrop" onClick={panel.closeOverlay} aria-label="Close agent" tabIndex={-1}/> : null}
    {connected ? <AgentWorkspace panel={panel} label="Agent" tab={tab} onTab={setTab}
      tabs={[['chat', 'Agent', 'spark'], ['ideas', 'Ideas', 'wand', pending || null], ['insights', 'Insights', 'eye']]}
      actions={<button className="icon-btn" onClick={() => runAgent()} disabled={running} aria-label="New review" data-tip={running ? 'Reviewing…' : 'New review'}><Icon name="refresh" size={19}/></button>}>
      {tab === 'chat' ? <AgentChat title={title} /> : tab === 'ideas' ? <AgentIdeas /> : <AgentInsights />}
    </AgentWorkspace> : null}
  </div>;
}
