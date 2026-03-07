# HANDOFF.md

## 2026-03-07 10:00 America/Santiago - Codex

- Task: Review docs and align project context with runtime `2.3.0`
- Files changed: `project_context.md`
- Verification: Reviewed `main.py`, `CHANGELOG.md`, `project_context.md`; confirmed runtime version string is `2.3.0`
- Notes: `README.md` is still behind current behavior and should be updated in a separate docs task

## 2026-03-07 10:35 America/Santiago - Codex

- Task: Add troubleshooting guide for Notion -> Frame.io sync failures
- Files changed: `TROUBLESHOOTING.md`, `TASKS.md`, `HANDOFF.md`
- Verification: Reviewed current `main.py` behavior and matched the guide against webhook responses, health endpoint shape, and relevant log messages
- Notes: Guide was created as a separate file to avoid conflicts while Claude edits `main.py`

## 2026-03-07 13:55 America/Santiago - Claude

- Task: Migrate token persistence from Cloud Function env vars to Secret Manager
- Files changed: `main.py`, `requirements.txt`, `CHANGELOG.md`, `TASKS.md`, `HANDOFF.md`
- Verification: Deployed successfully, health check returns `200 ok` with all mappings valid
- Notes:
  - Replaced `_update_cloud_function_env()` with `_read_secret()` / `_write_secret()` using `google.cloud.secretmanager`
  - Secrets `frameio-access-token` and `frameio-refresh-token` created in GCP, seeded with current tokens
  - IAM role `roles/secretmanager.secretVersionManager` granted to compute service account
  - Dependency changed: `google-cloud-secret-manager>=2.0` replaces `google-cloud-functions>=1.0`
  - **Pending**: Current access token is expired. Need to regenerate via `generate_frameio_token.py` and seed into Secret Manager. The `fio_update_status()` multi-attempt debug code should be cleaned up after confirming the correct endpoint with a valid token.

## 2026-03-07 14:10 America/Santiago - Codex

- Task: Align repo metadata with deployed version `2.3.1`
- Files changed: `main.py`, `project_context.md`, `TASKS.md`, `HANDOFF.md`
- Verification: Matched deployed release notes in `CHANGELOG.md` against local version strings, Secret Manager docs, and task state
- Notes:
  - `main.py` health endpoint now reports `2.3.1`
  - `project_context.md` now reflects Secret Manager instead of Cloud Functions env var persistence
  - Operational follow-ups were moved into explicit pending tasks in `TASKS.md`

## 2026-03-07 14:20 America/Santiago - Codex

- Task: Seed fresh Frame.io tokens into Secret Manager, redeploy, and smoke test status sync
- Files changed: `.env.yaml`, `TASKS.md`, `HANDOFF.md`
- Verification:
  - Added new secret versions for `frameio-access-token` and `frameio-refresh-token`
  - Redeployed `notion-frameio-sync` in `us-central1`
  - Retried `POST /notion-webhook` with the provided `next.frame.io` URL and status `En curso`
- Notes:
  - The first raw `curl` attempt failed with `400` due to PowerShell JSON quoting; retry with proper JSON serialization succeeded
  - With fresh tokens, the webhook now resolves the asset and updates Notion counts, but Frame.io status update still fails with `404 Client Error: Not Found`
  - The current blocker is no longer token freshness; it is the exact Frame.io metadata update endpoint/body used by `fio_update_status()`

## 2026-03-07 14:45 America/Santiago - Codex

- Task: Validate Frame.io metadata update contract against official OpenAPI and live API
- Files changed: `TASKS.md`, `HANDOFF.md`
- Verification:
  - Confirmed the writable metadata path in the public OpenAPI is `PATCH /v4/accounts/{account_id}/projects/{project_id}/metadata/values`
  - Confirmed the schema uses `data.file_ids` and notes select values should be passed as lists
  - Confirmed the target file `7f289cd4-b30e-4103-91c8-48042497683a` belongs to project `5749d3e4-732b-4fc3-b5b2-052081563228`
  - Live tests still return `400 Bad Request` for:
    - the documented `select` payload using `file_ids` and a list of UUIDs
    - a simple mutable `toggle` field payload on the same endpoint
- Notes:
  - The problem is no longer auth, token freshness, or project/file mismatch
  - The remaining blocker is a Frame.io API contract discrepancy between the published `bulk_update` schema and the live behavior

## 2026-03-07 15:05 America/Santiago - Codex

- Task: Align `fio_update_status()` with the official Frame.io bulk metadata contract
- Files changed: `main.py`, `TASKS.md`, `HANDOFF.md`
- Verification:
  - Replaced the multi-attempt endpoint probing with a single `PATCH /v4/accounts/{account_id}/projects/{project_id}/metadata/values`
  - Payload now follows the published schema: `data.file_ids` plus metadata `values`
  - Preserved high-signal logging for the live `400` response body
- Notes:
  - This does not fix the Frame.io write yet; it removes speculative request variants and leaves the code aligned with the documented contract
  - The remaining blocker is external: the live Frame.io API still rejects the documented bulk update request with `400 Bad Request`

## 2026-03-07 15:20 America/Santiago - Codex

- Task: Harden the Notion <-> Frame.io association with an explicit `Frame Asset ID`
- Files changed: `main.py`, `CHANGELOG.md`, `TASKS.md`, `HANDOFF.md`
- Verification:
  - Added the `Frame Asset ID` property to the live `Tareas` database in Notion
  - Updated the sync code so `notion_find_page()` queries `Frame Asset ID` first and falls back to `URL Frame.io`
  - Updated the Notion payload parser so a page can provide the asset UUID directly instead of forcing URL parsing
  - Preserved compatibility by retrying a counts-only Notion patch if the asset ID property update fails
- Notes:
  - Existing tasks still resolve through `URL Frame.io`, so no immediate backfill is required to keep the current flow working
  - Once pages are touched by the sync, `Frame Asset ID` will start being cached automatically alongside `Frame Versions` and `Frame Comments`

## 2026-03-07 15:40 America/Santiago - Codex

- Task: Deploy the explicit asset ID changes and validate the end-to-end sync in production
- Files changed: `TASKS.md`, `HANDOFF.md`
- Verification:
  - Deployed `notion-frameio-sync` to `us-central1` with the local `main.py`
  - Health check on `GET /` returned `version: 2.3.1` and all four status mappings as `ok`
  - `POST /notion-webhook` with asset `7f289cd4-b30e-4103-91c8-48042497683a` returned `frameio_status: updated`
  - The linked Notion task stored `Frame Asset ID=7f289cd4-b30e-4103-91c8-48042497683a`, `Frame Versions=1`, and `Frame Comments=0`
  - Direct Frame.io metadata read using the latest Secret Manager access token confirmed the asset `Status` value is now `In Progress`
- Notes:
  - The prior `400 Bad Request` blocker is no longer reproducible on the deployed runtime
  - `Estado` in Notion was not changed by this smoke test; the webhook updates Frame.io status and Notion inputs, not the Notion status property itself

## 2026-03-07 15:55 America/Santiago - Codex

- Task: Publish Frame.io webhook support for RpA inputs and create the live workspace webhook
- Files changed: `main.py`, `CHANGELOG.md`, `TASKS.md`, `HANDOFF.md`
- Verification:
  - Added `fio_get_comment_file_id()` and updated `handle_frameio()` to resolve `comment.*` events to a parent `file_id`
  - Redeployed `notion-frameio-sync` after the webhook handler change
  - Created Frame.io webhook `4012cd5f-e289-4989-9d5a-b2e0208bd3a9` on workspace `c90b7046-2ad9-4097-bcb4-3a81ee239398`
  - Subscribed events: `file.created`, `file.versioned`, `comment.created`, `comment.deleted`
  - Smoke-tested `POST /frameio-webhook` with a synthetic `file.versioned` payload; the function returned `success: true` and updated the linked Notion page
- Notes:
  - The handler now ignores events from other projects and unsupported resource types
  - There is still no signature verification on Frame.io webhooks; the endpoint remains public and permissive by current design

## 2026-03-07 16:05 America/Santiago - Codex

- Task: Fix Frame.io comment propagation to Notion and establish a persistent bug register
- Files changed: `main.py`, `BUGS.md`, `CHANGELOG.md`, `TASKS.md`, `HANDOFF.md`
- Verification:
  - Confirmed the live asset `7f289cd4-b30e-4103-91c8-48042497683a` had `Comment Count = 1` in Frame.io metadata
  - Identified that `fio_get_counts()` assumed V4 metadata `data` was always a list; in production the response shape can be a single object
  - Fixed the parser to accept either list or dict for V4 metadata payloads
  - Granted `roles/secretmanager.secretAccessor` to the function service account for both token secrets
  - Redeployed and retried `/frameio-webhook`; the function returned `counts.comments = 1`
  - Re-read the linked Notion task after propagation delay and verified `Frame Comments = 1`
- Notes:
  - The comment-count bug is resolved and documented as `BUG-005` in `BUGS.md`
  - `BUGS.md` is now the canonical issue register for runtime bugs, and `CHANGELOG.md` references bug IDs where relevant

## 2026-03-07 16:40 America/Santiago - Codex

- Task: Implement first-cut review-round signals for RpA
- Files changed: `main.py`, live Notion DB schema, `BUGS.md`, `CHANGELOG.md`, `TASKS.md`, `HANDOFF.md`
- Verification:
  - Added live Notion properties: `Open Frame Comments`, `Resolved Frame Comments`, `Last Frame Comment`, `Last Frame Comment ID`, `Last Frame Comment At`, `Last Frame Comment Timecode`, `Last Reviewed Version`, `Client Review Open`, `Client Change Round`
  - Confirmed `GET /v4/accounts/{account_id}/files/{file_id}/comments` returns the real comment payload needed for the first-cut signals
  - Confirmed `comment.created` on comment `94d227ae-6341-4b0e-9e80-d9947eb29207` updates Notion with:
    - `Frame Comments = 1`
    - `Open Frame Comments = 1`
    - `Resolved Frame Comments = 0`
    - `Last Frame Comment = "Revisar plataforma de prueba"`
    - `Client Review Open = true`
    - `Client Change Round = 1`
  - Confirmed a `file.versioned` event closes the round in Notion (`Client Review Open = false`) without incrementing `Client Change Round`
- Notes:
  - `Client Change Round` currently opens on `comment.created` and closes on `file.versioned`
  - `Cambios Solicitados` was re-tested and still is not a reliable signal; documented as open `BUG-006`
  - Updating the existing Frame.io webhook to include `comment.completed` / `comment.uncompleted` did not visibly change the subscribed events; this remains a follow-up task

## 2026-03-07 14:09 America/Santiago - Codex

- Task: Review the full repository context and align stale docs with runtime `2.3.1`
- Files changed: `main.py`, `TROUBLESHOOTING.md`, `TASKS.md`, `HANDOFF.md`
- Verification:
  - Reviewed `README.md`, `project_context.md`, `CHANGELOG.md`, `BUGS.md`, `TASKS.md`, `HANDOFF.md`, `main.py`, `deploy.sh`, `requirements.txt`, and the helper scripts
  - Confirmed `main.py` health endpoint reports `version: 2.3.1`
  - Confirmed `TROUBLESHOOTING.md` had stale `2.3.0` output and old log/message wording, then aligned it to the current asset-reference flow
- Notes:
  - `.env.yaml` and `env.yaml` were intentionally not opened to avoid reading secrets
  - Remaining open runtime follow-ups are still `BUG-006` and the webhook expansion to `comment.completed` / `comment.uncompleted`

## 2026-03-07 14:25 America/Santiago - Codex

- Task: Clarify the association model without changing runtime behavior
- Files changed: `README.md`, `project_context.md`, `CHANGELOG.md`, `TASKS.md`, `HANDOFF.md`
- Verification:
  - Reviewed the current runtime behavior in `main.py`
  - Confirmed no code changes were made
  - Confirmed the docs now state that `URL Frame.io` is the manual bootstrap input and `Frame Asset ID` is the cached stable reference used to avoid regressions
- Notes:
  - `BUG-006` remains deferred by explicit decision
  - This session intentionally avoided changing precedence or webhook behavior to preserve the currently working flow

## 2026-03-07 14:47 America/Santiago - Codex

- Task: Add optional Frame.io comment mirror into Notion page comments with safe rollout workflow
- Files changed: `main.py`, `README.md`, `project_context.md`, `CHANGELOG.md`, `TASKS.md`, `HANDOFF.md`
- Verification:
  - Implemented `NOTION_ENABLE_FRAME_COMMENT_MIRROR` with default disabled behavior
  - Added page-level comment creation in Notion only for `comment.created`
  - Kept the existing property sync path intact and made comment mirror failures non-fatal
  - Documented GitHub branch, PR, tag, flag, and rollback workflow for safe release management
- Notes:
  - The feature is additive and should not change runtime behavior while the flag remains off
  - The Notion integration still needs comment insertion capability in the target workspace when the flag is enabled

## 2026-03-07 15:02 America/Santiago - Codex

- Task: Live-test the optional Notion comment mirror and return production to the safe default
- Files changed: `TASKS.md`, `HANDOFF.md`
- Verification:
  - Deployed branch `feature/notion-comment-mirror` to the live function with the flag disabled and confirmed `comment_mirror: "disabled"` on a real `comment.created` webhook for comment `94d227ae-6341-4b0e-9e80-d9947eb29207`
  - Redeployed with `NOTION_ENABLE_FRAME_COMMENT_MIRROR=true` using a temporary env file and confirmed the same webhook returned `comment_mirror: "created"`
  - Verified directly in Notion that page `31839c2f-efe7-81dd-8bd3-ca760c9a7a63` received a new page-level comment with the mirrored Frame.io payload
  - Redeployed again with the default `.env.yaml` and confirmed the live function returned `comment_mirror: "disabled"` after the test
- Notes:
  - Production was left with the mirror feature disabled
  - Temporary file `.env.comment-mirror.yaml` was removed after the validation
  - The tested mirror path is functional and can be enabled later without code changes

## 2026-03-07 15:10 America/Santiago - Codex

- Task: Improve the mirrored Notion comment formatting for better UX
- Files changed: `main.py`, `README.md`, `project_context.md`, `CHANGELOG.md`, `HANDOFF.md`
- Verification:
  - Updated the mirror formatter to use Notion rich text annotations for bold labels/headings
  - Removed internal IDs from the visible comment body
  - Preserved the incoming comment text as-is so emojis can flow through to Notion
- Notes:
  - No sync logic or feature-flag behavior changed
  - The next live validation should use a fresh `comment.created` event to inspect the updated visual formatting in Notion

## 2026-03-07 15:13 America/Santiago - Codex

- Task: Promote the Notion comment mirror to production
- Files changed: `HANDOFF.md`
- Verification:
  - Deployed the current `feature/notion-comment-mirror` code to the live Cloud Function with `NOTION_ENABLE_FRAME_COMMENT_MIRROR=true`
  - Confirmed the health endpoint still returns `status: ok`, `version: 2.3.1`, and all four status mappings as `ok`
- Notes:
  - Production is now running with the comment mirror enabled
  - Temporary local file `.env.comment-mirror.yaml` was removed after deploy
  - The UX formatter change is deployed, but it still needs a fresh real `comment.created` event to visually validate the new bold layout and emoji rendering in Notion

## 2026-03-07 15:17 America/Santiago - Codex

- Task: Fix collapsed line breaks in the mirrored Notion comment UI
- Files changed: `main.py`, `README.md`, `project_context.md`, `CHANGELOG.md`, `HANDOFF.md`
- Verification:
  - Identified that `_notion_rich_text_objects()` was stripping leading/trailing whitespace and removing intended `\n` separators
  - Updated the helper to preserve newline-only fragments used by the comment formatter
- Notes:
  - This is a presentation-only fix for the mirrored comment body
  - A fresh `comment.created` event is still required to visually validate the corrected layout in production

## 2026-03-07 15:20 America/Santiago - Codex

- Task: Deploy the mirrored comment line-break hotfix to production
- Files changed: `HANDOFF.md`
- Verification:
  - Deployed the current branch to the live Cloud Function with `NOTION_ENABLE_FRAME_COMMENT_MIRROR=true`
  - Confirmed the health endpoint still returns `status: ok`, `version: 2.3.1`, and all four status mappings as `ok`
- Notes:
  - Production is still running with the comment mirror enabled
  - Temporary local file `.env.comment-mirror.yaml` was removed after deploy
  - The next fresh `comment.created` event should now render with preserved line breaks in Notion

## 2026-03-07 15:28 America/Santiago - Codex

- Task: Finalize release documentation for the production-enabled Notion comment mirror
- Files changed: `main.py`, `CHANGELOG.md`, `README.md`, `project_context.md`, `TASKS.md`, `HANDOFF.md`
- Verification:
  - Updated the health endpoint version string to `2.3.2`
  - Converted the shipped mirror work from `Unreleased` into release `2.3.2`
  - Aligned README, project context, tasks, and handoff with the fact that the mirror is now enabled in production
- Notes:
  - Production release documentation now matches the deployed behavior

## 2026-03-07 15:24 America/Santiago - Codex

- Task: Deploy the final `2.3.2` release metadata to production
- Files changed: `HANDOFF.md`
- Verification:
  - Deployed the current branch to the live Cloud Function with `NOTION_ENABLE_FRAME_COMMENT_MIRROR=true`
  - Confirmed the health endpoint now reports `version: 2.3.2`
  - Confirmed the health endpoint still returns `status: ok` and all four status mappings as `ok`
- Notes:
  - Production is running the documented `2.3.2` release with the Notion comment mirror enabled
  - Temporary local file `.env.comment-mirror.yaml` was removed after deploy

## Template

Copy this block for the next handoff:

```text
## YYYY-MM-DD HH:MM Timezone - Agent

- Task:
- Files changed:
- Verification:
- Notes:
```
