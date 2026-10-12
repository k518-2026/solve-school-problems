"""
Check if today's story has been published to Blogger and WordPress for solve-school-problems.
If not, trigger the publication workflows directly via GitHub Actions Workflow Dispatch API.
"""

import base64
import json
import logging
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST = timezone(timedelta(hours=9))
REPO = "k518-2026/solve-school-problems"

# GitHub Actions Workflow IDs
WORKFLOW_BLOGGER_ID = 379654976
WORKFLOW_WP_ID = 379654977

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("startup-publisher")


def get_github_token() -> str:
    """Retrieve GitHub Personal Access Token or credential from git-credential-manager."""
    res = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        text=True,
        capture_output=True,
    )
    for line in res.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    return ""


def get_today_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


def trigger_workflow_api(token: str, workflow_id: int, name: str) -> bool:
    url = f"https://api.github.com/repos/{REPO}/actions/workflows/{workflow_id}/dispatches"
    payload = json.dumps({"ref": "main"}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "StartupPublisher/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status in (200, 204):
                logger.info(f"Successfully triggered '{name}' on GitHub Actions!")
                return True
            else:
                logger.warning(f"Trigger {name} returned status: {resp.status}")
    except urllib.error.HTTPError as e:
        logger.error(f"HTTPError triggering {name}: {e.code} - {e.read().decode('utf-8', errors='ignore')}")
    except Exception as e:
        logger.error(f"Error triggering {name}: {e}")
    return False


def check_and_trigger():
    today_jst = get_today_jst()
    logger.info(f"Checking today's ({today_jst} JST) publication status for {REPO}...")

    repo_dir = Path("E:/GoogleAntigravity/books/solve-school-problems")
    history_file = repo_dir / "data" / "history.json"
    if not history_file.exists():
        logger.warning(f"history.json not found at {history_file}")
        return

    # Sync latest state first
    subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=str(repo_dir), capture_output=True)

    try:
        data = json.loads(history_file.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Failed to read history.json: {e}")
        return

    posts = data.get("posts", [])
    has_blogger_today = False
    has_wp_today = False

    for p in reversed(posts):
        b_at = (p.get("blogger_posted_at") or "")[:10]
        w_at = (p.get("wp_posted_at") or "")[:10]
        if b_at == today_jst:
            has_blogger_today = True
        if w_at == today_jst:
            has_wp_today = True

    token = get_github_token()
    if not token:
        logger.error("GitHub token not found. Cannot dispatch workflows.")
        return

    if not has_blogger_today:
        logger.info(f"Blogger post missing today ({today_jst}). Dispatching workflow...")
        trigger_workflow_api(token, WORKFLOW_BLOGGER_ID, "Blogger Publisher")
    else:
        logger.info(f"Blogger already posted today ({today_jst}).")

    if not has_wp_today:
        logger.info(f"WordPress post missing today ({today_jst}). Dispatching workflow...")
        trigger_workflow_api(token, WORKFLOW_WP_ID, "WordPress Publisher")
    else:
        logger.info(f"WordPress already posted today ({today_jst}).")


if __name__ == "__main__":
    check_and_trigger()
