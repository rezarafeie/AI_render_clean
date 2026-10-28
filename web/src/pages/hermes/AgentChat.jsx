import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import hermesApi from '../../services/hermesApi';
import { Composer } from '../../studio/Composer';
import { Thread } from '../../studio/Thread';
import { array, message } from './hermesUtils';
import { peekCache, useHermesData, writeCache } from './hermesCache';
import { useHermes } from './HermesContext';

const STEPS = [['sync', 'خواندن پروفایل و پست‌ها', 'account'], ['analyze', 'تحلیل پیج و محتوای قبلی', 'creative'], ['propose', 'ساخت پیشنهاد محتوا برای موتورهای ادیتور', 'script']];
const TAB_FOR = { overview: '', content: 'content', analytics: 'analytics', settings: 'settings' };
const CHIPS = ['این صفحه را برایم توضیح بده', 'بهترین زمان انتشار چیست؟', 'یک ایده‌ی ریلز بده', 'برنامه‌ی این هفته را بچین'];

const step = (key, label, tool, status, at) => ({ key, label, status, startedAt: at, endedAt: at, tool, events: [], notes: [] });
const fromStored = (m) => ({ role: m.role === 'user' ? 'user' : 'assistant', text: m.text, at: typeof m.at === 'number' ? m.at : Date.parse(m.at) || Date.now(), activity: m.activity, suggestions: m.suggestions });

/** The agent's conversation drawn with the Studio chat's own components (Thread, activity timeline, Composer).
 *  With `chatId` it is a stored chat (sidebar history); without, a light assistant for the page being viewed. */
export default function AgentChat({ title, chatId }) {
  const navigate = useNavigate();
  const { agent, runAgent } = useHermes();
  const stored = useHermesData(`chat:${chatId}`, () => hermesApi.getChat(chatId), { enabled: Boolean(chatId) });
  const [local, setLocal] = useState(() => (chatId ? [] : peekCache('assistant') || []));
  const [pending, setPending] = useState([]);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const scroll = useRef(null);
  const run = agent?.run;
  const sentFirst = useRef(false);

  const log = useMemo(() => (chatId ? [...array(stored.data?.messages).map(fromStored), ...pending] : local), [chatId, stored.data, pending, local]);
  const items = useMemo(() => {
    const out = [];
    log.forEach((m, i) => {
      if (m.role === 'assistant' && array(m.activity).length) out.push({ kind: 'activity', id: `act-${i}`, live: false, steps: m.activity.map((a, k) => step(`a${i}-${k}`, a.label, a.tool, 'done', m.at)) });
      out.push({ kind: 'message', id: `m-${i}`, role: m.role, content: m.text, attachments: [], createdAt: m.at });
    });
    if (run?.status === 'running') {
      const at = Date.now();
      const current = STEPS.findIndex(([key]) => key === run.step);
      out.push({ kind: 'activity', id: 'run', live: true, steps: STEPS.map(([key, label, tool], k) => step(key, label, tool, k < current ? 'done' : 'active', at)).slice(0, Math.max(current, 0) + 1) });
    }
    const last = log[log.length - 1];
    const choices = last?.role === 'assistant' && array(last.suggestions).length ? last.suggestions : !log.length && !stored.loading ? CHIPS : [];
    if (choices.length && !busy) out.push({ kind: 'question', id: 'choices', question: '', style: false, seq: 0, choices: choices.map((c) => ({ label: c, value: c })) });
    return out;
  }, [log, run?.status, run?.step, busy, stored.loading]);

  useEffect(() => { const node = scroll.current; if (node) node.scrollTop = node.scrollHeight; }, [items.length, busy]);

  const act = useCallback((action) => {
    if (action?.type === 'open_tab' && action.tab in TAB_FOR) navigate(`/hermes${TAB_FOR[action.tab] ? `/${TAB_FOR[action.tab]}` : ''}`);
    if (action?.type === 'run_agent') void runAgent();
  }, [navigate, runAgent]);

  const send = useCallback(async (raw) => {
    const value = (raw ?? text).trim();
    if (!value || busy) return;
    setText(''); setBusy(true); setError('');
    const page = { title, text: (document.querySelector('[data-hermes-main]')?.innerText || '').slice(0, 6000) };   // what the person is looking at
    const mine = { role: 'user', text: value, at: Date.now() };
    try {
      if (chatId) {
        setPending([mine]);
        const out = await hermesApi.sendChatMessage(chatId, value, page);
        await stored.reload();
        window.dispatchEvent(new Event('hermes:chats-updated'));
        act(out.reply?.action);
      } else {
        const history = local.slice(-8).map((m) => ({ role: m.role === 'assistant' ? 'agent' : 'user', text: m.text }));
        setLocal((prev) => [...prev, mine]);
        const out = await hermesApi.chatAgent(value, page, history);
        const done = [...local, mine, { role: 'assistant', text: out.reply || '…', at: Date.now(), activity: out.activity, suggestions: out.suggestions }].slice(-60);
        setLocal(done); writeCache('assistant', done);
        act(out.action);
      }
    } catch (e) { setError(message(e)); } finally { setPending([]); setBusy(false); }
  }, [text, busy, title, chatId, local, stored, act]);

  useEffect(() => {          // a chat started from the home page carries its first message
    if (!chatId || sentFirst.current) return;
    let first = null;
    try { first = sessionStorage.getItem(`hermes:first:${chatId}`); } catch { /* optional */ }
    if (first) { sentFirst.current = true; try { sessionStorage.removeItem(`hermes:first:${chatId}`); } catch { /* optional */ } void send(first); }
  }, [chatId, send]);

  return <div className="chat-col agent-chat">
    <div className="chat-scroll" ref={scroll}>
      <div className="chat-inner">
        {!log.length && !stored.loading ? <p className="agent-hello" dir="auto">درباره‌ی هر چیزی که روی صفحه می‌بینید بپرسید؛ ایجنت محتوای همین صفحه و اطلاعات پیج شما را می‌بیند.</p> : null}
        <Thread items={items} events={[]} conversation={null} projects={[]} thinking={busy ? 'در حال بررسی…' : undefined}
          onOpenPreview={() => {}} onEditAgain={() => {}} onChoice={(choice) => void send(choice)} onRetryMessage={() => {}} compactRender/>
      </div>
    </div>
    <div className="dock">
      <Composer variant="dock" text={text} setText={setText} files={[]} onRemoveFile={() => {}} onFiles={() => {}} processing={busy} onSend={() => void send()}
        error={error} onDismissError={() => setError('')} hasSpeech={false} listening={false} onListen={() => {}} placeholder="از ایجنت بپرسید…" textOnly />
    </div>
  </div>;
}
