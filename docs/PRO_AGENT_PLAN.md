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
