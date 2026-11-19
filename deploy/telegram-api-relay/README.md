# Shared Telegram/API relay

Recovered verbatim source from production deployment
`dpl_946V71VyXSf2SVPdrmmKiUEVKnSC` on 2026-10-23 before modifying ElevenLabs.
Project: `rafiei-telegram-api-relay`, team `rezas-projects-00aa9a21`.

Only `api/elevenlabs.js` is changed: authenticated GET voice/model discovery,
allow-listed voice search/pagination query forwarding, private/no-store GET
responses. Existing speech, transcription, Gemini, video analysis, upload and
generic proxy behavior is retained. No environment secrets are in these files.

Run offline regression tests with `node --test elevenlabs.test.mjs`. Tests mock
the upstream fetch; they never generate audio or contact a provider.

Stage production without aliases, verify authenticated discovery and negative
authentication tests, then promote that tested deployment. Keep the preceding
deployment available for rollback. Do not delete or change other project routes.

## Published fix (2026-10-23)

- Deployment: `dpl_D96WTMj6EtaTPr3si7E5EtavEzJq`, production READY.
- Main domain: `https://rafiei-telegram-api-relay.vercel.app`.
- Verified live: authenticated v1 voices, v2 voices (including Persian filter),
  and models all HTTP 200; no key HTTP 401.
- 27 account voices, zero `language=fa` matches, 11 models. Persian-supporting
  model IDs: `eleven_v4`, `eleven_v4_turbo`, `eleven_v3`, `eleven_v3_conversational`.
- Five offline regression tests pass; no synthesis or transcription was submitted.
- This is a CLI source patch, not a newly committed Git release. All files except
  `api/elevenlabs.js` match the preceding deployment's source hashes exactly.

## Voice cloning route (2026-11-10)

`api/elevenlabs-clone.js` is a separate function: one authenticated multipart POST (<= 4 MB) forwarded to ElevenLabs `v1/voices/add`. The shared
`api/elevenlabs.js` allow-list is unchanged, so editing or deleting voices stays unreachable. The production project had moved on since the first
recovery (it now also has `api/telegram-download.js`, `lib/file-location.js`, a lock file and dependencies), so the new deployment keeps every existing file
by its content hash and adds only the new function plus one `functions` entry in `vercel.json`.

- Deployment: `dpl_B6BefEpCbpLtspM73e8Ku4JyDsLR` (production). Rollback target: `dpl_5Tt2e7uMQ2Lqh7hWZRmnSFgPBqMX` (the production deployment before it).
- Verified on the public domain: every route returns 401 without the key; the authenticated speech/voice route still returns 200.
- Offline tests: `node --test elevenlabs.test.mjs elevenlabs-clone.test.mjs`.

## EditorGPT Pro Anthropic Messages

`POST /api/anthropic` forwards the original Messages body to the fixed
Anthropic Messages endpoint and streams the status and body back. EditorGPT
keeps the Anthropic key in Direct Providers and sends it in the server
request. Access to the relay uses its existing `RELAY_SECRET`, which matches
`GEMINI_RELAY_SECRET` on EditorGPT. Anthropic routing is limited to Pro.
The shared relay accepts request bodies up to 4 MiB.

Stage the route using the full source of the current production deployment.
Preserve existing functions and settings. Run `node --test anthropic.test.mjs`
to verify authorization, streaming, and upstream errors with a mock provider.
