import re
import html
import urllib.parse
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any

# Try importing yaml, with fallback to built-in parser
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# Try importing markdown, with fallback to built-in converter
try:
    import markdown
    HAS_MARKDOWN = True
except ImportError:
    HAS_MARKDOWN = False

@dataclass
class FormattedPost:
    title: str
    pattern: str = "A"
    categories: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    status: str = "publish"
    content_raw: str = ""
    content_html: str = ""
    content_plain: str = ""

def _fallback_yaml_parser(text: str) -> Dict[str, Any]:
    """Lightweight fallback YAML parser for simple frontmatter dictionaries."""
    data: Dict[str, Any] = {}
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            if val.startswith("[") and val.endswith("]"):
                items = [item.strip().strip("'\"") for item in val[1:-1].split(",") if item.strip()]
                data[key] = items
            else:
                data[key] = val
    return data

def _sanitize_url(url: str) -> str:
    """Safely percent-encodes non-ASCII characters and parentheses in URLs while preserving URL structure."""
    url = url.replace("\\(", "(").replace("\\)", ")")
    try:
        parts = urllib.parse.urlsplit(url)
        # Omit '(' and ')' from safe so they become %28 and %29, preventing Markdown/WP breakage on DOIs like 10.1016/S0079-7421(02)80005-6
        path = urllib.parse.quote(urllib.parse.unquote(parts.path), safe="/:@&=+$,-_.!~*'")
        query = urllib.parse.quote(urllib.parse.unquote(parts.query), safe="/:@&=+$,-_.!~*'*?")
        fragment = urllib.parse.quote(urllib.parse.unquote(parts.fragment), safe="/:@&=+$,-_.!~*'")
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, fragment))
    except Exception:
        return url

def _format_inline_markdown(text: str) -> str:
    """Formats inline bold, italic, code, and links ensuring target='_blank'."""
    text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.*?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`(.*?)`", r'<code style="background-color: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-family: Consolas, monospace; font-size: 0.9em; color: #0f172a;">\1</code>', text)
    
    # 1. Convert standard Markdown links: [text](url) -> <a ... target="_blank">
    # Supports balanced parentheses and escaped parentheses inside URLs (e.g., Elsevier DOIs)
    def _md_link_replacer(match):
        label = match.group(1).replace("\\(", "(").replace("\\)", ")")
        raw_url = match.group(2)
        safe_url = _sanitize_url(raw_url)
        return f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer" style="color: #2563eb; text-decoration: underline;">{label}</a>'

    text = re.sub(
        r"\[([^\]]+)\]\((https?://(?:[^\s\(\)]|\\?\([^\s\(\)]*\\?\))+)\)",
        _md_link_replacer,
        text
    )
    
    # 2. Convert remaining raw URLs that are not already inside an <a>...</a> element
    parts = re.split(r'(<a\s+[^>]*>.*?</a>)', text, flags=re.DOTALL)
    def _url_replacer(match):
        prefix = match.group(1)
        raw_url = match.group(2)
        safe_url = _sanitize_url(raw_url)
        display_url = raw_url.replace("\\(", "(").replace("\\)", ")")
        return f'{prefix}<a href="{safe_url}" target="_blank" rel="noopener noreferrer" style="color: #2563eb; text-decoration: underline;">{display_url}</a>'

    for idx in range(0, len(parts), 2):
        parts[idx] = re.sub(
            r'(^|[\s（\(「『：:])(https?://(?:[^\s\(\)<>\"\'\]]|\\?\([^\s\(\)]*\\?\))+)',
            _url_replacer,
            parts[idx]
        )
    text = "".join(parts)

    # 3. Ensure any existing <a> tags have target="_blank" and rel="noopener noreferrer"
    def _ensure_target_blank(match):
        a_tag = match.group(0)
        if 'target=' not in a_tag:
            a_tag = a_tag[:-1] + ' target="_blank">'
        if 'rel=' not in a_tag:
            a_tag = a_tag[:-1] + ' rel="noopener noreferrer">'
        return a_tag

    text = re.sub(r'<a\s+[^>]+>', _ensure_target_blank, text)
    return text

def _fallback_markdown_to_html(md_text: str) -> str:
    """
    Lightweight fallback Markdown to HTML converter.
    Supports headings, blockquotes, lists, code blocks, and tables.
    Never produces bare <hr> tags that might cause email clients to truncate content.
    """
    lines = md_text.splitlines()
    html_lines = []
    in_code_block = False
    code_block_lines = []
    in_list = False
    in_table = False
    table_rows: List[List[str]] = []

    def flush_table():
        nonlocal in_table, table_rows
        if not table_rows:
            in_table = False
            return
        tbl_html = [
            '<table style="width: 100%; border-collapse: collapse; margin: 1.5em 0; font-size: 14px; line-height: 1.7; background-color: #ffffff; border: 1px solid #cbd5e1;">'
        ]
        has_header = False
        start_idx = 0
        if len(table_rows) >= 2 and all(c.strip().replace(":", "").replace("-", "") == "" for c in table_rows[1]):
            has_header = True
            tbl_html.append('  <thead>\n    <tr style="background-color: #f8fafc;">')
            for cell in table_rows[0]:
                cell_fmt = _format_inline_markdown(cell.strip())
                tbl_html.append(f'      <th style="padding: 10px 14px; border: 1px solid #cbd5e1; font-weight: bold; text-align: left; color: #1e293b;">{cell_fmt}</th>')
            tbl_html.append('    </tr>\n  </thead>')
            start_idx = 2

        tbl_html.append('  <tbody>')
        for r_idx, row in enumerate(table_rows[start_idx:]):
            bg = "#ffffff" if r_idx % 2 == 0 else "#f8fafc"
            tbl_html.append(f'    <tr style="background-color: {bg};">')
            for cell in row:
                cell_fmt = _format_inline_markdown(cell.strip())
                tbl_html.append(f'      <td style="padding: 10px 14px; border: 1px solid #cbd5e1; color: #334155;">{cell_fmt}</td>')
            tbl_html.append('    </tr>')
        tbl_html.append('  </tbody>\n</table>')
        html_lines.append("\n".join(tbl_html))
        table_rows = []
        in_table = False

    def flush_list():
        nonlocal in_list
        if in_list:
            html_lines.append("</ul>")
            in_list = False

    for line in lines:
        stripped = line.strip()

        # Handle Code Blocks (```)
        if stripped.startswith("```"):
            if in_code_block:
                in_code_block = False
                escaped_code = html.escape("\n".join(code_block_lines))
                html_lines.append(
                    f'<pre style="background-color: #1e293b; color: #f8fafc; padding: 14px 18px; border-radius: 6px; overflow-x: auto; font-family: Consolas, Monaco, monospace; font-size: 13.5px; line-height: 1.5; margin: 1.2em 0;"><code>{escaped_code}</code></pre>'
                )
                code_block_lines = []
            else:
                flush_table()
                flush_list()
                in_code_block = True
                code_block_lines = []
            continue

        if in_code_block:
            code_block_lines.append(line)
            continue

        # Handle Table Rows
        if stripped.startswith("|") and stripped.endswith("|"):
            flush_list()
            cells = [c for c in stripped.split("|")[1:-1]]
            table_rows.append(cells)
            in_table = True
            continue
        elif in_table:
            flush_table()

        # Handle Blank lines
        if not stripped:
            flush_list()
            continue

        # Handle Scene Dividers (* * * or ---)
        if stripped in ("* * *", "***", "---", "- - -", "___"):
            flush_list()
            html_lines.append(
                '<div style="text-align: center; margin: 2em 0; color: #94a3b8; font-size: 1.2em; letter-spacing: 0.5em;">✦ ✦ ✦</div>'
            )
            continue

        # Handle Headings
        if stripped.startswith("### "):
            flush_list()
            title_text = _format_inline_markdown(stripped[4:].strip())
            html_lines.append(
                f'<h3 style="color: #0f172a; border-left: 4px solid #3b82f6; padding: 6px 12px; margin-top: 1.8em; margin-bottom: 0.8em; font-size: 1.25em; background-color: #f0f9ff; border-radius: 0 4px 4px 0;">{title_text}</h3>'
            )
            continue
        elif stripped.startswith("## "):
            flush_list()
            title_text = _format_inline_markdown(stripped[3:].strip())
            html_lines.append(
                f'<h2 style="color: #0f172a; border-bottom: 2px solid #3b82f6; padding-bottom: 6px; margin-top: 2em; margin-bottom: 0.8em; font-size: 1.45em;">{title_text}</h2>'
            )
            continue
        elif stripped.startswith("# "):
            flush_list()
            title_text = _format_inline_markdown(stripped[2:].strip())
            html_lines.append(
                f'<h1 style="color: #0f172a; margin-top: 1.5em; margin-bottom: 0.8em; font-size: 1.7em;">{title_text}</h1>'
            )
            continue

        # Handle Blockquotes
        if stripped.startswith("> "):
            flush_list()
            quote_content = _format_inline_markdown(stripped[2:].strip())
            html_lines.append(
                f'<blockquote style="border-left: 4px solid #cbd5e1; margin: 1.2em 0; padding: 10px 16px; background-color: #f8fafc; color: #475569; font-style: normal; border-radius: 0 4px 4px 0;">{quote_content}</blockquote>'
            )
            continue

        # Handle Unordered Lists
        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_lines.append('<ul style="margin: 0.8em 0; padding-left: 1.8em; line-height: 1.8; color: #334155;">')
                in_list = True
            item_text = _format_inline_markdown(stripped[2:].strip())
            html_lines.append(f'  <li style="margin-bottom: 0.3em;">{item_text}</li>')
            continue
        else:
            flush_list()

        # Handle Ordered Lists
        ord_match = re.match(r"^(\d+)\.\s+(.*)$", stripped)
        if ord_match:
            flush_list()
            item_num = ord_match.group(1)
            item_text = _format_inline_markdown(ord_match.group(2).strip())
            html_lines.append(
                f'<div style="margin: 0.4em 0; padding-left: 1.5em; text-indent: -1.5em; line-height: 1.8; color: #334155;">'
                f'<span style="font-weight: bold; color: #2563eb; margin-right: 0.4em;">{item_num}.</span>{item_text}</div>'
            )
            continue

        # Regular Paragraph
        p_text = _format_inline_markdown(stripped)
        html_lines.append(f'<p style="margin: 1em 0; line-height: 1.85; font-size: 16px; color: #1e293b;">{p_text}</p>')

    flush_table()
    flush_list()

    return "\n".join(html_lines)

def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """Extracts YAML frontmatter and body from Markdown text."""
    pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
    match = re.match(pattern, content, re.DOTALL)
    if match:
        fm_text, body = match.group(1), match.group(2)
        if HAS_YAML:
            try:
                fm_data = yaml.safe_load(fm_text) or {}
                return fm_data, body.strip()
            except Exception:
                pass
        return _fallback_yaml_parser(fm_text), body.strip()
    return {}, content.strip()

def format_post_content(
    raw_markdown: str,
    default_status: str = "publish",
    use_jetpack_shortcodes: bool = True
) -> FormattedPost:
    """
    Parses Markdown, extracts frontmatter, and formats into both rich HTML and Plain Text.
    Adds Jetpack / Postie shortcodes to ensure correct category, tags, and publishing status.
    """
    meta, body = parse_frontmatter(raw_markdown)

    title = meta.get("title", "学校の課題を解決する物語")
    pattern = meta.get("pattern", "A")

    # Categories
    categories = meta.get("categories", [])
    if isinstance(categories, str):
        categories = [c.strip() for c in categories.split(",") if c.strip()]
    if not categories:
        if pattern == "A":
            categories = ["教育相談・学級経営", "教育心理学・教育哲学"]
        elif pattern == "C":
            categories = ["学校法制・教育法規", "学校管理・教育委員会"]
        else:
            categories = ["校務DX・学校ICT", "ネットワーク・業務効率化"]

    # Tags
    tags = meta.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    if not tags:
        if pattern == "A":
            tags = ["教育学", "教育心理学", "学級経営", "生徒指導", "若手教員育成", "Aパターン"]
        elif pattern == "C":
            tags = ["学校法制", "教育法規", "学校管理職", "校長", "教育委員会", "Cパターン"]
        else:
            tags = ["校務DX", "学校ICT", "業務効率化", "プログラミング", "ネットワーク", "Bパターン"]

    status = meta.get("status", default_status)

    # Clean any accidental pattern labels from the beginning of body
    body = re.sub(r'^(?:#+\s*)?(?:[📘💻⚖️]?\s*パターン[ABC][:：][^\n]*\n+)+', '', body, flags=re.MULTILINE).strip()
    body = re.sub(r'^(?:#+\s*)?(?:新米教員\s*[×x]\s*先輩教員|年配教員\s*[×x]\s*若手教員|校長先生?\s*[×x]\s*(?:指導主事|教育委員会))[^\n]*\n+', '', body, flags=re.MULTILINE).strip()

    # Convert Markdown to HTML
    body_html = _fallback_markdown_to_html(body)

    # Footer note styling
    footer_html = (
        '<div style="margin-top: 2.5em; padding: 16px 20px; background-color: #f8fafc; '
        'border-top: 1px solid #e2e8f0; border-radius: 6px; font-size: 13px; color: #64748b; line-height: 1.7;">'
        '<p style="margin: 0;"><strong>🏫 Solve School Problems</strong> は、学校現場の教育課題と校務の負担を、学術的英知・最新テクノロジー・学校法制の知見で解決する情報を定期配信しています。</p>'
        '</div>'
    )

    # Wrap in responsive, clean container without top pattern badge
    final_html = (
        f'<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, \'Hiragino Sans\', \'BIZ UDPGothic\', Meiryo, sans-serif; '
        f'color: #1e293b; max-width: 820px; margin: 0 auto; line-height: 1.85; font-size: 16px;">\n'
        f'{body_html}\n'
        f'{footer_html}\n'
        f'</div>'
    )

    # Build Plain Text with Jetpack shortcodes
    plain_parts = []
    if use_jetpack_shortcodes:
        if categories:
            cat_str = ", ".join(categories)
            plain_parts.append(f"[category {cat_str}]")
        if tags:
            tag_str = ", ".join(tags)
            plain_parts.append(f"[tags {tag_str}]")
        plain_parts.append(f"[status {status}]")
        plain_parts.append("")

    def _format_plain_link(m) -> str:
        clean_label = m.group(1).replace("\\(", "(").replace("\\)", ")")
        clean_url = _sanitize_url(m.group(2))
        return f"[{clean_label}]({clean_url})"

    plain_body = re.sub(
        r"\[([^\]]+)\]\((https?://(?:[^\s\(\)]|\\?\([^\s\(\)]*\\?\))+)\)",
        _format_plain_link,
        body
    )
    plain_parts.append(plain_body)
    final_plain = "\n".join(plain_parts)

    return FormattedPost(
        title=title,
        pattern=pattern,
        categories=categories,
        tags=tags,
        status=status,
        content_raw=raw_markdown,
        content_html=final_html,
        content_plain=final_plain
    )
