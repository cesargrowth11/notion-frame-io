# TASKS.md

## Active Tasks

Use one line per task and keep it current.

| Status | Owner | Task | Files | Notes |
|--------|-------|------|-------|-------|
| done | Codex | Align `project_context.md` with `2.3.0` | `project_context.md` | Version and webhook notes updated |
| in_progress | Claude | Migrate token persistence from Cloud Function env vars to Secret Manager | `main.py`, `requirements.txt` | Env var approach fails with 403 permission error |
| done | Codex | Add troubleshooting guide for Notion -> Frame.io sync failures | `TROUBLESHOOTING.md`, `TASKS.md`, `HANDOFF.md` | Added standalone checklist without touching `main.py` |
| pending | Unassigned | Align `README.md` with current runtime behavior | `README.md` | README still reflects older behavior |

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
