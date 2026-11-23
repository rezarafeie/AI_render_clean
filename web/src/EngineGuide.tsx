import React from "react";
import { useNavigate } from "react-router-dom";
import { api, AgentMode } from "./api";
import { Icon } from "./components/Icon";
import { friendlyError } from "./ui";
import { Composer } from "./studio/Composer";

/* «کدام موتور؟»: a short chat with the engine advisor (Sonnet). It reads the request, shows what it noticed as live steps, asks at most a couple
   of questions with tappable answers, then recommends an engine with a ready prompt; one button starts the real studio chat with that engine. */

type Engine = "lite" | "medium" | "pro" | "claude";
type Advice = Awaited<ReturnType<typeof api.engineAdvice>>;
type Turn = { role: "user"; text: string } | { role: "assistant"; advice: Advice };

const ENGINES: { id: Engine; name: string; tag: string; speed: string; cost: string; good: string[]; not: string; sample: string }[] = [
  { id: "lite", name: "Lite", tag: "سریع و ارزان، برای کارهای روزمره", speed: "سریع", cost: "کم",
    good: ["تدوین ریلز صحبتی از ویدیوی خودت", "ریلز تبلیغاتی از لینک محصول", "موشن‌گرافیک و تایپوگرافی از یک متن", "مستند به سبک ووکس و اینتروی برند", "پیدا کردن کلیپ از ویدیوی بلند و دوبله"],
    not: "کاری که در هیچ‌کدام از این قالب‌ها جا نشود", sample: "این ویدیوی صحبتی رو برای ریلز تدوین کن، با زیرنویس و موسیقی آروم" },
  { id: "medium", name: "Medium", tag: "چندمرحله‌ای، با برنامه‌ای که اول تأیید می‌کنی", speed: "متوسط", cost: "متوسط",
    good: ["اول بسنج، بعد بساز (بلندی صدا، سکوت، اعوجاج)", "بررسی کپشن یا متن قبل از ساخت", "جست‌وجو در کتابخانهٔ افکت‌ها و قالب‌ها", "بررسی لینک یا تایم‌لاین یک پروژهٔ قبلی", "چند کار پشت سر هم در یک درخواست"],
    not: "یک ریلز ساده که Lite سریع‌تر و ارزان‌تر می‌سازد", sample: "اول بلندی صدای این ویدیو رو بسنج، اگه مشکل داشت درستش کن و بعد ریلز بساز" },
  { id: "pro", name: "Pro", tag: "قوی‌ترین؛ کندتر و پرهزینه‌تر (آزمایشی)", speed: "کند", cost: "زیاد",
    good: ["فیلم سفارشی که هیچ قالبی ندارد", "کپی دقیق سبک یک ویدیوی نمونه", "ترکیب چند موتور در یک پروژه", "پروژهٔ بلند یا غیرمعمول", "وقتی Lite از پسش برنیامد"],
    not: "کارهای ساده و تکراری؛ هزینه‌اش چند برابر است", sample: "یه ویدیو دقیقاً با سبک این ریلز نمونه بساز، با عکس‌هایی که می‌فرستم و روایت خودم" },
  { id: "claude", name: "Claude", tag: "خودِ Claude، بدون ابزارهای استودیو (آزمایشی)", speed: "کند", cost: "خیلی زیاد",
    good: ["مقایسهٔ خروجی استودیو با Claude خام", "کار کدنویسی‌محور (مثلاً انیمیشن با کد دلخواه)", "خودش ابزار و پکیج لازم را از اینترنت نصب می‌کند", "رندر ابری را خودش اجرا می‌کند"],
    not: "کارهای معمولی؛ مهارت‌ها، فونت‌ها، کتابخانه و تجربهٔ فارسی استودیو را ندارد و گران است", sample: "می‌خوام ببینم خود Claude بدون ابزارهای استودیو یه موشن‌گرافیک ۲۰ ثانیه‌ای از این متن چطور می‌سازه" },
];
const NAME: Record<Engine, string> = { lite: "Lite", medium: "Medium", pro: "Pro", claude: "Claude" };
const THINKING = ["در حال خواندن درخواست", "بررسی نوع کار و ورودی‌ها", "مقایسهٔ موتورها", "آماده کردن پیشنهاد"];

export default function EngineGuide() {
  const navigate = useNavigate();
  const [text, setText] = React.useState("");
  const [turns, setTurns] = React.useState<Turn[]>([]);
  const [busy, setBusy] = React.useState<"" | "ask" | "start">("");
  const [error, setError] = React.useState("");
  const [thinkStep, setThinkStep] = React.useState(0);
  const end = React.useRef<HTMLDivElement>(null);
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);

  React.useEffect(() => {
    if (busy !== "ask") return;
    setThinkStep(0);
    const timer = window.setInterval(() => setThinkStep(step => Math.min(step + 1, THINKING.length - 1)), 1300);
    return () => window.clearInterval(timer);
  }, [busy]);
  React.useEffect(() => { if (turns.length) end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [turns, busy]);

  const send = async (value = text) => {
    const content = value.trim();
    if (content.length < 2 || busy) return;
    const next: Turn[] = [...turns, { role: "user", text: content }];
    setTurns(next); setText(""); setBusy("ask"); setError("");
    const messages = next.map(t => t.role === "user" ? { role: "user" as const, content: t.text }
      : { role: "assistant" as const, content: [t.advice.reply, t.advice.question?.text, t.advice.recommendation ? `پیشنهاد: ${t.advice.recommendation.engine} — ${t.advice.recommendation.title}` : ""].filter(Boolean).join("\n") || "…" });
    try { const advice = await api.engineAdvice(messages.slice(-16)); setTurns(current => [...current, { role: "assistant", advice }]); }
    catch (e) { setError(friendlyError(e, "get advice")); }
    finally { setBusy(""); }
  };
  const start = async (engine: Engine, title: string, content: string) => {
    if (!content.trim() || busy) return;
    setBusy("start"); setError("");
    try {
      const chat = await api.createStudioConversation(title || content.slice(0, 50));
      await api.updateStudioConversation(chat.id, { agent_mode: engine as AgentMode });
      await api.sendStudioMessage(chat.id, content.trim(), [], { agent_mode: engine as AgentMode });
      navigate(`/studio/${chat.id}`);
    } catch (e) { setError(friendlyError(e, "start the job")); setBusy(""); }
  };
  const reset = () => { setTurns([]); setText(""); setError(""); textareaRef.current?.focus(); };
  const chatting = turns.length > 0;
  const lastAdvice = [...turns].reverse().find((t): t is Extract<Turn, { role: "assistant" }> => t.role === "assistant")?.advice;
  const active = lastAdvice?.recommendation?.engine;

  const composer = <Composer variant={chatting ? "dock" : "home"} text={text} setText={setText} files={[]} onRemoveFile={() => {}} onFiles={() => {}}
    processing={busy === "ask"} onSend={() => void send()} error={error} onDismissError={() => setError("")} hasSpeech={false} listening={false} onListen={() => {}}
    textOnly autoFocus={!chatting} textareaRef={textareaRef}
    placeholder={chatting ? "جواب بده یا جزئیات بیشتری بگو…" : "بگو چه ویدیویی می‌خواهی؛ مثلاً یه ریلز تبلیغاتی ۳۰ ثانیه‌ای برای این محصول: https://…"}/>;

  return <main className="eg-guide" dir="rtl" data-chatting={chatting || undefined}>
    {!chatting ? <header className="eg-hero">
      <span className="eg-kicker"><Icon name="spark" size={14}/>مشاور انتخاب موتور</span>
      <h1>کدام موتور برای کار من مناسب است؟</h1>
      <p>کارت را بنویس. مشاور درخواستت را بررسی می‌کند، اگر لازم بود یکی دو سؤال می‌پرسد و بعد بهترین موتور را با یک پرامپت آماده پیشنهاد می‌دهد؛ با یک دکمه کار در استودیو شروع می‌شود.</p>
    </header> : <div className="eg-chat-head">
      <span><Icon name="spark" size={14}/>مشاور انتخاب موتور</span>
      <button type="button" className="btn btn-sm" onClick={reset} disabled={!!busy}><Icon name="refresh" size={14}/>از اول</button>
    </div>}

    {chatting ? <ol className="thread eg-thread" aria-label="گفتگو با مشاور" aria-live="polite">
      {turns.map((turn, index) => turn.role === "user"
        ? <li key={index} className="msg msg-user"><div className="bubble bidi" dir="auto">{turn.text}</div></li>
        : <li key={index} className="msg msg-assistant"><AdvisorTurn advice={turn.advice} latest={index === turns.length - 1} busy={!!busy}
            onAnswer={answer => void send(answer)} onStart={start}/></li>)}
      {busy === "ask" ? <li className="msg msg-assistant"><div className="assistant">
        <span className="assistant-mark"><Icon name="spark" size={13}/></span>
        <div className="assistant-body"><ul className="act-list eg-steps">{THINKING.slice(0, thinkStep + 1).map((label, i) => <li key={label} className="act-row eg-step-in">
          <span className="act-icon" data-status={i < thinkStep ? "done" : "active"}>{i < thinkStep ? <Icon name="check" size={13}/> : <i className="act-dot"/>}</span>
          <span className={`act-label${i === thinkStep ? " is-active" : ""}`}>{label}…</span></li>)}</ul></div>
      </div></li> : null}
    </ol> : null}
    <div ref={end}/>

    <div className={chatting ? "eg-dock" : "eg-home-composer"}>{composer}</div>

    {!chatting ? <div className="eg-samples" aria-label="نمونهٔ درخواست">
      {ENGINES.map(e => <button key={e.id} type="button" className="eg-sample" onClick={() => void send(e.sample)}>
        <span className="eg-badge" data-engine={e.id}>{e.name}</span><span>{e.sample}</span></button>)}
    </div> : null}

    <section className="eg-cards" aria-label="مقایسهٔ موتورها">
      {ENGINES.map(e => <article key={e.id} className="eg-card" data-engine={e.id} data-active={active === e.id || undefined}>
        <header><h2><span className="eg-badge" data-engine={e.id}>{e.name}</span></h2><p>{e.tag}</p></header>
        <dl><div><dt>سرعت</dt><dd>{e.speed}</dd></div><div><dt>هزینه</dt><dd>{e.cost}</dd></div></dl>
        <h3>مناسب برای</h3>
        <ul>{e.good.map(g => <li key={g}>{g}</li>)}</ul>
        <p className="eg-not"><b>مناسب نیست برای:</b> {e.not}</p>
        <button type="button" className="btn btn-sm" disabled={!!busy} onClick={() => { window.scrollTo({ top: 0, behavior: "smooth" }); void send(e.sample); }}>امتحان با یک نمونه</button>
      </article>)}
    </section>

    <section className="eg-rule">
      <h2>قاعدهٔ سرانگشتی</h2>
      <ol>
        <li><b>همیشه اول Lite</b> — بیشتر کارها (ریلز، تبلیغ، موشن، دوبله) با Lite سریع و ارزان درست می‌شوند.</li>
        <li><b>اگر باید اول چیزی بررسی شود یا چند کار پشت سر هم است</b> — Medium.</li>
        <li><b>اگر کار خاص است یا Lite از پسش برنیامد</b> — Pro (کندتر و گران‌تر).</li>
        <li><b>فقط برای مقایسه با خودِ Claude</b> — Claude (بدون ابزارهای استودیو و پرهزینه).</li>
      </ol>
    </section>
  </main>;
}

function AdvisorTurn({ advice, latest, busy, onAnswer, onStart }: { advice: Advice; latest: boolean; busy: boolean;
  onAnswer: (answer: string) => void; onStart: (engine: Engine, title: string, prompt: string) => void }) {
  const rec = advice.recommendation;
  const [prompt, setPrompt] = React.useState(rec?.prompt || "");
  const [shown, setShown] = React.useState(latest ? 0 : advice.steps.length);
  React.useEffect(() => {
    if (shown >= advice.steps.length) return;
    const timer = window.setTimeout(() => setShown(n => n + 1), 380);
    return () => window.clearTimeout(timer);
  }, [shown, advice.steps.length]);
  const ready = shown >= advice.steps.length;
  const id = React.useId();
  return <div className="assistant">
    <span className="assistant-mark"><Icon name="spark" size={13}/></span>
    <div className="assistant-body eg-turn">
      {advice.steps.length ? <ul className="act-list eg-steps">{advice.steps.slice(0, shown).map((step, i) => <li key={i} className="act-row eg-step-in">
        <span className="act-icon" data-status="done"><Icon name="check" size={13}/></span><span className="act-label">{step}</span></li>)}</ul> : null}
      {ready && advice.reply ? <p className="eg-reply eg-step-in">{advice.reply}</p> : null}
      {ready && advice.question ? <div className="eg-question eg-step-in">
        <p><b>{advice.question.text}</b></p>
        {latest && advice.question.options.length ? <div className="eg-options">{advice.question.options.map(option =>
          <button key={option} type="button" className="eg-option" disabled={busy} onClick={() => onAnswer(option)}>{option}</button>)}</div> : null}
      </div> : null}
      {ready && rec ? <div className="eg-advice eg-step-in" data-engine={rec.engine}>
        <div className="eg-advice-head"><span className="eg-badge" data-engine={rec.engine}>{NAME[rec.engine]}</span><b>{rec.title}</b></div>
        <p>{rec.why}</p>
        <label htmlFor={id}>پرامپتی که فرستاده می‌شود (می‌توانی ویرایشش کنی)</label>
        <textarea id={id} className="input bidi" dir="auto" rows={5} value={prompt} onChange={e => setPrompt(e.target.value)} disabled={busy}/>
        {rec.attach ? <p className="eg-attach"><Icon name="paperclip" size={14}/>{rec.attach} — بعد از شروع، در همان چت پیوستش کن.</p> : null}
        {rec.tips.length ? <ul className="eg-tips">{rec.tips.map((t, i) => <li key={i}>{t}</li>)}</ul> : null}
        <div className="eg-actions">
          <button type="button" className="btn btn-primary" disabled={busy || !prompt.trim()} onClick={() => onStart(rec.engine, rec.title, prompt)}>
            <Icon name="play" size={15}/>{`شروع کار با ${NAME[rec.engine]}`}</button>
          {latest ? <span className="eg-alt">یا با موتور دیگر: {(["lite", "medium", "pro"] as Engine[]).filter(e => e !== rec.engine).map(e =>
            <button key={e} type="button" className="eg-link" disabled={busy || !prompt.trim()} onClick={() => onStart(e, rec.title, prompt)}>{NAME[e]}</button>)}</span> : null}
        </div>
      </div> : null}
    </div>
  </div>;
}
