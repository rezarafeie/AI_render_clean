import React from "react";
import { api, AgentMode, StudioAgentRun } from "../api";
import { Icon } from "../components/Icon";
import { Menu } from "../components/Menu";

export const agentModes = [
  {id: "lite" as const, name: "Lite", hint: "سریع، برای ادیت‌های روزمره"},
  {id: "medium" as const, name: "Medium", hint: "پیشرفته، کارهای چندمرحله‌ای"},
  {id: "pro" as const, name: "Pro", hint: "قوی‌ترین؛ کندتر و پرهزینه‌تر (آزمایشی)"},
];

export function AgentModeSelector({value, onChange}: {value: AgentMode; onChange: (mode: AgentMode) => void}) {
  return <Menu label="Agent mode" side="top" trigger={props => <button type="button" className="composer-agent" {...props}>
    <span>{agentModes.find(m => m.id === value)?.name || "Lite"}</span><Icon name="chevronDown" size={12}/>
  </button>}>
    {close => agentModes.map(mode => <button type="button" key={mode.id} role="menuitem" className="menu-item agent-option"
      aria-current={mode.id === value ? "true" : undefined} onClick={() => {onChange(mode.id); close();}}>
      <span aria-hidden="true" className="agent-tick">{mode.id === value ? "✓" : ""}</span>
      <span><b>{mode.name}</b><small>{mode.hint}</small></span>
    </button>)}
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
          {agentModes.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}
        </select></div>
    </div>
    {error ? <p className="notice" data-tone="error" role="alert">{error}</p> : null}
  </section>;
}

/** Only actual pending Medium executions get controls; no second chat interface. */
export function AgentRunControls({runs, onChanged}: {runs: StudioAgentRun[]; onChanged: () => void}) {
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
  return <>{runs.filter(r => r.agent_mode === "medium" && ["waiting_approval", "failed"].includes(r.status)).map(record =>
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
