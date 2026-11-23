import React from "react";
import { useNavigate } from "react-router-dom";
import { api, AgentMode } from "./api";
import { Icon } from "./components/Icon";
import { friendlyError } from "./ui";

type Engine = "lite" | "medium" | "pro";
const ENGINES: { id: Engine; name: string; tag: string; speed: string; cost: string; good: string[]; not: string; sample: string }[] = [
  { id: "lite", name: "Lite", tag: "سریع و ارزان، برای کارهای روزمره", speed: "سریع", cost: "کم",
    good: ["تدوین ریلز صحبتی از ویدیوی خودت", "ریلز تبلیغاتی از لینک محصول", "موشن‌گرافیک و تایپوگرافی از یک متن", "مستند به سبک ووکس و اینتروی برند", "پیدا کردن کلیپ از ویدیوی بلند و دوبله"],
    not: "کاری که در هیچ‌کدام از این قالب‌ها جا نشود", sample: "این ویدیوی صحبتی رو برای ریلز تدوین کن، با زیرنویس و موسیقی آروم" },
  { id: "medium", name: "Medium", tag: "چندمرحله‌ای، با برنامه‌ای که اول تأیید می‌کنی", speed: "متوسط", cost: "متوسط",
    good: ["اول بسنج، بعد بساز (بلندی صدا، سکوت، اعوجاج)", "بررسی کپشن یا متن قبل از ساخت", "جست‌وجو در کتابخانهٔ افکت‌ها و قالب‌ها", "بررسی لینک یا تایم‌لاین یک پروژهٔ قبلی", "چند کار پشت سر هم در یک درخواست"],
    not: "یک ریلز ساده که Lite سریع‌تر و ارزان‌تر می‌سازد", sample: "اول بلندی صدای این ویدیو رو بسنج، بعد اگه مشکل داشت درستش کن و ریلز بساز" },
  { id: "pro", name: "Pro", tag: "قوی‌ترین؛ کندتر و پرهزینه‌تر (آزمایشی)", speed: "کند", cost: "زیاد",
    good: ["فیلم سفارشی که هیچ قالبی ندارد", "کپی دقیق سبک یک ویدیوی نمونه", "ترکیب چند موتور در یک پروژه", "پروژهٔ بلند یا غیرمعمول", "وقتی Lite از پسش برنیامد"],
    not: "کارهای ساده و تکراری؛ هزینه‌اش چند برابر است", sample: "یه ویدیو دقیقاً با سبک این ریلز نمونه بساز، با عکس‌هایی که فرستادم و روایت خودم" },
];

type Advice = Awaited<ReturnType<typeof api.engineAdvice>>;

export default function EngineGuide() {
  const navigate = useNavigate();
  const [text, setText] = React.useState("");
  const [advice, setAdvice] = React.useState<Advice | null>(null);
  const [prompt, setPrompt] = React.useState("");
  const [busy, setBusy] = React.useState<"" | "ask" | "start">("");
  const [error, setError] = React.useState("");
  const ask = async (value = text) => {
    if (value.trim().length < 2 || busy) return;
    setBusy("ask"); setError(""); setAdvice(null);
    try { const result = await api.engineAdvice(value.trim()); setAdvice(result); setPrompt(result.prompt); }
    catch (e) { setError(friendlyError(e, "get advice")); }
    finally { setBusy(""); }
  };
  const start = async (engine: Engine, content: string) => {
    if (!content.trim() || busy) return;
    setBusy("start"); setError("");
    try {
      const chat = await api.createStudioConversation(advice?.title || content.slice(0, 50));
      await api.updateStudioConversation(chat.id, { agent_mode: engine as AgentMode });
      await api.sendStudioMessage(chat.id, content.trim(), [], { agent_mode: engine as AgentMode });
      navigate(`/studio/${chat.id}`);
    } catch (e) { setError(friendlyError(e, "start the job")); setBusy(""); }
  };
  const recommended = ENGINES.find(e => e.id === advice?.engine);
  return <main className="eg-guide" dir="rtl">
    <header className="eg-hero">
      <h1>کدام موتور برای کار من مناسب است؟</h1>
      <p>بنویس چه ویدیویی می‌خواهی (یا لینک نمونه بگذار)؛ مشاور می‌گوید با کدام موتور و با چه پرامپتی شروع کنی، و با یک دکمه کار شروع می‌شود.</p>
    </header>

    <section className="eg-advisor" aria-label="مشاور انتخاب موتور">
      <textarea className="input bidi" dir="auto" rows={4} maxLength={4000} value={text} disabled={!!busy}
        placeholder="مثلاً: یه ریلز تبلیغاتی ۳۰ ثانیه‌ای برای این محصول می‌خوام: https://…  یا: این ویدیوی پادکست یک‌ساعته رو تبدیل به چند ریلز کن"
        onChange={e => setText(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void ask(); }}/>
      <div className="eg-row">
        <div className="eg-samples">{ENGINES.map(e => <button key={e.id} type="button" className="chip" disabled={!!busy} onClick={() => { setText(e.sample); void ask(e.sample); }}>{e.sample.slice(0, 42)}…</button>)}</div>
        <button type="button" className="btn btn-primary" disabled={!!busy || text.trim().length < 2} onClick={() => void ask()}>
          <Icon name="spark" size={15}/>{busy === "ask" ? "در حال بررسی…" : "پیشنهاد بده"}</button>
      </div>
      {error ? <p className="notice" data-tone="error" role="alert">{error}</p> : null}
      {advice && recommended ? <div className="eg-advice" aria-live="polite">
        <div className="eg-advice-head"><span className="eg-badge" data-engine={advice.engine}>{recommended.name}</span><b>{advice.title}</b></div>
        <p>{advice.why}</p>
        <label htmlFor="eg-prompt">پرامپت پیشنهادی (می‌توانی ویرایشش کنی)</label>
        <textarea id="eg-prompt" className="input bidi" dir="auto" rows={5} value={prompt} onChange={e => setPrompt(e.target.value)} disabled={!!busy}/>
        {advice.attach ? <p className="eg-attach"><Icon name="paperclip" size={14}/>{advice.attach}</p> : null}
        {advice.tips.length ? <ul className="eg-tips">{advice.tips.map((t, i) => <li key={i}>{t}</li>)}</ul> : null}
        <div className="eg-actions">
          <button type="button" className="btn btn-primary" disabled={!!busy || !prompt.trim()} onClick={() => void start(advice.engine, prompt)}>
            <Icon name="play" size={15}/>{busy === "start" ? "در حال شروع…" : `شروع کار با ${recommended.name}`}</button>
          {advice.attach ? <small className="eg-muted">اگر فایل لازم است، بعد از شروع در همان چت پیوستش کن.</small> : null}
        </div>
      </div> : null}
    </section>

    <section className="eg-cards" aria-label="مقایسهٔ موتورها">
      {ENGINES.map(e => <article key={e.id} className="eg-card" data-engine={e.id} data-active={advice?.engine === e.id || undefined}>
        <header><h2>{e.name}</h2><p>{e.tag}</p></header>
        <dl><div><dt>سرعت</dt><dd>{e.speed}</dd></div><div><dt>هزینه</dt><dd>{e.cost}</dd></div></dl>
        <h3>مناسب برای</h3>
        <ul>{e.good.map(g => <li key={g}>{g}</li>)}</ul>
        <p className="eg-not"><b>مناسب نیست برای:</b> {e.not}</p>
        <button type="button" className="btn btn-sm" disabled={!!busy} onClick={() => { setText(e.sample); setAdvice(null); window.scrollTo({ top: 0, behavior: "smooth" }); }}>نمونهٔ درخواست</button>
      </article>)}
    </section>

    <section className="eg-rule">
      <h2>قاعدهٔ سرانگشتی</h2>
      <ol>
        <li><b>همیشه اول Lite</b> — بیشتر کارها (ریلز، تبلیغ، موشن، دوبله) با Lite سریع و ارزان درست می‌شوند.</li>
        <li><b>اگر باید اول چیزی بررسی شود یا چند کار پشت سر هم است</b> — Medium.</li>
        <li><b>اگر کار خاص است یا Lite از پسش برنیامد</b> — Pro (کندتر و گران‌تر).</li>
      </ol>
    </section>
  </main>;
}
