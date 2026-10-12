"""
Check if today's story has been published to Blogger and WordPress for solve-school-problems.
If not, trigger the publication workflows via push event or GitHub Actions dispatch.
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

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("startup-publisher")


def get_today_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


def check_and_trigger():
    today_jst = get_today_jst()
    logger.info(f"Checking today's ({today_jst} JST) publication status for {REPO}...")

    repo_dir = Path("E:/GoogleAntigravity/books/solve-school-problems")
    if not repo_dir.exists():
        logger.error(f"Repository directory not found: {repo_dir}")
        return

    # Check history.json
    history_file = repo_dir / "data" / "history.json"
    if not history_file.exists():
        logger.warning(f"history.json not found at {history_file}")
        return

    try:
        data = json.loads(history_file.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Failed to read history.json: {e}")
        return

    last_run_at = (data.get("last_run_at") or "")[:10]
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

    targets_needed = []
    if not has_blogger_today:
        targets_needed.append("blogger")
    if not has_wp_today:
        targets_needed.append("wordpress")

    if not targets_needed:
        logger.info(f"Both Blogger and WordPress already published today ({today_jst}). Nothing to do.")
        return

    logger.info(f"Missing publications today for: {targets_needed}. Triggering via trigger_publish.ps1...")
    target_arg = "all" if len(targets_needed) == 2 else targets_needed[0]

    ps1_script = repo_dir / "trigger_publish.ps1"
    res = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1_script), "-Target", target_arg],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
    )
    if res.returncode == 0:
        logger.info(f"Successfully triggered publication for {target_arg}!")
    else:
        logger.error(f"Failed to trigger publication: {res.stderr}")


if __name__ == "__main__":
    check_and_trigger()
