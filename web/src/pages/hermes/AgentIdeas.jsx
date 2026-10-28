import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import hermesApi from '../../services/hermesApi';
import { api } from '../../api';
import { Icon } from '../../components/Icon';
import { array, message } from './hermesUtils';
import { useHermes } from './HermesContext';

const ENGINE = { talking: 'صحبتی', explainer: 'اکسپلینر' };
const STATUS = { proposed: 'پیشنهاد', in_production: 'در حال ساخت', produced: 'ساخته شد', queued: 'در صف انتشار', rejected: 'رد شد' };

/** Ideas the agent proposes for the editor's engines; approving one opens an editor project with its script. */
export default function AgentIdeas({ limit = 0, embedded = false }) {
  const navigate = useNavigate();
  const { agent, reloadAgent, runAgent } = useHermes();
  const [working, setWorking] = useState('');
  const [error, setError] = useState('');
  const all = array(agent?.proposals).filter((p) => p.status !== 'rejected').slice().reverse();
  const list = limit ? all.slice(0, limit) : all;
  async function approve(item) {
    setWorking(item.id); setError('');
    try {
      const conversation = await api.createStudioConversation(item.title || 'ریلز اینستاگرام');
      await api.sendStudioMessage(conversation.id, `یک ریلز اینستاگرام (عمودی، فارسی، سبک ${ENGINE[item.engine] || 'صحبتی'}) بساز. این پیشنهاد را ایجنت اینستاگرام از تحلیل پیج کاربر ساخته و کاربر تأیید کرده است.\n\n${item.editor_brief || item.title}${item.hook ? `\n\nهوک: ${item.hook}` : ''}${item.script ? `\n\nمتن گفتاری پیشنهادی:\n${item.script}` : ''}${item.caption ? `\n\nکپشن برای انتشار:\n${item.caption}\n${array(item.hashtags).join(' ')}` : ''}`, [], {});
      await hermesApi.setProposalStatus(item.id, 'in_production', conversation.id);
      navigate(`/studio/${conversation.id}`);
    } catch (e) { setError(message(e)); setWorking(''); }
  }
  async function reject(item) { await hermesApi.setProposalStatus(item.id, 'rejected').catch((e) => setError(message(e))); void reloadAgent(); }
  return <div className={embedded ? 'agent-embedded' : 'agent-tab'}>
    {error ? <div className="notice" data-tone="error" role="alert">{error}</div> : null}
    {!list.length ? <div className="ws-empty"><span className="empty-icon"><Icon name="spark" size={24}/></span><h2>هنوز ایده‌ای نیست</h2><p>ایجنت بعد از تحلیل پیج، ایده و سناریو پیشنهاد می‌دهد.</p>
      <button className="btn btn-secondary btn-sm" type="button" onClick={() => runAgent()}>بررسی جدید</button></div> : null}
    {list.map((p) => <article key={p.id} className="action-card" dir="rtl">
      <div className="agent-card-head"><h3>{p.title}</h3><span className="agent-tag">{ENGINE[p.engine] || p.engine}</span></div>
      {p.hook ? <p className="agent-hook">«{p.hook}»</p> : null}
      {p.why ? <p className="muted-text">{p.why}</p> : null}
      <details><summary>متن و کپشن</summary>{p.script ? <pre className="agent-pre">{p.script}</pre> : null}{p.caption ? <pre className="agent-pre">{p.caption}</pre> : null}</details>
      <div className="action-buttons">
        {p.status === 'proposed' ? <><button className="btn btn-sm" type="button" disabled={!!working} onClick={() => approve(p)}><Icon name="check" size={15}/>{working === p.id ? 'در حال ساخت…' : 'تأیید و ساخت در ادیتور'}</button>
          <button className="btn btn-secondary btn-sm" type="button" disabled={!!working} onClick={() => reject(p)}>رد</button></> : <span className="muted-text">{STATUS[p.status] || p.status}</span>}
        {p.conversation_id ? <Link className="btn btn-secondary btn-sm" to={`/studio/${p.conversation_id}`}>باز کردن در ادیتور</Link> : null}
      </div></article>)}
  </div>;
}
