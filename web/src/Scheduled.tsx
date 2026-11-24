import React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { authFetch, BASE } from "./api";
import { Icon } from "./components/Icon";
import { short } from "./CreditsPage";
import "./styles/scheduled.css";

/* Scheduled tasks: a standing instruction that runs on its own (app/scheduled_tasks.py). Every run opens new chats; the task keeps the run history. */

type Engine = "lite" | "medium" | "pro";
type Kind = "hourly" | "daily" | "weekdays" | "weekly" | "once";
export type Schedule = { kind: Kind; time: string; every_hours: number; weekday: number; date: string };
export type TaskDraft = { name: string; instructions: string; engine: Engine; per_run: number; research: boolean; schedule: Schedule; status?: "active" | "paused" };
type Summary = TaskDraft & { id: string; status: "active" | "paused"; created_at: string; next_run_at: string | null; last_run_at: string | null;
  last_run: { at: string; status: string } | null; runs_count: number };
type RunItem = { title: string; prompt: string; conversation_id: string; status: string; error: string; credits: number };
type Run = { id: string; at: string; trigger: string; status: string; items: RunItem[]; error: string; credits: number };
type Detail = Summary & { runs: Run[]; running_now: boolean };

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await authFetch(`${BASE}/scheduled${path}`, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) { const d = (data as any)?.detail; throw new Error(typeof d === "string" ? d : d?.message || "درخواست انجام نشد"); }
  return data as T;
}

const ENGINE: Record<Engine, string> = { lite: "Lite", medium: "Medium", pro: "Pro" };
const DAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"];
const fa = (s: string | number) => String(s).replace(/\d/g, d => "۰۱۲۳۴۵۶۷۸۹"[+d]);
export function describe(s: Schedule): string {
  const at = `ساعت ${fa(s.time)}`;
  switch (s.kind) {
    case "hourly": return s.every_hours === 1 ? `هر ساعت، دقیقهٔ ${fa(s.time.slice(3))}` : `هر ${fa(s.every_hours)} ساعت، دقیقهٔ ${fa(s.time.slice(3))}`;
    case "daily": return `هر روز ${at}`;
    case "weekdays": return `روزهای کاری (شنبه تا چهارشنبه) ${at}`;
    case "weekly": return `هر ${DAYS[s.weekday] || "هفته"} ${at}`;
    case "once": return `یک‌بار، ${s.date ? fa(s.date) + " " : ""}${at}`;
  }
}
const when = (iso: string | null | undefined) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("fa-IR", { timeZone: "Asia/Tehran", weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
};
const STATUS: Record<string, string> = { preparing: "در حال آماده‌سازی", starting: "در حال شروع", running: "در حال ساخت", done: "تمام شد", partial: "بخشی تمام شد",
  failed: "ناموفق", needs_you: "منتظر شما" };
const TRIGGER: Record<string, string> = { schedule: "زمان‌بندی", manual: "اجرای دستی" };

const blank = (): TaskDraft => ({ name: "", instructions: "", engine: "lite", per_run: 1, research: false, schedule: { kind: "daily", time: "09:00", every_hours: 1, weekday: 0, date: "" } });

const TEMPLATES: { icon: "motion" | "film" | "spark" | "captions" | "globe" | "video"; title: string; text: string; draft: TaskDraft }[] = [
  { icon: "motion", title: "۵ موشن‌گرافیک روزانه", text: "هر روز پنج موشن‌گرافیک با موضوع‌های تازه در حوزه‌ای که تعیین می‌کنید؛ خودش جست‌وجو و انتخاب می‌کند.",
    draft: { name: "۵ موشن‌گرافیک روزانه", engine: "lite", per_run: 5, research: true, schedule: { kind: "daily", time: "08:00", every_hours: 1, weekday: 0, date: "" },
      instructions: "هر بار یک موشن‌گرافیک عمودی ۹:۱۶ حدود ۴۰ ثانیه با نریشن فارسی بساز درباره‌ی یک نکته یا خبر تازه در حوزه‌ی [حوزه‌ی موردنظر را بنویسید]. یک هوک قوی در ثانیه‌ی اول، یک ایده در هر صحنه و در پایان دعوت به دنبال‌کردن پیج." } },
  { icon: "film", title: "خبر روز به سبک ووکس", text: "هر عصر مهم‌ترین خبر روز در حوزه‌ی شما، به شکل یک مستند کوتاه ووکس با منابع واقعی.",
    draft: { name: "خبر روز به سبک ووکس", engine: "lite", per_run: 1, research: true, schedule: { kind: "daily", time: "18:00", every_hours: 1, weekday: 0, date: "" },
      instructions: "مهم‌ترین خبر امروز در حوزه‌ی [حوزه را بنویسید] را پیدا کن و یک اکسپلینر ووکس عمودی ۶۰ ثانیه‌ای فارسی درباره‌اش بساز: چه اتفاقی افتاد، چرا مهم است و چه اثری دارد. فقط از فکت‌های منبع استفاده کن." } },
  { icon: "spark", title: "فکت روزانه", text: "دو فکت جذاب و کوتاه هر روز، با تایپوگرافی متحرک و نریشن.",
    draft: { name: "فکت روزانه", engine: "lite", per_run: 2, research: false, schedule: { kind: "daily", time: "07:30", every_hours: 1, weekday: 0, date: "" },
      instructions: "یک موشن‌گرافیک تایپوگرافی عمودی ۲۵ ثانیه‌ای با نریشن فارسی بساز درباره‌ی یک فکت شگفت‌انگیز و درست درباره‌ی [موضوع]. لحن صمیمی، پایان با یک سؤال برای کامنت." } },
  { icon: "video", title: "تبلیغ هفتگی محصول", text: "هر هفته یک ویدیوی تبلیغاتی تازه از صفحه‌ی محصول شما، با زاویه‌ای متفاوت.",
    draft: { name: "تبلیغ هفتگی محصول", engine: "lite", per_run: 1, research: false, schedule: { kind: "weekly", time: "10:00", every_hours: 1, weekday: 0, date: "" },
      instructions: "از صفحه‌ی محصول [لینک محصول] یک ویدیوی تبلیغاتی عمودی ۳۰ ثانیه‌ای بساز. هر هفته روی یک مزیت یا مخاطب متفاوت تمرکز کن. پیشنهاد: [تخفیف یا پیشنهاد]. دعوت به اقدام: [مثلاً لینک در بیو]." } },
  { icon: "captions", title: "نکته‌ی آموزشی روزهای کاری", text: "شنبه تا چهارشنبه، صبح زود یک نکته‌ی آموزشی کوتاه برای مخاطبان شما.",
    draft: { name: "نکته‌ی آموزشی روزهای کاری", engine: "lite", per_run: 1, research: false, schedule: { kind: "weekdays", time: "07:00", every_hours: 1, weekday: 0, date: "" },
      instructions: "یک موشن‌گرافیک توضیحی عمودی ۳۵ ثانیه‌ای با نریشن فارسی بساز که یک نکته‌ی کاربردی درباره‌ی [موضوع آموزشی] را ساده توضیح بدهد، با یک مثال واقعی." } },
  { icon: "globe", title: "مرور هفتگی ترندها", text: "پنجشنبه‌ها یک جمع‌بندی ویدیویی از مهم‌ترین اتفاق‌ها و ترندهای هفته در حوزه‌ی شما.",
    draft: { name: "مرور هفتگی ترندها", engine: "medium", per_run: 1, research: true, schedule: { kind: "weekly", time: "17:00", every_hours: 1, weekday: 5, date: "" },
      instructions: "سه اتفاق یا ترند مهم این هفته در حوزه‌ی [حوزه] را پیدا کن و یک اکسپلینر ووکس عمودی ۷۵ ثانیه‌ای فارسی بساز که هر کدام را کوتاه و دقیق توضیح بدهد، با منابع واقعی." } },
];

/* ── form ─────────────────────────────────────────────────────────────────── */

function TaskForm({ initial, title, onClose, onSaved, onAssist }: { initial: TaskDraft; title: string; onClose: () => void; onSaved: (id: string) => void;
  onAssist?: () => void; }) {
  const [d, setD] = React.useState<TaskDraft>(initial);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const editing = (initial as any).id as string | undefined;
  const set = (patch: Partial<TaskDraft>) => setD(v => ({ ...v, ...patch }));
  const setS = (patch: Partial<Schedule>) => setD(v => ({ ...v, schedule: { ...v.schedule, ...patch } }));
  async function save() {
    setBusy(true); setError("");
    try {
      const body = JSON.stringify({ name: d.name.trim(), instructions: d.instructions.trim(), engine: d.engine, per_run: d.per_run, research: d.research, schedule: d.schedule,
        ...(editing ? {} : { status: "active" }) });
      const out = editing ? await call<Summary>(`/tasks/${editing}`, { method: "PATCH", body }) : await call<Summary>("/tasks", { method: "POST", body });
      onSaved(out.id);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const ok = d.name.trim().length > 0 && d.instructions.trim().length >= 3 && (d.schedule.kind !== "once" || !!d.schedule.date);
  return <div className="st-modal-back" onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
    <div className="st-modal" role="dialog" aria-modal="true" aria-label={title}>
      <header><h2>{title}</h2><button className="st-x" aria-label="بستن" onClick={onClose}><Icon name="close" size={16}/></button></header>
      {onAssist ? <button className="st-link" onClick={onAssist}>به‌جایش با هوش مصنوعی بسازید</button> : null}
      <label className="st-field"><span>نام</span><input value={d.name} onChange={e => set({ name: e.target.value })} placeholder="مثلاً: ۵ موشن‌گرافیک روزانه" maxLength={120} autoFocus/></label>
      <div className="st-field"><span>دستور کار</span>
        <div className="st-instr">
          <textarea value={d.instructions} onChange={e => set({ instructions: e.target.value })} rows={6} maxLength={6000}
            placeholder="هر بار چه چیزی ساخته شود؟ نوع ویدیو، موضوع، لحن، طول، قالب و دعوت به اقدام را بنویسید."/>
          <div className="st-instr-bar">
            <label className="st-pick"><Icon name="spark" size={14}/><select value={d.engine} onChange={e => set({ engine: e.target.value as Engine })} aria-label="موتور">
              <option value="lite">Lite · سریع و ارزان</option><option value="medium">Medium · چندمرحله‌ای</option><option value="pro">Pro · قوی‌ترین</option></select></label>
            <label className="st-pick"><Icon name="copy" size={14}/><select value={d.per_run} onChange={e => set({ per_run: +e.target.value })} aria-label="تعداد در هر اجرا">
              {[1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{fa(n)} ویدیو در هر اجرا</option>)}</select></label>
            <label className="st-check"><input type="checkbox" checked={d.research} onChange={e => set({ research: e.target.checked })}/>جست‌وجوی تازه در وب</label>
          </div>
        </div>
      </div>
      <div className="st-note"><Icon name="alert" size={15}/><span>هر اجرا بدون پرسیدن از شما کار را کامل می‌سازد و از اعتبارتان کم می‌کند. هر ویدیو در یک چت تازه ساخته می‌شود و اگر تلگرام وصل باشد، خروجی آن‌جا هم فرستاده می‌شود.</span></div>
      <div className="st-trigger"><span className="st-label">زمان اجرا</span>
        <div className="st-trigger-row">
          <label className="st-pick"><Icon name="clock" size={14}/><select value={d.schedule.kind} onChange={e => setS({ kind: e.target.value as Kind })} aria-label="تکرار">
            <option value="daily">هر روز</option><option value="weekdays">روزهای کاری</option><option value="weekly">هفتگی</option><option value="hourly">هر چند ساعت</option><option value="once">یک‌بار</option></select></label>
          {d.schedule.kind === "weekly" ? <select className="st-sel" value={d.schedule.weekday} onChange={e => setS({ weekday: +e.target.value })} aria-label="روز هفته">
            {DAYS.map((n, i) => <option key={i} value={i}>{n}</option>)}</select> : null}
          {d.schedule.kind === "hourly" ? <select className="st-sel" value={d.schedule.every_hours} onChange={e => setS({ every_hours: +e.target.value })} aria-label="هر چند ساعت">
            {[1, 2, 3, 4, 6, 8, 12].map(n => <option key={n} value={n}>هر {fa(n)} ساعت</option>)}</select> : null}
          {d.schedule.kind === "once" ? <input className="st-sel" type="date" value={d.schedule.date} onChange={e => setS({ date: e.target.value })} aria-label="تاریخ"/> : null}
          <input className="st-sel st-time" type="time" value={d.schedule.time} onChange={e => setS({ time: e.target.value || "09:00" })} aria-label="ساعت"/>
        </div>
        <small>{describe(d.schedule)} · به وقت ایران</small>
      </div>
      {error ? <div className="st-error" role="alert">{error}</div> : null}
      <footer><button className="st-btn ghost" onClick={onClose}>انصراف</button><button className="st-btn" disabled={!ok || busy} onClick={() => void save()}>{busy ? "در حال ذخیره…" : editing ? "ذخیره" : "ساخت"}</button></footer>
    </div>
  </div>;
}

/* ── create with AI: a new Studio chat with the setup assistant (app/scheduled_tasks.py start_setup) ── */

function useStartSetup() {
  const navigate = useNavigate();
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const start = async () => {
    if (busy) return;
    setBusy(true); setError("");
    try { const out = await call<{ id: string }>("/setup", { method: "POST" }); window.dispatchEvent(new Event("editorgpt:conversations-updated")); navigate(`/studio/${out.id}`); }
    catch (e) { setError((e as Error).message); setBusy(false); }
  };
  return { start, busy, error };
}

/* ── list ─────────────────────────────────────────────────────────────────── */

function NewMenu({ onAssist, onManual }: { onAssist: () => void; onManual: () => void }) {
  const [open, setOpen] = React.useState(false);
  React.useEffect(() => { if (!open) return; const close = () => setOpen(false); window.addEventListener("click", close); return () => window.removeEventListener("click", close); }, [open]);
  return <div className="st-new" onClick={e => e.stopPropagation()}>
    <button className="st-btn" aria-expanded={open} onClick={() => setOpen(!open)}>کار جدید <Icon name="chevronDown" size={14}/></button>
    {open ? <div className="st-menu" role="menu">
      <button role="menuitem" onClick={() => { setOpen(false); onAssist(); }}><Icon name="thinking" size={16}/>ساخت با هوش مصنوعی</button>
      <button role="menuitem" onClick={() => { setOpen(false); onManual(); }}><Icon name="settings" size={16}/>تنظیم دستی</button>
    </div> : null}
  </div>;
}

export default function ScheduledPage() {
  const [tab, setTab] = React.useState<"mine" | "templates">("mine");
  const [tasks, setTasks] = React.useState<Summary[] | null>(null);
  const [error, setError] = React.useState("");
  const [form, setForm] = React.useState<TaskDraft | null>(null);
  const setup = useStartSetup();
  const [query, setQuery] = React.useState("");
  const navigate = useNavigate();
  const load = React.useCallback(() => { void call<{ tasks: Summary[] }>("/tasks").then(r => setTasks(r.tasks)).catch(e => setError((e as Error).message)); }, []);
  React.useEffect(load, [load]);
  const opened = (id: string) => { setForm(null); navigate(`/scheduled/${id}`); };
  const shown = (tasks || []).filter(t => !query.trim() || (t.name + " " + t.instructions).includes(query.trim()));
  const templates = <div className="st-templates">{TEMPLATES.map(t => <button key={t.title} className="st-tpl" onClick={() => setForm({ ...t.draft })}>
    <span className="st-tpl-ic"><Icon name={t.icon} size={18}/></span>
    <span className="st-tpl-body"><b>{t.title}</b><span>{t.text}</span><small><Icon name="clock" size={13}/>{describe(t.draft.schedule)}</small></span>
  </button>)}</div>;
  return <main className="st-page">
    <h1>کارهای زمان‌بندی‌شده</h1>
    <div className="st-bar">
      <nav className="st-tabs"><button aria-pressed={tab === "mine"} onClick={() => setTab("mine")}>کارهای من</button><button aria-pressed={tab === "templates"} onClick={() => setTab("templates")}>قالب‌ها</button></nav>
      <div className="st-tools">
        {tab === "mine" && (tasks?.length || 0) > 3 ? <label className="st-search"><Icon name="search" size={15}/><input value={query} onChange={e => setQuery(e.target.value)} placeholder="جست‌وجو"/></label> : null}
        <NewMenu onAssist={() => void setup.start()} onManual={() => setForm(blank())}/>
      </div>
    </div>
    {error || setup.error ? <div className="st-error" role="alert">{error || setup.error}</div> : null}
    {tab === "templates" ? templates : tasks === null ? <div className="st-empty-sm">در حال بارگذاری…</div> : !tasks.length ? <>
      <div className="st-empty">
        <svg viewBox="0 0 120 130" width="104" height="112" aria-hidden="true"><rect x="45" y="6" width="30" height="10" rx="3" fill="none" stroke="currentColor" strokeWidth="4"/><path d="M60 16v10" stroke="currentColor" strokeWidth="4"/><circle cx="60" cy="76" r="46" fill="var(--st-dial)" stroke="currentColor" strokeWidth="4"/><path d="M60 46v32l20 12" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round"/></svg>
        <p>هنوز کار زمان‌بندی‌شده‌ای ندارید.</p>
        <div className="st-empty-actions"><button className="st-btn" disabled={setup.busy} onClick={() => void setup.start()}><Icon name="thinking" size={15}/>{setup.busy ? "در حال باز کردن چت…" : "ساخت با هوش مصنوعی"}</button><button className="st-btn ghost" onClick={() => setForm(blank())}>تنظیم دستی</button></div>
      </div>
      <div className="st-wave" aria-hidden="true"/>
      <h2 className="st-sub">یا از یک قالب شروع کنید</h2>
      {templates}
    </> : <div className="st-grid">{shown.map(t => <Link key={t.id} to={`/scheduled/${t.id}`} className="st-card" data-paused={t.status === "paused" || undefined}>
      <b className="st-card-name">{t.name}</b>
      <p>{t.instructions}</p>
      <div className="st-card-meta"><span className="st-dot" data-on={t.status === "active" || undefined}/>{t.status === "active" ? "فعال" : "متوقف"}<i>·</i>{describe(t.schedule)}
        <span className="st-card-engine">{ENGINE[t.engine]}{t.per_run > 1 ? ` × ${fa(t.per_run)}` : ""}</span></div>
      {t.status === "active" && t.next_run_at ? <small className="st-card-next">اجرای بعدی: {when(t.next_run_at)}</small> : t.last_run ? <small className="st-card-next">آخرین اجرا: {when(t.last_run.at)} · {STATUS[t.last_run.status] || t.last_run.status}</small> : null}
    </Link>)}</div>}
    {form ? <TaskForm initial={form} title="کار زمان‌بندی‌شده‌ی جدید" onClose={() => setForm(null)} onSaved={opened} onAssist={() => { setForm(null); void setup.start(); }}/> : null}
  </main>;
}

/* ── detail ───────────────────────────────────────────────────────────────── */

export function ScheduledDetail() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [task, setTask] = React.useState<Detail | null>(null);
  const [error, setError] = React.useState("");
  const [editing, setEditing] = React.useState(false);
  const [busy, setBusy] = React.useState("");
  const [confirmDelete, setConfirmDelete] = React.useState(false);
  const [open, setOpen] = React.useState<string | null>(null);
  const load = React.useCallback(() => { void call<Detail>(`/tasks/${id}`).then(setTask).catch(e => setError((e as Error).message)); }, [id]);
  React.useEffect(load, [load]);
  const live = !!task && (task.running_now || task.runs.some(r => ["preparing", "running", "starting"].includes(r.status)));
  React.useEffect(() => { if (!live) return; const t = window.setInterval(load, 8000); return () => window.clearInterval(t); }, [live, load]);
  React.useEffect(() => { if (task && open === null && task.runs[0]) setOpen(task.runs[0].id); }, [task, open]);
  async function act(kind: "toggle" | "run" | "delete") {
    if (!task) return;
    setBusy(kind); setError("");
    try {
      if (kind === "toggle") await call(`/tasks/${id}`, { method: "PATCH", body: JSON.stringify({ status: task.status === "active" ? "paused" : "active" }) });
      if (kind === "run") { await call(`/tasks/${id}/run`, { method: "POST" }); window.setTimeout(load, 1500); }
      if (kind === "delete") { await call(`/tasks/${id}`, { method: "DELETE" }); navigate("/scheduled"); return; }
      load();
    } catch (e) { setError((e as Error).message); } finally { setBusy(""); }
  }
  if (!task) return <main className="st-page">{error ? <div className="st-error">{error}</div> : <div className="st-empty-sm">در حال بارگذاری…</div>}</main>;
  const total = task.runs.reduce((s, r) => s + (r.credits || 0), 0);
  return <main className="st-page st-detail">
    <Link to="/scheduled" className="st-back"><Icon name="chevron" size={14}/>کارهای زمان‌بندی‌شده</Link>
    <div className="st-detail-head">
      <div><h1>{task.name}</h1>
        <div className="st-card-meta"><span className="st-dot" data-on={task.status === "active" || undefined}/>{task.status === "active" ? "فعال" : "متوقف"}<i>·</i>{describe(task.schedule)}<i>·</i>{ENGINE[task.engine]}{task.per_run > 1 ? ` × ${fa(task.per_run)}` : ""}{task.research ? <><i>·</i>جست‌وجوی وب</> : null}</div>
      </div>
      <div className="st-actions">
        <button className="st-btn" disabled={!!busy || task.running_now} onClick={() => void act("run")}><Icon name="play" size={14}/>{task.running_now || busy === "run" ? "در حال شروع…" : "اجرای همین حالا"}</button>
        <button className="st-btn ghost" disabled={!!busy} onClick={() => void act("toggle")}><Icon name={task.status === "active" ? "pause" : "play"} size={14}/>{task.status === "active" ? "توقف" : "فعال‌سازی"}</button>
        <button className="st-btn ghost" onClick={() => setEditing(true)}><Icon name="edit" size={14}/>ویرایش</button>
        <button className="st-btn ghost danger" onClick={() => setConfirmDelete(true)} aria-label="حذف"><Icon name="trash" size={14}/></button>
      </div>
    </div>
    {error ? <div className="st-error" role="alert">{error}</div> : null}
    {confirmDelete ? <div className="st-confirm"><span>این کار و تاریخچه‌اش حذف شود؟ چت‌ها و ویدیوهایی که ساخته پاک نمی‌شوند.</span>
      <button className="st-btn danger" disabled={!!busy} onClick={() => void act("delete")}>حذف</button><button className="st-btn ghost" onClick={() => setConfirmDelete(false)}>انصراف</button></div> : null}
    <div className="st-info">
      <section><h3>دستور کار</h3><p className="st-instr-text">{task.instructions}</p></section>
      <aside>
        <div><span>اجرای بعدی</span><b>{task.status === "active" ? when(task.next_run_at) : "متوقف است"}</b></div>
        <div><span>آخرین اجرا</span><b>{when(task.last_run_at)}</b></div>
        <div><span>تعداد اجراها</span><b>{fa(task.runs_count)}</b></div>
        <div><span>مصرف اجراهای اخیر</span><b>{total ? short(total) + " اعتبار" : "—"}</b></div>
      </aside>
    </div>
    <h2 className="st-sub">تاریخچه‌ی اجراها</h2>
    {!task.runs.length ? <div className="st-empty-sm">هنوز اجرا نشده است. {task.status === "active" ? `اولین اجرا: ${when(task.next_run_at)}` : ""}</div> :
      <div className="st-runs">{task.runs.map(r => <div className="st-run" key={r.id} data-open={open === r.id || undefined}>
        <button className="st-run-head" onClick={() => setOpen(open === r.id ? null : r.id)}>
          <span className="st-badge" data-s={r.status}>{STATUS[r.status] || r.status}</span>
          <b>{when(r.at)}</b><small>{TRIGGER[r.trigger] || r.trigger} · {fa(r.items.length)} چت{r.credits ? ` · ${short(r.credits)} اعتبار` : ""}</small>
          <Icon name="chevronDown" size={14}/>
        </button>
        {open === r.id ? <div className="st-run-body">
          {r.error ? <div className="st-error">{r.error}</div> : null}
          {r.status === "preparing" && !r.items.length ? <div className="st-empty-sm">در حال انتخاب موضوع‌ها و آماده‌کردن درخواست‌ها…</div> : null}
          {r.items.map((it, i) => <div className="st-item" key={i}>
            <span className="st-badge sm" data-s={it.status}>{STATUS[it.status] || it.status}</span>
            <div className="st-item-text"><b>{it.title}</b><small>{it.error || it.prompt}</small></div>
            {it.credits ? <span className="st-item-cr">{short(it.credits)}</span> : null}
            {it.conversation_id ? <Link className="st-btn ghost sm" to={`/studio/${it.conversation_id}`}>باز کردن چت</Link> : null}
          </div>)}
        </div> : null}
      </div>)}</div>}
    {editing ? <TaskForm initial={{ ...task, id: task.id } as TaskDraft} title="ویرایش کار" onClose={() => setEditing(false)} onSaved={() => { setEditing(false); load(); }}/> : null}
  </main>;
}
