# Cloud Media Storage — repository audit (Phase 1)

Branch: `feat/cloud-storage`, from `main` @ f9214dd. Everything below was read from the code; items marked **UNVERIFIED** were not.

## What exists and is reusable

| Area | Where | Notes |
|---|---|---|
| Composio boundary | `hermes/services/composio_sessions.py`, `composio_read.py`, `hermes/composio_contracts.py`, `hermes/routers/connected_apps.py` | One Composio **session per user** (`identity(user_id)` = sha256 of instance id + user id). Encrypted per-user state in Hermes settings. SDK `composio==0.30.0` (`requirements-composio.txt`). |
| Connect / disconnect | `composio_sessions.connect()` / `connections()` | OAuth redirect via `sessions.use(ref).authorize(toolkit, callback_url)`. No disconnect endpoint. Toolkit allow-list `COMPOSIO_TOOLKITS` (default `instagram`). |
| Tool discovery | `composio_sessions.discover()` | Returns schemas as untrusted reference data, `executable: False`. |
| Tool execution | `composio_read.execute()` | **Read-only by design**: slug must be in `COMPOSIO_READ_TOOLS`, must carry `readOnlyHint` and no create/update/destructive hint; result capped at 40k chars and secret keys redacted. SDK built with `file_upload_dirs=False`, `dangerously_allow_auto_upload_download_files=False`. |
| Medium agent bridge | `app/agents/medium/tools.py` (imports `DiscoverInput`, `ReadInput`, calls `discover` / `read`) | Hermes/Composio is already reachable from the Studio agent in-process. |
| Frontend for connected apps | `web/src/pages/hermes/ConnectedAppsPanel.tsx`, `HermesSettings.tsx`, `web/src/services/hermesApi.js` | Existing connect UI to extend. |
| Uploads in Studio | `app/routers/studio.py::upload_attachment` (+ `StudioAttachment`, `repo.create_attachment`) | Streams to a temp file, enforces `MAX_BYTES[kind]`, probes/decodes before any engine sees it, then moves to `ROOT/<user>/<conversation>/attachments/<id>`. This is the validation and storage path imports must go through. |
| Jobs / progress | Celery (`app/tasks.py`, `celery_app.py` with a beat schedule), `StudioEvent` + SSE, `studio_flags` busy heartbeats, `work.state` events | Reuse for transfer jobs and progress; no new scheduler or WebSocket. |
| Migrations | `alembic/versions/*` | Needed only for a transfer-job table and a linked-asset table. |
| Rendering | FFmpeg / Remotion / HyperFrames take local file paths from attachments or job dirs | Already independent of any provider, as required. |

## Findings that change the brief

1. **There is no unified Media Library.** `web/src/Library.tsx` is a B-roll / music / SFX asset library. Uploads for projects are per-conversation `StudioAttachment` rows. "Extend the Media Library" therefore means: add a cloud source to the attachment flow (and to `Library.tsx` for reusable assets). The single normalised reference the orchestrator will receive is a `StudioAttachment` id.
2. **The Composio layer cannot move files today, and that is deliberate.** Download, upload and any create/update tool are blocked by the read-only policy, and file auto-upload/download is switched off in the SDK. Browse/search/metadata are reachable by allow-listing read tools. Import (download) and export (upload) need a new, separately approved execution path. This is a security-policy decision, not just a coding task.
3. **Binary transfer through Composio is UNVERIFIED.** Composio file actions normally return a temporary URL or a file descriptor; whether it streams, is resumable, or enforces size limits for Drive/Dropbox/OneDrive has not been checked. No Composio key exists on this machine, so tool slugs and input/output contracts for `GOOGLEDRIVE_*`, `DROPBOX_*`, `ONE_DRIVE_*` cannot be confirmed here.
4. **No disconnect and no multi-account support** in the current session model (one session per user; `manage_connections=False`). Multiple accounts per provider and disconnect need Composio connected-account APIs, to be verified against SDK 0.30.0.
5. Temporary download URLs from a provider must be fetched by a server-side client with an SSRF guard (https only, host allow-list per provider, no redirects to private ranges) — nothing like this exists yet.

## Proposed implementation map

- `app/cloud_storage/` — `service.py` (user → account resolution, capability discovery), `providers/{base,gdrive,dropbox,onedrive}.py` (adapters over Composio execution), `transfer.py` (streaming, bounded memory, backoff, cancel), `ssrf.py`.
- Tables: `cloud_transfers` (durable job: state, bytes, error, provider ref, idempotency key) and `cloud_assets` (provider, account ref, provider file id, revision, checksum, internal attachment id, state `linked|imported`). Alembic migration.
- Celery tasks `airender.cloud_import` / `airender.cloud_export`; progress as `StudioEvent`s reusing existing SSE.
- Routes under `/studio/cloud/*` (accounts, list, search, metadata, import, export, transfers, cancel, folders) using the existing `_user(request)` identity.
- Imported files enter `upload_attachment`'s validate/probe/store code path (factored into a shared function) so rendering needs no change; render start checks transfer state.
- Frontend: one `CloudPicker` component in the Studio composer (next to device upload), later in `Library.tsx` and the render-result panel; connect flow reuses the Hermes connected-apps API.
- Hermes/Medium tools: `cloud_search`, `cloud_import`, `cloud_export` calling the service, never raw Composio.

## What I need to continue (exact requirements)

- A Composio API key plus instance id on the machine I develop on (or approval to read the existing ones from the server), a Google Drive toolkit with an auth config, and a test Drive account — otherwise adapters cannot be verified against real contracts.
- A decision on enabling mutation execution (upload/export) and file download through Composio.

## Verified against the live Composio account (read-only SDK inspection, no user data touched)

Server config (names only): Composio SDK 0.30.0 in `app` and `hermes`; `COMPOSIO_TOOLKITS=instagram`, `COMPOSIO_READ_TOOLS` = five Instagram slugs, all calls go through the Vercel relay (`deploy/composio-relay`, 60 s per request, body fully buffered). So today **no storage toolkit is enabled and no storage tool is allow-listed.**

Tool counts: googledrive 105, dropbox 178, one_drive 98.

Google Drive (exact slugs, hints from Composio):
- Browse/search: `GOOGLEDRIVE_FIND_FILE` (readOnly; `q`, `folder_id`, `pageSize`, `pageToken`, `orderBy`, `driveId`, `corpora` — covers shared drives), `GOOGLEDRIVE_FIND_FOLDER`, `GOOGLEDRIVE_LIST_SHARED_DRIVES`. `GOOGLEDRIVE_LIST_FILES` is **deprecated** — do not use.
- Metadata: `GOOGLEDRIVE_GET_FILE_METADATA` (`fileId`, `fields`, `supportsAllDrives`).
- Change detection: `GOOGLEDRIVE_GET_CHANGES_START_PAGE_TOKEN`, `GOOGLEDRIVE_LIST_CHANGES` (cursor-based, `includeRemoved`). `WATCH_CHANGES` needs a public webhook address — polling is the plan.
- Download: `GOOGLEDRIVE_DOWNLOAD_FILE` (readOnly) returns `downloaded_file_content = {name, mimetype, s3url}` — a **temporary Composio S3 URL**, not bytes. Native blobs come back unconverted; `mime_type` is only for Google-native docs (`EXPORT_GOOGLE_WORKSPACE_FILE` is separate). Size cap: UNVERIFIED.
- Upload: `GOOGLEDRIVE_UPLOAD_FILE` is **max 5 MB** and takes `file_to_upload = {name, mimetype, s3key}` where `s3key` must already exist in Composio's S3. `GOOGLEDRIVE_RESUMABLE_UPLOAD` (for >5 MB; `chunkSize`, `folder_to_upload_to`) also takes `file_to_upload` and returns `sessionUri` + `file`; whether it uploads the chunks itself or only opens the session is UNVERIFIED.
- `GOOGLEDRIVE_CREATE_FOLDER` (`name`, `parent_id`). Create/upload tools carry `createHint`, so the current read-only gate rejects them by design.
- Not usable for video: `UPLOAD_FROM_URL` (would require making our files public).

Dropbox (slugs seen): `DROPBOX_FILES_SEARCH`, `DROPBOX_GET_METADATA`, `DROPBOX_GET_TEMPORARY_LINK`, `DROPBOX_CREATE_FOLDER`, upload-session family (`APPEND_UPLOAD_SESSION`, `FINISH_UPLOAD_SESSION`, `GET_TEMPORARY_UPLOAD_LINK`). Folder listing / cursor tools were cut off in my listing — to verify.
OneDrive (slugs seen): `ONE_DRIVE_ONEDRIVE_LIST_ITEMS`, `ONE_DRIVE_LIST_FOLDER_CHILDREN`, `ONE_DRIVE_LIST_DRIVES`, `ONE_DRIVE_DOWNLOAD_FILE`, `ONE_DRIVE_CREATE_UPLOAD_SESSION`, `ONE_DRIVE_ONEDRIVE_UPLOAD_FILE`, `ONE_DRIVE_ONEDRIVE_CREATE_FOLDER`, thumbnails tools; delta tools exist only for SharePoint lists/sites (OneDrive item delta: to verify).

## Consequences for the design

- **Import is feasible through Composio**: `DOWNLOAD_FILE` → `s3url` → server-side streaming fetch into the existing attachment pipeline. The fetch must be limited to the Composio S3 host(s), https only, no redirects, streamed to disk (never through the relay, never through the LLM). Maximum size Composio will stage is unknown.
- **Export of large videos through Composio is the weak point.** It needs the file staged in Composio's S3 first (`file_to_upload.s3key`), which the SDK is currently configured to refuse (`file_upload_dirs=False`, auto upload/download off), and `UPLOAD_FILE` caps at 5 MB. Options: (a) enable Composio staging for one narrow path and use `RESUMABLE_UPLOAD`, after verifying it really sends chunks; (b) use the resumable `sessionUri` for chunk PUTs from our server (the session URL is pre-authorised, so no OAuth token is handled by us); (c) a provider-native adapter with a token — rejected unless nothing else works. Needs a real test upload with the test account to decide.
- The mutation gate in `composio_read.py` stays untouched. A separate allow-list (`COMPOSIO_STORAGE_TOOLS`) with explicit user approval per export will be added next to it, not inside it.
