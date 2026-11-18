import React from "react";
import { api, type CloudFile, type StudioAttachment, type StudioFile } from "../api";
import { Icon, type IconName } from "../components/Icon";
import { AuthenticatedMedia } from "../AuthenticatedMedia";
import { friendlyError } from "../ui";
import type { Capabilities, Engine, Setup as SetupData } from "./types";

const FilesPicker = React.lazy(() => import("../studio/FilesPicker").then(m => ({ default: m.FilesPicker })));
const CloudPicker = React.lazy(() => import("../studio/CloudPicker").then(m => ({ default: m.CloudPicker })));
export const engines: {id: Engine; name: string; detail: string; icon: IconName; claude?: boolean}[] = [
  { id: "clips", name: "برش و تدوین دستی", detail: "از یک ویدیو شروع کنید و برش‌ها را روی تایم‌لاین بسازید", icon: "film" },
  { id: "talking", name: "ریلز صحبتی", detail: "تحلیل گفتار، زیرنویس و تدوین از روی ویدیو", icon: "mic2" },
  { id: "discovery", name: "کشف کلیپ از ویدیوی بلند", detail: "پیدا کردن بخش‌های مستقل از پادکست، کلاس یا مصاحبه", icon: "eye" },
  { id: "storyboard", name: "ساخت با استوری‌بورد", detail: "بررسی و ویرایش صحنه‌ها پیش از تولید تصویر و نریشن", icon: "projects" },
  { id: "localize", name: "فارسی‌سازی و دوبله", detail: "ترجمه و گویندگی روی ویدیوی موجود", icon: "globe" },
  { id: "motion", name: "موشن توضیحی", detail: "ساخت صحنه و نریشن از موضوع یا رفرنس", icon: "motion" },
  { id: "vox", name: "اکسپلینر Vox", detail: "طراحی مستند و کلاژ", icon: "film", claude: true },
  { id: "story", name: "ویدیوی روایی", detail: "معرفی به شکل قصه با صحنه‌های طراحی‌شده", icon: "captions", claude: true },
  { id: "product", name: "معرفی محصول", detail: "شوریل محصول با عکس یا صفحهٔ منبع", icon: "spark", claude: true },
];

type Props = { id: string; initial: SetupData; capabilities: Capabilities; onStarted: () => Promise<unknown> };

export function Setup({id, initial, capabilities, onStarted}: Props) {
  const [data, setData] = React.useState(initial);
  const [picker, setPicker] = React.useState<"files" | "cloud" | null>(null);
  const [assets, setAssets] = React.useState<Record<string, StudioAttachment>>({});
  const [busy, setBusy] = React.useState("");
  const [error, setError] = React.useState("");
  const [saveStatus, setSaveStatus] = React.useState("ذخیره شد");
  const latest = React.useRef(initial);
  const persisted = React.useRef(JSON.stringify(initial));
  const queue = React.useRef(Promise.resolve());
  const fileRef = React.useRef<HTMLInputElement>(null);
  const [preview, setPreview] = React.useState<string | null>(null);
  const sourceVideo = data.engine === "talking" || data.engine === "localize" || data.engine === "clips" || data.engine === "discovery";
  React.useEffect(() => {
    let active = true;
    api.panelDraftMedia(id).then(rows => {
      if (active) setAssets(current => ({...Object.fromEntries(rows.map(row => [row.id, row])), ...current}));
    }).catch(e => { if (active) setError(friendlyError(e, "load draft files")); });
    return () => { active = false; };
  }, [id]);

  const save = React.useCallback((value: SetupData) => {
    const key = JSON.stringify(value);
    setSaveStatus("در حال ذخیره…");
    const task = queue.current.catch(() => {}).then(async () => {
      if (key !== persisted.current) {
        await api.savePanelSetup(id, value);
        persisted.current = key;
      }
    });
    queue.current = task;
    return task.then(() => setSaveStatus("ذخیره شد"), e => {
      setSaveStatus("ذخیره نشد");
      throw e;
    });
  }, [id]);

  React.useEffect(() => {
    if (JSON.stringify(data) === persisted.current) return;
    const timer = setTimeout(() => void save(data).catch(e => setError(friendlyError(e, "save the draft"))), 450);
    return () => clearTimeout(timer);
  }, [data, save]);

  function update(next: Partial<SetupData>) {
    latest.current = {...latest.current, ...next};
    setData(latest.current);
    setSaveStatus("تغییر ثبت‌نشده");
  }

  function add(file: StudioAttachment) {
    setAssets(current => ({...current, [file.id]: file}));
    update({attachment_ids: [...new Set([...latest.current.attachment_ids, file.id])].slice(0, 16)});
  }

  async function upload(file?: File) {
    if (!file) return;
    setError("");
    setBusy("در حال آپلود…");
    try { add(await api.uploadStudioMedia(id, file, percent => setBusy(`آپلود ${Math.round(percent)}٪`))); }
    catch (e) { setError(friendlyError(e, "upload this file")); }
    finally { setBusy(""); }
  }

  async function attach(files: StudioFile[]) {
    setBusy("در حال افزودن فایل…");
    try { for (const file of files.slice(0, 16 - latest.current.attachment_ids.length)) add(await api.attachStudioFile(id, file.id)); }
    finally { setBusy(""); }
  }

  async function cloud(files: CloudFile[]) {
    setBusy("در حال دریافت از Drive…");
    try {
      const result = await api.cloudImport("googledrive", id, files.map(file => file.id));
      if (!result.transfers.length) throw new Error(result.errors[0]?.message || "انتقال آغاز نشد.");
      for (let transfer of result.transfers) {
        const limit = Date.now() + 10 * 60 * 1000;
        while (!["completed", "failed", "cancelled"].includes(transfer.state) && Date.now() < limit) {
          await new Promise(resolve => setTimeout(resolve, 1800));
          transfer = await api.cloudTransfer(id, transfer.id);
        }
        if (!transfer.attachment_id || transfer.state !== "completed") {
          setError(transfer.error || "انتقال هنوز کامل نشده است. فایل‌های حساب را بررسی کنید.");
          continue;
        }
        add({id: transfer.attachment_id, filename: transfer.filename, mime_type: "", size_bytes: transfer.size ?? 0,
             kind: transfer.kind === "video" || transfer.kind === "audio" ? transfer.kind : "image"});
      }
    } finally { setBusy(""); }
  }

  async function start() {
    setBusy(data.engine === "clips" ? "در حال آماده‌سازی تایم‌لاین…" : sourceVideo ? "در حال ارسال برای تحلیل…" : "در حال شروع ساخت…");
    setError("");
    try { await save(latest.current); await api.startPanelWork(id); await onStarted(); }
    catch (e) { setError(friendlyError(e, "start this project")); }
    finally { setBusy(""); }
  }

  return <section className="mp-setup">
    <header className="mp-section-head"><div><h1>پروژهٔ جدید</h1><p>نوع ویدیو را انتخاب کنید و رسانهٔ آن را اضافه کنید.</p></div><span className="badge" role="status">{saveStatus}</span></header>
    <fieldset disabled={Boolean(busy)} className="mp-reset">
      <legend className="mp-section-label">نوع ویدیو</legend>
      <div className="mp-engine-grid">
        {engines.map(engine => <button key={engine.id} className="mp-engine" aria-pressed={data.engine === engine.id}
          disabled={engine.claude && !capabilities.claude_motion} onClick={() => update({engine: engine.id, style: "", motion_so: false})}>
          <span className="mp-engine-icon"><Icon name={engine.icon} size={21}/></span><span><b>{engine.name}</b>
            <small>{engine.claude && !capabilities.claude_motion ? "روی این سرور فعال نیست" : engine.detail}</small></span>
        </button>)}
      </div>
      <div className="mp-form-grid">
        <label>نام پروژه<input className="input" maxLength={100} value={data.title} onChange={e => update({title: e.target.value})}/></label>
        <label>گردش کار<select className="input" value={data.mode} onChange={e => update({mode: e.target.value as SetupData["mode"]})}>
          <option value="manual">دستی</option><option value="assisted">با کمک دستیار</option><option value="auto">ساخت خودکار</option>
        </select></label>
        {data.engine === "talking" && <label>سبک تدوین<select className="input" value={data.style} onChange={e => update({style: e.target.value})}>
          <option value="">پیشنهاد موتور پس از تحلیل</option>
          {capabilities.talking_styles.map(style => <option key={style.id} value={style.id}>{style.label}</option>)}
          <option value="premium">پریمیوم تمام‌قاب</option>
        </select></label>}
        {data.engine === "clips" && <label>نسبت تصویر<select className="input" value={data.aspect || "source"} onChange={e => update({aspect: e.target.value as SetupData["aspect"]})}>
          <option value="source">همان منبع</option><option value="vertical">عمودی ۹:۱۶</option>
          <option value="square">مربع ۱:۱</option><option value="landscape">افقی ۱۶:۹</option>
        </select></label>}
        {data.engine === "discovery" && <label>محور کلیپ‌ها (اختیاری)<input className="input" maxLength={600}
          value={data.topic} onChange={e => update({topic: e.target.value})} placeholder="مثلاً بخش‌هایی دربارهٔ جذب مشتری"/></label>}
        {data.engine === "storyboard" && capabilities.motion_so && <label className="mp-check">
          <input type="checkbox" checked={Boolean(data.motion_so)} onChange={e => update({motion_so: e.target.checked})}/>
          کلیپ موشن هوشمند با Motion.so · تولید پس از تأیید
        </label>}
        {!sourceVideo && <>
          <label>موضوع<input className="input" maxLength={1000} value={data.topic} onChange={e => update({topic: e.target.value})} placeholder="مثلاً معرفی یک اپ یادگیری زبان"/></label>
          <label>لینک صفحهٔ منبع<input type="url" dir="ltr" className="input" value={data.source_url} onChange={e => update({source_url: e.target.value})} placeholder="https://"/></label>
          <label>مدت هدف<select className="input" value={data.seconds} onChange={e => update({seconds: Number(e.target.value) as SetupData["seconds"]})}>
              {[15, 30, 45, 60].map(n => <option key={n} value={n}>{n} ثانیه</option>)}</select></label>
        </>}
      </div>
      <h2 className="mp-section-label">رسانه</h2>
      <div className="mp-actions">
        <button className="btn btn-secondary" onClick={() => fileRef.current?.click()} disabled={data.attachment_ids.length >= 16}><Icon name="paperclip" size={17}/>آپلود</button>
        <button className="btn btn-secondary" onClick={() => setPicker("files")} disabled={data.attachment_ids.length >= 16}>فایل‌های حساب</button>
        <button className="btn btn-secondary" onClick={() => setPicker("cloud")} disabled={data.attachment_ids.length >= 16}>Google Drive</button>
        <input hidden type="file" ref={fileRef} accept={sourceVideo ? "video/*" : "image/*,audio/*,video/*"} onChange={e => {
          void upload(e.target.files?.[0]); e.target.value = "";
        }}/>
      </div>
      {data.attachment_ids.length > 0 && <ul className="mp-files">
        {data.attachment_ids.map((asset, index) => <li key={asset}>
          <button className="btn btn-secondary btn-sm" onClick={() => setPreview(preview === asset ? null : asset)}>{assets[asset]?.filename || `رسانهٔ ${index + 1}`}</button>
          <button className="icon-btn" aria-label={`برداشتن رسانهٔ ${index + 1}`} onClick={() => {
            if (preview === asset) setPreview(null);
            update({attachment_ids: data.attachment_ids.filter(item => item !== asset)});
          }}><Icon name="close" size={17}/></button>
        </li>)}
      </ul>}
      {preview && <AuthenticatedMedia key={preview} as={assets[preview]?.kind === "image" ? "img" : assets[preview]?.kind === "audio" ? "audio" : "video"}
        className="mp-setup-media" src={api.studioAttachmentUrl(id, preview)} controls playsInline preload="none"/>}
    </fieldset>
    <div className="mp-actions">
      <button className="btn btn-primary" onClick={() => void start()} disabled={Boolean(busy) || (sourceVideo && !data.attachment_ids.length)}>
        {busy || (data.engine === "clips" ? "باز کردن تایم‌لاین" : sourceVideo ? "شروع تحلیل و باز کردن ادیتور" : "ساخت پروژه و شروع طراحی")}
      </button>
      <button className="btn btn-secondary" onClick={() => void save(data).catch(e => setError(friendlyError(e, "save the draft")))} disabled={Boolean(busy) || saveStatus === "ذخیره شد"}>ذخیرهٔ پیش‌نویس</button>
    </div>
    {error && <p className="notice" data-tone="error" role="alert">{error}</p>}
    <React.Suspense fallback={<p role="status">در حال باز کردن فایل‌ها…</p>}>
      {picker === "files" && <FilesPicker onClose={() => setPicker(null)} onAttach={attach}/>}
      {picker === "cloud" && <CloudPicker onClose={() => setPicker(null)} onImport={cloud}/>}
    </React.Suspense>
  </section>;
}
