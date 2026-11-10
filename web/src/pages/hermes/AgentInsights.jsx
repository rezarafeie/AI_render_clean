import { useState } from 'react';
import hermesApi from '../../services/hermesApi';
import { Icon } from '../../components/Icon';
import { array, reason } from './hermesUtils';
import { useHermes } from './HermesContext';

/** What the agent understood about the page, and the questions it still has. */
export default function AgentInsights({ embedded = false }) {
  const { agent, reloadAgent, runAgent, running } = useHermes();
  const [values, setValues] = useState({});
  const a = agent?.analysis;
  const open = array(agent?.questions).filter((q) => q.kind !== 'info');
  const [saved, setSaved] = useState({});
  const [problem, setProblem] = useState('');
  // An answer is only saved (instantly); the new analysis that uses the answers is one separate button, so answering several questions never starts several long runs.
  async function answer(key) {
    setProblem('');
    try { await hermesApi.answerAgent(key, values[key]); setSaved((prev) => ({ ...prev, [key]: true })); await reloadAgent(); } catch (e) { setProblem(reason(e)); }
  }
  const stored = Object.keys(agent?.answers || {}).length;
  return <div className={embedded ? 'agent-embedded' : 'agent-tab'} dir="rtl">
    {array(agent?.questions).filter((q) => q.kind === 'info').map((q) => <div key={q.id} className="notice" data-tone="info">{q.text}</div>)}
    {open.map((q) => <section key={q.id} className="action-card"><h3>{q.text}</h3>
      <div className="agent-ask"><input className="input" dir="rtl" value={values[q.id] || ''} onChange={(e) => setValues({ ...values, [q.id]: e.target.value })} placeholder={q.kind === 'handles' ? '@نام‌کاربری‌ها با ویرگول' : ''} />
        <button className="btn btn-sm" type="button" disabled={!(values[q.id] || '').trim()} onClick={() => answer(q.id)}>{saved[q.id] ? 'ذخیره شد ✓' : 'ثبت'}</button></div></section>)}
    {stored || Object.keys(saved).length ? <section className="action-card"><p className="muted-text">{`${stored} پاسخ ذخیره شده است.`} برای اینکه تحلیل و ایده‌ها با پاسخ‌هایتان به‌روز شود، دکمهٔ زیر را بزنید.</p>
      <div className="agent-ask"><button className="btn btn-sm" type="button" disabled={running} onClick={() => void runAgent(['analyze', 'propose'])}>{running ? 'در حال تحلیل…' : 'به‌روزرسانی تحلیل با پاسخ‌ها'}</button></div></section> : null}
    {problem ? <div className="notice" data-tone="error">{problem}</div> : null}
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
      {a.benchmark?.basis || array(a.benchmark?.formulas_that_over_index).length || agent?.benchmark ? <details className="action-card" open><summary>بنچمارک رقبا (ig-viral)</summary>
        {a.benchmark?.basis ? <p dir="auto">{a.benchmark.basis}</p> : null}
        {array(a.benchmark?.formulas_that_over_index).length ? <p><strong>فرمول‌هایی که بیشتر از میانه می‌ترکانند:</strong> {array(a.benchmark.formulas_that_over_index).join('، ')}</p> : null}
        {array(a.benchmark?.what_top_reels_share).length ? <><strong>مشترک ریلزهای برتر</strong><ul className="agent-list">{array(a.benchmark.what_top_reels_share).map((t, i) => <li key={i} dir="auto">{t}</li>)}</ul></> : null}
        {array(a.benchmark?.ideas_to_borrow).length ? <><strong>فرمول‌هایی که می‌شود قرض گرفت</strong><ul className="agent-list">{array(a.benchmark.ideas_to_borrow).map((t, i) => <li key={i} dir="auto">{t}</li>)}</ul></> : null}
        {a.benchmark?.sample_note ? <p className="muted-text" dir="auto">{a.benchmark.sample_note}</p> : null}
        {agent?.benchmark?.sample?.reels ? <p className="muted-text">بنچمارک ذخیره‌شده: {agent.benchmark.sample.reels} ریلز از {agent.benchmark.sample.accounts} پیج · {agent.benchmark.sample.confidence}</p> : <p className="muted-text">برای بنچمارک واقعی، در «مهارت‌ها ← بنچمارک رقبا» جدول ریلزهای رقبا را بچسبانید؛ بدون داده، چیزی حدس زده نمی‌شود.</p>}
      </details> : null}
      {array(a.data_gaps).length ? <p className="muted-text">داده‌ی ناقص: {array(a.data_gaps).join('؛ ')}</p> : null}</> : null}
  </div>;
}
