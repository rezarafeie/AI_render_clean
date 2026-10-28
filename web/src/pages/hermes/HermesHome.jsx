import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import hermesApi from '../../services/hermesApi';
import { Composer } from '../../studio/Composer';
import { message } from './hermesUtils';
import { useHermes } from './HermesContext';
import HermesOnboarding from './HermesOnboarding';
import HermesOverview from './HermesOverview';

const SUGGESTIONS = ['پیجم را تحلیل کن', 'یک ایده‌ی ریلز بده', 'برنامه‌ی این هفته را بچین', 'بهترین زمان انتشار چیست؟'];

/** The home page is the Studio's: a title, the input, quick suggestions; the overview of the page sits under them. */
export default function HermesHome() {
  const navigate = useNavigate();
  const { connected } = useHermes();
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const textareaRef = useRef(null);
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
      <div className="chip-row home-chips">{SUGGESTIONS.map((item) => <button key={item} className="chip" onClick={() => void start(item)}>{item}</button>)}</div>
      <div className="hs-home-overview" data-hermes-main><HermesOverview /></div>
    </div>
  </div>;
}
