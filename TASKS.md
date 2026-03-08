# TASKS.md

## Active Tasks

Use one line per task and keep it current.

| Status | Owner | Task | Files | Notes |
|--------|-------|------|-------|-------|
| done | Codex | Align `project_context.md` with `2.3.0` | `project_context.md` | Version and webhook notes updated |
| done | Claude | Migrate token persistence from Cloud Function env vars to Secret Manager | `main.py`, `requirements.txt` | Deployed 2026-03-07, secrets created, IAM configured |
| done | Codex | Add troubleshooting guide for Notion -> Frame.io sync failures | `TROUBLESHOOTING.md`, `TASKS.md`, `HANDOFF.md` | Added standalone checklist without touching `main.py` |
| done | Codex | Align repo metadata with deployed version `2.3.1` | `main.py`, `project_context.md`, `TASKS.md`, `HANDOFF.md` | Health endpoint and project context now match changelog |
| done | Codex | Regenerate fresh Frame.io access token and seed Secret Manager | `.env.yaml`, GCP Secret Manager, deploy | Secrets updated, function redeployed, test payload executed |
| done | Codex | Align `fio_update_status()` with the official Frame.io bulk metadata contract | `main.py`, `TASKS.md`, `HANDOFF.md` | Replaced multi-attempt probing with the documented `PATCH .../projects/{project_id}/metadata/values` using `data.file_ids` |
| done | Codex | Harden Notion <-> Frame.io association with explicit `Frame Asset ID` | `main.py`, Notion DB schema, `CHANGELOG.md`, `TASKS.md`, `HANDOFF.md` | Added `Frame Asset ID` property to Notion, lookup now prefers explicit asset UUID and falls back to `URL Frame.io` |
| done | Codex | Verify documented Frame.io metadata bulk update works in production | `main.py`, deploy, `TASKS.md`, `HANDOFF.md` | Deployed latest code, `/notion-webhook` returned `frameio_status: updated`, and direct metadata read confirmed `Status=In Progress` on asset `7f289cd4-b30e-4103-91c8-48042497683a` |
| done | Codex | Create the Frame.io workspace webhook and publish comment event support | `main.py`, Frame.io webhook config, `CHANGELOG.md`, `TASKS.md`, `HANDOFF.md` | Added comment resource resolution in `/frameio-webhook`, deployed, created workspace webhook `4012cd5f-e289-4989-9d5a-b2e0208bd3a9`, and smoke-tested with `file.versioned` |
| done | Codex | Fix Frame.io comment count propagation to Notion and add a bug register | `main.py`, GCP IAM, `BUGS.md`, `CHANGELOG.md`, `TASKS.md`, `HANDOFF.md` | Fixed V4 metadata parsing for `Comment Count`, granted Secret Manager read access, validated `Frame Comments=1` in Notion, and created `BUGS.md` with stable bug IDs |
| done | Codex | Enrich Notion with Frame.io comment signals and first-cut Client Change Round logic | `main.py`, Notion DB schema, `BUGS.md`, `CHANGELOG.md`, `TASKS.md`, `HANDOFF.md` | Added review-round properties in Notion, synced comment signals, validated `Client Change Round = 1` on `comment.created`, and validated round close on `file.versioned` |
| done | Codex | Align review docs with current `2.3.1` runtime behavior | `main.py`, `TROUBLESHOOTING.md`, `TASKS.md`, `HANDOFF.md` | Updated stale troubleshooting examples/log references and removed a misleading hard-coded Notion DB comment from `main.py` |
| done | Codex | Clarify URL bootstrap vs `Frame Asset ID` stable linkage without changing runtime logic | `README.md`, `project_context.md`, `CHANGELOG.md`, `TASKS.md`, `HANDOFF.md` | Documented that `URL Frame.io` remains the manual input and `Frame Asset ID` remains the stable cached reference; no code path was changed to avoid regressions |
| done | Codex | Investigate resolved-comment sync feasibility and define an implementation plan | `TASKS.md`, `project_context.md`, `HANDOFF.md` | Official docs confirm partial feasibility only: Frame.io can emit completion/reopen events, but Notion public API cannot operate or read native resolved discussions; recommended plan is structured-state sync, not native bidirectional comment resolution |
| pending | Unassigned | Investigate `BUG-006` for `Cambios Solicitados` -> `Changes requested` | `main.py`, `BUGS.md`, `HANDOFF.md` | `frameio_status: updated` is reported but the asset remains in `Needs Review`; do not use this status as a round signal until confirmed |
| done | Codex | Redefine `Client Change Round` as a version-based round counter and adjust runtime logic | `main.py`, `README.md`, `project_context.md`, `CHANGELOG.md`, `BUGS.md`, `TASKS.md`, `HANDOFF.md` | Branch `feature/client-change-round-version-logic`; validated locally and via temporary staging function: task `31839c2f-efe7-81dd-8bd3-ca760c9a7a63` self-healed from round `2` to `1` while preserving the rest of the review signals |
| done | Codex | Implement workflow-backed review rounds for tasks without Frame.io | `main.py`, `README.md`, `project_context.md`, `CHANGELOG.md`, `TASKS.md`, `HANDOFF.md` | Merged into `main` after local merge validation and prior staging validation with page `31c39c2f-efe7-811a-9b6e-f40938fd0946`; deployment is still pending if the feature should go live |
| pending | Unassigned | Expand the Frame.io webhook to include `comment.completed` / `comment.uncompleted` and refresh review signals from those events | Frame.io webhook config, `main.py`, `README.md`, `project_context.md`, `HANDOFF.md` | Official Frame.io docs confirm both webhook events exist; implement by subscribing the live webhook, mapping both events to `fio_get_comment_signals()`, and updating `Client Review Open` / open-resolved counts without changing native Notion discussion state |
| done | Codex | Add version attribution to Frame.io comments and mirrored Notion feedback | `main.py`, Notion schema, `README.md`, `project_context.md`, `CHANGELOG.md`, `TASKS.md`, `HANDOFF.md` | Merged into `main` and deployed to production; runtime now resolves comment versions through V4 `files/{file_id}` plus `version_stacks/{version_stack_id}/children`, production validation passed for linked page `31839c2f-efe7-81dd-8bd3-ca760c9a7a63`, and `Last Frame Comment Version` persisted as `1`; still pending the first real observation of `Version > 1` once a linked asset actually gets a new version |
| pending | Unassigned | Investigate why direct local Frame.io API calls return `403` while equivalent reads succeed inside the Cloud Function | Local auth flow, Frame.io permissions, Secret Manager tokens, staging diagnostics, `project_context.md`, `BUGS.md`, `TASKS.md`, `HANDOFF.md` | During validation of `feature/frameio-comment-version-attribution`, direct local calls using refreshed OAuth tokens kept returning `403`, while staging/live Cloud Function requests could read the same file and comment resources; isolate whether the difference comes from token audience/scope, account context, secret freshness, or tenant-level policy before relying on local Frame.io diagnostics again |
| pending | Unassigned | Design the structured Notion-side UX for "resolve in Frame.io" without relying on native Notion comment resolution | Notion schema, `README.md`, `project_context.md`, `TASKS.md`, `HANDOFF.md` | Native Notion comment resolve/reopen is not observable or controllable via public API; if users need an action from Notion, it must be modeled with properties, buttons, or an auxiliary feedback database keyed by `Frame Comment ID` |
| pending | Unassigned | Validate whether Frame.io exposes a supported API write path to complete or reopen comments | Frame.io official docs, prototype script, `project_context.md`, `TASKS.md`, `HANDOFF.md` | Webhooks and comment reads are documented, but the public docs do not yet establish a stable completion-status mutation contract; do not implement `Notion -> Frame.io` comment completion until this is confirmed against official docs and a live prototype |
| done | Codex | Evaluate posting Frame.io feedback into Notion comments via API | `main.py`, `README.md`, `project_context.md`, `CHANGELOG.md`, `TASKS.md`, `HANDOFF.md` | Branch `feature/notion-comment-mirror`; implemented, validated live, UX-polished, and enabled in production for `comment.created` |
| done | Codex | Align `README.md` and `project_context.md` with the current review-round model | `README.md`, `project_context.md`, `TASKS.md` | Docs now reflect Secret Manager, `Frame Asset ID`, comment signals, `Client Change Round`, webhook scope, and current limitations |

## Status Values

- `pending`
- `in_progress`
- `blocked`
- `review`
- `done`

## Usage Rules

- Claim a task before editing shared files.
- Update the row if scope changes.
- If blocked, describe the blocker in `Notes`.
- When done, keep the task listed until the handoff is captured in `HANDOFF.md`.
