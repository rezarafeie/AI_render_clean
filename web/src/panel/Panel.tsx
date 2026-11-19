import React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type AgentMode, type MotionGraphic, type StudioConversation, type StudioEvent, type StudioProject } from "../api";
import { AuthenticatedMedia } from "../AuthenticatedMedia";
import { Icon, type IconName } from "../components/Icon";
import { friendlyError } from "../ui";
import { ActivityBlock, ThinkingRow } from "../studio/Activity";
import { type ActivityStep, buildTimeline, renderView, serverBusy, stageText } from "../studio/model";
import { motionSteps } from "../studio/motionModel";
import { mergeEvents } from "../studio/windowing";
import { Setup } from "./Setup";
import type { Capabilities, PanelPreferences, Setup as SetupData } from "./types";
import "./panel.css";

const Workspace = React.lazy(() => import("../studio/Workspace").then(m => ({default: m.Workspace})));
const NativeTimeline = React.lazy(() => import("./NativeTimeline").then(m => ({default: m.NativeTimeline})));
const TimelineView = React.lazy(() => import("../studio/TimelineView").then(m => ({default: m.TimelineView})));
const PanelDiscovery = React.lazy(() => import("./PanelDiscovery").then(m => ({default: m.PanelDiscovery})));
const Speech = React.lazy(() => import("./Speech").then(m => ({default: m.Speech})));
const Resources = React.lazy(() => import("./Resources").then(m => ({default: m.Resources})));
const MotionEditPane = React.lazy(() => import("../studio/MotionWorkspace").then(m => ({default: m.MotionEditPane})));
const AgentRunControls = React.lazy(() => import("../studio/AgentMode").then(m => ({default: m.AgentRunControls})));
const ProjectRender = React.lazy(() => import("../local/ProjectRender").then(m => ({default: m.ProjectRender})));
const PremiereCard = React.lazy(() => import("../PremiereCard").then(m => ({default: m.PremiereCard})));
const Audio = React.lazy(() => import("./Audio").then(m => ({default: m.Audio})));
const RenderProgress = React.lazy(() => import("../studio/RenderProgress").then(m => ({default: m.RenderProgress})));

type View = "preview" | "timeline" | "tools" | "speech" | "audio" | "library" | "assistant";
const views: {id: View; label: string; icon: IconName}[] = [
  {id: "preview", label: "پیش‌نمایش", icon: "eye"}, {id: "timeline", label: "تایم‌لاین", icon: "motion"},
  {id: "tools", label: "ویرایش", icon: "edit"}, {id: "speech", label: "گفتار", icon: "captions"},
  {id: "audio", label: "صدا", icon: "music"}, {id: "library", label: "کتابخانه", icon: "library"}, {id: "assistant", label: "دستیار", icon: "spark"},
];
const ACTIVE = new Set(["queued", "running", "rendering", "planning", "analyzing"]);
const wait = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

function Loading() { return <p className="mp-muted" role="status"><span className="spinner"/> در حال بارگذاری…</p>; }

function PanelHome() {
  const [rows, setRows] = React.useState<StudioConversation[]>([]);
  const [library, setLibrary] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [query, setQuery] = React.useState("");
  const navigate = useNavigate();
  React.useEffect(() => {
    let live = true;
    api.listStudioConversations().then(items => { if (live) setRows(items); })
      .catch(e => { if (live) setError(friendlyError(e, "load your projects")); });
    return () => { live = false; };
  }, []);
  async function create() {
    setBusy(true); setError("");
    try { const row = await api.createPanelDraft(); navigate(`/panel/${row.id}`); }
    catch (e) { setError(friendlyError(e, "create a project")); }
    finally { setBusy(false); }
  }
  return <div className="mp-home">
    <header className="mp-section-head"><div><h1>ادیتور دستی</h1><p>ویدیو بسازید یا یکی از پروژه‌های Studio را باز کنید.</p></div></header>
    <div className="mp-actions">
      <button className="btn btn-primary" disabled={busy} onClick={() => void create()}><Icon name="plus" size={18}/>{busy ? "در حال ساخت…" : "پروژهٔ جدید"}</button>
      <button className="btn btn-secondary" aria-expanded={library} onClick={() => setLibrary(v => !v)}><Icon name="library" size={18}/>کتابخانهٔ خلاقیت</button>
    </div>
    {error && <p className="notice" data-tone="error" role="alert">{error}</p>}
    {library && <React.Suspense fallback={<Loading/>}><Resources/></React.Suspense>}
    <section className="mp-projects">
      <div className="mp-section-head"><h2>پروژه‌های من</h2><input type="search" className="input" aria-label="جستجوی پروژه" placeholder="جستجوی پروژه…" value={query} onChange={e => setQuery(e.target.value)}/></div>
      <div className="mp-engine-grid">
        {rows.filter(item => (item.state?.current_project_id || item.state?.motion || item.state?.discovery || item.state?.panel) && item.title.includes(query.trim())).map(item =>
          <Link key={item.id} className="mp-engine" to={`/panel/${item.id}`}><span className="mp-engine-icon"><Icon name="film" size={20}/></span>
            <span><b dir="auto">{item.title}</b><small>{item.state?.panel && !item.state?.current_project_id && !item.state?.motion && !item.state?.discovery ? "پیش‌نویس" : "باز کردن پروژه"}</small></span>
          </Link>)}
      </div>
    </section>
  </div>;
}

function TimelineDetails({project, refresh, output}: {project: StudioProject; refresh: () => void; output: string}) {
  const [open, setOpen] = React.useState(false);
  return <details className="mp-timeline-details" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>مسیرهای صدا، متن و افکت</summary>
    {open && <TimelineView project={project} onChanged={refresh} currentOutput={output || undefined}/>}
  </details>;
}

function AuthorizedPanel({id}: {id: string}) {
  const [chat, setChat] = React.useState<StudioConversation | null>(null);
  const [capabilities, setCapabilities] = React.useState<Capabilities | null>(null);
  const [events, setEvents] = React.useState<StudioEvent[]>([]);
  const [historyLoaded, setHistoryLoaded] = React.useState(false);
  const [motion, setMotion] = React.useState<MotionGraphic | null>(null);
  const [view, setView] = React.useState<View>("preview");
  const [projectId, setProjectId] = React.useState<string | null>(null);
  const [sourceOnly, setSourceOnly] = React.useState(false);
  const [safe, setSafe] = React.useState(false);
  const [output, setOutput] = React.useState("");
  const [fileVersions, setFileVersions] = React.useState<{file: string; version: number}[]>([]);
  const [motionVersion, setMotionVersion] = React.useState("");
  const [advanced, setAdvanced] = React.useState(false);
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState("");
  const [preferences, setPreferences] = React.useState<PanelPreferences>({});
  const [preferencesLoaded, setPreferencesLoaded] = React.useState(false);
  const [savingPreferences, setSavingPreferences] = React.useState(false);
  const [motionAnswer, setMotionAnswer] = React.useState("");
  const [pendingSeek, setPendingSeek] = React.useState<{seconds: number; play: boolean} | null>(null);
  const video = React.useRef<HTMLVideoElement>(null);
  const request = React.useRef(0);
  const alive = React.useRef(true);
  const setup = chat?.state?.panel?.setup as SetupData | undefined;
  const discoveryId = String(chat?.state?.discovery?.analysis_id || "");
  const motionId = String(chat?.state?.motion?.motion_id || "");
  const projects = chat?.projects ?? [];
  const project = projects.find(row => row.id === (projectId || chat?.state?.current_project_id)) ?? projects[projects.length - 1];
  const currentMotion = !project ? motion : null;
  const workflowMode = preferences.mode || setup?.mode || "manual";
  const agent: AgentMode = preferences.agent_mode || chat?.state?.agent_mode || "lite";
  const isDraft = Boolean(setup && !project && !motionId && !discoveryId);
  const action = chat?.actions?.find(row => row.project_id === project?.id && row.status === "pending");
  const renderActive = Boolean(currentMotion?.active || (project && ACTIVE.has(project.status)));
  const awaitingReview = project?.status === "awaiting_confirmation";
  const waitingForInput = Boolean(awaitingReview || project?.status === "awaiting_input" || currentMotion?.questions?.length && !currentMotion.active);
  const working = renderActive || (!waitingForInput && serverBusy(events, Boolean(chat?.busy)) === true);
  const renderPhase = renderView(project).phase;
  const rendering = Boolean(project && renderActive && (renderPhase === "rendering" || renderPhase === "finalizing"));
  const activity = React.useMemo<ActivityStep[]>(() => {
    if (currentMotion) return motionSteps(currentMotion, Date.now());
    const relevant = events.filter(event => !event.data.project_id || event.data.project_id === project?.id);
    return buildTimeline({ messages: chat?.messages || [], events: relevant, projects: project ? [project] : [], processing: working })
      .flatMap(item => item.kind === "activity" ? item.steps.map(step => ({...step, key: item.id + ":" + step.key})) : []);
  }, [chat?.messages, currentMotion, events, project, working]);
  const currentSteps = activity.filter(step => step.status !== "done");
  const completedSteps = activity.filter(step => step.status === "done");
  const awaitingUpdate = working && !rendering && !currentSteps.some(step => step.status === "active");
  const stage = project?.state?.last_observed?.stage;
  const statusLabel = waitingForInput ? "منتظر شما" : working ? "در حال انجام" :
    project?.status === "error" || currentMotion?.status === "failed" ? "متوقف شده" :
    project?.status === "done" || currentMotion?.status === "completed" ? "آماده" : "بدون پردازش فعال";
  const sourceAttachment = (project?.state?.attachment_ids?.[0] || setup?.attachment_ids?.[0]) as string | undefined;
  const src = project?.engine === "talking" && project.external_ref ? api.rawUrl(project.external_ref)
    : sourceAttachment ? api.studioAttachmentUrl(id, sourceAttachment) : "";
  const motionOutput = currentMotion && (motionVersion || currentMotion.current) ?
    api.motionMediaUrl(motionId, "video", Number(motionVersion || currentMotion.current)) : "";
  const currentOutput = motionOutput || (project && fileVersions.length ? `${api.studioOutputUrl(project.id)}?file=${encodeURIComponent(output || fileVersions[fileVersions.length - 1].file)}` :
    project && (project.status === "done" || project.state?.candidate_output) ?
      api.studioOutputUrl(project.id) + (project.state?.candidate_output && project.status !== "done" ? "?candidate=true" : "") : "");
  const shown = sourceOnly ? src : currentOutput || src;

  const refresh = React.useCallback(async () => {
    const ticket = ++request.current;
    try {
      const value = await api.getStudioConversation(id, {messages: 1});
      if (!alive.current || ticket !== request.current) return;
      setChat(value); setError("");
    } catch (e) {
      if (alive.current && ticket === request.current) setError(friendlyError(e, "open this project"));
    }
  }, [id]);

  React.useEffect(() => {
    alive.current = true;
    void refresh();
    return () => { alive.current = false; request.current++; };
  }, [refresh]);

  React.useEffect(() => {
    if (!isDraft) return;
    let live = true;
    api.panelCapabilities().then(value => { if (live) setCapabilities(value); })
      .catch(e => { if (live) setError(friendlyError(e, "load engines")); });
    return () => {live = false;};
  }, [isDraft]);

  const opened = Boolean(chat && !isDraft);
  React.useEffect(() => {
    if (!opened) return;
    let live = true;
    api.panelPreferences(id).then(value => { if (live) setPreferences(value); })
      .catch(e => { if (live) setError(friendlyError(e, "load editor preferences")); })
      .finally(() => { if (live) setPreferencesLoaded(true); });
    return () => { live = false; };
  }, [id, opened]);

  async function savePreferences(values: PanelPreferences) {
    if (savingPreferences) return;
    setSavingPreferences(true);
    setError("");
    try {
      setPreferences(await api.savePanelPreferences(id, values));
      if (values.mode) setView(values.mode === "manual" ? "preview" : "assistant");
    } catch (e) { setError(friendlyError(e, "save editor preferences")); }
    finally { setSavingPreferences(false); }
  }
  React.useEffect(() => {
    if (!opened) return;
    const controller = new AbortController();
    let cursor = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const sync = () => { if (!timer) timer = setTimeout(() => {timer = undefined; void refresh();}, 450); };
    const loop = async () => {
      try {
        let batch: StudioEvent[];
        do {
          batch = await api.studioEventHistory(id, cursor, controller.signal);
          if (controller.signal.aborted || !batch.length) break;
          cursor = Math.max(cursor, ...batch.map(event => event.seq));
          setEvents(previous => mergeEvents(previous, batch.filter(event => event.type !== "assistant.response.delta")));
        } while (batch.length === 500 && !controller.signal.aborted);
      } catch { /* The event stream can replay any part of history that did not load. */ }
      if (!controller.signal.aborted) setHistoryLoaded(true);
      while (!controller.signal.aborted) {
        try {
          await api.streamStudioEvents(id, cursor, event => {
            if (event.seq <= cursor) return;
            cursor = event.seq;
            if (event.type === "assistant.response.delta") return;
            setEvents(previous => [...previous, event]);
            if (/^(plan|tool|motion|render|project|agent|work)\./.test(event.type)) sync();
          }, controller.signal);
        } catch { if (controller.signal.aborted) break; }
        await wait(2000);
      }
    };
    void loop();
    const poll = setInterval(() => { if (document.visibilityState === "visible") void refresh(); }, 12000);
    return () => { controller.abort(); clearInterval(poll); if (timer) clearTimeout(timer); };
  }, [id, opened, refresh]);

  React.useEffect(() => {
    if (!motionId) return;
    let live = true, timer: ReturnType<typeof setTimeout>;
    const fetch = async () => {
      try { const value = await api.motionView(motionId); if (live) { setMotion(value); if (value.active) timer = setTimeout(fetch, 3200); } }
      catch (e) { if (live) setError(friendlyError(e, "open the motion project")); }
    };
    void fetch();
    return () => {live = false; clearTimeout(timer);};
  }, [motionId, events[events.length - 1]?.seq]);

  React.useEffect(() => {
    if (!project || !["done", "awaiting_confirmation", "error"].includes(project.status)) return;
    let live = true;
    api.studioOutputs(project.id).then(values => { if (live) setFileVersions(values); })
      .catch(() => { if (live) setFileVersions([]); });
    return () => {live = false;};
  }, [project?.id, project?.status, project?.current_version, project?.updated_at]);

  async function run(label: string, fn: () => Promise<unknown>) {
    setBusy(label); setError("");
    try { await fn(); await refresh(); }
    catch (e) { setError(friendlyError(e, label)); }
    finally { setBusy(""); }
  }

  function seek(seconds: number, play = true) {
    setSourceOnly(true);
    const player = video.current;
    if (!player?.readyState || (!sourceOnly && currentOutput)) {
      setPendingSeek({seconds, play});
      return;
    }
    player.currentTime = seconds;
    if (play) void player.play().catch(() => {});
    else player.pause();
  }

  async function download() {
    if (!currentOutput) { setView(project?.state?.panel_native ? "timeline" : "tools"); return; }
    await run("دانلود خروجی", () => api.downloadAuthenticated(currentOutput, `${chat?.title || "video"}.mp4`));
  }

  const available = views.filter(item =>
    (item.id !== "speech" || project?.engine === "talking") && (item.id !== "timeline" || project) &&
    (item.id !== "assistant" || workflowMode !== "manual") && (item.id !== "audio" || project));
  const effective = available.some(item => item.id === view) ? view : "preview";
  const stills = currentMotion?.snapshots || [];

  return <>
    <header className="mp-bar">
      <Link to="/panel" className="mp-bar-back icon-btn" aria-label="پروژه‌ها"><Icon name="projects" size={20}/></Link>
      <div className="mp-bar-title"><b dir="auto">{chat?.title || "ادیتور دستی"}</b><small>{busy || (isDraft ? "پیش‌نویس" : statusLabel)}</small></div>
      <div className="mp-bar-actions">
        <Link reloadDocument to={`/studio/${id}`} className="btn btn-secondary btn-sm"><Icon name="spark" size={16}/><span>چت</span></Link>
        {!isDraft && !discoveryId && <button type="button" className="btn btn-primary btn-sm" disabled={Boolean(busy)} onClick={() => void download()}><Icon name="download" size={16}/>{currentOutput ? "خروجی" : "رندر"}</button>}
      </div>
    </header>
    {error && <p className="mp-error notice" role="alert" data-tone="error">{error}</p>}
    {!chat ? (!error && <Loading/>) : isDraft ? (capabilities && setup ? <Setup id={id} initial={setup} capabilities={capabilities} onStarted={refresh}/> : <Loading/>) : discoveryId ? <div className="mp-home">
      <React.Suspense fallback={<Loading/>}><PanelDiscovery key={discoveryId} id={discoveryId} events={events}/></React.Suspense>
    </div> : <>
      <div className="mp-workspace" data-view={effective}>
        <section className="mp-preview" aria-label="پیش‌نمایش پروژه">
          <div className="mp-section-head"><h2>پیش‌نمایش</h2>
            <button className="icon-btn" title="حاشیهٔ امن" aria-label="حاشیهٔ امن" aria-pressed={safe} onClick={() => setSafe(v => !v)}><Icon name="grid" size={18}/></button></div>
          <div className="mp-monitor">
            {shown ? <>
              <AuthenticatedMedia as="video" key={shown} ref={video} src={shown} controls playsInline preload="none" onLoadedMetadata={(event: React.SyntheticEvent<HTMLVideoElement>) => {
                if (pendingSeek) {
                  event.currentTarget.currentTime = pendingSeek.seconds;
                  if (pendingSeek.play) void event.currentTarget.play().catch(() => {});
                  setPendingSeek(null);
                }
              }}/>
              {safe && <div className="mp-safe" aria-hidden="true"/>}
            </> : <div className="mp-preview-empty"><Icon name="film" size={32}/><p>{renderActive ? "پیش‌نمایش پس از آماده‌شدن می‌آید" : "ویدیویی برای پیش‌نمایش آماده نیست"}</p></div>}
          </div>
          {shown && <div className="mp-actions">
            <button className="btn btn-secondary btn-sm" onClick={() => { if (video.current?.readyState) video.current.currentTime = Math.max(0, video.current.currentTime - 1 / 30); }}>فریم قبل</button>
            <button className="btn btn-secondary btn-sm" onClick={() => { if (video.current?.readyState) video.current.currentTime = Math.min(video.current.duration, video.current.currentTime + 1 / 30); }}>فریم بعد</button>
            {src && currentOutput && <button className="btn btn-secondary btn-sm" aria-pressed={sourceOnly} onClick={() => setSourceOnly(v => !v)}>{sourceOnly ? "دیدن خروجی" : "مقایسه با منبع"}</button>}
          </div>}
          {fileVersions.length > 0 && <label>نسخهٔ خروجی<select className="input" value={output || fileVersions[fileVersions.length - 1]?.file || ""} onChange={e => {setOutput(e.target.value); setSourceOnly(false);}}>
            {[...fileVersions].reverse().map(item => <option key={item.file} value={item.file}>نسخهٔ {item.version}</option>)}
          </select></label>}
          {currentMotion && currentMotion.versions.length > 0 && <label>نسخهٔ موشن<select className="input" value={motionVersion || currentMotion.current} onChange={e => setMotionVersion(e.target.value)}>
            {[...currentMotion.versions].reverse().map(item => <option key={item.n} value={item.n}>نسخهٔ {item.n}</option>)}
          </select></label>}
          {stills.length > 0 && <div className="mp-stills">{stills.map(shot => <AuthenticatedMedia key={shot.n} as="img" loading="lazy" alt={shot.headline} src={api.motionSnapshotUrl(motionId, shot.n)}/>)}</div>}
          {effective !== "preview" && rendering && project && <React.Suspense fallback={<Loading/>}><RenderProgress project={project}/></React.Suspense>}
          {effective !== "preview" && renderActive && <button className="btn btn-secondary btn-sm" disabled={Boolean(busy)} onClick={() => void run("توقف", () =>
            project ? api.cancelStudioProject(project.id) : api.motionStop(motionId))}><Icon name="stop" size={15}/>توقف</button>}
          {effective !== "preview" && !renderActive && currentMotion?.status === "failed" && <button className="btn btn-secondary" onClick={() => void run("ادامهٔ موشن", () => api.motionRetry(motionId))}>تلاش مجدد</button>}
        </section>
        <section className="mp-control" aria-label="کنترل‌های پروژه" data-preview={effective === "preview" || undefined}>
          {effective === "preview" && <section className="mp-activity" aria-label="مراحل کار">
            <div className="mp-activity-head">
              <h2><Icon name="list" size={19}/>مراحل کار</h2>
              <span className="mp-activity-status" data-state={waitingForInput ? "waiting" : working ? "active" : "idle"} role="status">
                {working && <span className="act-dot" aria-hidden="true"/>}{statusLabel}
              </span>
            </div>
            {rendering && project ? <React.Suspense fallback={<Loading/>}><RenderProgress project={project}/></React.Suspense> : null}
            {currentSteps.length > 0 && <ActivityBlock steps={currentSteps} live={working}/>}
            {awaitingUpdate && <ThinkingRow label={stageText(stage) || (historyLoaded ? "در انتظار گزارش موتور" : "در حال دریافت مراحل…")}/>}
            {waitingForInput && <div className="mp-activity-next">
              <span>{awaitingReview ? "برنامهٔ تدوین آمادهٔ بررسی است." : "برای ادامه، پاسخ شما لازم است."}</span>
              {awaitingReview ? <button type="button" className="btn btn-primary btn-sm" onClick={() => setView("tools")}><Icon name="storyboard" size={16}/>بررسی برنامه</button> :
                !currentMotion?.questions?.length && <Link reloadDocument className="btn btn-secondary btn-sm" to={`/studio/${id}`}>باز کردن چت</Link>}
            </div>}
            {completedSteps.length > 0 && <div className="mp-activity-history">
              <ActivityBlock key={`${project?.id || motionId}:${working}`} steps={completedSteps} live={false} initiallyExpanded={!working}/>
            </div>}
            {!historyLoaded && !working && !activity.length && !waitingForInput && <p className="mp-muted" role="status">در حال دریافت مراحل…</p>}
            {renderActive && <button className="btn btn-secondary btn-sm mp-activity-stop" disabled={Boolean(busy)} onClick={() => void run("توقف", () =>
              project ? api.cancelStudioProject(project.id) : api.motionStop(motionId))}><Icon name="stop" size={15}/>توقف</button>}
            {!renderActive && currentMotion?.status === "failed" && <button className="btn btn-secondary btn-sm mp-activity-stop" onClick={() => void run("ادامهٔ موشن", () => api.motionRetry(motionId))}>تلاش مجدد</button>}
          </section>}
          <div className="mp-context">
            {projects.length > 1 && <label>پروژه<select className="input" value={project?.id || ""} onChange={e => {
              setProjectId(e.target.value); setOutput(""); setFileVersions([]); setSourceOnly(false); setPendingSeek(null);
            }}>{projects.map(item => <option value={item.id} key={item.id}>{item.title}</option>)}</select></label>}
            <label>گردش کار<select className="input" value={workflowMode} disabled={!preferencesLoaded || savingPreferences}
              onChange={e => void savePreferences({mode: e.target.value as SetupData["mode"]})}>
              <option value="manual">دستی</option><option value="assisted">با کمک دستیار</option><option value="auto">ساخت خودکار</option>
            </select></label>
            <span className="badge">{project?.engine === "talking" || currentMotion ? "۹:۱۶ پیش‌فرض" : "ابعاد ویدیوی پروژه"}</span>
            <span className="badge">{project?.state?.render_target === "browser" ? "رندر مرورگر" : "رندر سرور"}</span>
          </div>
          <React.Suspense fallback={<Loading/>}>
            {effective === "tools" && (project ? <>
              {action && <div className="mp-approval">
                <span>ساخت خروجی بر اساس استوری‌بورد آمادهٔ تأیید است.</span>
                <button className="btn btn-primary" disabled={Boolean(busy)} onClick={() => void run("تأیید و رندر", () => api.confirmStudioAction(action.id))}>تأیید و رندر</button>
              </div>}
              <Workspace key={project.id} conversation={chat} project={project} projects={[]} onSelectProject={() => {}}
                tab="edit" onTab={() => {}} onCancel={() => void run("توقف", () => api.cancelStudioProject(project.id))}
                onSaved={refresh} showTabs={false}/>
              {project.engine === "motion" && project.external_ref && <details open={advanced} onToggle={e => setAdvanced(e.currentTarget.open)}>
                <summary>خروجی پیشرفته و انتقال به Premiere</summary>
                {advanced && <>
                  <ProjectRender project={project} onChanged={() => void refresh()}/>
                  <PremiereCard id={project.external_ref} renderDone={project.status === "done"}/>
                </>}
              </details>}
            </> : motionId ? <MotionEditPane motionId={motionId} events={events}/> : <p className="mp-muted">ابزاری برای این پروژه هنوز آماده نیست.</p>)}
            {effective === "timeline" && project && <>
              {project.engine === "motion" && <NativeTimeline key={project.id} project={project} refresh={refresh} seek={src && project.state?.panel_native ? seconds => seek(seconds, false) : undefined}/>}
              {project.state?.panel_native
                ? <TimelineDetails project={project} refresh={refresh} output={currentOutput}/>
                : <TimelineView key={project.id} project={project} onChanged={() => void refresh()} currentOutput={currentOutput || undefined}/>}
            </>}
            {effective === "audio" && project && <Audio key={project.id} project={project} refresh={refresh}/>}
            {effective === "speech" && project && <Speech key={project.id} project={project} seek={seek} onChanged={refresh}/>}
            {effective === "library" && <Resources key={project?.id || "library"} projectId={project?.id} job={project?.state?.panel_native ? project.external_ref || undefined : undefined}
              onTools={project ? () => setView("tools") : undefined} onApplied={refresh}/>}
            {effective === "assistant" && <div className="mp-inspector">
              <h2>دستیار پروژه</h2>
              <label>موتور عامل<select className="input" value={agent} disabled={!preferencesLoaded || savingPreferences}
                onChange={e => void savePreferences({agent_mode: e.target.value as AgentMode})}>
                <option value="lite">Lite</option><option value="medium">Medium</option><option value="pro">Pro</option>
              </select></label>
              <div className="mp-actions">{[
                ["بازبینی", "پروژهٔ فعلی را بررسی کن و فقط پیشنهادهای اولویت‌دار و قابل اجرا بده."],
                ["پیشنهاد هوک", "سه هوک کوتاه و دقیق برای محتوای همین پروژه پیشنهاد کن."],
                ["پیشنهاد ریتم", "از داده‌های همین پروژه، پیشنهاد عملی برای بهتر کردن ریتم بده."],
              ].map(([label, content]) => <button className="btn btn-secondary" key={label} disabled={Boolean(busy) || renderActive || !preferencesLoaded || savingPreferences}
                onClick={() => void run(label, () => api.sendStudioMessage(id, content, [], {agent_mode: agent, render_target: "server"}))}>{label}</button>)}</div>
              <AgentRunControls runs={chat.agent_runs || []} onChanged={() => void refresh()}/>
              {chat.messages?.[chat.messages.length - 1]?.role === "assistant" && <p className="mp-reply" dir="auto">{chat.messages[chat.messages.length - 1]?.content}</p>}
              <Link reloadDocument className="btn btn-secondary" to={`/studio/${id}`}>باز کردن چت همین پروژه</Link>
            </div>}
          </React.Suspense>
          {currentMotion?.status === "needs_input" && <form className="mp-motion-question" onSubmit={e => {
            e.preventDefault();
            if (motionAnswer.trim()) void run("پاسخ به سؤال موشن", () => api.answerPanelMotion(id, motionAnswer.trim())).then(() => setMotionAnswer(""));
          }}>
            <p>{currentMotion.questions.join(" ")}</p>
            <input className="input" aria-label="پاسخ به سؤال موتور موشن" value={motionAnswer} onChange={e => setMotionAnswer(e.target.value)}/>
            <button className="btn btn-primary" type="submit" disabled={!motionAnswer.trim() || Boolean(busy)}>ادامه</button>
          </form>}
        </section>
      </div>
      <nav className="mp-tabs" aria-label="ابزارهای ادیتور">
        {available.map(item => <button key={item.id} className="mp-tab" aria-current={effective === item.id ? "true" : undefined}
          onClick={() => setView(item.id)}><Icon name={item.icon} size={20}/><span>{item.label}</span></button>)}
      </nav>
    </>}
  </>;
}

export default function Panel() {
  const {conversationId} = useParams();
  return <div className="manual-panel" dir="rtl">
    {conversationId ? <AuthorizedPanel id={conversationId} key={conversationId}/> : <>
      <header className="mp-bar">
        <span className="brand-mark"><Icon name="spark" size={18}/></span>
        <div className="mp-bar-title"><b>EditorGPT</b></div>
        <Link reloadDocument className="btn btn-secondary btn-sm" to="/studio">استودیو چت</Link>
      </header>
      <PanelHome/>
    </>}
  </div>;
}
