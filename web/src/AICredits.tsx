import React from "react";
import { aiAdminRequest as request } from "./api";
import type { CreditEntry, CreditGroup, CreditOrder, CreditPackage } from "./api";
import { fmt } from "./CreditsPage";

type UserRow = { id: string; email: string; name: string; has_account: boolean; balance: number; used_total: number; granted_total: number; unlimited: boolean };
type Weight = { in: number; out: number; cache: number; write: number };
type Settings = { initial_grant: number; enforce: boolean; weights: Record<string, Weight>; default: Weight; per_call: Record<string, number> };
type Detail = { account: { balance: number; used_total: number; granted_total: number; unlimited: boolean }; chats: CreditGroup[]; projects: CreditGroup[]; items: CreditEntry[]; total: number };
const json = (body: unknown, method = "POST"): RequestInit => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const fmtErr = (e: unknown) => e instanceof Error ? e.message : String(e);

/** Administrator → اعتبار: balances, the weights table, packages and orders. All texts are Persian (the rest of this panel is English). */
export default function AICredits() {
  const [users, setUsers] = React.useState<UserRow[]>([]);
  const [query, setQuery] = React.useState("");
  const [settings, setSettings] = React.useState<Settings | null>(null);
  const [packages, setPackages] = React.useState<CreditPackage[]>([]);
  const [orders, setOrders] = React.useState<CreditOrder[]>([]);
  const [detail, setDetail] = React.useState<{ id: string; label: string; data: Detail } | null>(null);
  const [error, setError] = React.useState(""); const [notice, setNotice] = React.useState("");
  const [tick, setTick] = React.useState(0);
  const refresh = () => setTick(n => n + 1);
  React.useEffect(() => { const t = setTimeout(() => void request<{ items: UserRow[] }>(`/credits/users?query=${encodeURIComponent(query)}`).then(r => setUsers(r.items)).catch(e => setError(fmtErr(e))), 200); return () => clearTimeout(t); }, [query, tick]);
  React.useEffect(() => { void request<Settings>("/credits/settings").then(setSettings).catch(e => setError(fmtErr(e))); }, [tick]);
  React.useEffect(() => { void request<{ items: CreditPackage[] }>("/credits/packages").then(r => setPackages(r.items)).catch(() => {}); void request<{ items: CreditOrder[] }>("/credits/orders").then(r => setOrders(r.items)).catch(() => {}); }, [tick]);
  async function act(task: () => Promise<unknown>, message: string) { setError(""); setNotice(""); try { await task(); setNotice(message); refresh(); } catch (e) { setError(fmtErr(e)); } }
  async function adjust(user: UserRow) {
    const raw = prompt(`تغییر اعتبار «${user.name || user.email}»\nعدد مثبت = افزایش، عدد منفی = کاهش (مثلاً 5000000 یا -200000):`); if (!raw) return;
    const amount = Math.round(Number(raw.replace(/[,٬\s]/g, "")));
    if (!Number.isFinite(amount) || amount === 0) { setError("عدد معتبر نیست."); return; }
    const note = prompt("توضیح (اختیاری):") || "";
    await act(() => request(`/credits/users/${encodeURIComponent(user.id)}/adjust`, json({ amount, note })), "اعتبار تغییر کرد.");
  }
  async function open(user: UserRow) { try { setDetail({ id: user.id, label: user.name || user.email, data: await request<Detail>(`/credits/users/${encodeURIComponent(user.id)}?size=100`) }); } catch (e) { setError(fmtErr(e)); } }
  const setWeight = (key: string, field: keyof Weight, value: number) => settings && setSettings({ ...settings, weights: { ...settings.weights, [key]: { ...settings.weights[key], [field]: value } } });
  const dir = { dir: "rtl" as const, style: { textAlign: "right" as const } };
  return <section {...dir}>
    {error ? <div role="alert" className="ai-alert">{error}</div> : null}{notice ? <p role="status">{notice}</p> : null}
    <h2>تنظیمات اعتبار</h2>
    {settings ? <div className="ai-form-grid">
      <label>اعتبار اولیه هر کاربر (توکن وزن‌دار)<input type="number" min={0} value={settings.initial_grant} onChange={e => setSettings({ ...settings, initial_grant: Number(e.target.value) })}/></label>
      <label><input type="checkbox" checked={settings.enforce} onChange={e => setSettings({ ...settings, enforce: e.target.checked })}/> رد کردن درخواست جدید وقتی اعتبار تمام شد</label>
    </div> : null}
    {settings ? <><h3>ضریب مدل‌ها</h3>
      <p className="eg-muted">۱ = قیمت یک توکن ورودی Claude Opus (۴ دلار در میلیون). ضریب هر مدل برای توکن ورودی، خروجی، کش‌خوانده و کش‌نوشته جدا است. نام مدل با نامی که شامل این کلید باشد جور می‌شود (کلید بلندتر برنده است)؛ بقیه مدل‌ها «پیش‌فرض» می‌گیرند.</p>
      <div className="ai-table-wrap"><table><thead><tr><th>کلید مدل</th><th>ورودی</th><th>خروجی</th><th>کش‌خوانده</th><th>کش‌نوشته</th><th/></tr></thead><tbody>
        {Object.entries(settings.weights).map(([key, w]) => <tr key={key}><td><code>{key}</code></td>{(["in", "out", "cache", "write"] as const).map(f => <td key={f}><input type="number" step="0.01" min={0} style={{ width: 80 }} value={w[f]} onChange={e => setWeight(key, f, Number(e.target.value))}/></td>)}
          <td><button onClick={() => { const { [key]: _drop, ...rest } = settings.weights; void _drop; setSettings({ ...settings, weights: rest }); }}>حذف</button></td></tr>)}
        <tr><td><b>پیش‌فرض</b></td>{(["in", "out", "cache", "write"] as const).map(f => <td key={f}><input type="number" step="0.01" min={0} style={{ width: 80 }} value={settings.default[f]} onChange={e => setSettings({ ...settings, default: { ...settings.default, [f]: Number(e.target.value) } })}/></td>)}<td/></tr>
      </tbody></table></div>
      <button onClick={() => { const key = (prompt("کلید مدل جدید (مثلاً gpt_5_mini):") || "").trim().toLowerCase(); if (key) setSettings({ ...settings, weights: { ...settings.weights, [key]: { ...settings.default } } }); }}>افزودن مدل</button>
      <h3>هزینهٔ ثابت هر فراخوانی (تصویر، صدا، ویدیو، رونویسی؛ جایی که توکن گزارش نمی‌شود)</h3>
      <div className="ai-form-grid">{Object.entries(settings.per_call).map(([key, value]) => <label key={key}>{key}<input type="number" min={0} value={value} onChange={e => setSettings({ ...settings, per_call: { ...settings.per_call, [key]: Number(e.target.value) } })}/></label>)}</div>
      <button onClick={() => void act(() => request("/credits/settings", json(settings, "PUT")), "تنظیمات ذخیره شد؛ برای درخواست‌های بعدی اعمال می‌شود.")}>ذخیره تنظیمات</button></> : null}

    <h2>کاربران</h2>
    <div className="ai-toolbar"><input placeholder="جست‌وجوی نام یا ایمیل" value={query} onChange={e => setQuery(e.target.value)}/></div>
    <div className="ai-table-wrap"><table><thead><tr><th>کاربر</th><th>مانده</th><th>مصرف‌شده</th><th>دریافتی</th><th>نامحدود</th><th/></tr></thead><tbody>
      {users.map(u => <tr key={u.id}><td><button className="ai-text-button" onClick={() => void open(u)}>{u.name || u.email}</button><small>{u.email} · #{u.id}{u.has_account ? "" : " · هنوز حسابی ندارد (اعتبار اولیه را با اولین استفاده می‌گیرد)"}</small></td>
        <td style={{ direction: "ltr", textAlign: "left", color: u.balance <= 0 && !u.unlimited ? "#d33" : undefined }}>{fmt(u.balance)}</td><td style={{ direction: "ltr", textAlign: "left" }}>{fmt(u.used_total)}</td><td style={{ direction: "ltr", textAlign: "left" }}>{fmt(u.granted_total)}</td>
        <td><input type="checkbox" checked={u.unlimited} onChange={e => void act(() => request(`/credits/users/${encodeURIComponent(u.id)}/unlimited`, json({ unlimited: e.target.checked }, "PUT")), "ذخیره شد.")}/></td>
        <td><button onClick={() => void adjust(u)}>کم / زیاد کردن</button></td></tr>)}</tbody></table></div>

    <h2>بسته‌های خرید</h2>
    <div className="ai-table-wrap"><table><thead><tr><th>شناسه</th><th>عنوان</th><th>اعتبار</th><th>قیمت (تومان)</th><th>فعال</th><th/></tr></thead><tbody>
      {packages.map((p, i) => <tr key={p.id}><td><code>{p.id}</code></td>
        <td><input value={p.title} onChange={e => setPackages(packages.map((x, j) => j === i ? { ...x, title: e.target.value } : x))}/></td>
        <td><input type="number" min={1} value={p.credits} onChange={e => setPackages(packages.map((x, j) => j === i ? { ...x, credits: Number(e.target.value) } : x))}/></td>
        <td><input type="number" min={0} value={p.price} onChange={e => setPackages(packages.map((x, j) => j === i ? { ...x, price: Number(e.target.value) } : x))}/></td>
        <td><input type="checkbox" checked={p.active} onChange={e => setPackages(packages.map((x, j) => j === i ? { ...x, active: e.target.checked } : x))}/></td>
        <td><button onClick={() => void act(() => request("/credits/packages", json(p, "PUT")), "بسته ذخیره شد.")}>ذخیره</button></td></tr>)}</tbody></table></div>
    <button onClick={() => { const id = (prompt("شناسهٔ بستهٔ جدید (انگلیسی، مثل p4):") || "").trim(); if (id) setPackages([...packages, { id, title: "بستهٔ جدید", credits: 1000000, price: 0, currency: "IRT", active: false, sort: packages.length + 1 }]); }}>افزودن بسته</button>

    <h2>سفارش‌ها</h2>
    <p className="eg-muted">درگاه پرداخت هنوز وصل نشده است: پس از دریافت پول، «تأیید پرداخت» اعتبار را یک‌بار به کاربر اضافه می‌کند (تأیید دوباره اثری ندارد).</p>
    <div className="ai-table-wrap"><table><thead><tr><th>زمان</th><th>کاربر</th><th>اعتبار</th><th>وضعیت</th><th/></tr></thead><tbody>
      {orders.map(o => <tr key={o.id}><td>{new Date(o.created_at).toLocaleString("fa-IR")}</td><td>#{o.user_id}</td><td style={{ direction: "ltr", textAlign: "left" }}>{fmt(o.credits)}</td><td>{o.status === "paid" ? "پرداخت‌شده" : o.status === "pending" ? "در انتظار" : "لغوشده"}</td>
        <td>{o.status === "pending" ? <button onClick={() => void act(() => request(`/credits/orders/${o.id}/paid`, json({})), "اعتبار به کاربر اضافه شد.")}>تأیید پرداخت</button> : null}</td></tr>)}</tbody></table></div>

    {detail ? <div className="ai-sheet-shade" onClick={() => setDetail(null)}><section className="ai-sheet" dir="rtl" role="dialog" aria-modal="true" aria-label="جزئیات اعتبار" onClick={e => e.stopPropagation()}>
      <button className="ai-close" aria-label="بستن" onClick={() => setDetail(null)}>×</button>
      <h2>{detail.label}</h2><p>مانده: <b>{detail.data.account.unlimited ? "نامحدود" : fmt(detail.data.account.balance)}</b> · مصرف‌شده: {fmt(detail.data.account.used_total)}</p>
      <h3>ویدیو / پروژه</h3><ul>{detail.data.projects.map(p => <li key={p.id}><code>{p.kind || "project"} {p.id.slice(0, 8)}</code> — {fmt(p.credits)} اعتبار ({fmt(p.calls)} فراخوانی)</li>)}</ul>
      <h3>چت</h3><ul>{detail.data.chats.map(c => <li key={c.id}><code>{c.id.slice(0, 8)}</code> — {fmt(c.credits)} اعتبار ({fmt(c.calls)} فراخوانی)</li>)}</ul>
      <h3>تراکنش‌ها</h3><div className="ai-table-wrap"><table><thead><tr><th>زمان</th><th>نوع</th><th>مدل</th><th>ورودی</th><th>خروجی</th><th>تغییر</th><th>مانده</th></tr></thead><tbody>
        {detail.data.items.map(e => <tr key={e.id}><td>{new Date(e.at).toLocaleString("fa-IR")}</td><td>{e.kind}{e.note ? ` · ${e.note}` : ""}</td><td>{e.model || "—"}<small>{e.route}</small></td><td>{fmt(e.input_tokens)}</td><td>{fmt(e.output_tokens)}</td><td style={{ direction: "ltr" }}>{fmt(e.amount)}</td><td style={{ direction: "ltr" }}>{fmt(e.balance_after)}</td></tr>)}</tbody></table></div>
    </section></div> : null}
  </section>;
}
