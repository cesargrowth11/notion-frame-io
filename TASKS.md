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
| pending | Unassigned | Investigate `BUG-006` for `Cambios Solicitados` -> `Changes requested` | `main.py`, `BUGS.md`, `HANDOFF.md` | `frameio_status: updated` is reported but the asset remains in `Needs Review`; do not use this status as a round signal until confirmed |
| pending | Unassigned | Expand the Frame.io webhook to include `comment.completed` / `comment.uncompleted` if the API supports updating the existing workspace webhook | Frame.io webhook config, `HANDOFF.md` | PATCH of the existing webhook did not visibly change the subscribed events; open/resolved counts currently refresh on `comment.created`, `comment.deleted`, and `file.versioned` |
| pending | Unassigned | Evaluate posting Frame.io feedback into Notion comments via API | `main.py`, Notion integration settings, `README.md`, `project_context.md` | Proposed as a readable audit trail on the page, separate from the structured properties used by `RpA` and `Semaforo RpA` |
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
