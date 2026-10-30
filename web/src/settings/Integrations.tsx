import React from "react";
import hermesApi from "../services/hermesApi";
import { message } from "../pages/hermes/hermesUtils";

type Status = { configured: boolean; enabled: boolean; applications: string[] };
type Conn = { application: string; name: string; connected: boolean; status: string };
type Account = { id: string | number; username: string; source?: string; token_expires_at?: string | null };
type Direct = { configured: boolean; instagram_user_id: string | null };

const APPS: Record<string, { name: string; description: string }> = {
  instagram: { name: "Instagram", description: "Publishing, analytics and content ideas for your professional account." },
  googledrive: { name: "Google Drive", description: "Import videos, audio and images from your Drive into projects." },
};
const PENDING_KEY = "editorgpt.connecting";
const appName = (slug: string) => APPS[slug]?.name || slug;

const pendingApp = () => { try { return sessionStorage.getItem(PENDING_KEY) || ""; } catch { return ""; } };
const setPending = (slug: string) => { try { slug ? sessionStorage.setItem(PENDING_KEY, slug) : sessionStorage.removeItem(PENDING_KEY); } catch { /* storage is optional */ } };
const wait = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

function StatusBadge({ conn, checking }: { conn?: Conn; checking: boolean }) {
  if (checking && !conn) return <span className="status-badge">Checking…</span>;
  if (conn?.connected) return <span className="status-badge" data-tone="ok">Connected</span>;
  if (conn && !/NOT_CONNECTED|INITIATED|INITIALIZING/i.test(conn.status)) return <span className="status-badge" data-tone="warn">Needs reconnect</span>;
  return <span className="status-badge">Not connected</span>;
}

function IdeaMix() {
  const [saved, setSaved] = React.useState<number | null>(null);
  const [value, setValue] = React.useState(50);
  const [state, setState] = React.useState("");
  const timer = React.useRef(0);
  React.useEffect(() => {
    let live = true;
    hermesApi.getAgent().then((agent: any) => { if (live) { const share = agent?.prefs?.talking_share ?? 50; setSaved(share); setValue(share); } }).catch(() => undefined);
    return () => { live = false; window.clearTimeout(timer.current); };
  }, []);
  if (saved === null) return null;
  const change = (next: number) => {
    setValue(next); setState("");
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(async () => {
      try { await hermesApi.setAgentPrefs(next); setState("Saved"); } catch { setState("Could not save"); }
    }, 500);
  };
  return <div className="set-row"><span><b>Idea mix</b><small>How many of the agent’s ideas are talking reels you film, and how many the editor produces from scratch.</small></span>
    <span style={{ display: "grid", gap: 4, minWidth: 220 }}>
      <input type="range" min={0} max={100} step={5} value={value} aria-label="Share of talking ideas" onChange={event => change(Number(event.target.value))}/>
      <small>{value}% talking · {100 - value}% produced {state ? `· ${state}` : ""}</small>
    </span></div>;
}

function DirectInstagram() {
  const fields = [["access_token", "Access token", "password"], ["instagram_user_id", "Instagram user ID", "text"], ["app_id", "App ID", "text"], ["app_secret", "App secret", "password"]] as const;
  const empty = { access_token: "", instagram_user_id: "", app_id: "", app_secret: "" };
  const [form, setForm] = React.useState<Record<string, string>>(empty);
  const [status, setStatus] = React.useState<Direct | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");
  React.useEffect(() => { hermesApi.getInstagramSettings().then(setStatus).catch(() => setStatus(null)); }, []);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (fields.some(([key]) => !form[key].trim())) { setError("Fill in every field."); return; }
    setBusy(true); setError(""); setNotice("");
    try {
      setStatus(await hermesApi.saveInstagramSettings(Object.fromEntries(fields.map(([key]) => [key, form[key].trim()]))));
      setForm(empty); setNotice("Credentials saved.");
    } catch (e) { setError(message(e)); } finally { setBusy(false); }
  }
  async function remove() {
    setBusy(true); setError(""); setNotice("");
    try { setStatus(await hermesApi.deleteInstagramSettings()); setNotice("Credentials removed."); }
    catch (e) { setError(message(e)); } finally { setBusy(false); }
  }
  return <details className="set-details"><summary>Advanced · direct Instagram API credentials</summary>
    <div className="set-detail-body">
      <p className="set-hint">Optional. Only for your own Meta developer app; separate from the connections above. Values are encrypted and never shown again.</p>
      <p className="set-hint" role="status">{status?.configured ? `Configured${status.instagram_user_id ? ` · ${status.instagram_user_id}` : ""}` : "Not configured"}</p>
      <form onSubmit={save} autoComplete="off" noValidate style={{ display: "grid", gap: 10 }}>
        {fields.map(([key, label, type]) => <label className="field" key={key}>{label}
          <input className="input" type={type} value={form[key]} disabled={busy} autoComplete="new-password" spellCheck={false}
            onChange={event => setForm(current => ({ ...current, [key]: event.target.value }))}/></label>)}
        <div className="set-actions">
          <button className="btn btn-sm btn-primary" type="submit" disabled={busy}>{busy ? "Working…" : "Save"}</button>
          <button className="btn btn-sm btn-secondary" type="button" onClick={remove} disabled={busy || !status?.configured}>Remove</button>
        </div>
        {error ? <p role="alert">{error}</p> : null}{notice ? <p role="status">{notice}</p> : null}
      </form></div></details>;
}

export function IntegrationsSettings() {
  const [status, setStatus] = React.useState<Status | null>(null);
  const [conns, setConns] = React.useState<Conn[]>([]);
  const [accounts, setAccounts] = React.useState<Account[]>([]);
  const [checking, setChecking] = React.useState(false);
  const [busy, setBusy] = React.useState("");
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");
  const alive = React.useRef(true);
  React.useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);

  const check = React.useCallback(async (expect = ""): Promise<Conn[]> => {
    setChecking(true);
    let latest: Conn[] = [];
    try {
      // Right after authorization the provider can take a few seconds to report the account as active.
      for (let attempt = 0; attempt < (expect ? 5 : 1); attempt++) {
        latest = (await hermesApi.getComposioConnections()).applications as Conn[];
        if (!alive.current) return latest;
        setConns(latest);
        if (!expect || latest.some(item => item.application === expect && item.connected)) break;
        await wait(3000);
      }
    } finally { if (alive.current) setChecking(false); }
    return latest;
  }, []);

  React.useEffect(() => {
    let live = true;
    (async () => {
      try {
        const result: Status = await hermesApi.getComposioSettings();
        if (!live) return;
        setStatus(result);
        const query = new URLSearchParams(window.location.search);
        const returned = query.has("connected_account_id") || query.has("status");
        if (returned) {
          query.delete("connected_account_id"); query.delete("status");
          window.history.replaceState(null, "", window.location.pathname + (query.size ? `?${query}` : "") + window.location.hash);
        }
        if (result.enabled && result.configured) {
          const expect = returned ? pendingApp() : "";
          if (returned) setNotice(`Finishing the ${expect ? appName(expect) : "account"} connection…`);
          const latest = await check(expect);
          if (!live) return;
          if (returned) {
            setPending("");
            const ok = expect ? latest.some(item => item.application === expect && item.connected) : latest.some(item => item.connected);
            setNotice(ok ? `${expect ? appName(expect) : "Account"} connected.` : "Authorization finished, but the account is not active yet. Press Check connections.");
          }
        }
      } catch (e) { if (live) setError(message(e)); }
    })();
    hermesApi.getAccounts().then((list: Account[]) => { if (live) setAccounts(Array.isArray(list) ? list : []); }).catch(() => undefined);
    return () => { live = false; };
  }, [check]);

  async function run(name: string, action: () => Promise<void>) {
    if (busy) return;
    setBusy(name); setError(""); setNotice("");
    try { await action(); } catch (e) { if (alive.current) setError(message(e)); } finally { if (alive.current) setBusy(""); }
  }
  const toggle = () => run("toggle", async () => {
    const next = await hermesApi.setComposioEnabled(!status?.enabled);
    setStatus(next); setConns([]);
    if (next.enabled && next.configured) await check();
  });
  const connect = (slug: string) => run(`connect-${slug}`, async () => {
    const result = await hermesApi.connectComposioApp(slug);
    const target = new URL(result.redirect_url);
    if (target.protocol !== "https:" || target.username || target.password) throw new Error("The authorization link is invalid.");
    setPending(slug);
    setNotice(`Opening ${appName(slug)} authorization…`);
    window.location.assign(target.href);
  });
  const refreshToken = (account: Account) => run(`token-${account.id}`, async () => {
    await hermesApi.refreshToken(account.id);
    setAccounts(await hermesApi.getAccounts());
    setNotice(`Token refreshed for @${account.username}.`);
  });

  const usable = !!status?.enabled && !!status.configured;
  return <section className="set-section" id="integrations" aria-labelledby="set-integrations" aria-busy={!!busy || checking}>
    <h2 id="set-integrations">Connected services</h2>
    <p className="set-hint">Connect accounts through their own authorization page. Passwords and API keys are never requested here.</p>
    {error ? <p role="alert">{error}</p> : null}
    {notice ? <p role="status">{notice}</p> : null}
    {status && !status.configured ? <div className="notice" role="status"><b>Server setup required</b>
      <p className="set-hint">An administrator must configure Composio (API key, instance ID and callback URL) on the server before services can be connected.</p></div> : null}

    {status ? <div className="set-row"><span><b>Integration</b><small>{status.enabled ? "On: EditorGPT can use the services below." : "Off: EditorGPT has no access to any connected service. Your accounts are not removed."}</small></span>
      <button className="btn btn-sm btn-secondary" type="button" onClick={() => void toggle()} disabled={!!busy || (!status.configured && !status.enabled)}>{status.enabled ? "Turn off" : "Turn on"}</button></div> : <p className="set-hint">Checking…</p>}

    {usable ? status!.applications.map(slug => {
      const conn = conns.find(item => item.application === slug);
      return <div className="set-row" key={slug}><span><b>{appName(slug)} <StatusBadge conn={conn} checking={checking}/></b><small>{APPS[slug]?.description || "Connected through Composio."}</small></span>
        <button className="btn btn-sm btn-primary" type="button" disabled={!!busy || checking} onClick={() => void connect(slug)}>
          {busy === `connect-${slug}` ? "Opening…" : conn?.connected ? "Add another account" : conn && !/NOT_CONNECTED/i.test(conn.status) ? "Reconnect" : "Connect"}</button></div>;
    }) : null}
    {usable ? <div className="set-actions"><button className="btn btn-sm btn-secondary" type="button" disabled={!!busy || checking} onClick={() => void check()}>{checking ? "Checking…" : "Check connections"}</button>
      {checking && !conns.length ? <small>The first check can take up to a minute.</small> : null}</div> : null}

    {accounts.length ? <>
      <h3 style={{ marginTop: 18 }}>Instagram accounts</h3>
      {accounts.map(account => {
        const expiry = account.token_expires_at ? new Date(account.token_expires_at).getTime() : 0;
        const composio = account.source === "composio";
        const state = composio ? "Connected" : !expiry || expiry < Date.now() ? "Expired" : expiry < Date.now() + 14 * 86400000 ? "Expiring soon" : "Connected";
        return <div className="set-row" key={account.id}><span><b>@{account.username}</b><small>{composio ? "Connected through Composio · read-only" : `Direct token · ${state}`}</small></span>
          {composio ? <span className="status-badge" data-tone="ok">Connected</span> : <button className="btn btn-sm btn-secondary" type="button" disabled={!!busy} onClick={() => void refreshToken(account)}>Refresh token</button>}</div>;
      })}</> : null}

    <IdeaMix/>
    <DirectInstagram/>
    <p className="set-footnote">Turning an integration off stops EditorGPT’s access; it does not revoke the provider account. Publishing and messaging stay disabled in this stage.</p>
  </section>;
}
