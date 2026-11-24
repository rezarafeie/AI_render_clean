import React from "react";
import { api, CreditOrder, CreditsBreakdown, CreditsState, CreditsUsage, CreditGroup } from "./api";
import { friendlyError } from "./ui";
import "./styles/credits.css";

/** Full number with Persian digits. */
export const fmt = (value: number | null | undefined) => value === null || value === undefined ? "—" : Math.round(value).toLocaleString("fa-IR");
/** Short form for tight places: ۵٫۹ میلیون / ۱۲۰ هزار. */
export function short(value: number): string {
  const sign = value < 0 ? "-" : ""; const n = Math.abs(value);
  if (n >= 1_000_000) return sign + (Math.round(n / 100_000) / 10).toLocaleString("fa-IR") + " میلیون";
  if (n >= 10_000) return sign + Math.round(n / 1000).toLocaleString("fa-IR") + " هزار";
  return sign + Math.round(n).toLocaleString("fa-IR");
}
const KIND: Record<string, string> = { motion: "موشن‌گرافیک", talking: "تالکینگ", long_video: "تحلیل ویدیوی بلند", project: "پروژه" };
const ENTRY: Record<string, string> = { usage: "مصرف", initial: "اعتبار اولیه", grant: "هدیه", purchase: "خرید اعتبار", admin: "تغییر توسط مدیر", refund: "بازگشت" };
const STATUS: Record<string, string> = { pending: "در انتظار پرداخت", paid: "پرداخت‌شده", cancelled: "لغوشده" };
const when = (iso: string) => { const d = new Date(iso); return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("fa-IR", { dateStyle: "medium", timeStyle: "short" }); };
const PAGE = 20;
type Tab = "buy" | "usage" | "log";

export function Breakdown({ id }: { id: string }) {
  const [data, setData] = React.useState<CreditsBreakdown | null>(null);
  React.useEffect(() => { void api.creditsProject(id).then(setData).catch(() => setData(null)); }, [id]);
  if (!data) return <div className="cp-detail"><small>در حال بارگذاری…</small></div>;
  return <div className="cp-detail"><table><thead><tr><th>مدل</th><th className="n">فراخوانی</th><th className="n">ورودی</th><th className="n">خروجی</th><th className="n">اعتبار</th></tr></thead>
    <tbody>{data.by_model.map(row => <tr key={row.key || "-"}><td>{row.key || "—"}</td><td className="n">{fmt(row.calls)}</td><td className="n">{short(row.input_tokens)}</td><td className="n">{short(row.output_tokens)}</td><td className="n">{short(row.credits)}</td></tr>)}</tbody></table></div>;
}

function Groups({ rows, title, project }: { rows: CreditGroup[]; title: string; project?: boolean }) {
  const [open, setOpen] = React.useState<string | null>(null);
  return <section className="cp-card"><h2>{title}</h2>
    {!rows.length ? <div className="cp-empty">هنوز مصرفی ثبت نشده است.</div> : rows.map(row => {
      const name = row.title || (project ? `${KIND[row.kind || "project"] || "پروژه"} ${row.id.slice(0, 6)}` : `چت ${row.id.slice(0, 6)}`);
      const inner = <><div className="main"><b>{name}</b><small>{project && row.kind ? `${KIND[row.kind] || row.kind} · ` : ""}{fmt(row.calls)} فراخوانی · {when(row.last_at)}</small></div><span className="amt">{short(row.credits)}</span></>;
      return <React.Fragment key={row.id}><div className="cp-row">{project ? <button className="row" onClick={() => setOpen(open === row.id ? null : row.id)}>{inner}</button> : inner}</div>{project && open === row.id ? <Breakdown id={row.id}/> : null}</React.Fragment>;
    })}</section>;
}

/* Credits per finished job, from the ledger (14–24 Nov 2026, 32 Pro runs, 23 motion films, 7 talking reels, 15 Medium chats; failed runs left out):
   talking median ~260K (p75 ~290K, up to ~1M), motion/Vox film median ~0.9M (p75 ~1.1M, heavy revisions 3–5M; the prompt cache of 24 Nov should lower it),
   Medium median ~0.4M (p75 ~1.3M, up to 5.5M), Pro median ~0.4M (p75 ~0.95M, up to 7.5M). "typical" is the conservative figure the pack counts divide by. */
type EngineCost = { id: string; name: string; typical: number; min: number; max: number; tail?: string; note: string };
const ENGINE_COST: EngineCost[] = [
  { id: "edit", name: "زیرنویس، برش و دوبله", typical: 100_000, min: 50_000, max: 150_000, note: "کارهای سادهٔ Lite روی ویدیوی خودتان" },
  { id: "talking", name: "ریلز صحبتی", typical: 300_000, min: 200_000, max: 400_000, tail: "با اصلاح‌های زیاد تا ۱ میلیون", note: "تحلیل گفتار، تدوین، زیرنویس و B-roll (Lite)" },
  { id: "film", name: "فیلم موشن / ووکس / تبلیغ", typical: 900_000, min: 500_000, max: 1_500_000, tail: "با اصلاح‌های زیاد تا ۳ میلیون", note: "موشن‌گرافیک، مستند ووکس، معرفی محصول و روایی (Lite)" },
  { id: "medium", name: "Medium", typical: 1_200_000, min: 300_000, max: 2_000_000, tail: "کارهای چندمرحله‌ای سنگین تا ۵ میلیون", note: "چند مرحله با برنامه‌ای که اول تأیید می‌کنید" },
  { id: "pro", name: "Pro", typical: 1_000_000, min: 300_000, max: 1_500_000, tail: "پروژه‌های سنگین تا ۷ میلیون", note: "فیلم سفارشی و پروژه‌های خاص" },
  { id: "claude", name: "Claude", typical: 10_000_000, min: 8_000_000, max: 15_000_000, note: "خودِ Claude بدون ابزارهای استودیو (آزمایشی)" },
];
/** «۲۰۰ تا ۴۰۰ هزار», «۵۰۰ هزار تا ۱٫۵ میلیون», «۸ تا ۱۵ میلیون». */
function rangeText(min: number, max: number): string {
  const unit = (n: number) => n >= 1_000_000 ? "میلیون" : "هزار";
  const num = (n: number) => (n >= 1_000_000 ? Math.round(n / 100_000) / 10 : Math.round(n / 1000)).toLocaleString("fa-IR");
  return unit(min) === unit(max) ? `${num(min)} تا ${num(max)} ${unit(max)}` : `${num(min)} ${unit(min)} تا ${num(max)} ${unit(max)}`;
}
/** Position on a log scale from 30 thousand to 20 million, in percent. */
const scale = (n: number) => Math.max(0, Math.min(100, (Math.log10(n) - Math.log10(30_000)) / (Math.log10(20_000_000) - Math.log10(30_000)) * 100));
function count(n: number): string {
  if (n < 1) return "کمتر از ۱";
  const v = n >= 20 ? Math.floor(n / 5) * 5 : Math.floor(n);
  return v.toLocaleString("fa-IR");
}
const PACK_USES = ["talking", "film", "pro"];

export default function CreditsPage() {
  const [state, setState] = React.useState<CreditsState | null>(null);
  const [usage, setUsage] = React.useState<CreditsUsage | null>(null);
  const [orders, setOrders] = React.useState<CreditOrder[]>([]);
  const [page, setPage] = React.useState(1);
  const [tab, setTab] = React.useState<Tab>("usage");
  const [banner, setBanner] = React.useState<{ tone: "ok" | "warn" | "error"; text: string } | null>(null);
  const [buying, setBuying] = React.useState("");
  const tabChosen = React.useRef(false);
  const load = React.useCallback(() => {
    void api.creditsMe().then(value => { setState(value); if (!tabChosen.current) { tabChosen.current = true; if (value.exhausted) setTab("buy"); } }).catch(e => setBanner({ tone: "error", text: friendlyError(e, "load credits") }));
    void api.creditsUsage(page, PAGE).then(setUsage).catch(e => setBanner({ tone: "error", text: friendlyError(e, "load credit usage") }));
    void api.creditsOrders().then(r => setOrders(r.items)).catch(() => {});
  }, [page]);
  React.useEffect(load, [load]);
  // Back from the payment gateway: the server asks the gateway itself (the address is only a hint) and adds the credits if the payment is verified.
  React.useEffect(() => {
    const query = new URLSearchParams(window.location.search); const order = query.get("order");
    if (!query.get("pay") || !order) return;
    void api.creditsCheck(order).then(result => {
      setBanner(result.status === "paid" ? { tone: "ok", text: "پرداخت تأیید شد و اعتبار به حساب شما اضافه شد." } : { tone: "warn", text: "پرداخت هنوز تأیید نشده است. اگر پول از حساب شما کم شده، چند دقیقه بعد این صفحه را دوباره باز کنید." });
      window.history.replaceState(null, "", "/credits"); load();
    }).catch(e => setBanner({ tone: "error", text: friendlyError(e, "check the payment") }));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  React.useEffect(() => { if (banner?.tone === "ok") { const t = window.setTimeout(() => setBanner(null), 8000); return () => window.clearTimeout(t); } }, [banner]);
  async function buy(id: string) {
    setBuying(id); setBanner(null);
    try { const created = await api.creditsOrder(id); if (created.payment_url) { window.location.href = created.payment_url; return; } setBanner({ tone: "warn", text: created.message }); load(); }
    catch (e) { setBanner({ tone: "error", text: friendlyError(e, "create the order") }); }
    finally { setBuying(""); }
  }
  const paid = orders.filter(o => o.status === "paid").length;
  const packs = state?.packages || [];
  const best = packs.length > 2 ? packs[1].id : "";
  return <main className="eg-page cp">
    <header><h1>اعتبار و مصرف</h1><p className="cp-sub">هر درخواست به هوش مصنوعی از اعتبار شما کم می‌کند. اعتبار بر پایه‌ی توکن است: توکن خروجی گران‌تر از ورودی حساب می‌شود و هر مدل ضریب خودش را دارد.</p></header>
    {state ? <section className="cp-hero">
      <div><div className="label">مانده اعتبار</div><div className="num" data-empty={state.exhausted || undefined}>{state.unlimited ? "نامحدود" : fmt(state.balance)}</div></div>
      <div className="cp-stats"><div><b>{short(state.used_total)}</b><span>مصرف‌شده</span></div><div><b>{short(state.granted_total)}</b><span>مجموع دریافتی</span></div></div>
    </section> : <div className="cp-empty">در حال بارگذاری…</div>}
    {state?.exhausted ? <div className="cp-alert" data-tone="error"><span>اعتبار شما تمام شده است؛ درخواست جدید پذیرفته نمی‌شود. کارهای در حال اجرا تا پایان ادامه می‌یابند.</span></div> : null}
    {banner ? <div className="cp-alert" data-tone={banner.tone} role={banner.tone === "error" ? "alert" : "status"}><span>{banner.text}</span><button aria-label="بستن" onClick={() => setBanner(null)}>×</button></div> : null}
    <nav className="cp-tabs" aria-label="بخش‌های اعتبار">
      {([["usage", "مصرف"], ["buy", "خرید اعتبار"], ["log", "تراکنش‌ها"]] as const).map(([id, label]) => <button key={id} aria-pressed={tab === id} onClick={() => setTab(id)}>{label}</button>)}
    </nav>

    {tab === "buy" ? <>
      <div className="cp-packs">{packs.map(p => {
        const base = packs.find(x => x.price > 0 && x.credits > 0);
        const per = p.price > 0 ? p.price / (p.credits / 1_000_000) : 0;
        const basePer = base ? base.price / (base.credits / 1_000_000) : 0;
        const off = per && basePer && per < basePer ? Math.round((1 - per / basePer) * 100) : 0;
        return <div className="cp-pack" key={p.id} data-best={p.id === best || undefined}>
          <div className="cp-pack-head"><span className="name">{p.title}</span>{p.id === best ? <span className="tag">پرفروش</span> : off ? <span className="tag soft">{off.toLocaleString("fa-IR")}٪ به‌صرفه‌تر</span> : null}</div>
          <div className="cp-pack-amount"><span className="big">{short(p.credits)}</span><span className="unit">اعتبار</span></div>
          <div className="cp-pack-price"><span>{p.price > 0 ? <><b>{p.price.toLocaleString("fa-IR")}</b> {p.currency === "IRT" ? "تومان" : p.currency}</> : "به‌زودی"}</span>
            {per ? <small>هر میلیون اعتبار {Math.round(per).toLocaleString("fa-IR")} تومان</small> : null}</div>
          <div className="cp-uses" aria-label="تقریباً به اندازهٔ">{PACK_USES.map(id => { const e = ENGINE_COST.find(x => x.id === id)!; const n = p.credits / e.typical;
            return <div key={id} data-low={n < 1 || undefined}><b>{count(n)}</b><span>{e.id === "pro" ? "اجرای Pro" : e.name}</span></div>; })}</div>
          <button disabled={p.price <= 0 || buying !== ""} onClick={() => void buy(p.id)}>{buying === p.id ? "در حال انتقال…" : p.price > 0 ? "خرید" : "به‌زودی"}</button>
        </div>; })}</div>
      <section className="cp-card cp-engines"><div className="cp-engines-head"><h2>مصرف حدودی هر کار</h2>
        <p className="cp-sub">بر پایهٔ مصرف واقعی کارهای ۱۰ روز اخیر. مقدار دقیق به طول ویدیو، تعداد اصلاح‌ها و پیچیدگی کار بستگی دارد.</p></div>
        <div className="cp-scale" aria-hidden="true"><span style={{ insetInlineStart: `${scale(100_000)}%` }}>۱۰۰ هزار</span><span style={{ insetInlineStart: `${scale(1_000_000)}%` }}>۱ میلیون</span><span style={{ insetInlineStart: `${scale(10_000_000)}%` }}>۱۰ میلیون</span></div>
        {ENGINE_COST.map(e => <div className="cp-eng" key={e.id}>
          <div className="cp-eng-text"><b>{e.name}</b><small>{e.note}</small></div>
          <div className="cp-eng-bar" aria-hidden="true"><i style={{ insetInlineStart: `${scale(e.min)}%`, width: `${Math.max(2, scale(e.max) - scale(e.min))}%` }}/><em style={{ insetInlineStart: `${scale(e.typical)}%` }}/></div>
          <div className="cp-eng-amt"><b>{rangeText(e.min, e.max)}</b>{e.tail ? <small>{e.tail}</small> : null}</div>
        </div>)}
      </section>
      <p className="cp-note">پرداخت از طریق درگاه امن رفیعی‌پی انجام می‌شود و بعد از تأیید، اعتبار خودکار به حساب شما اضافه می‌شود.</p>
      {orders.length ? <section className="cp-card"><h2>سفارش‌های من{paid ? ` · ${fmt(paid)} پرداخت‌شده` : ""}</h2>{orders.slice(0, 8).map(o => <div className="cp-row" key={o.id}><div className="main"><b>{short(o.credits)} اعتبار</b><small>{when(o.created_at)}</small></div><span className="amt" style={{ fontWeight: 500, color: o.status === "paid" ? "var(--success)" : undefined }}>{STATUS[o.status] || o.status}</span></div>)}</section> : null}
    </> : null}

    {tab === "usage" ? (usage ? <><Groups rows={usage.projects} title="به‌تفکیک ویدیو و پروژه" project/><Groups rows={usage.chats} title="به‌تفکیک چت"/></> : <div className="cp-empty">در حال بارگذاری…</div>) : null}

    {tab === "log" ? (usage ? <section className="cp-card">
      {usage.items.map(e => <div className="cp-row" key={e.id}><div className="main"><b>{ENTRY[e.kind] || e.kind}{e.model && e.kind === "usage" ? ` · ${e.model.replace(/^custom:/, "").replace(/#.*/, "")}` : ""}</b><small>{when(e.at)}{e.route && e.kind === "usage" ? ` · ${e.route}` : ""}{e.note ? ` · ${e.note}` : ""}</small></div>
        <div style={{ textAlign: "left", display: "grid", gap: 2 }}><span className="amt" data-plus={e.amount > 0 || undefined}>{e.amount > 0 ? "+" : ""}{short(e.amount)}</span><small style={{ direction: "ltr" }}>{short(e.balance_after)}</small></div></div>)}
      <div className="cp-pager"><button disabled={page <= 1} onClick={() => setPage(page - 1)}>قبلی</button><span>{page.toLocaleString("fa-IR")} / {Math.max(1, Math.ceil(usage.total / PAGE)).toLocaleString("fa-IR")}</span><button disabled={page * PAGE >= usage.total} onClick={() => setPage(page + 1)}>بعدی</button></div>
    </section> : <div className="cp-empty">در حال بارگذاری…</div>) : null}
  </main>;
}
