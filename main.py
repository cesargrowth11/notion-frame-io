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
import unicodedata
import functions_framework
from flask import jsonify
import requests

# =============================================
# CONFIG (environment variables)
# =============================================

# Frame.io V4
FRAMEIO_ACCOUNT_ID = os.environ.get("FRAMEIO_ACCOUNT_ID")
FRAMEIO_PROJECT_ID = os.environ.get("FRAMEIO_PROJECT_ID")
FRAMEIO_STATUS_FIELD_ID = os.environ.get("FRAMEIO_STATUS_FIELD_ID")

# Token management (mutable at runtime)
_tokens = {
    "access_token": os.environ.get("FRAMEIO_ACCESS_TOKEN", ""),
    "refresh_token": os.environ.get("FRAMEIO_REFRESH_TOKEN", ""),
    "client_id": os.environ.get("FRAMEIO_CLIENT_ID", ""),
    "client_secret": os.environ.get("FRAMEIO_CLIENT_SECRET", ""),
}

# Secret Manager config
_SM_ACCESS_SECRET = os.environ.get("SM_ACCESS_SECRET", "frameio-access-token")
_SM_REFRESH_SECRET = os.environ.get("SM_REFRESH_SECRET", "frameio-refresh-token")

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


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value.strip())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(normalized.split()).lower()


_NORMALIZED_STATUS_MAP = {_normalize_text(k): v for k, v in STATUS_MAP.items() if k}


def _status_uuid_for(status: str | None) -> str:
    return _NORMALIZED_STATUS_MAP.get(_normalize_text(status), "")

# =============================================
# FRAME.IO TOKEN AUTO-REFRESH
# =============================================

_ADOBE_TOKEN_URL = "https://ims-na1.adobelogin.com/ims/token/v3"
_GCP_PROJECT = os.environ.get("GCP_PROJECT", os.environ.get("GCLOUD_PROJECT", "efeonce-group"))


def _read_secret(secret_id: str) -> str | None:
    """Read the latest version of a secret from Secret Manager."""
    try:
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{_GCP_PROJECT}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        logger.warning(f"Could not read secret {secret_id}: {e}")
        return None


def _write_secret(secret_id: str, value: str):
    """Add a new version of a secret in Secret Manager."""
    try:
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        parent = f"projects/{_GCP_PROJECT}/secrets/{secret_id}"
        client.add_secret_version(
            request={"parent": parent, "payload": {"data": value.encode("UTF-8")}}
        )
        logger.info(f"Secret {secret_id} updated in Secret Manager")
    except Exception as e:
        logger.warning(f"Could not write secret {secret_id}: {e}")


def _load_tokens_from_secrets():
    """Load tokens from Secret Manager, falling back to env vars."""
    access = _read_secret(_SM_ACCESS_SECRET)
    if access:
        _tokens["access_token"] = access
        logger.info("Loaded access_token from Secret Manager")

    refresh = _read_secret(_SM_REFRESH_SECRET)
    if refresh:
        _tokens["refresh_token"] = refresh
        logger.info("Loaded refresh_token from Secret Manager")


# Load tokens from Secret Manager on cold start
_load_tokens_from_secrets()


def _refresh_access_token() -> str | None:
    """Exchange refresh_token for a new access_token via Adobe IMS."""
    if not _tokens["refresh_token"] or not _tokens["client_id"] or not _tokens["client_secret"]:
        logger.error("Cannot refresh: missing refresh_token, client_id, or client_secret")
        return None

    resp = requests.post(_ADOBE_TOKEN_URL, data={
        "grant_type": "refresh_token",
        "client_id": _tokens["client_id"],
        "client_secret": _tokens["client_secret"],
        "refresh_token": _tokens["refresh_token"],
    }, timeout=30)

    if resp.status_code != 200:
        logger.error(f"Token refresh failed: {resp.status_code} {resp.text[:300]}")
        return None

    data = resp.json()
    new_access = data.get("access_token", "")
    new_refresh = data.get("refresh_token", _tokens["refresh_token"])

    if not new_access:
        logger.error("Token refresh returned empty access_token")
        return None

    _tokens["access_token"] = new_access
    _tokens["refresh_token"] = new_refresh
    logger.info("Token refreshed successfully")

    # Persist new tokens to Secret Manager
    _write_secret(_SM_ACCESS_SECRET, new_access)
    _write_secret(_SM_REFRESH_SECRET, new_refresh)

    return new_access


def _fio_request(method: str, url: str, **kwargs) -> requests.Response:
    """Make a Frame.io API request with automatic token refresh on 401."""
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {_tokens['access_token']}"
    headers.setdefault("Content-Type", "application/json")

    r = requests.request(method, url, headers=headers, **kwargs)

    if r.status_code == 401:
        logger.warning("Frame.io returned 401, attempting token refresh...")
        new_token = _refresh_access_token()
        if new_token:
            headers["Authorization"] = f"Bearer {new_token}"
            r = requests.request(method, url, headers=headers, **kwargs)

    return r


# =============================================
# FRAME.IO URL PARSER
# =============================================

_URL_PATTERNS = [
    r"frame\.io/player/([a-f0-9\-]{36})",
    r"frame\.io/reviews/[^/]+/asset/([a-f0-9\-]{36})",
    r"frame\.io/reviews/[^/]+/([a-f0-9\-]{36})",
    r"frame\.io/(?:v4/)?projects/[^/]+/files/([a-f0-9\-]{36})",
    r"next\.frame\.io/project/[^/]+/view/([a-f0-9\-]{36})",
    r"frame\.io/.*?([a-f0-9\-]{36})(?:\?|#|$)",
]
_UUID_RE = re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", re.I)
_SHORT_URL_RE = re.compile(r"^https?://(f\.io|fio\.co)/", re.I)
_VIEW_URL_RE = re.compile(r"next\.frame\.io/.+/view/", re.I)


def _resolve_short_url(url: str) -> str | None:
    """Resolve a shortened f.io URL to its final destination."""
    try:
        r = requests.head(url, allow_redirects=True, timeout=10)
        final = r.url
        if final and final != url:
            logger.info(f"Resolved short URL: {url} -> {final}")
            return final
    except Exception as e:
        logger.warning(f"Failed to resolve short URL {url}: {e}")
    return None


def _search_project_for_url(original_url: str) -> str | None:
    """Search all assets in the project comparing view_url with the given URL."""
    if not FRAMEIO_ACCOUNT_ID or not FRAMEIO_PROJECT_ID:
        return None

    try:
        # Get project root folder
        url = f"{_FIO}/v2/projects/{FRAMEIO_PROJECT_ID}"
        r = _fio_request("GET", url, timeout=15)
        if r.status_code != 200:
            logger.warning(f"Cannot get project info: {r.status_code}")
            return None

        root_asset_id = r.json().get("root_asset_id")
        if not root_asset_id:
            return None

        # Search children recursively (max 2 levels to avoid timeout)
        return _search_children_for_url(root_asset_id, original_url, depth=0, max_depth=2)
    except Exception as e:
        logger.warning(f"Project search error: {e}")
        return None


def _search_children_for_url(parent_id: str, target_url: str, depth: int, max_depth: int) -> str | None:
    """Recursively search children for an asset whose view_url matches."""
    r = _fio_request("GET", f"{_FIO}/v2/assets/{parent_id}/children?page_size=50", timeout=15)
    if r.status_code != 200:
        return None

    children = r.json()
    if not isinstance(children, list):
        return None

    for child in children:
        child_id = child.get("id", "")
        # Check if the target URL contains this asset's ID
        if child_id and child_id in target_url:
            return child_id

        # Check view_url or _links
        for url_field in ["view_url", "original_url"]:
            val = child.get(url_field, "")
            if val and (val == target_url or target_url in val or val in target_url):
                return child_id

        # Recurse into folders and version stacks
        if depth < max_depth and child.get("type") in ("folder", "version_stack"):
            found = _search_children_for_url(child_id, target_url, depth + 1, max_depth)
            if found:
                return found

    return None


def parse_asset_id(url_or_id: str) -> str | None:
    s = (url_or_id or "").strip()
    if not s:
        return None
    if _UUID_RE.match(s):
        return s

    # Resolve shortened URLs (f.io/xxx, fio.co/xxx)
    if _SHORT_URL_RE.match(s):
        resolved = _resolve_short_url(s)
        if resolved:
            s = resolved

    # Try standard patterns
    for pat in _URL_PATTERNS:
        m = re.search(pat, s, re.I)
        if m:
            return m.group(1)

    # For next.frame.io view URLs or unrecognized URLs, fallback to project search
    if _VIEW_URL_RE.search(s) or "frame.io" in s.lower():
        logger.info(f"URL not matched by patterns, trying project search: {s}")
        found = _search_project_for_url(s)
        if found:
            logger.info(f"Found asset via project search: {found}")
            return found

    logger.warning(f"Cannot extract asset ID from: {s}")
    return None

# =============================================
# FRAME.IO V4 API
# =============================================

_FIO = "https://api.frame.io"


def fio_update_status(asset_id: str, status_uuid: str):
    # List of endpoint/body combinations to try
    attempts = [
        # 1) Account-level metadata values
        ("PATCH", f"{_FIO}/v4/accounts/{FRAMEIO_ACCOUNT_ID}/metadata/values",
         {"data": {"asset_ids": [asset_id], "values": [{"field_definition_id": FRAMEIO_STATUS_FIELD_ID, "value": [status_uuid]}]}}),
        # 2) Project-level metadata values
        ("PATCH", f"{_FIO}/v4/accounts/{FRAMEIO_ACCOUNT_ID}/projects/{FRAMEIO_PROJECT_ID}/metadata/values",
         {"data": {"asset_ids": [asset_id], "values": [{"field_definition_id": FRAMEIO_STATUS_FIELD_ID, "value": [status_uuid]}]}}),
        # 3) Account-level without data wrapper
        ("PATCH", f"{_FIO}/v4/accounts/{FRAMEIO_ACCOUNT_ID}/metadata/values",
         {"asset_ids": [asset_id], "values": [{"field_definition_id": FRAMEIO_STATUS_FIELD_ID, "value": [status_uuid]}]}),
        # 4) POST instead of PATCH
        ("POST", f"{_FIO}/v4/accounts/{FRAMEIO_ACCOUNT_ID}/metadata/values",
         {"data": {"asset_ids": [asset_id], "values": [{"field_definition_id": FRAMEIO_STATUS_FIELD_ID, "value": [status_uuid]}]}}),
    ]

    r = None
    for i, (method, url, body) in enumerate(attempts, 1):
        r = _fio_request(method, url, json=body, timeout=10)
        short_url = url.split("/v4/")[-1]
        logger.warning(f"FIO attempt {i} ({method} {short_url}): {r.status_code} resp={r.text[:200]}")
        if r.status_code < 400:
            logger.warning(f"FIO status update SUCCESS on attempt {i}")
            return r.json()
        if r.status_code not in (404, 405, 422):
            break

    r.raise_for_status()
    return r.json()


def fio_get_counts(asset_id: str) -> dict:
    """Get version count + comment count for an asset."""
    out = {"versions": 1, "comments": 0}

    # --- Try V2 first (more reliable for version stacks) ---
    try:
        r = _fio_request("GET", f"{_FIO}/v2/assets/{asset_id}", timeout=15)
        if r.status_code == 200:
            d = r.json()
            out["comments"] = d.get("comment_count", 0)

            # If the asset itself is a version_stack
            if d.get("type") == "version_stack":
                ch = _fio_request("GET", f"{_FIO}/v2/assets/{asset_id}/children", timeout=15)
                if ch.status_code == 200:
                    children = ch.json()
                    out["versions"] = len(children) if isinstance(children, list) else 1

            # If the asset is inside a version_stack
            elif d.get("parent_id"):
                pr = _fio_request("GET", f"{_FIO}/v2/assets/{d['parent_id']}", timeout=15)
                if pr.status_code == 200 and pr.json().get("type") == "version_stack":
                    ch = _fio_request("GET", f"{_FIO}/v2/assets/{d['parent_id']}/children", timeout=15)
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


def notion_get_page(page_id: str) -> dict | None:
    """Fetch a Notion page to recover properties when webhook payload is minimal."""
    r = requests.get(f"{_NOTION}/pages/{page_id}", headers=_not_h(), timeout=15)
    if r.status_code == 200:
        return r.json()
    logger.warning(f"Could not fetch Notion page {page_id}: {r.status_code} {r.text[:300]}")
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
    data_sources = []
    if isinstance(data, dict):
        data_sources.append(data)
        props = data.get("properties")
        if isinstance(props, dict):
            data_sources.append(props)
    elif isinstance(payload, dict):
        data_sources.append(payload)

    asset_id = None
    status = None
    page_id = None

    for source in data_sources:
        if not page_id:
            page_id = source.get("page_id") or source.get("id")
        page = source.get("page")
        if not page_id and isinstance(page, dict):
            page_id = page.get("id")

    # -- Frame URL --
    for source in data_sources:
        for key in [PROP_FRAME_URL, "URL Frame.io", "Frame URL", "Entregable"]:
            prop = source.get(key)
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
        if asset_id:
            break

    # -- Status --
    for source in data_sources:
        for key in [PROP_STATUS, "Estado", "Status"]:
            prop = source.get(key)
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

    if page_id and (not asset_id or not status):
        page = notion_get_page(page_id)
        if page:
            recovered_asset_id, recovered_status, _ = parse_notion_payload({
                "data": page.get("properties", {}),
                "page_id": page_id,
            })
            asset_id = asset_id or recovered_asset_id
            status = status or recovered_status

    if not asset_id:
        return jsonify({"skipped": True, "reason": "No Frame.io URL in this task", "hint": f"Fill '{PROP_FRAME_URL}' in the Notion page"}), 200

    result = {"asset_id": asset_id, "status": status}

    # 1) Update Frame.io status
    status_uuid = _status_uuid_for(status)
    if status and status_uuid:
        try:
            fio_update_status(asset_id, status_uuid)
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
            "version": "2.3.0",
            "status": "ok",
            "endpoints": ["/notion-webhook", "/frameio-webhook"],
            "mapping": {k: ("ok" if v else "NOT SET") for k, v in STATUS_MAP.items()},
            "notion_db": NOTION_DATABASE_ID,
        }), 200

    if request.method != "POST":
        return jsonify({"error": "Method not allowed"}), 405

    missing = [k for k, v in {"FRAMEIO_ACCESS_TOKEN": _tokens["access_token"], "NOTION_TOKEN": NOTION_TOKEN}.items() if not v]
    if missing:
        return jsonify({"error": "Missing env vars", "missing": missing}), 500

    if path == "/frameio-webhook":
        return handle_frameio(request)
    return handle_notion(request)
