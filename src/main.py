import argparse
import os
import sys
import subprocess
import logging
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List

from src.config import get_config
from src.history_manager import HistoryManager
from src.story_generator import StoryGenerator
from src.post_formatter import format_post_content, parse_frontmatter
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

def print_stock_status(history_mgr: HistoryManager):
    """Displays current stock and illustration status in content/."""
    content_dir = Path("content")
    posted_files = history_mgr.get_posted_files()
    all_md = sorted(content_dir.glob("*.md")) if content_dir.exists() else []
    stocked = [f for f in all_md if f.name not in posted_files]

    print("\n================ [Solve School Problems - ストック＆挿絵状況] ================")
    print(f"・配信済み記事数: {len(history_mgr.history_data.get('posts', []))} 件")
    print(f"・未配信の書き溜めストック数: {len(stocked)} 件")
    if stocked:
        for f in stocked:
            has_img = f.with_suffix(".png").exists()
            badge = "🎨[挿絵あり]" if has_img else "  [挿絵なし]"
            print(f"  - {badge} {f.name}")
    print("==============================================================================\n")

def git_sync_and_push(generated_files: List[Path], logger: logging.Logger) -> bool:
    """Commits and pushes newly generated stock/illustrations to GitHub."""
    if not generated_files:
        return True
    try:
        subprocess.run(["git", "add", "content/", "data/"], check=True)
        diff_res = subprocess.run(["git", "diff", "--staged", "--quiet"])
        if diff_res.returncode == 0:
            logger.info("No new changes in content/ or data/ to commit.")
            return True
        msg = f"feat(stock): Add {len(generated_files)} Solve School Problems asset(s) with FLUX.2 illustrations [skip ci]"
        subprocess.run(["git", "commit", "-m", msg], check=True)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=True)
        subprocess.run(["git", "push", "origin", "HEAD:main"], check=True)
        logger.info("Successfully pushed stocked stories & illustrations to GitHub!")
        return True
    except Exception as e:
        logger.error(f"Git push failed: {e}")
        return False

def count_unposted_stock(history_mgr: HistoryManager, content_dir: Path = Path("content")) -> int:
    if not content_dir.exists():
        return 0
    posted_files = history_mgr.get_posted_files()
    return sum(1 for f in content_dir.glob("*.md") if f.name not in posted_files)

def replenish_stock_if_needed(
    history_mgr: HistoryManager,
    generator: StoryGenerator,
    min_stock: int = 1,
    target_stock: int = 6,
    push_to_git: bool = True,
    logger: logging.Logger = logging.getLogger(__name__),
) -> List[Path]:
    """
    Checks how many unposted stocked stories remain in `content/`.
    1) Ensures all existing unposted stocked stories have their `.png` illustration if Draw Things is online.
    2) If remaining unposted stock <= `min_stock`, generates new stories + Draw Things illustrations up to `target_stock`.
    """
    try:
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False)
        history_mgr.history_data = history_mgr._load_history()
        history_mgr.catalog_data = history_mgr._load_catalog()
    except Exception:
        pass

    generated_assets: List[Path] = []
    content_dir = Path("content")
    posted_files = history_mgr.get_posted_files()
    dt_conn = generator.check_draw_things_connection()
    dt_online = dt_conn.get("online", False)

    # 1. Ensure existing unposted stocked stories have their .png illustration
    if dt_online and content_dir.exists():
        for md_file in sorted(content_dir.glob("*.md")):
            if md_file.name in posted_files:
                continue
            img_p = md_file.with_suffix(".png")
            if not img_p.exists():
                logger.info(f"[Auto-Replenish] Generating missing illustration for stocked story '{md_file.name}'...")
                md_text = md_file.read_text(encoding="utf-8", errors="ignore")
                meta, body = parse_frontmatter(md_text)
                pat = meta.get("pattern", "A")
                tid = meta.get("topic_id", "")
                title = meta.get("title", md_file.stem)
                topic_info = {"id": tid, "category": meta.get("category", ""), "problem_title": title}
                saved_img, _ = generator.generate_illustration(
                    pattern=pat,
                    topic=topic_info,
                    output_image_path=img_p,
                    story_body=body,
                    title=title,
                )
                if saved_img:
                    generated_assets.append(saved_img)

    # 2. Check remaining unposted stock count
    current_stock = count_unposted_stock(history_mgr, content_dir)
    logger.info(f"[Auto-Replenish Check] Unposted stocked stories: {current_stock} (trigger threshold <= {min_stock}, target = {target_stock})")

    if current_stock <= min_stock:
        needed = max(1, target_stock - current_stock)
        logger.info(f"[Auto-Replenish Triggered!] Generating {needed} new story/stories and illustration(s)...")
        sim_pattern = history_mgr.history_data.get("last_pattern")
        used_topic_ids = set()
        for idx in range(1, needed + 1):
            if sim_pattern == "A":
                next_pat = "B"
            elif sim_pattern == "B":
                next_pat = "C"
            else:
                next_pat = "A"
            sim_pattern = next_pat

            key = f"pattern_{next_pat}_topics"
            candidates = history_mgr.catalog_data.get(key, [])
            posted_topic_ids = {p.get("topic_id") for p in history_mgr.history_data.get("posts", [])}
            chosen_topic = None
            for t in candidates:
                tid = t.get("id", "")
                if tid not in posted_topic_ids and tid not in used_topic_ids and not history_mgr.find_stock_file_for_topic(tid):
                    chosen_topic = dict(t)
                    break
            if not chosen_topic:
                chosen_topic = history_mgr.get_topic(next_pat)
            tid = chosen_topic.get("id", "unknown")
            used_topic_ids.add(tid)

            logger.info(f"\n=== [Auto-Replenish {idx}/{needed}] Pattern {next_pat} | [{tid}] {chosen_topic.get('problem_title')} ===")
            raw_md, title, _ = generator.generate_story(next_pat, chosen_topic, use_local_llm=True)
            today_str = datetime.now(JST).strftime("%Y-%m-%d")
            safe_title = sanitize_filename(title)
            out_path = content_dir / f"{today_str}_pattern_{next_pat.lower()}_{tid.lower()}_{safe_title}.md"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(raw_md, encoding="utf-8")
            generated_assets.append(out_path)
            logger.info(f"Saved auto-replenished story: {out_path}")

            img_out_path = out_path.with_suffix(".png")
            saved_img, _ = generator.generate_illustration(
                pattern=next_pat,
                topic=chosen_topic,
                output_image_path=img_out_path,
                story_body=raw_md,
                title=title,
            )
            if saved_img:
                generated_assets.append(saved_img)

    if generated_assets and push_to_git:
        git_sync_and_push(generated_assets, logger)

    return generated_assets

def main():
    parser = argparse.ArgumentParser(
        description="Solve School Problems - Alternating Pedagogical & ICT Story Generator + Draw Things (FLUX.2) & Mail Poster"
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
        "--stock-count", "-n",
        type=int,
        default=0,
        help="Batch-generate N stories + FLUX.2 illustrations into content/"
    )
    parser.add_argument(
        "--auto-replenish",
        action="store_true",
        help="Automatically generate new stories + illustrations when unposted stock <= --min-stock"
    )
    parser.add_argument(
        "--min-stock",
        type=int,
        default=1,
        help="Stock threshold to trigger --auto-replenish (default: 1)"
    )
    parser.add_argument(
        "--target-stock",
        type=int,
        default=6,
        help="Target number of unposted stories to maintain on --auto-replenish (default: 6)"
    )
    parser.add_argument(
        "--generate-images",
        action="store_true",
        help="Generate missing .png illustrations for existing markdown stories in content/ via Draw Things"
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Git commit & push after generating stock or illustrations"
    )
    parser.add_argument(
        "--status-report",
        action="store_true",
        help="Show current stock & illustration status"
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
        help="Bypass schedule cooldown check and force story/image generation"
    )
    parser.add_argument(
        "--blogger-only",
        action="store_true",
        help="Send only to Blogger using the latest published story (or --file) without sending to WordPress"
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

    if args.status_report:
        print_stock_status(history_mgr)
        return 0

    generator = StoryGenerator(
        ollama_host=config.ollama_host,
        writer_model=config.writer_model,
        draw_things_host=config.draw_things_host,
    )

    if args.auto_replenish:
        replenish_stock_if_needed(
            history_mgr=history_mgr,
            generator=generator,
            min_stock=args.min_stock,
            target_stock=args.target_stock,
            push_to_git=args.push,
            logger=logger,
        )
        print_stock_status(history_mgr)
        return 0

    # Mode: Generate missing .png illustrations for existing markdown stories in content/
    if args.generate_images:
        dt_conn = generator.check_draw_things_connection()
        if not dt_conn.get("online"):
            logger.error(f"Cannot reach Draw Things HTTP API at {config.draw_things_host}: {dt_conn.get('error')}")
            return 1
        content_dir = Path("content")
        posted_files = history_mgr.get_posted_files()
        md_files = sorted(content_dir.glob("*.md")) if content_dir.exists() else []
        # Prioritize unposted stock files first; if --force or no unposted stock, process latest files
        targets = [f for f in md_files if f.name not in posted_files]
        if not targets:
            targets = md_files[-6:] if not args.force else md_files

        generated_imgs: List[Path] = []
        for md_file in targets:
            img_path = md_file.with_suffix(".png")
            if img_path.exists() and not args.force:
                logger.info(f"Illustration already exists: {img_path}")
                continue
            md_text = md_file.read_text(encoding="utf-8", errors="ignore")
            meta, body = parse_frontmatter(md_text)
            pat = meta.get("pattern", "A")
            tid = meta.get("topic_id", "")
            title = meta.get("title", md_file.stem)
            topic_info = {"id": tid, "category": meta.get("category", ""), "problem_title": title}
            saved_img, _ = generator.generate_illustration(
                pattern=pat,
                topic=topic_info,
                output_image_path=img_path,
                story_body=body,
                title=title,
            )
            if saved_img:
                generated_imgs.append(saved_img)

        if args.push and generated_imgs:
            git_sync_and_push(generated_imgs, logger)
        print_stock_status(history_mgr)
        return 0

    # Mode: Batch-generate N stories + illustrations into content/
    if args.stock_count > 0:
        generated_files: List[Path] = []
        sim_pattern = history_mgr.history_data.get("last_pattern")
        used_topic_ids = set()
        for idx in range(1, args.stock_count + 1):
            if sim_pattern == "A":
                next_pat = "B"
            elif sim_pattern == "B":
                next_pat = "C"
            else:
                next_pat = "A"
            sim_pattern = next_pat

            # Pick next unstocked topic for next_pat
            key = f"pattern_{next_pat}_topics"
            candidates = history_mgr.catalog_data.get(key, [])
            posted_topic_ids = {p.get("topic_id") for p in history_mgr.history_data.get("posts", [])}
            chosen_topic = None
            for t in candidates:
                tid = t.get("id", "")
                if tid not in posted_topic_ids and tid not in used_topic_ids and not history_mgr.find_stock_file_for_topic(tid):
                    chosen_topic = dict(t)
                    break
            if not chosen_topic:
                chosen_topic = history_mgr.get_topic(next_pat)
            tid = chosen_topic.get("id", "unknown")
            used_topic_ids.add(tid)

            logger.info(f"\n=== [{idx}/{args.stock_count}] Stocking Pattern {next_pat} | [{tid}] {chosen_topic.get('problem_title')} ===")
            raw_md, title, _ = generator.generate_story(next_pat, chosen_topic)
            today_str = datetime.now(JST).strftime("%Y-%m-%d")
            safe_title = sanitize_filename(title)
            out_path = Path("content") / f"{today_str}_pattern_{next_pat.lower()}_{tid.lower()}_{safe_title}.md"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(raw_md, encoding="utf-8")
            generated_files.append(out_path)
            logger.info(f"Saved stocked story: {out_path}")

            img_out_path = out_path.with_suffix(".png")
            saved_img, _ = generator.generate_illustration(
                pattern=next_pat,
                topic=chosen_topic,
                output_image_path=img_out_path,
                story_body=raw_md,
                title=title,
            )
            if saved_img:
                generated_files.append(saved_img)

        if args.push and generated_files:
            git_sync_and_push(generated_files, logger)
        print_stock_status(history_mgr)
        return 0

    # Cooldown check for scheduled GitHub Actions runs to prevent duplicate consecutive posts
    # when a manual run and a delayed cron schedule overlap.
    event_name = os.getenv("GITHUB_EVENT_NAME", "")
    if event_name == "schedule" and not args.force and not args.blogger_only:
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

    # If --blogger-only is set without --file, automatically pick the latest published markdown file
    target_file = args.file
    if args.blogger_only and not target_file:
        posts = history_mgr.history_data.get("posts", [])
        for entry in reversed(posts):
            candidate = entry.get("file_path")
            if candidate and Path(candidate).exists():
                target_file = candidate
                break
        if not target_file:
            content_files = sorted(Path("content").glob("*.md"))
            if content_files:
                target_file = str(content_files[-1])

    topic = {}
    # Branch 1: Publish from existing markdown file (or --blogger-only)
    if target_file:
        file_path = Path(target_file)
        if not file_path.exists():
            logger.error(f"Specified markdown file not found: {file_path}")
            return 1

        logger.info(f"Loading existing story from {file_path}...")
        with open(file_path, "r", encoding="utf-8") as f:
            raw_markdown = f.read()

        meta, _ = parse_frontmatter(raw_markdown)
        selected_pattern = meta.get("pattern", "A")
        topic_id = meta.get("topic_id", "custom_file")
        topic_category = meta.get("category", "手動投稿")
        topic = {"id": topic_id, "category": topic_category, "problem_title": meta.get("title", "")}
    else:
        # Branch 2: Auto-alternate or generate based on requested pattern
        requested_pat = None if args.pattern.lower() == "auto" else args.pattern.upper()
        selected_pattern = history_mgr.get_next_pattern(forced_pattern=requested_pat)

        topic = history_mgr.get_topic(selected_pattern, topic_id=args.topic_id)
        topic_id = topic.get("id", "unknown")
        topic_category = topic.get("category", "")

        existing_stock = history_mgr.find_stock_file_for_topic(topic_id)
        if existing_stock and not args.force:
            file_path = existing_stock
            logger.info(f"Using pre-stocked story file from content/: {file_path}")
            raw_markdown = file_path.read_text(encoding="utf-8")
        else:
            logger.info(
                f"=== Generating Story: Pattern {selected_pattern} | "
                f"Topic: [{topic_id}] {topic.get('problem_title')} ==="
            )

            raw_markdown, title, refs = generator.generate_story(selected_pattern, topic)

            # Save generated markdown to content/ directory
            today_str = datetime.now(JST).strftime("%Y-%m-%d")
            safe_title = sanitize_filename(title)
            filename = f"{today_str}_pattern_{selected_pattern.lower()}_{topic_id.lower()}_{safe_title}.md"
            content_dir = Path("content")
            content_dir.mkdir(parents=True, exist_ok=True)
            file_path = content_dir / filename

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(raw_markdown)

            logger.info(f"Generated story saved to: {file_path}")

    # Ensure sidecar illustration .png exists if Draw Things is reachable on LAN
    sidecar_png = file_path.with_suffix(".png")
    if not sidecar_png.exists():
        dt_conn = generator.check_draw_things_connection()
        if dt_conn.get("online"):
            meta, body = parse_frontmatter(raw_markdown)
            generator.generate_illustration(
                pattern=selected_pattern,
                topic=topic,
                output_image_path=sidecar_png,
                story_body=body,
                title=meta.get("title", ""),
            )

    formatted_post = format_post_content(
        raw_markdown=raw_markdown,
        default_status=post_status,
        use_jetpack_shortcodes=config.use_jetpack_shortcodes,
        file_path=str(file_path)
    )

    # Optional Preview Export
    if args.preview_html:
        preview_path = Path("preview_output.html")
        with open(preview_path, "w", encoding="utf-8") as f:
            f.write(formatted_post.content_html)
        logger.info(f"Preview HTML written to: {preview_path.resolve()}")

    # Dispatch via Mail Sender
    sender = WordPressMailSender(config)
    result = sender.send_post(formatted_post, dry_run=dry_run, blogger_only=args.blogger_only)

    if args.blogger_only:
        logger.info(f"Done. Blogger-only dispatch processed (success={result.get('success')}).")
        return 0 if result.get("success") else 1

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
