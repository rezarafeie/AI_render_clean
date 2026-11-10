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
import HermesOverview from './HermesOverview';
import { ScrollRow } from '../../components/ScrollRow';

const SUGGESTIONS = ['پیجم را تحلیل کن', 'یک ایده‌ی ریلز بده', 'برنامه‌ی این هفته را بچین', 'بهترین زمان انتشار چیست؟'];

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
      navigate(`/hermes/chat/${chat.id}`);
    } catch (e) { setError(message(e)); setBusy(false); }
  }
  if (connected === false) return <div className="studio-home"><div className="home-inner"><HermesOnboarding /></div></div>;
  return <div className="studio-home hermes-home" data-hermes-main>
    <div className="home-inner">
      <h1>What do you want to know about your page?</h1>
      <Composer variant="home" text={text} setText={setText} files={[]} onRemoveFile={() => {}} onFiles={() => {}} processing={busy} onSend={() => void start()}
        error={error} onDismissError={() => setError('')} hasSpeech={false} listening={false} onListen={() => {}} autoFocus textareaRef={textareaRef}
        placeholder="Ask about your page, content, ideas, or schedule…" textOnly />
      <ScrollRow>{SUGGESTIONS.map((item) => <button key={item} className="chip home-chip" onClick={() => void start(item)}><span dir="auto">{item}</span></button>)}</ScrollRow>
      <div className="hs-home-links">
        <NavLink to="/hermes/skills" className="chip home-chip"><Icon name="wand" size={15}/><span>مهارت‌ها</span></NavLink>
        <NavLink to="/hermes/insights" className="chip home-chip"><Icon name="spark" size={15}/><span>بینش‌ها</span></NavLink>
      </div>
      {array(chats.data?.chats).length ? <section className="home-recent" aria-label="آخرین گفتگوها" dir="rtl">
        <div className="home-recent-head"><h2>آخرین گفتگوها</h2></div>
        <ul>{array(chats.data.chats).slice(0, 3).map((item) => <li key={item.id}><Link to={`/hermes/chat/${item.id}`} title={item.title}>
          <span className="home-thumb" aria-hidden="true"><Icon name="spark" size={18}/></span>
          <span className="home-recent-copy"><span className="home-title" dir="auto">{item.title || 'گفتگوی جدید'}</span>
            <span className="home-meta"><span>{item.updated_at ? new Date(item.updated_at).toLocaleDateString('fa-IR', { month: 'long', day: 'numeric' }) : ''}</span></span></span>
        </Link></li>)}</ul>
      </section> : null}
      <div className="hs-home-overview" data-hermes-main><HermesOverview /></div>
    </div>
  </div>;
}
