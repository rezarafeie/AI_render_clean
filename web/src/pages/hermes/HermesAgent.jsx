import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import hermesApi from '../../services/hermesApi';
import { api } from '../../api';
import { array, message, number } from './hermesUtils';
import HermesOnboarding from './HermesOnboarding';

const STEP_LABEL = { sync: 'خواندن پروفایل و پست‌ها', analyze: 'تحلیل پروفایل و محتوا', propose: 'ساخت پیشنهاد محتوا' };
const ENGINE_LABEL = { talking: 'صحبتی', explainer: 'اکسپلینر' };
const STATUS_LABEL = { proposed: 'پیشنهاد جدید', approved: 'تأیید شد', in_production: 'در حال ساخت در ادیتور', produced: 'ساخته شد', queued: 'در صف انتشار', rejected: 'رد شد' };
const SKILL_CHOICES = [['reel', 'ریلز'], ['carousel', 'کاروسل'], ['story', 'استوری'], ['caption', 'کپشن'], ['plan', 'برنامه‌ی هفته'], ['comment', 'کامنت برای دیگران'], ['reply', 'پاسخ به کامنت'], ['dm', 'دایرکت'], ['human', 'طبیعی‌کردن متن'], ['viral', 'فایل ایده از رقبا']];

function Steps({ run }) {
  return <ol className="hm-stack" style={{ listStyle: 'none', padding: 0, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
    {Object.entries(STEP_LABEL).map(([key, label]) => {
      const active = run?.status === 'running' && run.step === key;
      return <li key={key} className="hm-tiny" style={{ opacity: active || run?.status !== 'running' ? 1 : .55 }}>{active ? '◐' : '●'} {label}</li>;
    })}
  </ol>;
}

function Analysis({ analysis }) {
  if (!analysis) return null;
  const { profile, content, strategy, data_gaps: gaps } = analysis;
  return <section className="hm-panel hm-stack">
    <div className="hm-section-title"><h3>آنچه ایجنت از پیج شما فهمید</h3>{profile?.score != null && <span>امتیاز پروفایل {profile.score}/۱۰۰</span>}</div>
    {strategy && <p>{[strategy.niche && `حوزه: ${strategy.niche}`, strategy.audience && `مخاطب: ${strategy.audience}`, strategy.format_mix && `ترکیب قالب: ${strategy.format_mix}`].filter(Boolean).join(' · ')}</p>}
    {array(strategy?.pillars).length > 0 && <p className="hm-tiny">ستون‌های محتوا: {array(strategy.pillars).join('، ')}</p>}
    {array(profile?.parts).length > 0 && <details><summary>جزئیات پروفایل</summary><ul>{array(profile.parts).map((p, i) => <li key={i}><strong>{p.part}</strong> ({p.score}) — {p.note}{p.rewrite ? <em> ← {p.rewrite}</em> : null}</li>)}</ul></details>}
    {content && <details open><summary>محتوای قبلی</summary>
      {array(content.top).length > 0 && <><strong>بهترین‌ها</strong><ul>{array(content.top).map((t, i) => <li key={i}>{t.post} — {t.why}</li>)}</ul></>}
      {array(content.weak).length > 0 && <><strong>ضعیف‌ها</strong><ul>{array(content.weak).map((t, i) => <li key={i}>{t.post} — {t.why}</li>)}</ul></>}
      {array(content.do_more).length > 0 && <p><strong>بیشتر بساز:</strong> {array(content.do_more).join('، ')}</p>}
      {array(content.stop).length > 0 && <p><strong>دیگر نساز:</strong> {array(content.stop).join('، ')}</p>}</details>}
    {array(gaps).length > 0 && <p className="hm-tiny">داده‌ی ناقص: {array(gaps).join('؛ ')}</p>}
  </section>;
}

function Questions({ questions, onAnswer, busy }) {
  const [values, setValues] = useState({});
  const open = array(questions).filter((q) => q.kind !== 'info');
  const infos = array(questions).filter((q) => q.kind === 'info');
  if (!open.length && !infos.length) return null;
  return <section className="hm-panel hm-stack">
    <div className="hm-section-title"><h3>ایجنت از شما می‌پرسد</h3></div>
    {infos.map((q) => <p key={q.id} className="hm-tiny">ℹ {q.text}</p>)}
    {open.map((q) => <label key={q.id} className="field"><span className="field-label">{q.text}</span>
      <div className="hm-account-actions"><input className="input" dir="rtl" value={values[q.id] || ''} placeholder={q.kind === 'handles' ? '@نام‌کاربری‌ها با ویرگول' : ''} onChange={(e) => setValues({ ...values, [q.id]: e.target.value })} />
        <button className="hm-btn hm-btn-primary" type="button" disabled={busy || !(values[q.id] || '').trim()} onClick={() => onAnswer(q.id, values[q.id])}>ثبت</button></div></label>)}
  </section>;
}

function Proposal({ item, onApprove, onReject, working }) {
  const hookScore = item.checks?.hook?.score;
  return <article className="hm-panel hm-stack" dir="rtl">
    <div className="hm-section-title"><div><h3>{item.title}</h3><p className="hm-tiny">{ENGINE_LABEL[item.engine] || item.engine} · {item.length_seconds ? `${item.length_seconds} ثانیه` : 'ریلز'} · {STATUS_LABEL[item.status] || item.status}</p></div></div>
    {item.why && <p>{item.why}</p>}
    {item.hook && <p><strong>هوک:</strong> {item.hook}{hookScore != null && <small> (امتیاز {hookScore})</small>}</p>}
    <details><summary>متن و کپشن</summary>{item.script && <pre className="hm-pre" style={{ whiteSpace: 'pre-wrap' }}>{item.script}</pre>}{item.caption && <><strong>کپشن</strong><pre className="hm-pre" style={{ whiteSpace: 'pre-wrap' }}>{item.caption}</pre><p className="hm-tiny">{array(item.hashtags).join(' ')}</p></>}</details>
    {item.status === 'proposed' && <div className="hm-account-actions">
      <button className="hm-btn hm-btn-primary" type="button" disabled={working} onClick={() => onApprove(item)}>{working ? 'در حال ساخت پروژه…' : 'تأیید و ساخت در ادیتور'}</button>
      <button className="hm-btn hm-btn-quiet" type="button" disabled={working} onClick={() => onReject(item)}>رد</button></div>}
    {item.conversation_id && <Link to={`/studio/${item.conversation_id}`}>باز کردن پروژه در ادیتور ←</Link>}
  </article>;
}

export default function HermesAgent() {
  const navigate = useNavigate();
  const [connected, setConnected] = useState(null);
  const [state, setState] = useState(null);
  const [error, setError] = useState('');
  const [working, setWorking] = useState('');
  const [ask, setAsk] = useState({ skill: 'reel', text: '' });
  const [asked, setAsked] = useState(null);
  const started = useRef(false);
  const refresh = useCallback(async () => { const next = await hermesApi.getAgent(); setState(next); return next; }, []);
  useEffect(() => {
    hermesApi.getSkillAccount().then((a) => setConnected(!!a.connected)).catch((e) => { setError(message(e)); setConnected(false); });
  }, []);
  useEffect(() => { if (connected) refresh().catch((e) => setError(message(e))); }, [connected, refresh]);
  useEffect(() => {
    if (!state || !connected || started.current) return;
    if (!state.analysis && state.run?.status !== 'running') { started.current = true; hermesApi.runAgent().then(refresh).catch((e) => setError(message(e))); }
  }, [state, connected, refresh]);
  useEffect(() => {
    if (state?.run?.status !== 'running') return undefined;
    const timer = setInterval(() => { refresh().catch(() => {}); }, 3500);
    return () => clearInterval(timer);
  }, [state?.run?.status, refresh]);
  if (connected === null) return <div className="hm-page hm-rise"><div className="hm-loading" role="status">Loading Hermes…</div></div>;
  if (!connected) return <HermesOnboarding />;
  const running = state?.run?.status === 'running';
  const profile = state?.profile;

  async function approve(item) {
    setWorking(item.id); setError('');
    try {
      const brief = item.editor_brief || item.title;
      const conversation = await api.createStudioConversation(item.title || 'ریلز اینستاگرام');
      await api.sendStudioMessage(conversation.id, `یک ریلز اینستاگرام (عمودی، فارسی، سبک ${ENGINE_LABEL[item.engine] || 'صحبتی'}) بساز. این پیشنهاد را حساب اینستاگرام کاربر از تحلیل پیجش ساخته و تأیید شده است.\n\n${brief}${item.hook ? `\n\nهوک: ${item.hook}` : ''}${item.script ? `\n\nمتن گفتاری پیشنهادی:\n${item.script}` : ''}${item.caption ? `\n\nکپشن برای انتشار:\n${item.caption}\n${array(item.hashtags).join(' ')}` : ''}`, [], {});
      await hermesApi.setProposalStatus(item.id, 'in_production', conversation.id);
      navigate(`/studio/${conversation.id}`);
    } catch (e) { setError(message(e)); setWorking(''); }
  }
  async function reject(item) { await hermesApi.setProposalStatus(item.id, 'rejected').catch((e) => setError(message(e))); refresh().catch(() => {}); }
  async function answer(key, value) {
    setError('');
    try { setState(await hermesApi.answerAgent(key, value)); await hermesApi.runAgent(['analyze', 'propose']); refresh().catch(() => {}); } catch (e) { setError(message(e)); }
  }
  async function more() { setError(''); try { await hermesApi.runAgent(); await refresh(); } catch (e) { setError(message(e)); } }
  async function doAsk() { setError(''); setAsked(null); setWorking('ask'); try { setAsked(await hermesApi.askAgent(ask.skill, ask.text)); } catch (e) { setError(message(e)); } finally { setWorking(''); } }

  const proposals = array(state?.proposals).slice().reverse();
  const live = proposals.filter((p) => p.status !== 'rejected');
  const queue = proposals.filter((p) => ['produced', 'queued'].includes(p.status));
  return <div className="hm-page hm-rise" dir="rtl">
    <div className="hm-page-head"><div><span className="hm-eyebrow">HERMES AGENT</span><h2>ایجنت اینستاگرام</h2>
      <p>{profile ? `@${profile.username} · ${profile.followers != null ? `${number(profile.followers)} فالوور` : ''} · ${profile.media_count != null ? `${number(profile.media_count)} پست` : ''}` : 'در حال شناخت پیج شما…'}</p></div>
      <button className="hm-btn hm-btn-quiet" type="button" disabled={running} onClick={more}>{running ? 'در حال بررسی…' : 'بررسی و پیشنهاد جدید'}</button></div>
    <Steps run={state?.run} />
    {error && <div className="hm-alert" role="alert">{error}</div>}
    {state?.run?.status === 'error' && <div className="hm-alert" role="alert">بررسی کامل نشد ({state.run.error}). {state.run.error === 'AGENT_NO_ACCOUNT' ? 'اتصال اینستاگرام را دوباره بررسی کنید.' : 'دوباره امتحان کنید؛ اتصال به Composio گاهی ناپایدار است.'}</div>}
    <Questions questions={state?.questions} onAnswer={answer} busy={running} />
    <Analysis analysis={state?.analysis} />
    <section className="hm-stack"><div className="hm-section-title"><h3>پیشنهادهای ساخت محتوا</h3><span>{live.length}</span></div>
      {live.length ? live.map((p) => <Proposal key={p.id} item={p} onApprove={approve} onReject={reject} working={working === p.id} />) : <p className="hm-tiny">{running ? 'ایجنت در حال ساخت پیشنهاد است…' : 'هنوز پیشنهادی نیست.'}</p>}</section>
    <section className="hm-panel hm-stack"><div className="hm-section-title"><h3>صف انتشار</h3><span>{queue.length}</span></div>
      {queue.length ? queue.map((p) => <p key={p.id}>{p.title} — {STATUS_LABEL[p.status]}</p>) : <p className="hm-tiny">ویدیوهایی که در ادیتور ساخته شوند اینجا می‌آیند. انتشار خودکار از Composio هنوز فعال نیست؛ هر انتشار نیاز به تأیید شما دارد.</p>}</section>
    <details className="hm-panel"><summary>از ایجنت بخواه (ریلز، کاروسل، استوری، کپشن، کامنت، دایرکت…)</summary>
      <div className="hm-stack"><div className="hm-account-actions"><select value={ask.skill} onChange={(e) => setAsk({ ...ask, skill: e.target.value })}>{SKILL_CHOICES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        <button className="hm-btn hm-btn-primary" type="button" disabled={working === 'ask'} onClick={doAsk}>{working === 'ask' ? 'در حال کار…' : 'اجرا'}</button></div>
        <textarea className="input" rows={4} dir="rtl" value={ask.text} placeholder="ایده یا متن (خالی بگذارید تا از پیج خودتان استفاده شود)" onChange={(e) => setAsk({ ...ask, text: e.target.value })} />
        {asked && <pre className="hm-pre" style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(asked.result, null, 1)}</pre>}</div></details>
  </div>;
}
