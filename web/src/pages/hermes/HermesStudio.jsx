import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import hermesApi from '../../services/hermesApi';
import { api } from '../../api';
import { array, message, number } from './hermesUtils';
import HermesOnboarding from './HermesOnboarding';

const GROUPS = [['understand', 'بشناس'], ['plan', 'برنامه بریز'], ['create', 'بساز'], ['engage', 'تعامل'], ['quality', 'کیفیت']];
const copy = (text) => navigator.clipboard?.writeText(text).catch(() => {});

function Result({ data, onProduce, producing }) {
  const r = data.result || {};
  const hookChecks = array(data.checks?.hooks);
  return <section className="hm-panel hm-stack" dir="rtl" aria-live="polite">
    <div className="hm-section-title"><div><h3>{r.title || 'نتیجه'}</h3>{r.summary && <p>{r.summary}</p>}</div>
      <span>{data.account_used ? 'با داده‌ی حساب شما' : 'بدون داده‌ی حساب'}</span></div>
    {array(r.hooks).length > 0 && <div><strong>هوک‌ها</strong><ol>{array(r.hooks).map((hook, i) => <li key={i}>{hook}
      {hookChecks[i]?.check?.score != null && <small> — امتیاز هوک {hookChecks[i].check.score}</small>}</li>)}</ol></div>}
    {r.script && <div><strong>متن ویدیو</strong><pre className="hm-pre" style={{ whiteSpace: 'pre-wrap' }}>{r.script}</pre></div>}
    {data.checks?.beats?.rows && <p className="hm-tiny">زمان‌بندی تقریبی: {number(Math.round(data.checks.beats.total_seconds || 0))} ثانیه</p>}
    {r.caption && <div><strong>کپشن</strong><pre className="hm-pre" style={{ whiteSpace: 'pre-wrap' }}>{r.caption}</pre>
      {array(r.hashtags).length > 0 && <p className="hm-tiny">{array(r.hashtags).join(' ')}</p>}</div>}
    {array(r.sections).map((s, i) => <div key={i}><strong>{s.heading}</strong>{s.body && <p>{s.body}</p>}{array(s.items).length > 0 && <ul>{array(s.items).map((it, j) => <li key={j}>{it}</li>)}</ul>}</div>)}
    {array(r.next_steps).length > 0 && <div><strong>قدم بعدی</strong><ul>{array(r.next_steps).map((it, i) => <li key={i}>{it}</li>)}</ul></div>}
    <p className="hm-tiny">{data.checks?.sounds_like_ai ? 'بررسی لحن: ' + JSON.stringify(data.checks.sounds_like_ai.verdict || data.checks.sounds_like_ai.score || '') : ''}</p>
    <div className="hm-account-actions">
      <button className="hm-btn hm-btn-quiet" type="button" onClick={() => copy([r.title, r.script, r.caption].filter(Boolean).join('\n\n') || JSON.stringify(r, null, 1))}>کپی</button>
      {(data.can_produce || r.editor_brief) && <button className="hm-btn hm-btn-primary" type="button" disabled={producing} onClick={() => onProduce(r)}>{producing ? 'در حال ساخت پروژه…' : 'ساخت ویدیو در ادیتور'}</button>}
    </div>
  </section>;
}

export default function HermesStudio() {
  const navigate = useNavigate();
  const [skills, setSkills] = useState([]);
  const [account, setAccount] = useState(null);
  const [loading, setLoading] = useState(true);
  const [skill, setSkill] = useState('reel');
  const [text, setText] = useState('');
  const [language, setLanguage] = useState('fa');
  const [busy, setBusy] = useState(false);
  const [producing, setProducing] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState(null);
  useEffect(() => {
    Promise.all([hermesApi.getSkills(), hermesApi.getSkillAccount()]).then(([s, a]) => { setSkills(array(s.skills)); setAccount(a); })
      .catch((e) => setError(message(e))).finally(() => setLoading(false));
  }, []);
  const current = useMemo(() => skills.find((item) => item.id === skill), [skills, skill]);
  if (loading) return <div className="hm-page hm-rise"><div className="hm-loading" role="status">Loading Hermes studio…</div></div>;
  if (!account?.connected && !error) return <HermesOnboarding />;
  async function run() {
    setBusy(true); setError(''); setData(null);
    try { setData(await hermesApi.runSkill(skill, text, language)); } catch (e) { setError(message(e)); } finally { setBusy(false); }
  }
  async function produce(result) {
    setProducing(true); setError('');
    try {
      const brief = result.editor_brief || [result.title, result.script || result.caption].filter(Boolean).join('\n\n');
      const conversation = await api.createStudioConversation(result.title || 'ویدیوی اینستاگرام');
      await api.sendStudioMessage(conversation.id, `یک ریلز اینستاگرام (عمودی، فارسی) بساز.\n\n${brief}${result.script ? `\n\nمتن گفتاری پیشنهادی:\n${result.script}` : ''}${result.caption ? `\n\nکپشن:\n${result.caption}` : ''}`, [], {});
      navigate(`/studio/${conversation.id}`);
    } catch (e) { setError(message(e)); setProducing(false); }
  }
  const profile = account?.profile;
  return <div className="hm-page hm-rise" dir="rtl">
    <div className="hm-page-head"><div><span className="hm-eyebrow">HERMES STUDIO</span><h2>از پیج خودت شروع کن</h2><p>هر ابزار، مهارت واقعی instagram-agent-skill است و روی داده‌ی همین حساب اجرا می‌شود.</p></div></div>
    {profile && <section className="hm-panel"><strong>@{profile.username}</strong>
      <span className="hm-tiny"> · {profile.followers != null ? `${number(profile.followers)} فالوور` : 'فالوور نامشخص'} · {profile.media_count != null ? `${number(profile.media_count)} پست` : ''} · Composio (فقط‌خواندنی)</span>
      {array(account.recent_posts).length > 0 && <ul className="hm-tiny">{account.recent_posts.slice(0, 5).map((p) => <li key={p.id}>{(p.caption || '').slice(0, 70) || '(بدون کپشن)'} — {p.likes ?? '?'} لایک · {p.comments ?? '?'} کامنت</li>)}</ul>}</section>}
    {error && <div className="hm-alert" role="alert">{error}</div>}
    <div className="hm-stack">{GROUPS.map(([id, label]) => <div key={id}><strong>{label}</strong>
      <div className="hm-account-actions">{skills.filter((item) => item.group === id).map((item) => <button key={item.id} type="button" className={`hm-btn ${skill === item.id ? 'hm-btn-primary' : 'hm-btn-quiet'}`} onClick={() => { setSkill(item.id); setData(null); }}>{item.label}</button>)}</div></div>)}</div>
    {current && <section className="hm-panel hm-form-panel" aria-busy={busy}>
      <label className="field"><span className="field-label">{current.label}</span>
        <textarea className="input" rows={6} dir="rtl" value={text} placeholder={current.hint} maxLength={20000} onChange={(e) => setText(e.target.value)} /></label>
      <div className="hm-account-actions">
        <select value={language} onChange={(e) => setLanguage(e.target.value)} aria-label="Language"><option value="fa">فارسی</option><option value="en">English</option></select>
        <button className="hm-btn hm-btn-primary" type="button" onClick={run} disabled={busy}>{busy ? 'در حال کار…' : 'اجرا'}</button></div>
      {current.id === 'viral' && <p className="hm-tiny">جستجوی خودکار ریلزهای موفق از اینستاگرام (طبق اسکیل اصلی) هنوز وصل نیست؛ محتوای رقبا را خودتان بچسبانید.</p>}
    </section>}
    {data && <Result data={data} onProduce={produce} producing={producing} />}
    <p className="hm-tiny">انتشار پست و ارسال پیام/کامنت از طریق Composio بدون تأیید صریح انجام نمی‌شود و در این نسخه فعال نیست؛ خروجی‌ها پیش‌نویس‌اند.</p>
  </div>;
}
