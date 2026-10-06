import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))

class HistoryManager:
    """
    Manages publication history, alternations between Pattern A and Pattern B,
    and updates both history.json and POSTED_STORIES.md.
    """

    def __init__(
        self,
        history_path: Path = Path("data/history.json"),
        markdown_log_path: Path = Path("data/POSTED_STORIES.md"),
        catalog_path: Path = Path("data/topic_catalog.json")
    ):
        self.history_path = history_path
        self.markdown_log_path = markdown_log_path
        self.catalog_path = catalog_path
        self.history_data: Dict[str, Any] = self._load_history()
        self.catalog_data: Dict[str, Any] = self._load_catalog()

    def _load_history(self) -> Dict[str, Any]:
        """Loads execution history from JSON file or initializes defaults."""
        if self.history_path.exists():
            try:
                with open(self.history_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read {self.history_path}: {e}. Initializing empty history.")
        return {
            "last_pattern": None,
            "last_run_at": None,
            "total_posted": 0,
            "posts": []
        }

    def _load_catalog(self) -> Dict[str, Any]:
        """Loads topic catalog."""
        if self.catalog_path.exists():
            try:
                with open(self.catalog_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load catalog from {self.catalog_path}: {e}")
        return {"pattern_A_topics": [], "pattern_B_topics": [], "pattern_C_topics": []}

    def save_history(self) -> None:
        """Saves history data to history.json."""
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump(self.history_data, f, ensure_ascii=False, indent=2)

    def get_next_pattern(self, forced_pattern: Optional[str] = None) -> str:
        """
        Determines the next pattern to generate in cyclic order: A -> B -> C -> A.
        If forced_pattern is provided ('A', 'B', or 'C'), uses it.
        Otherwise alternates: A -> B, B -> C, C -> A, default initial: A.
        """
        if forced_pattern:
            clean = forced_pattern.strip().upper()
            if clean in ("A", "B", "C"):
                logger.info(f"Pattern manually specified: Pattern {clean}")
                return clean
            elif clean in ("PATTERN_A", "PATTERNA"):
                return "A"
            elif clean in ("PATTERN_B", "PATTERNB"):
                return "B"
            elif clean in ("PATTERN_C", "PATTERNC"):
                return "C"

        last_pattern = self.history_data.get("last_pattern")
        if last_pattern == "A":
            next_pattern = "B"
        elif last_pattern == "B":
            next_pattern = "C"
        elif last_pattern == "C":
            next_pattern = "A"
        else:
            # First time default
            next_pattern = "A"

        logger.info(f"Cyclic pattern alternation (A->B->C): Last was '{last_pattern}', Next is Pattern {next_pattern}")
        return next_pattern

    def get_topic(self, pattern: str, topic_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieves a topic definition for the given pattern ('A', 'B', or 'C').
        1) Prioritizes completely unused topics from catalog.
        2) Once all catalog topics for the pattern have been used, selects the topic
           with the lowest usage count and oldest last-used timestamp (True LRU),
           and attaches past post titles so StoryGenerator creates a fresh, non-overlapping story.
        """
        if pattern == "A":
            key = "pattern_A_topics"
        elif pattern == "B":
            key = "pattern_B_topics"
        else:
            key = "pattern_C_topics"

        topics = self.catalog_data.get(key, [])

        if not topics:
            raise ValueError(f"No topics found for pattern {pattern} in catalog.")

        posts = self.history_data.get("posts", [])

        # Track usage count and last used index for each topic_id in this pattern
        usage_count: Dict[str, int] = {}
        last_used_idx: Dict[str, int] = {}
        same_topic_titles: Dict[str, List[str]] = {}
        pattern_titles: List[str] = []

        for idx, p in enumerate(posts):
            if p.get("pattern") == pattern:
                t_title = p.get("title", "")
                if t_title:
                    pattern_titles.append(t_title)
                tid = p.get("topic_id")
                if tid:
                    usage_count[tid] = usage_count.get(tid, 0) + 1
                    last_used_idx[tid] = idx
                    if t_title:
                        same_topic_titles.setdefault(tid, []).append(t_title)

        selected = None

        # If specific topic ID requested
        if topic_id:
            for t in topics:
                if t.get("id", "").lower() == topic_id.lower():
                    selected = dict(t)
                    break
            if not selected:
                logger.warning(f"Topic ID '{topic_id}' not found. Selecting an unused/LRU topic instead.")

        if not selected:
            # Filter unused topics first
            unused_topics = [t for t in topics if usage_count.get(t.get("id", ""), 0) == 0]
            if unused_topics:
                selected = dict(unused_topics[0])
            else:
                # All topics used at least once: sort by (usage_count ASC, last_used_idx ASC)
                sorted_topics = sorted(
                    topics,
                    key=lambda t: (
                        usage_count.get(t.get("id", ""), 0),
                        last_used_idx.get(t.get("id", ""), -1)
                    )
                )
                selected = dict(sorted_topics[0])

        sel_id = selected.get("id", "")
        selected["_repeat_count"] = usage_count.get(sel_id, 0)
        selected["_same_topic_past_titles"] = same_topic_titles.get(sel_id, [])
        selected["_recent_pattern_titles"] = pattern_titles[-15:]

        return selected

    def record_post(self, post_info: Dict[str, Any]) -> None:
        """
        Records a newly generated/published post in history.json and updates POSTED_STORIES.md.
        If an entry with the same file_path already exists, updates it in-place rather than duplicating.
        """
        now_iso = datetime.now(JST).isoformat()
        pattern = post_info.get("pattern", "A")
        raw_fp = str(post_info.get("file_path", "")).replace("\\", "/")
        fp_name = Path(raw_fp).name if raw_fp else ""

        posts = self.history_data.setdefault("posts", [])
        existing_entry = None
        if fp_name:
            for p in posts:
                if Path(p.get("file_path", "")).name == fp_name:
                    existing_entry = p
                    break

        if existing_entry is not None:
            if post_info.get("title"):
                existing_entry["title"] = post_info["title"]
            if post_info.get("sent_to_wp"):
                existing_entry["sent_to_wp"] = True
            if post_info.get("sent_to_blogger"):
                existing_entry["sent_to_blogger"] = True
                existing_entry["blogger_posted_at"] = now_iso
            if post_info.get("status"):
                existing_entry["status"] = post_info["status"]
        else:
            record = {
                "title": post_info.get("title", "Untitled"),
                "pattern": pattern,
                "topic_id": post_info.get("topic_id", ""),
                "category": post_info.get("category", ""),
                "file_path": raw_fp,
                "timestamp": now_iso,
                "sent_to_wp": post_info.get("sent_to_wp", False),
                "sent_to_blogger": post_info.get("sent_to_blogger", False),
                "status": post_info.get("status", "publish"),
            }
            if record["sent_to_blogger"]:
                record["blogger_posted_at"] = now_iso
            self.history_data["last_pattern"] = pattern
            self.history_data["total_posted"] = self.history_data.get("total_posted", 0) + 1
            posts.append(record)

        self.history_data["last_run_at"] = now_iso
        self.save_history()
        self._update_markdown_log()

    def has_posted_to_blogger_today(self) -> bool:
        """
        Checks whether an article has already been posted to Blogger on the current JST calendar day
        to strictly enforce the 1-post-per-day Blogger Terms of Service / anti-spam schedule.
        """
        today_prefix = datetime.now(JST).strftime("%Y-%m-%d")
        for p in self.history_data.get("posts", []):
            if not p.get("sent_to_blogger", False):
                continue
            b_ts = str(p.get("blogger_posted_at", ""))
            if b_ts.startswith(today_prefix):
                return True
        return False

    def count_blogger_unposted_stock(self, content_dir: Path = Path("content")) -> int:
        """Counts how many accumulated stories in history.json / content/ have not yet been sent to Blogger."""
        count = 0
        seen_names = {
            "2026-09-29_pattern_a_classroom_silence.md",
            "2026-09-29_pattern_b_spreadsheet_grade_calculation.md",
        }
        for p in self.history_data.get("posts", []):
            fp_str = p.get("file_path", "")
            if not fp_str:
                continue
            fp = Path(fp_str)
            seen_names.add(fp.name)
            if not p.get("sent_to_blogger", False) and (fp.exists() or (content_dir / fp.name).exists()):
                count += 1
        if content_dir.exists():
            for md_file in content_dir.glob("*.md"):
                if md_file.name not in seen_names:
                    count += 1
        return count

    def get_next_blogger_stock_post(
        self,
        content_dir: Path = Path("content"),
        topic_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Selects the next accumulated article from GitHub to post to Blogger (1 per day at 05:00 JST):
        1) If topic_id is explicitly specified, selects the matching entry in history/content.
        2) Prioritizes newly accumulated stories (`status == 'github_pages'` and `sent_to_blogger == False`,
           e.g. #29 -> #30 -> #31 -> future weekly batches) in chronological order.
        3) Falls back to any earlier story in `posts` where `sent_to_blogger == False` (#01 -> #18).
        4) Falls back to any unrecorded `.md` file in `content/` (excluding initial sample files).
        """
        posts = self.history_data.get("posts", [])
        clean_tid = topic_id.strip().upper() if topic_id else ""

        def _resolve_path(fp_str: str) -> Optional[Path]:
            if not fp_str:
                return None
            p = Path(fp_str)
            if p.exists():
                return p
            cand = content_dir / p.name
            if cand.exists():
                return cand
            return None

        if clean_tid:
            for entry in posts:
                if str(entry.get("topic_id", "")).strip().upper() == clean_tid:
                    resolved = _resolve_path(entry.get("file_path", ""))
                    if resolved:
                        res = dict(entry)
                        res["resolved_path"] = resolved
                        return res

        # Priority 1: Newly accumulated stories (status == "github_pages" and not sent_to_blogger)
        for entry in posts:
            if not entry.get("sent_to_blogger", False) and entry.get("status") == "github_pages":
                resolved = _resolve_path(entry.get("file_path", ""))
                if resolved:
                    res = dict(entry)
                    res["resolved_path"] = resolved
                    return res

        # Priority 2: Any other story in history.json not yet sent to Blogger
        for entry in posts:
            if not entry.get("sent_to_blogger", False):
                resolved = _resolve_path(entry.get("file_path", ""))
                if resolved:
                    res = dict(entry)
                    res["resolved_path"] = resolved
                    return res

        # Priority 3: Any unrecorded .md file in content/
        if content_dir.exists():
            recorded_names = {
                "2026-09-29_pattern_a_classroom_silence.md",
                "2026-09-29_pattern_b_spreadsheet_grade_calculation.md",
            }
            for entry in posts:
                fp_str = entry.get("file_path", "")
                if fp_str:
                    recorded_names.add(Path(fp_str).name)
            for md_file in sorted(content_dir.glob("*.md")):
                if md_file.name not in recorded_names:
                    return {
                        "title": md_file.stem,
                        "file_path": str(md_file).replace("\\", "/"),
                        "resolved_path": md_file,
                        "sent_to_blogger": False,
                    }
        return None

    def _update_markdown_log(self) -> None:
        """Regenerates data/POSTED_STORIES.md markdown summary table."""
        self.markdown_log_path.parent.mkdir(parents=True, exist_ok=True)
        posts = self.history_data.get("posts", [])

        lines = [
            "# 🏫 Solve School Problems - 投稿履歴一覧 (Posted Stories)",
            "",
            "本システムが自動生成およびWordPress・Bloggerへメール投稿したストーリーの履歴ログです。",
            "**Aパターン（新米教員×先輩教員・教育学）**、**Bパターン（年配教員×若手教員・校務DX）**、**Cパターン（校長先生×教育委員会/指導主事・教育法制）** を交代（A→B→C）で配信しています。",
            "",
            f"- **総投稿数**: {len(posts)} 件",
            f"- **最終更新**: {datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S JST')}",
            f"- **前回のパターン**: パターン {self.history_data.get('last_pattern', 'なし')}",
            "",
            "| No. | 配信日時 | パターン | ID | タイトル | カテゴリ | WP / Blogger送信 | ファイル |",
            "|:---:|:---|:---:|:---:|:---|:---|:---:|:---|"
        ]

        for i, p in enumerate(posts, 1):
            ts = p.get("timestamp", "")[:16].replace("T", " ")
            pat = p.get("pattern", "A")
            if pat == "A":
                pat_badge = "📘 **A (教育学)**"
            elif pat == "B":
                pat_badge = "💻 **B (校務DX)**"
            else:
                pat_badge = "⚖️ **C (学校法制)**"
            tid = p.get("topic_id", "-")
            title = p.get("title", "-")
            cat = p.get("category", "-")
            wp_ok = p.get("sent_to_wp", False)
            bg_ok = p.get("sent_to_blogger", False)
            if wp_ok and bg_ok:
                sent = "✅ WP & Blogger済"
            elif wp_ok:
                sent = "✅ WP済 (Blogger待機)"
            elif bg_ok:
                sent = "✅ Blogger済"
            else:
                sent = "📚 GitHub蓄積 (Blogger待機)"
            fp = Path(p.get("file_path", "")).name
            lines.append(f"| {i} | {ts} | {pat_badge} | `{tid}` | {title} | {cat} | {sent} | `{fp}` |")

        lines.append("")

        with open(self.markdown_log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def get_posted_files(self) -> set:
        """Returns a set of normalized file names that have already been recorded as posted (plus initial sample files)."""
        posted = {
            "2026-09-29_pattern_a_classroom_silence.md",
            "2026-09-29_pattern_b_spreadsheet_grade_calculation.md",
        }
        for p in self.history_data.get("posts", []):
            fp = p.get("file_path", "")
            if fp:
                posted.add(Path(fp).name)
        return posted

    def find_stock_file_for_topic(self, topic_id: str, content_dir: Path = Path("content")) -> Optional[Path]:
        """
        Finds an unposted pre-stocked markdown file in content/ matching topic_id.
        """
        if not topic_id or not content_dir.exists():
            return None
        posted_names = self.get_posted_files()
        tid_lower = topic_id.strip().lower()
        for md_file in sorted(content_dir.glob("*.md")):
            if md_file.name in posted_names:
                continue
            if f"_{tid_lower}_" in md_file.name.lower() or md_file.stem.lower().endswith(f"_{tid_lower}"):
                return md_file
            try:
                head = md_file.read_text(encoding="utf-8", errors="ignore")[:800]
                if f'topic_id: "{topic_id}"' in head or f"topic_id: '{topic_id}'" in head or f"topic_id: {topic_id}" in head:
                    return md_file
            except Exception:
                continue
        return None

    def reset_history(self) -> None:
        """Resets the history file and log."""
        self.history_data = {
            "last_pattern": None,
            "last_run_at": None,
            "total_posted": 0,
            "posts": []
        }
        self.save_history()
        self._update_markdown_log()
        logger.info("History has been completely reset.")
