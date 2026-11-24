import React from "react";
import { api, AgentMode, StudioAgentRun } from "../api";
import { Icon } from "../components/Icon";
import { Menu } from "../components/Menu";

export const agentModes = [
  {id: "lite" as const, name: "Lite", hint: "سریع، برای ادیت‌های روزمره"},
  {id: "medium" as const, name: "Medium", hint: "پیشرفته، کارهای چندمرحله‌ای"},
  {id: "pro" as const, name: "Pro", hint: "قوی‌ترین؛ کندتر و پرهزینه‌تر (آزمایشی)"},
  {id: "claude" as const, name: "Claude", hint: "خودِ Claude، بدون مهارت‌ها، ابزارها و قواعد ادیتورجی‌پی‌تی (آزمایشی)"},
];

export function AgentModeSelector({value, onChange}: {value: AgentMode; onChange: (mode: AgentMode) => void}) {
  return <Menu label="Agent mode" side="top" trigger={props => <button type="button" className="composer-agent" {...props}>
    <span>{agentModes.find(m => m.id === value)?.name || "Lite"}</span><Icon name="chevronDown" size={12}/>
  </button>}>
    {close => <>{agentModes.map(mode => <button type="button" key={mode.id} role="menuitem" className="menu-item agent-option"
      aria-current={mode.id === value ? "true" : undefined} onClick={() => {onChange(mode.id); close();}}>
      <span aria-hidden="true" className="agent-tick">{mode.id === value ? "✓" : ""}</span>
      <span><b>{mode.name}</b><small>{mode.hint}</small></span>
    </button>)}
    <a className="menu-item agent-option agent-guide-link" href="/guide" role="menuitem" onClick={close}><span aria-hidden="true" className="agent-tick"/><span><b>کدام موتور؟</b><small>راهنما و مشاور انتخاب موتور</small></span></a></>}
  </Menu>;
}

export function AgentSettings() {
  const [mode, setMode] = React.useState<AgentMode>("lite");
  const [loaded, setLoaded] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState("");
  React.useEffect(() => {
    let live = true;
    api.agentPreferences().then(value => {if (live) {setMode(value.default_agent_mode); setLoaded(true);}})
      .catch(() => {if (live) setError("تنظیمات ایجنت دریافت نشد؛ دوباره صفحه را باز کنید.");});
    return () => {live = false;};
  }, []);
  const change = async (next: AgentMode) => {
    setSaving(true); setError("");
    try {const saved = await api.saveAgentPreferences(next); setMode(saved.default_agent_mode);}
    catch {setError("ذخیرهٔ حالت پیش‌فرض انجام نشد. دوباره تلاش کنید.");}
    finally {setSaving(false);}
  };
  return <section className="set-section" aria-labelledby="set-agent" dir="rtl">
    <h2 id="set-agent">ایجنت</h2>
    <div className="set-controls">
      <div className="set-control"><label htmlFor="default-agent-mode"><b>حالت پیش‌فرض ایجنت</b><small>برای گفتگوهای جدید. گفتگوهای موجود انتخاب خودشان را نگه می‌دارند.</small></label>
        <select id="default-agent-mode" className="input" aria-label="حالت پیش‌فرض ایجنت" value={mode} disabled={!loaded || saving}
          onChange={event => void change(event.target.value as AgentMode)}>
          {agentModes.filter(item => item.id !== "claude").map(item => <option value={item.id} key={item.id}>{item.name}</option>)}
        </select></div>
    </div>
    {error ? <p className="notice" data-tone="error" role="alert">{error}</p> : null}
  </section>;
}

/** Only actual pending Medium executions get controls; no second chat interface. */
export function AgentRunControls({runs, chatCredits, onChanged}: {runs: StudioAgentRun[]; chatCredits?: number; onChanged: () => void}) {
  const [busy, setBusy] = React.useState<string | null>(null);
  const [error, setError] = React.useState("");
  const [confirming, setConfirming] = React.useState<string | null>(null);
  const act = async (id: string, decision: "approve" | "retry" | "cancel") => {
    if (busy) return;
    setConfirming(null); setBusy(id); setError("");
    try {await api.resumeAgentRun(id, decision); onChanged();}
    catch {setError("عملیات انجام نشد؛ گفتگو را تازه‌سازی و دوباره بررسی کنید.");}
    finally {setBusy(null);}
  };
  const pro = [...runs].reverse().find(r => r.agent_mode === "pro" && r.pro?.spent_credits != null);
  const fa = (n: number) => n.toLocaleString("fa-IR");
  // The whole chat: every Pro run of it (each run's own figure already counts its engines); a new run ("ادامه بده") adds to it, it never starts again from zero.
  const proRuns = runs.filter(r => r.agent_mode === "pro" && r.pro?.spent_credits != null);
  const chatTotal = Math.max(chatCredits ?? 0, proRuns.reduce((sum, r) => sum + (r.pro?.spent_credits || 0), 0));      // the ledger's figure counts every engine too
  const chatCalls = proRuns.reduce((sum, r) => sum + (r.pro?.calls || 0), 0);
  // Amount + unit: «۸۵۰ هزار», «۱٫۰۳ میلیون» (a bare «۱,۰۳۴ هزار» read as if it were small).
  const amount = (n: number) => n >= 1_000_000 ? `${(n / 1_000_000).toLocaleString("fa-IR", { maximumFractionDigits: n >= 10_000_000 ? 1 : 2 })} میلیون`
    : `${fa(Math.max(1, Math.round(n / 1000)))} هزار`;
  const proLine = pro ? <p className="pro-cost" dir="rtl" style={{ margin: "4px 0", fontSize: 12, color: "var(--muted, #8b8b8b)" }}>
    {pro.status === "running" || pro.status === "queued" ? "Pro در حال کار · " : "Pro · "}
    مصرف کل این چت {amount(chatTotal)} اعتبار
    {proRuns.length > 1 ? ` (این اجرا ${amount(pro.pro?.spent_credits || 0)})` : ""}
    {pro.pro?.budget_credits ? ` · سقف: اعتبار حساب (${amount(pro.pro.budget_credits)})` : " · بدون سقف"}
    {chatCalls ? ` · ${fa(chatCalls)} تماس با مدل` : ""}
  </p> : null;
  // Lite and Medium chats get the same line: everything the chat used (its own calls and every engine it started), from the credit ledger.
  const medium = [...runs].reverse().find(r => r.agent_mode === "medium");
  const mediumBusy = medium && ["queued", "running", "waiting_job"].includes(medium.status);
  const chatLine = !pro && (chatCredits || 0) > 0 ? <p className="pro-cost" dir="rtl" style={{ margin: "4px 0", fontSize: 12, color: "var(--muted, #8b8b8b)" }}>
    {mediumBusy ? "Medium در حال کار · " : ""}مصرف کل این چت {amount(chatCredits || 0)} اعتبار
  </p> : null;
  return <>{proLine}{chatLine}{runs.filter(r => r.agent_mode === "medium" && ["waiting_approval", "failed"].includes(r.status)).map(record =>
    <div className="action-card" key={record.id} aria-label="EditorGPT Medium plan">
      <h3>{record.status === "waiting_approval" ? "تأیید برنامهٔ EditorGPT Medium" : "اجرای Medium کامل نشد"}</h3>
      <p className="bidi" dir="auto">{record.status === "failed" ? record.error : record.plan?.summary}</p>
      {record.status === "waiting_approval" ? <ol>{record.plan?.steps.map((step, i) => <li key={i} dir="auto">{step.label}</li>)}</ol> : null}
      {confirming === record.id ? <p className="notice" role="status" dir="rtl">از مراحل ذخیره‌شده ادامه می‌دهد. عملیات با نتیجهٔ نامشخص خودکار تکرار نمی‌شوند و ادامه ممکن است مصرف Gateway داشته باشد.</p> : null}
      <div className="rc-actions"><button className="btn btn-sm btn-primary" disabled={busy !== null}
        onClick={() => record.status === "failed" && confirming !== record.id ? setConfirming(record.id) : void act(record.id, record.status === "failed" ? "retry" : "approve")}>
        {busy === record.id ? "در حال ارسال…" : record.status === "failed" ? (confirming === record.id ? "بله، ادامه بده" : "ادامه از مرحلهٔ ذخیره‌شده") : "تأیید برنامه"}</button>
        {confirming === record.id ? <button className="btn btn-sm btn-ghost" disabled={busy !== null} onClick={() => setConfirming(null)}>انصراف</button> : null}
        <button className="btn btn-sm btn-secondary" disabled={busy !== null} onClick={() => void act(record.id, "cancel")}>لغو</button></div>
    </div>)}{error ? <p role="alert">{error}</p> : null}</>;
}
