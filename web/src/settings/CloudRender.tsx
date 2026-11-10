import React from "react";
import { renderCloudAdminRequest } from "../api";
import { friendlyError } from "../ui";

type Limits = { daily_budget: number; monthly_budget: number; max_cost: number; max_workers: number; max_gpu: number };
type Execution = { id: string; state: string; backend: string; reservation: number; provider_charge_usd: number | null; cleanup_pending: number; cancel_requested: number };
type Status = { enabled: boolean; cpu: boolean; gpu: boolean; sandbox_verified: boolean; network_namespace_verified: boolean; browser_isolation_verified?: boolean; override: string; limits: Limits; ceilings: Limits; executions: Execution[]; cost_note: string };
const FIELDS: { key: keyof Limits; label: string; min: number; step: number }[] = [
  { key: "daily_budget", label: "Daily budget (USD)", min: .01, step: .01 },
  { key: "monthly_budget", label: "Monthly budget (USD)", min: .01, step: .01 },
  { key: "max_cost", label: "Maximum per render (USD)", min: .01, step: .01 },
  { key: "max_workers", label: "Maximum workers", min: 1, step: 1 },
  { key: "max_gpu", label: "Maximum GPU jobs", min: 0, step: 1 },
];

/** Mounted only inside the existing administrator section; backend also enforces authorization. */
export function CloudRenderSettings() {
  const [data, setData] = React.useState<Status | null>(null);
  const [draft, setDraft] = React.useState<Limits | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const mounted = React.useRef(true);
  const accept = React.useCallback((value: Status) => { if (mounted.current) { setData(value); setDraft(value.limits); } }, []);
  React.useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    renderCloudAdminRequest<Status>("/status", { signal: controller.signal }).then(accept).catch(e => {
      if (!controller.signal.aborted) setError(friendlyError(e, "load render infrastructure"));
    });
    return () => { mounted.current = false; controller.abort(); };
  }, [accept]);
  async function request(path: string, init?: RequestInit) {
    setBusy(true); setError("");
    try {
      if (path === "/cancel") {
        await renderCloudAdminRequest(path, init);
        accept(await renderCloudAdminRequest<Status>("/status"));
      } else accept(await renderCloudAdminRequest<Status>(path, init));
    } catch (e) { if (mounted.current) setError(friendlyError(e, "update render infrastructure")); }
    finally { if (mounted.current) setBusy(false); }
  }
  function controls(value: object) { return request("/controls", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(value) }); }
  const state = data ? `${data.enabled ? "Administrator canary enabled" : "Cloud rendering disabled"} · ${data.sandbox_verified ? "MLT isolation verified" : "MLT isolation check required"}` : "Loading infrastructure status…";
  return <section className="set-cloud" aria-label="Cloud rendering · administration">
    <p className="set-hint"><b>{state}</b>{data ? ((data.browser_isolation_verified ?? data.network_namespace_verified) ? " · Browser isolation verified; each engine still requires a matching render profile." : " · HyperFrames, Remotion and Talking require a separate browser isolation check.") : ""}</p>
    {draft && data ? <form onSubmit={event => { event.preventDefault(); void controls(draft); }}>
      <div className="set-controls">
        {FIELDS.map(field => <label className="set-control set-control-compact" key={field.key}><span><b>{field.label}</b></span>
          <input className="input" type="number" min={field.min} max={data.ceilings[field.key]} step={field.step} required disabled={busy}
            value={Number.isFinite(draft[field.key]) ? draft[field.key] : ""} onChange={event => setDraft(current => current ? { ...current, [field.key]: event.target.valueAsNumber } : current)}/></label>)}
        <label className="set-control set-control-compact"><span><b>Execution environment</b></span><select className="input" value={data.override} disabled={busy}
          onChange={event => void controls({ override: event.target.value })}>
          <option value="auto">Measured automatic selection</option><option value="local">Local only</option>
          <option value="runpod_cpu" disabled={!data.cpu}>RunPod CPU</option><option value="runpod_gpu" disabled={!data.gpu}>RunPod GPU</option>
        </select></label>
      </div>
      <div className="set-actions">
        <button className="btn btn-sm" type="submit" disabled={busy}>{busy ? "Working…" : "Save limits"}</button>
        <button className="btn btn-sm btn-secondary" type="button" disabled={busy || (!data.enabled && !data.sandbox_verified)}
          onClick={() => void controls({ enable_cloud_render: !data.enabled })}>{data.enabled ? "Pause new cloud jobs" : "Enable administrator canary"}</button>
        <button className="btn btn-sm btn-secondary" type="button" disabled={busy} onClick={() => void request("/status")}>Refresh</button>
      </div>
    </form> : <div className="set-actions"><button className="btn btn-sm btn-secondary" type="button" disabled={busy} onClick={() => void request("/status")}>Refresh</button></div>}
    {error ? <p className="notice" data-tone="error" role="alert">{error}</p> : null}
    {data ? <><p className="set-hint">{data.cost_note}</p><ul className="set-runs">{data.executions.slice(0, 10).map(row => <li key={row.id}>
      <span>{row.id.slice(0, 10)} · {row.backend} · {row.state} · reserved ${row.reservation.toFixed(3)} · provider {row.provider_charge_usd == null ? "not reported" : `$${row.provider_charge_usd.toFixed(3)}`}{row.cleanup_pending ? " · cleanup pending" : ""}</span>
      {!['completed','failed','cancelled'].includes(row.state) ? <button className="btn btn-sm btn-secondary" type="button" disabled={busy || !!row.cancel_requested}
        aria-label={`Cancel render ${row.id}`} onClick={() => void request("/cancel", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ job_id: row.id }) })}>{row.cancel_requested ? "Stopping…" : "Cancel"}</button> : null}
    </li>)}</ul></> : null}
  </section>;
}
