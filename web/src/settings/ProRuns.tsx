import React from "react";
import { authFetch, BASE } from "../api";

type Run = { id: string; user: string; conversation_id: string; status: string; updated_at: string; request: string; spent_credits?: number; usd: number;
  calls?: number; turns?: number; outputs: number; error?: string };
type Entry = { kind: "text" | "tool" | "result"; text?: string; name?: string; input?: string; error?: boolean };

/** Admin: every EditorGPT Pro run, its cost, and the agent's own log (texts, tool calls, results). */
export function ProRuns() {
  const [runs, setRuns] = React.useState<Run[] | null>(null);
  const [error, setError] = React.useState("");
  const [open, setOpen] = React.useState<string | null>(null);
  const [log, setLog] = React.useState<Entry[] | null>(null);
  React.useEffect(() => {
    authFetch(`${BASE}/admin/pro/runs`).then(r => r.ok ? r.json() : Promise.reject(r.status)).then(d => setRuns(d.runs)).catch(() => setError("فهرست اجراها دریافت نشد (فقط مدیر)."));
  }, []);
  const show = async (id: string) => {
    if (open === id) { setOpen(null); return; }
    setOpen(id); setLog(null);
    const r = await authFetch(`${BASE}/admin/pro/runs/${id}/log`);
    setLog(r.ok ? (await r.json()).entries : []);
  };
  const total = (runs || []).reduce((a, r) => a + (r.usd || 0), 0);
  return <main className="page" dir="rtl" style={{ maxWidth: 1100, margin: "0 auto", padding: 16 }}>
    <h1>اجراهای EditorGPT Pro</h1>
    {error ? <p role="alert">{error}</p> : null}
    {runs ? <p>{runs.length} اجرا · مجموع حدود {total.toFixed(2)} دلار</p> : <p><span className="spinner"/> در حال دریافت…</p>}
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
      <thead><tr><th>زمان</th><th>کاربر</th><th>درخواست</th><th>وضعیت</th><th>هزینه</th><th>تماس / دور</th><th></th></tr></thead>
      <tbody>{(runs || []).map(run => <React.Fragment key={run.id}>
        <tr style={{ borderTop: "1px solid var(--border)" }}>
          <td dir="ltr">{run.updated_at?.slice(0, 16).replace("T", " ")}</td><td>{run.user}</td>
          <td><a href={`/studio/${run.conversation_id}`}>{run.request || "—"}</a>{run.error ? <div style={{ color: "var(--error)" }}>{run.error}</div> : null}</td>
          <td>{run.status}{run.outputs ? ` · ${run.outputs} خروجی` : ""}</td><td dir="ltr">${run.usd.toFixed(2)}</td>
          <td dir="ltr">{run.calls ?? "—"} / {run.turns ?? "—"}</td>
          <td><button className="btn btn-sm btn-secondary" onClick={() => void show(run.id)}>{open === run.id ? "بستن" : "لاگ"}</button></td>
        </tr>
        {open === run.id ? <tr><td colSpan={7}>{log === null ? <p><span className="spinner"/></p> :
          <div style={{ maxHeight: 520, overflow: "auto", display: "grid", gap: 6, padding: 8 }}>{log.map((e, i) =>
            <pre key={i} dir="auto" style={{ margin: 0, whiteSpace: "pre-wrap", fontSize: 12, padding: 8, borderRadius: 6,
              background: e.kind === "tool" ? "#0b0d10" : e.kind === "result" ? "rgba(255,255,255,.04)" : "transparent",
              color: e.error ? "var(--error, #e5484d)" : undefined, borderInlineStart: e.kind === "text" ? "3px solid #7aa2f7" : undefined }}>
              {e.kind === "tool" ? `› ${e.name}  ${e.input}` : e.kind === "result" ? `↳ ${e.text}` : e.text}</pre>)}</div>}</td></tr> : null}
      </React.Fragment>)}</tbody>
    </table>
  </main>;
}
