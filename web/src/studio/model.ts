/**
 * Pure view-model for the Studio conversation.
 *
 * Turns the persisted messages + the live SSE event log into what the UI shows:
 * a chronological list of messages, grouped activity blocks, and one render card
 * per project. Nothing here invents events — every step, label and percentage
 * is derived from a real backend event or project state. Self-contained (type
 * imports only) so it can be unit-tested with plain `node --test`.
 */
import type { StudioEvent, StudioMessage, StudioProject } from "../api";

export type StepStatus = "active" | "done" | "failed";
export interface ActivityStep {
  key: string;
  label: string;
  status: StepStatus;
  progress?: number;
  startedAt: number;
  endedAt: number;
  tool?: string;
  stage?: string;
  /** Every real event folded into this step (history is preserved, only the display is grouped). */
  events: StudioEvent[];
  /** Distinct backend descriptions for this step, oldest first. */
  notes: string[];
  /** The exact request this step was given (the tool's arguments), when the server sent it. */
  request?: string;
  /** The exact material of the step (its lines, choices, results) when the server wrote it, shown when the step is opened. */
  detail?: string;
  /** A playable file of this step (the narration take), shown in its log. */
  audioSrc?: string;
  /** What came back from the step's model call (when it has returned), and the numbers about the call. */
  response?: string;
  run?: { model?: string; inputTokens?: number; outputTokens?: number; latencyMs?: number; elapsedSeconds?: number; error?: string };
}
export type TimelineItem =
  | { kind: "message"; id: string; role: "user" | "assistant"; content: string; attachments: string[]; createdAt: number; pending?: boolean; failed?: boolean; narration?: boolean; pro?: boolean }
  | { kind: "activity"; id: string; steps: ActivityStep[]; live: boolean }
  | { kind: "render"; id: string; projectId: string; startedAt: number }
  | { kind: "question"; id: string; question: string; choices: QuestionChoice[]; seq: number; style: boolean }
  | { kind: "discovery"; id: string; analysisId: string }
  | { kind: "motion"; id: string; motionId: string; run?: number; version?: number; startedAt?: number; summaries?: { plan?: string; ready?: string } }
  /** A Pro engine job (`pro.job` events): the render card of the studio engine the Pro agent started. Only Pro chats have these. */
  | { kind: "pro_job"; id: string; jobId: string; startedAt: number; data: Record<string, any> };

export interface QuestionChoice { label: string; /** What to send as the user's answer. */ value: string }
/** Backend choices are either plain strings or { id, label } objects (talking styles). */
export function normalizeChoices(raw: unknown, kind?: string): QuestionChoice[] {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((choice): QuestionChoice[] => {
    if (typeof choice === "string") return [{ label: choice, value: choice }];
    if (choice && typeof choice === "object") {
      const item = choice as Record<string, unknown>;
      const id = String(item.id ?? item.key ?? "");
      const label = String(item.label ?? item.title ?? item.name ?? id);
      if (!label) return [];
      // Style answers are sent in the form the orchestrator already parses.
      return [{ label, value: kind === "talking_style" && id ? `سبک ${id}` : label }];
    }
    return [];
  });
}

/** Plain-language summary of a backend failure message; the raw text stays available in the details. */
export function friendlyFailure(message: string | undefined): string {
  const text = (message || "").trim();
  if (!text) return "این مرحله نیاز به بررسی دارد.";
  if (/timeout|timed out|ReadTimeout/i.test(text)) return "این مرحله در مهلت تعیین‌شده کامل نشد. جزئیات خطا را بررسی کنید؛ تلاش دوباره خودکار انجام نمی‌شود.";
  if (/LM API|gateway|HTTP 5\d\d/i.test(text)) return "سرویس هوش مصنوعی پاسخ قابل‌استفاده نداد؛ جزئیات خطا ثبت شده است.";
  return text;
}

export interface PendingMessage { id: string; content: string; attachments: string[]; createdAt: number; failed?: boolean }

export function publicAssistantText(text: string): string {
  if (text === 'عملیات متوقف شد: یکی از گزینه‌های همین مرحله را انتخاب کنید.') return 'منتظر انتخاب شما: یکی از گزینه‌های همین مرحله را انتخاب کنید.';
  // Old versions exposed the internal A/B/C critic verdict. Preserve storage/audit;
  // show the actual proposal, not private scoring prose, in the conversation.
  if (text.startsWith("ایدهٔ انتخاب‌شده:")) return text.replace(/\n\nاز بین [\s\S]*?(?=\nمی‌توانید|$)/, "");
  return text;
}

export const TOOL_LABELS: Record<string, string> = {
  analyze_talking_reel: "تحلیل ویدیو",
  localize_video: "بررسی گفتار و زیرنویس",
  inspect_url: "خواندن صفحه",
  create_storyboard: "طراحی استوری‌بورد",
  generate_visual_assets: "آماده‌سازی دارایی‌های تصویری",
  cancel_operation: "توقف پردازش",
  creative_direction: "طراحی ایدهٔ تدوین",
  understanding_request: "بررسی درخواست شما",
  creative_brief: "بررسی هدف و محتوا",
  creative_concepts: "بررسی ایده‌های تدوین",
  creative_review: "ارزیابی ایده‌ها",
  creative_script: "نوشتن سناریو",
  creative_script_review: "نقد مستقل سناریو",
  creative_storyboard: "تکمیل استوری‌بورد",
  motion_generation: "ساخت موشن",
  motion_so: "کلیپ موشن هوشمند",
  visual_analysis: "تحلیل محتوای تصویر",
  visual_review: "بررسی کیفیت بصری",
  translation: "آماده‌سازی ترجمه",
  script: "نوشتن سناریو",
  medium_plan: "برنامه‌ریزی مراحل کار",
  medium_job: "اجرای کار در پس‌زمینه",
  medium_retry: "اتصال دوباره به مدل",
  create_motion_graphic: "ساخت موشن‌گرافیک",
  revise_motion_graphic: "اعمال تغییر روی موشن‌گرافیک",
  inspect_media: "بررسی فایل پیوست",
  inspect_project: "بررسی پروژهٔ فعلی",
  modify_project: "ویرایش پروژه",
  render_approved_plan: "رندر نسخهٔ تأییدشده",
  check_render_status: "بررسی وضعیت رندر",
  instagram_content_check: "بررسی متن اینستاگرام",
  discover_connected_app_tools: "جست‌وجوی ابزارهای برنامهٔ متصل",
  read_connected_app: "خواندن از برنامهٔ متصل",
  search_creative_resources: "جست‌وجوی منابع خلاقانه",
  audio_check: "سنجش صدای فایل",
  plan_audio_direction: "طرح صوتی ویدیو",
};
export const STAGE_LABELS: Record<string, string> = {
  "loading transcript": "خواندن متن ذخیره‌شدهٔ گفتار", "planning render": "آماده‌سازی برنامهٔ رندر",
  "rendering source preparation": "تبدیل فرمت و آماده‌سازی ویدیو", "rendering captions": "آماده‌سازی زیرنویس و تیتر",
  "rendering outro": "ساخت صفحهٔ پایانی و لوگو", "rendering shot": "رندر بخش‌های تدوین",
  "rendering composition": "ترکیب تصویر و صدا و رمزگذاری خروجی", "rendering finalizing": "نهایی‌سازی فایل ویدیو",
  "rendering effects": "افزودن افکت‌ها روی ویدیو",
  transcribing: "استخراج متن گفتار", "finding captions": "شناسایی زیرنویس روی تصویر",
  translating: "آماده‌سازی ترجمهٔ فارسی", "generating voice": "ساخت گویندگی",
  "choosing style": "انتخاب سبک تدوین", "editing text": "آماده‌سازی زیرنویس و هوک",
  planning: "طراحی برنامهٔ تدوین", generating: "آماده‌سازی دارایی‌ها", "generating assets": "آماده‌سازی دارایی‌ها",
  analyzing: "تحلیل ویدیو", transcribed: "متن گفتار آماده است", storyboard: "طراحی استوری‌بورد",
  "storyboard ready": "استوری‌بورد آماده است", "tracking the face": "ردیابی گوینده",
  "planning visual beats": "طراحی بخش‌های تصویری", "finding pictures": "انتخاب تصاویر مکمل",
  "building motion graphics": "ساخت موشن‌گرافیک", "reviewing motion graphics": "بازبینی موشن‌گرافیک",
  "improving motion graphics": "اصلاح موشن‌گرافیک", queued: "در صف شروع", pending: "طراحی برنامهٔ تدوین",
  "directing the edit": "طراحی ایدهٔ تدوین"
};
const RENDER_STAGE_LABELS: Record<string, string> = {
  "rendering source preparation": "تبدیل فرمت و آماده‌سازی ویدیو", "rendering captions": "آماده‌سازی زیرنویس و تیتر",
  "rendering outro": "ساخت صفحهٔ پایانی و لوگو", "rendering shot": "رندر بخش‌های تدوین",
  "rendering composition": "ترکیب تصویر و صدا و رمزگذاری خروجی", "rendering finalizing": "نهایی‌سازی فایل ویدیو",
  "rendering effects": "افزودن افکت‌ها روی ویدیو", rendering: "رندر ویدیو", "rendering rough cut": "رندر نسخهٔ اولیه",
  "rendering motion graphics": "رندر موشن‌گرافیک", queued: "در صف رندر",
};

export function parseTime(value: string | number | undefined | null): number {
  if (value == null || value === "") return 0;
  if (typeof value === "number") return value;
  const time = Date.parse(value);
  return Number.isNaN(time) ? 0 : time;
}
const stageKey = (value: unknown) => String(value || "").trim().toLocaleLowerCase();
export const isRenderStage = (stage: unknown) => stageKey(stage).startsWith("render");

function stepLabel(event: StudioEvent): string {
  const { tool, stage, message } = event.data;
  if (event.type === 'tool.failed' && message === 'یکی از گزینه‌های همین مرحله را انتخاب کنید.') return 'منتظر انتخاب شما';
  if (tool && TOOL_LABELS[tool]) return TOOL_LABELS[tool];
  const known = STAGE_LABELS[stageKey(stage)] || stageText(stage) || STAGE_LABELS[String(message || "").toLocaleLowerCase().replace(/[._-]+/g, " ")] || stageText(message);
  if (known) return known;
  if (event.type === "agent.thinking_summary") return "بررسی درخواست شما";
  if (event.type === "storyboard.ready") return "استوری‌بورد آماده است";
  if (event.type === "tool.failed") return "این مرحله نیاز به بررسی دارد";
  const said = presentable(message) || "";
  if (said && said.length <= 70) return said;                               // the step's own description beats a generic word; English wording is never shown
  return GENERIC_STEP;
}

function stepKey(event: StudioEvent): string | null {
  const { tool, stage, project_id } = event.data;
  switch (event.type) {
    case "agent.thinking_summary": return "thinking";
    case "tool.started": case "tool.completed": return `tool:${tool || "work"}${event.data.activity_id ? `:${event.data.activity_id}` : ""}`;
    case "tool.progress": return tool ? `tool:${tool}${event.data.activity_id ? `:${event.data.activity_id}` : ""}` : `stage:${project_id || ""}:${stageKey(stage) || "work"}`;
    case "storyboard.ready": return "storyboard";
    case "tool.failed": return `failed:${event.seq}`;
    default: return null;
  }
}

export interface RenderView {
  review?: boolean;
  phase: "idle" | "queued" | "rendering" | "finalizing" | "done" | "failed";
  progress?: number;
  stageLabel: string;
  output?: string;
  message?: string;
}
/** Truthful render state, read only from the project's observed state. */
export function renderView(project: StudioProject | undefined): RenderView {
  const observed = (project?.state?.last_observed || {}) as Record<string, any>;
  const stage = stageKey(observed.stage);
  const progress = typeof observed.progress === "number" ? Math.max(0, Math.min(100, Math.round(observed.progress))) : undefined;
  if (!project) return { phase: "idle", stageLabel: "" };
  const candidate = project.state?.candidate_output;
  if (candidate && project.state?.creative_review?.status !== 'passed' && !observed.output && project.status !== 'running') {
    return {phase:'done',review:true,output:String(candidate),progress:100,stageLabel:'ویدیو رندر شده؛ منتظر بررسی شما',message:project.state?.creative_review?.summary};
  }
  if (observed.output) return { phase: "done", output: String(observed.output), progress: 100, stageLabel: "Your video is ready" };
  if (project.status === "error" || observed.status === "error") return { phase: "failed", stageLabel: "Rendering stopped", message: observed.message ? String(observed.message) : undefined };
  if (project.status === "done") return { phase: "finalizing", progress: 100, stageLabel: "Finalizing your video" };
  if (isRenderStage(stage)) {
    if (progress != null && progress >= 100) return { phase: "finalizing", progress, stageLabel: "Finalizing your video" };
    return { phase: "rendering", progress, stageLabel: RENDER_STAGE_LABELS[stage] || "Rendering your video" };
  }
  // A storyboard video shows the render card only while frames are really being rendered; designing the scenes, preparing assets, subtitles and review are steps of the chat.
  if (project.status === "running" && project.engine !== "motion") return { phase: "queued", progress, stageLabel: STAGE_LABELS[stage] || "Preparing to render" };
  return { phase: "idle", stageLabel: "" };
}

export interface TimelineInput {
  messages: StudioMessage[];
  events: StudioEvent[];
  projects: StudioProject[];
  pending?: PendingMessage | null;
  /** Whether work is in flight right now (see isProcessing). */
  processing: boolean;
  /** The long-video analysis the conversation already owns (from its saved state), shown even when its events are older than the page. */
  discoveryId?: string;
  /** The motion graphic the conversation already owns (from its saved state). */
  motionId?: string;
}

export function buildTimeline({ messages, events, projects, pending, processing, discoveryId, motionId }: TimelineInput): TimelineItem[] {
  const savedIds = new Set(messages.filter(m => m.role === 'assistant').map(m => String(m.id)));
  const openRuns = new Map<string, Extract<TimelineItem, { kind: "motion" }>>();
  // The model calls a motion film makes while it is being built: its card already lists those steps from the film's own log.
  const filmCalls = new Set<string>();
  const runCount = new Map<string, number>();
  const savedResponses = new Set(events.filter(e => e.type.startsWith('assistant.response.') && savedIds.has(String(e.data.message_id))).map(e => e.data.response_id));
  type Entry = { t: number; order: number; tie: number; message?: StudioMessage; event?: StudioEvent };
  const entries: Entry[] = [
    ...messages.map(message => ({ t: parseTime(message.created_at), order: 0, tie: Number(message.id) || 0, message })),
    ...events.map(event => ({ t: parseTime(event.created_at), order: 1, tie: event.seq, event })),
  ].sort((a, b) => a.t - b.t || a.order - b.order || a.tie - b.tie);

  // The agent's one-line narration of the motion graphic's phases is the summary of that step inside the progress card, not a separate bubble.
  const responseKinds = new Map<string, string>();
  const messageKinds = new Map<string, string>();
  for (const event of events) {
    if (event.type === "assistant.response.started") responseKinds.set(String(event.data.response_id), String(event.data.narration || ""));
    if (event.type === "assistant.response.completed" && event.data.message_id != null) messageKinds.set(String(event.data.message_id), responseKinds.get(String(event.data.response_id)) || "");
  }
  const MOTION_SUMMARY: Record<string, "plan" | "ready"> = { motion_plan: "plan", motion_ready: "ready" };
  const summaries: { kind: "plan" | "ready"; text: string; t: number }[] = [];

  const items: TimelineItem[] = [];
  const placedRender = new Set<string>();
  let block: { id: string; steps: Map<string, ActivityStep> } | null = null;
  const projectIds = new Set(projects.map(project => project.id));
  const lastFailure = new Map<string, number>();
  for (const event of events) if (event.type === "tool.failed" && event.data.project_id) lastFailure.set(String(event.data.project_id), event.seq);
  const lastRenderDone = Math.max(0, ...events.filter(event => event.type === "render.completed").map(event => event.seq));
  let lastUserIndex = -1;

  const flush = () => {
    if (block && block.steps.size) items.push({ kind: "activity", id: block.id, steps: mergeSameSteps([...block.steps.values()]), live: false });
    block = null;
  };

  for (const entry of entries) {
    if (entry.message && entry.message.role === "assistant" && MOTION_SUMMARY[messageKinds.get(String(entry.message.id)) || ""]) {
      summaries.push({ kind: MOTION_SUMMARY[messageKinds.get(String(entry.message.id)) || ""], text: publicAssistantText(entry.message.content), t: entry.t });
      continue;
    }
    if (entry.message) {
      flush();
      const message = entry.message;
      if (message.role === "user") lastUserIndex = items.length;
      items.push({ kind: "message", id: `m-${message.role}-${message.id}`, role: message.role, content: message.role === "assistant" ? publicAssistantText(message.content) : message.content, attachments: message.attachments || [], createdAt: entry.t, pro: message.role === "assistant" && message.agent_mode === "pro" || undefined });
      continue;
    }
    const event = entry.event!;
    if (event.type.startsWith('assistant.response.')) {
      if (savedResponses.has(event.data.response_id)) continue;
      const id = `response:${event.data.response_id}`;
      const content = String(event.data.text || '');
      const summaryKind = MOTION_SUMMARY[responseKinds.get(String(event.data.response_id)) || ""];
      if (summaryKind) { if (content && event.type !== 'assistant.response.failed') summaries.push({ kind: summaryKind, text: content, t: entry.t }); continue; }
      const previous = items.find(item => item.kind === 'message' && item.id === id);
      // A streamed message keeps its pictures (the page's images, the reference frame review): the completed event names them.
      const attached = Array.isArray(event.data.attachments) ? event.data.attachments.map(String) : [];
      if (previous?.kind === 'message') { previous.content = content; if (attached.length) previous.attachments = attached; }
      else if (content) { flush(); items.push({kind:'message',id,role:'assistant',content,attachments:attached,createdAt:entry.t}); }
      continue;
    }
    if (event.type === 'agent.narration') {
      // Retain the audit history but no longer display the old canned receipt.
      if (/^(received:|phase:)/.test(String(event.data.narration_id || ''))) continue;
      const id = `narration:${event.data.narration_id || event.seq}`;
      const content = String(event.data.message || '').trim();
      if (!content) continue;
      const previous = items.find(item => item.kind === 'message' && item.id === id);
      if (previous?.kind === 'message') previous.content = content;
      else {
        flush();
        items.push({kind:'message', id, role:'assistant', content, attachments:[], createdAt:entry.t, narration:true});
      }
      continue;
    }
    // Every render run of the motion graphic is its own message, where it happened: a new version never rewrites an old card, and nothing is
    // pinned to the end of the chat. A run ends when it completes; a failed run stays open so a retry reuses its card.
    if (event.type === "motion.created" || event.type === "motion.progress" || event.type === "motion.completed") {
      const motionKey = String(event.data.motion_id || "");
      if (!motionKey) continue;
      let run = openRuns.get(motionKey);
      const live = event.type === "motion.progress" && !["completed", "failed"].includes(String(event.data.status));
      if (!run && (event.type !== "motion.progress" || live)) {
        flush();
        const number = (runCount.get(motionKey) || 0) + 1;
        runCount.set(motionKey, number);
        run = { kind: "motion", id: `mg-${motionKey}-${number}`, motionId: motionKey, run: number, startedAt: entry.t };
        items.push(run);
        openRuns.set(motionKey, run);
      }
      if (run && event.type === "motion.completed") {
        run.version = Number(event.data.version) || undefined; openRuns.delete(motionKey);
        const at = items.indexOf(run);                                   // it finished now: it sits below what was said while it ran
        if (at >= 0) { items.splice(at, 1); items.push(run); }
      }
      continue;
    }
    if (event.type === "pro.job") {
      const jobId = String(event.data.job_id || "");
      if (!jobId) continue;
      const card = items.find(item => item.kind === "pro_job" && item.jobId === jobId);
      if (card && card.kind === "pro_job") {
        // Updated in place: moving it would split the engine's steps around it into collapsed groups.
        card.data = { ...card.data, ...event.data, attachment_id: event.data.attachment_id || card.data.attachment_id };
        continue;
      }
      // An engine job (talking edit) shows its steps in the timeline like Lite's own chat; its card appears where the render starts. A cloud
      // render or a heavy ffmpeg job is the render itself: its card appears at once.
      const state = String(event.data.state || "");
      const engineJob = !["render", "ffmpeg"].includes(String(event.data.style || ""));
      if (engineJob && !["rendering", "done", "failed"].includes(state)) continue;
      flush();
      items.push({ kind: "pro_job", id: `pj-${jobId}`, jobId, startedAt: entry.t, data: { ...event.data } });
      continue;
    }
    if (event.type === "discovery.created") {
      flush();
      if (!items.some(item => item.kind === "discovery")) items.push({ kind: "discovery", id: `dv-${event.data.analysis_id}`, analysisId: String(event.data.analysis_id) });
      continue;
    }
    const projectId = String(event.data.project_id || "");
    if (event.type === "question.required") {
      if (event.data.action_id) continue;          // an approval the chat shows as its own card: the raw "confirm / edit" words are not repeated as buttons
      flush();
      const kind = String(event.data.kind || "");
      items.push({ kind: "question", id: `q-${event.seq}`, question: String(event.data.question || ""), choices: normalizeChoices(event.data.choices, kind), seq: event.seq, style: kind === "talking_style" });
      continue;
    }
    const renderish = event.type.startsWith("render.") || (["tool.progress", "tool.failed"].includes(event.type) && isRenderStage(event.data.stage));
    if (renderish && projectId && projectIds.has(projectId)) {
      if (event.type === 'render.started' && placedRender.has(projectId)) {
        const previous=items.findIndex(item=>item.kind==='render' && item.projectId===projectId);
        if(previous>=0) items.splice(previous,1);
        placedRender.delete(projectId);
      }
      if (!placedRender.has(projectId)) {
        flush();
        placedRender.add(projectId);
        items.push({ kind: "render", id: `r-${projectId}`, projectId, startedAt: entry.t });
      }
      continue;
    }
    // A failure of a project that is no longer failed (it was retried and finished, or is running again), or that a later failure replaced,
    // is history: a wall of red cards for something that already worked helps nobody.
    if (event.type === "tool.failed" && event.seq < lastRenderDone) continue;     // the video exists now: earlier stops are history
    if (event.type === "tool.failed" && projectId) {
      const owner = projects.find(p => p.id === projectId);
      if (owner && owner.status !== "error") continue;
      if (lastFailure.get(projectId) !== event.seq) continue;
    }
    if (event.type.startsWith("tool.") && !projectId) {
      const call = String(event.data.activity_id || "");
      if (call && event.type === "tool.started" && openRuns.size) filmCalls.add(call);
      if (call && filmCalls.has(call)) continue;
    }
    const key = stepKey(event);
    if (!key) continue;
    if (!block) block = { id: `a-${event.seq}`, steps: new Map() };
    let step = block.steps.get(key);
    if (!step) {
      step = { key, label: stepLabel(event), status: "active", startedAt: entry.t, endedAt: entry.t, tool: event.data.tool, stage: event.data.stage, events: [], notes: [] };
      block.steps.set(key, step);
    }
    step.events.push(event);
    step.endedAt = entry.t;
    if (typeof event.data.progress === "number") step.progress = Math.round(event.data.progress);
    if (typeof event.data.request === "string" && event.data.request.trim() && event.data.request.trim() !== "{}") step.request = event.data.request;
    if (typeof event.data.response === "string" && event.data.response.trim()) step.response = event.data.response;
    if (event.type === "tool.completed" || typeof event.data.elapsed_seconds === "number") {
      step.run = { ...(step.run || {}), model: event.data.actual_model ? String(event.data.actual_model) : step.run?.model,
        inputTokens: typeof event.data.input_tokens === "number" ? event.data.input_tokens : step.run?.inputTokens,
        outputTokens: typeof event.data.output_tokens === "number" ? event.data.output_tokens : step.run?.outputTokens,
        latencyMs: typeof event.data.latency_ms === "number" ? event.data.latency_ms : step.run?.latencyMs,
        elapsedSeconds: typeof event.data.elapsed_seconds === "number" ? event.data.elapsed_seconds : step.run?.elapsedSeconds,
        error: typeof event.data.error === "string" && event.data.error ? event.data.error : step.run?.error };
    }
    const rawNote = String(event.data.message || "").trim();
    // «Waiting for the AI service · 15 s» is just «working»: the chat counts the seconds itself, live, next to the step.
    const note = /^Planning the edit\.?$/i.test(rawNote) ? STAGE_LABELS.planning : /^در انتظار پاسخ سرویس هوش مصنوعی/.test(rawNote) ? WORKING_NOTE : (presentable(rawNote) || "");      // the raw text stays in the step's log
    if (note && !step.notes.includes(note)) {
      if (note === WORKING_NOTE) step.notes = step.notes.filter(n => n !== WORKING_NOTE);
      step.notes.push(note);
      step.notes = step.notes.slice(-5);
    }
    if (event.type === "tool.completed" || event.type === "storyboard.ready") step.status = "done";
    if (event.type === "tool.failed") step.status = /^یکی از گزینه‌های همین مرحله را انتخاب کنید[.؟]?$/u.test(note) ? "done" : "failed";
    if (event.type === 'tool.failed' && projects.some(p => p.id === event.data.project_id && p.state?.candidate_output && p.state?.creative_review?.summary === note)) {
      step.status = 'done'; step.label = 'بازبینی خروجی؛ منتظر نظر شما';
    }
    if (event.type === "agent.thinking_summary") step.status = "done";
  }
  flush();
  if (discoveryId && !items.some(item => item.kind === "discovery")) items.push({ kind: "discovery", id: `dv-${discoveryId}`, analysisId: discoveryId });
  if (motionId && !items.some(item => item.kind === "motion")) items.push({ kind: "motion", id: `mg-${motionId}`, motionId, run: 0 });

  // A render card for any project that is rendering or finished but whose events were not seen
  // in this session (e.g. a project opened from history).
  for (const project of projects) {
    if (placedRender.has(project.id)) continue;
    const view = renderView(project);
    // A failure with no render stage is already shown as a failed step; don't relabel it "rendering".
    // A queued project that has started rendering (preparing the source, subtitles, ...) is a live render: the chat shows the same card as the tabs.
    // The Claude talking engine plans, cuts, draws and checks before it renders: until its stage says rendering, those are steps in the chat, not a render card.
    const claudeEditing = String((project.state as any)?.last_observed?.stage || "").trim().toLowerCase() === "claude talking";
    const started = view.phase === "queued" && project.status === "running" && Boolean(project.state?.render_started) && !claudeEditing;
    if (view.phase === "idle" || (view.phase === "queued" && !started) || view.phase === "failed") continue;
    items.push({ kind: "render", id: `r-${project.id}`, projectId: project.id, startedAt: parseTime(project.updated_at) });
  }

  // Steps that were followed by later work, or by a message, are no longer in progress.
  // Only the very last step, and only while work is really in flight, stays active.
  const lastActivityIndex = (() => { for (let i = items.length - 1; i >= 0; i--) if (items[i].kind === "activity") return i; return -1; })();
  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    if (item.kind !== "activity") continue;
    // A later render card or message takes over as the live indicator.
    const isLast = i === lastActivityIndex && processing && items.slice(i + 1).every(next => next.kind === "question" || (next.kind === 'message' && next.narration));
    item.steps.forEach((step, index) => {
      if (step.status === "active" && !(isLast && index === item.steps.length - 1)) step.status = "done";
    });
    item.live = isLast && item.steps.some(step => step.status === "active");
  }

  // Only the latest unanswered question is actionable.
  const lastQuestion = [...items].reverse().find(item => item.kind === "question");
  const filtered = items.filter(item => {
    if (item.kind !== "question") return true;
    if (item !== lastQuestion) return false;
    return !items.slice(items.indexOf(item) + 1).some(next => next.kind === "message" && next.role === "user");
  });


  // The render card of the project being worked on (running, waiting for review, done or failed) belongs to the latest message: its first event
  // may have landed above later messages (a re-render started after others), and the finished video must appear at the bottom, not where the
  // first render once was. A running card's clock starts at the request that started this run.
  const phaseOf = (item: TimelineItem) => renderView(projects.find(project => project.id === (item as { projectId: string }).projectId)).phase;
  const cards = filtered.filter(item => item.kind === "render" && phaseOf(item) !== "idle");
  if (cards.length) {
    const updated = (item: TimelineItem) => parseTime(projects.find(project => project.id === (item as { projectId: string }).projectId)?.updated_at || "");
    const latest = cards.reduce((best, item) => updated(item) >= updated(best) ? item : best);
    const card = latest as { kind: "render"; id: string; projectId: string; startedAt: number };
    let startedAt = card.startedAt;
    if (["queued", "rendering", "finalizing"].includes(phaseOf(latest))) {
      const lastUserAt = Math.max(0, ...filtered.filter(item => item.kind === "message" && item.role === "user").map(item => (item as { createdAt: number }).createdAt || 0));
      const started = Math.max(0, ...events.filter(event => event.type === "render.started" && String(event.data.project_id || "") === card.projectId).map(event => parseTime(event.created_at)));
      startedAt = Math.max(startedAt, lastUserAt, started);
    }
    const rest = filtered.filter(item => item !== latest);
    filtered.length = 0; filtered.push(...rest, { ...card, startedAt } as TimelineItem);
  }

  // Summaries belong to the run that was current when they were said (the latest summary of each kind wins).
  const runs = filtered.filter((item): item is Extract<TimelineItem, { kind: "motion" }> => item.kind === "motion");
  for (const summary of summaries) {
    const owner = [...runs].reverse().find(run => (run.startedAt || 0) <= summary.t) || runs[runs.length - 1];
    if (owner) owner.summaries = { ...owner.summaries, [summary.kind]: summary.text };
  }
  // A run in progress is the last message of the chat; a finished run stays where it finished (below), and a new run (an edit, a new version)
  // starts a new card at the end while the earlier one stays on its own message.
  for (const run of openRuns.values()) {
    const at = filtered.indexOf(run);
    if (at >= 0) { filtered.splice(at, 1); filtered.push(run); }
  }

  // The message the server already holds is the real one: the optimistic copy is dropped as soon as it shows up (a slow refresh used to leave both on screen).
  const delivered = pending && messages.some(m => m.role === "user" && m.content === pending.content && parseTime(m.created_at) >= pending.createdAt - 120000);
  if (pending && !delivered) filtered.push({ kind: "message", id: pending.id, role: "user", content: pending.content, attachments: pending.attachments, createdAt: pending.createdAt, pending: !pending.failed, failed: pending.failed });
  void lastUserIndex;
  return filtered;
}

/** True while the assistant is working on the latest user turn or a project is running. */
/** The server's own answer to "is anything working for this chat?", from the latest `work.state` event (any process emits it) or, before one arrives, the conversation. */
export function serverBusy(events: StudioEvent[], fallback?: boolean, now: number = Date.now()): boolean | undefined {
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].type === "work.state") {
      // A worker that died (a server restart) never said "idle". When the server itself reports nothing running and no event has come for a while, that last "busy" is stale.
      if (events[i].data.busy && fallback === false && now - parseTime(events[events.length - 1].created_at) > 2 * 60 * 1000) return false;
      return Boolean(events[i].data.busy);
    }
    // A ready plan is a human approval boundary, not unfinished analysis.
    // A later work.state (e.g. a new revision request) still takes precedence.
    if (events[i].type === "plan.ready") return false;
    if (events[i].type === "render.completed") return false;                 // the video is finished: nothing announces "idle" after a render that the status sync completed
    if (events[i].type === "content.discovery.completed") return false;     // a long-video analysis that ended no longer keeps the chat busy
    if (events[i].type === "message.stopped" || events[i].type === "job.failed" || events[i].type === "motion.completed" || events[i].type === "motion.questions") return false;
    if (events[i].type === "motion.progress" && ["failed", "completed"].includes(String(events[i].data.status))) return false;   // the job ended after the last "busy"
  }
  return fallback;
}

export function isProcessing(args: { sending: boolean; messages: StudioMessage[]; events: StudioEvent[]; project?: StudioProject; now?: number }): boolean {
  const { sending, messages, events, project } = args;
  const now = args.now ?? Date.now();
  if (sending) return true;
  // A persisted approval gate means the worker is waiting for the person,
  // even if the preceding upload message has no assistant reply yet.
  if (project?.status === "awaiting_confirmation" && project.state?.manual_checkpoint && !project.state.manual_checkpoint.claimed) return false;
  if (project?.status === "running") return true;
  const last = messages[messages.length - 1];
  if (!last || last.role !== "user") return false;
  const sentAt = parseTime(last.created_at);
  const after = events.filter(event => parseTime(event.created_at) >= sentAt - 1000);
  if (after.some(event => event.type === "tool.failed" || event.type === "question.required" || event.type === "message.stopped")) return false;
  const latest = Math.max(sentAt, ...after.map(event => parseTime(event.created_at)));
  // No heartbeat for 3 minutes: stop claiming the assistant is working.
  return now - latest < 3 * 60 * 1000;
}

/** Label for the bottom-of-conversation indicator when no step is active. */
export function thinkingLabel(events: StudioEvent[], messages: StudioMessage[]): string {
  const last = events[events.length - 1];
  if (last) {
    if (last.type === "assistant.response.started" || last.type === "assistant.response.delta") return "دارم پاسخ را می‌نویسم…";
    if (/^tool\.(started|progress)$/.test(last.type)) return `${stepLabel(last)}…`;
    if (last.type === "tool.completed" && last.data.tool) return "مرحلهٔ بعدی را آماده می‌کنم…";
    if (last.type.startsWith("motion.")) return "ساخت موشن‌گرافیک در جریان است…";
    if (last.type.startsWith("render.")) return "رندر ویدیو در جریان است…";
  }
  const lastMessage = messages[messages.length - 1];
  if (!lastMessage || lastMessage.role === "user") return "دارم درخواست شما را می‌خوانم…";
  return "دارم کار بعدی را آماده می‌کنم…";
}

export function activeStep(items: TimelineItem[]): ActivityStep | undefined {
  for (let i = items.length - 1; i >= 0; i--) {
    const item = items[i];
    if (item.kind === "activity") return item.steps.find(step => step.status === "active");
  }
  return undefined;
}

/** Details worth expanding. Empty means: show no expand control at all. */
export interface PreparedAsset { kind: "image" | "video" | "motion" | "audio"; scene: number; label: string; group?: string; src: string; duration_s?: number | null; text?: string }
export function stepDetails(step: ActivityStep): { notes: string[]; durationMs: number; updates: number; tool?: string; failed: boolean; request?: string; response?: string; run?: ActivityStep["run"]; assets: PreparedAsset[]; projectId?: string } | null {
  const notes = step.notes.filter(note => note.length > 0);
  const durationMs = Math.max(0, step.endedAt - step.startedAt);
  const updates = step.events.length;
  if (!updates && !notes.length && !step.request && !step.audioSrc) return null;                // a step with recorded events always opens to its log
  let assets: PreparedAsset[] = [];
  for (const event of step.events) if (Array.isArray(event.data?.assets)) assets = event.data.assets.filter((asset: any) => asset && typeof asset.src === "string" && asset.src);      // the newest list wins; the server hides keys named file/path, so the file is `src`
  const projectId = step.events.map(event => event.data?.project_id).find(Boolean);
  return { notes, durationMs, updates, tool: step.tool, failed: step.status === "failed", request: step.request, response: step.response, run: step.run, assets, projectId };
}

// ── Persian wording of steps (no English stage names in a Persian chat); the raw text stays in each step's log ──
const hasPersian = (text: string) => /[؀-ۿ]/.test(text);
const normalize = (value: unknown) => String(value || "").trim().toLocaleLowerCase().replace(/[._-]+/g, " ").replace(/\s+/g, " ");

/** Stage names the engines report, in Persian. */
export const STAGE_FA: Record<string, string> = {
  "creative brief": "بررسی هدف و محتوا", "creative concepts": "بررسی ایده‌های تدوین", "creative review": "ارزیابی ایده‌ها", "creative storyboard": "تکمیل استوری‌بورد",
  "creative script": "نوشتن سناریو", "creative script review": "نقد مستقل سناریو", "creative direction": "طراحی ایدهٔ تدوین", "script writer": "نوشتن سناریو", "script critic": "نقد مستقل سناریو",
  queued: "در صف شروع", pending: "در انتظار شروع", running: "در حال اجرا", done: "انجام شد", completed: "انجام شد", failed: "ناموفق", stopped: "متوقف شد", stopping: "در حال توقف",
  checking: "بررسی", enhancing: "بهبود نتیجه", finding: "جست‌وجو", planning: "طراحی برنامهٔ کار", repair: "اصلاح", understanding: "درک درخواست", validating: "اعتبارسنجی", writing: "نوشتن",
  "quality review": "بازبینی کیفیت", analyzing: "تحلیل ویدیو", transcribing: "استخراج متن گفتار", transcribed: "متن گفتار آماده است", translating: "آماده‌سازی ترجمهٔ فارسی",
  "loading transcript": "خواندن متن ذخیره‌شدهٔ گفتار", "choosing style": "انتخاب سبک تدوین", "editing text": "آماده‌سازی زیرنویس و هوک", "directing the edit": "طراحی ایدهٔ تدوین",
  "planning render": "آماده‌سازی برنامهٔ رندر", "planning visual beats": "طراحی بخش‌های تصویری", "planning caption phrases": "آماده‌سازی عبارت‌های زیرنویس",
  "finding captions": "شناسایی زیرنویس روی تصویر", "finding english text": "شناسایی متن انگلیسی روی تصویر", "tracking caption frames": "ردیابی قاب‌های زیرنویس", "tracking the face": "ردیابی چهرهٔ گوینده",
  "generating voice": "ساخت گویندگی", "generating": "آماده‌سازی دارایی‌ها", "generating assets": "آماده‌سازی دارایی‌ها", "finding pictures": "انتخاب تصاویر مکمل",
  "reusing prepared cut": "استفاده از برش آمادهٔ قبلی", "designing motion scenes": "طراحی صحنه‌های موشن", "adding subtitles": "افزودن زیرنویس کلمه‌به‌کلمه", "choosing design style": "انتخاب سبک طراحی", "repairing motion scenes": "اصلاح صحنه‌های موشن",
  "building motion graphics": "ساخت موشن‌گرافیک", "reviewing motion graphics": "بازبینی موشن‌گرافیک", "improving motion graphics": "اصلاح موشن‌گرافیک",
  "reviewing creative output": "بازبینی خلاقانهٔ خروجی", "reviewing localized output": "بازبینی خروجی دوبله",
  rendering: "رندر ویدیو", "rendering source preparation": "تبدیل فرمت و آماده‌سازی ویدیو", "rendering captions": "آماده‌سازی زیرنویس و تیتر", "rendering outro": "ساخت صفحهٔ پایانی و لوگو",
  "rendering shot": "رندر بخش‌های تدوین", "rendering composition": "ترکیب تصویر و صدا و رمزگذاری خروجی", "rendering finalizing": "نهایی‌سازی فایل ویدیو", "rendering effects": "افزودن افکت‌ها روی ویدیو",
  "rendering rough cut": "رندر نسخهٔ اولیه", "rendering motion graphics": "رندر موشن‌گرافیک", "rendering motion": "رندر موشن‌گرافیک",
  "cloud provisioning": "آماده‌سازی سرور رندر ابری", "cloud preparing": "آماده‌سازی موتور رندر ابری", "cloud downloading": "ارسال فایل‌ها به سرور ابری", "cloud rendering": "رندر روی سرور ابری",
  "cloud uploading": "دریافت خروجی از سرور ابری", "cloud completed": "خروجی ابری دریافت شد",
  "translation revision ready": "اصلاح ترجمه آماده است", "awaiting confirmation": "منتظر تأیید شما", "awaiting plan": "منتظر تأیید برنامه", ready: "آماده است",
  storyboard: "طراحی استوری‌بورد", "storyboard ready": "استوری‌بورد آماده است",
};

/** Persian wording for a stage or short status text; undefined when there is none. */
export function stageText(raw: unknown): string | undefined {
  const key = normalize(raw);
  const scene = key.match(/^designing scene (\d+)$/);
  if (scene) return `طراحی صحنهٔ ${scene[1]}`;
  return key ? STAGE_FA[key] : undefined;
}

/**
 * Text fit to show in a Persian chat: Persian as written, a known stage name translated, anything else in English hidden (it stays in the log).
 * Returns null when nothing presentable remains.
 */
export function presentable(raw: unknown): string | null {
  const text = String(raw || "").trim();
  if (!text) return null;
  const known = stageText(text);
  if (known) return known;
  if (hasPersian(text)) return text;
  return /^[\x00-\x7F\s]*$/.test(text) && /[a-zA-Z]{3}/.test(text) ? null : text;     // plain English wording: not shown; numbers, symbols and mixed text are
}

/** Generic wording for a step whose own name is unusable. */
export const WORKING_NOTE = "در حال کار";
export const GENERIC_STEP = "در حال انجام کار";

/** The same step reported twice (the project's stage and the tool's own event) is one row: its events, notes and outcome are joined. */
export function mergeSameSteps(steps: ActivityStep[]): ActivityStep[] {
  const out: ActivityStep[] = [];
  for (const step of steps) {
    // Only reports of a project's stage (no tool of their own) are joined: two attempts of the same tool are two real steps and stay two rows.
    const same = out.find(other => !other.tool && !step.tool && other.label === step.label && other.status !== "failed" && step.status !== "failed");
    if (!same) { out.push(step); continue; }
    same.events = [...same.events, ...step.events].sort((a, b) => a.seq - b.seq);
    for (const note of step.notes) if (!same.notes.includes(note)) same.notes.push(note);
    same.startedAt = Math.min(same.startedAt, step.startedAt);
    same.endedAt = Math.max(same.endedAt, step.endedAt);
    same.status = same.status === "active" || step.status === "active" ? "active" : "done";
    same.progress = step.progress ?? same.progress;
    same.request = same.request || step.request;
    same.response = same.response || step.response;
    same.run = { ...(step.run || {}), ...(same.run || {}) };
    same.tool = same.tool || step.tool;
  }
  return out;
}
