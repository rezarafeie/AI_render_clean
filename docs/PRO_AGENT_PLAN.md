# EditorGPT Pro — phase 0 findings (2026-11-17)

Spec: `~/Desktop/motionclaude/pro_agent/EDITORGPT_PRO_AGENT.md`. This file records what phase 0 measured and the decisions phase 1 depends on.

## 1. Does the model path carry what the Agent SDK sends? — yes

- **Jarvis serves the native Anthropic Messages API** at `https://api.jarvis.you/v1/messages` (auth `x-api-key`, `anthropic-version: 2023-06-01`).
  Streaming SSE with `tool_use` works (model `claude-opus-5-5`, Bedrock-backed: tool ids `toolu_bdrk_…`), non-streaming too.
- **The exact request Claude Code sends** was captured with a logging fake server and replayed against Jarvis: `POST /v1/messages?beta=true`, `stream: true`,
  `max_tokens: 128000`, `thinking: {type: adaptive, display: updates}`, `context_management`, `output_config`, 12 tools, 2 `cache_control` marks and the beta
  header `claude-code-20250219, interleaved-thinking-2025-05-14, context-management-2025-06-27, per-turn-control-2026-07-01, mid-conversation-tool-changes-2026-07-01,
  thinking-token-count-2026-05-13, advanced-tool-use-2025-11-20, effort-2025-11-24, thinking-display-updates-2026-08-18`. Jarvis accepted it unchanged and answered with
  a `tool_use` block (8.6K input tokens, 26.6 s on a loaded afternoon).
- **The CLI calls only one route**: `/v1/messages?beta=true` (with `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`, no telemetry, no count_tokens, no model list).
  The proxy (`/internal/anthropic/v1/messages`) therefore needs exactly one endpoint, streamed through without buffering.
- SDK: `claude-agent-sdk` 0.2.183 (Python); it bundles the `claude` CLI binary (~400 MB venv). Pin this version.

## 2. Gateway path

Production runs in **direct mode** (`brain/lm_direct.py`, providers `jarvis` …), not through the LM API gateway. `brain/lm_gateway.py` already knows a `messages`
endpoint (adds `anthropic-version`) but the direct client only speaks OpenAI chat. Phase 1 therefore adds to the proxy: run-token check → model allow-list of a
new `pro_agent` route → forward the raw Anthropic body to the jarvis provider's `/messages` (key added server-side, never in the agent container) → stream
back → sum `message_start.usage` + `message_delta.usage` (input, output, cache read/write) → `_audit` + `credits.charge` → 402 when the run budget or the
person's credit is spent. `tests/test_no_router_bypass.py` stays green: the only Anthropic-shaped URL is the internal proxy.

## 3. Findings that change the plan

1. **Hidden thinking counts against `max_tokens` on Jarvis.** Our own code calls (16K/48K) once spent the whole budget thinking and returned no text. The CLI
   asks 128K with adaptive thinking, which avoids it, but the proxy must not lower `max_tokens`.
2. **This VPS is the wrong place for agent containers.** 4 vCPU with ~45 % steal time (OpenStack/KVM host), load 10–14, two Supabase stacks and other
   projects on the same machine. Each Pro run is a Node CLI + Remotion/Chromium + ffmpeg. Options: (a) a dedicated-CPU server for `agent-worker`, (b) run
   agent containers on RunPod CPU pods (the render cloud already provisions pods, has a relay and R2 storage), (c) start here with concurrency 1 and a
   hard CPU cap. Decision needed before phase 1.
3. **Opuscar texts**: the owner confirmed the licence is fine (2026-11-17); the 99 Lemo styles are already vendored (`vendor/motion-skills/lemo`) and can be
   a skill.
4. Prompt caching: Jarvis caches automatically for chat; the CLI sends `cache_control` marks and Jarvis accepted them. Cache hit rates must be measured in
   phase 5 (they decide the cost of 100-turn runs).

## 4. Phase 1 file map

| file | what |
|---|---|
| `app/routers/agent_proxy.py` | `POST /internal/anthropic/v1/messages`: HMAC run token, model allow-list, stream to jarvis `/messages`, usage → credits, 402 |
| `app/agents/pro/{runner,policy,prompt,tools}.py` | SDK client, PreToolUse/PostToolUse hooks, system prompt, in-process MCP `editorgpt` (say, step, assets_list, assets_fetch, show_stills, deliver) |
| `app/agents/{store,dispatcher}.py`, `app/routers/studio.py` | `agent_mode="pro"`; no fallback between modes |
| `Dockerfile.agent`, compose service `agent-worker` (queue `agent`) | SDK + CLI pinned, node + Remotion kit, ffmpeg, no keys, internal network only |
| `app/agents/pro/skills/{video-director,remotion-kit}` | first two skills |
| `brain/lm_gateway.py` `ROUTES["pro_agent"]` | allowed models `claude-opus-*`, `claude-sonnet-*`, `claude-haiku-*` |

## 5. Open questions for the owner

1. Where do agent containers run (section 3.2)?
2. Default per-run budget (spec suggests $8) and who may use Pro at first (admin only?).

---

# Phases 1–5: status (2026-11-18)

| phase | status | evidence |
|---|---|---|
| 0 — findings | done | sections 1–5 above |
| 1 — core | done | proxy `/internal/anthropic/v1/messages` (run token, model allow-list, stream, usage → `_audit` → credits, 402 on budget); runner + daemon in `ai-render-agent-worker-1` (internal `pro_net`, no keys); first film delivered from chat |
| 2 — tools | done | 25 tools: say, step, assets_list/fetch, show_stills, deliver, render_cloud/status, tts, music_generate/library, sfx, image_generate, stt, web_read, fonts, brand_profile, person_matte, qc_report, ask_user, request_approval; PreToolUse policy; stop (`interrupt`) and resume (same session per chat) |
| 3 — skills | done | video-director, remotion-kit, talking-premium-edit, talking-reel-edit, ad-reel, motion-explainer, vox-documentary, intro-engines, whiteboard-explainer, film-styles (SKILL.md + reference + kit) |
| 4 — UI | done | Lite / Medium / Pro switcher (composer + settings), live reply streaming, live thinking rows, one row per tool with request/response, image thumbnails (click to enlarge), Pro cost line, admin page `settings/pro-runs` with the CLI transcript |
| 5 — measure | done (first pass) | table below; `tests/test_pro_agent.py` (token, folder, policy, image lift, follow-up) passes in the app and agent containers |

## Measured runs (Opus 5.5 through Jarvis; 1M credits ≈ $4 provider cost)

Credits are the studio's weighted tokens (1 = one fresh Opus input token, output ×5, cache read ×0.1), the same ledger as every other engine.

| job | output | credits | ≈ $ | model calls | active time | notes |
|---|---|---|---|---|---|---|
| 10 s title film from a photo (phase 1) | 1080×1920, 10 s | 0.26 M | 1.0 | 23 | 13 min | |
| talking reel from a discovered clip (39 s source) | 1080×1920, 36 s, −14.4 LUFS, cloud render | 1.36 M | 5.5 | 42 | 33 min | three runs: base edit; mix + render; mux + QC + deliver (one more run lost to the resume bug, now fixed) |
| motion explainer «نخِ ناتمام» (Zeigarnik effect) | 1080×1920, 46 s, narration, music, sfx, generated images | 2.46 M | 9.9 | 31 | 78 min | the big run spent 2.0 M; provider errors forced two continues |
| 4:5 talking post (25 s source) | TALK2_RESULT | | | | | |

### Where the money goes

- **Fresh input dominates.** In the explainer run 1.69 M of the 2.05 M credits were *uncached* input. Each call resends the whole conversation
  (40–150 K tokens late in a run); only ~12 K (the system prompt and tools) was read from cache in most calls.
- **Jarvis caching is erratic.** A direct test (same 35 K-token prefix sent three times with `cache_control`) read 0, then 4 K, then all 35 K from
  cache: hits depend on which backend serves the call. With steady hits a run would cost roughly a third. **Ask Jarvis for session affinity /
  sticky routing for one `x-session-id`** — the largest single saving available.
- Output is small (2–60 K per run); images (contact sheets, stills) are the next driver, hence the one-contact-sheet rule in video-director.

### Proposed credit rule

- Pro is charged with the same weights as every engine (nothing extra to build). A job costs **0.3–3 M credits**; the per-run cap stays 3 M
  (`PRO_BUDGET_CREDITS`), and a run stops cleanly with a Persian message at the cap.
- **Start gate:** require a balance of at least 1.5 M credits to start a Pro run (the median job), so a run does not die half-way on 402.
- **Selling price:** 1 M credits costs ≈ $4 at Jarvis prices; a package price of ≥ $8 per million keeps a 2× margin for retries and cloud render.
  Show the person the typical range in the switcher hint («معمولاً ۰٫۵ تا ۳ میلیون اعتبار»).

## Traps found while building (all handled in code)

1. Jarvis drops images that sit inside a `tool_result` → the proxy lifts them after the result (`_lift_tool_images`). Without it the agent re-read one still 13 times.
2. Jarvis sometimes answers an SSE `error` ("could not authenticate") before the first token → the proxy resends (4 tries); the runner continues
   the same session after a mid-run provider error (3 times), and never posts the error as the agent's message.
3. The agent may end its turn while a cloud render runs → the runner waits for the render and continues the session; the prompt forbids it too.
4. A resumed session can first emit a 0-turn result for a leftover background-task notice → the runner reads on to its own turn's result; Bash
   `run_in_background` is forbidden (background jobs die with the turn); Bash timeouts 10 / 30 min.
5. Text without any Persian never reaches the chat (it becomes an internal note step in the timeline); the language rule is the prompt's first rule.
6. The person's upload quota must not block agent outputs → agent files are attached without the quota; admins have unlimited storage.
7. ElevenLabs Scribe JSON has `sentences`/`words`, no `text` → the stt tool returns timed sentences.

## Operations

- Agent code: `/opt/ai-render/deploy/pro-agent/code/pro` (bind mount). Swap the folder (strip macOS `._*` files); the daemon reloads runner and
  prompt before every run, so **no restart** (a restart kills an active run). Proxy/tool code is in the app image (thin-layer deploy).
- Secret: `PRO_WORKER_SECRET` only in `/opt/ai-render/deploy/pro-agent/pro.yml` (600). Logs: `docker logs ai-render-agent-worker-1`;
  transcripts: `/runs/<chat>/.claude-config/projects/*/*.jsonl` (also on the admin page).
- Runs one at a time (one daemon). On this VPS (4 vCPU, ~45 % steal) more than one parallel run is not advised; a second worker belongs on a
  dedicated-CPU host or a RunPod CPU pod (open decision).
