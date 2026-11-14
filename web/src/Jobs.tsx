import React from "react";
import { NavLink } from "react-router-dom";
import { api, LocalizeSummary, ProjectCard, TalkingReelSummary } from "./api";
import { useJobCache } from "./JobCache";
import { AuthenticatedMedia } from "./AuthenticatedMedia";
import { Icon } from "./EditorShell";
import { friendlyError } from "./ui";
import { displayTitle, parseTime } from "./format";
import "./styles/projects.css";

type Status = "running" | "needs_input" | "failed" | "ready" | "draft";
type Item = { key: string; title: string; kind: string; kindLabel: string; status: Status; updated: number; to: string; thumb?: string | null; chat: boolean };

const STATUS: Record<Status, string> = { running: "در حال ساخت", needs_input: "منتظر شما", failed: "ناموفق", ready: "آماده", draft: "بدون خروجی" };
const KIND_ICON: Record<string, "film" | "globe" | "mic2" | "video" | "motion" | "wand" | "thinking"> = { motion: "motion", talking: "mic2", localize: "globe", edit: "wand", chat: "thinking" };
const TYPE_ORDER = ["motion", "talking", "localize", "edit", "chat"];
const TYPE_LABEL: Record<string, string> = { motion: "موشن‌گرافیک", talking: "تدوین صحبتی", localize: "دوبله و زیرنویس", edit: "تدوین هوشمند", chat: "گفتگو" };
const dateText = (time: number) => {
  if (!time) return "";
  const diff = Date.now() - time;
  if (diff < 45_000) return "همین حالا";
  const rtf = new Intl.RelativeTimeFormat("fa", { numeric: "auto" });
  if (diff < 3_600_000) return rtf.format(-Math.round(diff / 60_000), "minute");
  if (diff < 86_400_000) return rtf.format(-Math.round(diff / 3_600_000), "hour");
  if (diff < 7 * 86_400_000) return rtf.format(-Math.round(diff / 86_400_000), "day");
  return new Date(time).toLocaleDateString("fa-IR", { month: "long", day: "numeric" });
};
function legacyStatus(status: string): Status {
  const value = (status || "").toLowerCase();
  if (["done", "ready", "completed"].includes(value)) return "ready";
  if (["error", "failed"].includes(value)) return "failed";
  if (["paused", "awaiting_confirmation", "awaiting_input"].includes(value)) return "needs_input";
  if (["rendering", "running", "processing", "generating", "analyzing", "queued", "transcribing"].includes(value)) return "running";
  return "draft";
}

export default function Projects() {
  const { jobs, loading, error, refetch } = useJobCache();
  const [cards, setCards] = React.useState<ProjectCard[] | null>(null);
  const [localize, setLocalize] = React.useState<LocalizeSummary[]>([]);
  const [talking, setTalking] = React.useState<TalkingReelSummary[]>([]);
  const [overviewError, setOverviewError] = React.useState<unknown>(null);
  const [query, setQuery] = React.useState("");
  const [type, setType] = React.useState("all");
  const [status, setStatus] = React.useState<"all" | Status>("all");
  const [sort, setSort] = React.useState("recent");

  const load = React.useCallback(async () => {
    const results = await Promise.allSettled([api.studioProjectsOverview(), api.listLocalize(), api.listTalkingReels()]);
    if (results[0].status === "fulfilled") { setCards(results[0].value.items); setOverviewError(null); } else setOverviewError(results[0].reason);
    if (results[1].status === "fulfilled") setLocalize(results[1].value);
    if (results[2].status === "fulfilled") setTalking(results[2].value);
  }, []);
  React.useEffect(() => { void refetch(); void load(); }, [refetch, load]);

  // Every card is a chat (that is where a project lives and is edited). Older videos that no chat points to are listed too, opening in the studio.
  const items = React.useMemo(() => {
    const out: Item[] = (cards || []).map(card => ({ key: `chat-${card.id}`, title: card.title || "بدون عنوان", kind: card.kind in TYPE_LABEL ? card.kind : "edit", kindLabel: TYPE_LABEL[card.kind] || card.kind_label,
      status: card.status, updated: parseTime(card.updated_at || "") || 0, to: `/studio/${card.id}`, thumb: card.thumb ? `/api${card.thumb}` : null, chat: true }));
    const linkedRefs = new Set((cards || []).flatMap(card => card.refs || []));
    for (const item of talking) if (!linkedRefs.has(item.job_id)) out.push({ key: `talking-${item.job_id}`, title: item.name || item.hook || "ویدیوی صحبتی", kind: "talking", kindLabel: TYPE_LABEL.talking, status: legacyStatus(item.status), updated: item.updated_at * 1000, chat: false,
      to: `/studio?legacy=talking:${item.job_id}&title=${encodeURIComponent(item.name || item.hook || "")}` });
    for (const item of localize) if (!linkedRefs.has(item.id)) out.push({ key: `localize-${item.id}`, title: item.title || item.name || "ویدیوی دوبله‌شده", kind: "localize", kindLabel: TYPE_LABEL.localize, status: legacyStatus(item.status), updated: (item.updated_at || item.created_at || 0) * 1000, chat: false,
      to: `/studio?legacy=localize:${item.id}&title=${encodeURIComponent(item.title || item.name || "")}` });
    const talkingIds = new Set(talking.map(item => item.job_id));
    for (const job of jobs) if (!linkedRefs.has(job.id) && !talkingIds.has(job.id)) {
      const active = job.render.status !== "idle" ? job.render.status : job.generate.status;
      const title = job.raw_name || job.plan?.title || "ویرایش ویدیو";
      out.push({ key: `job-${job.id}`, title, kind: "edit", kindLabel: TYPE_LABEL.edit, status: legacyStatus(active), updated: 0, chat: false, to: `/studio?legacy=motion:${job.id}&title=${encodeURIComponent(title)}` });
    }
    return out;
  }, [cards, talking, localize, jobs]);

  const matching = (item: Item) => !query.trim() || `${item.title} ${item.kindLabel}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase());
  const shown = React.useMemo(() => items.filter(item => matching(item) && (type === "all" || item.kind === type) && (status === "all" || item.status === status))
    .sort((a, b) => sort === "oldest" ? a.updated - b.updated : b.updated - a.updated), [items, query, type, status, sort]); // eslint-disable-line react-hooks/exhaustive-deps
  const typeCounts = React.useMemo(() => { const c: Record<string, number> = {}; for (const item of items) if (matching(item) && (status === "all" || item.status === status)) { c[item.kind] = (c[item.kind] || 0) + 1; c.all = (c.all || 0) + 1; } return c; }, [items, query, status]); // eslint-disable-line react-hooks/exhaustive-deps
  const statusCounts = React.useMemo(() => { const c: Record<string, number> = {}; for (const item of items) if (matching(item) && (type === "all" || item.kind === type)) { c[item.status] = (c[item.status] || 0) + 1; c.all = (c.all || 0) + 1; } return c; }, [items, query, type]); // eslint-disable-line react-hooks/exhaustive-deps
  const waiting = cards === null && loading;

  return <div className="page pj">
    <header className="pj-head"><div><h1>پروژه‌ها</h1><p>{items.length ? `${items.length.toLocaleString("fa-IR")} پروژه · ` : ""}هر پروژه به چت خودش وصل است؛ از همان‌جا ادامه بده.</p></div>
      <NavLink className="btn" to="/studio"><Icon name="edit" size={16}/>ویرایش جدید</NavLink></header>
    <div className="pj-tools">
      <label className="pj-search"><span className="sr-only">جست‌وجوی پروژه‌ها</span><Icon name="search" size={16}/><input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="جست‌وجوی پروژه‌ها"/></label>
      <select value={status} onChange={event => setStatus(event.target.value as "all" | Status)} aria-label="وضعیت">
        <option value="all">همه وضعیت‌ها ({(statusCounts.all || 0).toLocaleString("fa-IR")})</option>
        {(Object.keys(STATUS) as Status[]).filter(s => statusCounts[s]).map(s => <option key={s} value={s}>{STATUS[s]} ({statusCounts[s].toLocaleString("fa-IR")})</option>)}
      </select>
      <select value={sort} onChange={event => setSort(event.target.value)} aria-label="مرتب‌سازی"><option value="recent">تازه‌ترین</option><option value="oldest">قدیمی‌ترین</option></select>
    </div>
    <div className="pj-types" role="group" aria-label="نوع تدوین">
      <button aria-pressed={type === "all"} onClick={() => setType("all")}>همه<i>{(typeCounts.all || 0).toLocaleString("fa-IR")}</i></button>
      {TYPE_ORDER.filter(k => typeCounts[k] || type === k).map(k => <button key={k} aria-pressed={type === k} onClick={() => setType(k)}><Icon name={KIND_ICON[k]} size={14}/>{TYPE_LABEL[k]}<i>{(typeCounts[k] || 0).toLocaleString("fa-IR")}</i></button>)}
    </div>
    {waiting ? <ul className="pj-grid" aria-busy="true">{Array.from({ length: 8 }, (_, i) => <li key={i} className="pj-card"><span className="pj-thumb skeleton"/><span className="skeleton" style={{ height: 14, width: "70%" }}/></li>)}</ul>
      : overviewError && !items.length ? <div className="notice" data-tone="error" role="alert">{friendlyError(overviewError, "load projects")}</div>
      : !items.length ? <div className="empty"><span className="empty-icon"><Icon name="projects" size={24}/></span><strong>هنوز پروژه‌ای نداری</strong><p>با یک پیام شروع کن و ویدیو، تصویر یا لینک محصول اضافه کن.</p><NavLink className="btn" to="/studio">شروع</NavLink></div>
      : !shown.length ? <div className="empty"><span className="empty-icon"><Icon name="search" size={24}/></span><strong>پروژه‌ای پیدا نشد</strong><p>جست‌وجو یا فیلتر را عوض کن.</p><button className="btn btn-secondary" onClick={() => { setQuery(""); setType("all"); setStatus("all"); }}>پاک کردن فیلترها</button></div>
      : <ul className="pj-grid">{shown.map(item => <li key={item.key}><NavLink to={item.to} className="pj-card" title={item.title}>
          <span className="pj-thumb">{item.thumb ? <AuthenticatedMedia as="img" src={item.thumb} alt="" loading="lazy" draggable={false}/> : <span className="pj-ph" data-kind={item.kind}><Icon name={KIND_ICON[item.kind] || "video"} size={30}/></span>}
            <span className="pj-status" data-status={item.status}>{STATUS[item.status]}</span>
            <span className="pj-kind"><Icon name={KIND_ICON[item.kind] || "video"} size={12}/>{item.kindLabel}</span></span>
          <b className="pj-title" dir="auto">{displayTitle(item.title, 80)}</b>
          <span className="pj-meta">{dateText(item.updated)}{item.chat ? <span className="pj-chat"><Icon name="thinking" size={12}/>چت</span> : null}</span>
        </NavLink></li>)}</ul>}
    {(error || overviewError) && items.length ? <p className="notice" data-tone="warning">بعضی منبع‌ها به‌روز نشدند. <button className="link-btn" onClick={() => { void refetch(); void load(); }}>دوباره</button></p> : null}
  </div>;
}
