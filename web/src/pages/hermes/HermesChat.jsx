import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { Icon } from '../../components/Icon';
import hermesApi from '../../services/hermesApi';
import { array, number } from './hermesUtils';
import { useHermesData } from './hermesCache';
import { useHermes } from './HermesContext';
import { useAgentPanel } from './useAgentPanel';
import AgentWorkspace from './AgentWorkspace';
import AgentChat from './AgentChat';
import AgentIdeas from './AgentIdeas';
import AgentInsights from './AgentInsights';

function Data() {
  const { agent } = useHermes();
  const p = agent?.profile;
  const media = array(agent?.media);
  return <div className="agent-tab" dir="rtl">
    <section className="action-card"><h3>{p ? `@${p.username}` : 'پیج'}</h3>
      <p className="muted-text">{p ? [p.followers != null && `${number(p.followers)} فالوور`, p.follows != null && `${number(p.follows)} دنبال‌شونده`, p.media_count != null && `${number(p.media_count)} پست`].filter(Boolean).join(' · ') : 'هنوز خوانده نشده'}</p></section>
    {media.length ? <section className="action-card"><h3>پست‌های اخیر</h3><ul className="agent-list">{media.slice(0, 8).map((m) => <li key={m.id}>{(m.caption || '(بدون کپشن)').slice(0, 80)} — {m.likes ?? '?'} لایک · {m.comments ?? '?'} کامنت</li>)}</ul></section> : null}
    {agent?.analysis?.strategy ? <section className="action-card"><h3>استراتژی</h3><p className="muted-text">{[agent.analysis.strategy.niche, agent.analysis.strategy.audience].filter(Boolean).join(' · ')}</p></section> : null}
  </div>;
}

/** One agent conversation, laid out exactly like a Studio chat: the thread and composer on one side, the data it reads in the preview-style panel. */
export default function HermesChat() {
  const { chatId } = useParams();
  const { agent, connected } = useHermes();
  const chat = useHermesData(`chat:${chatId}`, () => hermesApi.getChat(chatId));
  const panel = useAgentPanel('chat');
  const [tab, setTab] = useState('data');
  const pending = array(agent?.proposals).filter((p) => p.status === 'proposed').length;
  const open = Boolean(connected) && panel.visible;
  const title = chat.data?.title || 'گفتگو';
  return <div className="studio hermes" ref={panel.studioRef} data-layout={panel.layout} data-ws={open ? 'open' : 'closed'} data-resizing={panel.resizing || undefined}
    style={panel.layout === 'desktop' && open && panel.width ? { '--ws-w': `${panel.width}px` } : undefined}>
    <section className="chat-col" aria-label="Conversation">
      <header className="chat-head">
        <h1 className="chat-title bidi wrap-safe" dir="auto" title={title}>{title}</h1>
        {!open ? <button type="button" className="btn btn-sm btn-secondary" onClick={panel.open}><Icon name="panelRight" size={16}/>Data</button> : null}
      </header>
      <AgentChat key={chatId} chatId={chatId} title={title} />
    </section>
    {panel.layout !== 'desktop' && panel.overlay ? <button className="ws-backdrop" onClick={panel.closeOverlay} aria-label="Close panel" tabIndex={-1}/> : null}
    <AgentWorkspace panel={panel} label="Data" tab={tab} onTab={setTab} tabs={[['data', 'Data', 'eye'], ['ideas', 'Ideas', 'wand', pending || null], ['insights', 'Insights', 'spark']]}>
      {tab === 'data' ? <Data /> : tab === 'ideas' ? <AgentIdeas /> : <AgentInsights />}
    </AgentWorkspace>
  </div>;
}
