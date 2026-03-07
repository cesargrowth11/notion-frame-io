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

Base de datos Notion: "Tareas"
Propiedades clave: Estado, URL Frame.io, Frame Asset ID, Frame Versions, Frame Comments
"""

import os
import re
import json
import logging
import unicodedata
from datetime import datetime, timezone
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
PROP_ASSET_ID = os.environ.get("NOTION_PROP_ASSET_ID", "Frame Asset ID")
PROP_VERSIONS = os.environ.get("NOTION_PROP_VERSIONS", "Frame Versions")
PROP_COMMENTS = os.environ.get("NOTION_PROP_COMMENTS", "Frame Comments")
PROP_OPEN_COMMENTS = os.environ.get("NOTION_PROP_OPEN_COMMENTS", "Open Frame Comments")
PROP_RESOLVED_COMMENTS = os.environ.get("NOTION_PROP_RESOLVED_COMMENTS", "Resolved Frame Comments")
PROP_LAST_COMMENT = os.environ.get("NOTION_PROP_LAST_COMMENT", "Last Frame Comment")
PROP_LAST_COMMENT_ID = os.environ.get("NOTION_PROP_LAST_COMMENT_ID", "Last Frame Comment ID")
PROP_LAST_COMMENT_AT = os.environ.get("NOTION_PROP_LAST_COMMENT_AT", "Last Frame Comment At")
PROP_LAST_COMMENT_TIMECODE = os.environ.get("NOTION_PROP_LAST_COMMENT_TIMECODE", "Last Frame Comment Timecode")
PROP_LAST_COMMENT_VERSION = os.environ.get("NOTION_PROP_LAST_COMMENT_VERSION", "Last Frame Comment Version")
PROP_LAST_REVIEWED_VERSION = os.environ.get("NOTION_PROP_LAST_REVIEWED_VERSION", "Last Reviewed Version")
PROP_CLIENT_REVIEW_OPEN = os.environ.get("NOTION_PROP_CLIENT_REVIEW_OPEN", "Client Review Open")
PROP_CHANGE_ROUND = os.environ.get("NOTION_PROP_CHANGE_ROUND", "Client Change Round")
PROP_WORKFLOW_CHANGE_ROUND = os.environ.get("NOTION_PROP_WORKFLOW_CHANGE_ROUND", "Workflow Change Round")
PROP_WORKFLOW_REVIEW_OPEN = os.environ.get("NOTION_PROP_WORKFLOW_REVIEW_OPEN", "Workflow Review Open")
PROP_LAST_WORKFLOW_STATUS = os.environ.get("NOTION_PROP_LAST_WORKFLOW_STATUS", "Last Workflow Status")
PROP_REVIEW_SOURCE = os.environ.get("NOTION_PROP_REVIEW_SOURCE", "Review Source")

# Status mapping: Notion status name -> Frame.io status UUID
STATUS_MAP = {
    "En curso":             os.environ.get("FRAMEIO_STATUS_IN_PROGRESS", ""),
    "Listo para revision":  os.environ.get("FRAMEIO_STATUS_NEEDS_REVIEW", ""),
    "Cambios Solicitados":  os.environ.get("FRAMEIO_STATUS_CHANGES_REQUESTED", ""),
    "Listo":                os.environ.get("FRAMEIO_STATUS_APPROVED", ""),
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("notion-frameio-sync")


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


NOTION_ENABLE_FRAME_COMMENT_MIRROR = _env_flag("NOTION_ENABLE_FRAME_COMMENT_MIRROR", False)


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value.strip())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(normalized.split()).lower()


_NORMALIZED_STATUS_MAP = {_normalize_text(k): v for k, v in STATUS_MAP.items() if k}
_STATUS_REVIEW = _normalize_text("Listo para revision")
_STATUS_CHANGES = _normalize_text("Cambios Solicitados")
_STATUS_IN_PROGRESS = _normalize_text("En curso")
_STATUS_DONE = _normalize_text("Listo")


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
    url = f"{_FIO}/v4/accounts/{FRAMEIO_ACCOUNT_ID}/projects/{FRAMEIO_PROJECT_ID}/metadata/values"
    body = {
        "data": {
            "file_ids": [asset_id],
            "values": [{
                "field_definition_id": FRAMEIO_STATUS_FIELD_ID,
                "value": [status_uuid],
            }],
        }
    }

    r = _fio_request("PATCH", url, json=body, timeout=10)
    logger.warning(f"FIO bulk_update metadata: {r.status_code} resp={r.text[:500]}")

    if r.status_code == 204 or not r.text.strip():
        logger.info("FIO status update request accepted")
        return {}

    r.raise_for_status()
    return r.json() if r.text else {}


def fio_get_counts(asset_id: str) -> dict:
    """Get version count + comment count for an asset."""
    out = {"versions": 1, "comments": 0}

    # --- Prefer V4 metadata for comment count ---
    try:
        r = _fio_request("GET", f"{_FIO}/v4/accounts/{FRAMEIO_ACCOUNT_ID}/files/{asset_id}/metadata", timeout=15)
        if r.status_code == 200:
            payload = r.json().get("data", [])
            if isinstance(payload, list):
                file_data = payload[0] if payload else {}
            elif isinstance(payload, dict):
                file_data = payload
            else:
                file_data = {}
            metadata = file_data.get("metadata", []) if isinstance(file_data, dict) else []
            for field in metadata:
                if field.get("field_definition_name") == "Comment Count":
                    value = field.get("value", 0)
                    if isinstance(value, (int, float)):
                        out["comments"] = int(value)
                    break
    except Exception as e:
        logger.warning(f"V4 metadata fetch error: {e}")

    # --- Try V2 first (more reliable for version stacks) ---
    try:
        r = _fio_request("GET", f"{_FIO}/v2/assets/{asset_id}", timeout=15)
        if r.status_code == 200:
            d = r.json()
            out["comments"] = max(out["comments"], d.get("comment_count", 0))

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
                        out["comments"] = max(out["comments"], total_comments)

    except Exception as e:
        logger.warning(f"V2 asset fetch error: {e}")

    logger.info(f"Asset {asset_id}: versions={out['versions']}, comments={out['comments']}")
    return out


def fio_get_comment_file_id(comment_id: str) -> str | None:
    """Resolve the parent file ID for a comment webhook resource."""
    try:
        r = _fio_request("GET", f"{_FIO}/v4/accounts/{FRAMEIO_ACCOUNT_ID}/comments/{comment_id}", timeout=15)
        r.raise_for_status()
        data = r.json().get("data", {})

        # Stable docs expose GET /comments/{comment_id}; be tolerant to response shape.
        file_id = data.get("file_id")
        if file_id:
            return file_id

        file_obj = data.get("file", {})
        if isinstance(file_obj, dict):
            return file_obj.get("id")
    except Exception as e:
        logger.warning(f"Could not resolve file_id for comment {comment_id}: {e}")

    return None


def fio_get_comment(comment_id: str) -> dict | None:
    """Fetch a single comment payload from Frame.io V4."""
    try:
        r = _fio_request("GET", f"{_FIO}/v4/accounts/{FRAMEIO_ACCOUNT_ID}/comments/{comment_id}", timeout=15)
        r.raise_for_status()
        data = r.json().get("data", {})
        return data if isinstance(data, dict) else None
    except Exception as e:
        logger.warning(f"Could not fetch comment {comment_id}: {e}")
        return None


def fio_comment_file_id(comment: dict | None) -> str | None:
    if not isinstance(comment, dict):
        return None
    file_id = comment.get("file_id")
    if file_id:
        return file_id

    file_obj = comment.get("file", {})
    if isinstance(file_obj, dict):
        return file_obj.get("id")
    return None


def _fio_get_v2_asset(asset_id: str) -> dict | None:
    try:
        r = _fio_request("GET", f"{_FIO}/v2/assets/{asset_id}", timeout=15)
        if r.status_code == 200:
            data = r.json()
            return data if isinstance(data, dict) else None
    except Exception as e:
        logger.warning(f"Could not fetch V2 asset {asset_id}: {e}")
    return None


def _fio_get_v2_children(asset_id: str) -> list[dict]:
    try:
        r = _fio_request("GET", f"{_FIO}/v2/assets/{asset_id}/children", timeout=15)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
    except Exception as e:
        logger.warning(f"Could not fetch V2 children for {asset_id}: {e}")
    return []


def fio_resolve_file_version_ordinal(file_id: str | None) -> int | None:
    if not file_id:
        return None

    asset = _fio_get_v2_asset(file_id)
    if not isinstance(asset, dict):
        return None

    parent_id = asset.get("parent_id")
    if not parent_id:
        return 1

    parent = _fio_get_v2_asset(parent_id)
    if not isinstance(parent, dict) or parent.get("type") != "version_stack":
        return 1

    children = _fio_get_v2_children(parent_id)
    for index, child in enumerate(children):
        if child.get("id") == file_id:
            return index + 1

    logger.warning(f"File {file_id} was not found inside version stack {parent_id}")
    return None


def fio_resolve_comment_version(comment: dict | None) -> int | None:
    return fio_resolve_file_version_ordinal(fio_comment_file_id(comment))


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_timecode(value) -> str:
    if value in (None, ""):
        return ""
    try:
        total_seconds = int(float(value))
    except (TypeError, ValueError):
        return str(value)

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def fio_get_comment_signals(asset_id: str) -> dict:
    """Get richer comment signals for review tracking."""
    out = {
        "open_comments": 0,
        "resolved_comments": 0,
        "last_comment_id": "",
        "last_comment_text": "",
        "last_comment_at": "",
        "last_comment_timecode": "",
        "last_comment_version": 0,
    }

    try:
        r = _fio_request("GET", f"{_FIO}/v4/accounts/{FRAMEIO_ACCOUNT_ID}/files/{asset_id}/comments", timeout=15)
        if r.status_code != 200:
            logger.warning(f"Comment signal fetch failed for {asset_id}: {r.status_code} {r.text[:300]}")
            return out

        payload = r.json().get("data", [])
        if isinstance(payload, dict):
            comments = [payload]
        elif isinstance(payload, list):
            comments = [item for item in payload if isinstance(item, dict)]
        else:
            comments = []

        latest = None
        latest_dt = None
        for comment in comments:
            if comment.get("completed_at"):
                out["resolved_comments"] += 1
            else:
                out["open_comments"] += 1

            sort_dt = _parse_iso_datetime(comment.get("updated_at")) or _parse_iso_datetime(comment.get("created_at"))
            if latest is None or (sort_dt and (latest_dt is None or sort_dt > latest_dt)):
                latest = comment
                latest_dt = sort_dt

        if latest:
            out["last_comment_id"] = latest.get("id", "")
            out["last_comment_text"] = (latest.get("text") or "").strip()
            out["last_comment_at"] = latest.get("updated_at") or latest.get("created_at") or ""
            out["last_comment_timecode"] = _format_timecode(latest.get("timestamp"))
            out["last_comment_version"] = fio_resolve_comment_version(latest) or 0
    except Exception as e:
        logger.warning(f"Comment signal fetch error for {asset_id}: {e}")

    return out

# =============================================
# NOTION API
# =============================================

_NOTION = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"
_NOTION_COMMENT_VERSION = "2025-09-03"


def _not_h(version: str = _NOTION_VERSION):
    return {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": version}


def _notion_first_page(filter_body: dict) -> str | None:
    body = {"filter": filter_body, "page_size": 1}
    r = requests.post(f"{_NOTION}/databases/{NOTION_DATABASE_ID}/query", headers=_not_h(), json=body, timeout=15)
    if r.status_code == 200:
        results = r.json().get("results", [])
        if results:
            return results[0]["id"]
        return None

    logger.warning(f"Notion query failed ({r.status_code}): {r.text[:300]}")
    return None


def notion_find_page(asset_id: str) -> str | None:
    """Find the Notion page for an asset, preferring an explicit asset ID property."""
    page_id = _notion_first_page({"property": PROP_ASSET_ID, "rich_text": {"contains": asset_id}})
    if page_id:
        return page_id
    return _notion_first_page({"property": PROP_FRAME_URL, "url": {"contains": asset_id}})


def notion_get_page(page_id: str) -> dict | None:
    """Fetch a Notion page to recover properties when webhook payload is minimal."""
    r = requests.get(f"{_NOTION}/pages/{page_id}", headers=_not_h(), timeout=15)
    if r.status_code == 200:
        return r.json()
    logger.warning(f"Could not fetch Notion page {page_id}: {r.status_code} {r.text[:300]}")
    return None


def _notion_prop_number(props: dict, name: str, default: int = 0) -> int:
    prop = props.get(name, {})
    value = prop.get("number") if isinstance(prop, dict) else None
    return int(value) if isinstance(value, (int, float)) else default


def _notion_prop_checkbox(props: dict, name: str, default: bool = False) -> bool:
    prop = props.get(name, {})
    value = prop.get("checkbox") if isinstance(prop, dict) else None
    return bool(value) if isinstance(value, bool) else default


def _notion_prop_plain_text(props: dict, name: str, default: str = "") -> str:
    prop = props.get(name, {})
    if not isinstance(prop, dict):
        return default
    rich_text = prop.get("rich_text", [])
    if isinstance(rich_text, list) and rich_text:
        return "".join(item.get("plain_text", "") for item in rich_text).strip()
    title = prop.get("title", [])
    if isinstance(title, list) and title:
        return "".join(item.get("plain_text", "") for item in title).strip()
    return default


def _notion_prop_select_name(props: dict, name: str, default: str = "") -> str:
    prop = props.get(name, {})
    if not isinstance(prop, dict):
        return default
    select_value = prop.get("select", {})
    if isinstance(select_value, dict) and select_value.get("name"):
        return select_value["name"]
    status_value = prop.get("status", {})
    if isinstance(status_value, dict) and status_value.get("name"):
        return status_value["name"]
    return default


def _notion_annotations(*, bold: bool = False) -> dict:
    return {
        "bold": bold,
        "italic": False,
        "strikethrough": False,
        "underline": False,
        "code": False,
        "color": "default",
    }


def _notion_rich_text_objects(value: str, chunk_size: int = 1800, *, bold: bool = False) -> list[dict]:
    text = "" if value is None else str(value)
    if text == "":
        return []
    return [
        {
            "type": "text",
            "text": {"content": text[i:i + chunk_size]},
            "annotations": _notion_annotations(bold=bold),
        }
        for i in range(0, len(text), chunk_size)
    ]


def notion_calculate_review_state(page: dict | None, versions: int, comment_signals: dict, event: str, resource_id: str = "") -> dict:
    props = page.get("properties", {}) if isinstance(page, dict) else {}
    state = {
        "client_change_round": _notion_prop_number(props, PROP_CHANGE_ROUND, 0),
        "client_review_open": _notion_prop_checkbox(props, PROP_CLIENT_REVIEW_OPEN, False),
        "last_reviewed_version": _notion_prop_number(props, PROP_LAST_REVIEWED_VERSION, 0),
        "last_comment_id": _notion_prop_plain_text(props, PROP_LAST_COMMENT_ID, ""),
    }

    # Self-heal states written by the previous round-counting logic, where the
    # round counter could grow beyond the version that actually opened a round.
    if state["last_reviewed_version"] > 0 and state["client_change_round"] > state["last_reviewed_version"]:
        state["client_change_round"] = state["last_reviewed_version"]

    if event == "file.versioned":
        state["client_review_open"] = False

    if event == "comment.created":
        incoming_comment_id = resource_id or comment_signals.get("last_comment_id", "")
        is_new_comment = bool(incoming_comment_id and incoming_comment_id != state["last_comment_id"])
        version_has_counted_round = versions <= state["last_reviewed_version"]
        if is_new_comment and not version_has_counted_round:
            state["client_change_round"] += 1
            state["last_reviewed_version"] = versions
        if is_new_comment:
            state["client_review_open"] = True

    if event in ("comment.deleted", "comment.completed"):
        if comment_signals.get("open_comments", 0) == 0:
            state["client_review_open"] = False

    if comment_signals.get("last_comment_id"):
        state["last_comment_id"] = comment_signals["last_comment_id"]

    return state


def notion_calculate_workflow_review_state(page: dict | None, status: str | None) -> dict:
    props = page.get("properties", {}) if isinstance(page, dict) else {}
    normalized_status = _normalize_text(status)
    previous_status = _normalize_text(_notion_prop_plain_text(props, PROP_LAST_WORKFLOW_STATUS, ""))
    previous_round = _notion_prop_number(props, PROP_WORKFLOW_CHANGE_ROUND, 0)
    state = {
        "workflow_change_round": previous_round,
        "workflow_review_open": _notion_prop_checkbox(props, PROP_WORKFLOW_REVIEW_OPEN, False),
        "last_workflow_status": status or "",
    }

    if not normalized_status:
        return state

    enters_review = normalized_status == _STATUS_REVIEW
    returns_to_work = normalized_status == _STATUS_CHANGES
    closes_review = normalized_status == _STATUS_DONE
    was_in_review = previous_status == _STATUS_REVIEW
    came_from_work = previous_status in {
        _STATUS_IN_PROGRESS,
        _STATUS_CHANGES,
    }
    bootstrap_first_round = not previous_status and previous_round == 0

    if enters_review:
        if not state["workflow_review_open"] and (came_from_work or bootstrap_first_round):
            state["workflow_change_round"] += 1
        state["workflow_review_open"] = True
    elif returns_to_work or closes_review:
        if was_in_review or state["workflow_review_open"]:
            state["workflow_review_open"] = False

    return state


def _notion_rich_text_prop(value: str) -> dict:
    return {"rich_text": _notion_rich_text_objects(value[:2000])}


def _format_comment_datetime(value: str) -> str:
    dt = _parse_iso_datetime(value)
    if not dt:
        return value
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def format_frameio_comment_for_notion(comment: dict, version_ordinal: int | None = None) -> list[dict]:
    text = (comment.get("text") or "").strip() or "(Comentario de Frame.io sin texto)"
    rich_text = []
    rich_text.extend(_notion_rich_text_objects("Feedback desde Frame.io", bold=True))
    rich_text.extend(_notion_rich_text_objects("\n\n" + text))

    metadata = []
    if version_ordinal:
        metadata.append(("Version", str(version_ordinal)))

    timecode = _format_timecode(comment.get("timestamp"))
    if timecode:
        metadata.append(("Timecode", timecode))

    comment_at = comment.get("updated_at") or comment.get("created_at") or ""
    if comment_at:
        metadata.append(("Fecha", _format_comment_datetime(comment_at)))

    if metadata:
        rich_text.extend(_notion_rich_text_objects("\n\n"))
        for index, (label, value) in enumerate(metadata):
            if index:
                rich_text.extend(_notion_rich_text_objects("\n"))
            rich_text.extend(_notion_rich_text_objects(f"{label}: ", bold=True))
            rich_text.extend(_notion_rich_text_objects(value))

    return rich_text


def notion_create_page_comment(page_id: str, rich_text: list[dict]) -> dict:
    body = {
        "parent": {"page_id": page_id},
        "rich_text": rich_text,
    }
    r = requests.post(f"{_NOTION}/comments", headers=_not_h(_NOTION_COMMENT_VERSION), json=body, timeout=15)
    r.raise_for_status()
    return r.json() if r.text else {}


def maybe_mirror_frameio_comment_to_notion(
    page_id: str,
    page: dict | None,
    event: str,
    resource_id: str,
    asset_id: str,
    comment: dict | None,
    comment_version: int | None = None,
):
    if not NOTION_ENABLE_FRAME_COMMENT_MIRROR:
        return "disabled"
    if event != "comment.created":
        return "skipped:not-comment-created"
    if not resource_id or not page_id:
        return "skipped:missing-context"

    props = page.get("properties", {}) if isinstance(page, dict) else {}
    if _notion_prop_plain_text(props, PROP_LAST_COMMENT_ID, "") == resource_id:
        logger.info(f"Skipping mirrored Notion comment for duplicate Frame.io comment {resource_id}")
        return "skipped:duplicate"

    if not isinstance(comment, dict):
        logger.warning(f"Skipping mirrored Notion comment for {resource_id}: comment payload unavailable")
        return "skipped:no-comment"

    notion_create_page_comment(page_id, format_frameio_comment_for_notion(comment, comment_version))
    logger.info(f"Mirrored Frame.io comment {resource_id} into Notion page {page_id}")
    return "created"


def notion_update_counts(
    page_id: str,
    versions: int,
    comments: int,
    asset_id: str | None = None,
    comment_signals: dict | None = None,
    review_state: dict | None = None,
    workflow_review_state: dict | None = None,
):
    """Set sync inputs and review signals on a Notion page."""
    props = {
        PROP_VERSIONS: {"number": versions},
        PROP_COMMENTS: {"number": comments},
    }
    if asset_id:
        props[PROP_ASSET_ID] = _notion_rich_text_prop(asset_id)

    if comment_signals:
        total_comments = max(comments, comment_signals.get("open_comments", 0) + comment_signals.get("resolved_comments", 0))
        props[PROP_COMMENTS] = {"number": total_comments}
        props[PROP_OPEN_COMMENTS] = {"number": comment_signals.get("open_comments", 0)}
        props[PROP_RESOLVED_COMMENTS] = {"number": comment_signals.get("resolved_comments", 0)}
        props[PROP_LAST_COMMENT] = _notion_rich_text_prop(comment_signals.get("last_comment_text", ""))
        props[PROP_LAST_COMMENT_ID] = _notion_rich_text_prop(comment_signals.get("last_comment_id", ""))
        props[PROP_LAST_COMMENT_TIMECODE] = _notion_rich_text_prop(comment_signals.get("last_comment_timecode", ""))
        props[PROP_LAST_COMMENT_VERSION] = {"number": int(comment_signals.get("last_comment_version", 0) or 0)}
        last_comment_at = comment_signals.get("last_comment_at", "")
        props[PROP_LAST_COMMENT_AT] = {"date": {"start": last_comment_at}} if last_comment_at else {"date": None}

    if review_state:
        props[PROP_LAST_REVIEWED_VERSION] = {"number": review_state.get("last_reviewed_version", versions)}
        props[PROP_CLIENT_REVIEW_OPEN] = {"checkbox": review_state.get("client_review_open", False)}
        props[PROP_CHANGE_ROUND] = {"number": review_state.get("client_change_round", 0)}

    if workflow_review_state:
        props[PROP_WORKFLOW_CHANGE_ROUND] = {"number": workflow_review_state.get("workflow_change_round", 0)}
        props[PROP_WORKFLOW_REVIEW_OPEN] = {"checkbox": workflow_review_state.get("workflow_review_open", False)}
        props[PROP_LAST_WORKFLOW_STATUS] = _notion_rich_text_prop(workflow_review_state.get("last_workflow_status", ""))

    r = requests.patch(f"{_NOTION}/pages/{page_id}", headers=_not_h(), json={"properties": props}, timeout=15)
    if asset_id and r.status_code == 400:
        logger.warning(f"Notion asset ID property update failed, retrying counts-only patch: {r.text[:300]}")
        for optional_prop in [
            PROP_ASSET_ID,
            PROP_OPEN_COMMENTS,
            PROP_RESOLVED_COMMENTS,
            PROP_LAST_COMMENT,
            PROP_LAST_COMMENT_ID,
            PROP_LAST_COMMENT_AT,
            PROP_LAST_COMMENT_TIMECODE,
            PROP_LAST_COMMENT_VERSION,
            PROP_LAST_REVIEWED_VERSION,
            PROP_CLIENT_REVIEW_OPEN,
            PROP_CHANGE_ROUND,
            PROP_WORKFLOW_CHANGE_ROUND,
            PROP_WORKFLOW_REVIEW_OPEN,
            PROP_LAST_WORKFLOW_STATUS,
        ]:
            props.pop(optional_prop, None)
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

    # -- Explicit Asset ID --
    for source in data_sources:
        for key in [PROP_ASSET_ID, "Frame Asset ID", "Asset ID"]:
            prop = source.get(key)
            if not prop:
                continue
            raw = None
            if isinstance(prop, str):
                raw = prop
            elif isinstance(prop, dict):
                t = prop.get("type", "")
                if t == "rich_text":
                    tx = prop.get("rich_text", [])
                    raw = "".join(item.get("plain_text", "") for item in tx) if tx else None
                elif t == "title":
                    tx = prop.get("title", [])
                    raw = "".join(item.get("plain_text", "") for item in tx) if tx else None
            if raw:
                asset_id = parse_asset_id(raw)
                if asset_id:
                    break
        if asset_id:
            break

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
    page = None

    if page_id and (not asset_id or not status):
        page = notion_get_page(page_id)
        if page:
            recovered_asset_id, recovered_status, _ = parse_notion_payload({
                "data": page.get("properties", {}),
                "page_id": page_id,
            })
            asset_id = asset_id or recovered_asset_id
            status = status or recovered_status

    if page_id and page is None:
        page = notion_get_page(page_id)

    props = page.get("properties", {}) if isinstance(page, dict) else {}
    review_source = _normalize_text(_notion_prop_select_name(props, PROP_REVIEW_SOURCE, "Auto"))
    workflow_forced = review_source == _normalize_text("Workflow")
    frameio_forced = review_source == _normalize_text("Frame.io")
    workflow_only = page_id and status and (workflow_forced or (not frameio_forced and not asset_id))

    if workflow_only:
        try:
            workflow_review_state = notion_calculate_workflow_review_state(page, status)
            notion_update_counts(
                page_id,
                _notion_prop_number(props, PROP_VERSIONS, 0),
                _notion_prop_number(props, PROP_COMMENTS, 0),
                workflow_review_state=workflow_review_state,
            )
            return jsonify({
                "success": True,
                "workflow_only": True,
                "status": status,
                "review_source": "Workflow" if workflow_forced else "Auto",
                "workflow_review_state": workflow_review_state,
            }), 200
        except Exception as e:
            logger.error(f"Workflow-only round update error: {e}")
            return jsonify({
                "error": "Workflow-only round update failed",
                "status": status,
                "details": str(e),
            }), 500

    if not asset_id:
        return jsonify({
            "skipped": True,
            "reason": "No Frame.io asset reference in this task",
            "hint": f"Fill '{PROP_ASSET_ID}' or '{PROP_FRAME_URL}' in the Notion page",
        }), 200

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
            page = notion_get_page(page_id)
            comment_signals = fio_get_comment_signals(asset_id)
            review_state = notion_calculate_review_state(page, counts["versions"], comment_signals, "notion.sync")
            notion_update_counts(
                page_id,
                counts["versions"],
                counts["comments"],
                asset_id=asset_id,
                comment_signals=comment_signals,
                review_state=review_state,
            )
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
                page = notion_get_page(found)
                comment_signals = fio_get_comment_signals(asset_id)
                review_state = notion_calculate_review_state(page, counts["versions"], comment_signals, "notion.sync")
                notion_update_counts(
                    found,
                    counts["versions"],
                    counts["comments"],
                    asset_id=asset_id,
                    comment_signals=comment_signals,
                    review_state=review_state,
                )
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
    project_id = payload.get("project", {}).get("id", "")
    resource = payload.get("resource", {})
    resource_id = resource.get("id", "")
    resource_type = resource.get("type", "")

    if project_id and FRAMEIO_PROJECT_ID and project_id != FRAMEIO_PROJECT_ID:
        return jsonify({"skipped": True, "reason": "Event for another project", "event": event, "project_id": project_id}), 200

    asset_id = ""
    comment = None
    comment_version = None
    if resource_type == "file":
        asset_id = resource_id
    elif resource_type == "comment" or event.startswith("comment."):
        comment = fio_get_comment(resource_id)
        asset_id = fio_comment_file_id(comment) or fio_get_comment_file_id(resource_id) or ""
        comment_version = fio_resolve_comment_version(comment)
    else:
        return jsonify({"skipped": True, "reason": f"Unsupported resource type '{resource_type}'", "event": event}), 200

    if not asset_id:
        return jsonify({"error": "No asset ID"}), 400

    # Find Notion page
    page_id = notion_find_page(asset_id)
    if not page_id:
        return jsonify({"warning": "No Notion page found", "asset_id": asset_id}), 200

    # Get counts and update
    try:
        counts = fio_get_counts(asset_id)
        page = notion_get_page(page_id)
        comment_signals = fio_get_comment_signals(asset_id)
        review_state = notion_calculate_review_state(page, counts["versions"], comment_signals, event, resource_id)
        notion_update_counts(
            page_id,
            counts["versions"],
            counts["comments"],
            asset_id=asset_id,
            comment_signals=comment_signals,
            review_state=review_state,
        )
        try:
            mirror_status = maybe_mirror_frameio_comment_to_notion(page_id, page, event, resource_id, asset_id, comment, comment_version)
        except Exception as e:
            mirror_status = f"error:{e}"
            logger.warning(f"Notion comment mirror failed for page {page_id}, comment {resource_id}: {e}")
        return jsonify({
            "success": True,
            "event": event,
            "page_id": page_id,
            "counts": counts,
            "comment_mirror": mirror_status,
            "review_state": {
                "client_change_round": review_state["client_change_round"],
                "client_review_open": review_state["client_review_open"],
                "last_reviewed_version": review_state["last_reviewed_version"],
            },
        }), 200
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
            "version": "2.3.2",
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
