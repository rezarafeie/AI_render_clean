import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import hermesApi from '../../services/hermesApi';
import { api } from '../../api';
import { array, message, number } from './hermesUtils';
import { peekCache, writeCache } from './hermesCache';
import { useHermes } from './HermesContext';

const ENGINE = { talking: 'صحبتی', explainer: 'اکسپلینر' };
const STATUS = { proposed: 'پیشنهاد', in_production: 'در حال ساخت', produced: 'ساخته شد', queued: 'در صف انتشار', rejected: 'رد شد' };
const STEP = { sync: 'خواندن پروفایل و پست‌ها', analyze: 'تحلیل پیج', propose: 'ساخت پیشنهاد' };
const CHIPS = ['این صفحه را برایم توضیح بده', 'بهترین زمان انتشار چیست؟', 'هشتگ‌های مناسب پیج من', 'یک ایده‌ی ریلز بده', 'برنامه‌ی این هفته را بچین'];
const TAB_FOR = { overview: '', content: 'content', analytics: 'analytics', settings: 'settings' };

function Chat({ title }) {
  const navigate = useNavigate();
  const { runAgent } = useHermes();
  const [messages, setMessages] = useState(() => peekCache('chat') || []);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const end = useRef(null);
  useEffect(() => { end.current?.scrollIntoView({ block: 'end' }); }, [messages, busy]);
  async function send(raw) {
    const value = (raw ?? text).trim();
    if (!value || busy) return;
    const history = messages.slice(-8);
    const next = [...messages, { role: 'user', text: value }];
    setMessages(next); setText(''); setBusy(true); setError('');
    const page = { title, text: (document.querySelector('[data-hermes-main]')?.innerText || '').slice(0, 6000) };   // what the person is looking at
    try {
      const out = await hermesApi.chatAgent(value, page, history);
      const done = [...next, { role: 'agent', text: out.reply, suggestions: out.suggestions }].slice(-40);
      setMessages(done); writeCache('chat', done);
      if (out.action?.type === 'open_tab' && out.action.tab in TAB_FOR) navigate(`/hermes${TAB_FOR[out.action.tab] ? `/${TAB_FOR[out.action.tab]}` : ''}`);
      if (out.action?.type === 'run_agent') void runAgent();
    } catch (e) { setError(message(e)); } finally { setBusy(false); }
  }
  return <div className="hs-chat">
    <div className="hs-chat-log" role="log" aria-live="polite">
      {!messages.length && <p className="hs-muted">درباره‌ی چیزی که روی صفحه می‌بینید بپرسید؛ ایجنت محتوای همین صفحه را می‌بیند.</p>}
      {messages.map((m, i) => <div key={i} className={`hs-msg hs-msg-${m.role}`}><p>{m.text}</p>
        {m.role === 'agent' && i === messages.length - 1 && array(m.suggestions).length > 0 && <div className="hs-chips">{m.suggestions.map((s) => <button key={s} type="button" className="btn btn-ghost btn-sm" onClick={() => send(s)}>{s}</button>)}</div>}</div>)}
      {busy && <div className="hs-msg hs-msg-agent hs-typing">در حال فکر کردن…</div>}
      <div ref={end} />
    </div>
    {error && <div className="hs-error" role="alert">{error}</div>}
    {!messages.length && <div className="hs-chips">{CHIPS.map((c) => <button key={c} type="button" className="btn btn-ghost btn-sm" onClick={() => send(c)}>{c}</button>)}</div>}
    <form className="hs-compose" onSubmit={(e) => { e.preventDefault(); void send(); }}>
      <input className="input" dir="rtl" value={text} placeholder="از ایجنت بپرس…" onChange={(e) => setText(e.target.value)} disabled={busy} />
      <button className="btn btn-sm" type="submit" disabled={busy || !text.trim()}>ارسال</button>
    </form>
  </div>;
}

function Proposals() {
  const navigate = useNavigate();
  const { agent, reloadAgent } = useHermes();
  const [working, setWorking] = useState('');
  const [error, setError] = useState('');
  const list = array(agent?.proposals).filter((p) => p.status !== 'rejected').slice().reverse();
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
  if (!list.length) return <p className="hs-muted">هنوز پیشنهادی نیست. ایجنت بعد از تحلیل پیج پیشنهاد می‌سازد.</p>;
  return <div className="hs-list">
    {error && <div className="hs-error" role="alert">{error}</div>}
    {list.map((p) => <article key={p.id} className="hs-card">
      <div className="hs-card-head"><strong>{p.title}</strong><span className="hs-tag">{ENGINE[p.engine] || p.engine}</span></div>
      {p.hook && <p className="hs-hook">«{p.hook}»</p>}
      {p.why && <p className="hs-muted">{p.why}</p>}
      <details><summary>متن و کپشن</summary>{p.script && <pre className="hs-pre">{p.script}</pre>}{p.caption && <pre className="hs-pre">{p.caption}</pre>}</details>
      <div className="hs-row">
        {p.status === 'proposed' && <><button className="btn btn-sm" type="button" disabled={!!working} onClick={() => approve(p)}>{working === p.id ? 'در حال ساخت…' : 'تأیید و ساخت در ادیتور'}</button>
          <button className="btn btn-ghost btn-sm" type="button" disabled={!!working} onClick={() => reject(p)}>رد</button></>}
        {p.status !== 'proposed' && <span className="hs-muted">{STATUS[p.status] || p.status}</span>}
        {p.conversation_id && <Link className="btn btn-ghost btn-sm" to={`/studio/${p.conversation_id}`}>باز کردن در ادیتور</Link>}
      </div></article>)}
  </div>;
}

function Findings() {
  const { agent, reloadAgent } = useHermes();
  const [values, setValues] = useState({});
  const a = agent?.analysis;
  const open = array(agent?.questions).filter((q) => q.kind !== 'info');
  async function answer(key) {
    await hermesApi.answerAgent(key, values[key]).catch(() => {}); await hermesApi.runAgent(['analyze', 'propose']).catch(() => {}); void reloadAgent();
  }
  return <div className="hs-list">
    {array(agent?.questions).filter((q) => q.kind === 'info').map((q) => <p key={q.id} className="hs-muted">ℹ {q.text}</p>)}
    {open.map((q) => <label key={q.id} className="field"><span className="field-label">{q.text}</span>
      <div className="hs-compose"><input className="input" dir="rtl" value={values[q.id] || ''} onChange={(e) => setValues({ ...values, [q.id]: e.target.value })} placeholder={q.kind === 'handles' ? '@نام‌کاربری‌ها با ویرگول' : ''} />
        <button className="btn btn-sm" type="button" disabled={!(values[q.id] || '').trim()} onClick={() => answer(q.id)}>ثبت</button></div></label>)}
    {!a && !open.length && <p className="hs-muted">تحلیل هنوز آماده نیست.</p>}
    {a && <>
      <div className="hs-card"><strong>امتیاز پروفایل {a.profile?.score != null ? `${a.profile.score}/۱۰۰` : ''}</strong>
        {a.strategy && <p className="hs-muted">{[a.strategy.niche, a.strategy.audience].filter(Boolean).join(' · ')}</p>}
        {array(a.strategy?.pillars).length > 0 && <p className="hs-muted">ستون‌های محتوا: {array(a.strategy.pillars).join('، ')}</p>}</div>
      {array(a.profile?.parts).length > 0 && <details className="hs-card"><summary>جزئیات پروفایل</summary><ul>{array(a.profile.parts).map((p, i) => <li key={i}><strong>{p.part}</strong> ({p.score}) — {p.note}{p.rewrite ? <em> ← {p.rewrite}</em> : null}</li>)}</ul></details>}
      {a.content && <details className="hs-card" open><summary>محتوای قبلی</summary>
        {array(a.content.top).length > 0 && <><strong>بهترین‌ها</strong><ul>{array(a.content.top).map((t, i) => <li key={i}>{t.post} — {t.why}</li>)}</ul></>}
        {array(a.content.weak).length > 0 && <><strong>ضعیف‌ها</strong><ul>{array(a.content.weak).map((t, i) => <li key={i}>{t.post} — {t.why}</li>)}</ul></>}
        {array(a.content.do_more).length > 0 && <p><strong>بیشتر بساز:</strong> {array(a.content.do_more).join('، ')}</p>}
        {array(a.content.stop).length > 0 && <p><strong>دیگر نساز:</strong> {array(a.content.stop).join('، ')}</p>}</details>}
      {array(a.data_gaps).length > 0 && <p className="hs-muted">داده‌ی ناقص: {array(a.data_gaps).join('؛ ')}</p>}</>}
  </div>;
}

export default function AgentPanel({ onClose }) {
  const location = useLocation();
  const { agent, runAgent } = useHermes();
  const [tab, setTab] = useState('chat');
  const run = agent?.run;
  const running = run?.status === 'running';
  const pending = useMemo(() => array(agent?.proposals).filter((p) => p.status === 'proposed').length, [agent]);
  const questions = array(agent?.questions).filter((q) => q.kind !== 'info').length;
  const title = ({ '/hermes': 'نمای کلی', '/hermes/content': 'محتوا', '/hermes/analytics': 'آمار', '/hermes/settings': 'تنظیمات' })[location.pathname] || 'Hermes';
  return <aside className="hs-agent" aria-label="ایجنت اینستاگرام">
    <header className="hs-agent-head">
      <div><strong>ایجنت</strong>
        <span className="hs-muted">{running ? `${STEP[run.step] || 'در حال کار'}…` : agent?.profile ? `@${agent.profile.username}${agent.profile.followers != null ? ` · ${number(agent.profile.followers)} فالوور` : ''}` : 'آماده'}</span></div>
      <div className="hs-row">
        <button className="btn btn-ghost btn-sm" type="button" disabled={running} onClick={() => runAgent()}>{running ? '…' : 'بررسی جدید'}</button>
        {onClose && <button className="btn btn-ghost btn-sm hs-close" type="button" onClick={onClose} aria-label="بستن">✕</button>}
      </div>
    </header>
    {run?.status === 'error' && <div className="hs-error" role="alert">بررسی کامل نشد ({run.error}). دوباره امتحان کنید.</div>}
    <nav className="hs-seg" role="tablist">
      {[['chat', 'گفتگو'], ['proposals', `پیشنهادها${pending ? ` (${pending})` : ''}`], ['findings', `تحلیل${questions ? ` · ${questions} سؤال` : ''}`]].map(([id, label]) => <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? 'is-on' : ''} type="button" onClick={() => setTab(id)}>{label}</button>)}
    </nav>
    <div className="hs-agent-body">{tab === 'chat' ? <Chat title={title} /> : tab === 'proposals' ? <Proposals /> : <Findings />}</div>
  </aside>;
}
