# TROUBLESHOOTING.md

## Notion Changes Status But Frame.io Does Not

Use this checklist when a Notion automation fires but the asset status in Frame.io does not change.

## 1. Confirm The Function Is Alive

Run:

```bash
curl https://us-central1-efeonce-group.cloudfunctions.net/notion-frameio-sync
```

Expected shape:

```json
{
  "service": "notion-frameio-sync",
  "version": "2.3.1",
  "status": "ok",
  "endpoints": ["/notion-webhook", "/frameio-webhook"],
  "mapping": {
    "En curso": "ok",
    "Listo para revision": "ok",
    "Cambios Solicitados": "ok",
    "Listo": "ok"
  }
}
```

If any mapping value shows `NOT SET`, the function cannot translate that Notion status to a Frame.io UUID.

## 2. Confirm The Notion Automation URL

The automation must call:

```text
https://us-central1-efeonce-group.cloudfunctions.net/notion-frameio-sync/notion-webhook
```

Common mistakes:

- calling `/` instead of `/notion-webhook`
- using an old function URL after redeploy
- trailing spaces or an incomplete pasted URL in Notion

## 3. Confirm The Page Has A Frame.io Reference

The webhook returns HTTP 200 even when the task cannot be synced.

If the page is missing both the explicit asset ID and the Frame.io URL, the function responds with:

```json
{
  "skipped": true,
  "reason": "No Frame.io asset reference in this task"
}
```

Check that the Notion page actually contains a valid asset reference in one of these properties:

- `Frame Asset ID`
- `URL Frame.io`

Accepted formats include:

- `https://app.frame.io/player/<asset-id>`
- `https://app.frame.io/reviews/...`
- `https://app.frame.io/projects/.../files/<asset-id>`
- `https://f.io/...`
- `https://fio.co/...`
- `https://next.frame.io/project/.../view/...`

## 4. Confirm The Status Is Mapped

Supported Notion statuses are:

- `En curso`
- `Listo para revision`
- `Cambios Solicitados`
- `Listo`

The current code normalizes accents, spaces, and case before matching, so common accent or capitalization variations of `Listo para revision` should still resolve.

If the status is not mapped or its UUID env var is empty, the function responds with something like:

```json
{
  "frameio_status": "skipped ('<status>' not mapped or no UUID)"
}
```

If that happens, verify:

- the Notion status name is one of the supported values
- the corresponding env var exists in the deployed function
- the health endpoint shows `ok` for that mapping

## 5. Manually Test The Webhook Outside Notion

Run a direct request to isolate whether the problem is in Notion or in the function.

```bash
curl -X POST https://us-central1-efeonce-group.cloudfunctions.net/notion-frameio-sync/notion-webhook \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "URL Frame.io": {
        "type": "url",
        "url": "https://app.frame.io/player/TU-ASSET-ID"
      },
      "Estado": {
        "type": "status",
        "status": {"name": "Listo"}
      }
    }
  }'
```

Interpretation:

- `frameio_status: "updated"` means the Notion side is probably misconfigured
- `skipped` means the payload is missing URL or status data
- `frameio_status_error` means the function reached Frame.io and Frame.io rejected the update

## 6. Check Cloud Logs

Search for the latest request in Cloud Logging for `notion-frameio-sync`.

Important log lines:

- `Notion webhook:` shows the received payload
- `Cannot extract asset ID from:` means URL parsing failed
- `Found asset via project search:` means fallback lookup worked
- `Frame.io returned 401, attempting token refresh...` means the access token expired
- `FIO bulk_update metadata:` shows the actual Frame.io metadata write response and status code
- `Frame.io error:` means the sync reached Frame.io but failed

## 7. Interpret The Most Common Failure Modes

### Case A: HTTP 200 but nothing changes in Frame.io

Most likely:

- missing `Frame Asset ID` and `URL Frame.io`
- status not mapped
- Notion automation sent too little data and page recovery also failed

Check the JSON response body first. Do not rely only on the HTTP status code.

### Case B: Frame.io returns 401

Most likely:

- expired access token
- refresh token flow failed
- token storage/update issue in the deployed environment

Look for:

- `Frame.io returned 401, attempting token refresh...`
- `Token refresh failed:`

### Case C: Frame.io returns 404, 405, or 422 during metadata update

Most likely:

- wrong account or project configuration
- wrong metadata field UUID
- wrong status value UUID
- asset does not belong to the expected account/project

Look for the `FIO bulk_update metadata:` log to see the live API response body.

### Case D: Notion automation fires but the payload is too small

The function can recover missing properties from Notion if it receives a `page_id`, but if the automation sends neither useful properties nor a recoverable page reference, status sync will be skipped.

## 8. Fast Triage Order

Use this order to avoid wasting time:

1. Hit the health endpoint.
2. Check that all mappings are `ok`.
3. Confirm the page has `Frame Asset ID` or `URL Frame.io`.
4. Trigger the Notion automation and inspect the response body.
5. If unclear, run the manual `curl` test.
6. If manual `curl` works, fix Notion automation payload or URL.
7. If manual `curl` fails, inspect Cloud Logging and Frame.io config.

## 9. Known Relevant Files

- `main.py`
- `project_context.md`
- `CHANGELOG.md`
- `deploy.sh`

## 10. Escalate When

Escalate to code/config review if:

- the health endpoint shows correct mappings but all Frame.io metadata updates fail
- token refresh fails repeatedly
- the asset URL is valid but `Cannot extract asset ID from:` still appears
- the asset belongs to a different Frame.io account/project than the configured one
