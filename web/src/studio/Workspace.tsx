import React from "react";
import { NavLink } from "react-router-dom";
import { api, StudioConversation, StudioProject } from "../api";
import { AuthenticatedMedia } from "../AuthenticatedMedia";
import { Icon } from "../components/Icon";
import { useFullscreen } from "../components/useFullscreen";
import { displayTitle } from "../format";
import { friendlyError } from "../ui";
import { renderView } from "./model";
import { ThinkingRow } from "./Activity";
import { RenderProgress } from "./RenderProgress";
import {MotionScenes} from './MotionScenes';
import { LocalizeEdit } from "./LocalizeEdit";
import { EditCard, EditSwitch } from "./EditCard";
import { EffectsEditor } from "./EffectsEditor";
import { PlanReview } from "./PlanReview";
import { currentVersion, planPhase } from "./plan";
import { TimelineView } from "./TimelineView";
import { useTopbarAction } from '../components/ShellContext';

export type WorkspaceTab = "preview" | "edit";

/** Talking projects carry a Creative Plan, shown at the top of the Edit tab as soon as one is being built. */
export function hasPlan(project?: StudioProject): boolean {
  return project?.engine === "talking" && planPhase(project) !== "none";
}

export function statusMeta(project?: StudioProject): { label: string; tone: "success" | "error" | "warning" | "working" | "neutral" } {
  const status = project?.status || "";
  if (["done", "ready"].includes(status)) return { label: "Ready", tone: "success" };
  if (["error", "failed"].includes(status)) return { label: "Needs attention", tone: "error" };
  if (["awaiting_confirmation", "awaiting_input", "paused"].includes(status)) return { label: "Waiting for you", tone: "warning" };
  if (["running", "rendering", "queued"].includes(status)) return { label: "Working", tone: "working" };
  return { label: "Draft", tone: "neutral" };
}

export function projectOutputUrl(project?: StudioProject) {
  const candidate = project?.state?.candidate_output;
  const output = candidate || project?.state?.last_observed?.output;
  return output && project ? `${api.studioOutputUrl(project.id)}?candidate=${Boolean(candidate)}&version=${encodeURIComponent(output)}` : undefined;
}

function Empty({ icon, title, text }: { icon: "spark" | "advanced"; title: string; text: string }) {
  return <div className="ws-empty"><span className="empty-icon"><Icon name={icon} size={24}/></span><h2>{title}</h2><p>{text}</p></div>;
}

function PreviewPane({ project, conversation, sourceAttachment, onCancel }: { project?: StudioProject; conversation: StudioConversation | null; sourceAttachment?: string; onCancel: () => void }) {
  const phase = renderView(project);
  const rendering = ['queued','rendering','finalizing'].includes(phase.phase);
  const [versions, setVersions] = React.useState<{file: string; version: number}[]>([]);
  const [selected, setSelected] = React.useState<string | null>(null);
  const playerRef = React.useRef<HTMLDivElement>(null);
  const videoRef = React.useRef<HTMLVideoElement>(null);
  const fullscreen = useFullscreen(playerRef, videoRef);
  React.useEffect(() => {
    let active = true;
    setSelected(null);
    setVersions([]);
    if (project) void api.studioOutputs(project.id).then(items => { if (active) setVersions(items); }).catch(() => {});
    return () => { active = false; };
  }, [project?.id, project?.state?.candidate_output, project?.state?.last_observed?.output]);
  if (!project) return <Empty icon="spark" title="Your preview will appear here" text="Describe an edit or add media in the chat. The video shows up here as soon as there is something to watch."/>;
  const selectedFile = selected || versions[versions.length - 1]?.file;
  const output = selectedFile ? `${api.studioOutputUrl(project.id)}?file=${encodeURIComponent(selectedFile)}` : projectOutputUrl(project);
  const view = renderView(project);
  const source = sourceAttachment && conversation ? api.studioAttachmentUrl(conversation.id, sourceAttachment) : undefined;
  const meta = statusMeta(project);
  const version = String(project.state?.last_observed?.output || "").match(/\/v(\d+)(?:_preview)?\.mp4(?:$|\?)/)?.[1] || project.current_version;
  const busy = view.phase === "queued" || view.phase === "rendering" || view.phase === "finalizing";
  return <div className="ws-preview">
    {versions.length ? <div className="ws-actions" role="group" aria-label="نسخه‌های خروجی">{versions.map(item => <button key={item.file} className="btn btn-sm btn-secondary" aria-pressed={selectedFile === item.file} onClick={() => setSelected(item.file)}>نسخهٔ {item.version}</button>)}</div> : null}
    <div className="ws-player" ref={playerRef}>
      {output ? <AuthenticatedMedia as="video" ref={videoRef} controls playsInline preload="metadata" src={output}/>
        : source ? <AuthenticatedMedia as="video" ref={videoRef} controls playsInline preload="metadata" src={source}/>
        : <div className="ws-placeholder"><span className="spinner"/><span>{view.stageLabel || "Preparing preview"}</span></div>}
      {(output || source) ? <button type="button" className="ws-fs" onClick={() => void fullscreen.toggle()} aria-pressed={fullscreen.active}
        aria-label={fullscreen.active ? "Exit fullscreen" : "Fullscreen"} data-tip={fullscreen.active ? "Exit fullscreen" : "Fullscreen"}>
        <Icon name={fullscreen.active ? "fullscreenExit" : "fullscreen"} size={18}/></button> : null}
    </div>
    {busy ? <RenderProgress project={project}/> : null}
    <div className="ws-meta">
      <span>Version {versions.find(item => item.file === selectedFile)?.version || version}</span>
      <span>{output ? (view.review ? 'خروجی برای بررسی نگه داشته شده' : 'Final quality') : 'Original upload'}</span>
    </div>
    <div className="ws-actions">
      {output && !view.review ? <button className="btn btn-sm" onClick={() => void api.downloadAuthenticated(output, `${project.title || "video"}.mp4`)}><Icon name="download" size={15}/>Download video</button> : null}
      {project.status === "running" ? <button className="btn btn-sm btn-secondary" onClick={onCancel}>Cancel</button> : null}
    </div>
  </div>;
}

function StoryboardEditor({ project, onSaved }: { project: StudioProject; onSaved: () => void }) {
  const [scenes, setScenes] = React.useState<any[]>(project.state.storyboard.scenes || []);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState("");
  const [saved, setSaved] = React.useState(false);
  React.useEffect(() => setScenes(project.state.storyboard.scenes || []), [project.id, project.current_version, project.state.storyboard]);
  const update = (index: number, patch: any) => { setSaved(false); setScenes(value => value.map((scene, i) => i === index ? { ...scene, ...patch } : scene)); };
  async function save() {
    setSaving(true); setError("");
    try { await api.updateStudioStoryboard(project.id, scenes); setSaved(true); onSaved(); }
    catch { setError("ذخیرهٔ استوری‌بورد انجام نشد. دوباره تلاش کنید."); }
    finally { setSaving(false); }
  }
  const total = scenes.reduce((sum, scene) => sum + (Number(scene.duration_s) || 0), 0);
  return <EditCard title="صحنه‌ها" open summary={`${scenes.length} صحنه · ${Math.round(total)} ثانیه`} hint="متن روی تصویر، نریشن و مدت هر صحنه را اینجا عوض کنید.">
    {error ? <div className="notice" data-tone="error" role="alert">{error}</div> : null}
    {scenes.map((scene, index) => <details className="scene" key={scene.index ?? index}>
      <summary><span className="scene-n">{index + 1}</span><b className="wrap-safe bidi" dir="auto">{scene.text_overlay || `صحنهٔ ${index + 1}`}</b><small>{scene.duration_s} ث</small><Icon name="chevronDown" size={16} className="scene-chev"/></summary>
      <div className="scene-body">
        <div className="field"><label htmlFor={`s-text-${index}`}>متن روی تصویر</label><input id={`s-text-${index}`} className="input bidi" dir="auto" value={scene.text_overlay || ""} onChange={event => update(index, { text_overlay: event.target.value })}/></div>
        <div className="field"><label htmlFor={`s-nar-${index}`}>نریشن</label><textarea id={`s-nar-${index}`} className="input bidi" dir="auto" rows={3} value={scene.narration_text || ""} onChange={event => update(index, { narration_text: event.target.value })}/></div>
        <div className="field"><label htmlFor={`s-dur-${index}`}>مدت صحنه (ثانیه)</label><input id={`s-dur-${index}`} className="input" type="number" min="0.5" max="30" step="0.5" value={scene.duration_s} onChange={event => update(index, { duration_s: Number(event.target.value) })}/></div>
        <div className="field"><label htmlFor={`s-engine-${index}`}>روش ساخت تصویر</label>
          <select id={`s-engine-${index}`} className="input" value={scene.motion_engine || "default"} onChange={event => update(index, { motion_engine: event.target.value })}>
            <option value="default">روش معمول EditorGPT</option><option value="motion_so">کلیپ موشن هوشمند (از اعتبار حساب مصرف می‌کند)</option></select></div>
        {scene.motion_engine === "motion_so" ? <>
          <p className="ec-hint">کلیپ بی‌صدا؛ نریشن و زیرنویس همچنان در EditorGPT ساخته می‌شود. شرح و تصاویر مرجع فقط بعد از تأیید شما ارسال می‌شود، هزینهٔ دقیق مشخص نیست و تلاش مجدد خودکار انجام نمی‌شود.</p>
          <div className="field"><label htmlFor={`s-visual-${index}`}>توضیح تصویر</label><textarea id={`s-visual-${index}`} className="input bidi" dir="auto" rows={3} value={scene.media_prompt || scene.description || ""} onChange={event => update(index, { media_prompt: event.target.value })}/></div>
          <div className="ec-grid">
            <div className="field"><label htmlFor={`s-effort-${index}`}>دقت ساخت</label><select id={`s-effort-${index}`} className="input" value={scene.motion_effort || "light"} onChange={event => update(index, { motion_effort: event.target.value })}>{[["light", "سبک"], ["medium", "متوسط"], ["high", "بالا"]].map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></div>
            <div className="field"><label htmlFor={`s-bg-${index}`}>رنگ پس‌زمینه</label><input id={`s-bg-${index}`} className="input" style={{ padding: 4 }} type="color" value={scene.motion_background || "#101010"} onChange={event => update(index, { motion_background: event.target.value })}/></div>
          </div></> : null}
      </div>
    </details>)}
    <div className="ec-actions"><button className="btn" disabled={saving} onClick={() => void save()}>{saving ? "در حال ذخیره…" : saved ? "ذخیره شد" : "ذخیرهٔ تغییرات"}</button></div>
  </EditCard>;
}

/** The existing specialist editor for this project, where failed runs can be re-analyzed. */
export function advancedEditorUrl(project?: StudioProject): string {
  if (!project) return "";
  return project.engine === "talking" ? `/talking?job=${project.external_ref}` : project.engine === "localize" ? `/localize?project=${project.external_ref}` : project.external_ref ? `/jobs/${project.external_ref}/render` : "";
}

/** Which engines have a project timeline: talking once its plan exists, the others once the project has started. */
export function hasTimeline(project?: StudioProject): boolean {
  if (!project) return false;
  return project.engine === "talking" ? hasPlan(project) && Boolean(currentVersion(project)) : Boolean(project.external_ref);
}

function EditPane({ project, onSaved, superseding = false }: { project?: StudioProject; onSaved: () => void | Promise<unknown>; superseding?: boolean }) {
  const [view, setView] = React.useState<"main" | "timeline">("main");
  const [footerSlot, setFooterSlot] = React.useState<HTMLElement | null>(null);
  if (!project) return <Empty icon="advanced" title="Nothing to edit yet" text="Once EditorGPT creates a project, the controls that apply to it appear here."/>;
  const advanced = advancedEditorUrl(project);
  const timeline = hasTimeline(project);
  const shown = timeline ? view : "main";
  return <div className="ws-edit">
    {timeline ? <div className="segmented ws-edit-views" role="group" aria-label="نمای ویرایش" dir="rtl">
      <button type="button" aria-pressed={shown === "main"} onClick={() => setView("main")}>{hasPlan(project) ? "برنامه" : "ویرایش"}</button>
      <button type="button" aria-pressed={shown === "timeline"} onClick={() => setView("timeline")}>تایم‌لاین</button>
    </div> : null}
    {shown === "timeline" ? <TimelineView project={project} onChanged={onSaved} currentOutput={projectOutputUrl(project)}/> : null}
    {shown === "timeline" ? null : project.engine === "localize" && project.external_ref ? <LocalizeEdit key={project.external_ref} id={project.external_ref} onChanged={onSaved}/>
      : hasPlan(project) ? <PlanReview project={project} onChanged={onSaved} superseding={superseding} footerSlot={footerSlot}/>
      : <header className="ws-edit-intro" dir="rtl"><h2>ویرایش این ویدیو</h2><p>تغییر زیرنویس، ریتم، رنگ یا صدا را در چت بگویید. هر چه این نوع ویدیو پشتیبانی کند، همین‌جا کنترلش را می‌بینید.</p></header>}
    {shown === "timeline" ? null : <>
    {project.engine === 'talking' && project.external_ref ? <EffectsEditor key={`fx-${project.external_ref}`} jobId={project.external_ref} onSaved={onSaved}/> : null}
    {project.engine === 'talking' && project.external_ref ? <KeyMoments key={`km-${project.external_ref}`} jobId={project.external_ref} onSaved={onSaved}/> : null}
    {project.engine === 'talking' && project.external_ref && !hasPlan(project) ? <TalkingShade key={project.external_ref} jobId={project.external_ref} onSaved={onSaved}/> : null}
    {project.state?.storyboard?.scenes?.length ? <StoryboardEditor project={project} onSaved={onSaved}/> : null}
    {project.external_ref && project.engine!=='localize' ? <MotionScenes jobId={project.external_ref} onSaved={onSaved}/> : null}
    </>}
    {shown === "timeline" ? null : advanced
      ? <NavLink className="adv-link" to={advanced}><Icon name="advanced" size={20}/><span><b>ویرایشگر پیشرفته</b><small>تایم‌لاین، صدا و تنظیمات دقیق‌تر</small></span><Icon name="chevron" size={18}/></NavLink>
      : <p className="ws-hint" dir="rtl">تغییر را در چت بگویید؛ نسخهٔ تازه‌ای ساخته می‌شود و نسخهٔ فعلی دست‌نخورده می‌ماند.</p>}
    <div className="ws-edit-footer" dir="rtl" ref={setFooterSlot}/>
  </div>;
}

/**
 * Fullscreen for the whole workspace (Preview or Edit tab, not just the video). The panel is stretched over the page
 * with CSS, which works everywhere (embedded browsers and iPhones refuse the Fullscreen API); the browser's own
 * fullscreen is requested on top of it when it is available.
 */
function usePanelFullscreen() {
  const node = React.useRef<HTMLElement | null>(null);
  const [active, setActive] = React.useState(false);
  const native = React.useRef(false);
  React.useEffect(() => {
    if (!active) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") setActive(false); };
    const onChange = () => { if (native.current && !document.fullscreenElement) { native.current = false; setActive(false); } };
    window.addEventListener("keydown", onKey);
    document.addEventListener("fullscreenchange", onChange);
    return () => { window.removeEventListener("keydown", onKey); document.removeEventListener("fullscreenchange", onChange); };
  }, [active]);
  const toggle = React.useCallback(async () => {
    if (active) {
      setActive(false);
      if (document.fullscreenElement) { native.current = false; try { await document.exitFullscreen(); } catch { /* already out */ } }
      return;
    }
    setActive(true);
    try { if (node.current?.requestFullscreen) { await node.current.requestFullscreen(); native.current = true; } } catch { /* the CSS layout is enough */ }
  }, [active]);
  return { node, active, toggle };
}

/** The black-and-white key moments of a Talking 1 reel, in the same card style as the other Edit settings. */
function KeyMoments({jobId, onSaved}: {jobId:string; onSaved:()=>void}) {
  const [state,setState]=React.useState<Awaited<ReturnType<typeof api.getTalkingReel>> | null>(null);
  const [chosen,setChosen]=React.useState<Record<number,string>>({});
  const [saving,setSaving]=React.useState(false);
  const [error,setError]=React.useState('');
  const [saved,setSaved]=React.useState(false);
  React.useEffect(()=>{let active=true; void api.getTalkingReel(jobId).then(s=>{if(!active)return;setState(s);setChosen(Object.fromEntries((s.key_moments||[]).map(m=>[m.i,m.text])));}).catch(()=>{if(active)setError('لحظه‌های کلیدی دریافت نشد.');}); return ()=>{active=false;};},[jobId]);
  if (!state || String(state.style||'talking_1')!=='talking_1' || !(state.captions||[]).length) return error ? <p className="notice" data-tone="error" role="alert" dir="rtl">{error}</p> : null;
  const busy=saving||['running','analyzing'].includes(state.status);
  const count=Object.keys(chosen).length;
  const toggle=(i:number,on:boolean)=>{setSaved(false);setChosen(c=>{const next={...c};if(!on)delete next[i];else if(Object.keys(next).length<8)next[i]=next[i]??'';return next;});};
  async function save(){
    setSaving(true);setError('');
    try{const next=await api.editTalkingReel(jobId,{key_moments:Object.entries(chosen).map(([i,text])=>({i:Number(i),text}))});setState(next);setSaved(true);onSaved();}
    catch(e){setError(friendlyError(e,'save the key moments'));}finally{setSaving(false);}
  }
  return <EditCard title="لحظه‌های کلیدی" summary={count ? `${count} لحظهٔ سیاه‌وسفید از حداکثر ۸` : 'هیچ لحظه‌ای انتخاب نشده'} hint="جمله‌هایی که سیاه‌وسفید می‌شوند. برای هر کدام می‌توانید یک جملهٔ کوتاه (حداکثر ۵ کلمهٔ فارسی) بنویسید تا درشت و سفید نمایش داده شود. روی رندر بعدی اعمال می‌شود.">
    <div className="km-list">
      {(state.captions||[]).map(c=>{const on=c.i in chosen; return <div key={c.i} className="km-row" data-on={on || undefined}>
        <EditSwitch label={c.text.length>70?`${c.text.slice(0,70)}…`:c.text} checked={on} disabled={busy || (!on && count>=8)} onChange={value=>toggle(c.i,value)}/>
        {on ? <input className="input" type="text" dir="rtl" value={chosen[c.i]} disabled={busy} maxLength={60} placeholder="جملهٔ کوتاه روی تصویر (اختیاری)" aria-label="جملهٔ کوتاه روی تصویر"
          onChange={e=>{setSaved(false);setChosen(m=>({...m,[c.i]:e.target.value}));}}/> : null}
      </div>;})}
    </div>
    {error ? <p className="notice" data-tone="error" role="alert">{error}</p> : null}
    <button className="btn btn-sm" disabled={busy} onClick={()=>void save()}>{saving?'در حال ذخیره…':saved?'ذخیره شد':'ذخیرهٔ لحظه‌های کلیدی'}</button>
  </EditCard>;
}

function TalkingShade({jobId, onSaved}: {jobId:string; onSaved:()=>void}) {
  const [state,setState]=React.useState<Awaited<ReturnType<typeof api.getTalkingReel>> | null>(null);
  const [shade,setShade]=React.useState(0);
  const [saving,setSaving]=React.useState(false);
  const [error,setError]=React.useState('');
  const [saved,setSaved]=React.useState(false);
  React.useEffect(()=>{let active=true; void api.getTalkingReel(jobId).then(s=>{if(active){setState(s);setShade(s.render_settings?.bottom_shade ?? 0);}}).catch(()=>{if(active)setError('تنظیمات فید دریافت نشد.');});return()=>{active=false;};},[jobId]);
  async function save(){
    setSaving(true);setError('');
    try {const latest=await api.getTalkingReel(jobId);if(!latest.render_settings)throw new Error();
      const next=await api.editTalkingReel(jobId,{render_settings:{...latest.render_settings,bottom_shade:shade}});
      setState(next);setSaved(true);onSaved();
    }catch{setError('ذخیرهٔ فید انجام نشد؛ دوباره تلاش کنید.');}finally{setSaving(false);}
  }
  return <section className="sb" dir="rtl">
    <label htmlFor="talking-bottom-shade">شدت فید مشکی پایین: {shade}%</label>
    <input id="talking-bottom-shade" type="range" min="0" max="60" step="1" value={shade}
      disabled={!state || saving || ['running','analyzing'].includes(state.status)}
      onChange={e=>{setShade(Number(e.target.value));setSaved(false);}} style={{width:'100%'}}/>
    <p>این تنظیم روی رندر بعدی اعمال می‌شود؛ فایل فعلی تغییر نمی‌کند.</p>
    {error ? <p role="alert">{error}</p> : null}
    <button className="btn btn-sm" disabled={!state || saving || ['running','analyzing'].includes(state.status)} onClick={()=>void save()}>{saving?'در حال ذخیره…':saved?'ذخیره شد':'ذخیرهٔ فید'}</button>
  </section>;
}

export function Workspace({ conversation, project, projects, onSelectProject, tab, onTab, sourceAttachment, onCancel, onSaved, onCollapse, showTabs, panelRef, resizer, topbarEdit = false, working = null }: {
  conversation: StudioConversation | null; project?: StudioProject; projects: StudioProject[]; onSelectProject: (id: string) => void;
  tab: WorkspaceTab; onTab: (tab: WorkspaceTab) => void; sourceAttachment?: string; onCancel: () => void; onSaved: () => void | Promise<unknown>;
  onCollapse?: () => void; showTabs: boolean; panelRef?: React.Ref<HTMLElement>;
  /** Drag handle on the panel's inner edge (desktop only), rendered by the page that owns the layout. */
  resizer?: React.ReactNode;
  topbarEdit?: boolean;
  /** What the assistant is doing right now (a new edit request being worked on), shown in the Edit tab like in the chat. */
  working?: string | null;
}) {
  const meta = statusMeta(project);
  const panel = usePanelFullscreen();
  const action = React.useMemo(() => topbarEdit ? { active: panel.active, onClick: () => { void panel.toggle(); } } : null, [topbarEdit, panel.active, panel.toggle]);
  useTopbarAction(action);
  const view = renderView(project);
  const rendering = tab === "edit" && ["queued", "rendering", "finalizing"].includes(view.phase);
  const setNode = React.useCallback((element: HTMLElement | null) => {
    panel.node.current = element;
    if (typeof panelRef === "function") panelRef(element);
    else if (panelRef) (panelRef as React.MutableRefObject<HTMLElement | null>).current = element;
  }, [panelRef, panel.node]);
  return <section className="workspace" ref={setNode} data-max={panel.active || undefined} aria-label="Video workspace">
    {resizer}
    <header className="ws-head" hidden={topbarEdit}>
      {showTabs ? <div className="tabs-bar" role="tablist" aria-label="Workspace">
        {(["preview", "edit"] as WorkspaceTab[]).map(item => <button key={item} role="tab" id={`ws-tab-${item}`} aria-controls={`ws-panel-${item}`} aria-selected={tab === item} tabIndex={tab === item ? 0 : -1} className="tab"
          onClick={() => onTab(item)}
          onKeyDown={event => { if (event.key === "ArrowRight" || event.key === "ArrowLeft") { onTab(item === "preview" ? "edit" : "preview"); } }}>
          <Icon name={item === "preview" ? "eye" : "edit"} size={15}/>{item === "preview" ? "Preview" : "Edit"}</button>)}
      </div> : <h2 className="ws-title-solo">{tab === "preview" ? "Preview" : "Edit"}</h2>}
      <span className="grow"/>
      {projects.length > 1 ? <select className="input ws-select" aria-label="Project" value={project?.id} onChange={event => onSelectProject(event.target.value)}>{projects.map(item => <option key={item.id} value={item.id}>{displayTitle(item.title, 32)}</option>)}</select> : null}
      <button className="icon-btn" onClick={() => void panel.toggle()} aria-pressed={panel.active} aria-label={panel.active ? "Exit full screen" : "Full screen"}
        data-tip={panel.active ? "Exit full screen" : "Full screen"}><Icon name={panel.active ? "fullscreenExit" : "fullscreen"} size={19}/></button>
      {onCollapse && !panel.active ? <button className="icon-btn" onClick={onCollapse} aria-label="Hide workspace" data-tip="Hide workspace"><Icon name="panelRight" size={19}/></button> : null}
    </header>
    {topbarEdit && panel.active ? <button className="icon-btn ws-edit-exit" onClick={() => void panel.toggle()} aria-label="Exit full screen"><Icon name="fullscreenExit" size={18}/></button> : null}
    {project ? <div className="ws-titlebar"><h2 className="bidi wrap-safe" dir="auto" title={project.title}>{displayTitle(project.title, 80)}</h2><span className="badge" data-tone={meta.tone === "neutral" ? undefined : meta.tone}><i/>{meta.label}</span></div> : null}
    {rendering ? <div className="ws-edit-progress"><RenderProgress project={project!}/></div> : null}
    {working && !rendering && tab === "edit" ? <div className="ws-edit-progress" role="status" dir="rtl"><ThinkingRow label={working}/></div> : null}
    <div className="ws-body">
      <div role="tabpanel" id="ws-panel-preview" aria-labelledby="ws-tab-preview" hidden={tab !== "preview"}><PreviewPane project={project} conversation={conversation} sourceAttachment={sourceAttachment} onCancel={onCancel}/></div>
      <div role="tabpanel" id="ws-panel-edit" aria-labelledby="ws-tab-edit" hidden={tab !== "edit"}><EditPane project={project} onSaved={onSaved} superseding={Boolean(working)}/></div>
    </div>
  </section>;
}
