import html
import json
import logging
import re
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.history_manager import HistoryManager
from src.post_formatter import (
    parse_frontmatter,
    HAS_MARKDOWN,
    _fallback_markdown_to_html,
    _sanitize_url,
)

if HAS_MARKDOWN:
    import markdown

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))

DOCS_DIR = Path("docs")
STORIES_DIR = DOCS_DIR / "stories"
IMAGES_DIR = DOCS_DIR / "assets" / "images"

INITIAL_SAMPLE_FILES = {
    "2026-09-29_pattern_a_classroom_silence.md",
    "2026-09-29_pattern_b_spreadsheet_grade_calculation.md",
}

PATTERN_LABELS = {
    "A": "📘 パターンA：教育相談・教育学・心理学",
    "B": "💻 パターンB：校務DX・ICT・ネットワーク",
    "C": "⚖️ パターンC：学校法制・教育委員会・学校法務",
}

PATTERN_SHORT_LABELS = {
    "A": "📘 A: 教育学・心理学",
    "B": "💻 B: 校務DX・ICT",
    "C": "⚖️ C: 学校法制・法務",
}


def _render_web_markdown(md_text: str) -> str:
    """
    Renders story Markdown to clean semantic HTML for the GitHub Pages web reader,
    preserving clickable DOI, e-Gov, and MEXT links.
    """
    cleaned = re.sub(r"^\s*\[(?:category|tags|status)[^\]]*\]\s*$", "", md_text, flags=re.MULTILINE)
    cleaned = re.sub(r"^#\s*.*?\n+", "", cleaned)
    cleaned = re.sub(
        r"^[ \t]*#+[ \t]*[【\[（(]?(?:起|承|転|結|第一部|第1部)[】\]）)]?.*$",
        "",
        cleaned,
        flags=re.MULTILINE,
    )
    cleaned = re.sub(r"^[ \t]*[-*_]{3,}[ \t]*$", "✦ ✦ ✦", cleaned, flags=re.MULTILINE)

    # Sanitize parentheses inside Markdown link URLs before conversion
    def _format_web_link(m) -> str:
        clean_label = m.group(1).replace("\\(", "(").replace("\\)", ")")
        clean_url = _sanitize_url(m.group(2))
        return f"[{clean_label}]({clean_url})"

    cleaned = re.sub(
        r"\[([^\]]+)\]\((https?://(?:[^\s\(\)]|\\?\([^\s\(\)]*\\?\))+)\)",
        _format_web_link,
        cleaned,
    )

    if HAS_MARKDOWN:
        rendered = markdown.markdown(cleaned, extensions=["extra", "sane_lists", "tables", "nl2br"])
    else:
        rendered = _fallback_markdown_to_html(cleaned)

    rendered = re.sub(
        r"<p>\s*(?:✦ ✦ ✦|◆ ◆ ◆|\* \* \*)\s*</p>|<hr\s*/?>",
        '<div class="scene-divider">✦ ✦ ✦</div>',
        rendered,
        flags=re.IGNORECASE,
    )
    rendered = re.sub(
        r"<a\b([^>]*?)>",
        r'<a\1 target="_blank" rel="noopener noreferrer">',
        rendered,
        flags=re.IGNORECASE,
    )
    return rendered


def _build_catalog_lookup(history_mgr: HistoryManager) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    for pat in ("A", "B", "C"):
        for item in history_mgr.catalog_data.get(f"pattern_{pat}_topics", []):
            tid = item.get("id", "").strip().upper()
            if tid:
                entry = dict(item)
                entry["pattern"] = pat
                lookup[tid] = entry
    return lookup


def _format_roles(pattern: str, roles: Dict[str, str]) -> str:
    if not roles:
        if pattern == "A":
            return "新米教員 × 先輩教員（指導教諭・学年主任）"
        if pattern == "B":
            return "年配教員 × 若手教員（情報担当・ICT推進）"
        return "校長先生 × 教育委員会（指導主事・管理主事）"
    if pattern == "A":
        return f"{roles.get('novice', '新米教員')} × {roles.get('senior', '先輩教員')}"
    if pattern == "B":
        return f"{roles.get('veteran', '年配教員')} × {roles.get('young', '若手教員')}"
    return f"{roles.get('principal', '校長先生')} × {roles.get('supervisor', '教育委員会・指導主事')}"


def collect_all_stories(history_mgr: Optional[HistoryManager] = None) -> List[Dict[str, Any]]:
    """
    Collects all stories in content/ in chronological creation/publication order:
    1. First in the chronological order recorded in data/history.json.
    2. Then any remaining stocked Markdown files in content/ (sorted by date prefix & mtime).
    When reversed for index.html and README.md, the newest story is always at the very top.
    """
    if history_mgr is None:
        history_mgr = HistoryManager()

    catalog_lookup = _build_catalog_lookup(history_mgr)
    ordered_files: List[Path] = []
    seen_resolved = set()

    # 1. Chronological order from data/history.json
    for post in history_mgr.history_data.get("posts", []):
        fp_str = post.get("file_path", "").replace("\\", "/")
        if not fp_str:
            continue
        p = Path(fp_str)
        if not p.exists():
            alt = Path("content") / p.name
            if alt.exists():
                p = alt
        if p.exists() and p.name not in INITIAL_SAMPLE_FILES:
            res = p.resolve()
            if res not in seen_resolved:
                ordered_files.append(p)
                seen_resolved.add(res)

    # 2. Remaining stocked files in content/, ordered chronologically by filename date prefix & mtime
    content_dir = Path("content")
    if content_dir.exists():
        unposted_candidates = []
        for md_path in content_dir.glob("*.md"):
            if md_path.name in INITIAL_SAMPLE_FILES:
                continue
            res = md_path.resolve()
            if res in seen_resolved:
                continue
            date_prefix = md_path.name[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", md_path.name) else "0000-00-00"
            mtime = md_path.stat().st_mtime
            unposted_candidates.append((date_prefix, mtime, md_path))

        unposted_candidates.sort(key=lambda item: (item[0], item[1], item[2].name))
        for _, _, md_path in unposted_candidates:
            ordered_files.append(md_path)
            seen_resolved.add(md_path.resolve())

    stories: List[Dict[str, Any]] = []
    for idx, md_path in enumerate(ordered_files, start=1):
        raw_md = md_path.read_text(encoding="utf-8", errors="ignore")
        meta, body = parse_frontmatter(raw_md)

        pattern = str(meta.get("pattern", "")).strip().upper()
        if pattern not in ("A", "B", "C"):
            if "_pattern_b_" in md_path.name.lower():
                pattern = "B"
            elif "_pattern_c_" in md_path.name.lower():
                pattern = "C"
            else:
                pattern = "A"

        topic_id = str(meta.get("topic_id", "")).strip().upper()
        if not topic_id:
            m_tid = re.search(r"_([abc]\d{2})_", md_path.name.lower())
            topic_id = m_tid.group(1).upper() if m_tid else f"{pattern}{idx:02d}"

        cat_item = catalog_lookup.get(topic_id, {})
        category = str(meta.get("category", "")).strip() or cat_item.get("category", "学校課題解決")
        full_title = str(meta.get("title", "")).strip().strip("『』\"'") or cat_item.get("problem_title", md_path.stem)
        if "――" in full_title:
            main_title, subtitle = [p.strip() for p in full_title.split("――", 1)]
        else:
            main_title, subtitle = full_title, ""

        story_id = f"ep{idx:02d}-{topic_id.lower()}"
        png_path = md_path.with_suffix(".png")
        has_image = png_path.exists()
        image_rel = f"assets/images/{story_id}.png" if has_image else ""

        roles_text = _format_roles(pattern, cat_item.get("roles", {}))
        solution_framework = cat_item.get("solution_framework", "")
        key_items = (
            cat_item.get("key_theories")
            or cat_item.get("key_technologies")
            or cat_item.get("key_laws")
            or []
        )
        keywords_str = " / ".join(key_items) if key_items else category

        # Extract short summary from catalog situation or opening paragraph of body
        summary = cat_item.get("situation", "")
        if not summary:
            first_para = re.sub(r"#+.*?\n", "", body).strip().split("\n")[0]
            summary = first_para[:110] + ("…" if len(first_para) > 110 else "")

        char_count = len(re.sub(r"\s+", "", body))
        date_str = md_path.name[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", md_path.name) else ""

        stories.append({
            "no": idx,
            "story_id": story_id,
            "topic_id": topic_id,
            "pattern": pattern,
            "pattern_label": PATTERN_LABELS.get(pattern, PATTERN_LABELS["A"]),
            "pattern_short": PATTERN_SHORT_LABELS.get(pattern, PATTERN_SHORT_LABELS["A"]),
            "category": category,
            "full_title": full_title,
            "main_title": main_title,
            "subtitle": subtitle,
            "problem_title": cat_item.get("problem_title", ""),
            "roles_text": roles_text,
            "solution_framework": solution_framework,
            "keywords_str": keywords_str,
            "summary": summary,
            "date": date_str,
            "md_path": md_path,
            "png_path": png_path if has_image else None,
            "has_image": has_image,
            "image_rel": image_rel,
            "page_rel": f"stories/{story_id}.html",
            "char_count": char_count,
            "body_md": body,
            "catalog_item": cat_item,
        })

    return stories


def _write_stylesheet(target_css: Path):
    css = """/* Solve School Problems Novel Library - GitHub Pages Stylesheet */
:root {
  --bg-primary: #f8fafc;
  --bg-secondary: #eef2f6;
  --bg-card: #ffffff;
  --bg-reader: #ffffff;
  --text-primary: #1e293b;
  --text-secondary: #475569;
  --text-muted: #64748b;
  --accent: #1d4ed8;
  --accent-soft: rgba(29, 78, 216, 0.1);
  --pat-a: #0284c7;
  --pat-b: #059669;
  --pat-c: #b45309;
  --border: #dbe3ee;
  --reader-font-size: 17.5px;
}

[data-theme="dark"] {
  --bg-primary: #0f172a;
  --bg-secondary: #1e293b;
  --bg-card: #1e293b;
  --bg-reader: #162032;
  --text-primary: #f1f5f9;
  --text-secondary: #cbd5e1;
  --text-muted: #94a3b8;
  --accent: #60a5fa;
  --accent-soft: rgba(96, 165, 250, 0.15);
  --pat-a: #38bdf8;
  --pat-b: #34d399;
  --pat-c: #fbbf24;
  --border: #334155;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  padding: 0;
  background-color: var(--bg-primary);
  color: var(--text-primary);
  font-family: "Hiragino Kaku Gothic ProN", "Yu Gothic", "Meiryo", sans-serif;
  line-height: 1.8;
  transition: background-color 0.25s ease, color 0.25s ease;
}

a {
  color: var(--accent);
  text-decoration: none;
}
a:hover {
  text-decoration: underline;
}

/* Header & Hero */
.site-header {
  background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 55%, #0f766e 100%);
  border-bottom: 1px solid var(--border);
  padding: 2.8rem 1.5rem 2.2rem;
  text-align: center;
  color: #f8fafc;
}
.site-badge {
  display: inline-block;
  font-size: 0.78rem;
  letter-spacing: 0.12em;
  padding: 0.3rem 0.95rem;
  border-radius: 999px;
  background: rgba(56, 189, 248, 0.2);
  border: 1px solid rgba(56, 189, 248, 0.45);
  color: #bae6fd;
  margin-bottom: 0.9rem;
}
.site-title {
  font-family: "Hiragino Mincho ProN", "Yu Mincho", "Noto Serif JP", serif;
  font-size: clamp(1.6rem, 3.5vw, 2.45rem);
  font-weight: 700;
  margin: 0 0 0.7rem;
  letter-spacing: 0.04em;
}
.site-subtitle {
  max-width: 840px;
  margin: 0 auto 1.5rem;
  color: #e2e8f0;
  font-size: 0.95rem;
  line-height: 1.75;
}
.stats-bar {
  display: flex;
  justify-content: center;
  gap: 1rem;
  flex-wrap: wrap;
  margin-top: 1rem;
}
.stat-pill {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 10px;
  padding: 0.45rem 1rem;
  font-size: 0.85rem;
  color: #f8fafc;
}
.stat-pill strong {
  color: #7dd3fc;
  font-size: 1.05rem;
  margin-right: 0.25rem;
}

/* Controls & Toolbar */
.container {
  max-width: 1180px;
  margin: 0 auto;
  padding: 1.8rem 1.25rem 4rem;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 0.8rem;
  align-items: center;
  justify-content: space-between;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 1rem 1.2rem;
  margin-bottom: 1.8rem;
}
.filter-group {
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem;
  align-items: center;
  flex: 1;
}
.search-input, .select-filter {
  background: var(--bg-card);
  color: var(--text-primary);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.55rem 0.85rem;
  font-size: 0.9rem;
}
.search-input {
  min-width: 220px;
  flex: 1;
}
.btn-toggle {
  background: var(--bg-card);
  color: var(--text-primary);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.5rem 0.85rem;
  font-size: 0.85rem;
  cursor: pointer;
}
.btn-toggle:hover {
  border-color: var(--accent);
}

/* Story Cards Grid with Container Queries & Media Query Fallback */
.story-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 1.4rem;
}
.story-card-wrap {
  container-type: inline-size;
}
.story-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  height: 100%;
  transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
}
.story-card:hover {
  transform: translateY(-3px);
  border-color: var(--accent);
  box-shadow: 0 10px 26px rgba(0, 0, 0, 0.12);
}
@media (min-width: 600px) {
  .story-card {
    flex-direction: row;
  }
  .card-thumb-wrap {
    width: 210px;
    flex-shrink: 0;
  }
}
@supports (container-type: inline-size) {
  @media (min-width: 600px) {
    .story-card {
      flex-direction: column;
    }
    .card-thumb-wrap {
      width: 100%;
    }
  }
  @container (min-width: 560px) {
    .story-card {
      flex-direction: row;
    }
    .card-thumb-wrap {
      width: 210px;
      flex-shrink: 0;
    }
  }
}
.card-thumb-wrap {
  position: relative;
  width: 100%;
  aspect-ratio: 1 / 1;
  background: linear-gradient(135deg, #1e3a8a 0%, #0f172a 100%);
  overflow: hidden;
}
.card-thumb {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.card-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 1.2rem;
  text-align: center;
  color: #f1f5f9;
  font-family: "Hiragino Mincho ProN", "Yu Mincho", serif;
}
.card-no-badge {
  position: absolute;
  top: 0.65rem;
  left: 0.65rem;
  background: rgba(15, 23, 42, 0.86);
  color: #7dd3fc;
  border: 1px solid rgba(125, 211, 252, 0.45);
  font-size: 0.76rem;
  font-weight: 700;
  padding: 0.2rem 0.6rem;
  border-radius: 6px;
}
.card-body {
  padding: 1.2rem 1.25rem 1.35rem;
  display: flex;
  flex-direction: column;
  flex: 1;
}
.card-pattern {
  font-size: 0.78rem;
  font-weight: 700;
  margin-bottom: 0.35rem;
}
.pat-A { color: var(--pat-a); }
.pat-B { color: var(--pat-b); }
.pat-C { color: var(--pat-c); }
.card-title {
  font-family: "Hiragino Mincho ProN", "Yu Mincho", "Noto Serif JP", serif;
  font-size: 1.14rem;
  font-weight: 700;
  margin: 0 0 0.55rem;
  line-height: 1.45;
}
.card-title a {
  color: var(--text-primary);
}
.card-title a:hover {
  color: var(--accent);
  text-decoration: none;
}
.card-framework {
  font-size: 0.78rem;
  background: var(--accent-soft);
  color: var(--accent);
  padding: 0.28rem 0.65rem;
  border-radius: 6px;
  margin-bottom: 0.7rem;
  line-height: 1.45;
}
.card-summary {
  font-size: 0.86rem;
  color: var(--text-secondary);
  margin: 0 0 1rem;
  flex: 1;
}
.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-top: 1px solid var(--border);
  padding-top: 0.75rem;
  font-size: 0.8rem;
  color: var(--text-muted);
}
.read-link {
  font-weight: 600;
  color: var(--accent);
}

/* Story Reader Page */
.reader-nav {
  position: sticky;
  top: 0;
  z-index: 50;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  padding: 0.7rem 1.25rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.6rem;
}
.reader-controls {
  display: flex;
  gap: 0.45rem;
  align-items: center;
}
.reader-container {
  max-width: 820px;
  margin: 2rem auto 4.5rem;
  padding: 2.5rem 2.2rem;
  background: var(--bg-reader);
  border: 1px solid var(--border);
  border-radius: 16px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
}
@media (max-width: 640px) {
  .reader-container {
    margin: 0.75rem;
    padding: 1.4rem 1.15rem;
  }
}
.story-meta-box {
  background: var(--bg-secondary);
  border-left: 4px solid var(--accent);
  border-radius: 8px;
  padding: 1rem 1.2rem;
  margin-bottom: 1.8rem;
  font-size: 0.9rem;
}
.story-meta-box div {
  margin-bottom: 0.35rem;
}
.story-meta-box div:last-child {
  margin-bottom: 0;
}
.story-hero-image {
  width: 100%;
  max-width: 520px;
  margin: 0 auto 2rem;
  display: block;
  border-radius: 12px;
  border: 1px solid var(--border);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.16);
}
.story-header-title {
  font-family: "Hiragino Mincho ProN", "Yu Mincho", "Noto Serif JP", serif;
  font-size: clamp(1.45rem, 3vw, 2.05rem);
  line-height: 1.45;
  margin: 0 0 1.2rem;
}
.story-content {
  font-family: "Hiragino Mincho ProN", "Yu Mincho", "Noto Serif JP", serif;
  font-size: var(--reader-font-size);
  line-height: 2.0;
  color: var(--text-primary);
}
.story-content p {
  margin: 0 0 1.45em;
  text-align: justify;
}
.story-content h2, .story-content h3, .story-content h4 {
  font-family: "Hiragino Kaku Gothic ProN", "Yu Gothic", sans-serif;
  margin-top: 2.2em;
  margin-bottom: 0.8em;
  padding-bottom: 0.35em;
  border-bottom: 2px solid var(--border);
  color: var(--accent);
}
.story-content blockquote {
  background: var(--bg-secondary);
  border-left: 4px solid var(--accent);
  margin: 1.5em 0;
  padding: 1em 1.3em;
  border-radius: 8px;
}
.story-content ul, .story-content ol {
  padding-left: 1.5em;
  margin-bottom: 1.5em;
}
.story-content li {
  margin-bottom: 0.65em;
  line-height: 1.8;
}
.story-content code {
  background: var(--bg-secondary);
  padding: 0.15em 0.4em;
  border-radius: 4px;
  font-family: Consolas, Monaco, monospace;
  font-size: 0.9em;
}
.scene-divider {
  text-align: center;
  margin: 2.4em 0;
  letter-spacing: 0.5em;
  color: var(--accent);
  font-size: 0.95rem;
}
.story-pager {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  margin-top: 3rem;
  padding-top: 1.5rem;
  border-top: 1px solid var(--border);
  flex-wrap: wrap;
}
.pager-btn {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 0.8rem 1.1rem;
  color: var(--text-primary);
  font-size: 0.9rem;
  max-width: 48%;
}
.pager-btn:hover {
  border-color: var(--accent);
  text-decoration: none;
}
.site-footer {
  text-align: center;
  padding: 2.5rem 1rem;
  border-top: 1px solid var(--border);
  color: var(--text-muted);
  font-size: 0.85rem;
}
"""
    target_css.write_text(css, encoding="utf-8")


def _build_story_page(
    story: Dict[str, Any],
    prev_story: Optional[Dict[str, Any]],
    next_story: Optional[Dict[str, Any]],
) -> str:
    rendered_body = _render_web_markdown(story["body_md"])
    hero_img_html = ""
    if story["has_image"]:
        hero_img_html = (
            f'<img class="story-hero-image" src="../{html.escape(story["image_rel"])}" '
            f'alt="{html.escape(story["full_title"])}" loading="lazy" />'
        )

    prev_html = (
        f'<a class="pager-btn" href="{html.escape(prev_story["story_id"])}.html">'
        f'← 前の作品：#{prev_story["no"]:02d} {html.escape(prev_story["main_title"])}</a>'
        if prev_story
        else "<span></span>"
    )
    next_html = (
        f'<a class="pager-btn" href="{html.escape(next_story["story_id"])}.html">'
        f'次の作品：#{next_story["no"]:02d} {html.escape(next_story["main_title"])} →</a>'
        if next_story
        else "<span></span>"
    )

    framework_line = ""
    if story.get("solution_framework"):
        framework_line = f'<div><strong>💡 解決フレームワーク：</strong>{html.escape(story["solution_framework"])}</div>'

    return f"""<!DOCTYPE html>
<html lang="ja" data-theme="light">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(story["full_title"])} | 学校のモヤモヤを解決する教育・校務DX・学校法制小説図書館</title>
  <link rel="stylesheet" href="../style.css" />
</head>
<body>
  <nav class="reader-nav">
    <a href="../index.html">← 作品一覧（Solve School Problems 図書館トップ）へ戻る</a>
    <div class="reader-controls">
      <button class="btn-toggle" onclick="setFontSize('15.5px')">文字 小</button>
      <button class="btn-toggle" onclick="setFontSize('17.5px')">文字 中</button>
      <button class="btn-toggle" onclick="setFontSize('20px')">文字 大</button>
      <button class="btn-toggle" onclick="toggleTheme()" id="themeBtn">🌙 ダーク表示</button>
    </div>
  </nav>

  <main class="reader-container">
    <div class="site-badge">EPISODE #{story["no"]:02d} ・ [{html.escape(story["topic_id"])}] {html.escape(story["pattern_label"])}</div>
    <h1 class="story-header-title">{html.escape(story["full_title"])}</h1>

    <div class="story-meta-box">
      <div><strong>🏷️ カテゴリ・領域：</strong>{html.escape(story["category"])}（{html.escape(story["keywords_str"])}）</div>
      <div><strong>👥 登場人物：</strong>{html.escape(story["roles_text"])}</div>
      {framework_line}
    </div>

    {hero_img_html}

    <article class="story-content">
      {rendered_body}
    </article>

    <div class="story-pager">
      {prev_html}
      {next_html}
    </div>
  </main>

  <footer class="site-footer">
    <p>学校のモヤモヤを解決する『教育学 × 校務DX × 学校法制』小説図書館 — Powered by Local LLM (Ollama) &amp; FLUX.2 on Mac mini M4</p>
  </footer>

  <script>
    function toggleTheme() {{
      const root = document.documentElement;
      const curr = root.getAttribute('data-theme') || 'light';
      const next = curr === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      localStorage.setItem('ssp_theme', next);
      document.getElementById('themeBtn').textContent = next === 'dark' ? '☀️ ライト表示' : '🌙 ダーク表示';
    }}
    function setFontSize(size) {{
      document.documentElement.style.setProperty('--reader-font-size', size);
      localStorage.setItem('ssp_font_size', size);
    }}
    (function initPrefs() {{
      const savedTheme = localStorage.getItem('ssp_theme');
      if (savedTheme) {{
        document.documentElement.setAttribute('data-theme', savedTheme);
        document.getElementById('themeBtn').textContent = savedTheme === 'dark' ? '☀️ ライト表示' : '🌙 ダーク表示';
      }}
      const savedSize = localStorage.getItem('ssp_font_size');
      if (savedSize) {{
        document.documentElement.style.setProperty('--reader-font-size', savedSize);
      }}
    }})();
  </script>
</body>
</html>
"""


def _build_index_page(stories: List[Dict[str, Any]]) -> str:
    total_count = len(stories)
    illustrated_count = sum(1 for s in stories if s["has_image"])
    pat_a_count = sum(1 for s in stories if s["pattern"] == "A")
    pat_b_count = sum(1 for s in stories if s["pattern"] == "B")
    pat_c_count = sum(1 for s in stories if s["pattern"] == "C")
    updated_str = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")

    cards_html_list = []
    for s in reversed(stories):
        if s["has_image"]:
            thumb_inner = (
                f'<img class="card-thumb" src="{html.escape(s["image_rel"])}" '
                f'alt="{html.escape(s["full_title"])}" loading="lazy" />'
            )
        else:
            thumb_inner = (
                f'<div class="card-placeholder">'
                f'<div style="font-size:0.78rem;color:#93c5fd;margin-bottom:0.3rem;">[{html.escape(s["topic_id"])}] {html.escape(s["pattern_short"])}</div>'
                f'<div style="font-size:1.0rem;color:#f8fafc;margin-bottom:0.35rem;font-weight:700;">{html.escape(s["main_title"])}</div>'
                f'<div style="font-size:0.76rem;color:#cbd5e1;">{html.escape(s["category"])}</div>'
                f'</div>'
            )

        search_blob = (
            f"{s['full_title']} {s['topic_id']} {s['pattern_label']} {s['category']} "
            f"{s['keywords_str']} {s['solution_framework']} {s['roles_text']} {s['summary']}"
        ).lower()

        cards_html_list.append(
            f"""      <div class="story-card-wrap" data-no="{s['no']}" data-pattern="{html.escape(s['pattern'])}" data-illustrated="{'yes' if s['has_image'] else 'no'}" data-search="{html.escape(search_blob)}">
        <article class="story-card">
          <a href="{html.escape(s['page_rel'])}" class="card-thumb-wrap">
            {thumb_inner}
            <span class="card-no-badge">#{s['no']:02d} [{html.escape(s['topic_id'])}]</span>
          </a>
          <div class="card-body">
            <div class="card-pattern pat-{html.escape(s['pattern'])}">{html.escape(s['pattern_label'])}</div>
            <h2 class="card-title"><a href="{html.escape(s['page_rel'])}">{html.escape(s['full_title'])}</a></h2>
            <div class="card-framework">🏷️ {html.escape(s['category'])} ／ {html.escape(s['keywords_str'])}</div>
            <p class="card-summary">{html.escape(s['summary'])}</p>
            <div class="card-footer">
              <span>約 {s['char_count']:,} 文字 {'🎨 挿絵あり' if s['has_image'] else ''}</span>
              <a class="read-link" href="{html.escape(s['page_rel'])}">物語を読む →</a>
            </div>
          </div>
        </article>
      </div>"""
        )

    cards_block = "\n".join(cards_html_list)

    return f"""<!DOCTYPE html>
<html lang="ja" data-theme="light">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>学校のモヤモヤを解決する『教育学 × 校務DX × 学校法制』小説図書館 | Solve School Problems</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <header class="site-header">
    <div class="site-badge">SOLVE SCHOOL PROBLEMS NOVEL ARCHIVE</div>
    <h1 class="site-title">学校のモヤモヤを解決する『教育学 × 校務DX × 学校法制』小説図書館</h1>
    <p class="site-subtitle">
      学校現場のリアルな課題を、<strong>📘 パターンA（新米教員×先輩教員：教育学・心理学）</strong>・<strong>💻 パターンB（年配教員×若手教員：校務DX・ICT）</strong>・<strong>⚖️ パターンC（校長先生×指導主事：教育法規・学校法務）</strong>の3視点で解き明かす短編教育小説コレクション。<br/>
      外部生成AI APIは一切使用せず、Mac mini M4 ローカルAI（Ollama &amp; Draw Things FLUX.2）で執筆・挿絵生成し、GitHub Pages上で公開しています。
    </p>
    <div class="stats-bar">
      <div class="stat-pill"><strong>{total_count}</strong> 収録エピソード</div>
      <div class="stat-pill"><strong>{illustrated_count}</strong> 挿絵付き作品</div>
      <div class="stat-pill">📘 A: <strong>{pat_a_count}</strong> ／ 💻 B: <strong>{pat_b_count}</strong> ／ ⚖️ C: <strong>{pat_c_count}</strong></div>
      <div class="stat-pill">最終更新: {updated_str}</div>
    </div>
  </header>

  <main class="container">
    <div class="toolbar">
      <div class="filter-group">
        <input type="search" id="searchInput" class="search-input" placeholder="タイトル・教育理論・GAS/ICT技術・教育法規・登場人物で検索..." oninput="filterCards()" />
        <select id="patternFilter" class="select-filter" onchange="filterCards()">
          <option value="">すべてのパターン（全{total_count}話）</option>
          <option value="A">📘 パターンA：教育相談・教育学・心理学 ({pat_a_count})</option>
          <option value="B">💻 パターンB：校務DX・ICT・ネットワーク ({pat_b_count})</option>
          <option value="C">⚖️ パターンC：学校法制・教育委員会 ({pat_c_count})</option>
        </select>
        <select id="imageFilter" class="select-filter" onchange="filterCards()">
          <option value="">すべて表示</option>
          <option value="yes">🎨 挿絵ありのみ ({illustrated_count})</option>
        </select>
        <select id="sortOrder" class="select-filter" onchange="sortCards()">
          <option value="desc">新しい順（#大 → #01）</option>
          <option value="asc">作品番号順（#01 → #大）</option>
        </select>
      </div>
      <button class="btn-toggle" onclick="toggleTheme()" id="themeBtn">🌙 ダーク表示</button>
    </div>

    <div class="story-grid" id="storyGrid">
{cards_block}
    </div>
  </main>

  <footer class="site-footer">
    <p>学校のモヤモヤを解決する『教育学 × 校務DX × 学校法制』小説図書館 — Generated locally on Mac mini M4 &amp; Published on GitHub Pages</p>
  </footer>

  <script>
    function filterCards() {{
      const q = (document.getElementById('searchInput').value || '').trim().toLowerCase();
      const pat = document.getElementById('patternFilter').value;
      const imgOnly = document.getElementById('imageFilter').value;
      const cards = document.querySelectorAll('.story-card-wrap');
      cards.forEach(card => {{
        const matchQ = !q || (card.getAttribute('data-search') || '').includes(q);
        const matchPat = !pat || card.getAttribute('data-pattern') === pat;
        const matchImg = !imgOnly || card.getAttribute('data-illustrated') === imgOnly;
        card.style.display = (matchQ && matchPat && matchImg) ? '' : 'none';
      }});
    }}
    function sortCards() {{
      const order = document.getElementById('sortOrder').value;
      const grid = document.getElementById('storyGrid');
      const cards = Array.from(grid.querySelectorAll('.story-card-wrap'));
      cards.sort((a, b) => {{
        const na = parseInt(a.getAttribute('data-no'), 10);
        const nb = parseInt(b.getAttribute('data-no'), 10);
        return order === 'asc' ? na - nb : nb - na;
      }});
      cards.forEach(c => grid.appendChild(c));
    }}
    function toggleTheme() {{
      const root = document.documentElement;
      const curr = root.getAttribute('data-theme') || 'light';
      const next = curr === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      localStorage.setItem('ssp_theme', next);
      document.getElementById('themeBtn').textContent = next === 'dark' ? '☀️ ライト表示' : '🌙 ダーク表示';
    }}
    (function initPrefs() {{
      const savedTheme = localStorage.getItem('ssp_theme');
      if (savedTheme) {{
        document.documentElement.setAttribute('data-theme', savedTheme);
        document.getElementById('themeBtn').textContent = savedTheme === 'dark' ? '☀️ ライト表示' : '🌙 ダーク表示';
      }}
    }})();
  </script>
</body>
</html>
"""


def _write_root_readme(stories: List[Dict[str, Any]], target_readme: Path = Path("README.md")):
    """
    Generates the root README.md containing links to the GitHub Pages web library
    and a complete index table with direct links to every novel (Web Reader + Markdown + Illustration).
    """
    pages_base = "https://k518-2026.github.io/solve-school-problems"
    illustrated_count = sum(1 for s in stories if s["has_image"])
    updated_str = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")

    lines = [
        "# 🏫 学校のモヤモヤを解決する『教育学 × 校務DX × 学校法制』小説図書館（Solve School Problems）",
        "",
        f"🌐 **Webサイト（GitHub Pages）で読む**: **[{pages_base}/]({pages_base}/)**",
        "",
        "学校現場で日々生じるリアルな悩みやトラブルを、以下の**3つのアプローチ（A・B・Cパターン）**で交互に描き出し、実在する学術論文（DOI検証済み）・国内公的ITガイドライン・e-Gov法令検索リンクとともに解決へ導く短編教育小説シリーズです。",
        "",
        "1. **📘 パターンA（新米教員 × 先輩教員）**: 教育学・教育心理学・認知科学の理論に基づく学級経営・授業改善・生徒指導の対話劇",
        "2. **💻 パターンB（年配教員 × 若手教員）**: Google Apps Script (GAS)、Python、正規表現、Wi-Fi設計など最新ICT技術による校務DXドラマ",
        "3. **⚖️ パターンC（校長先生 × 指導主事・教育委員会）**: 教育基本法、学校教育法、いじめ防止対策推進法、教育機会確保法など教育法規に基づく学校法務小説",
        "",
        "- **執筆・挿絵生成（完全ローカルAI）**: Mac mini M4 ローカル環境（Ollama `shosetsu` ＆ Draw Things `FLUX.2 [klein] 4B`）",
        "- **外部生成AI API不使用・Blogger毎日朝5時配信**: 外部の商用生成AI APIは一切使用せず、毎週金・土曜日に Mac mini M4 上で文章と挿絵を5本ずつ作成して GitHub Pages に蓄積し、毎日朝5:00（JST）に1日1本ずつ Blogger の利用規約・コンテンツポリシーを遵守して自動配信しています。",
        f"- **収録作品数**: 全 **{len(stories)}** 話（うち挿絵付き **{illustrated_count}** 話 / 最終更新: {updated_str}）",
        "",
        "---",
        "",
        "## 📚 収録教育小説一覧（新しい順・リンク集）",
        "",
        "| No. | パターン | ID | タイトル | Webページで読む | 原稿 (Markdown) | 挿絵 | カテゴリ・テーマ | 文字数 |",
        "|:---:|:---:|:---:|:---|:---:|:---:|:---:|:---|---:|",
    ]

    for s in reversed(stories):
        md_rel = urllib.parse.quote(s["md_path"].as_posix(), safe="/") if "urllib" in globals() else s["md_path"].as_posix()
        raw_md_rel = s["md_path"].as_posix()
        web_url = f"{pages_base}/{s['page_rel']}"
        img_cell = f"[🎨挿絵](<{s['png_path'].as_posix()}>)" if s["has_image"] and s["png_path"] else "—"
        lines.append(
            f"| {s['no']:02d} | {s['pattern_short']} | `{s['topic_id']}` | **[{s['full_title']}]({web_url})** | [🌐Web版]({web_url}) | [📄原稿](<{raw_md_rel}>) | {img_cell} | {s['category']} | {s['char_count']:,}字 |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 🛠️ ローカル執筆＆GitHub Pages更新コマンド（Mac mini M4連携・毎週土曜5本自動蓄積）",
        "",
        "```powershell",
        "# 5本の小説と挿絵をMac mini M4 (Ollama + Draw Things) で一括生成し、GitHub Pages (docs/) へ公開",
        "python -m src.main --auto-replenish --min-stock 5 --target-stock 5 --push",
        "",
        "# 指定話数をバッチ生成してGitHub Pagesへ反映",
        "python -m src.main --stock-count 5 --push",
        "",
        "# 既存小説のうち未生成の挿絵 (.png) を生成してGitHub Pagesへ反映",
        "python -m src.main --generate-images --push",
        "",
        "# Webサイト (docs/) と README.md のリンク一覧を再ビルド",
        "python -m src.site_builder",
        "```",
        "",
    ])

    target_readme.write_text("\n".join(lines), encoding="utf-8")


def build_github_pages(history_mgr: Optional[HistoryManager] = None) -> Dict[str, Any]:
    """
    Generates the static GitHub Pages site in `docs/` and updates root `README.md`
    from all Markdown stories and PNG illustrations in `content/`.
    """
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    STORIES_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    (DOCS_DIR / ".nojekyll").write_text("", encoding="utf-8")

    stories = collect_all_stories(history_mgr)
    _write_stylesheet(DOCS_DIR / "style.css")

    for idx, story in enumerate(stories):
        if story["has_image"] and story["png_path"] is not None:
            dest_img = IMAGES_DIR / f"{story['story_id']}.png"
            shutil.copy2(story["png_path"], dest_img)

        prev_story = stories[idx - 1] if idx > 0 else None
        next_story = stories[idx + 1] if idx + 1 < len(stories) else None
        page_html = _build_story_page(story, prev_story=prev_story, next_story=next_story)
        (STORIES_DIR / f"{story['story_id']}.html").write_text(page_html, encoding="utf-8")

    index_html = _build_index_page(stories)
    (DOCS_DIR / "index.html").write_text(index_html, encoding="utf-8")

    manifest = [
        {
            "no": s["no"],
            "story_id": s["story_id"],
            "topic_id": s["topic_id"],
            "pattern": s["pattern"],
            "title": s["full_title"],
            "category": s["category"],
            "keywords": s["keywords_str"],
            "has_image": s["has_image"],
            "url": s["page_rel"],
            "image": s["image_rel"],
            "char_count": s["char_count"],
        }
        for s in reversed(stories)
    ]
    (DOCS_DIR / "stories.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    _write_root_readme(stories, Path("README.md"))

    illustrated = sum(1 for s in stories if s["has_image"])
    logger.info(
        f"GitHub Pages site built in docs/ and README.md updated: {len(stories)} stories ({illustrated} with illustrations)"
    )
    return {
        "total_stories": len(stories),
        "illustrated_stories": illustrated,
        "docs_dir": str(DOCS_DIR.resolve()),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    build_github_pages()
