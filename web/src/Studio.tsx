import React from "react";
import { getUser } from "./auth";
import { processingPreferences } from "./local/preferences";
import { verifyLocalBackend } from "./local/backend";
const ProjectRender = React.lazy(() => import("./local/ProjectRender").then(m => ({default:m.ProjectRender})));
import { saveAsset, listAssets, readAsset, removeAsset, saveDraft, loadDraft, mediaMetadata } from "./local/storage";
import { NavLink, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, AgentMode, CloudFile, CloudTransfer, StudioConversation, StudioEvent } from "./api";
import { AgentRunControls } from "./studio/AgentMode";
import { useAuth } from "./auth/AuthContext";
import { Icon } from "./components/Icon";
import { useStudioLayout } from "./components/hooks";
import { useTopbarTitle } from "./components/ShellContext";
import { displayTitle, parseTime, relativeTime } from "./format";
import { friendlyError } from "./ui";
import { Resizer, usePanelWidth } from "./components/Resizer";
import { useMotionActive } from "./studio/MotionGraphic";
import { useDiscoveryActive } from "./studio/Discovery";
import { Composer, PendingFile } from "./studio/Composer";
import { CloudPicker } from "./studio/CloudPicker";
import { ManualQuestion } from "./studio/ManualQuestion";
import { Thread, LocalFileInfo } from "./studio/Thread";
import { Workspace, WorkspaceTab, advancedEditorUrl } from "./studio/Workspace";
import { currentVersion, planPhase } from "./studio/plan";
import { PendingMessage, TimelineItem, activeStep, buildTimeline, isProcessing, renderView, serverBusy, thinkingLabel } from "./studio/model";
import { suggestions, templatePrompts } from "./templateData";

type MobileView = "chat" | WorkspaceTab;
const WORKSPACE_BOUNDS = { min: 340, max: 1100 };
/** The chat keeps at least this much room, so the workspace cannot be dragged over it. */
const MIN_CHAT = 360;
const lsGet = (key: string, fallback: string) => { try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; } };
const lsSet = (key: string, value: string) => { try { localStorage.setItem(key, value); } catch { /* storage unavailable */ } };

function cloudNote(transfer: CloudTransfer): string | undefined {
  const mb = (value: number | null) => value ? `${(value / 1024 ** 2).toFixed(value > 10 * 1024 ** 2 ? 0 : 1)} MB` : "";
  if (transfer.state === "queued") return "Waiting to start…";
  if (transfer.state === "connecting" || transfer.state === "fetching_metadata") return "Asking Google Drive for the file… this can take up to a minute";
  if (transfer.state === "validating") return "Checking the file…";
  if (transfer.state === "downloading") {
    const speed = transfer.speed ? ` · ${(transfer.speed / 1024 ** 2).toFixed(2)} MB/s` : "";
    return transfer.bytes ? `${mb(transfer.bytes)}${transfer.size ? ` of ${mb(transfer.size)}` : ""}${speed}` : "Starting the download…";
  }
  return undefined;
}

export default function Studio() {
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { authenticated, openAuth } = useAuth();
  const layout = useStudioLayout();

  const [conversations, setConversations] = React.useState<StudioConversation[]>([]);
  const [conversation, setConversation] = React.useState<StudioConversation | null>(null);
  const [events, setEvents] = React.useState<StudioEvent[]>([]);
  const [text, setText] = React.useState(() => searchParams.get("prompt") || templatePrompts[searchParams.get("template") || ""] || "");
  const [files, setFiles] = React.useState<PendingFile[]>([]);
  const [cloudOpen, setCloudOpen] = React.useState(false);

  const [sending, setSending] = React.useState(false);
  const [error, setError] = React.useState("");
  const [pending, setPending] = React.useState<PendingMessage | null>(null);
  const [localFiles, setLocalFiles] = React.useState<LocalFileInfo[]>([]);
  const [listening, setListening] = React.useState(false);
  const [manualDraft, setManualDraft] = React.useState(false);
  const [agentMode, setAgentMode] = React.useState<AgentMode>("lite");
  const agentChoice = React.useRef<{conversation: string | null; mode: AgentMode} | null>(null);
  const modeOwner = conversationId || "new";
  React.useEffect(() => {
    let live = true;
    agentChoice.current = null;
    if (conversationId) {
      setAgentMode("lite");
    } else if (authenticated) {
      void api.agentPreferences().then(value => {
        if (live && !agentChoice.current) setAgentMode(value.default_agent_mode);
      }).catch(() => {if (live && !agentChoice.current) setAgentMode("lite");});
    }
    return () => {live = false;};
  }, [modeOwner, authenticated]);
  const [modeSaving, setModeSaving] = React.useState(false);
  const [submittedQuestionId, setSubmittedQuestionId] = React.useState<string | null>(null);
  const [wsTab, setWsTab] = React.useState<WorkspaceTab>("preview");
  const [desktopOpen, setDesktopOpen] = React.useState(() => lsGet("editorgpt.workspace", "open") !== "closed");
  const [overlayOpen, setOverlayOpen] = React.useState(false);
  const [mobileView, setMobileView] = React.useState<MobileView>("chat");
  const [selectedProject, setSelectedProject] = React.useState<string | null>(null);
  const [stuck, setStuck] = React.useState(true);
  const [now, setNow] = React.useState(() => Date.now());

  const studioRef = React.useRef<HTMLDivElement>(null);
  const workspaceRef = React.useRef<HTMLElement>(null);
  const [workspaceWidth, setWorkspaceWidth] = usePanelWidth("editorgpt.workspace.width", WORKSPACE_BOUNDS);
  const [liveWorkspace, setLiveWorkspace] = React.useState<number | null>(null);
  const [resizingWorkspace, setResizingWorkspace] = React.useState(false);
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);
  const cursorRef = React.useRef(0);
  const filesRef = React.useRef<PendingFile[]>([]);
  const removedFilesRef = React.useRef(new Set<string>());
  const voiceEnabledRef = React.useRef(false);
  const legacyOpenRef = React.useRef("");
  const refreshTimerRef = React.useRef<number | null>(null);
  const listTimerRef = React.useRef<number | null>(null);
  const lastSendRef = React.useRef<{ text: string; ids: string[] } | null>(null);
  const logoUploadRef = React.useRef(false);
  // Conversation created only so attachments have somewhere to upload; we don't navigate until the user sends.
  const draftIdRef = React.useRef<string | null>(null);
  const activeId = conversationId || null;
  React.useEffect(() => {
    if (conversation?.id !== activeId || !activeId || agentChoice.current?.conversation === activeId) return;
    setAgentMode(conversation.state.agent_mode === "medium" ? "medium" : "lite");
  }, [conversation?.id, conversation?.state.agent_mode, activeId]);
  const changeAgentMode = (next: AgentMode) => {
    agentChoice.current = {conversation: activeId, mode: next};
    setAgentMode(next);
    // The request captures this value separately; switching never changes an active run.
    const id = activeId || draftIdRef.current;
    if (id) void api.updateStudioConversation(id, {agent_mode: next})
      .catch(() => setError("انتخاب موتور ذخیره نشد؛ پیام بعدی همچنان با انتخاب فعلی ارسال می‌شود."));
  };
  const localOwner = getUser()?.id || "guest";
  const localProject = activeId || "new";
  const draftKey = `${localOwner}:${localProject}`;
  const previousDraftKey = React.useRef(draftKey);
  const [loadedDraftKey, setLoadedDraftKey] = React.useState("");
  React.useEffect(() => {
    let live = true;
    if (previousDraftKey.current !== draftKey) {
      setText("");
      setFiles(previous => { previous.forEach(file=>URL.revokeObjectURL(file.url)); return []; });
    }
    previousDraftKey.current = draftKey;
    void loadDraft(draftKey).then(value => { if (live && value) setText(previous => previous || value); }).catch(() => {}).finally(() => { if (live) setLoadedDraftKey(draftKey); });
    void listAssets(localOwner, localProject).then(async records => {
      for (const record of records) {
        try {
          const file = await readAsset(record);
          if (live) setFiles(previous => previous.some(f => f.localId === record.id) ? previous : [...previous, { key: record.id, localId: record.id, file, progress: -1, url: URL.createObjectURL(file) }]);
        } catch { if (live) setError("Some local media was removed by the browser; select the original again."); }
      }
    }).catch(() => {});
    return () => { live = false; };
  }, [draftKey]);
  React.useEffect(() => { if (loadedDraftKey !== draftKey) return; const timer = setTimeout(() => { void saveDraft(draftKey, text).catch(() => {}); }, 400); return () => clearTimeout(timer); }, [draftKey, text, loadedDraftKey]);
  const hasSpeech = typeof window !== "undefined" && Boolean((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);

  React.useEffect(() => { voiceEnabledRef.current = Boolean(conversation?.status_voice_enabled); }, [conversation?.status_voice_enabled]);
  React.useEffect(() => { filesRef.current = files; }, [files]);
  React.useEffect(() => { const id = window.setInterval(() => setNow(Date.now()), 15000); return () => window.clearInterval(id); }, []);

  const refreshList = React.useCallback(() => authenticated ? api.listStudioConversations().then(setConversations).catch(() => undefined) : Promise.resolve(), [authenticated]);
  // `quiet` is for background updates (a live event arrived, the tab came back): a dropped connection there is not worth an error, the next update catches up.
  const refresh = React.useCallback(async (id = activeId, quiet = false) => {
    if (!id) return;
    try { setConversation(await api.getStudioConversation(id)); } catch (e) { if (!quiet) setError(friendlyError(e, "load conversation")); }
  }, [activeId]);
  React.useEffect(() => { void refreshList(); }, [refreshList]);
  React.useEffect(() => {
    setEvents([]); cursorRef.current = 0; setSelectedProject(null);
    if (authenticated && activeId) void refresh(activeId); else setConversation(null);
  }, [authenticated, activeId, refresh]);

  React.useEffect(() => {
    const legacy = searchParams.get("legacy");
    if (!legacy || !authenticated || legacyOpenRef.current === legacy) return;
    const [engine, externalRef] = legacy.split(":", 2);
    if (!externalRef || !["motion", "talking", "localize"].includes(engine)) return;
    legacyOpenRef.current = legacy;
    setSending(true);
    void api.openLegacyInStudio(engine as "motion" | "talking" | "localize", externalRef, searchParams.get("title") || "Video project")
      .then(value => { setConversation(value); navigate(`/studio/${value.id}`, { replace: true }); })
      .catch(e => setError(friendlyError(e, "open project"))).finally(() => setSending(false));
  }, [authenticated, navigate, searchParams]);

  // Live events (SSE) with cursor-based reconnect.
  React.useEffect(() => {
    if (!activeId) return;
    const controller = new AbortController(); let stopped = false;
    let connection: AbortController | null = null;      // the current live connection; replaced when the tab comes back, its socket is likely dead
    const resume = () => {
      if (document.visibilityState === "hidden" || stopped) return;
      connection?.abort();
      void refresh(activeId, true);
    };
    controller.signal.addEventListener("abort", () => connection?.abort(), { once: true });
    document.addEventListener("visibilitychange", resume);
    window.addEventListener("online", resume);
    window.addEventListener("pageshow", resume);
    const connect = async () => {
      try {
        while (!stopped) {
          const history = await api.studioEventHistory(activeId, cursorRef.current, controller.signal);
          if (stopped) return;
          if (history.length) {
            cursorRef.current = Math.max(cursorRef.current, ...history.map(event => event.seq));
            setEvents(value => [...value, ...history.filter(event => !value.some(item => item.seq === event.seq))]);
          }
          if (history.length < 500) break;
        }
      } catch { /* Older servers can still replay through the existing SSE cursor. */ }
      while (!stopped) {
        try {
          connection = new AbortController();
          await api.streamStudioEvents(activeId, cursorRef.current, event => {
            cursorRef.current = Math.max(cursorRef.current, event.seq);
            setEvents(value => value.some(item => item.seq === event.seq) ? value : [...value, event]);
            if (refreshTimerRef.current != null) window.clearTimeout(refreshTimerRef.current);
            refreshTimerRef.current = window.setTimeout(() => void refresh(activeId, true), 180);
            if (listTimerRef.current == null) listTimerRef.current = window.setTimeout(() => {
              listTimerRef.current = null; void refreshList(); window.dispatchEvent(new Event("editorgpt:conversations-updated"));
            }, 1200);
            if (event.type === "narration.ready" && voiceEnabledRef.current) void api.authenticatedObjectUrl(api.studioEventAudioUrl(activeId, event.data.event_seq)).then(url => { const audio = new Audio(url); void audio.play().finally(() => URL.revokeObjectURL(url)); });
          }, connection.signal);
        } catch { if (!controller.signal.aborted) await new Promise(resolve => setTimeout(resolve, connection?.signal.aborted ? 150 : 1200)); }
      }
    };
    void connect();
    return () => {
      stopped = true; controller.abort();
      document.removeEventListener("visibilitychange", resume);
      window.removeEventListener("online", resume);
      window.removeEventListener("pageshow", resume);
      if (refreshTimerRef.current != null) window.clearTimeout(refreshTimerRef.current);
      if (listTimerRef.current != null) window.clearTimeout(listTimerRef.current);
      refreshTimerRef.current = null; listTimerRef.current = null;
    };
  }, [activeId, refresh, refreshList]);
  React.useEffect(() => () => filesRef.current.forEach(item => item.url && URL.revokeObjectURL(item.url)), []);

  // ── derived state ────────────────────────────────────────────
  const projects = conversation?.projects || [];
  const linkTitles: Record<string,string> = {};
  for (const project of projects) {
    const page = project.state?.url_inspection;
    if (page?.url && page?.title) linkTitles[page.url] = String(page.title);
  }
  for (const event of events) {
    if (event.data.source_url && event.data.source_title) linkTitles[String(event.data.source_url)] = String(event.data.source_title);
  }
  const current = projects.find(item => item.id === (selectedProject || conversation?.state?.current_project_id)) || projects[projects.length - 1];
  const manual = conversation ? conversation.state.execution_mode === "manual" : manualDraft;
  const checkpoint = current?.state?.manual_checkpoint;
  const rawManualQuestion = checkpoint ? (checkpoint.claimed ? null : checkpoint) : conversation?.state?.manual_question;
  const manualQuestion = rawManualQuestion?.id === submittedQuestionId ? null : rawManualQuestion;
  const toggleManual = async () => {
    if (modeSaving) return;
    if (!authenticated) { openAuth("login"); return; }
    if (!conversation) { setManualDraft(!manualDraft); return; }
    setModeSaving(true);
    try { await api.updateStudioConversation(conversation.id, { execution_mode: manual ? "auto" : "manual" }); await refresh(); }
    catch (e) { setError(friendlyError(e, "change execution mode")); }
    finally { setModeSaving(false); }
  };
  const pendingAction = (conversation?.actions || []).find(item => item.project_id === current?.id && item.status === "pending");
  const [resuming, setResuming] = React.useState(false);
  const phase = planPhase(current);
  const planVersion = currentVersion(current);
  const awaitingPlan = current?.engine === "talking" && phase === "awaiting" ? planVersion : undefined;
  const approvePlan = async () => {
    if (!current || !awaitingPlan || resuming) return;
    setResuming(true); setError("");
    try { await api.approveStudioPlan(current.id, awaitingPlan.id); await refresh(); }
    catch (e) { setError(friendlyError(e, "approve the plan")); }
    finally { setResuming(false); }
  };
  // A new plan version waiting for approval brings the Edit tab (where the plan lives) forward; the panel opens on desktop only.
  const shownPlanRef = React.useRef("");
  React.useEffect(() => {
    if (!awaitingPlan || shownPlanRef.current === awaitingPlan.id) return;
    shownPlanRef.current = awaitingPlan.id;
    setWsTab("edit");
    if (layout === "desktop") { setDesktopOpen(true); lsSet("editorgpt.workspace", "open"); }
  }, [awaitingPlan?.id, layout]);
  const qualityBlocked = current?.engine === 'talking' && ['error','awaiting_confirmation'].includes(current?.status || '') && Boolean(current?.state?.candidate_output) && !current?.state?.last_observed?.output;
  const acceptOutput = async () => {
    if (!current || resuming) return;
    setResuming(true); setError('');
    try { await api.acceptStudioOutput(current.id, current.state.candidate_output); await refresh(); openWorkspace('preview', current.id); }
    catch (e) { setError(friendlyError(e, 'accept output')); }
    finally { setResuming(false); }
  };
  const [askResume, setAskResume] = React.useState(false);       // window.confirm can be silently blocked: ask inline
  const resume = async () => {
    if (!current || resuming) return;
    setAskResume(false);
    setResuming(true); setError("");
    try { await api.resumeStudioProject(current.id,true); await refresh(); }
    catch (e) { setError(friendlyError(e, "continue this project")); }
    finally { setResuming(false); }
  };
  const styles = current?.state?.styles || [];
  const sourceAttachment = current?.state?.attachment_ids?.[0];
  const messages = conversation?.messages || [];
  const lastUserMessage = [...messages].reverse().find(message => message.role === 'user');
  const motionActive = useMotionActive(conversation?.state?.motion?.motion_id, events);
  const discoveryActive = useDiscoveryActive(conversation?.state?.discovery?.analysis_id, events);
  const projectRunning = projects.some(project => project.status === "running");
  const busyOnServer = serverBusy(events, conversation?.busy);
  const processing = isProcessing({ sending, messages, events, project: current, now }) || motionActive || discoveryActive || projectRunning || busyOnServer === true;
  // The live stream can be held back by a proxy or a mobile network (nothing arrives until a reload): also ask for new events every few seconds.
  React.useEffect(() => {
    if (!activeId) return;
    let alive = true;
    const timer = window.setInterval(async () => {
      if (document.visibilityState === "hidden") return;
      try {
        const history = await api.studioEventHistory(activeId, cursorRef.current, new AbortController().signal);
        if (!alive || !history.length) return;
        cursorRef.current = Math.max(cursorRef.current, ...history.map(event => event.seq));
        setEvents(value => [...value, ...history.filter(event => !value.some(item => item.seq === event.seq))]);
        void refresh(activeId, true);
      } catch { /* the stream or the next poll will catch up */ }
    }, processing ? 2000 : 4000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [activeId, processing, refresh]);
  const items = React.useMemo(() => buildTimeline({ messages, events, projects, pending, processing, discoveryId: conversation?.state?.discovery?.analysis_id, motionId: conversation?.state?.motion?.motion_id }), [messages, events, projects, pending, processing, conversation?.state?.discovery?.analysis_id, conversation?.state?.motion?.motion_id]);
  // A live render card is its own progress indicator; otherwise show what the assistant is doing.
  const renderLive = items.some(item => item.kind === "render" && ["queued", "rendering", "finalizing"].includes(renderView(projects.find(p => p.id === item.projectId)).phase));
  // While the render card shows the real progress (the same block as the Preview and Edit tabs), the render steps of the activity log
  // ("planning render 35%") would only repeat it, and they stay stuck at their last report: they are left out until the render ends.
  const shown = React.useMemo<TimelineItem[]>(() => {
    if (!renderLive) return items;
    const kept: TimelineItem[] = [];
    for (const item of items) {
      if (item.kind !== "activity") { kept.push(item); continue; }
      const steps = item.steps.filter(entry => !/render/i.test(`${entry.tool || ""} ${entry.stage || ""}`));
      if (steps.length) kept.push({ ...item, steps });
    }
    return kept;
  }, [items, renderLive]);
  const step = activeStep(shown);
  const thinking = processing && !step && !renderLive ? thinkingLabel(events, messages) : undefined;
  const showConversation = Boolean(activeId) || Boolean(pending);
  const title = conversation?.title ? displayTitle(conversation.title, 60) : "New edit";
  useTopbarTitle(showConversation ? title : "");
  const announcement = step ? `${step.label}` : thinking ? `${thinking}` : processing ? "Working" : "";
  const sourceUrl = conversation && sourceAttachment ? api.studioAttachmentUrl(conversation.id, sourceAttachment) : undefined;
  const canStop = processing && Boolean(conversationId);

  // ── scrolling: stick to bottom unless the reader scrolled up ──
  const onScroll = () => { const node = scrollRef.current; if (node) setStuck(node.scrollHeight - node.scrollTop - node.clientHeight < 140); };
  React.useLayoutEffect(() => {
    const node = scrollRef.current; if (!node || !stuck) return;
    node.scrollTo({ top: node.scrollHeight, behavior: "auto" });
  }, [items, thinking, stuck, pendingAction, mobileView]);
  const jumpToLatest = () => { setStuck(true); scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" }); };

  // ── actions ──────────────────────────────────────────────────
  const requireLogin = () => openAuth("login");
  async function ensureConversation(titleText = "گفتگوی جدید", go = true) {
    if (activeId) return activeId;
    let id = draftIdRef.current;
    if (!id) { id = (await api.createStudioConversation(titleText)).id; draftIdRef.current = id; }
    if (go) { draftIdRef.current = null; navigate(`/studio/${id}`, { replace: true }); void refreshList(); }
    return id;
  }
  async function addFiles(input: FileList | File[]) {
    const list = Array.from(input); // snapshot: a live FileList can be emptied while we await
    if (!authenticated) { requireLogin(); return; }
    const autoLogo = manualQuestion?.key === "logo_asset";
    if (autoLogo && (logoUploadRef.current || sending)) return;
    if (autoLogo && (list.length !== 1 || !list[0].type.startsWith("image/"))) {
      setError("برای لوگو فقط یک تصویر انتخاب کنید."); return;
    }
    if (autoLogo) logoUploadRef.current = true;
    setError("");
    for (const file of list.slice(0, 12)) {
      const key = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      const entry: PendingFile = { key, file, progress: processingPreferences().mode === "online" ? 0 : -1, url: URL.createObjectURL(file) };
      setFiles(value => [...value, entry]);
      if (processingPreferences().mode !== "online") try {
        const saved = await saveAsset(file, localOwner, localProject);
        entry.localId = saved.id;
        if (removedFilesRef.current.has(key)) { await removeAsset(saved.id, localOwner); continue; }
        setFiles(value => value.map(item => item.key === key ? { ...item, localId: saved.id } : item));
      } catch (e) { setFiles(value => value.map(item => item.key === key ? { ...item, localNote: `Session only: ${String(e)}` } : item)); }
      void mediaMetadata(file).then(meta => setFiles(value => value.map(item => item.key === key ? { ...item, localNote: `${meta.width}×${meta.height}${Number.isFinite(meta.duration) && meta.duration ? ` · ${Math.round(meta.duration)}s` : ""}` } : item))).catch(() => {});
      const online = processingPreferences().mode === "online";
      if (!autoLogo && !online) continue;
      try {
        if (autoLogo && !online && !confirm("Upload this logo to the current project and continue?")) continue;
        const id = await ensureConversation("New media edit", false);
        setFiles(value => value.map(item => item.key === key ? {...item,progress:0} : item));
        const attachment = await api.uploadStudioMedia(id, file, progress => setFiles(value => value.map(item => item.key === key ? { ...item, progress } : item)));
        setFiles(value => value.map(item => item.key === key ? { ...item, progress: 100, attachmentId: attachment.id } : item));
        if (autoLogo) {
          await send(undefined, { text: "attached", ids: [attachment.id] });
          if (entry.localId) void removeAsset(entry.localId, localOwner).catch(() => {});
          setFiles(value => value.filter(item => item.key !== key));
          URL.revokeObjectURL(entry.url);
        }
      } catch (e) { setError(friendlyError(e, "upload attachment")); setFiles(value => value.filter(item => item.key !== key)); URL.revokeObjectURL(entry.url); }
    }
    if (autoLogo) logoUploadRef.current = false;
  }
  async function importCloud(picked: CloudFile[]) {
    if (!authenticated) { requireLogin(); return; }
    const id = await ensureConversation("New media edit", false);
    const result = await api.cloudImport("googledrive", id, picked.map(file => file.id));
    if (result.errors.length) setError(result.errors.map(item => item.message).join(" "));
    const entries: PendingFile[] = result.transfers.map(transfer => {
      const source = picked.find(file => file.id === transfer.file_id);
      const done = transfer.state === "completed" && !!transfer.attachment_id;
      return { key: `cloud-${transfer.id}`, file: new File([], transfer.filename, { type: source?.mime_type || "" }), url: "", progress: done ? 100 : 0,
        attachmentId: done ? transfer.attachment_id! : undefined, localNote: transfer.reused ? "Already imported" : undefined,
        cloud: { transferId: transfer.id, provider: "googledrive", conversationId: id, size: transfer.size || source?.size || 0 } };
    });
    setFiles(value => [...value, ...entries]);
  }
  const cloudWaiting = files.filter(item => item.cloud && !item.attachmentId).map(item => item.key).join(",");
  React.useEffect(() => {
    if (!cloudWaiting) return;
    const timer = window.setInterval(async () => {
      for (const entry of filesRef.current.filter(item => item.cloud && !item.attachmentId)) {
        try {
          const transfer = await api.cloudTransfer(entry.cloud!.conversationId, entry.cloud!.transferId);
          if (transfer.state === "completed") setFiles(value => value.map(item => item.key === entry.key ? { ...item, attachmentId: transfer.attachment_id || undefined, progress: 100, localNote: undefined } : item));
          else if (transfer.state === "failed" || transfer.state === "cancelled") {
            setFiles(value => value.filter(item => item.key !== entry.key));
            if (transfer.state === "failed") setError(`${transfer.filename}: ${transfer.error || "The import failed."}`);
          } else setFiles(value => value.map(item => item.key === entry.key ? { ...item, progress: transfer.size && transfer.bytes ? Math.min(99, (transfer.bytes / transfer.size) * 100) : 0,
            localNote: cloudNote(transfer) } : item));
        } catch { /* the next tick asks again */ }
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [cloudWaiting]);
  function removeFile(file: PendingFile) { if (file.cloud && !file.attachmentId) void api.cloudCancel(file.cloud.conversationId, file.cloud.transferId).catch(() => {}); removedFilesRef.current.add(file.key); setFiles(value => value.filter(item => item.key !== file.key)); URL.revokeObjectURL(file.url); if (file.localId) void removeAsset(file.localId, localOwner).catch(() => {}); }

  async function send(override?: string, resend?: { text: string; ids: string[] }) {
    const submittedAgentMode = agentMode; // snapshot before uploads/navigation or an active-job mode switch
    if (!authenticated) { requireLogin(); return; }
    const source = resend?.text ?? override ?? text;
    const ids = resend?.ids ? [...resend.ids] : files.map(item => item.attachmentId!).filter(Boolean);
    const finalText = source.trim() || (ids.length || files.length ? (manualQuestion?.key === "logo_asset" ? "attached" : "این فایل را بررسی کن و برای تدوین آماده کن") : "");
    if (!finalText || sending) return;
    const processing = processingPreferences();
    const deviceRender = processing.engine === "device" || (processing.mode === "device" && processing.engine === "auto");
    if (deviceRender) {
      try {
        const capabilities = await api.projectRenderCapabilities();
        if (!capabilities.device_render_hold) throw new Error("This backend needs an update before safe device rendering. Nothing has been uploaded.");
      } catch (error) { setError(error instanceof Error ? error.message : String(error)); return; }
    }
    if (processing.mode === "lan" || processing.engine === "lan") {
      try { await verifyLocalBackend(); }
      catch (error) { setError(error instanceof Error ? error.message : String(error)); return; }
    }
    if (!resend && files.some(item => !item.attachmentId && !item.cloud)) {
      const pendingFiles = files.filter(item => !item.attachmentId && !item.cloud);
      const mb = Math.round(pendingFiles.reduce((sum, f) => sum + f.file.size, 0) / 1024**2);
      const destination = processing.mode === "lan" || processing.engine === "lan" ? `your Mac’s EditorGPT backend (${location.origin}), not the EditorGPT cloud` : `this installation’s backend (${location.origin})`;
      if (!confirm(`AI editing needs ${pendingFiles.length} file(s), ${mb} MB, transferred to ${destination}. AI providers may receive text, frames or audio required for analysis. Render choice is separate. Allow this transfer? Cancel keeps the originals on this device.`)) return;
      setSending(true);
      try {
        const id = await ensureConversation(finalText.slice(0, 70), false);
        for (const entry of pendingFiles) {
          const attached = await api.uploadStudioMedia(id, entry.file, progress => setFiles(value => value.map(item => item.key === entry.key ? { ...item, progress } : item)));
          ids.push(attached.id);
          setFiles(value => value.map(item => item.key === entry.key ? { ...item, attachmentId: attached.id, progress: 100 } : item));
        }
      } catch (e) { setError(friendlyError(e, "upload media")); setFiles(value => value.map(item => item.attachmentId ? item : { ...item, progress: -1 })); setSending(false); return; }
      setSending(false);
    }
    // Show the message and the processing state immediately.
    setError(""); setSending(true); setStuck(true);
    if (!resend) {
      setLocalFiles(files.map(item => ({ name: item.file.name, type: item.file.type, url: item.url })));
      setFiles([]); setText("");
    }
    setPending({ id: `pending-${Date.now()}`, content: finalText, attachments: ids, createdAt: Date.now() });
    lastSendRef.current = { text: finalText, ids };
    try {
      const id = await ensureConversation(finalText.slice(0, 70));
      await api.sendStudioMessage(id, finalText, ids, { execution_mode: conversation || !activeId ? (manual ? "manual" : "auto") : undefined, manual_question_id: manualQuestion?.id,
        render_target: deviceRender ? "browser" : "server", agent_mode: submittedAgentMode });
      void saveDraft(draftKey, "").catch(() => {});
      files.forEach(file => { removedFilesRef.current.add(file.key); if (file.localId) void removeAsset(file.localId, localOwner).catch(() => {}); });
      if (manualQuestion?.id && (finalText === 'approve' || (manualQuestion.key === 'logo_asset' && finalText === 'attached'))) setSubmittedQuestionId(manualQuestion.id);
      await refresh(id);
      setPending(null); setLocalFiles(list => { list.forEach(file => URL.revokeObjectURL(file.url)); return []; });
    } catch (e) {
      setPending(value => value ? { ...value, failed: true } : value);
      setError(friendlyError(e, "send message"));
    } finally { setSending(false); }
  }
  const retryMessage = () => { if (lastSendRef.current) void send(undefined, lastSendRef.current); };
  const stop = () => { if (conversationId) void api.stopConversation(conversationId).then(() => refresh()).catch(e => setError(friendlyError(e, "stop"))); };

  function startVoiceInput() {
    const Speech = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!Speech) return;
    const recognition = new Speech(); recognition.lang = document.documentElement.lang === "en" ? "en-US" : "fa-IR"; recognition.interimResults = true;
    recognition.onstart = () => setListening(true); recognition.onend = () => setListening(false);
    recognition.onresult = (event: any) => setText(Array.from(event.results).map((result: any) => result[0].transcript).join(" "));
    recognition.onerror = () => { setListening(false); setError("Voice input could not start. Check microphone access."); };
    recognition.start();
  }

  // ── workspace visibility per layout ──────────────────────────
  const openWorkspace = (tab: WorkspaceTab, projectId?: string) => {
    if (projectId) setSelectedProject(projectId);
    setWsTab(tab);
    if (layout === "desktop") { setDesktopOpen(true); lsSet("editorgpt.workspace", "open"); }
    else if (layout === "tablet") setOverlayOpen(true);
    else setMobileView(tab);
  };
  const closeWorkspace = () => {
    if (layout === "desktop") { setDesktopOpen(false); lsSet("editorgpt.workspace", "closed"); }
    else if (layout === "tablet") setOverlayOpen(false);
    else setMobileView("chat");
  };
  React.useEffect(() => {
    if (layout !== "tablet") setOverlayOpen(false);
    // Keep the last mobile tab across breakpoint changes. Native fullscreen
    // exits before its resize settles, so a document.fullscreenElement guard
    // alone would still reset Preview/Edit to Chat during that transition.
  }, [layout]);
  React.useEffect(() => {
    if (!overlayOpen || layout !== "tablet") return;
    const key = (event: KeyboardEvent) => { if (event.key === "Escape") setOverlayOpen(false); };
    document.addEventListener("keydown", key); return () => document.removeEventListener("keydown", key);
  }, [overlayOpen, layout]);
  const editAgain = (projectId: string) => { openWorkspace("edit", projectId); };
  const wsVisible = layout === "desktop" ? desktopOpen : layout === "tablet" ? overlayOpen : mobileView !== "chat";
  const mobileTab = layout === "mobile" ? (mobileView === "chat" ? "chat" : wsTab) : null;

  const composer = (variant: "home" | "dock") => <><Composer variant={variant} text={text} setText={setText} files={files} onRemoveFile={removeFile} onFiles={addFiles}
    agentMode={agentMode} onAgentModeChange={changeAgentMode}
    manual={manual} onManualChange={modeSaving ? undefined : () => void toggleManual()}
    processing={processing} onStop={canStop ? stop : undefined} onSend={() => void send()} error={error} onDismissError={() => setError("")}
    hasSpeech={hasSpeech} listening={listening} onListen={startVoiceInput} textareaRef={textareaRef} autoFocus={variant === "home" && layout !== "mobile"}
    onCloud={authenticated && processingPreferences().mode === "online" ? () => setCloudOpen(true) : undefined}/>
    {cloudOpen ? <CloudPicker onClose={() => setCloudOpen(false)} onImport={importCloud}/> : null}</>;

  if (!showConversation) return <div className="studio-home">
    <div className="home-inner">
      <h1>What would you like to create?</h1>
      {composer("home")}
      <div className="chip-row home-chips">{suggestions.map(item => <button key={item} className="chip" onClick={() => { setText(item); textareaRef.current?.focus(); }}>{item}</button>)}</div>
      {authenticated && conversations.length ? <section className="home-recent" aria-label="Recent projects">
        <div className="home-recent-head"><h2>Recent</h2><NavLink to="/projects">View all</NavLink></div>
        <ul>{[...conversations].sort((a, b) => parseTime(b.updated_at) - parseTime(a.updated_at)).slice(0, 3).map(item => <li key={item.id}><NavLink to={`/studio/${item.id}`} title={item.title}><span className="bidi wrap-safe" dir="auto">{displayTitle(item.title, 60)}</span><small>{relativeTime(parseTime(item.updated_at), now)}</small><Icon name="chevron" size={16}/></NavLink></li>)}</ul>
      </section> : null}
      {!authenticated ? <p className="home-note">Log in to save projects and start creating.</p> : null}
    </div>
  </div>;

  const shownWorkspace = liveWorkspace ?? workspaceWidth;
  return <div className="studio" ref={studioRef} data-layout={layout} data-ws={wsVisible ? "open" : "closed"} data-view={mobileView} data-resizing={resizingWorkspace || undefined}
    style={layout === "desktop" && wsVisible && shownWorkspace ? { ["--ws-w" as string]: `${shownWorkspace}px` } : undefined}>
    <section className="chat-col" aria-label="Conversation" hidden={layout === "mobile" && mobileView !== "chat"}>
      {layout !== "mobile" ? <header className="chat-head">
        <h1 className="chat-title bidi wrap-safe" dir="auto" title={conversation?.title}>{title}</h1>
        {!wsVisible ? <button className="btn btn-sm btn-secondary" onClick={() => openWorkspace(wsTab)}><Icon name="panelRight" size={16}/>Preview</button> : null}
      </header> : null}
      <div className="chat-scroll" ref={scrollRef} onScroll={onScroll}>
        <div className="chat-inner">
          {current ? <React.Suspense fallback={null}><ProjectRender key={current.id} project={current} onChanged={()=>void refresh()}/></React.Suspense> : null}
          {!conversation && !pending ? <div className="thread-loading" role="status" aria-label="Loading conversation"><span className="skeleton"/><span className="skeleton"/><span className="skeleton"/></div> : null}
          <Thread items={shown} events={events} conversation={conversation} projects={projects} localFiles={localFiles} thinking={thinking} sourceUrl={sourceUrl} linkTitles={linkTitles} compactRender={layout === "desktop" && desktopOpen}
            onOpenPreview={id => openWorkspace("preview", id)} onEditAgain={editAgain}
            retryHref={current?.status === "error" && !qualityBlocked ? advancedEditorUrl(current) || undefined : undefined}
            onChoice={choice => void send(choice)} onRetryMessage={retryMessage}/>
          <AgentRunControls runs={conversation?.agent_runs || []} onChanged={() => void refresh()}/>
          {qualityBlocked && current ? <div className="rc-actions" aria-label="بازبینی خروجی">
            <button className="btn btn-secondary" disabled={resuming} onClick={() => void acceptOutput()}>تأیید خروجی</button>
            <button className="btn btn-secondary" disabled={resuming} onClick={() => void send('ایرادهای واقعی کنترل کیفیت همین خروجی را اصلاح کن؛ انتخاب‌های طراحی تأییدشده را حفظ کن و مدیای پولی جدید بدون تأیید تولید نکن.')}>درست کردن</button>
            {advancedEditorUrl(current) ? <a className="btn btn-secondary" href={advancedEditorUrl(current)!}>ویرایش دستی</a> : null}
          </div> : current && (["talking", "localize"].includes(current.engine) || (current.engine === "motion" && current.state?.confirmed)) && ["error", "canceled", "paused"].includes(current.status) ? (askResume
            ? <div className="resume-confirm" role="alertdialog">
                <p>تحلیل و دارایی‌های آماده دوباره تولید نمی‌شوند. تکمیل مراحل ناقص ممکن است هزینهٔ API داشته باشد؛ هر مدیای ناقص فقط یک تلاش می‌شود.</p>
                <button className="btn" disabled={resuming} onClick={() => void resume()}>بله، ادامه بده</button>{" "}
                <button className="btn btn-secondary" onClick={() => setAskResume(false)}>انصراف</button>
              </div>
            : <button className="btn btn-secondary" disabled={resuming} onClick={() => setAskResume(true)}><Icon name="play" size={14}/>{resuming ? "در حال ادامه…" : "ادامه از مرحلهٔ متوقف‌شده"}</button>) : null}
          {!current && !processing && !pending && lastUserMessage && messages[messages.length - 1]?.content.startsWith('عملیات متوقف شد:') ? <button className="btn btn-secondary" disabled={sending} onClick={() => {
            if (window.confirm('هنوز پروژه‌ای ساخته نشده است. درخواست اصلی با همان فایل‌ها دوباره بررسی شود؟ این کار ممکن است هزینهٔ API داشته باشد؛ تولید نهایی همچنان نیازمند تأیید برنامه است.')) void send(undefined, { text: lastUserMessage.content, ids: lastUserMessage.attachments || [] });
          }}><Icon name="play" size={14}/>تلاش مجدد درخواست</button> : null}
          {styles.length > 0 && current?.status === "awaiting_input" ? <div className="action-card"><h3>Choose a style</h3><p>How should this video feel?</p><div className="style-options">{styles.map((style: any) => <button key={style.id || style.key} onClick={() => void send(`سبک ${style.id || style.key}`)}><b className="bidi" dir="auto">{style.label || style.title || style.name}</b><small className="bidi" dir="auto">{style.description || "Talking Reel style"}</small></button>)}</div></div> : null}
          {manualQuestion ? <ManualQuestion key={manualQuestion.id} question={manualQuestion} busy={processing || sending} onAnswer={value => void send(value)}/> : null}
          {awaitingPlan && current && !processing ? <section className="action-card plan-gate" dir="rtl" aria-label="تأیید برنامهٔ تدوین">
            <h3>برنامهٔ تدوین آماده است · نسخهٔ {awaitingPlan.n}</h3>
            <p>سبک «{awaitingPlan.content.style.label}»{awaitingPlan.content.hook.text ? <> با هوک «{awaitingPlan.content.hook.text}»</> : null}. رندر فقط بعد از تأیید شما شروع می‌شود؛ هر تغییری را در تب Edit یا همین چت بگویید.</p>
            <div className="action-buttons">
              <button className="btn" disabled={resuming} onClick={() => void approvePlan()}><Icon name="check" size={15}/>{resuming ? "در حال شروع…" : "تأیید و شروع رندر"}</button>
              <button className="btn btn-secondary" onClick={() => openWorkspace("edit", current.id)}>بررسی و تغییر برنامه</button>
            </div>
          </section> : null}
          {pendingAction ? <div className="action-card"><h3 dir="rtl">این سناریو تأیید شود؟</h3>
            {Array.isArray(current?.state.storyboard?.scenes) ? <details open dir="rtl"><summary>سناریوی همین نسخه</summary>{current.state.storyboard.scenes.map((scene: {index?: number; duration_s?: number; narration_text?: string; text_overlay?: string; description?: string}, index: number) => <section key={index}><h4>صحنهٔ {index + 1} · {scene.duration_s} ثانیه</h4><p>نریشن: {scene.narration_text || 'بدون نریشن'}</p>{scene.text_overlay ? <p>متن روی تصویر: {scene.text_overlay}</p> : null}<p>تصویر: {scene.description}</p></section>)}</details> : null}
            <p dir="rtl">با تأیید، تصویرها، نریشن و رندر نهایی طبق این سناریو ساخته می‌شود.</p>{pendingAction.estimated_cost_usd != null ? <small className="muted-text" dir="rtl">برآورد ثبت‌شده: ${pendingAction.estimated_cost_usd.toFixed(4)}</small> : null}
            <div className="action-buttons"><button className="btn" onClick={() => void api.confirmStudioAction(pendingAction.id).then(() => refresh()).catch(e => setError(friendlyError(e, "approve the plan")))}>تأیید و ادامه</button><button className="btn btn-secondary" onClick={() => void api.cancelStudioAction(pendingAction.id).then(() => refresh()).catch(e => setError(friendlyError(e, "cancel the plan")))}>انصراف</button></div></div> : null}
        </div>
      </div>
      <div className="dock">
        {!stuck ? <button className="jump-latest icon-btn" onClick={jumpToLatest} aria-label="Jump to latest"><Icon name="chevronDown" size={18}/></button> : null}
        {composer("dock")}
      </div>
      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">{announcement}</div>
    </section>

    {layout === "tablet" && overlayOpen ? <button className="ws-backdrop" onClick={() => setOverlayOpen(false)} aria-label="Close workspace" tabIndex={-1}/> : null}
    <Workspace conversation={conversation} project={current} projects={projects} onSelectProject={setSelectedProject} tab={wsTab} onTab={setWsTab}
      sourceAttachment={sourceAttachment} onCancel={stop} onSaved={() => refresh()} showTabs={layout !== "mobile"} onCollapse={layout === "mobile" ? undefined : closeWorkspace}
      panelRef={workspaceRef}
      topbarControls={layout === "mobile" && mobileView !== "chat"}
      working={processing && !renderLive ? (step?.label || thinking || "در حال بررسی درخواست شما…") : null}
      resizer={layout === "desktop" && wsVisible ? <Resizer panel={workspaceRef} edge="start" label="عرض پنل پیش‌نمایش" width={shownWorkspace}
        bounds={() => ({ min: WORKSPACE_BOUNDS.min, max: Math.min(WORKSPACE_BOUNDS.max, (studioRef.current?.clientWidth ?? 1400) - MIN_CHAT) })}
        onResize={setLiveWorkspace} onDragState={setResizingWorkspace} onCommit={value => { setWorkspaceWidth(value); setLiveWorkspace(null); }}/> : undefined}/>

    {layout === "mobile" ? <nav className="studio-tabs" aria-label="Studio views">
      {([["chat", "Chat", "spark"], ["preview", "Preview", "eye"], ["edit", "Edit", "edit"]] as const).map(([id, label, icon]) => <button key={id} aria-current={mobileTab === id ? "page" : undefined}
        onClick={() => { if (id === "chat") setMobileView("chat"); else { setWsTab(id); setMobileView(id); } }}><Icon name={icon} size={20}/><span>{label}</span></button>)}
    </nav> : null}
  </div>;
}
