import type { ActivityStep } from "./model";

/** The motion graphic's live log as the same activity steps every other chat shows, so its narration looks and behaves like theirs
 * (a shimmering current step with a live timer and a collapsed history). */
export function motionSteps(motion: { log?: { key: string; text: string; state: string; at: number; done_at?: number; detail?: string }[]; active: boolean; status: string; progress: number; message: string }, nowMs: number): ActivityStep[] {
  const lines = motion.log || [];
  const failed = motion.status === "failed";
  const steps: ActivityStep[] = lines.map((line, index) => {
    const started = Math.round(line.at * 1000);
    const next = lines[index + 1];
    const live = line.state === "active" && motion.active;
    return {
      key: line.key, label: line.text, startedAt: started, detail: line.detail,
      endedAt: live ? nowMs : Math.max(started, line.done_at ? Math.round(line.done_at * 1000) : next ? Math.round(next.at * 1000) : nowMs),
      status: live ? "active" : line.state === "active" ? (failed ? "failed" : "done") : "done",
      stage: line.key, events: [], notes: [], progress: live && motion.progress > 0 ? motion.progress : undefined,
    };
  });
  if (!steps.length) steps.push({ key: "start", label: motion.message || "در حال شروع…", startedAt: nowMs, endedAt: nowMs, status: motion.active ? "active" : "done", events: [], notes: [] });
  return steps;
}

/** "About 40 seconds left" / "about 2 minutes left", from the server's measured estimate (counted down between updates). */
export function etaText(deadline: number | null, now: number): string {
  if (deadline === null) return "";
  const left = Math.max(0, Math.round(deadline - now));
  const fa = (n: number) => new Intl.NumberFormat("fa-IR").format(n);
  if (left < 8) return "چند ثانیهٔ دیگر";
  if (left < 75) return `حدود ${fa(Math.round(left / 5) * 5)} ثانیه مانده`;
  return `حدود ${fa(Math.round(left / 60))} دقیقه مانده`;
}
