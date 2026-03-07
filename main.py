"""
Notion <-> Frame.io V4 Bidirectional Sync — V2
Google Cloud Function (2nd Gen)

FLUJO 1 — Notion -> Frame.io:
  Status change in Notion -> webhook -> update Frame.io asset status

FLUJO 2 — Frame.io -> Notion (push):
  New version/comment in Frame.io -> webhook -> update counts in Notion

FLUJO 3 — Pull on status change:
  When Notion status changes, also pull Frame.io counts back to Notion

Efeonce Group — Globe Studio Pipeline

Base de datos Notion: "Tareas" (5126d7d8-bf3f-454c-80f4-be31d1ca38d4)
Propiedades: Estado, URL Frame.io, Frame Versions, Frame Comments
"""

import os
import re
import json
import logging
import functions_framework
from flask import jsonify
import requests

# =============================================
# CONFIG (environment variables)
# =============================================

# Frame.io V4
FRAMEIO_ACCESS_TOKEN = os.environ.get("FRAMEIO_ACCESS_TOKEN")
FRAMEIO_ACCOUNT_ID = os.environ.get("FRAMEIO_ACCOUNT_ID")
FRAMEIO_PROJECT_ID = os.environ.get("FRAMEIO_PROJECT_ID")
FRAMEIO_STATUS_FIELD_ID = os.environ.get("FRAMEIO_STATUS_FIELD_ID")

# Notion
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "3a54f0904be14158833533ba96557a73")

# Notion property names (match your "Tareas" DB)
PROP_STATUS = os.environ.get("NOTION_PROP_STATUS", "Estado")
PROP_FRAME_URL = os.environ.get("NOTION_PROP_FRAME_URL", "URL Frame.io")
PROP_VERSIONS = os.environ.get("NOTION_PROP_VERSIONS", "Frame Versions")
PROP_COMMENTS = os.environ.get("NOTION_PROP_COMMENTS", "Frame Comments")

# Status mapping: Notion status name -> Frame.io status UUID
STATUS_MAP = {
    "En curso":             os.environ.get("FRAMEIO_STATUS_IN_PROGRESS", ""),
    "Listo para revision":  os.environ.get("FRAMEIO_STATUS_NEEDS_REVIEW", ""),
    "Cambios Solicitados":  os.environ.get("FRAMEIO_STATUS_CHANGES_REQUESTED", ""),
    "Listo":                os.environ.get("FRAMEIO_STATUS_APPROVED", ""),
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("notion-frameio-sync")

# =============================================
# FRAME.IO URL PARSER
# =============================================

_URL_PATTERNS = [
    r"frame\.io/player/([a-f0-9\-]{36})",
    r"frame\.io/reviews/[^/]+/asset/([a-f0-9\-]{36})",
    r"frame\.io/reviews/[^/]+/([a-f0-9\-]{36})",
    r"frame\.io/(?:v4/)?projects/[^/]+/files/([a-f0-9\-]{36})",
    r"frame\.io/.*?([a-f0-9\-]{36})(?:\?|#|$)",
]
_UUID_RE = re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", re.I)


def parse_asset_id(url_or_id: str) -> str | None:
    s = (url_or_id or "").strip()
    if not s:
        return None
    if _UUID_RE.match(s):
        return s
    for pat in _URL_PATTERNS:
        m = re.search(pat, s, re.I)
        if m:
            return m.group(1)
    logger.warning(f"Cannot extract asset ID from: {s}")
    return None

# =============================================
# FRAME.IO V4 API
# =============================================

_FIO = "https://api.frame.io"


def _fio_h():
    return {"Authorization": f"Bearer {FRAMEIO_ACCESS_TOKEN}", "Content-Type": "application/json"}


def fio_update_status(asset_id: str, status_uuid: str):
    url = f"{_FIO}/v4/accounts/{FRAMEIO_ACCOUNT_ID}/projects/{FRAMEIO_PROJECT_ID}/metadata/values"
    body = {"data": {"asset_ids": [asset_id], "values": [{"field_definition_id": FRAMEIO_STATUS_FIELD_ID, "value": [status_uuid]}]}}
    r = requests.patch(url, headers=_fio_h(), json=body, timeout=30)
    logger.info(f"Frame.io PATCH status: {r.status_code}")
    r.raise_for_status()
    return r.json()


def fio_get_counts(asset_id: str) -> dict:
    """Get version count + comment count for an asset."""
    out = {"versions": 1, "comments": 0}

    # --- Try V2 first (more reliable for version stacks) ---
    try:
        r = requests.get(f"{_FIO}/v2/assets/{asset_id}", headers=_fio_h(), timeout=15)
        if r.status_code == 200:
            d = r.json()
            out["comments"] = d.get("comment_count", 0)

            # If the asset itself is a version_stack
            if d.get("type") == "version_stack":
                ch = requests.get(f"{_FIO}/v2/assets/{asset_id}/children", headers=_fio_h(), timeout=15)
                if ch.status_code == 200:
                    children = ch.json()
                    out["versions"] = len(children) if isinstance(children, list) else 1

            # If the asset is inside a version_stack
            elif d.get("parent_id"):
                pr = requests.get(f"{_FIO}/v2/assets/{d['parent_id']}", headers=_fio_h(), timeout=15)
                if pr.status_code == 200 and pr.json().get("type") == "version_stack":
                    ch = requests.get(f"{_FIO}/v2/assets/{d['parent_id']}/children", headers=_fio_h(), timeout=15)
                    if ch.status_code == 200:
                        children = ch.json()
                        out["versions"] = len(children) if isinstance(children, list) else 1
                        # Sum comments across all versions
                        total_comments = sum(c.get("comment_count", 0) for c in children if isinstance(c, dict))
                        if total_comments > out["comments"]:
                            out["comments"] = total_comments

    except Exception as e:
        logger.warning(f"V2 asset fetch error: {e}")

    logger.info(f"Asset {asset_id}: versions={out['versions']}, comments={out['comments']}")
    return out

# =============================================
# NOTION API
# =============================================

_NOTION = "https://api.notion.com/v1"


def _not_h():
    return {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}


def notion_find_page(asset_id: str) -> str | None:
    """Find Notion page whose 'URL Frame.io' contains this asset_id."""
    body = {"filter": {"property": PROP_FRAME_URL, "url": {"contains": asset_id}}, "page_size": 1}
    r = requests.post(f"{_NOTION}/databases/{NOTION_DATABASE_ID}/query", headers=_not_h(), json=body, timeout=15)
    if r.status_code == 200:
        results = r.json().get("results", [])
        if results:
            return results[0]["id"]
    return None


def notion_update_counts(page_id: str, versions: int, comments: int):
    """Set Frame Versions and Frame Comments on a Notion page."""
    props = {
        PROP_VERSIONS: {"number": versions},
        PROP_COMMENTS: {"number": comments},
    }
    r = requests.patch(f"{_NOTION}/pages/{page_id}", headers=_not_h(), json={"properties": props}, timeout=15)
    r.raise_for_status()
    return r.json()

# =============================================
# NOTION WEBHOOK PAYLOAD PARSER
# =============================================


def parse_notion_payload(payload: dict) -> tuple[str | None, str | None, str | None]:
    """
    Returns (frame_asset_id, notion_status, notion_page_id)
    """
    data = payload.get("data", payload)
    asset_id = None
    status = None
    page_id = data.get("page_id", data.get("id"))

    # -- Frame URL --
    for key in [PROP_FRAME_URL, "URL Frame.io", "Frame URL", "Entregable"]:
        prop = data.get(key)
        if not prop:
            continue
        raw = None
        if isinstance(prop, str):
            raw = prop
        elif isinstance(prop, dict):
            t = prop.get("type", "")
            if t == "url":
                raw = prop.get("url", "")
            elif t == "rich_text":
                tx = prop.get("rich_text", [])
                raw = tx[0].get("plain_text", "") if tx else None
            elif "url" in prop:
                raw = prop["url"]
        if raw:
            asset_id = parse_asset_id(raw)
            if asset_id:
                break

    # -- Status --
    for key in [PROP_STATUS, "Estado", "Status"]:
        prop = data.get(key)
        if not prop:
            continue
        if isinstance(prop, str):
            status = prop.strip()
        elif isinstance(prop, dict):
            t = prop.get("type", "")
            if t == "status":
                o = prop.get("status", {})
                status = o.get("name", "").strip() if o else None
            elif t == "select":
                o = prop.get("select", {})
                status = o.get("name", "").strip() if o else None
        if status:
            break

    return asset_id, status, page_id

# =============================================
# HANDLERS
# =============================================


def handle_notion(request):
    """Notion status change -> Frame.io + pull counts."""
    try:
        payload = request.get_json(force=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    logger.info(f"Notion webhook: {json.dumps(payload)[:800]}")
    asset_id, status, page_id = parse_notion_payload(payload)

    if not asset_id:
        return jsonify({"error": "No Frame.io URL found in payload", "hint": f"Include '{PROP_FRAME_URL}' in webhook"}), 400

    result = {"asset_id": asset_id, "status": status}

    # 1) Update Frame.io status
    if status and status in STATUS_MAP and STATUS_MAP[status]:
        try:
            fio_update_status(asset_id, STATUS_MAP[status])
            result["frameio_status"] = "updated"
        except Exception as e:
            result["frameio_status_error"] = str(e)
            logger.error(f"Frame.io error: {e}")
    else:
        result["frameio_status"] = f"skipped ('{status}' not mapped or no UUID)"

    # 2) Pull counts from Frame.io -> Notion
    if page_id:
        try:
            counts = fio_get_counts(asset_id)
            notion_update_counts(page_id, counts["versions"], counts["comments"])
            result["notion_counts"] = counts
        except Exception as e:
            result["notion_counts_error"] = str(e)
            logger.error(f"Notion counts error: {e}")
    else:
        # Try to find page by URL
        found = notion_find_page(asset_id)
        if found:
            try:
                counts = fio_get_counts(asset_id)
                notion_update_counts(found, counts["versions"], counts["comments"])
                result["notion_counts"] = counts
                result["notion_page_found"] = found
            except Exception as e:
                result["notion_counts_error"] = str(e)
        else:
            result["notion_counts"] = "skipped (no page_id, page not found)"

    return jsonify({"success": True, **result}), 200


def handle_frameio(request):
    """Frame.io event -> update Notion counts."""
    try:
        payload = request.get_json(force=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    logger.info(f"Frame.io webhook: {json.dumps(payload)[:800]}")

    event = payload.get("type", "unknown")
    asset_id = payload.get("resource", {}).get("id", "")
    if not asset_id:
        return jsonify({"error": "No asset ID"}), 400

    # Find Notion page
    page_id = notion_find_page(asset_id)
    if not page_id:
        return jsonify({"warning": "No Notion page found", "asset_id": asset_id}), 200

    # Get counts and update
    try:
        counts = fio_get_counts(asset_id)
        notion_update_counts(page_id, counts["versions"], counts["comments"])
        return jsonify({"success": True, "event": event, "page_id": page_id, "counts": counts}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 502

# =============================================
# ENTRYPOINT
# =============================================


@functions_framework.http
def sync_status(request):
    path = request.path.rstrip("/")

    if request.method == "GET":
        return jsonify({
            "service": "notion-frameio-sync",
            "version": "2.0.0",
            "status": "ok",
            "endpoints": ["/notion-webhook", "/frameio-webhook"],
            "mapping": {k: ("ok" if v else "NOT SET") for k, v in STATUS_MAP.items()},
            "notion_db": NOTION_DATABASE_ID,
        }), 200

    if request.method != "POST":
        return jsonify({"error": "Method not allowed"}), 405

    missing = [k for k, v in {"FRAMEIO_ACCESS_TOKEN": FRAMEIO_ACCESS_TOKEN, "NOTION_TOKEN": NOTION_TOKEN}.items() if not v]
    if missing:
        return jsonify({"error": "Missing env vars", "missing": missing}), 500

    if path == "/frameio-webhook":
        return handle_frameio(request)
    return handle_notion(request)
