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
        return {"pattern_A_topics": [], "pattern_B_topics": []}

    def save_history(self) -> None:
        """Saves history data to history.json."""
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump(self.history_data, f, ensure_ascii=False, indent=2)

    def get_next_pattern(self, forced_pattern: Optional[str] = None) -> str:
        """
        Determines the next pattern to generate ('A' or 'B').
        If forced_pattern is provided ('A' or 'B'), uses it.
        Otherwise alternates: if last was 'A' -> 'B', if last was 'B' -> 'A', default: 'A'.
        """
        if forced_pattern:
            clean = forced_pattern.strip().upper()
            if clean in ("A", "B"):
                logger.info(f"Pattern manually specified: Pattern {clean}")
                return clean
            elif clean in ("PATTERN_A", "PATTERNA"):
                return "A"
            elif clean in ("PATTERN_B", "PATTERNB"):
                return "B"

        last_pattern = self.history_data.get("last_pattern")
        if last_pattern == "A":
            next_pattern = "B"
        elif last_pattern == "B":
            next_pattern = "A"
        else:
            # First time default
            next_pattern = "A"

        logger.info(f"Alternating pattern: Last was '{last_pattern}', Next is Pattern {next_pattern}")
        return next_pattern

    def get_topic(self, pattern: str, topic_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieves a topic definition for the given pattern ('A' or 'B').
        Prioritizes unused topics from catalog.
        """
        key = "pattern_A_topics" if pattern == "A" else "pattern_B_topics"
        topics = self.catalog_data.get(key, [])

        if not topics:
            raise ValueError(f"No topics found for pattern {pattern} in catalog.")

        # If specific topic ID requested
        if topic_id:
            for t in topics:
                if t.get("id", "").lower() == topic_id.lower():
                    return t
            logger.warning(f"Topic ID '{topic_id}' not found. Selecting an unused topic instead.")

        # Find used topic IDs in history
        used_ids = set()
        for p in self.history_data.get("posts", []):
            if p.get("pattern") == pattern and "topic_id" in p:
                used_ids.add(p["topic_id"])

        # Filter unused topics
        unused_topics = [t for t in topics if t.get("id") not in used_ids]
        if unused_topics:
            selected = unused_topics[0]
        else:
            # All topics were used at least once, rotate back or select round-robin
            # Pick the one least recently used
            selected = topics[len(self.history_data.get("posts", [])) % len(topics)]

        return selected

    def record_post(self, post_info: Dict[str, Any]) -> None:
        """
        Records a newly generated/published post in history.json and updates POSTED_STORIES.md.
        """
        now_iso = datetime.now(JST).isoformat()
        pattern = post_info.get("pattern", "A")

        record = {
            "title": post_info.get("title", "Untitled"),
            "pattern": pattern,
            "topic_id": post_info.get("topic_id", ""),
            "category": post_info.get("category", ""),
            "file_path": str(post_info.get("file_path", "")),
            "timestamp": now_iso,
            "sent_to_wp": post_info.get("sent_to_wp", False),
            "status": post_info.get("status", "publish")
        }

        self.history_data["last_pattern"] = pattern
        self.history_data["last_run_at"] = now_iso
        self.history_data["total_posted"] = self.history_data.get("total_posted", 0) + 1
        self.history_data.setdefault("posts", []).append(record)

        self.save_history()
        self._update_markdown_log()

    def _update_markdown_log(self) -> None:
        """Regenerates data/POSTED_STORIES.md markdown summary table."""
        self.markdown_log_path.parent.mkdir(parents=True, exist_ok=True)
        posts = self.history_data.get("posts", [])

        lines = [
            "# 🏫 Solve School Problems - 投稿履歴一覧 (Posted Stories)",
            "",
            "本システムが自動生成およびWordPressへメール投稿したストーリーの履歴ログです。",
            "**Aパターン（新米教員×先輩教員の教育相談・学術論文知見）** と **Bパターン（年配教員×若手教員の校務ICT・ネットワーク技術解決）** を交代で配信しています。",
            "",
            f"- **総投稿数**: {len(posts)} 件",
            f"- **最終更新**: {datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S JST')}",
            f"- **前回のパターン**: パターン {self.history_data.get('last_pattern', 'なし')}",
            "",
            "| No. | 配信日時 | パターン | ID | タイトル | カテゴリ | WP送信 | ファイル |",
            "|:---:|:---|:---:|:---:|:---|:---|:---:|:---|"
        ]

        for i, p in enumerate(posts, 1):
            ts = p.get("timestamp", "")[:16].replace("T", " ")
            pat = p.get("pattern", "A")
            pat_badge = "📘 **A (教育学)**" if pat == "A" else "💻 **B (校務DX)**"
            tid = p.get("topic_id", "-")
            title = p.get("title", "-")
            cat = p.get("category", "-")
            sent = "✅ 済" if p.get("sent_to_wp") else "📝 下書き/DryRun"
            fp = Path(p.get("file_path", "")).name
            lines.append(f"| {i} | {ts} | {pat_badge} | `{tid}` | {title} | {cat} | {sent} | `{fp}` |")

        lines.append("")

        with open(self.markdown_log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

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
