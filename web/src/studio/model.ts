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

export type StepStatus = "active" | "done" | "failed" | "needs_review";
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
}
export type TimelineItem =
  | { kind: "message"; id: string; role: "user" | "assistant"; content: string; attachments: string[]; createdAt: number; pending?: boolean; failed?: boolean; narration?: boolean }
  | { kind: "activity"; id: string; steps: ActivityStep[]; live: boolean }
  | { kind: "render"; id: string; projectId: string; startedAt: number }
  | { kind: "question"; id: string; question: string; choices: QuestionChoice[]; seq: number; style: boolean }
  | { kind: "discovery"; id: string; analysisId: string }
  | { kind: "motion"; id: string; motionId: string };

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
  creative_storyboard: "تکمیل استوری‌بورد",
  motion_generation: "ساخت موشن",
  motion_so: "کلیپ موشن هوشمند",
  visual_analysis: "تحلیل محتوای تصویر",
  visual_review: "بررسی کیفیت بصری",
  translation: "آماده‌سازی ترجمه",
  script: "نوشتن سناریو",
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
  const known = STAGE_LABELS[stageKey(stage)] || STAGE_LABELS[String(message || "").toLocaleLowerCase().replace(/[._-]+/g, " ")];
  if (known) return known;
  if (event.type === "agent.thinking_summary") return "بررسی درخواست شما";
  if (event.type === "storyboard.ready") return "استوری‌بورد آماده است";
  if (event.type === "tool.failed") return "این مرحله نیاز به بررسی دارد";
  return "در حال تدوین";
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
  phase: "idle" | "queued" | "rendering" | "finalizing" | "done" | "failed" | "needs_review";
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
  if (observed.status === 'needs_review' || (candidate && project.state?.creative_review?.status !== 'passed' && !observed.output && project.status !== 'running')) {
    return {phase:'needs_review',review:true,output:candidate ? String(candidate) : undefined,stageLabel:'خروجی برای بررسی نگه داشته شده است',message:String(observed.message || project.state?.creative_review?.summary || '')};
  }
  if (observed.output) return { phase: "done", output: String(observed.output), progress: 100, stageLabel: "Your video is ready" };
  if (project.status === "error" || observed.status === "error") return { phase: "failed", stageLabel: "Rendering stopped", message: observed.message ? String(observed.message) : undefined };
  if (project.status === "done") return { phase: "finalizing", progress: 100, stageLabel: "Finalizing your video" };
  if (isRenderStage(stage)) {
    if (progress != null && progress >= 100) return { phase: "finalizing", progress, stageLabel: "Finalizing your video" };
    return { phase: "rendering", progress, stageLabel: RENDER_STAGE_LABELS[stage] || "Rendering your video" };
  }
  if (project.status === "running") return { phase: "queued", progress, stageLabel: STAGE_LABELS[stage] || "Preparing to render" };
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
  const savedResponses = new Set(events.filter(e => e.type.startsWith('assistant.response.') && savedIds.has(String(e.data.message_id))).map(e => e.data.response_id));
  type Entry = { t: number; order: number; tie: number; message?: StudioMessage; event?: StudioEvent };
  const entries: Entry[] = [
    ...messages.map(message => ({ t: parseTime(message.created_at), order: 0, tie: Number(message.id) || 0, message })),
    ...events.map(event => ({ t: parseTime(event.created_at), order: 1, tie: event.seq, event })),
  ].sort((a, b) => a.t - b.t || a.order - b.order || a.tie - b.tie);

  const items: TimelineItem[] = [];
  const placedRender = new Set<string>();
  let block: { id: string; steps: Map<string, ActivityStep> } | null = null;
  const projectIds = new Set(projects.map(project => project.id));
  const lastFailure = new Map<string, number>();
  for (const event of events) if (event.type === "tool.failed" && event.data.project_id) lastFailure.set(String(event.data.project_id), event.seq);
  const lastRenderDone = Math.max(0, ...events.filter(event => event.type === "render.completed").map(event => event.seq));
  let lastUserIndex = -1;

  const flush = () => {
    if (block && block.steps.size) items.push({ kind: "activity", id: block.id, steps: [...block.steps.values()], live: false });
    block = null;
  };

  for (const entry of entries) {
    if (entry.message) {
      flush();
      const message = entry.message;
      if (message.role === "user") lastUserIndex = items.length;
      items.push({ kind: "message", id: `m-${message.role}-${message.id}`, role: message.role, content: message.role === "assistant" ? publicAssistantText(message.content) : message.content, attachments: message.attachments || [], createdAt: entry.t });
      continue;
    }
    const event = entry.event!;
    if (event.type.startsWith('assistant.response.')) {
      if (savedResponses.has(event.data.response_id)) continue;
      const id = `response:${event.data.response_id}`;
      const content = String(event.data.text || '');
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
    if (event.type === "motion.created") {
      flush();
      if (!items.some(item => item.kind === "motion")) items.push({ kind: "motion", id: `mg-${event.data.motion_id}`, motionId: String(event.data.motion_id) });
      continue;
    }
    if (event.type === "discovery.created") {
      flush();
      if (!items.some(item => item.kind === "discovery")) items.push({ kind: "discovery", id: `dv-${event.data.analysis_id}`, analysisId: String(event.data.analysis_id) });
      continue;
    }
    const projectId = String(event.data.project_id || "");
    if (event.type === "question.required") {
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
    const rawNote = String(event.data.message || "").trim();
    const note = /^Planning the edit\.?$/i.test(rawNote) ? STAGE_LABELS.planning : rawNote;
    if (note && !step.notes.includes(note)) {
      if (/در انتظار پاسخ سرویس هوش مصنوعی/.test(note)) step.notes = step.notes.filter(n => !/در انتظار پاسخ سرویس هوش مصنوعی/.test(n));
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
  if (motionId && !items.some(item => item.kind === "motion")) items.push({ kind: "motion", id: `mg-${motionId}`, motionId });

  // A render card for any project that is rendering or finished but whose events were not seen
  // in this session (e.g. a project opened from history).
  for (const project of projects) {
    if (placedRender.has(project.id)) continue;
    const view = renderView(project);
    // A failure with no render stage is already shown as a failed step; don't relabel it "rendering".
    // A queued project that has started rendering (preparing the source, subtitles, ...) is a live render: the chat shows the same card as the tabs.
    const started = view.phase === "queued" && project.status === "running" && Boolean(project.state?.render_started);
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

  // The motion graphic's progress and result belong to the latest message: they stay at the end however many messages follow.
  const motion = filtered.filter(item => item.kind === "motion");
  if (motion.length) { const rest = filtered.filter(item => item.kind !== "motion"); filtered.length = 0; filtered.push(...rest, ...motion); }

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

  if (pending) filtered.push({ kind: "message", id: pending.id, role: "user", content: pending.content, attachments: pending.attachments, createdAt: pending.createdAt, pending: !pending.failed, failed: pending.failed });
  void lastUserIndex;
  return filtered;
}

/** True while the assistant is working on the latest user turn or a project is running. */
/** The server's own answer to "is anything working for this chat?", from the latest `work.state` event (any process emits it) or, before one arrives, the conversation. */
export function serverBusy(events: StudioEvent[], fallback?: boolean): boolean | undefined {
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].type === "work.state") return Boolean(events[i].data.busy);
    if (events[i].type === "message.stopped") return false;
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
  void events; void messages;
  return "در حال بررسی…";
}

export function activeStep(items: TimelineItem[]): ActivityStep | undefined {
  for (let i = items.length - 1; i >= 0; i--) {
    const item = items[i];
    if (item.kind === "activity") return item.steps.find(step => step.status === "active");
  }
  return undefined;
}

/** Details worth expanding. Empty means: show no expand control at all. */
export function stepDetails(step: ActivityStep): { notes: string[]; durationMs: number; updates: number; tool?: string; failed: boolean } | null {
  const notes = step.notes.filter(note => note.length > 0);
  const durationMs = Math.max(0, step.endedAt - step.startedAt);
  const updates = step.events.length;
  const informative = notes.some(note => note !== step.label) || step.status === "failed" || updates > 1 || Boolean(step.tool);
  if (!informative) return null;
  return { notes, durationMs, updates, tool: step.tool, failed: step.status === "failed" };
}
