import React from "react";
import hermesApi from "../services/hermesApi";
import { message } from "../pages/hermes/hermesUtils";

type Status = { configured: boolean; enabled: boolean; applications: string[] };
type Conn = { application: string; name: string; connected: boolean; status: string };
type Account = { id: string | number; username: string; source?: string; token_expires_at?: string | null };
type Direct = { configured: boolean; instagram_user_id: string | null };

const APPS: Record<string, { name: string; description: string }> = {
  instagram: { name: "اینستاگرام", description: "انتشار، آمار و ایدهٔ محتوا برای حساب حرفه‌ای شما." },
  googledrive: { name: "گوگل درایو", description: "ویدیو، صدا و تصویر را از درایو خود به پروژه‌ها وارد کنید." },
};
const PENDING_KEY = "editorgpt.connecting";
const appName = (slug: string) => APPS[slug]?.name || slug;

const pendingApp = () => { try { return sessionStorage.getItem(PENDING_KEY) || ""; } catch { return ""; } };
const setPending = (slug: string) => { try { slug ? sessionStorage.setItem(PENDING_KEY, slug) : sessionStorage.removeItem(PENDING_KEY); } catch { /* storage is optional */ } };
const wait = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

function StatusBadge({ conn, checking }: { conn?: Conn; checking: boolean }) {
  if (checking && !conn) return <span className="badge">در حال بررسی…</span>;
  if (conn?.connected) return <span className="badge" data-tone="success">متصل</span>;
  if (conn && !/NOT_CONNECTED|INITIATED|INITIALIZING/i.test(conn.status)) return <span className="badge" data-tone="warning">نیاز به اتصال دوباره</span>;
  return <span className="badge">متصل نیست</span>;
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
      try { await hermesApi.setAgentPrefs(next); setState("ذخیره شد"); } catch { setState("ذخیره نشد"); }
    }, 500);
  };
  return <div className="conn-card">
    <header><div><b>ترکیب ایده‌ها</b></div>
      <p>چند درصد ایده‌های ایجنت، ریل صحبتی است که خودتان فیلم می‌گیرید و چند درصد را ادیتور از صفر می‌سازد.</p></header>
    <div style={{ display: "grid", gap: 6 }}>
      <input type="range" min={0} max={100} step={5} value={value} aria-label="سهم ایده‌های صحبتی" onChange={event => change(Number(event.target.value))}/>
      <small className="conn-note">{value}٪ صحبتی · {100 - value}٪ ساخته‌شده توسط ادیتور {state ? `· ${state}` : ""}</small>
    </div></div>;
}

function DirectInstagram() {
  const fields = [["access_token", "توکن دسترسی", "password"], ["instagram_user_id", "شناسهٔ کاربری اینستاگرام", "text"], ["app_id", "شناسهٔ اپ (App ID)", "text"], ["app_secret", "رمز اپ (App secret)", "password"]] as const;
  const empty = { access_token: "", instagram_user_id: "", app_id: "", app_secret: "" };
  const [form, setForm] = React.useState<Record<string, string>>(empty);
  const [status, setStatus] = React.useState<Direct | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");
  React.useEffect(() => { hermesApi.getInstagramSettings().then(setStatus).catch(() => setStatus(null)); }, []);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (fields.some(([key]) => !form[key].trim())) { setError("همهٔ فیلدها را پر کنید."); return; }
    setBusy(true); setError(""); setNotice("");
    try {
      setStatus(await hermesApi.saveInstagramSettings(Object.fromEntries(fields.map(([key]) => [key, form[key].trim()]))));
      setForm(empty); setNotice("اطلاعات ذخیره شد.");
    } catch (e) { setError(message(e)); } finally { setBusy(false); }
  }
  async function remove() {
    setBusy(true); setError(""); setNotice("");
    try { setStatus(await hermesApi.deleteInstagramSettings()); setNotice("اطلاعات حذف شد."); }
    catch (e) { setError(message(e)); } finally { setBusy(false); }
  }
  return <details className="set-details"><summary>پیشرفته · اطلاعات مستقیم API اینستاگرام</summary>
    <div className="set-detail-body">
      <p className="set-hint">اختیاری. فقط برای اپ توسعه‌دهندهٔ Meta خودتان؛ جدا از اتصال‌های بالا. مقدارها رمزگذاری می‌شوند و دوباره نشان داده نمی‌شوند.</p>
      <p className="set-hint" role="status">{status?.configured ? `تنظیم شده${status.instagram_user_id ? ` · ${status.instagram_user_id}` : ""}` : "تنظیم نشده"}</p>
      <form onSubmit={save} autoComplete="off" noValidate style={{ display: "grid", gap: 10 }}>
        {fields.map(([key, label, type]) => <label className="field" key={key}>{label}
          <input className="input" type={type} dir="ltr" value={form[key]} disabled={busy} autoComplete="new-password" spellCheck={false}
            onChange={event => setForm(current => ({ ...current, [key]: event.target.value }))}/></label>)}
        <div className="set-actions">
          <button className="btn btn-sm btn-primary" type="submit" disabled={busy}>{busy ? "در حال انجام…" : "ذخیره"}</button>
          <button className="btn btn-sm btn-secondary" type="button" onClick={remove} disabled={busy || !status?.configured}>حذف</button>
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
  const [confirming, setConfirming] = React.useState("");     // "disconnect-<slug>" or "switch-<slug>" while the person is asked to confirm
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

  const loadAccounts = React.useCallback(async () => {
    try { const list = await hermesApi.getAccounts(); if (alive.current) setAccounts(Array.isArray(list) ? list : []); } catch { /* the list is optional */ }
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
          if (returned) setNotice(`در حال نهایی‌کردن اتصال ${expect ? appName(expect) : "حساب"}…`);
          const latest = await check(expect);
          if (!live) return;
          if (returned) {
            setPending("");
            const ok = expect ? latest.some(item => item.application === expect && item.connected) : latest.some(item => item.connected);
            setNotice(ok ? `${expect ? appName(expect) : "حساب"} متصل شد.` : "مجوز داده شد، ولی حساب هنوز فعال نشده. دکمهٔ «بررسی اتصال‌ها» را بزنید.");
            void loadAccounts();
          }
        }
      } catch (e) { if (live) setError(message(e)); }
    })();
    void loadAccounts();
    return () => { live = false; };
  }, [check, loadAccounts]);

  async function run(name: string, action: () => Promise<void>) {
    if (busy) return;
    setBusy(name); setError(""); setNotice(""); setConfirming("");
    try { await action(); } catch (e) { if (alive.current) setError(message(e)); } finally { if (alive.current) setBusy(""); }
  }
  const toggle = () => run("toggle", async () => {
    const next = await hermesApi.setComposioEnabled(!status?.enabled);
    setStatus(next); setConns([]);
    if (next.enabled && next.configured) await check();
  });
  async function openAuthorization(slug: string) {
    const result = await hermesApi.connectComposioApp(slug);
    const target = new URL(result.redirect_url);
    if (target.protocol !== "https:" || target.username || target.password) throw new Error("لینک مجوز نامعتبر است.");
    setPending(slug);
    setNotice(`در حال باز کردن صفحهٔ مجوز ${appName(slug)}…`);
    window.location.assign(target.href);
  }
  async function removeConnection(slug: string) {
    await hermesApi.disconnectComposioApp(slug);
    setConns(current => current.map(item => item.application === slug ? { ...item, connected: false, status: "NOT_CONNECTED" } : item));
    await loadAccounts();
  }
  const connect = (slug: string) => run(`connect-${slug}`, () => openAuthorization(slug));
  const disconnect = (slug: string) => run(`disconnect-${slug}`, async () => {
    await removeConnection(slug);
    await check();
    setNotice(`اتصال ${appName(slug)} قطع شد. هر وقت خواستید حساب دیگری را وصل کنید.`);
  });
  const switchAccount = (slug: string) => run(`switch-${slug}`, async () => {
    await removeConnection(slug);          // the old account is removed first, so the authorization page connects a different one
    await openAuthorization(slug);
  });
  const refreshToken = (account: Account) => run(`token-${account.id}`, async () => {
    await hermesApi.refreshToken(account.id);
    setAccounts(await hermesApi.getAccounts());
    setNotice(`توکن @${account.username} تازه شد.`);
  });

  const usable = !!status?.enabled && !!status.configured;
  const viaComposio = accounts.find(account => account.source === "composio");
  const direct = accounts.filter(account => account.source !== "composio");
  return <section className="set-section conn" id="integrations" aria-labelledby="set-integrations" aria-busy={!!busy || checking}>
    <h2 id="set-integrations">سرویس‌های متصل</h2>
    <p className="set-hint">حساب‌ها را از صفحهٔ مجوز خودِ سرویس وصل کنید. گذرواژه و کلید API هرگز اینجا خواسته نمی‌شود.</p>
    {error ? <p role="alert">{error}</p> : null}
    {notice ? <p role="status">{notice}</p> : null}
    {status && !status.configured ? <div className="notice" role="status"><b>نیاز به تنظیم سرور</b>
      <p className="set-hint">یک مدیر باید Composio (کلید API، شناسهٔ نمونه و آدرس بازگشت) را روی سرور تنظیم کند تا بشود سرویس‌ها را وصل کرد.</p></div> : null}

    {status ? <div className="conn-card conn-master">
      <header><div><b>یکپارچگی</b> <span className="badge" data-tone={status.enabled ? "success" : undefined}>{status.enabled ? "روشن" : "خاموش"}</span></div>
        <p>{status.enabled ? "روشن: ادیتورجی‌پی‌تی می‌تواند از سرویس‌های زیر استفاده کند." : "خاموش: ادیتورجی‌پی‌تی به هیچ سرویس متصلی دسترسی ندارد. حساب‌های شما حذف نمی‌شوند."}</p></header>
      <div className="conn-actions"><button className="btn btn-sm btn-secondary" type="button" onClick={() => void toggle()} disabled={!!busy || (!status.configured && !status.enabled)}>{status.enabled ? "خاموش‌کردن" : "روشن‌کردن"}</button></div></div>
      : <p className="set-hint">در حال بررسی…</p>}

    {usable ? <div className="conn-list">{status!.applications.map(slug => {
      const conn = conns.find(item => item.application === slug);
      const connected = !!conn?.connected;
      const needsReconnect = !!conn && !connected && !/NOT_CONNECTED|INITIATED|INITIALIZING/i.test(conn.status);
      const account = slug === "instagram" && connected ? viaComposio : undefined;
      const name = appName(slug);
      return <article className="conn-card" key={slug} data-connected={connected}>
        <header><div><b>{name}</b> <StatusBadge conn={conn} checking={checking}/></div>
          <p>{APPS[slug]?.description || "از طریق Composio وصل می‌شود."}</p>
          {account ? <p className="conn-account">حساب متصل: <bdi dir="ltr">@{account.username}</bdi> · فقط‌خواندنی</p> : null}</header>
        <div className="conn-actions">
          {connected ? <>
            <button className="btn btn-sm btn-primary" type="button" disabled={!!busy || checking} onClick={() => setConfirming(`switch-${slug}`)}>
              {busy === `switch-${slug}` ? "در حال انجام…" : "تغییر حساب"}</button>
            <button className="btn btn-sm btn-danger" type="button" disabled={!!busy || checking} onClick={() => setConfirming(`disconnect-${slug}`)}>
              {busy === `disconnect-${slug}` ? "در حال قطع…" : "قطع اتصال"}</button>
          </> : <button className="btn btn-sm btn-primary" type="button" disabled={!!busy || checking} onClick={() => void connect(slug)}>
            {busy === `connect-${slug}` ? "در حال باز کردن…" : needsReconnect ? "اتصال دوباره" : "اتصال"}</button>}
        </div>
        {confirming === `disconnect-${slug}` ? <div className="conn-confirm" role="alertdialog" aria-label={`قطع اتصال ${name}`}>
          <p>اتصال {name} از حساب شما در ادیتورجی‌پی‌تی قطع شود؟ فقط همین اتصال حذف می‌شود و اتصال سایر کاربران دست‌نخورده می‌ماند. هر زمان می‌توانید دوباره وصلش کنید.</p>
          <div className="set-actions"><button className="btn btn-sm btn-danger" type="button" onClick={() => void disconnect(slug)}>بله، قطع شود</button>
            <button className="btn btn-sm btn-secondary" type="button" onClick={() => setConfirming("")}>انصراف</button></div></div> : null}
        {confirming === `switch-${slug}` ? <div className="conn-confirm" role="alertdialog" aria-label={`تغییر حساب ${name}`}>
          <p>اول اتصال حساب فعلی قطع می‌شود و بعد صفحهٔ مجوز {name} باز می‌شود تا حساب دیگری را وصل کنید. اگر آن صفحه خودکار با حساب قبلی وارد شد، از همان‌جا خارج شوید و حساب دیگر را انتخاب کنید.</p>
          <div className="set-actions"><button className="btn btn-sm btn-primary" type="button" onClick={() => void switchAccount(slug)}>ادامه</button>
            <button className="btn btn-sm btn-secondary" type="button" onClick={() => setConfirming("")}>انصراف</button></div></div> : null}
      </article>;
    })}</div> : null}
    {usable ? <div className="set-actions"><button className="btn btn-sm btn-secondary" type="button" disabled={!!busy || checking} onClick={() => void check()}>{checking ? "در حال بررسی…" : "بررسی اتصال‌ها"}</button>
      {checking && !conns.length ? <small>بررسی اول ممکن است تا یک دقیقه طول بکشد.</small> : null}</div> : null}

    {direct.length ? <>
      <h3 className="conn-sub">حساب‌های اینستاگرام با توکن مستقیم</h3>
      <div className="conn-list">{direct.map(account => {
        const expiry = account.token_expires_at ? new Date(account.token_expires_at).getTime() : 0;
        const state = !expiry || expiry < Date.now() ? "منقضی" : expiry < Date.now() + 14 * 86400000 ? "به‌زودی منقضی می‌شود" : "متصل";
        return <article className="conn-card" key={account.id}>
          <header><div><b dir="ltr">@{account.username}</b></div><p>توکن مستقیم · {state}</p></header>
          <div className="conn-actions"><button className="btn btn-sm btn-secondary" type="button" disabled={!!busy} onClick={() => void refreshToken(account)}>تازه‌کردن توکن</button></div>
        </article>;
      })}</div></> : null}

    <h3 className="conn-sub">تنظیمات دیگر</h3>
    <div className="conn-list"><IdeaMix/><DirectInstagram/></div>
    <p className="set-footnote">خاموش‌کردن یکپارچگی فقط دسترسی ادیتورجی‌پی‌تی را قطع می‌کند و حساب سرویس‌دهنده را لغو نمی‌کند؛ برای لغو کامل از «قطع اتصال» استفاده کنید. انتشار و پیام‌دهی در این مرحله غیرفعال‌اند.</p>
  </section>;
}
