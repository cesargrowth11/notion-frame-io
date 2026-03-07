#!/usr/bin/env python3
"""
Seed tokens into Secret Manager, update .env.yaml, redeploy, and test.

Usage:
  python seed_and_deploy.py <access_token> <refresh_token>

Or with environment variables:
  export NEW_ACCESS_TOKEN="eyJ..."
  export NEW_REFRESH_TOKEN="eyJ..."
  python seed_and_deploy.py
"""

import os
import re
import sys
import subprocess

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PROJECT = "efeonce-group"
REGION = "us-central1"
FUNCTION_NAME = "notion-frameio-sync"
ENV_YAML = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.yaml")
ACCESS_SECRET = "frameio-access-token"
REFRESH_SECRET = "frameio-refresh-token"

TEST_PAYLOAD = (
    '{"data":{'
    '"URL Frame.io":{"type":"url","url":"https://next.frame.io/project/5749d3e4-732b-4fc3-b5b2-052081563228/view/7f289cd4-b30e-4103-91c8-48042497683a"},'
    '"Estado":{"type":"status","status":{"name":"En curso"}}'
    '}}'
)
FUNCTION_URL = f"https://{REGION}-{PROJECT}.cloudfunctions.net/{FUNCTION_NAME}"


def run(cmd, description, check=True):
    print(f"\n--- {description} ---")
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())
    if check and result.returncode != 0:
        print(f"FAILED (exit {result.returncode})")
        sys.exit(1)
    return result


def update_env_yaml(access_token):
    """Replace FRAMEIO_ACCESS_TOKEN value in .env.yaml."""
    with open(ENV_YAML, "r", encoding="utf-8") as f:
        content = f.read()

    # Match the key with any value (quoted or unquoted, single or multi-line JWT)
    pattern = r'(FRAMEIO_ACCESS_TOKEN:\s*).*'
    replacement = f'\\1"{access_token}"'
    new_content, count = re.subn(pattern, replacement, content, count=1)

    if count == 0:
        print(f"WARNING: Could not find FRAMEIO_ACCESS_TOKEN in {ENV_YAML}")
        return

    with open(ENV_YAML, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"Updated FRAMEIO_ACCESS_TOKEN in {ENV_YAML}")


def main():
    # Resolve tokens from args or env
    if len(sys.argv) >= 3:
        access_token = sys.argv[1]
        refresh_token = sys.argv[2]
    else:
        access_token = os.environ.get("NEW_ACCESS_TOKEN", "")
        refresh_token = os.environ.get("NEW_REFRESH_TOKEN", "")

    if not access_token or not refresh_token:
        print("Usage: python seed_and_deploy.py <access_token> <refresh_token>")
        print("  or set NEW_ACCESS_TOKEN and NEW_REFRESH_TOKEN env vars")
        sys.exit(1)

    print(f"Access token: {access_token[:40]}...")
    print(f"Refresh token: {refresh_token[:40]}...")

    # 1. Seed access token into Secret Manager
    run(
        f'echo -n "{access_token}" | gcloud secrets versions add {ACCESS_SECRET} --data-file=- --project={PROJECT}',
        "Seed access token into Secret Manager",
    )

    # 2. Seed refresh token into Secret Manager
    run(
        f'echo -n "{refresh_token}" | gcloud secrets versions add {REFRESH_SECRET} --data-file=- --project={PROJECT}',
        "Seed refresh token into Secret Manager",
    )

    # 3. Update .env.yaml
    print(f"\n--- Update .env.yaml ---")
    update_env_yaml(access_token)

    # 4. Deploy
    deploy_cmd = (
        f"gcloud functions deploy {FUNCTION_NAME} "
        f"--gen2 --region={REGION} --runtime=python312 "
        f'--source="{os.path.dirname(os.path.abspath(__file__))}" '
        f"--entry-point=sync_status "
        f"--trigger-http --allow-unauthenticated "
        f'--env-vars-file="{ENV_YAML}" '
        f"--memory=256MB --timeout=60s "
        f"--min-instances=0 --max-instances=10 "
        f"--project={PROJECT}"
    )
    run(deploy_cmd, "Deploy Cloud Function", check=True)

    # 5. Health check
    run(f'curl -s {FUNCTION_URL}', "Health check")

    # 6. Test webhook
    run(
        f"curl -s -X POST {FUNCTION_URL}/notion-webhook "
        f"-H 'Content-Type: application/json' "
        f"-d '{TEST_PAYLOAD}'",
        "Test notion-webhook",
        check=False,
    )

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
