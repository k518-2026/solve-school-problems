import argparse
import os
import sys
import logging
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.config import get_config
from src.history_manager import HistoryManager
from src.story_generator import StoryGenerator
from src.post_formatter import format_post_content
from src.mail_sender import WordPressMailSender

JST = timezone(timedelta(hours=9))

def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )

def sanitize_filename(name: str) -> str:
    """Removes or replaces invalid characters for safe file naming."""
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r'[\s_—―]+', "_", name)
    return name.strip("_")[:50]

def main():
    parser = argparse.ArgumentParser(
        description="Solve School Problems - Alternating Pedagogical & ICT Story Generator and WordPress Mail Poster"
    )
    parser.add_argument(
        "--pattern", "-p",
        choices=["auto", "A", "B", "C", "a", "b", "c"],
        default="auto",
        help="Story pattern: 'auto' (alternates A/B/C based on history), 'A' (Novice x Senior / Pedagogy), 'B' (Veteran x Young / ICT DX), 'C' (Principal x Board of Ed / School Law)"
    )
    parser.add_argument(
        "--topic-id",
        default=None,
        help="Optional: Specific topic ID from catalog (e.g. A01, B02)"
    )
    parser.add_argument(
        "--file", "-f",
        default=None,
        help="Optional: Path to a specific markdown file to publish directly without generating"
    )
    parser.add_argument(
        "--reset-history",
        action="store_true",
        help="Reset posted history in data/history.json and POSTED_STORIES.md"
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually send the email to WordPress via SMTP (if omitted, runs in dry-run mode)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicitly run in dry-run mode (no email sent, history still updated if requested)"
    )
    parser.add_argument(
        "--preview-html",
        action="store_true",
        help="Export rendered HTML to preview_output.html for browser preview"
    )
    parser.add_argument(
        "--status",
        choices=["publish", "draft"],
        default=None,
        help="Override WordPress post status (publish or draft)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass schedule cooldown check and force story generation"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable detailed debug logging"
    )

    args = parser.parse_args()
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    config = get_config()
    history_mgr = HistoryManager()

    if args.reset_history:
        history_mgr.reset_history()
        logger.info("History reset complete.")
        return 0

    # Cooldown check for scheduled GitHub Actions runs to prevent duplicate consecutive posts
    # when a manual run and a delayed cron schedule overlap.
    event_name = os.getenv("GITHUB_EVENT_NAME", "")
    if event_name == "schedule" and not args.force:
        last_run_str = history_mgr.history_data.get("last_run_at")
        if last_run_str:
            try:
                last_dt = datetime.fromisoformat(last_run_str)
                now_dt = datetime.now(JST)
                elapsed_minutes = (now_dt - last_dt).total_seconds() / 60.0
                if 0 <= elapsed_minutes < 120:
                    logger.info(
                        f"Skipping scheduled run: A story was already published {elapsed_minutes:.1f} minutes ago "
                        f"({last_run_str}). Preventing duplicate consecutive posts."
                    )
                    return 0
            except Exception as e:
                logger.warning(f"Could not parse last_run_at timestamp '{last_run_str}': {e}")

    post_status = args.status or config.default_status
    dry_run = args.dry_run or (not args.send)

    # Branch 1: Publish from existing markdown file
    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            logger.error(f"Specified markdown file not found: {file_path}")
            return 1

        logger.info(f"Loading existing story from {file_path}...")
        with open(file_path, "r", encoding="utf-8") as f:
            raw_markdown = f.read()

        formatted_post = format_post_content(
            raw_markdown=raw_markdown,
            default_status=post_status,
            use_jetpack_shortcodes=config.use_jetpack_shortcodes
        )
        selected_pattern = formatted_post.pattern
        topic_id = "custom_file"
        topic_category = "手動投稿"
    else:
        # Branch 2: Auto-alternate or generate based on requested pattern
        requested_pat = None if args.pattern.lower() == "auto" else args.pattern.upper()
        selected_pattern = history_mgr.get_next_pattern(forced_pattern=requested_pat)

        topic = history_mgr.get_topic(selected_pattern, topic_id=args.topic_id)
        topic_id = topic.get("id", "unknown")
        topic_category = topic.get("category", "")

        logger.info(
            f"=== Generating Story: Pattern {selected_pattern} | "
            f"Topic: [{topic_id}] {topic.get('problem_title')} ==="
        )

        generator = StoryGenerator()
        raw_markdown, title, refs = generator.generate_story(selected_pattern, topic)

        # Save generated markdown to content/ directory
        today_str = datetime.now(JST).strftime("%Y-%m-%d")
        safe_title = sanitize_filename(title)
        filename = f"{today_str}_pattern_{selected_pattern.lower()}_{safe_title}.md"
        content_dir = Path("content")
        content_dir.mkdir(parents=True, exist_ok=True)
        file_path = content_dir / filename

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(raw_markdown)

        logger.info(f"Generated story saved to: {file_path}")

        formatted_post = format_post_content(
            raw_markdown=raw_markdown,
            default_status=post_status,
            use_jetpack_shortcodes=config.use_jetpack_shortcodes
        )

    # Optional Preview Export
    if args.preview_html:
        preview_path = Path("preview_output.html")
        with open(preview_path, "w", encoding="utf-8") as f:
            f.write(formatted_post.content_html)
        logger.info(f"Preview HTML written to: {preview_path.resolve()}")

    # Dispatch via Mail Sender
    sender = WordPressMailSender(config)
    result = sender.send_post(formatted_post, dry_run=dry_run)

    # Update history
    history_mgr.record_post({
        "title": formatted_post.title,
        "pattern": selected_pattern,
        "topic_id": topic_id,
        "category": topic_category,
        "file_path": str(file_path),
        "sent_to_wp": (not dry_run) and result.get("sent_to_wp", result.get("success", False)),
        "sent_to_blogger": (not dry_run) and result.get("sent_to_blogger", False),
        "status": post_status
    })

    logger.info(f"Done. Pattern {selected_pattern} story processed successfully.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
