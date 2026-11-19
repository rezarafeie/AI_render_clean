import React from "react";
import { Link } from "react-router-dom";
import { api, type CreativeResource, type LibraryAsset, type StyleProfile } from "../api";
import { AuthenticatedMedia } from "../AuthenticatedMedia";
import { Icon } from "../components/Icon";
import { friendlyError } from "../ui";
import { canApplyResource, ResourceApply } from "./ResourceApply";
import { useAuth } from "../auth/AuthContext";

const MotionLibrary = React.lazy(() => import("../MotionLibrary"));
const Typography = React.lazy(() => import("./Typography").then(m => ({default: m.Typography})));

type Category = "gallery" | "registry" | "assets" | "fonts" | "styles" | "favorites";
const groups: [Category, string][] = [["registry", "رجیستری افکت و ترنزیشن"], ["gallery", "گالری موشن"], ["assets", "رسانه و صدا"], ["fonts", "فونت‌ها"], ["styles", "سبک‌ها"], ["favorites", "علاقه‌مندی‌ها"]];

export function Resources({onTools, job, projectId, onApplied}: {onTools?: () => void; job?: string; projectId?: string; onApplied?: () => Promise<unknown>}) {
  const {user} = useAuth();
  const storageKey = `editorgpt.panel.favorites.${user?.id ?? "local"}`;
  const [category, setCategory] = React.useState<Category>("registry");
  const [apply, setApply] = React.useState<CreativeResource | null>(null);
  const [saved, setSaved] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [onlyWorking, setOnlyWorking] = React.useState(false);
  const [rows, setRows] = React.useState<CreativeResource[]>([]);
  const [favorites, setFavorites] = React.useState<Record<string, CreativeResource>>(() => {
    try { return JSON.parse(localStorage.getItem(storageKey) || "{}"); } catch { return {}; }
  });
  const [assets, setAssets] = React.useState<LibraryAsset[]>([]);
  const [styles, setStyles] = React.useState<StyleProfile[]>([]);
  const [offset, setOffset] = React.useState(0);
  const [total, setTotal] = React.useState(0);
  const [current, setCurrent] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    if (category !== "registry") return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setLoading(true); setError("");
      api.searchCreativeResources(query.trim(), onlyWorking ? "existing-pipeline" : "", offset, controller.signal).then(result => {
        if (!controller.signal.aborted) {
          setRows(previous => offset ? [...previous, ...result.items] : result.items);
          setTotal(result.total);
        }
      }).catch(e => { if (!controller.signal.aborted) setError(friendlyError(e, "load the library")); })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 180);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [category, query, onlyWorking, offset]);

  React.useEffect(() => {
    if (category !== "styles" && category !== "assets") return;
    let live = true; setLoading(true); setError("");
    const load = async () => {
      try {
        if (category === "assets") { const value = await api.getLibrary(); if (live) setAssets(value.assets); }
        else { const value = await api.getStyleLibrary(); if (live) setStyles(value.profiles); }
      } catch (e) { if (live) setError(friendlyError(e, "load the library")); }
      finally { if (live) setLoading(false); }
    };
    void load();
    return () => { live = false; };
  }, [category]);

  function favorite(item: CreativeResource) {
    setFavorites(previous => {
      const next = {...previous};
      if (next[item.id]) delete next[item.id]; else next[item.id] = item;
      try { localStorage.setItem(storageKey, JSON.stringify(next)); } catch { /* favorites stay in this tab */ }
      return next;
    });
  }

  const matches = (text: string) => text.toLowerCase().includes(query.trim().toLowerCase());
  const items = category === "favorites" ? Object.values(favorites).filter(item => matches(item.name)) : rows;
  return <section className="mp-inspector" aria-label="کتابخانهٔ خلاقیت">
    <div className="mp-section-head"><h2>کتابخانه</h2><Link className="btn btn-sm btn-secondary" to="/motion-library">گالری موشن</Link></div>
    <div className="mp-chips">{groups.map(([key, label]) => <button key={key} className="btn btn-sm btn-secondary" aria-pressed={category === key}
      onClick={() => {setCategory(key); setOffset(0); setCurrent(null); setApply(null); setError(""); setLoading(false);}}>{label}</button>)}</div>
    {category !== "fonts" && category !== "gallery" && <input className="input" type="search" aria-label="جستجو در منابع" placeholder="جستجو در منابع…" value={query}
      onChange={e => {setOffset(0); setQuery(e.target.value);}}/>}
    {category === "registry" && <label className="mp-check"><input type="checkbox" checked={onlyWorking} onChange={e => {setOffset(0); setOnlyWorking(e.target.checked);}}/>فقط موارد متصل به موتور</label>}
    {error && <p className="notice" data-tone="error" role="alert">{error}</p>}
    {saved && <p role="status" className="mp-muted">در تایم‌لاین ذخیره شد. برای دیدن جلوهٔ نهایی، رندر پیش‌نمایش بگیرید.</p>}
    {apply && job && projectId && <ResourceApply key={`${job}:${apply.id}`} item={apply} job={job} projectId={projectId} onClose={() => setApply(null)}
      onSaved={async () => {setApply(null); setSaved(true); await onApplied?.();}}/>}
    {loading && <p className="mp-muted" role="status">در حال دریافت منابع…</p>}
    {(category === "registry" || category === "favorites") && <>
      <div className="mp-gallery">
        {items.map(item => <article key={item.id} className="mp-asset">
          {current === item.id && item.preview_video ? <video key={item.id} src={item.preview_video} poster={item.preview_poster || undefined} controls playsInline autoPlay preload="none"/>
            : item.preview_poster ? <img src={item.preview_poster} loading="lazy" alt=""/>
            : <div className="mp-asset-empty"><Icon name="motion" size={24}/><span>بدون تصویر پیش‌نمایش</span></div>}
          <div><b dir="auto">{item.name}</b><small dir="auto">{item.category} · {item.engine}</small><small>{item.availability === "existing-pipeline" ? "متصل به موتور سازگار" : item.availability === "catalog-only" ? "فقط مرجع" : "پشتیبانی نمی‌شود"}</small></div>
          <div className="mp-actions">
            {item.preview_video && <button className="btn btn-sm btn-secondary" onClick={() => setCurrent(current === item.id ? null : item.id)}>{current === item.id ? "بستن پخش" : "پیش‌نمایش"}</button>}
            {job && projectId && canApplyResource(item) && <button className="btn btn-sm btn-primary" onClick={() => {
              setApply(item); setSaved(false);
            }} aria-label={`اعمال ${item.name}`}>اعمال</button>}
            <button className="btn btn-sm btn-secondary" aria-pressed={Boolean(favorites[item.id])} onClick={() => favorite(item)}>{favorites[item.id] ? "★" : "☆"} <span className="sr-only">علاقه‌مندی</span></button>
          </div>
          {item.limitations.length > 0 && <details><summary>سازگاری و محدودیت‌ها</summary><p>{item.limitations.join(" · ")}</p></details>}
        </article>)}
      </div>
      {!loading && items.length === 0 && <p className="mp-muted">موردی پیدا نشد.</p>}
      {category === "registry" && rows.length < total && <button className="btn btn-secondary" disabled={loading} onClick={() => setOffset(rows.length)}>موارد بیشتر</button>}
    </>}
    {category === "assets" && <>
      <div className="mp-gallery">
        {assets.filter(asset => matches(`${asset.filename} ${asset.category} ${asset.tags.join(" ")}`)).slice(0, 30).map(asset => {
          const key = `${asset.category}/${asset.filename}`;
          return <article className="mp-asset" key={key}><div><b dir="auto">{asset.filename}</b><small dir="auto">{asset.category} · {asset.tags.join("، ")}</small></div>
            {current === key ? <AuthenticatedMedia as={asset.category === "broll" ? "video" : "audio"} controls playsInline preload="none"
              src={api.libraryPreviewUrl(asset.category, asset.filename)}/>
              : <button className="btn btn-secondary btn-sm" onClick={() => setCurrent(key)}>پیش‌نمایش</button>}
          </article>;
        })}
      </div>
      <Link className="btn btn-secondary btn-sm" to="/library">مدیریت همهٔ فایل‌های کتابخانه</Link>
    </>}
    {category === "styles" && <div className="mp-gallery">
      {styles.filter(style => matches(style.name)).map(style => <article className="mp-asset" key={`${style.style_id}:${style.version}`}>
        <div><b>{style.name}</b><small>نسخهٔ {style.version}</small></div>
      </article>)}
      <Link className="btn btn-secondary btn-sm" to="/style-library">پیش‌نمایش و مدیریت سبک‌ها</Link>
    </div>}
    {category === "gallery" && <React.Suspense fallback={<p role="status">در حال بارگذاری گالری…</p>}><MotionLibrary/></React.Suspense>}
    {category === "fonts" && <React.Suspense fallback={<p role="status">در حال باز کردن نمونهٔ فونت‌ها…</p>}><Typography/>
      <Link className="btn btn-secondary btn-sm" to="/style-library#fonts">مدیریت و ورود فونت</Link></React.Suspense>}
    <div className="mp-actions">
      {onTools && <button className="btn btn-secondary" onClick={onTools}>اعمال منابع سازگار در ابزار پروژه</button>}
      <Link className="btn btn-secondary btn-sm" to="/templates">تمپلیت‌ها</Link>
      <Link className="btn btn-secondary btn-sm" to="/my-effects">افکت‌های من</Link>
    </div>
  </section>;
}
