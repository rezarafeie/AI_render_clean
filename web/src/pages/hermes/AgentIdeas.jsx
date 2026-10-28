import { useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import hermesApi from '../../services/hermesApi';
import { api } from '../../api';
import { Icon } from '../../components/Icon';
import { array, message } from './hermesUtils';
import { useHermes } from './HermesContext';

const ENGINE = { talking: 'صحبتی', explainer: 'اکسپلینر' };
const STATUS = { proposed: 'پیشنهاد', in_production: 'در حال ساخت', produced: 'ساخته شد', queued: 'در صف انتشار', rejected: 'رد شد' };
const caption = (item) => (item.caption ? `\n\nکپشن برای انتشار:\n${item.caption}\n${array(item.hashtags).join(' ')}` : '');

/** What the editor receives for an idea it produces from scratch: the whole creative direction, not a one-line topic. */
function producedBrief(item) {
  const scenes = array(item.scenes).map((s, i) => `${i + 1}. (${s.seconds || '?'}s) تصویر: ${s.visual || ''} | متن روی صفحه: ${s.on_screen_text || ''} | روایت: ${s.narration || ''}`).join('\n');
  return `[موتور: اکسپلینر]\nیک ریلز اینستاگرام (عمودی، فارسی، با روایت صوتی) بساز. این ایده را ایجنت اینستاگرام از تحلیل پیج کاربر ساخته و کاربر تأیید کرده است.\n\n`
    + [item.concept && `ایده: ${item.concept}`, item.hook && `هوک (دو ثانیه‌ی اول): ${item.hook}`, item.style && `سبک بصری: ${item.style}`, item.mood && `حس و حال: ${item.mood}`,
      item.music && `موسیقی: ${item.music}`, scenes && `سکانس‌ها:\n${scenes}`, item.script && `متن کامل روایت:\n${item.script}`, item.cta && `دعوت به اقدام: ${item.cta}`, !item.concept && item.editor_brief].filter(Boolean).join('\n\n')
    + caption(item);
}

function TalkingCard({ item, busy, onSend, onReject }) {
  const file = useRef(null);
  const [video, setVideo] = useState(null);
  const open = item.status === 'proposed';
  return <article className="idea idea-talking" dir="rtl">
    <div className="idea-top"><span className="idea-tag" data-engine="talking">صحبتی</span><span className="idea-need">نیاز به ضبط ویدیو توسط شما</span>{!open ? <span className="idea-status">{STATUS[item.status] || item.status}</span> : null}</div>
    <h3 className="idea-title" dir="auto">{item.title}</h3>
    {item.why ? <p className="idea-why" dir="auto">{item.why}</p> : null}
    {item.script ? <div className="idea-script"><span className="idea-label">متن گفتاری</span><pre dir="auto">{item.script}</pre></div> : null}
    {array(item.on_screen).length ? <div className="idea-chips">{array(item.on_screen).map((t) => <span key={t} className="idea-chip">{t}</span>)}</div> : null}
    {array(item.shooting_tips).length ? <ul className="idea-tips">{array(item.shooting_tips).map((t) => <li key={t} dir="auto">{t}</li>)}</ul> : null}
    {item.caption ? <details className="idea-more"><summary>کپشن و هشتگ‌ها</summary><pre className="agent-pre" dir="auto">{item.caption}{'\n'}{array(item.hashtags).join(' ')}</pre></details> : null}
    {open ? <div className="idea-upload">
      <input ref={file} type="file" accept="video/*" hidden onChange={(e) => { setVideo(e.target.files?.[0] || null); e.target.value = ''; }}/>
      {video ? <div className="idea-file"><Icon name="video" size={18}/><span dir="auto">{video.name}</span><button type="button" className="icon-btn" onClick={() => setVideo(null)} aria-label="Remove video"><Icon name="close" size={16}/></button></div>
        : <button type="button" className="idea-drop" onClick={() => file.current?.click()} disabled={busy}><Icon name="paperclip" size={18}/>ویدیوی ضبط‌شده را اینجا بگذارید</button>}
      <div className="idea-actions">
        <button className="btn btn-sm" type="button" disabled={!video || busy} onClick={() => onSend(item, video)}>{busy ? 'در حال ارسال…' : 'Send to editor'}</button>
        <button className="btn btn-ghost btn-sm" type="button" disabled={busy} onClick={() => onReject(item)}>Skip</button>
      </div></div> : null}
    {item.conversation_id ? <div className="idea-actions"><Link className="btn btn-secondary btn-sm" to={`/studio/${item.conversation_id}`}>Open in editor</Link></div> : null}
  </article>;
}

function ProducedCard({ item, busy, onBuild, onReject }) {
  const open = item.status === 'proposed';
  const scenes = array(item.scenes);
  return <article className="idea" dir="rtl">
    <div className="idea-top"><span className="idea-tag" data-engine="explainer">اکسپلینر</span><span className="idea-need is-ok">ادیتور می‌سازد</span>{!open ? <span className="idea-status">{STATUS[item.status] || item.status}</span> : null}</div>
    <h3 className="idea-title" dir="auto">{item.title}</h3>
    {item.concept ? <p className="idea-hook" dir="auto">{item.concept}</p> : null}
    {item.hook ? <p className="idea-why" dir="auto">هوک: «{item.hook}»</p> : null}
    {item.style || item.mood || item.music ? <div className="idea-chips">{[item.style, item.mood, item.music].filter(Boolean).map((t) => <span key={t} className="idea-chip" dir="auto">{t}</span>)}</div> : null}
    {scenes.length ? <ol className="idea-scenes">{scenes.map((s, i) => <li key={i} dir="auto"><b>{s.on_screen_text || `سکانس ${i + 1}`}</b><span>{s.visual}</span></li>)}</ol> : null}
    {item.script ? <details className="idea-more"><summary>متن کامل روایت</summary><pre className="agent-pre" dir="auto">{item.script}</pre></details> : null}
    {item.caption ? <details className="idea-more"><summary>کپشن و هشتگ‌ها</summary><pre className="agent-pre" dir="auto">{item.caption}{'\n'}{array(item.hashtags).join(' ')}</pre></details> : null}
    <div className="idea-actions">
      {open ? <><button className="btn btn-sm" type="button" disabled={busy} onClick={() => onBuild(item)}>{busy ? 'Building…' : 'Build in editor'}</button>
        <button className="btn btn-ghost btn-sm" type="button" disabled={busy} onClick={() => onReject(item)}>Skip</button></> : null}
      {item.conversation_id ? <Link className="btn btn-secondary btn-sm" to={`/studio/${item.conversation_id}`}>Open in editor</Link> : null}
    </div>
  </article>;
}

/** Ideas the agent proposes: talking reels (the full script and a place to upload the filmed video) and ideas the editor produces from scratch. */
export default function AgentIdeas({ limit = 0, embedded = false }) {
  const navigate = useNavigate();
  const { agent, reloadAgent, runAgent } = useHermes();
  const [working, setWorking] = useState('');
  const [error, setError] = useState('');
  const all = array(agent?.proposals).filter((p) => p.status !== 'rejected').slice().reverse();
  const list = limit ? all.slice(0, limit) : all;

  async function handOver(item, text, files = []) {
    setWorking(item.id); setError('');
    try {
      const conversation = await api.createStudioConversation(item.title || 'ریلز اینستاگرام');
      const ids = [];
      for (const file of files) ids.push((await api.uploadStudioAttachment(conversation.id, file)).id);
      await api.sendStudioMessage(conversation.id, text, ids, {});
      await hermesApi.setProposalStatus(item.id, 'in_production', conversation.id);
      navigate(`/studio/${conversation.id}`);
    } catch (e) { setError(message(e)); setWorking(''); }
  }
  const build = (item) => handOver(item, producedBrief(item));
  const sendTalking = (item, video) => handOver(item, `[موتور: صحبتی]\nاین ویدیو را که خودم برای ریلز اینستاگرام ضبط کرده‌ام تدوین کن (زیرنویس، موشن و ریتم). این ایده را ایجنت اینستاگرام ساخته و من تأیید کرده‌ام.\n\nهوک: ${item.hook || ''}\n\nمتن گفتاری:\n${item.script || ''}${caption(item)}`, [video]);
  async function reject(item) { await hermesApi.setProposalStatus(item.id, 'rejected').catch((e) => setError(message(e))); void reloadAgent(); }

  return <div className={embedded ? 'agent-embedded' : 'agent-tab'}>
    {error ? <div className="notice" data-tone="error" role="alert">{error}</div> : null}
    {!list.length ? <div className="ws-empty"><span className="empty-icon"><Icon name="spark" size={24}/></span><h2>هنوز ایده‌ای نیست</h2><p>ایجنت بعد از تحلیل پیج، ایده و سناریو پیشنهاد می‌دهد.</p>
      <button className="btn btn-secondary btn-sm" type="button" onClick={() => runAgent()}>بررسی جدید</button></div> : null}
    <div className="ideas">
      {list.map((p) => p.engine === 'talking'
        ? <TalkingCard key={p.id} item={p} busy={working === p.id} onSend={sendTalking} onReject={reject}/>
        : <ProducedCard key={p.id} item={p} busy={working === p.id} onBuild={build} onReject={reject}/>)}
    </div>
  </div>;
}
