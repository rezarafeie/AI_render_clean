import { getToken, ensureFreshToken, handleUnauthorized, setToken } from "./auth";

const BASE = "/api";

type JobCacheListener = () => void;
const jobCacheListeners = new Set<JobCacheListener>();

export function subscribeJobCacheInvalidation(listener: JobCacheListener): () => void {
  jobCacheListeners.add(listener);
  return () => jobCacheListeners.delete(listener);
}

export function invalidateJobCache(): void {
  jobCacheListeners.forEach(listener => listener());
}

function isJobMutation(url: string, init?: RequestInit): boolean {
  const method = (init?.method || "GET").toUpperCase();
  if (["GET", "HEAD", "OPTIONS"].includes(method)) return false;
  const pathname = new URL(url, window.location.origin).pathname;
  if (!pathname.startsWith(`${BASE}/jobs`)) return false;
  // Validation is read-only despite using POST, so it must not churn the list cache.
  return !pathname.endsWith("/validate");
}

export interface Job {
  id: string;
  dir: string;
  raw_name?: string;
  plan_name: string;
  render: {
    status: string; progress: number; message: string;
    output?: string; preview: boolean;
  };
  generate: {
    status: string; stage: string; message: string;
    cost_usd: number; input_tokens: number; output_tokens: number; model: string;
  };
  versions: string[];
  plan?: any;
  has_transcript?: boolean;
}

export type PremiereMode = "editable_plan" | "rendered_video" | "plan_and_render" | "saved_project" | "reveal";
export interface PremiereStatus {
  available?: boolean;
  message?: string | null;
  capability: { available: boolean; local_launch_supported: boolean; version: string | null; bundle_id: string | null; app_path: string | null };
  editable_plan: "ready" | "stale" | "missing";
  final_render: "final" | "preview_only" | "missing" | "outdated";
  saved_project: "linked" | "outdated" | "not_linked";
  project_state: "not_linked" | "linked_current" | "linked_outdated" | "missing";
  render_name: string | null;
  xml_name: string;
  srt_name: string;
  project_name?: string;
  artifact_hashes?: { plan?: string; xml?: string; srt?: string; render?: string | null };
  changed_hashes?: Record<string, { linked: string | null; current: string | null }>;
  warnings: string[];
  bridge?: {
    available: boolean; protocol_version: number;
    state: "not_connected" | "waiting_for_premiere" | "paired" | "completed" | "partial" | "failed" | "stale";
    operation_id?: string; expires_at_unix?: number;
    bridge?: { kind?: string; version?: string; premiere_version?: string | null };
    receipt?: any;
  };
}

export interface Transcript {
  file_hash: string;
  cache_key?: string;
  model_size?: string;
  requested_language?: string;
  correction_count?: number;
  language: string;
  duration: number;
  words: { w: string; start: number; end: number; prob: number; reviewed?: boolean; original_w?: string }[];
  sentences: { text: string; start: number; end: number }[];
}

export interface EffectPreset {
  id: string; motion: string; light: string; label: string;
  description: string; needs_framing_review: boolean; strong_accent: boolean;
  energy?: number; mood?: string; best_roles?: string[]; category?: string; hint_color?: string;
}

export interface RafieiStyle {
  preferred_effects: string[]; avoid_effects: string[];
  caption_emphasis_color: string; caption_emphasis_alt_color: string;
  opening_title: boolean;
  watermark: { text: string; font: string; position: string; opacity: number; size: number };
  credit_lower_third: { text: string; font: string; show_on_intro: boolean };
}

export interface Correction {
  index: number;
  old: string;
  new: string;
  confidence: number;
  reason: string;
  type?: string;
}

export interface Corrections {
  auto_applied: Correction[];
  suggestions: Correction[];
}

export interface GenerateStatus {
  status: string; stage: string; message: string;
  cost_usd: number; input_tokens: number; output_tokens: number; model: string;
  asr_engine: string; asr_fallback_reason: string; asr_audio_seconds: number; asr_cost_usd: number;
  correction_model: string;
}

export interface FontEntry {
  id: string; kind: string; name?: string; family?: string; style?: string;
  filename?: string; sha256?: string; review_state: string;
  metadata?: { family: string; style: string; weight: number; license?: string;
    license_url?: string; glyph_count: number;
    persian_coverage: { supported: boolean; missing: string[] };
    latin_coverage: { supported: boolean; missing: string[] } };
  extracted_text?: string; ocr_note?: string;
  font_candidates?: { family: string; confidence: string; basis: string }[];
  copied_text?: string; font_name?: string; source?: any;
}
export interface FontLibrary { version: number; candidates: FontEntry[]; approved: FontEntry[] }
export interface StyleDraft { id: string; name: string; state: string; source: any; evidence: any[]; profile: any }
export interface StyleProfile { style_id: string; version: number; name: string; state: string; source: any; profile: any; evidence: any[] }
export interface StyleLibraryData { drafts: StyleDraft[]; profiles: StyleProfile[] }
export interface PlanStyleSelection { style_id: string | null; version: number | null; name: string | null; selected: boolean; default_hidden: boolean }
export interface LearnedStyleProfile {
  exists: boolean; active: boolean; enabled: boolean; sample_count: number;
  metrics: Record<string, unknown>; confidence: Record<string, unknown>;
  preset_overrides: Record<string, unknown>;
}

export interface LibraryAsset {
  filename: string; category: "broll" | "music" | "sfx"; path: string;
  tags: string[]; mood?: string; energy?: number;
  duration_sec?: number; description?: string;
}
export interface LibraryData {
  counts: { broll: number; music: number; sfx: number };
  assets: LibraryAsset[];
}

export interface MusicStatus {
  attached: boolean;
  file: string | null;
  name: string | null;
  duration_s: number;
  volume_level: number;
  fade_in_seconds: number;
  fade_out_seconds: number;
  status: "idle" | "queued" | "running" | "done" | "error";
  progress: number;
  message: string;
  output: string | null;
  mixed_from: string | null;
  technical_qc?: { loudness_lufs: number | null; true_peak_dbfs: number | null; warnings: string[] } | null;
}

export interface StudioAttachment { id: string; kind: "video" | "image" | "audio"; filename: string; mime_type: string; size_bytes: number }
export type AgentMode = "lite" | "medium";
export interface StudioAgentRun { id: string; message_id: string; agent_mode: AgentMode; status: string; plan?: {summary: string; steps: {tool: string; label: string}[]}; error?: string }
export interface StudioMessage { id: number; role: "user" | "assistant"; content: string; attachments: string[]; created_at: string; agent_mode?: AgentMode; agent_run_id?: string }
export interface StudioProject {
  id: string; conversation_id: string; engine: "localize" | "talking" | "motion";
  title: string; status: string; external_ref?: string; current_version: number;
  state: Record<string, any>; created_at: string; updated_at: string;
}
export interface StudioAction { id: string; project_id?: string; kind: string; status: string; payload: any; estimated_cost_usd?: number | null }
export interface StudioConversation {
  id: string; title: string; language: string; status_voice_enabled: boolean; state: Record<string, any>;
  created_at: string; updated_at: string; messages?: StudioMessage[]; projects?: StudioProject[]; actions?: StudioAction[];
  /** The server's own answer to "is anything working for this chat" (any process: the API, the worker, a narration, a motion graphic). */
  busy?: boolean;
  agent_runs?: StudioAgentRun[];
}
export interface StudioEvent { id: number; seq: number; type: string; data: Record<string, any>; created_at: string }

/** Motion graphics made in chat (app/motion_graphic.py). */
export interface MotionVersion { n: number; created_at: number; change: string; notes: string[]; title: string; summary: string; format: "vertical" | "horizontal" | "square"; duration: number; width: number; height: number; }
export interface MotionGraphic {
  id: string; conversation_id: string; status: "queued" | "writing" | "checking" | "rendering" | "needs_input" | "completed" | "failed"; stage: string;
  progress: number; message: string; questions: string[]; error: string | null; request: string; versions: MotionVersion[]; current: number; active: boolean; updated_at: number; log: { key: string; text: string; state: "active" | "done" | "note"; at: number }[]; eta_s: number | null; eta_at: number | null;
}

/** Long-video content discovery (app/long_video.py). */
export type CandidateStatus = "discovered" | "selected" | "editing" | "rendering" | "completed" | "failed";
export interface DiscoveryCandidate {
  id: string; title: string; summary: string; hook: string; hook_source: string; category: string; rationale: string; score: number;
  ranges: [number, number][]; estimated_duration: number; status: CandidateStatus; hidden: boolean;
  child_conversation_id: string | null; child_project_id: string | null; child_stale?: boolean; revisions: { revision: number }[]; problems?: string[];
}
export interface DiscoveryAnalysis {
  id: string; conversation_id: string; filename: string; duration: number; language: string | null; stage: string; message: string; error: string | null;
  transcription_status: string; discovery_status: string; transcript_version: string | null; analysis_version: number;
  progress: { processed_s: number; duration_s: number; percent: number; eta_s: number | null };
  estimate: { model: string; transcription_s: number; total_s: number } | null; media: { width?: number; height?: number; has_audio: boolean };
  running: boolean; interrupted: boolean; transcript_tail: { id: string; start: number; end: number; text: string }[]; chunks: number; enhanced_chunks: number;
  candidates: DiscoveryCandidate[];
}

/** Plain-language Creative Plan built by the backend from the real analysis (app/creative_plan.py). */
export interface PlanConcept { id: string; name: string; angle: string; hook: string; style: string; selected: boolean; why: string }
export interface PlanContent {
  kind: "talking"; goal: string; audience: string; message: string; tone: string;
  concept: { name: string; angle: string };
  hook: { text: string; highlight: string[] };
  structure: { role: string; intent: string; visual: string; sentence: number | null; at: string; text: string }[];
  duration_s: number;
  style: { id: string; label: string; summary: string; complexity: string };
  look: { preset: string; grade: Record<string, number>; accent_color: string; caption_font: string; zoom: number; key_moments: boolean;
  key_moment_effect: string; cold_open: boolean; cold_open_sentence: number | null; zoom_enabled: boolean; zoom_base: number; zoom_close: number; bottom_shade?: number;
  moments: { sentence: number; title: string }[] };
  captions: string; motion: string; broll: string; pictures: { sentence: number; title: string; source: string; new: boolean }[];
  audio: { music: string; voice: string; sfx: string };
  brand: { name: string; tagline: string; cta: string; logo: { enabled: boolean; motion: string; has_logo: boolean } };
  format: { aspect: string; resolution: string; fps: number };
  engines: string[];
  estimate: { render: { low_s: number; high_s: number; samples: number } | null; paid_media: boolean; new_images?: number; note: string };
  concepts: PlanConcept[];
  timeline_edits: Record<string, { text?: string; start?: number; end?: number; deleted?: boolean; x?: number; y?: number; scale?: number; color?: string }>;
  broll_edits: Record<string, { source: PictureSource; media?: string; library?: string; visual?: string; label?: string }>;
  style_options: { id: string; label: string; summary: string; complexity: string }[];
  frames?: Record<string, string>;
}
export interface PlanVersion { id: string; n: number; source: string; note: string; created_at: number; fingerprint: string; content: PlanContent }
export interface PlanState { versions: PlanVersion[]; approved_id: string | null }
export type PlanEdits = Partial<{
  hook: string; hook_highlight: string[]; look: string; accent_color: string; caption_font: string; zoom: number; bottom_shade: number;
  key_moments: boolean; logo_enabled: boolean; logo_motion: string; name: string; tagline: string; cta: string;
  concept_id: string; style: string; timeline_edits: PlanContent["timeline_edits"]; broll_edits: PlanContent["broll_edits"];
  music: string; music_mix: Partial<MusicMix>;
  cold_open: boolean; cold_open_sentence: number | null; key_moment_effect: string; zoom_enabled: boolean; zoom_base: number; zoom_close: number;
}>;
/** The music bed's mix: level under the voice (dB), fades (seconds) and automatic lowering while someone speaks. */
export interface MusicMix { volume_db: number; fade_in: number; fade_out: number; duck: boolean }
/** Engine-neutral project timeline (app/project_document.py). Read-only in this phase. */
export interface DocElement {
  id: string; type: string; start: number; end: number; label: string; text: string;
  source: { kind?: string; label?: string; file?: string | null; in?: number; out?: number };
  props: Record<string, any>; edit: { via: ("plan" | "chat" | "timeline" | "advanced")[]; note: string };
}
export interface DocTrack { id: string; kind: string; label: string; elements: DocElement[] }
/** The plan rendered without captions: what the timeline edits captions on (see app/clean_base.py). */
export interface CleanBase { state: "ready" | "building" | "missing" | "failed" | "unsupported"; key?: string; reason?: string }

export interface ProjectDocument {
  schema: number; engine: string; style: string; canvas: { width: number; height: number; fps: number };
  duration: number; content_duration: number; tracks: DocTrack[];
  /** synced: true = the video was rendered from exactly this timeline; false = it was not; null = unknown. */
  basis: { plan_version: number | null; rendered_version: number | null; workflow: string | null; synced: boolean | null };
  stale_edits: string[]; edit_count: number; notes: string[];
}
export type PictureSource = "upload" | "library" | "ai" | "hidden";
export interface PictureOp { slot: number; source?: PictureSource; media?: string; library?: string; visual?: string; label?: string; reset?: boolean }
export interface LibraryPicture { path: string; name: string; tags: string[] }
export interface TimelineOp { id: string; text?: string; start?: number; end?: number; deleted?: boolean; reset?: boolean; x?: number; y?: number; scale?: number; color?: string }
export interface BrandProfile {
  name: string; tagline: string; cta: string; accent_color: string; caption_font: string; logo_motion: string;
  answered: string[]; has_logo: boolean; updated_at: number | null;
}

async function authFetch(url: string, init?: RequestInit): Promise<Response> {
  await ensureFreshToken();
  const token = getToken();
  const headers = new Headers(init?.headers);
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const r = await fetch(url, { ...init, headers });
  if (r.status === 401) handleUnauthorized();
  if (r.ok && isJobMutation(url, init)) invalidateJobCache();
  return r;
}

export async function aiAdminRequest<T>(path: string, init?: RequestInit): Promise<T> {
  return j<T>(await authFetch(`${BASE}/admin/ai${path}`, init));
}

export async function aiAdminCsv(query: string): Promise<void> {
  const response = await authFetch(`${BASE}/admin/ai/logs.csv?${query}`);
  if (!response.ok) { await j(response); return; }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a"); link.href = url; link.download = "ai-requests.csv"; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function authenticatedObjectUrl(url: string): Promise<string> {
  const response = await authFetch(url);
  if (!response.ok) {
    const message = await response.text().catch(() => "");
    throw new Error(`${response.status} ${message || response.statusText}`);
  }
  return URL.createObjectURL(await response.blob());
}

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) {
    const t = await r.text().catch(() => "");
    let msg = t;
    try { const d = JSON.parse(t).detail; msg = typeof d === "string" ? d : JSON.stringify(d); } catch { /* raw text */ }
    throw new Error(`${r.status}${msg ? ` ${msg}` : ` ${r.statusText || "Request failed"}`}`);
  }
  if (r.status === 204) return undefined as T;
  try {
    return await r.json() as T;
  } catch {
    throw new Error(`Server returned an invalid JSON response (${r.status} ${r.statusText})`);
  }
}

async function uploadWithProgress<T>(url: string, body: FormData,
  onProgress?: (percent: number) => void, signal?: AbortSignal): Promise<T> {
  await ensureFreshToken();
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    if (signal?.aborted) {
      reject(new Error("Upload was cancelled"));
      return;
    }
    const abort = () => xhr.abort();
    const cleanup = () => signal?.removeEventListener("abort", abort);
    xhr.open("POST", url);
    signal?.addEventListener("abort", abort, { once: true });
    const token = getToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = event => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.min(100, Math.round(event.loaded / event.total * 100)));
      }
    };
    xhr.onerror = () => { cleanup(); reject(new Error("Upload failed: network error")); };
    xhr.onabort = () => { cleanup(); reject(new Error("Upload was cancelled")); };
    xhr.onload = () => {
      cleanup();
      if (xhr.status === 401) {
        try { handleUnauthorized(); } catch (error) { reject(error); }
        return;
      }
      let data: any;
      try { data = JSON.parse(xhr.responseText); }
      catch {
        reject(new Error(`Server returned an invalid JSON response (${xhr.status} ${xhr.statusText})`));
        return;
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        const detail = data?.detail;
        reject(new Error(`${xhr.status} ${typeof detail === "string" ? detail : JSON.stringify(detail ?? xhr.statusText)}`));
        return;
      }
      resolve(data as T);
    };
    xhr.send(body);
  });
}

export interface LocalizeLine {
  i: number;
  start: number;
  end: number;
  en: string;
  fa: string;
  kind: "speech" | "lyrics" | "cta";
}

export interface TalkingReelState {
  status: "idle" | "running" | "paused" | "canceled" | "ready" | "done" | "error" | "needs_review";
  stage: string;
  message: string;
  progress: number;
  hook: string;
  hook_highlight: string[];
  name: string;
  title: string;
  music: string | null;
  cta: string;
  style: string;
  suggested_style?: string | null;
  suggested_style_reason?: string;
  analysis_ready?: boolean;
  hook2?: string;
  captions?: { i: number; text: string }[];
  storyboard?: { i: number; title: string; visual_type: string; narrative_role?: string; motion_style?: string; why?: string }[];
  timeline?: { id: string; sentence: number; title: string; kind: "key_moment"; order: number }[];
  key_moments?: { i: number; text: string }[];
  render_settings?: TalkingRenderSettings;
  visual_beats?: { title: string; visual_type: string; start: number; end: number; registry_refs?: string[] }[];
  catalog_reviewed?: number;
  visual_qc?: { passed: boolean; problems: string[]; samples: number; mean_scene_change: number };
  slots?: { i: number; label: string; source: "upload" | "library" | "ai" | "card"; file: string | null }[];
  output: string | null;
  logo_uploaded?: boolean;
  duration?: number;
  shots?: number;
}

export interface TalkingEffect { fx: string; start: number; end: number; text?: string; [option: string]: string | number | undefined }
export interface EffectOption { key: string; label: string; type: "number" | "choice" | "color"; default?: number | string; min?: number; max?: number; step?: number; choices?: string[] }
export interface EffectSpec { id: string; title: string; description: string; text?: { label: string; default: string }; options: EffectOption[] }
export interface TalkingEffects { catalog: EffectSpec[]; available: boolean; plan: TalkingEffect[]; error: string }

export interface TalkingRenderSettings {
  bottom_shade?: number;
  effects?: TalkingEffect[];
  grade: { brightness: number; contrast: number; saturation: number; temperature: number; vignette: number };
  zoom: { enabled: boolean; amount: number; base_scale: number; close_scale: number };
  key_moments_enabled: boolean;
  first_key_moment_enabled: boolean;
  first_key_moment_sentence: number | null;
  key_moment_effect: "grayscale_title" | "title_only" | "grayscale" | "none";
  title_color: string;
  outro_logo: { enabled: boolean; motion: "pop" | "fade" | "slide" | "none" };
  disabled_moments: string[];
}

export interface TalkingReelSummary {
  job_id: string;
  name: string | null;
  status: TalkingReelState["status"];
  stage: string;
  hook: string;
  output: string | null;
  updated_at: number;
}

export type LocalizeBoxColour = "black" | "white" | "red" | "blue" | "green";

export interface LocalizeProject {
  id: string;
  name: string;
  status: "queued" | "analyzing" | "ready" | "rendering" | "paused" | "canceled" | "done" | "error";
  stage: string;
  message: string;
  progress: number;
  cta_number: string;
  music: string | null;
  voice_provider: "elevenlabs";
  caption_box?: LocalizeBoxColour | null;
  title_box?: LocalizeBoxColour | null;
  end_card?: boolean;
  end_card_seconds?: number;
  title: string;
  title_emojis: string;
  lines: LocalizeLine[];
  output: string | null;
  cost_usd: number;
  created_at: number;
}

export type LocalizeSummary = Pick<LocalizeProject, "id" | "name" | "status" | "stage" | "message" | "title" | "output" | "progress" | "created_at"> & {
  updated_at?: number;
};

export const api = {
  authenticatedObjectUrl,
  async downloadAuthenticated(url: string, filename: string, openInNewTab = false,
    onProgress?: (percent: number | null) => void): Promise<void> {
    // A download starts the moment it is clicked: the browser fetches the file itself (its own download bar, any size, no waiting for the whole
    // file to arrive in memory first). The read-only media cookie authenticates that request; only if it cannot be set does the old path run.
    if (!openInNewTab && !onProgress && url.startsWith(BASE + "/")) {
      try {
        await api.prepareMediaPlayback();
        const direct = document.createElement("a");
        direct.href = url;
        direct.download = filename;
        document.body.appendChild(direct);
        direct.click();
        direct.remove();
        return;
      } catch { /* fall through to the authenticated fetch below */ }
    }
    let objectUrl: string;
    if (onProgress) {
      const response = await authFetch(url);
      if (!response.ok) {
        const message = await response.text().catch(() => "");
        throw new Error(`${response.status} ${message || response.statusText}`);
      }
      const total = Number(response.headers.get("content-length")) || 0;
      const reader = response.body?.getReader();
      if (!reader) {
        onProgress(null);
        objectUrl = URL.createObjectURL(await response.blob());
      } else {
        const chunks: Uint8Array[] = [];
        let received = 0;
        onProgress(total ? 0 : null);
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          chunks.push(value);
          received += value.byteLength;
          onProgress(total ? Math.min(100, Math.round(received / total * 100)) : null);
        }
        objectUrl = URL.createObjectURL(new Blob(chunks as BlobPart[], { type: response.headers.get("content-type") || "application/octet-stream" }));
      }
    } else {
      objectUrl = await authenticatedObjectUrl(url);
    }
    if (openInNewTab) {
      const opened = window.open(objectUrl, "_blank", "noopener");
      if (!opened) URL.revokeObjectURL(objectUrl);
      else window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
      return;
    }
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
  },
  async signup(email: string, name: string, password: string): Promise<{ access_token: string; refresh_token: string; user: { id: string; email: string; name: string } }> {
    const r = await fetch(`${BASE}/auth/signup`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ email, name, password }),
    });
    if (!r.ok) {
      const t = await r.text();
      let msg = t;
      try { msg = JSON.parse(t).detail; } catch {}
      throw new Error(msg);
    }
    const data = await r.json();
    setToken(data.access_token);
    return data;
  },
  async login(email: string, password: string): Promise<{ access_token: string; refresh_token: string; user: { id: string; email: string; name: string } }> {
    const r = await fetch(`${BASE}/auth/login`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!r.ok) {
      const t = await r.text();
      let msg = t;
      try { msg = JSON.parse(t).detail; } catch {}
      throw new Error(msg);
    }
    const data = await r.json();
    setToken(data.access_token);
    return data;
  },
  async forgotPassword(email: string): Promise<{ ok: boolean; message: string; _dev_token?: string }> {
    const r = await fetch(`${BASE}/auth/forgot-password`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ email }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "Could not send the password reset email");
    return data;
  },
  async resetPassword(token: string, new_password: string): Promise<{ ok: boolean }> {
    const r = await fetch(`${BASE}/auth/reset-password`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ token, new_password }),
    });
    if (!r.ok) {
      const t = await r.text();
      let msg = t;
      try { msg = JSON.parse(t).detail; } catch {}
      throw new Error(msg);
    }
    return r.json();
  },
  async getMe(): Promise<{ id: string; email: string; name: string }> {
    return j(await authFetch(`${BASE}/auth/me`));
  },

  async createJob(video: File, plan?: File | string,
    onProgress?: (percent: number) => void, signal?: AbortSignal): Promise<{ job: Job; errors: string[] }> {
    const fd = new FormData();
    fd.append("video", video);
    if (plan instanceof File) fd.append("plan", plan);
    else if (typeof plan === "string") fd.append("plan_text", plan);
    return uploadWithProgress(`${BASE}/jobs`, fd, onProgress, signal);
  },
  async getJob(id: string, signal?: AbortSignal): Promise<Job> {
    return j(await authFetch(`${BASE}/jobs/${id}`, { signal }));
  },
  async listJobs(): Promise<Job[]> {
    return j(await authFetch(`${BASE}/jobs`));
  },
  async putPlan(id: string, plan: any): Promise<{ ok: boolean; errors?: string[] }> {
    const r = await authFetch(`${BASE}/jobs/${id}/plan`, {
      method: "PUT", headers: { "content-type": "application/json" },
      body: JSON.stringify({ plan }),
    });
    if (r.status === 422) return r.json();
    return j(r);
  },
  async validate(id: string, plan: any, signal?: AbortSignal): Promise<{ ok: boolean; errors: string[] }> {
    return j(await authFetch(`${BASE}/jobs/${id}/validate`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ plan }),
      signal,
    }));
  },
  async generatePlan(id: string, opts?: {
    style?: string; instruction?: string;
    whisper_model?: string; language?: string | null; use_saved_transcript?: boolean;
    transcribe_only?: boolean;
    transcription_hint?: string;
    asr_engine?: string;
    caption_font?: string;
    caption_font_id?: string;
    style_id?: string; style_version?: number;
    output_kind?: "reel" | "story" | "post";
    transition_style?: "auto" | "none" | "crossfade" | "directional" | "zoom";
    transition_request?: string;
  }): Promise<{ status: string; stage: string }> {
    return j(await authFetch(`${BASE}/jobs/${id}/generate-plan`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify(opts || {}),
    }));
  },
  async getStyleLibrary(): Promise<StyleLibraryData> { return j(await authFetch(`${BASE}/style-library`)); },
  async addStyleSnapshots(files: File[], name: string): Promise<StyleDraft> {
    const fd = new FormData(); files.forEach(file => fd.append("files", file)); fd.append("name", name);
    return j(await authFetch(`${BASE}/style-library/snapshots`, { method: "POST", body: fd }));
  },
  async addStyleVideo(file: File, name: string): Promise<StyleDraft> {
    const fd = new FormData(); fd.append("file", file); fd.append("name", name);
    return j(await authFetch(`${BASE}/style-library/video`, { method: "POST", body: fd }));
  },
  async addStyleFile(file: File, name: string): Promise<StyleDraft> {
    const fd = new FormData(); fd.append("file", file); fd.append("name", name);
    return j(await authFetch(`${BASE}/style-library/file`, { method: "POST", body: fd }));
  },
  async updateStyleDraft(id: string, draft: { name: string; profile: any }): Promise<StyleDraft> {
    return j(await authFetch(`${BASE}/style-library/drafts/${id}`, { method: "PUT",
      headers: { "content-type": "application/json" }, body: JSON.stringify(draft) }));
  },
  async approveStyleDraft(id: string): Promise<StyleProfile> {
    return j(await authFetch(`${BASE}/style-library/drafts/${id}/approve`, { method: "POST" }));
  },
  async forkStyleProfile(styleId: string, version: number): Promise<StyleDraft> {
    return j(await authFetch(`${BASE}/style-library/profiles/${styleId}/versions/${version}/draft`, { method: "POST" }));
  },
  async deleteStyleDraft(id: string): Promise<{ ok: boolean; id: string; state: string }> {
    return j(await authFetch(`${BASE}/style-library/drafts/${id}`, { method: "DELETE" }));
  },
  async deleteStyleProfile(styleId: string, version: number): Promise<{ ok: boolean; style_id: string; version: number; state: string }> {
    return j(await authFetch(`${BASE}/style-library/profiles/${styleId}/versions/${version}`, { method: "DELETE" }));
  },
  async getPlanStyleSelection(): Promise<PlanStyleSelection> {
    return j(await authFetch(`${BASE}/style/plan-selection`));
  },
  async setPlanStyleSelection(styleId: string | null, version: number | null): Promise<PlanStyleSelection & { ok: boolean }> {
    return j(await authFetch(`${BASE}/style/plan-selection`, {
      method: "PUT", headers: { "content-type": "application/json" },
      body: JSON.stringify({ style_id: styleId, version }),
    }));
  },
  async clearPlanStyleSelection(): Promise<PlanStyleSelection & { ok: boolean }> {
    return j(await authFetch(`${BASE}/style/plan-selection`, {
      method: "PUT", headers: { "content-type": "application/json" },
      body: JSON.stringify({ style_id: null, version: null, selected: false }),
    }));
  },
  async setPlanDefaultVisibility(hidden: boolean): Promise<{ ok: boolean; default_hidden: boolean }> {
    return j(await authFetch(`${BASE}/style/plan-default-visibility`, {
      method: "PUT", headers: { "content-type": "application/json" },
      body: JSON.stringify({ hidden }),
    }));
  },
  styleEvidenceUrl(asset: string): string { return `${BASE}/style-library/evidence/${encodeURIComponent(asset)}`; },
  async generateStatus(id: string, signal?: AbortSignal): Promise<GenerateStatus> {
    return j(await authFetch(`${BASE}/jobs/${id}/generate-plan/status`, { signal }));
  },
  async getTranscript(id: string, signal?: AbortSignal): Promise<Transcript> {
    return j(await authFetch(`${BASE}/jobs/${id}/transcript`, { signal }));
  },
  async putTranscriptCorrections(id: string, base_key: string,
    words: { index: number; text: string; start?: number; end?: number }[]): Promise<Transcript> {
    return j(await authFetch(`${BASE}/jobs/${id}/transcript/corrections`, {
      method: "PUT", headers: { "content-type": "application/json" },
      body: JSON.stringify({ base_key, words }),
    }));
  },
  async listEffects(signal?: AbortSignal): Promise<EffectPreset[]> {
    return j(await authFetch(`${BASE}/effects`, { signal }));
  },
  async listFonts(signal?: AbortSignal): Promise<string[]> {
    const data = await j<{ fonts: string[] }>(await authFetch(`${BASE}/fonts`, { signal }));
    return data.fonts;
  },
  async getFontLibrary(): Promise<FontLibrary> {
    return j(await authFetch(`${BASE}/font-library`));
  },
  async addFontTextReference(body: { name: string; copied_text: string; font_name?: string; visual_reference?: string }): Promise<FontEntry> {
    return j(await authFetch(`${BASE}/font-library/text`, { method: "POST",
      headers: { "content-type": "application/json" }, body: JSON.stringify(body) }));
  },
  async addFontImage(file: File): Promise<FontEntry> {
    const fd = new FormData(); fd.append("image", file);
    return j(await authFetch(`${BASE}/font-library/image`, { method: "POST", body: fd }));
  },
  async addFontFile(file: File): Promise<FontEntry> {
    const fd = new FormData(); fd.append("font", file);
    return j(await authFetch(`${BASE}/font-library/font`, { method: "POST", body: fd }));
  },
  async approveFont(id: string): Promise<FontEntry> {
    return j(await authFetch(`${BASE}/font-library/${id}/approve`, { method: "POST" }));
  },
  async deleteFont(id: string): Promise<{ ok: boolean; id: string; state: string }> {
    return j(await authFetch(`${BASE}/font-library/${id}`, { method: "DELETE" }));
  },
  fontFileUrl(id: string, candidate = false): string {
    return candidate ? `${BASE}/font-library/candidates/${id}/file` : `${BASE}/font-library/fonts/${id}/file`;
  },
  async getMyEffects(): Promise<any> {
    return j(await authFetch(`${BASE}/my-effects`));
  },
  async putMyEffects(data: any): Promise<any> {
    return j(await authFetch(`${BASE}/my-effects`, {
      method: "PUT", headers: { "content-type": "application/json" },
      body: JSON.stringify(data),
    }));
  },
  async getRafieiStyles(): Promise<RafieiStyle> {
    return j(await authFetch(`${BASE}/rafiei-styles`));
  },
  async selectRafieiStyle(styleId: string | null): Promise<{ ok: boolean; selected_rafiei_style: string | null }> {
    return j(await authFetch(`${BASE}/my-effects/select-rafiei`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ style_id: styleId }),
    }));
  },
  async getCorrections(id: string, signal?: AbortSignal): Promise<Corrections> {
    return j(await authFetch(`${BASE}/jobs/${id}/corrections`, { signal }));
  },
  async acceptCorrection(id: string, body: {
    base_key: string; index: number; old: string; new: string;
    start?: number; end?: number; save_to_glossary?: boolean;
  }): Promise<any> {
    return j(await authFetch(`${BASE}/jobs/${id}/corrections/accept`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }));
  },
  async rejectCorrection(id: string, body: { index: number; old: string }): Promise<any> {
    return j(await authFetch(`${BASE}/jobs/${id}/corrections/reject`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }));
  },
  async render(id: string, preview: boolean, loudnorm = true): Promise<{ status: string }> {
    return j(await authFetch(`${BASE}/jobs/${id}/render?preview=${preview}&loudnorm=${loudnorm}`, { method: "POST" }));
  },
  async renderStatus(id: string, signal?: AbortSignal) {
    return j<{
      status: string; progress: number; message: string;
      output?: string; preview: boolean; versions: string[];
    }>(await authFetch(`${BASE}/jobs/${id}/render/status`, { signal }));
  },
  premiereUrl(id: string) { return `${BASE}/jobs/${id}/premiere`; },
  premiereXmlUrl(id: string) { return `${BASE}/jobs/${id}/premiere.xml`; },
  premiereCaptionsUrl(id: string) { return `${BASE}/jobs/${id}/premiere/captions`; },
  premiereReportUrl(id: string) { return `${BASE}/jobs/${id}/premiere/report`; },
  async premiereReport(id: string, signal?: AbortSignal) {
    return j<any>(await authFetch(`${BASE}/jobs/${id}/premiere/report`, { signal }));
  },
  async premiereStatus(id: string) {
    return j<PremiereStatus>(await authFetch(`${BASE}/jobs/${id}/premiere/status`));
  },
  async openPremiere(id: string, mode: PremiereMode, confirmPreview = false) {
    return j<{ status: string; message: string }>(await authFetch(`${BASE}/jobs/${id}/premiere/open`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ mode, confirm_preview: confirmPreview }),
    }));
  },
  async linkPremiereProject(id: string) {
    return j<{ status: string; project_name: string; message?: string }>(await authFetch(`${BASE}/jobs/${id}/premiere/link-project`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ project_name: `ai-render-${id}-clean.prproj` }),
    }));
  },
  async startPremiereBridge(id: string, forceRefresh = false) {
    return j<{ operation_id: string; pairing_code: string; state: string; expires_in_seconds: number; bridge_kind: string }>(
      await authFetch(`${BASE}/jobs/${id}/premiere/bridge/session`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ force_refresh: forceRefresh }),
      }));
  },
  async runQC(id: string): Promise<{ status: string }> {
    return j(await authFetch(`${BASE}/jobs/${id}/qc/run`, { method: "POST" }));
  },
  async qcStatus(id: string) {
    return j<{
      status: string; message: string; current_round: number;
      total_issues: number; fixed_issues: number;
      issues: any[]; changes: any[];
    }>(await authFetch(`${BASE}/jobs/${id}/qc/status`));
  },
  async applyQCFixes(id: string, issueIndices?: number[]): Promise<{ ok: boolean; changes: any[]; plan: any }> {
    return j(await authFetch(`${BASE}/jobs/${id}/qc/apply`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ issue_indices: issueIndices ?? null }),
    }));
  },
  async uploadMusic(id: string, file: File): Promise<{ ok: boolean; path: string }> {
    const fd = new FormData();
    fd.append("file", file);
    return j(await authFetch(`${BASE}/jobs/${id}/music/upload`, { method: "POST", body: fd }));
  },
  async generateMusic(id: string, prompt: string): Promise<{ ok: boolean; path: string }> {
    return j(await authFetch(`${BASE}/jobs/${id}/music/generate`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ prompt }),
    }));
  },
  async importLibraryMusic(id: string, filename: string): Promise<{ ok: boolean; path: string }> {
    const response = await authFetch(`${BASE}/library/music/${encodeURIComponent(filename)}/preview`);
    if (!response.ok) throw new Error(`Could not read library track (${response.status})`);
    return api.uploadMusic(id, new File([await response.blob()], filename));
  },
  musicPreviewUrl(id: string, filename?: string) {
    return `${BASE}/jobs/${id}/music/preview${filename ? `?filename=${encodeURIComponent(filename)}` : ""}`;
  },
  // Background music mixed into the render
  async getMusicStatus(id: string, signal?: AbortSignal): Promise<MusicStatus> {
    return j(await authFetch(`${BASE}/jobs/${id}/music/status`, { signal }));
  },
  attachMusic(id: string, file: File, onProgress?: (percent: number) => void): Promise<MusicStatus> {
    const fd = new FormData();
    fd.append("file", file);
    return uploadWithProgress(`${BASE}/jobs/${id}/music`, fd, onProgress);
  },
  async mixMusic(id: string, settings: { volume_level: number; fade_in_seconds: number; fade_out_seconds: number }): Promise<{ status: string }> {
    return j(await authFetch(`${BASE}/jobs/${id}/music/mix`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify(settings),
    }));
  },
  async removeMusic(id: string): Promise<{ ok: boolean }> {
    return j(await authFetch(`${BASE}/jobs/${id}/music`, { method: "DELETE" }));
  },
  musicMixPreviewUrl(id: string, settings: { volume_level: number; fade_in_seconds: number; fade_out_seconds: number }, nonce: number) {
    const q = new URLSearchParams({
      volume_level: String(settings.volume_level), fade_in_seconds: String(settings.fade_in_seconds),
      fade_out_seconds: String(settings.fade_out_seconds), t: String(nonce),
    });
    return `${BASE}/jobs/${id}/music/preview?${q}`;
  },
  // ── Denoise ──
  async startDenoise(id: string, strength = 0.5): Promise<{ status: string }> {
    return j(await authFetch(`${BASE}/jobs/${id}/denoise/start`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ strength }),
    }));
  },
  async triggerDenoise(id: string, strength: "light" | "medium" | "heavy", preserveVoice: boolean): Promise<{ status: string }> {
    return j(await authFetch(`${BASE}/jobs/${id}/denoise`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ strength, preserve_voice: preserveVoice }),
    }));
  },
  async getDenoiseCompare(id: string): Promise<{ original_url: string; denoised_url: string }> {
    return j(await authFetch(`${BASE}/jobs/${id}/denoise/compare`));
  },
  async applyDenoise(id: string): Promise<any> {
    return j(await authFetch(`${BASE}/jobs/${id}/denoise/apply`, { method: "POST" }));
  },
  async getDenoiseStatus(id: string): Promise<any> {
    return j(await authFetch(`${BASE}/jobs/${id}/denoise/status`));
  },
  async getDenoiseSamples(id: string): Promise<{ original_url: string; cleaned_url: string; offset_s: number; duration_s: number }> {
    return j(await authFetch(`${BASE}/jobs/${id}/denoise/samples`));
  },
  async approveDenoise(id: string): Promise<any> {
    return j(await authFetch(`${BASE}/jobs/${id}/denoise/approve`, { method: "POST" }));
  },
  async bypassDenoise(id: string, bypass: boolean): Promise<any> {
    return j(await authFetch(`${BASE}/jobs/${id}/denoise/bypass`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ bypass }),
    }));
  },
  async adjustDenoise(id: string, strength: number): Promise<{ status: string }> {
    return j(await authFetch(`${BASE}/jobs/${id}/denoise/adjust`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ strength }),
    }));
  },
  denoiseAudioUrl(id: string, which: "original" | "cleaned"): string {
    return `${BASE}/jobs/${id}/denoise/sample/${which}`;
  },

  rawUrl(id: string) { return `${BASE}/jobs/${id}/raw`; },
  exportUrl(id: string, fname: string) { return `${BASE}/jobs/${id}/exports/${fname}`; },
  planUrl(id: string) { return `${BASE}/jobs/${id}/plan.json`; },

  // ── Localization (Dropshipping) ──
  async listLocalize(): Promise<LocalizeSummary[]> {
    return j(await authFetch(`${BASE}/localize`));
  },
  async getLocalize(id: string): Promise<LocalizeProject> {
    return j(await authFetch(`${BASE}/localize/${id}`));
  },
  async createLocalize(video: File, ctaNumber: string, music: string | null,
    onProgress?: (percent: number) => void): Promise<LocalizeProject> {
    const fd = new FormData();
    fd.append("video", video);
    fd.append("cta_number", ctaNumber);
    if (music) fd.append("music", music);
    return uploadWithProgress(`${BASE}/localize`, fd, onProgress);
  },
  async editLocalize(id: string, body: Partial<Pick<LocalizeProject, "title" | "title_emojis" | "cta_number" | "music" | "voice_provider" | "caption_box" | "title_box" | "end_card" | "end_card_seconds">>
    & { lines?: { i: number; fa?: string; kind?: LocalizeLine["kind"] }[] }): Promise<LocalizeProject> {
    return j(await authFetch(`${BASE}/localize/${id}`, {
      method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
    }));
  },
  async analyzeLocalize(id: string): Promise<LocalizeProject> {
    return j(await authFetch(`${BASE}/localize/${id}/analyze`, { method: "POST" }));
  },
  async renderLocalize(id: string): Promise<LocalizeProject> {
    return j(await authFetch(`${BASE}/localize/${id}/render`, { method: "POST" }));
  },
  async pauseLocalize(id: string): Promise<LocalizeProject> {
    return j(await authFetch(`${BASE}/localize/${id}/pause`, { method: "POST" }));
  },
  async resumeLocalize(id: string): Promise<LocalizeProject> {
    return j(await authFetch(`${BASE}/localize/${id}/resume`, { method: "POST" }));
  },
  async cancelLocalize(id: string): Promise<LocalizeProject> {
    return j(await authFetch(`${BASE}/localize/${id}/cancel`, { method: "POST" }));
  },
  async deleteLocalize(id: string): Promise<void> {
    return j(await authFetch(`${BASE}/localize/${id}`, { method: "DELETE" }));
  },
  async getTalkingEffects(jobId: string): Promise<TalkingEffects> {
    return j(await authFetch(`${BASE}/jobs/${jobId}/talking-reel/effects`));
  },
  async previewTalkingEffect(jobId: string, item: TalkingEffect, t: number): Promise<string> {
    const response = await authFetch(`${BASE}/jobs/${jobId}/talking-reel/effects/preview`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ item, t }) });
    if (!response.ok) {
      const message = await response.json().then(value => String(value?.detail || ""), () => "");
      throw new Error(message || `${response.status} ${response.statusText}`);
    }
    return URL.createObjectURL(await response.blob());
  },
  async getTalkingReel(jobId: string): Promise<TalkingReelState> {
    return j(await authFetch(`${BASE}/jobs/${jobId}/talking-reel`));
  },
  async editTalkingReel(jobId: string, body: Partial<Pick<TalkingReelState, "hook" | "hook2" | "hook_highlight" | "name" | "title" | "music" | "cta" | "style" | "captions" | "storyboard" | "render_settings" | "key_moments">>): Promise<TalkingReelState> {
    return j(await authFetch(`${BASE}/jobs/${jobId}/talking-reel`, {
      method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
    }));
  },
  async renderTalkingReel(jobId: string, regenerate = false): Promise<TalkingReelState> {
    return j(await authFetch(`${BASE}/jobs/${jobId}/talking-reel/render?regenerate=${regenerate}`, { method: "POST" }));
  },
  async analyzeTalkingReel(jobId: string, style?: string): Promise<TalkingReelState> {
    const query = style ? `?style=${encodeURIComponent(style)}` : "";
    return j(await authFetch(`${BASE}/jobs/${jobId}/talking-reel/analyze${query}`, { method: "POST" }));
  },
  async pauseTalkingReel(jobId: string): Promise<TalkingReelState> {
    return j(await authFetch(`${BASE}/jobs/${jobId}/talking-reel/pause`, { method: "POST" }));
  },
  async resumeTalkingReel(jobId: string): Promise<TalkingReelState> {
    return j(await authFetch(`${BASE}/jobs/${jobId}/talking-reel/resume`, { method: "POST" }));
  },
  async cancelTalkingReel(jobId: string): Promise<TalkingReelState> {
    return j(await authFetch(`${BASE}/jobs/${jobId}/talking-reel/cancel`, { method: "POST" }));
  },
  async talkingReelMedia(jobId: string): Promise<string[]> {
    return j(await authFetch(`${BASE}/jobs/${jobId}/talking-reel/media`));
  },
  async uploadTalkingReelMedia(jobId: string, files: File[]): Promise<{ saved: string[]; media: string[] }> {
    const fd = new FormData();
    files.forEach(f => fd.append("files", f));
    return j(await authFetch(`${BASE}/jobs/${jobId}/talking-reel/media`, { method: "POST", body: fd }));
  },
  async deleteTalkingReelMedia(jobId: string, name: string): Promise<void> {
    return j(await authFetch(`${BASE}/jobs/${jobId}/talking-reel/media/${encodeURIComponent(name)}`, { method: "DELETE" }));
  },
  async uploadTalkingReelLogo(jobId: string, file: File): Promise<{ logo_uploaded: boolean }> {
    const fd = new FormData(); fd.append("file", file);
    return j(await authFetch(`${BASE}/jobs/${jobId}/talking-reel/logo`, { method: "POST", body: fd }));
  },
  async deleteTalkingReelLogo(jobId: string): Promise<void> {
    return j(await authFetch(`${BASE}/jobs/${jobId}/talking-reel/logo`, { method: "DELETE" }));
  },
  talkingReelLogoUrl(jobId: string): string { return `${BASE}/jobs/${jobId}/talking-reel/logo`; },
  async talkingReelStyles(): Promise<{ id: string; label: string }[]> {
    return j(await authFetch(`${BASE}/talking-reels/styles`));
  },
  async listTalkingReels(): Promise<TalkingReelSummary[]> {
    return j(await authFetch(`${BASE}/talking-reels`));
  },
  talkingReelOutputUrl(jobId: string): string { return `${BASE}/jobs/${jobId}/talking-reel/output`; },
  localizeOutputUrl(id: string): string { return `${BASE}/localize/${id}/output`; },
  localizeSourceUrl(id: string): string { return `${BASE}/localize/${id}/source`; },

  // ── Asset Library ──
  async getLibrary(): Promise<LibraryData> {
    return j(await authFetch(`${BASE}/library`));
  },
  async rescanLibrary(): Promise<{ ok: boolean; counts: Record<string, number> }> {
    return j(await authFetch(`${BASE}/library/rescan`, { method: "POST" }));
  },
  async uploadLibraryAsset(file: File, category: string, tags: string,
    mood?: string, energy?: number, description?: string): Promise<LibraryAsset> {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("category", category);
    fd.append("tags", tags);
    if (mood) fd.append("mood", mood);
    if (energy != null) fd.append("energy", String(energy));
    if (description) fd.append("description", description);
    return j(await authFetch(`${BASE}/library/upload`, { method: "POST", body: fd }));
  },
  async updateLibraryAsset(category: string, filename: string,
    body: { tags?: string[]; mood?: string; energy?: number; description?: string }): Promise<LibraryAsset> {
    return j(await authFetch(`${BASE}/library/${category}/${encodeURIComponent(filename)}`, {
      method: "PUT", headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }));
  },
  async deleteLibraryAsset(category: string, filename: string): Promise<{ ok: boolean }> {
    return j(await authFetch(`${BASE}/library/${category}/${encodeURIComponent(filename)}`, { method: "DELETE" }));
  },
  libraryPreviewUrl(category: string, filename: string): string {
    return `${BASE}/library/${category}/${encodeURIComponent(filename)}/preview`;
  },
  // ── Style Learner ──
  async analyzeReference(file: File, onProgress?: (percent: number) => void): Promise<any> {
    const fd = new FormData(); fd.append("file", file);
    return uploadWithProgress(`${BASE}/style/analyze`, fd, onProgress);
  },
  async getLearnedProfile(): Promise<LearnedStyleProfile> {
    return j(await authFetch(`${BASE}/style/profile`));
  },
  async updateLearnedProfile(body: any): Promise<{ ok: boolean }> {
    return j(await authFetch(`${BASE}/style/profile`, {
      method: "PUT", headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }));
  },
  async rebuildLearnedProfile(): Promise<any> {
    return j(await authFetch(`${BASE}/style/rebuild`, { method: "POST" }));
  },
  async resetLearnedProfile(): Promise<{ ok: boolean }> {
    return j(await authFetch(`${BASE}/style/reset`, { method: "POST" }));
  },
  async getFeedbackSummary(): Promise<any> {
    return j(await authFetch(`${BASE}/style/feedback`));
  },
  async getFewShotExamples(): Promise<{ examples: any[] }> {
    return j(await authFetch(`${BASE}/style/examples`));
  },
  async postPlanFeedback(id: string, events: any[]): Promise<{ ok: boolean; logged: number }> {
    return j(await authFetch(`${BASE}/jobs/${id}/feedback`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ events }),
    }));
  },
  async listReferenceAnalyses(): Promise<{ analyses: any[] }> {
    return j(await authFetch(`${BASE}/style/analyses`));
  },
  styleReferenceVideoUrl(refId: string): string {
    return `${BASE}/style/analyses/${encodeURIComponent(refId)}/video`;
  },
  async deleteReferenceAnalysis(filename: string): Promise<{ ok: boolean }> {
    return j(await authFetch(`${BASE}/style/analyses/${encodeURIComponent(filename)}`, { method: "DELETE" }));
  },

  async matchBroll(query: string, minDuration = 0): Promise<LibraryAsset[]> {
    const fd = new FormData();
    fd.append("query", query);
    fd.append("min_duration", String(minDuration));
    return j(await authFetch(`${BASE}/library/match/broll`, { method: "POST", body: fd }));
  },

  // ── Content Creator ──
  async createContent(prompt: string, content_type: string, language: string, style: string, provider: string,
                      creative_brief: { audience?: string; goal?: string; brand?: string; avoid?: string } = {}): Promise<{ job_id: string; storyboard: { scenes?: any[]; is_fallback?: boolean; [key: string]: any } }> {
    const result = await j<{ job_id: string; storyboard: { scenes?: any[]; is_fallback?: boolean; [key: string]: any } }>(await authFetch(`${BASE}/content/create`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ prompt, content_type, language, style, provider, creative_brief }),
    }));
    invalidateJobCache();
    return result;
  },
  async getStoryboard(id: string): Promise<any> {
    return j(await authFetch(`${BASE}/jobs/${id}/storyboard`));
  },
  async updateStoryboard(id: string, scenes: any[]): Promise<any> {
    return j(await authFetch(`${BASE}/jobs/${id}/storyboard`, {
      method: "PUT", headers: { "content-type": "application/json" },
      body: JSON.stringify({ scenes }),
    }));
  },
  async approveStoryboard(id: string, provider?: string, retryConfirmed = false): Promise<{ status: string }> {
    return j(await authFetch(`${BASE}/jobs/${id}/storyboard/approve`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...(provider ? { provider } : {}), retry_confirmed: retryConfirmed }),
    }));
  },
  async motionScenes(id: string): Promise<any> {
    return j(await authFetch(`${BASE}/jobs/${id}/motion-scenes`));
  },
  async createMotionScene(id:string, body:unknown):Promise<any> {
    return j(await authFetch(`${BASE}/jobs/${id}/motion-scenes`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)}));
  },
  async placeMotionScene(id:string,key:string,at:number,duration:number,sentenceIndex?:number):Promise<any> {
    return j(await authFetch(`${BASE}/jobs/${id}/motion-scenes/${key}/timeline`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({at,duration,sentence_index:sentenceIndex})}));
  },
  async getStoryboardStatus(id: string): Promise<{ state: string; scenes_done: number; scenes_total: number; cost_so_far: number | null; error?: string; warnings?: string[] } | null> {
    return j(await authFetch(`${BASE}/jobs/${id}/storyboard/status`));
  },
  async getProviders(signal?: AbortSignal): Promise<any[]> {
    return j(await authFetch(`${BASE}/content/providers`, { signal }));
  },
  async exportImage(id: string): Promise<Blob> {
    const r = await authFetch(`${BASE}/content/export-image/${id}`, { method: "POST" });
    if (!r.ok) throw new Error(`${r.status}`);
    return r.blob();
  },

  // ── Chat-first Video Studio ──
  async createStudioConversation(title = "گفتگوی جدید"): Promise<StudioConversation> {
    return j(await authFetch(`${BASE}/studio/conversations`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ title }) }));
  },
  async listStudioConversations(): Promise<StudioConversation[]> {
    return j(await authFetch(`${BASE}/studio/conversations`));
  },
  async openLegacyInStudio(engine: "motion" | "talking" | "localize", external_ref: string, title: string): Promise<StudioConversation> {
    return j(await authFetch(`${BASE}/studio/legacy/open`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ engine, external_ref, title }) }));
  },
  async getStudioConversation(id: string): Promise<StudioConversation> {
    return j(await authFetch(`${BASE}/studio/conversations/${id}`));
  },
  async agentPreferences(): Promise<{default_agent_mode: AgentMode}> {
    return j(await authFetch(`${BASE}/studio/agent-preferences`));
  },
  async saveAgentPreferences(default_agent_mode: AgentMode): Promise<{default_agent_mode: AgentMode}> {
    return j(await authFetch(`${BASE}/studio/agent-preferences`, {method:"PUT",headers:{"content-type":"application/json"},body:JSON.stringify({default_agent_mode})}));
  },
  async resumeAgentRun(id: string, decision: "approve" | "retry" | "cancel") {
    return j(await authFetch(`${BASE}/studio/agent-runs/${id}/resume`, {method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({decision})}));
  },
  async updateStudioConversation(id: string, patch: { title?: string; status_voice_enabled?: boolean; execution_mode?: "auto" | "manual"; agent_mode?: AgentMode }): Promise<StudioConversation> {
    return j(await authFetch(`${BASE}/studio/conversations/${id}`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify(patch) }));
  },
  async uploadStudioAttachment(id: string, file: File, onProgress?: (value: number) => void): Promise<StudioAttachment> {
    const form = new FormData(); form.append("file", file);
    return uploadWithProgress(`${BASE}/studio/conversations/${id}/attachments`, form, onProgress);
  },
  async sendStudioMessage(id: string, content: string, attachment_ids: string[], options: { execution_mode?: "auto" | "manual"; manual_question_id?: string; render_target?: "server" | "browser"; agent_mode?: AgentMode } = {}): Promise<StudioMessage> {
    return j(await authFetch(`${BASE}/studio/conversations/${id}/messages`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ content, attachment_ids, ...options }) }));
  },
  async setProjectRenderTarget(id: string, target: "server" | "browser"): Promise<StudioProject> {
    return j(await authFetch(`${BASE}/studio/projects/${id}/render-target`, {method:"PATCH",headers:{"content-type":"application/json"},body:JSON.stringify({target})}));
  },
  async projectRenderCapabilities(): Promise<{device_render_hold:boolean}> {
    return j(await authFetch(`${BASE}/studio/render-capabilities`));
  },
  async browserProject(id: string): Promise<{renderer:string;revision:string;width:number;height:number;fps:number;durationInFrames:number;props:Record<string,unknown>;assets:{id:string;bytes:number}[]}> {
    return j(await authFetch(`${BASE}/studio/projects/${id}/browser-render`));
  },
  async saveBrowserProject(id: string, revision: string, blob: Blob) {
    const form=new FormData();form.append("file",blob,"device.mp4");
    return j(await authFetch(`${BASE}/studio/projects/${id}/browser-render/output?revision=${encodeURIComponent(revision)}`,{method:"POST",body:form}));
  },
  async confirmStudioAction(id: string): Promise<StudioAction> {
    return j(await authFetch(`${BASE}/studio/actions/${id}/confirm`, { method: "POST" }));
  },
  async cancelStudioAction(id: string): Promise<StudioAction> {
    return j(await authFetch(`${BASE}/studio/actions/${id}/cancel`, { method: "POST" }));
  },
  async cancelStudioProject(id: string): Promise<any> {
    return j(await authFetch(`${BASE}/studio/projects/${id}/cancel`, { method: "POST" }));
  },
  async acceptStudioOutput(id: string, candidate: string): Promise<any> {
    return j(await authFetch(`${BASE}/studio/projects/${id}/accept-output`, {method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({candidate})}));
  },
  async studioOutputs(id: string): Promise<{file: string; version: number}[]> {
    return j(await authFetch(`${BASE}/studio/projects/${id}/outputs`));
  },
  async resumeStudioProject(id: string, retryConfirmed: boolean = false): Promise<any> {
    return j(await authFetch(`${BASE}/studio/projects/${id}/resume`, { method: "POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({retry_confirmed:retryConfirmed}) }));
  },
  async updateStudioStoryboard(id: string, scenes: any[]): Promise<StudioProject> {
    return j(await authFetch(`${BASE}/studio/projects/${id}/storyboard`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ scenes }) }));
  },
  async approveStudioPlan(id: string, versionId: string): Promise<StudioProject> {
    return j(await authFetch(`${BASE}/studio/projects/${id}/plan/approve`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ version_id: versionId }) }));
  },
  async editStudioPlan(id: string, versionId: string, edits: PlanEdits): Promise<StudioProject> {
    return j(await authFetch(`${BASE}/studio/projects/${id}/plan`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ version_id: versionId, edits }) }));
  },
  async editStudioPictures(id: string, versionId: string, ops: PictureOp[]): Promise<StudioProject> {
    return j(await authFetch(`${BASE}/studio/projects/${id}/pictures`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ version_id: versionId, ops }) }));
  },
  async uploadStudioPicture(id: string, file: File): Promise<{ name: string; size: number }> {
    const form = new FormData(); form.append("file", file);
    return j(await authFetch(`${BASE}/studio/projects/${id}/media`, { method: "POST", body: form }));
  },
  studioMusicUrl(path: string): string { return `${BASE}/studio/music/${encodeURIComponent(path.split("/").pop() || "")}`; },
  studioPictureUrl(id: string, slot: number): string { return `${BASE}/studio/projects/${id}/pictures/${slot}`; },
  async libraryPictures(): Promise<LibraryPicture[]> {
    return j(await authFetch(`${BASE}/studio/library/pictures`));
  },
  async editStudioTimeline(id: string, versionId: string, ops: TimelineOp[]): Promise<StudioProject> {
    return j(await authFetch(`${BASE}/studio/projects/${id}/timeline`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ version_id: versionId, ops }) }));
  },
  /** Localize: where captions sit on the frame. Saved on the project only; it starts no render and no voice generation. */
  async editLocalizeCaptions(id: string, ops: TimelineOp[]): Promise<void> {
    await j(await authFetch(`${BASE}/studio/projects/${id}/localize-captions`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ ops }) }));
  },
  async stopConversation(id: string): Promise<{ stopped: string[] }> { return j(await authFetch(`${BASE}/studio/conversations/${id}/stop`, { method: "POST" })); },
  async motionView(id: string): Promise<MotionGraphic> { return j(await authFetch(`${BASE}/studio/motion/${id}`)); },
  async motionRetry(id: string): Promise<void> { await j(await authFetch(`${BASE}/studio/motion/${id}/retry`, { method: "POST" })); },
  async motionStop(id: string): Promise<void> { await j(await authFetch(`${BASE}/studio/motion/${id}/stop`, { method: "POST" })); },
  async motionRevise(id: string, change: string): Promise<void> {
    await j(await authFetch(`${BASE}/studio/motion/${id}/revise`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ change }) }));
  },
  motionMediaUrl(id: string, kind: "video" | "thumb" | "source", version?: number): string { return `${BASE}/studio/motion/${id}/${kind}${version ? `?v=${version}` : ""}`; },
  async conversationDiscovery(conversationId: string): Promise<{ analysis: DiscoveryAnalysis | null }> {
    return j(await authFetch(`${BASE}/studio/conversations/${conversationId}/discovery`));
  },
  async discoveryView(id: string): Promise<DiscoveryAnalysis> { return j(await authFetch(`${BASE}/studio/discovery/${id}`)); },
  async discoveryResume(id: string): Promise<void> { await j(await authFetch(`${BASE}/studio/discovery/${id}/resume`, { method: "POST" })); },
  async discoveryStop(id: string): Promise<void> { await j(await authFetch(`${BASE}/studio/discovery/${id}/stop`, { method: "POST" })); },
  async discoveryMore(id: string, focus: string): Promise<void> {
    await j(await authFetch(`${BASE}/studio/discovery/${id}/more`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ focus }) }));
  },
  async editCandidate(id: string, candidateId: string, changes: Partial<Pick<DiscoveryCandidate, "title" | "hook" | "summary" | "category" | "hidden">> & { ranges?: [number, number][] }): Promise<DiscoveryCandidate> {
    return j(await authFetch(`${BASE}/studio/discovery/${id}/candidates/${candidateId}`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify(changes) }));
  },
  async startCandidate(id: string, candidateId: string): Promise<{ conversation_id: string; created: boolean }> {
    return j(await authFetch(`${BASE}/studio/discovery/${id}/candidates/${candidateId}/start`, { method: "POST" }));
  },
  discoveryThumbUrl(id: string, candidateId: string): string { return `${BASE}/studio/discovery/${id}/candidates/${candidateId}/thumb`; },
  discoveryPreviewUrl(id: string, candidateId: string, version: number): string { return `${BASE}/studio/discovery/${id}/candidates/${candidateId}/preview?v=${version}`; },
  async studioDocument(id: string): Promise<ProjectDocument> {
    return j(await authFetch(`${BASE}/studio/projects/${id}/document`));
  },
  async startStudioCleanBase(id: string): Promise<CleanBase> {
    return j(await authFetch(`${BASE}/studio/projects/${id}/clean-base`, { method: "POST" }));
  },
  async studioCleanBase(id: string): Promise<CleanBase> {
    return j(await authFetch(`${BASE}/studio/projects/${id}/clean-base`));
  },
  studioCleanBaseUrl(id: string, key: string): string { return `${BASE}/studio/projects/${id}/clean-base?key=${encodeURIComponent(key)}`; },
  async studioFont(name: string): Promise<ArrayBuffer> {
    const response = await authFetch(`${BASE}/studio/fonts/${encodeURIComponent(name)}`);
    if (!response.ok) throw new Error("font");
    return response.arrayBuffer();
  },
  studioPlanFrameUrl(id: string, frame: string): string { return `${BASE}/studio/projects/${id}/plan/frames/${frame}`; },
  async getBrandProfile(): Promise<BrandProfile> {
    return j(await authFetch(`${BASE}/studio/profile`));
  },
  async updateBrandProfile(patch: Partial<Pick<BrandProfile, "name" | "tagline" | "cta" | "accent_color" | "caption_font" | "logo_motion">>): Promise<BrandProfile> {
    return j(await authFetch(`${BASE}/studio/profile`, { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify(patch) }));
  },
  async uploadBrandLogo(file: File): Promise<BrandProfile> {
    const form = new FormData(); form.append("file", file);
    return j(await authFetch(`${BASE}/studio/profile/logo`, { method: "POST", body: form }));
  },
  brandLogoUrl(): string { return `${BASE}/studio/profile/logo`; },
  studioOutputUrl(id: string): string { return `${BASE}/studio/projects/${id}/output`; },
  async prepareMediaPlayback(): Promise<void> {
    await j(await authFetch(`${BASE}/studio/media-session`, {method:"POST", credentials:"same-origin"}));
  },
  studioAssetUrl(id: string, index: number): string { return `${BASE}/studio/projects/${id}/assets/${index}`; },
  studioAttachmentUrl(conversationId: string, attachmentId: string): string { return `${BASE}/studio/conversations/${conversationId}/attachments/${attachmentId}`; },
  studioEventAudioUrl(conversationId: string, eventSeq: number): string { return `${BASE}/studio/conversations/${conversationId}/events/${eventSeq}/audio`; },
  async streamStudioEvents(id: string, after: number, onEvent: (event: StudioEvent) => void, signal: AbortSignal): Promise<void> {
    const response = await authFetch(`${BASE}/studio/conversations/${id}/events?after=${after}`, { signal, headers: { "Last-Event-ID": String(after) } });
    if (!response.ok || !response.body) throw new Error(`${response.status} Could not connect to live events`);
    const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = "";
    while (!signal.aborted) {
      const { value, done } = await reader.read(); if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary: number;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        const block = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
        const line = block.split("\n").find(item => item.startsWith("data: "));
        if (line) { try { onEvent(JSON.parse(line.slice(6))); } catch { /* ignore malformed event */ } }
      }
    }
    // A proxy may close an otherwise healthy SSE response. Avoid a tight
    // reconnect loop that would repeatedly authenticate and query PostgreSQL.
    if (!signal.aborted) await new Promise(resolve => setTimeout(resolve, 750));
  },
  async studioEventHistory(id: string, after: number, signal: AbortSignal): Promise<StudioEvent[]> {
    return j(await authFetch(`${BASE}/studio/conversations/${id}/event-history?after=${after}`, {signal}));
  },
};
