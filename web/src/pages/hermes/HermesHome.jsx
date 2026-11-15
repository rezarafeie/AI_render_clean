import { useRef, useState } from 'react';
import { Link, NavLink, useNavigate } from 'react-router-dom';
import { Icon } from '../../components/Icon';
import { useHermesData } from './hermesCache';
import { array } from './hermesUtils';
import hermesApi from '../../services/hermesApi';
import { Composer } from '../../studio/Composer';
import { message } from './hermesUtils';
import { useHermes } from './HermesContext';
import HermesOnboarding from './HermesOnboarding';
import { ScrollRow } from '../../components/ScrollRow';

const SUGGESTIONS = ['پیجم را تحلیل کن', 'یک ایده‌ی ریلز بده', 'برنامه‌ی این هفته را بچین', 'بهترین زمان انتشار چیست؟'];

const fa = (value) => (value == null ? '—' : new Intl.NumberFormat('fa-IR', { notation: 'compact', maximumFractionDigits: 1 }).format(value));

/** A small summary of "my page" (profile line, three numbers, one finding) that opens the full overview. */
function PageCard() {
  const { agent, running } = useHermes();
  const profile = agent?.profile;
  const analysis = agent?.analysis;
  const score = analysis?.profile?.score;
  const finding = analysis?.strategy?.niche || array(analysis?.content?.do_more)[0] || '';
  return <Link to="/insta/overview" className="home-pagecard" aria-label="پیج من؛ دیدن خلاصه‌ی کامل">
    <span className="pc-avatar" aria-hidden="true">{(profile?.username || '?').slice(0, 1).toUpperCase()}</span>
    <span className="pc-main">
      <b dir="ltr">{profile ? `@${profile.username}` : 'پیج من'}</b>
      <small dir="auto">{finding || (running ? 'در حال خواندن پیج…' : analysis ? 'بررسی آماده است' : 'خلاصه‌ی پیج و ایده‌ها')}</small>
    </span>
    <span className="pc-nums">
      <span><b>{fa(profile?.followers)}</b><small>دنبال‌کننده</small></span>
      <span><b>{fa(profile?.media_count)}</b><small>پست</small></span>
      <span><b>{score != null ? fa(score) : '—'}</b><small>امتیاز</small></span>
    </span>
    <Icon name="chevronLeft" size={16}/>
  </Link>;
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
