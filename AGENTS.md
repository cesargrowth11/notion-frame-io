# AGENTS.md

## Purpose

Shared operating guide for parallel work in this repository by Codex, Claude Code, or any other code agent.

This project is a Google Cloud Function that syncs status and metrics between Notion and Frame.io V4.

## Source Of Truth

- Runtime behavior: `main.py`
- Deployment details: `deploy.sh`
- Project overview: `project_context.md`
- Change history: `CHANGELOG.md`
- Bug and issue register: `BUGS.md`

If documentation conflicts with code, treat `main.py` as the current behavior and update docs in the same task.

## Repository Rules

- Do not commit or expose secrets from `.env.yaml`, `env.yaml`, `.env`, or tokens copied from terminals/logs.
- Do not rotate or replace production credentials unless explicitly requested.
- Do not change GCP project, region, function name, or public endpoints without documenting it first.
- Do not overwrite another agent's in-flight work. If a file is already being edited by another agent, stop and coordinate in `TASKS.md` or `HANDOFF.md`.
- Use ASCII by default when editing files unless the file clearly requires non-ASCII.

## Files That Need Extra Care

- `main.py`: production webhook logic and Frame.io/Notion integration
- `deploy.sh`: deployment workflow and GCP settings
- `project_context.md`: operational documentation
- `CHANGELOG.md`: versioned history
- `README.md`: user-facing setup guide, currently behind the code and should be updated carefully

## Parallel Work Protocol

- Prefer one task per branch or one task per `git worktree`.
- Before starting work, claim the task in `TASKS.md`.
- Before editing a shared file, note it in `TASKS.md`.
- After finishing or pausing, write a short entry in `HANDOFF.md`.
- If two agents must touch `main.py`, split by function/block and merge deliberately, not by blind overwrite.

## Recommended Worktree Layout

- `main`: stable local branch
- `worktrees/codex-*`: Codex task branches
- `worktrees/claude-*`: Claude task branches

Example naming:

- `codex/fix-notion-webhook`
- `claude/docs-readme-sync`

## Task Lifecycle

1. Read `project_context.md`, `CHANGELOG.md`, and relevant code.
2. Claim the task in `TASKS.md`.
3. Make the smallest correct change.
4. Run the narrowest useful verification.
5. Update docs and issue tracking before closing the task.
6. Add a handoff note in `HANDOFF.md`.

## Verification Expectations

Use the smallest relevant check for the task:

- Python syntax: `python -m py_compile main.py`
- Quick grep review: `rg -n "pattern" main.py`
- Manual health endpoint check after deploy: `curl <CLOUD_FUNCTION_URL>`

If deployment or live API checks are performed, record the outcome in `HANDOFF.md`.

## Documentation Expectations

At the start of every session:

- Read `README.md`, `project_context.md`, `CHANGELOG.md`, and `BUGS.md` if it exists.
- If any of them is stale relative to `main.py` or the deployed behavior, treat updating them as part of the active task, not optional cleanup.

After every meaningful change, before ending the session or handing off:

- `CHANGELOG.md` for the release entry
- `project_context.md` if architecture, behavior, or version changes
- `README.md` if setup, automation payloads, or deployment steps changed
- `BUGS.md` when:
  - a bug is discovered
  - a cause is confirmed
  - a workaround is adopted
  - a bug is resolved

Documentation and issue tracking are mandatory deliverables of each session. Do not leave behavior changes undocumented for a later pass unless the user explicitly asks you not to update docs.

## Current Project Notes

- Current runtime version is `2.3.1`.
- Tokens are persisted in Secret Manager, not Cloud Function env mutation.
- Notion association now prefers `Frame Asset ID` and falls back to `URL Frame.io`.
- Frame.io comment/version webhooks now feed review signals into Notion, including `Client Change Round`.
- `RpA` and `Semaforo RpA` remain calculated in Notion, not in Python.
- `BUG-006` is still open: `Cambios Solicitados` is not yet a reliable sync signal to Frame.io.

## Handoff Format

Each entry in `HANDOFF.md` should include:

- Date/time
- Agent name
- Task
- Files changed
- Verification run
- Remaining risks or next steps

## When In Doubt

- Avoid editing secrets.
- Avoid forceful git operations.
- Prefer documenting assumptions explicitly.
- Leave the repository in a state that another agent can pick up without guessing.
