import React from "react";
import { api, CreditOrder, CreditsBreakdown, CreditsState, CreditsUsage, CreditGroup } from "./api";
import { friendlyError } from "./ui";
import "./styles/credits.css";

export const fmt = (value: number | null | undefined) => value === null || value === undefined ? "—" : Math.round(value).toLocaleString("fa-IR");
const KIND: Record<string, string> = { motion: "موشن‌گرافیک", talking: "تالکینگ", long_video: "تحلیل ویدیوی بلند", project: "پروژه" };
const ENTRY: Record<string, string> = { usage: "مصرف", initial: "اعتبار اولیه", grant: "هدیه", purchase: "خرید", admin: "تغییر دستی مدیر", refund: "بازگشت" };
const STATUS: Record<string, string> = { pending: "در انتظار پرداخت", paid: "پرداخت‌شده", cancelled: "لغوشده" };
const when = (iso: string) => { const d = new Date(iso); return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("fa-IR"); };
const PAGE = 30;

export function Breakdown({ id }: { id: string }) {
  const [data, setData] = React.useState<CreditsBreakdown | null>(null);
  React.useEffect(() => { void api.creditsProject(id).then(setData).catch(() => setData(null)); }, [id]);
  if (!data) return <small>در حال بارگذاری…</small>;
  return <table><thead><tr><th>مدل</th><th className="num">فراخوانی</th><th className="num">توکن ورودی</th><th className="num">توکن خروجی</th><th className="num">توکن کش</th><th className="num">اعتبار</th></tr></thead>
    <tbody>{data.by_model.map(row => <tr key={row.key || "-"}><td>{row.key || "—"}</td><td className="num">{fmt(row.calls)}</td><td className="num">{fmt(row.input_tokens)}</td><td className="num">{fmt(row.output_tokens)}</td><td className="num">{fmt(row.cache_tokens)}</td><td className="num">{fmt(row.credits)}</td></tr>)}</tbody>
    <tfoot><tr><td colSpan={5}><b>جمع</b></td><td className="num"><b>{fmt(data.total)}</b></td></tr></tfoot></table>;
}

function Groups({ rows, title, project }: { rows: CreditGroup[]; title: string; project?: boolean }) {
  const [open, setOpen] = React.useState<string | null>(null);
  if (!rows.length) return <section className="credits-card"><h2>{title}</h2><small>هنوز مصرفی ثبت نشده است.</small></section>;
  return <section className="credits-card"><h2>{title}</h2><div className="credits-table-wrap"><table><thead><tr><th>{project ? "ویدیو / پروژه" : "چت"}</th><th>آخرین مصرف</th><th className="num">فراخوانی</th><th className="num">توکن ورودی</th><th className="num">توکن خروجی</th><th className="num">اعتبار مصرف‌شده</th></tr></thead>
    <tbody>{rows.map(row => <React.Fragment key={row.id}>
      <tr><td>{project ? <button className="linkish" onClick={() => setOpen(open === row.id ? null : row.id)}>{row.title || `${KIND[row.kind || "project"] || "پروژه"} ${row.id.slice(0, 8)}`}</button> : (row.title || row.id.slice(0, 8))}{project && row.kind ? <small>{KIND[row.kind] || row.kind}</small> : null}</td>
        <td>{when(row.last_at)}</td><td className="num">{fmt(row.calls)}</td><td className="num">{fmt(row.input_tokens)}</td><td className="num">{fmt(row.output_tokens)}</td><td className="num"><b>{fmt(row.credits)}</b></td></tr>
      {project && open === row.id ? <tr><td colSpan={6}><Breakdown id={row.id}/></td></tr> : null}
    </React.Fragment>)}</tbody></table></div></section>;
}

export default function CreditsPage() {
  const [state, setState] = React.useState<CreditsState | null>(null);
  const [usage, setUsage] = React.useState<CreditsUsage | null>(null);
  const [orders, setOrders] = React.useState<CreditOrder[]>([]);
  const [page, setPage] = React.useState(1);
  const [notice, setNotice] = React.useState("");
  const [error, setError] = React.useState("");
  const load = React.useCallback(() => {
    void api.creditsMe().then(setState).catch(e => setError(friendlyError(e, "load credits")));
    void api.creditsUsage(page, PAGE).then(setUsage).catch(e => setError(friendlyError(e, "load credit usage")));
    void api.creditsOrders().then(r => setOrders(r.items)).catch(() => {});
  }, [page]);
  React.useEffect(load, [load]);
  async function order(id: string) {
    setError(""); setNotice("");
    try { const created = await api.creditsOrder(id); setNotice(created.message); load(); } catch (e) { setError(friendlyError(e, "create the order")); }
  }
  return <main className="eg-page credits-page">
    <header><h1>اعتبار و مصرف</h1><small>هر درخواست به مدل هوش مصنوعی از اعتبار شما کم می‌کند. واحد اعتبار «توکن وزن‌دار» است: توکن خروجی گران‌تر از ورودی حساب می‌شود و هر مدل ضریب خودش را دارد.</small></header>
    {error ? <div role="alert" className="credits-alert">{error}</div> : null}
    {notice ? <div role="status" className="credits-card">{notice}</div> : null}
    {state ? <section className="credits-card"><div className="credits-balance">
      <div><small>مانده اعتبار</small><span className="big" style={state.balance <= 0 && !state.unlimited ? { color: "#d33" } : undefined}>{state.unlimited ? "نامحدود" : fmt(state.balance)}</span></div>
      <div><small>مصرف‌شده</small><b>{fmt(state.used_total)}</b></div><div><small>مجموع اعتبار دریافتی</small><b>{fmt(state.granted_total)}</b></div></div>
      {state.exhausted ? <p className="credits-alert">اعتبار شما تمام شده است؛ درخواست جدید پذیرفته نمی‌شود. کارهایی که در حال اجرا هستند تا پایان ادامه می‌یابند. برای ادامه، اعتبار بخرید.</p> : null}
    </section> : <small>در حال بارگذاری…</small>}
    {state?.packages.length ? <section><h2>خرید / افزایش اعتبار</h2><div className="credits-packages">{state.packages.map(p => <div className="credits-card" key={p.id}>
      <b>{p.title}</b><div>{fmt(p.credits)} اعتبار</div><small>{p.price > 0 ? `${p.price.toLocaleString("fa-IR")} ${p.currency === "IRT" ? "تومان" : p.currency}` : "قیمت به‌زودی اعلام می‌شود"}</small>
      <button className="btn btn-sm btn-primary" style={{ marginTop: 8 }} onClick={() => void order(p.id)}>ثبت سفارش</button></div>)}</div>
      <small>پرداخت آنلاین هنوز فعال نیست؛ سفارش ثبت می‌شود و پس از تأیید پرداخت توسط مدیر، اعتبار اضافه می‌شود.</small></section> : null}
    {usage ? <>
      <Groups rows={usage.projects} title="مصرف به‌تفکیک ویدیو / پروژه" project/>
      <Groups rows={usage.chats} title="مصرف به‌تفکیک چت"/>
      <section className="credits-card"><h2>آخرین تراکنش‌ها</h2><div className="credits-table-wrap"><table><thead><tr><th>زمان</th><th>نوع</th><th>مدل / مرحله</th><th className="num">ورودی</th><th className="num">خروجی</th><th className="num">تغییر اعتبار</th><th className="num">مانده</th></tr></thead>
        <tbody>{usage.items.map(e => <tr key={e.id}><td>{when(e.at)}</td><td>{ENTRY[e.kind] || e.kind}{e.note ? <small>{e.note}</small> : null}</td><td>{e.model || "—"}{e.route ? <small>{e.route}</small> : null}</td>
          <td className="num">{fmt(e.input_tokens)}</td><td className="num">{fmt(e.output_tokens)}</td><td className="num">{e.amount > 0 ? "+" : ""}{fmt(e.amount)}</td><td className="num">{fmt(e.balance_after)}</td></tr>)}</tbody></table></div>
        <div className="credits-pager"><button disabled={page <= 1} onClick={() => setPage(page - 1)}>قبلی</button><span>{page.toLocaleString("fa-IR")} / {Math.max(1, Math.ceil(usage.total / PAGE)).toLocaleString("fa-IR")}</span><button disabled={page * PAGE >= usage.total} onClick={() => setPage(page + 1)}>بعدی</button></div></section>
    </> : null}
    {orders.length ? <section className="credits-card"><h2>سفارش‌ها</h2><table><thead><tr><th>زمان</th><th className="num">اعتبار</th><th>وضعیت</th></tr></thead><tbody>{orders.map(o => <tr key={o.id}><td>{when(o.created_at)}</td><td className="num">{fmt(o.credits)}</td><td>{STATUS[o.status] || o.status}</td></tr>)}</tbody></table></section> : null}
  </main>;
}
