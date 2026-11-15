import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, useNavigate } from 'react-router-dom';
import { Icon } from '../../components/Icon';
import { useHermesData } from './hermesCache';
import { array } from './hermesUtils';
import hermesApi from '../../services/hermesApi';
import { api } from '../../api';
import { Composer } from '../../studio/Composer';
import { message } from './hermesUtils';
import { useHermes } from './HermesContext';
import HermesOnboarding from './HermesOnboarding';
import { ScrollRow } from '../../components/ScrollRow';

const SUGGESTIONS = ['پیجم را تحلیل کن', 'یک ایده‌ی ریلز بده', 'برنامه‌ی این هفته را بچین', 'بهترین زمان انتشار چیست؟'];

const fa = (value) => (value == null ? '—' : new Intl.NumberFormat('fa-IR', { notation: 'compact', maximumFractionDigits: 1 }).format(value));

const sinceText = (iso) => {
  const time = iso ? Date.parse(iso) : 0;
  if (!time) return '';
  const diff = Date.now() - time;
  if (diff < 60_000) return 'همین حالا';
  const rtf = new Intl.RelativeTimeFormat('fa', { numeric: 'auto' });
  if (diff < 3_600_000) return rtf.format(-Math.round(diff / 60_000), 'minute');
  if (diff < 86_400_000) return rtf.format(-Math.round(diff / 3_600_000), 'hour');
  return rtf.format(-Math.round(diff / 86_400_000), 'day');
};

/** "My page" in brief: profile picture and name, one finding, three numbers, the count of new ideas, when it was last updated and a button that updates it here. */
function PageCard() {
  const { agent, running, runAgent } = useHermes();
  const [picture, setPicture] = useState('');
  useEffect(() => { void api.studioHome().then((home) => setPicture(home?.instagpt?.picture || '')).catch(() => {}); }, []);
  const profile = agent?.profile;
  const analysis = agent?.analysis;
  const score = analysis?.profile?.score;
  const finding = analysis?.strategy?.niche || array(analysis?.content?.do_more)[0] || '';
  const fresh = array(agent?.proposals).filter((p) => p.status === 'proposed').length;
  const updated = sinceText(agent?.run?.finished_at);
  return <section className="home-pagecard" dir="rtl" aria-label="پیج من">
    <Link to="/insta/overview" className="pc-top">
      <span className="pc-avatar" aria-hidden="true">{picture ? <img src={picture} alt="" referrerPolicy="no-referrer" onError={() => setPicture('')}/> : (profile?.username || '?').slice(0, 1).toUpperCase()}</span>
      <span className="pc-main">
        <b dir="ltr">{profile ? `@${profile.username}` : 'پیج من'}</b>
        <small dir="auto">{finding || (running ? 'در حال خواندن پیج…' : analysis ? 'بررسی آماده است' : 'خلاصه‌ی پیج و ایده‌ها')}</small>
      </span>
      {fresh ? <span className="pc-badge" title="ایده‌های آماده‌ی بازبینی">{fa(fresh)} ایده‌ی جدید</span> : null}
      <Icon name="chevronLeft" size={16}/>
    </Link>
    <div className="pc-foot">
      <span className="pc-nums">
        <span><b>{fa(profile?.followers)}</b><small>دنبال‌کننده</small></span>
        <span><b>{fa(profile?.media_count)}</b><small>پست</small></span>
        <span><b>{score != null ? fa(score) : '—'}</b><small>امتیاز</small></span>
      </span>
      <span className="pc-update">
        <small>{running ? 'در حال به‌روزرسانی…' : updated ? `آخرین به‌روزرسانی ${updated}` : 'هنوز به‌روز نشده'}</small>
        <button type="button" className="btn btn-sm btn-secondary" onClick={() => runAgent()} disabled={running}><Icon name="refresh" size={14}/>{running ? 'صبر کنید' : 'به‌روزرسانی'}</button>
      </span>
    </div>
  </section>;
}

/** The home page is the Studio's: a title, the input, quick suggestions; the overview of the page sits under them. */
export default function HermesHome() {
  const navigate = useNavigate();
  const { connected } = useHermes();
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const textareaRef = useRef(null);
  const chats = useHermesData('chats', () => hermesApi.listChats());
  async function start(raw) {
    const value = (raw ?? text).trim();
    if (!value || busy) return;
    setBusy(true); setError('');
    try {
      const chat = await hermesApi.createChat();
      try { sessionStorage.setItem(`hermes:first:${chat.id}`, value); } catch { /* optional */ }
      window.dispatchEvent(new Event('hermes:chats-updated'));
      navigate(`/insta/chat/${chat.id}`);
    } catch (e) { setError(message(e)); setBusy(false); }
  }
  if (connected === false) return <div className="studio-home"><div className="home-inner"><HermesOnboarding /></div></div>;
  return <div className="studio-home hermes-home" data-hermes-main>
    <div className="home-inner">
      <h1>What do you want to know about your page?</h1>
      <Composer variant="home" text={text} setText={setText} files={[]} onRemoveFile={() => {}} onFiles={() => {}} processing={busy} onSend={() => void start()}
        error={error} onDismissError={() => setError('')} hasSpeech={false} listening={false} onListen={() => {}} autoFocus textareaRef={textareaRef}
        placeholder="Ask about your page, content, ideas, or schedule…" textOnly />
      <section className="home-suggest" aria-label="پیشنهادها">
        <ScrollRow>
          <NavLink to="/insta/overview" className="chip home-chip"><Icon name="user" size={15}/><span>پیج من</span></NavLink>
          <NavLink to="/insta/insights" className="chip home-chip"><Icon name="spark" size={15}/><span>بینش‌ها</span></NavLink>
          <NavLink to="/insta/skills" className="chip home-chip"><Icon name="wand" size={15}/><span>مهارت‌ها</span></NavLink>
          {SUGGESTIONS.slice(0, 3).map((item) => <button key={item} className="chip home-chip" onClick={() => void start(item)}><span dir="auto">{item}</span></button>)}
        </ScrollRow>
      </section>
      <PageCard />
      {array(chats.data?.chats).length ? <section className="home-recent" aria-label="آخرین گفتگوها">
        <div className="home-recent-head"><h2>آخرین گفتگوها</h2></div>
        <ul>{array(chats.data.chats).slice(0, 3).map((item) => <li key={item.id}><Link to={`/insta/chat/${item.id}`} title={item.title}>
          <span className="home-thumb" aria-hidden="true"><Icon name="spark" size={18}/></span>
          <span className="home-recent-copy"><span className="home-title" dir="auto">{item.title || 'گفتگوی جدید'}</span>
            <span className="home-meta"><span>گفتگو</span><span>{item.updated_at ? new Date(item.updated_at).toLocaleDateString('fa-IR', { month: 'long', day: 'numeric' }) : ''}</span></span></span>
        </Link></li>)}</ul>
      </section> : null}
    </div>
  </div>;
}
