import type { IconName } from "../components/Icon";
import type { StudioEvent } from "../api";

/**
 * How a step is presented: its Persian wording (no English stage names leak into a Persian chat), its icon and its technical log.
 * Nothing here changes what the server sent; the raw text stays in the step's log.
 */
import { presentable } from "./model";
export { GENERIC_STEP, presentable, stageText, STAGE_FA } from "./model";

export function toolIcon(tool: unknown, stage: unknown, type?: string): IconName {
  const name = `${tool || ""} ${stage || ""}`.toLowerCase().replace(/_/g, " ");
  if (type === "tool.failed") return "alert";
  if (/cancel|stop/.test(name)) return "stop";
  if (/cloud (downloading|uploading)/.test(name)) return "download";
  if (/cloud|render/.test(name)) return "film";
  if (/queued|pending|waiting|background|medium job/.test(name)) return "clock";
  if (/retry|repair|improv|enhanc/.test(name)) return "refresh";
  if (/instagram/.test(name)) return "instagram";
  if (/url|page|link|connected app/.test(name)) return "globe";
  if (/search|discover|resource/.test(name)) return "search";
  if (/review|critic|qc|visual|quality|check status|checking|validat/.test(name)) return "eye";
  if (/storyboard|concept|beats/.test(name)) return "storyboard";
  if (/motion|scene/.test(name)) return "motion";
  if (/creative|direction|directing|brief/.test(name)) return "wand";
  if (/plan|understanding|style/.test(name)) return "list";
  if (/voice|narration|audio|speech|sound/.test(name)) return "mic2";
  if (/music/.test(name)) return "music";
  if (/caption|transcri|translat|localize|subtitle|text/.test(name)) return "captions";
  if (/image|asset|picture|face/.test(name)) return "image";
  if (/script|writing|edit text|modify|editing/.test(name)) return "edit";
  if (/video|talking|analy|tracking|inspect project|inspect media|source/.test(name)) return "video";
  return "thinking";
}

const EVENT_FA: Record<string, string> = {
  "tool.started": "شروع", "tool.progress": "پیشرفت", "tool.completed": "پایان", "tool.failed": "خطا", "agent.thinking_summary": "بررسی درخواست",
  "storyboard.ready": "استوری‌بورد آماده شد", "source.inspected": "منبع خوانده شد", "render.started": "شروع رندر", "render.completed": "پایان رندر",
  "agent.narration": "توضیح", "question.required": "پرسش از شما",
};

export interface LogLine { at: number; kind: string; text: string; raw: string }

/** The technical log of a step: one line per event the server recorded for it, with the raw payload for anyone who wants it. */
export function stepLog(events: StudioEvent[], parse: (value: string | undefined | null) => number): LogLine[] {
  return events.map(event => {
    const data = { ...(event.data || {}) } as Record<string, unknown>;
    const message = String(data.message || "").trim();
    const raw = JSON.stringify(data, (_key, value) => typeof value === "string" && value.length > 700 ? `${value.slice(0, 700)}…` : value, 2) || "";
    const label = [EVENT_FA[event.type] || event.type, data.tool ? String(data.tool) : "", data.stage ? String(data.stage) : ""].filter(Boolean).join(" · ");
    return { at: parse(event.created_at), kind: label, text: presentable(message) || message, raw: raw.length > 4000 ? `${raw.slice(0, 4000)}…` : raw };
  });
}
