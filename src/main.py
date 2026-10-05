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
        datefmt="%H:%M:%S",
    )


def sanitize_filename(name: str) -> str:
    """Removes or replaces invalid characters for safe file naming."""
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r'[\s_—―]+', "_", name)
    return name.strip("_")[:50]


def print_stock_status(history_mgr: HistoryManager):
    """Displays current GitHub Pages library and illustration status."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    from src.site_builder import collect_all_stories

    stories = collect_all_stories(history_mgr)
    illustrated = sum(1 for s in stories if s["has_image"])
    total_catalog = sum(
        len(history_mgr.catalog_data.get(f"pattern_{p}_topics", []))
        for p in ("A", "B", "C")
    )
    used_topic_ids = {s["topic_id"] for s in stories}

    print("\n" + "=" * 78)
    print(" 【Solve School Problems（Ollama×FLUX.2）GitHub Pages 公開＆蓄積状況】")
    print("=" * 78)
    print("  ・Webサイト (GitHub Pages) : https://k518-2026.github.io/solve-school-problems/")
    print("  ・ブログメール自動投稿     : 休止中（GitHub Pages 蓄積・Web公開モード）")
    print("  ・外部生成AI API利用       : なし（Mac mini M4 完全ローカル生成）")
    print(f"  ・カタログ総テーマ数       : {total_catalog} テーマ（A:20 / B:20 / C:20）")
    print(f"  ・GitHub Pages 公開済み    : {len(stories)} 話（うち挿絵付き {illustrated} 話）")
    print(f"  ・未執筆テーマ数（第1巡）  : {max(0, total_catalog - len(used_topic_ids))} テーマ")
    print("-" * 78)

    if stories:
        print("\n[OK] 【GitHub Pages 収録エピソード（最新10件）】")
        for s in list(reversed(stories))[:10]:
            badge = "🎨[挿絵あり]" if s["has_image"] else "  [挿絵なし]"
            print(f"  [#{s['no']:02d}] {badge} [{s['topic_id']}] {s['full_title']} ({s['md_path'].name})")
    print("=" * 78 + "\n")


def git_sync_and_push(generated_files: List[Path], logger: logging.Logger) -> bool:
    """Commits and pushes newly generated stories, illustrations, and GitHub Pages (docs/) to GitHub."""
    if not generated_files:
        return True
    try:
        subprocess.run(["git", "add", "README.md", "content/", "data/", "docs/"], check=True)
        diff_res = subprocess.run(["git", "diff", "--staged", "--quiet"])
        if diff_res.returncode == 0:
            logger.info("No new changes in README.md, content/, data/, or docs/ to commit.")
            return True
        msg = f"feat(pages): Add {len(generated_files)} Solve School Problems asset(s) via Mac mini M4 & update GitHub Pages"
        subprocess.run(["git", "commit", "-m", msg], check=True)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False)
        subprocess.run(["git", "push", "origin", "HEAD:main"], check=True)
        logger.info("Successfully pushed stories, illustrations & GitHub Pages to GitHub!")
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
    Accumulates stories and Draw Things illustrations on GitHub and publishes them to GitHub Pages (`docs/`):
    1) Generates missing `.png` illustrations for existing stories in `content/` (up to 2 per run, newest first) if Draw Things is online.
    2) Generates new stories + Draw Things illustrations via Mac mini M4 Local LLM (Ollama + Draw Things FLUX.2),
       records them in history, and updates `docs/` + `README.md`.
    """
    from src.site_builder import build_github_pages, collect_all_stories

    try:
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False)
        history_mgr.history_data = history_mgr._load_history()
        history_mgr.catalog_data = history_mgr._load_catalog()
    except Exception:
        pass

    ollama_conn = generator.check_ollama_connection()
    if not ollama_conn.get("online"):
        logger.info(f"Mac mini M4 Ollama ({generator.ollama_host}) is not reachable on LAN; skipping auto-replenish.")
        return []

    generated_assets: List[Path] = []
    content_dir = Path("content")
    dt_conn = generator.check_draw_things_connection()
    dt_online = dt_conn.get("online", False)

    # 1. Backfill missing illustrations for existing stories (newest first, up to 2 per run)
    if dt_online:
        all_stories = collect_all_stories(history_mgr)
        missing_img_stories = [s for s in reversed(all_stories) if not s["has_image"]]
        for s in missing_img_stories[:2]:
            md_file = s["md_path"]
            img_p = md_file.with_suffix(".png")
            logger.info(f"[Auto-Replenish] Generating missing illustration for #{s['no']:02d} [{s['topic_id']}] '{s['full_title']}'...")
            topic_info = dict(s.get("catalog_item") or {})
            topic_info.update({
                "id": s["topic_id"],
                "category": s["category"],
                "problem_title": s["problem_title"] or s["full_title"],
                "solution_framework": s["solution_framework"],
            })
            saved_img, _ = generator.generate_illustration(
                pattern=s["pattern"],
                topic=topic_info,
                output_image_path=img_p,
                story_body=s["body_md"],
                title=s["full_title"],
            )
            if saved_img:
                generated_assets.append(saved_img)
                build_github_pages(history_mgr)
                if push_to_git:
                    git_sync_and_push([saved_img], logger)

    # 2. Determine how many new stories to generate
    blog_paused = os.environ.get("PAUSE_BLOG_AUTO_POST", "true").strip().lower() in ("1", "true", "yes")
    if blog_paused:
        needed = max(1, min_stock if min_stock > 0 else 1)
        logger.info(f"[GitHub Pages Accumulation Mode] Generating {needed} new story/stories and illustration(s) on Mac mini M4...")
    else:
        current_stock = count_unposted_stock(history_mgr, content_dir)
        logger.info(f"[Auto-Replenish Check] Unposted stocked stories: {current_stock} (trigger threshold <= {min_stock}, target = {target_stock})")
        needed = max(1, target_stock - current_stock) if current_stock <= min_stock else 0

    if needed > 0:
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
            ep_assets: List[Path] = []
            raw_md, title, _ = generator.generate_story(next_pat, chosen_topic, use_local_llm=True)
            today_str = datetime.now(JST).strftime("%Y-%m-%d")
            safe_title = sanitize_filename(title)
            out_path = content_dir / f"{today_str}_pattern_{next_pat.lower()}_{tid.lower()}_{safe_title}.md"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(raw_md, encoding="utf-8")
            generated_assets.append(out_path)
            ep_assets.append(out_path)
            logger.info(f"Saved story: {out_path}")

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
                ep_assets.append(saved_img)

            history_mgr.record_post({
                "title": title,
                "pattern": next_pat,
                "topic_id": tid,
                "category": chosen_topic.get("category", ""),
                "file_path": str(out_path).replace("\\", "/"),
                "sent_to_wp": False,
                "sent_to_blogger": False,
                "status": "github_pages",
            })

            build_github_pages(history_mgr)
            if push_to_git and ep_assets:
                git_sync_and_push(ep_assets, logger)

    return generated_assets


def main():
    parser = argparse.ArgumentParser(
        description="Solve School Problems - Local LLM (Ollama) & Draw Things (FLUX.2) Story Generator & GitHub Pages Publisher"
    )
    parser.add_argument(
        "--pattern", "-p",
        choices=["auto", "A", "B", "C", "a", "b", "c"],
        default="auto",
        help="Story pattern: 'auto' (alternates A/B/C), 'A' (Pedagogy), 'B' (ICT DX), 'C' (School Law)",
    )
    parser.add_argument(
        "--topic-id",
        default=None,
        help="Optional: Specific topic ID from catalog (e.g. A01, B02)",
    )
    parser.add_argument(
        "--file", "-f",
        default=None,
        help="Optional: Path to a specific markdown file",
    )
    parser.add_argument(
        "--stock-count", "-n",
        type=int,
        default=0,
        help="Batch-generate N stories + FLUX.2 illustrations into content/ and docs/",
    )
    parser.add_argument(
        "--auto-replenish",
        action="store_true",
        help="Automatically generate new stories + illustrations on Mac mini M4 and update GitHub Pages",
    )
    parser.add_argument(
        "--min-stock",
        type=int,
        default=5,
        help="Number of new stories per --auto-replenish run (default: 5)",
    )
    parser.add_argument(
        "--target-stock",
        type=int,
        default=5,
        help="Target number of stories on --auto-replenish (default: 5)",
    )
    parser.add_argument(
        "--generate-images",
        action="store_true",
        help="Generate missing .png illustrations for existing markdown stories in content/ via Draw Things",
    )
    parser.add_argument(
        "--build-pages",
        action="store_true",
        help="Rebuild GitHub Pages static site (docs/) and README.md from content/",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Git commit & push after generating stories, illustrations, or GitHub Pages",
    )
    parser.add_argument(
        "--status-report",
        action="store_true",
        help="Show current GitHub Pages & illustration status",
    )
    parser.add_argument(
        "--reset-history",
        action="store_true",
        help="Reset posted history in data/history.json and POSTED_STORIES.md",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="(Paused by default) Send email to WordPress/Blogger only if PAUSE_BLOG_AUTO_POST=false",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicitly run in dry-run mode",
    )
    parser.add_argument(
        "--preview-html",
        action="store_true",
        help="Export rendered HTML to preview_output.html for browser preview",
    )
    parser.add_argument(
        "--status",
        choices=["publish", "draft"],
        default=None,
        help="Override post status (publish or draft)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force regeneration",
    )
    parser.add_argument(
        "--blogger-only",
        action="store_true",
        help="Send only to Blogger",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable detailed debug logging",
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

    if args.build_pages:
        from src.site_builder import build_github_pages
        build_github_pages(history_mgr)
        if args.push:
            git_sync_and_push([Path("docs/index.html")], logger)
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
        from src.site_builder import build_github_pages, collect_all_stories
        dt_conn = generator.check_draw_things_connection()
        if not dt_conn.get("online"):
            logger.error(f"Cannot reach Draw Things HTTP API at {config.draw_things_host}: {dt_conn.get('error')}")
            return 1

        all_stories = collect_all_stories(history_mgr)
        targets = [s for s in reversed(all_stories) if not s["has_image"] or args.force]
        if args.min_stock and args.min_stock > 0 and not args.force:
            targets = targets[:args.min_stock]

        generated_imgs: List[Path] = []
        for s in targets:
            md_file = s["md_path"]
            img_path = md_file.with_suffix(".png")
            if img_path.exists() and not args.force:
                continue
            topic_info = dict(s.get("catalog_item") or {})
            topic_info.update({
                "id": s["topic_id"],
                "category": s["category"],
                "problem_title": s["problem_title"] or s["full_title"],
                "solution_framework": s["solution_framework"],
            })
            saved_img, _ = generator.generate_illustration(
                pattern=s["pattern"],
                topic=topic_info,
                output_image_path=img_path,
                story_body=s["body_md"],
                title=s["full_title"],
            )
            if saved_img:
                generated_imgs.append(saved_img)
                build_github_pages(history_mgr)
                if args.push:
                    git_sync_and_push([saved_img], logger)

        print_stock_status(history_mgr)
        return 0

    # Mode: Batch-generate N stories + illustrations into content/ and docs/
    if args.stock_count > 0:
        from src.site_builder import build_github_pages
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

            logger.info(f"\n=== [{idx}/{args.stock_count}] Generating Pattern {next_pat} | [{tid}] {chosen_topic.get('problem_title')} ===")
            ep_assets: List[Path] = []
            raw_md, title, _ = generator.generate_story(next_pat, chosen_topic, use_local_llm=True)
            today_str = datetime.now(JST).strftime("%Y-%m-%d")
            safe_title = sanitize_filename(title)
            out_path = Path("content") / f"{today_str}_pattern_{next_pat.lower()}_{tid.lower()}_{safe_title}.md"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(raw_md, encoding="utf-8")
            generated_files.append(out_path)
            ep_assets.append(out_path)
            logger.info(f"Saved story: {out_path}")

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
                ep_assets.append(saved_img)

            history_mgr.record_post({
                "title": title,
                "pattern": next_pat,
                "topic_id": tid,
                "category": chosen_topic.get("category", ""),
                "file_path": str(out_path).replace("\\", "/"),
                "sent_to_wp": False,
                "sent_to_blogger": False,
                "status": "github_pages",
            })

            build_github_pages(history_mgr)
            if args.push and ep_assets:
                git_sync_and_push(ep_assets, logger)

        print_stock_status(history_mgr)
        return 0

    # Default mode: Blog auto-posting is paused; rebuild GitHub Pages (docs/) and README.md
    blog_paused = os.environ.get("PAUSE_BLOG_AUTO_POST", "true").strip().lower() in ("1", "true", "yes")
    if blog_paused:
        from src.site_builder import build_github_pages
        logger.info("Blog email auto-posting is paused (PAUSE_BLOG_AUTO_POST=true). Building GitHub Pages (docs/) and README.md...")
        build_github_pages(history_mgr)
        if args.push:
            git_sync_and_push([Path("docs/index.html")], logger)
        print_stock_status(history_mgr)
        return 0

    post_status = args.status or config.default_status
    dry_run = args.dry_run or (not args.send)

    target_file = args.file
    if args.blogger_only and not target_file:
        posts = history_mgr.history_data.get("posts", [])
        for entry in reversed(posts):
            candidate = entry.get("file_path")
            if candidate and Path(candidate).exists():
                target_file = candidate
                break

    topic = {}
    if target_file:
        file_path = Path(target_file)
        if not file_path.exists():
            logger.error(f"Specified markdown file not found: {file_path}")
            return 1
        raw_markdown = file_path.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(raw_markdown)
        selected_pattern = meta.get("pattern", "A")
        topic_id = meta.get("topic_id", "custom_file")
        topic_category = meta.get("category", "手動投稿")
        topic = {"id": topic_id, "category": topic_category, "problem_title": meta.get("title", "")}
    else:
        requested_pat = None if args.pattern.lower() == "auto" else args.pattern.upper()
        selected_pattern = history_mgr.get_next_pattern(forced_pattern=requested_pat)
        topic = history_mgr.get_topic(selected_pattern, topic_id=args.topic_id)
        topic_id = topic.get("id", "unknown")
        topic_category = topic.get("category", "")

        existing_stock = history_mgr.find_stock_file_for_topic(topic_id)
        if existing_stock and not args.force:
            file_path = existing_stock
            raw_markdown = file_path.read_text(encoding="utf-8")
        else:
            raw_markdown, title, _ = generator.generate_story(selected_pattern, topic, use_local_llm=True)
            today_str = datetime.now(JST).strftime("%Y-%m-%d")
            safe_title = sanitize_filename(title)
            filename = f"{today_str}_pattern_{selected_pattern.lower()}_{topic_id.lower()}_{safe_title}.md"
            content_dir = Path("content")
            content_dir.mkdir(parents=True, exist_ok=True)
            file_path = content_dir / filename
            file_path.write_text(raw_markdown, encoding="utf-8")

    formatted_post = format_post_content(
        raw_markdown=raw_markdown,
        default_status=post_status,
        use_jetpack_shortcodes=config.use_jetpack_shortcodes,
        file_path=str(file_path),
    )

    if args.preview_html:
        preview_path = Path("preview_output.html")
        preview_path.write_text(formatted_post.content_html, encoding="utf-8")

    sender = WordPressMailSender(config)
    result = sender.send_post(formatted_post, dry_run=dry_run, blogger_only=args.blogger_only)

    if args.blogger_only:
        return 0 if result.get("success") else 1

    history_mgr.record_post({
        "title": formatted_post.title,
        "pattern": selected_pattern,
        "topic_id": topic_id,
        "category": topic_category,
        "file_path": str(file_path).replace("\\", "/"),
        "sent_to_wp": (not dry_run) and result.get("sent_to_wp", result.get("success", False)),
        "sent_to_blogger": (not dry_run) and result.get("sent_to_blogger", False),
        "status": post_status,
    })
    from src.site_builder import build_github_pages
    build_github_pages(history_mgr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
