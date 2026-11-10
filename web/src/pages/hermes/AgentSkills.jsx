import { useState } from 'react';
import hermesApi from '../../services/hermesApi';
import { Icon } from '../../components/Icon';
import { array, message, reason } from './hermesUtils';
import { useHermesData } from './hermesCache';
import { useHermes } from './HermesContext';

const GROUPS = { understand: 'شناخت پیج و رقبا', plan: 'برنامه‌ریزی', create: 'ساخت محتوا', engage: 'تعامل', quality: 'کیفیت متن' };

function Result({ out }) {
  const r = out.result || {};
  const swipe = out.checks?.swipe;
  return <section className="action-card" dir="rtl">
    {r.title ? <h3 dir="auto">{r.title}</h3> : null}
    {r.summary ? <p dir="auto">{r.summary}</p> : null}
    {swipe ? <p className="muted-text">نمونه: {swipe.n} ریلز از {swipe.accounts} پیج · خط پایه {typeof swipe.baseline === 'object' ? JSON.stringify(swipe.baseline) : (swipe.baseline ?? '—')} · {swipe.confidence}</p> : null}
    {array(swipe?.reels).length ? <details open><summary>ریلزهای برتر (ضریب نسبت به میانهٔ همان پیج)</summary>
      <ul className="agent-list">{array(swipe.reels).slice(0, 10).map((x, i) => <li key={i} dir="auto">{x.account} — {x.multiple ?? x.outlier}× — {x.hook}{x.formula ? ` (${x.formula})` : ''}</li>)}</ul></details> : null}
    {array(r.sections).map((s, i) => <div key={i}><strong dir="auto">{s.heading}</strong>{s.body ? <p dir="auto">{s.body}</p> : null}
      {array(s.items).length ? <ul className="agent-list">{array(s.items).map((t, k) => <li key={k} dir="auto">{t}</li>)}</ul> : null}</div>)}
    {array(r.hooks).length ? <><strong>هوک‌ها</strong><ul className="agent-list">{array(r.hooks).map((t, i) => <li key={i} dir="auto">{typeof t === 'string' ? t : t.text}</li>)}</ul></> : null}
    {r.script ? <pre className="agent-pre" dir="auto">{typeof r.script === 'string' ? r.script : JSON.stringify(r.script, null, 1)}</pre> : null}
    {r.caption ? <p dir="auto">{r.caption} {array(r.hashtags).join(' ')}</p> : null}
    {r.editor_brief ? <details><summary>شرح برای ادیتور</summary><p dir="auto">{r.editor_brief}</p></details> : null}
    {array(r.next_steps).length ? <><strong>قدم بعد</strong><ul className="agent-list">{array(r.next_steps).map((t, i) => <li key={i} dir="auto">{t}</li>)}</ul></> : null}
  </section>;
}

/** Hermes's skills (the 13 of the vendored instagram-agent-skill) plus the competitor list that the benchmark rests on. */
export default function AgentSkills() {
  const { agent, reloadAgent, runAgent } = useHermes();
  const catalog = useHermesData('skills', () => hermesApi.getSkills());
  const [skill, setSkill] = useState('viral');
  const [text, setText] = useState('');
  const [handle, setHandle] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [out, setOut] = useState(null);
  const list = array(catalog.data?.skills);
  const spec = list.find((s) => s.id === skill);
  const competitors = array(agent?.competitors);
  async function saveCompetitors(next) { await hermesApi.answerAgent('competitors', next.join(',')).catch((e) => setError(reason(e))); void reloadAgent(); }
  async function run() {
    setBusy(true); setError(''); setOut(null);
    try { setOut(await hermesApi.runSkill(skill, text, 'fa')); if (skill === 'viral') void reloadAgent(); } catch (e) { setError(reason(e)); } finally { setBusy(false); }
  }
  return <div className="agent-tab" dir="rtl">
    <section className="action-card"><h3>رقبا</h3>
      <p className="muted-text">رقبا را اینجا یا در چت بگویید («@نام را به رقبا اضافه کن»). اتصال اینستاگرام از طریق Composio فقط پیج خودتان را می‌خواند؛ برای بنچمارک جدول ریلزهای رقبا را در مهارت «بنچمارک رقبا» بچسبانید.</p>
      <div className="agent-chips">{competitors.map((c) => <button key={c} type="button" className="chip" onClick={() => void saveCompetitors(competitors.filter((x) => x !== c))} title="حذف">@{c} ×</button>)}</div>
      <div className="agent-ask"><input className="input" dir="ltr" value={handle} onChange={(e) => setHandle(e.target.value)} placeholder="@username" />
        <button className="btn btn-sm" type="button" disabled={!handle.trim()} onClick={() => { void saveCompetitors([...competitors, ...handle.split(/[ ,\n]+/).map((h) => h.replace(/^@/, '').trim()).filter(Boolean)]); setHandle(''); }}>افزودن</button>
        <button className="btn btn-sm btn-secondary" type="button" onClick={() => void runAgent(['benchmark', 'analyze', 'propose'])}><Icon name="refresh" size={14}/>بنچمارک و ایده‌های تازه</button></div>
      {agent?.benchmark?.sample?.reels ? <p className="muted-text">بنچمارک ذخیره‌شده: {agent.benchmark.sample.reels} ریلز از {agent.benchmark.sample.accounts} پیج · {agent.benchmark.sample.confidence}</p> : null}
    </section>
    <section className="action-card"><h3>مهارت‌ها</h3>
      {Object.entries(GROUPS).map(([g, label]) => { const items = list.filter((s) => s.group === g); return items.length ? <div key={g}><strong>{label}</strong>
        <div className="agent-chips">{items.map((s) => <button key={s.id} type="button" className="chip" aria-pressed={skill === s.id} onClick={() => { setSkill(s.id); setOut(null); }}>{s.label}</button>)}</div></div> : null; })}
      {spec ? <><p className="muted-text" dir="auto">{spec.hint}</p>
        <textarea className="input" rows={skill === 'viral' ? 8 : 4} dir="auto" value={text} onChange={(e) => setText(e.target.value)} placeholder={skill === 'viral' ? 'نام‌پیج⇥فالوور⇥میانهٔ بازدید⇥بازدید ریل⇥هوک (هر ریل در یک خط)' : spec.account ? 'اختیاری؛ خالی بگذارید تا از پیج وصل‌شده استفاده شود' : ''} />
        <div className="agent-ask"><button className="btn btn-sm" type="button" disabled={busy} onClick={run}>{busy ? 'در حال اجرا…' : 'اجرا'}</button></div></> : null}
      {error ? <div className="notice" data-tone="error">{error}</div> : null}
    </section>
    {out ? <Result out={out} /> : null}
  </div>;
}
