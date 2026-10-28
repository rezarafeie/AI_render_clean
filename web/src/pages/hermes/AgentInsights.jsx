import { useState } from 'react';
import hermesApi from '../../services/hermesApi';
import { Icon } from '../../components/Icon';
import { array } from './hermesUtils';
import { useHermes } from './HermesContext';

/** What the agent understood about the page, and the questions it still has. */
export default function AgentInsights() {
  const { agent, reloadAgent } = useHermes();
  const [values, setValues] = useState({});
  const a = agent?.analysis;
  const open = array(agent?.questions).filter((q) => q.kind !== 'info');
  async function answer(key) { await hermesApi.answerAgent(key, values[key]).catch(() => {}); await hermesApi.runAgent(['analyze', 'propose']).catch(() => {}); void reloadAgent(); }
  return <div className="agent-tab" dir="rtl">
    {array(agent?.questions).filter((q) => q.kind === 'info').map((q) => <div key={q.id} className="notice" data-tone="info">{q.text}</div>)}
    {open.map((q) => <section key={q.id} className="action-card"><h3>{q.text}</h3>
      <div className="agent-ask"><input className="input" dir="rtl" value={values[q.id] || ''} onChange={(e) => setValues({ ...values, [q.id]: e.target.value })} placeholder={q.kind === 'handles' ? '@نام‌کاربری‌ها با ویرگول' : ''} />
        <button className="btn btn-sm" type="button" disabled={!(values[q.id] || '').trim()} onClick={() => answer(q.id)}>ثبت</button></div></section>)}
    {!a && !open.length ? <div className="ws-empty"><span className="empty-icon"><Icon name="eye" size={24}/></span><h2>تحلیل آماده نیست</h2><p>ایجنت در حال خواندن پروفایل و پست‌های شماست.</p></div> : null}
    {a ? <>
      <section className="action-card"><h3>امتیاز پروفایل {a.profile?.score != null ? `${a.profile.score}/۱۰۰` : ''}</h3>
        {a.strategy ? <p className="muted-text">{[a.strategy.niche, a.strategy.audience].filter(Boolean).join(' · ')}</p> : null}
        {array(a.strategy?.pillars).length ? <p className="muted-text">ستون‌های محتوا: {array(a.strategy.pillars).join('، ')}</p> : null}</section>
      {array(a.profile?.parts).length ? <details className="action-card" open><summary>جزئیات پروفایل</summary><ul className="agent-list">{array(a.profile.parts).map((p, i) => <li key={i}><strong>{p.part}</strong> ({p.score}) — {p.note}{p.rewrite ? <em> ← {p.rewrite}</em> : null}</li>)}</ul></details> : null}
      {a.content ? <details className="action-card" open><summary>محتوای قبلی</summary>
        {array(a.content.top).length ? <><strong>بهترین‌ها</strong><ul className="agent-list">{array(a.content.top).map((t, i) => <li key={i}>{t.post} — {t.why}</li>)}</ul></> : null}
        {array(a.content.weak).length ? <><strong>ضعیف‌ها</strong><ul className="agent-list">{array(a.content.weak).map((t, i) => <li key={i}>{t.post} — {t.why}</li>)}</ul></> : null}
        {array(a.content.do_more).length ? <p><strong>بیشتر بساز:</strong> {array(a.content.do_more).join('، ')}</p> : null}
        {array(a.content.stop).length ? <p><strong>دیگر نساز:</strong> {array(a.content.stop).join('، ')}</p> : null}</details> : null}
      {array(a.data_gaps).length ? <p className="muted-text">داده‌ی ناقص: {array(a.data_gaps).join('؛ ')}</p> : null}</> : null}
  </div>;
}
