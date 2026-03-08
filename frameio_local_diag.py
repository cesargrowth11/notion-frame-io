#!/usr/bin/env python3
"""
Read-only local diagnostics for Frame.io.

Purpose:
- reproduce or avoid BUG-008 in a controlled way
- validate local token behavior without touching production code or deploys
- standardize local reads against Frame.io with a runtime-compatible header profile

Examples:
  python frameio_local_diag.py --check accounts
  python frameio_local_diag.py --check file --file-id <uuid>
  python frameio_local_diag.py --check comment --comment-id <uuid>
  python frameio_local_diag.py --check asset --asset-id <uuid>
  python frameio_local_diag.py --check accounts --profile bare
  python frameio_local_diag.py --check file --file-id <uuid> --token-source secret-refresh
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib import error, parse, request

DEFAULT_PROJECT = "efeonce-group"
DEFAULT_CONFIG_CANDIDATES = [".env.yaml", "env.yaml", ".env"]
DEFAULT_PROFILE = "requests"
DEFAULT_TOKEN_SOURCE = "secret-access"
REQUESTS_USER_AGENT = "python-requests/2.31.0"
DEFAULT_TIMEOUT = 30


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only local diagnostics for Frame.io.")
    parser.add_argument(
        "--check",
        choices=["accounts", "file", "comment", "asset"],
        default="accounts",
        help="Frame.io resource to read.",
    )
    parser.add_argument("--file-id", help="Required when --check file.")
    parser.add_argument("--comment-id", help="Required when --check comment.")
    parser.add_argument("--asset-id", help="Required when --check asset.")
    parser.add_argument(
        "--token-source",
        choices=["secret-access", "secret-refresh", "env-access"],
        default=DEFAULT_TOKEN_SOURCE,
        help="Where to obtain the local access token from.",
    )
    parser.add_argument(
        "--profile",
        choices=["requests", "bare"],
        default=DEFAULT_PROFILE,
        help="HTTP request profile. 'requests' mimics the runtime-compatible shape.",
    )
    parser.add_argument(
        "--config",
        help="Optional local config file. Defaults to the first existing file in .env.yaml, env.yaml, .env.",
    )
    parser.add_argument(
        "--project",
        default=os.environ.get("GCP_PROJECT") or os.environ.get("GCLOUD_PROJECT") or DEFAULT_PROJECT,
        help="GCP project used for Secret Manager.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="Request timeout in seconds.",
    )
    parser.add_argument(
        "--body-preview",
        type=int,
        default=400,
        help="Max response body preview length.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Pretty-print JSON bodies when possible.",
    )
    return parser.parse_args()


def fail(message: str, code: int = 1) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def find_config_file(explicit_path: str | None) -> Path:
    if explicit_path:
        path = Path(explicit_path)
        if not path.exists():
            fail(f"Config file not found: {path}")
        return path

    for candidate in DEFAULT_CONFIG_CANDIDATES:
        path = Path(candidate)
        if path.exists():
            return path

    fail(
        "No config file found. Expected one of: "
        + ", ".join(DEFAULT_CONFIG_CANDIDATES)
        + " or use --config."
    )


def load_config(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if ":" in line:
            key, value = line.split(":", 1)
        elif "=" in line:
            key, value = line.split("=", 1)
        else:
            continue

        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            data[key] = value
    return data


def gcloud_cmd() -> str:
    candidates = [
        shutil.which("gcloud"),
        shutil.which("gcloud.cmd"),
        r"C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    fail("gcloud command not found.")


def read_secret(secret_id: str, project: str) -> str:
    try:
        value = subprocess.check_output(
            [
                gcloud_cmd(),
                "secrets",
                "versions",
                "access",
                "latest",
                f"--secret={secret_id}",
                f"--project={project}",
            ],
            text=True,
        ).strip()
    except subprocess.CalledProcessError as exc:
        fail(f"Unable to read Secret Manager secret '{secret_id}': {exc}")
    if not value:
        fail(f"Secret '{secret_id}' is empty.")
    return value


def refresh_access_token(refresh_token: str, client_id: str, client_secret: str, timeout: int) -> str:
    token_url = "https://ims-na1.adobelogin.com/ims/token/v3"
    payload = parse.urlencode(
        {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        }
    ).encode("utf-8")
    req = request.Request(token_url, data=payload, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    status, body, _ = http_call(req, timeout)
    if status != 200:
        fail(f"Adobe IMS refresh failed with status {status}: {body[:240]}")

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        fail(f"Adobe IMS refresh returned non-JSON body: {exc}")

    access_token = data.get("access_token", "").strip()
    if not access_token:
        fail("Adobe IMS refresh returned an empty access token.")
    return access_token


def build_headers(access_token: str, profile: str) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    if profile == "requests":
        headers.update(
            {
                "User-Agent": REQUESTS_USER_AGENT,
                "Accept": "*/*",
                "Connection": "keep-alive",
            }
        )
    return headers


def http_call(req: request.Request, timeout: int) -> tuple[int, str, dict[str, str]]:
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            headers = {k: v for k, v in resp.headers.items()}
            return resp.getcode(), body, headers
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        headers = {k: v for k, v in exc.headers.items()}
        return exc.code, body, headers


def build_url(args: argparse.Namespace, config: dict[str, str]) -> str:
    account_id = config.get("FRAMEIO_ACCOUNT_ID", "")

    if args.check == "accounts":
        return "https://api.frame.io/v4/accounts"
    if args.check == "file":
        if not args.file_id:
            fail("--file-id is required when --check file.")
        if not account_id:
            fail("FRAMEIO_ACCOUNT_ID is required in the config for --check file.")
        return f"https://api.frame.io/v4/accounts/{account_id}/files/{args.file_id}"
    if args.check == "comment":
        if not args.comment_id:
            fail("--comment-id is required when --check comment.")
        if not account_id:
            fail("FRAMEIO_ACCOUNT_ID is required in the config for --check comment.")
        return f"https://api.frame.io/v4/accounts/{account_id}/comments/{args.comment_id}"
    if args.check == "asset":
        if not args.asset_id:
            fail("--asset-id is required when --check asset.")
        return f"https://api.frame.io/v2/assets/{args.asset_id}"
    fail(f"Unsupported check type: {args.check}")


def resolve_access_token(args: argparse.Namespace, config: dict[str, str]) -> tuple[str, str]:
    access_secret = config.get("SM_ACCESS_SECRET", "frameio-access-token")
    refresh_secret = config.get("SM_REFRESH_SECRET", "frameio-refresh-token")

    if args.token_source == "secret-access":
        return read_secret(access_secret, args.project), f"secret-access:{access_secret}"

    if args.token_source == "env-access":
        access = os.environ.get("FRAMEIO_ACCESS_TOKEN", "").strip()
        if not access:
            fail("FRAMEIO_ACCESS_TOKEN is not set in the current shell.")
        return access, "env-access:FRAMEIO_ACCESS_TOKEN"

    if args.token_source == "secret-refresh":
        refresh_token = read_secret(refresh_secret, args.project)
        client_id = config.get("FRAMEIO_CLIENT_ID", "").strip()
        client_secret = config.get("FRAMEIO_CLIENT_SECRET", "").strip()
        if not client_id or not client_secret:
            fail("FRAMEIO_CLIENT_ID and FRAMEIO_CLIENT_SECRET are required in the local config.")
        access = refresh_access_token(refresh_token, client_id, client_secret, args.timeout)
        return access, f"secret-refresh:{refresh_secret}"

    fail(f"Unsupported token source: {args.token_source}")


def render_body(body: str, as_json: bool, preview_limit: int) -> str:
    snippet = body[:preview_limit]
    if not as_json:
        return snippet
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return snippet
    return json.dumps(parsed, indent=2, ensure_ascii=True)[:preview_limit]


def main() -> None:
    args = parse_args()
    config_path = find_config_file(args.config)
    config = load_config(config_path)
    url = build_url(args, config)
    access_token, token_source_label = resolve_access_token(args, config)
    headers = build_headers(access_token, args.profile)

    req = request.Request(url, method="GET")
    for key, value in headers.items():
        req.add_header(key, value)

    status, body, response_headers = http_call(req, args.timeout)

    print("Frame.io Local Diagnostics")
    print(f"config={config_path}")
    print(f"check={args.check}")
    print(f"url={url}")
    print(f"token_source={token_source_label}")
    print(f"profile={args.profile}")
    print(f"status={status}")

    content_type = response_headers.get("Content-Type", "")
    if body:
        print("body_preview=")
        print(render_body(body, args.json or "json" in content_type.lower(), args.body_preview))

    if status >= 400:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
