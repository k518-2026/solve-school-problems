import argparse
import json
import logging
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.history_manager import HistoryManager
from src.site_builder import build_github_pages, collect_all_stories
from src.story_generator import StoryGenerator

JST = timezone(timedelta(hours=9))
logger = logging.getLogger("school-task-worker")

TASKS_JSON_PATH = Path("data/tasks.json")
TASKS_MD_PATH = Path("data/TASKS.md")
PLOTS_DIR = Path("data/plots")
LOCK_FILE_PATH = Path(".worker.lock")

PROJECT_ID = "09f1227e-033f-496d-9750-362d7a3f9f27"
PROJECT_NAME = "solve-school-problems"
PROJECT_TITLE = "Solve School Problems（学校課題解決・教育法務ドラマ）"

DEFAULT_ROLES_CONFIG = {
    "rtx5060lp": {
        "node": "rtx5060lp",
        "role": "writer_primary",
        "host": "http://rtx5060lp:11434",
        "fallback_host": "http://192.168.128.62:11434",
        "writer_model": "shosetsu",
        "daily_quota": 2,
        "description": "小説執筆・プライマリ担当（Ollama shosetsu / セカンダリと1話ずつ交互に執筆）",
    },
    "sff7020": {
        "node": "sff7020",
        "role": "writer_secondary",
        "host": "http://sff7020:1234",
        "fallback_host": "http://192.168.128.16:1234",
        "writer_model": "google/gemma-4-26b-a4b-qat",
        "model": "google/gemma-4-26b-a4b-qat",
        "daily_quota": 2,
        "description": "小説執筆・セカンダリ担当（LM Studio gemma-4-26b-a4b-qat / プライマリと1話ずつ交互に執筆＆校閲）",
    },
    "kenomac-mini": {
        "node": "kenomac-mini",
        "role": "illustrator",
        "host": "http://kenomac-mini:7860",
        "fallback_host": "http://192.168.128.59:7860",
        "ollama_host": "http://kenomac-mini:11434",
        "fallback_ollama_host": "http://192.168.128.59:11434",
        "model": "flux_2_klein_base_4b_i8x.ckpt",
        "daily_quota": 5,
        "description": "FLUX.2 挿絵生成（content/*.png）＆ GitHub Pages（docs/）ビルド更新",
    },
}


def setup_logging(verbose: bool = False):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r"[\s_—―]+", "_", name)
    return name.strip("_")[:50]


def acquire_worker_lock(max_age_seconds: int = 3600) -> bool:
    if LOCK_FILE_PATH.exists():
        try:
            age = time.time() - LOCK_FILE_PATH.stat().st_mtime
            if age < max_age_seconds:
                logger.info(f"別のワーカープロセスが実行中です ({LOCK_FILE_PATH}, 経過 {int(age)}秒)。重複実行をスキップします。")
                return False
        except Exception:
            pass
    try:
        LOCK_FILE_PATH.write_text(f"pid={os.getpid()} started={datetime.now(JST).isoformat()}\n", encoding="utf-8")
        return True
    except Exception:
        return True


def release_worker_lock() -> None:
    try:
        if LOCK_FILE_PATH.exists():
            LOCK_FILE_PATH.unlink()
    except Exception:
        pass


def git_pull_latest() -> bool:
    try:
        logger.info("GitHubから最新のタスクキューと原稿を同期中 (git pull --rebase origin main)...")
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False)
        return True
    except Exception as e:
        logger.warning(f"git pull warning: {e}")
        return False


def git_commit_and_push(message: str, paths: Optional[List[str]] = None) -> bool:
    target_paths = paths or ["README.md", "content/", "data/", "docs/"]
    try:
        for p in target_paths:
            if Path(p).exists():
                subprocess.run(["git", "add", p], check=False)
        diff_res = subprocess.run(["git", "diff", "--staged", "--quiet"])
        if diff_res.returncode == 0:
            logger.info("コミット対象の変更はありません。")
            return True
        subprocess.run(["git", "commit", "-m", message], check=True)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False)
        subprocess.run(["git", "push", "origin", "HEAD:main"], check=True)
        logger.info(f"GitHubへの自動プッシュ完了: {message}")
        return True
    except Exception as e:
        logger.error(f"Git push error: {e}")
        return False


def probe_http_json(url: str, timeout: int = 3) -> Optional[Dict[str, Any]]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AntigravityTaskWorker/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as res:
            if res.getcode() == 200:
                return json.loads(res.read().decode("utf-8", errors="ignore"))
    except Exception:
        return None
    return None


def resolve_reachable_url(candidates: List[str], probe_path: str, timeout: int = 3) -> Optional[str]:
    for base in candidates:
        if not base:
            continue
        clean_base = base.rstrip("/")
        data = probe_http_json(f"{clean_base}{probe_path}", timeout=timeout)
        if data is not None and "error" not in data:
            return clean_base
    return None


def build_interleaved_catalog(history_mgr: HistoryManager) -> List[Dict[str, Any]]:
    a_list = history_mgr.catalog_data.get("pattern_A_topics", [])
    b_list = history_mgr.catalog_data.get("pattern_B_topics", [])
    c_list = history_mgr.catalog_data.get("pattern_C_topics", [])
    max_len = max(len(a_list), len(b_list), len(c_list), 0)
    interleaved: List[Dict[str, Any]] = []
    for i in range(max_len):
        if i < len(a_list):
            item = dict(a_list[i])
            item["pattern"] = "A"
            interleaved.append(item)
        if i < len(b_list):
            item = dict(b_list[i])
            item["pattern"] = "B"
            interleaved.append(item)
        if i < len(c_list):
            item = dict(c_list[i])
            item["pattern"] = "C"
            interleaved.append(item)
    return interleaved


def sync_tasks_manifest(history_mgr: HistoryManager, ensure_min_queued: int = 0) -> Dict[str, Any]:
    existing_data: Dict[str, Any] = {}
    if TASKS_JSON_PATH.exists():
        try:
            existing_data = json.loads(TASKS_JSON_PATH.read_text(encoding="utf-8"))
        except Exception:
            existing_data = {}

    existing_tasks_map: Dict[str, Dict[str, Any]] = {
        t["id"]: t for t in existing_data.get("tasks", []) if isinstance(t, dict) and "id" in t
    }
    roles_cfg = DEFAULT_ROLES_CONFIG

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    all_stories = collect_all_stories(history_mgr)
    story_by_tid: Dict[str, Dict[str, Any]] = {}
    for s in all_stories:
        tid = str(s.get("topic_id", "")).upper()
        if tid:
            story_by_tid[tid] = s

    # Determine last completed writer so uncompleted tasks strictly alternate (sff7020 <-> rtx5060lp)
    last_writer = "rtx5060lp"
    for prev_t in existing_data.get("tasks", []):
        if prev_t.get("written_by") in ("rtx5060lp", "sff7020"):
            last_writer = prev_t["written_by"]

    next_alt_writer = "sff7020" if last_writer == "rtx5060lp" else "rtx5060lp"

    interleaved = build_interleaved_catalog(history_mgr)
    synced_tasks: List[Dict[str, Any]] = []

    for idx, topic in enumerate(interleaved, start=1):
        tid = str(topic["id"]).upper()
        prev = existing_tasks_map.get(tid, {})
        story_info = story_by_tid.get(tid)
        stock_md = story_info["md_path"] if story_info else None
        stock_png = stock_md.with_suffix(".png") if stock_md else None
        plot_path = PLOTS_DIR / f"{tid}.md"

        md_rel = str(stock_md).replace("\\", "/") if stock_md and stock_md.exists() else None
        png_rel = str(stock_png).replace("\\", "/") if stock_png and stock_png.exists() else None
        plot_rel = str(plot_path).replace("\\", "/") if plot_path.exists() else None

        if md_rel and png_rel:
            status = "completed"
        elif md_rel and not png_rel:
            status = "pending_illustration"
        elif prev.get("status") == "queued":
            status = "queued"
        elif plot_rel:
            status = "plot_ready"
        else:
            status = "pending"

        inferred_date = None
        if stock_md and re.match(r"^\d{4}-\d{2}-\d{2}_", stock_md.name):
            inferred_date = stock_md.name[:10]

        if md_rel:
            written_by = prev.get("written_by") or "rtx5060lp"
            assigned_writer = written_by
            assigned_model = "google/gemma-4-26b-a4b-qat" if written_by == "sff7020" else "shosetsu"
        else:
            written_by = None
            assigned_writer = next_alt_writer
            assigned_model = "google/gemma-4-26b-a4b-qat" if assigned_writer == "sff7020" else "shosetsu"
            next_alt_writer = "rtx5060lp" if next_alt_writer == "sff7020" else "sff7020"

        task_entry = {
            "id": tid,
            "order_num": idx,
            "pattern": topic.get("pattern", "A"),
            "category": topic.get("category", ""),
            "title": story_info["full_title"] if story_info else topic.get("problem_title", ""),
            "problem_title": topic.get("problem_title", ""),
            "solution_framework": topic.get("solution_framework", ""),
            "status": status,
            "assigned_writer": assigned_writer,
            "assigned_model": assigned_model,
            "queued_at": prev.get("queued_at"),
            "plot_file": plot_rel,
            "plot_by": prev.get("plot_by") or ("sff7020" if plot_rel else None),
            "plot_at": prev.get("plot_at"),
            "md_file": md_rel,
            "written_by": written_by,
            "written_at": prev.get("written_at") or inferred_date,
            "reviewed_by": prev.get("reviewed_by"),
            "reviewed_at": prev.get("reviewed_at"),
            "png_file": png_rel,
            "illustrated_by": prev.get("illustrated_by") or ("kenomac-mini" if png_rel else None),
            "illustrated_at": prev.get("illustrated_at") or (inferred_date if png_rel else None),
        }
        synced_tasks.append(task_entry)

    # Ensure minimum queued tasks if requested
    if ensure_min_queued > 0:
        currently_queued = sum(1 for t in synced_tasks if t["status"] == "queued")
        to_add = max(0, ensure_min_queued - currently_queued)
        now_iso = datetime.now(JST).isoformat()
        for t in synced_tasks:
            if to_add <= 0:
                break
            if t["status"] in ("pending", "plot_ready"):
                t["status"] = "queued"
                t["queued_at"] = now_iso
                to_add -= 1

    manifest = {
        "project_id": PROJECT_ID,
        "project_name": PROJECT_NAME,
        "project_title": PROJECT_TITLE,
        "updated_at": datetime.now(JST).isoformat(),
        "roles": roles_cfg,
        "tasks": synced_tasks,
    }

    TASKS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    TASKS_JSON_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_tasks_markdown(manifest)
    return manifest


def enqueue_daily_tasks(manifest: Dict[str, Any], count: int = 2) -> int:
    """Adds `count` new tasks from `pending`/`plot_ready` into `queued` status on GitHub."""
    now_iso = datetime.now(JST).isoformat()
    enqueued = 0
    for t in manifest.get("tasks", []):
        if enqueued >= count:
            break
        if t["status"] in ("pending", "plot_ready"):
            t["status"] = "queued"
            t["queued_at"] = now_iso
            enqueued += 1
            logger.info(
                f"[GitHub Task Queue] タスク追加: [{t['id']}] {t['problem_title']} "
                f"(担当: {t['assigned_writer']} / {t['assigned_model']})"
            )
    if enqueued > 0:
        manifest["updated_at"] = now_iso
        TASKS_JSON_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_tasks_markdown(manifest)
    return enqueued


def write_tasks_markdown(manifest: Dict[str, Any]) -> None:
    tasks = manifest.get("tasks", [])
    completed = [t for t in tasks if t["status"] == "completed"]
    pending_ill = [t for t in tasks if t["status"] == "pending_illustration"]
    queued = [t for t in tasks if t["status"] == "queued"]
    plot_ready = [t for t in tasks if t["status"] == "plot_ready"]
    pending = [t for t in tasks if t["status"] == "pending"]

    lines = [
        f"# 📋 分散ローカルLLM 自動作業リスト (`{PROJECT_NAME}`)",
        "",
        f"- **会話ID**: `{PROJECT_ID}`",
        f"- **最終同期日時 (JST)**: `{manifest.get('updated_at', '')[:19]}`",
        f"- **進捗サマリー**: 全 **{len(tasks)}** テーマ （完了: **{len(completed)}** / 挿絵待ち: **{len(pending_ill)}** / **PC起動時実行キュー(溜まっているタスク): {len(queued)}** / 待機中: **{len(plot_ready) + len(pending)}**）",
        "",
        "## 🖥️ 各ローカルLLM PCの役割分担（プライマリ＆セカンダリ交互執筆）",
        "",
        "| PCホスト名 | 役割 (`role`) | 使用モデル / API | 1回あたり上限 (`daily_quota`) | 担当作業内容 |",
        "|:---|:---|:---|:---:|:---|",
        "| **`rtx5060lp`** | `writer_primary` | Ollama `shosetsu` (`:11434`) | 2 話 | 小説執筆・プライマリ（`sff7020` と1話ずつ交互に担当） |",
        "| **`sff7020`** | `writer_secondary` | LM Studio `google/gemma-4-26b-a4b-qat` (`:1234`) | 2 話 | 小説執筆・セカンダリ（`rtx5060lp` と1話ずつ交互に担当）＆校閲 |",
        "| **`kenomac-mini`** | `illustrator` | Draw Things `FLUX.2` (`:7860`) | 5 枚 | 挿絵生成 (`content/*.png`) ＆ GitHub Pages (`docs/`) 更新 |",
        "",
        "## 🚀 次回PC起動時の自動実行キュー（GitHub蓄積タスク一覧）",
        "",
        "| パターン | テーマID | 課題タイトル | カテゴリ | 現在の状態 | 担当ライター（交互割当） |",
        "|:---:|:---:|:---|:---|:---:|:---|",
    ]

    active_queue = pending_ill + queued + plot_ready + pending
    if not active_queue:
        lines.append("| - | - | （全60テーマ完了済み・2巡目待機） | - | Completed | `rtx5060lp` / `sff7020` |")
    else:
        for t in active_queue[:15]:
            st = t["status"]
            writer_node = t.get("assigned_writer", "rtx5060lp")
            writer_model = t.get("assigned_model", "shosetsu")
            if st == "pending_illustration":
                next_pc = "🎨 `kenomac-mini` (挿絵生成のみ)"
            elif st == "queued":
                next_pc = f"🔥 **実行待機** ✍️ `{writer_node}` (`{writer_model}`) ＋ 🎨 `kenomac-mini`"
            else:
                next_pc = f"✍️ `{writer_node}` (`{writer_model}`) ＋ 🎨 `kenomac-mini`"
            lines.append(
                f"| **{t['pattern']}** | `{t['id']}` | {t['title']} | {t.get('category', '')} | `{st}` | {next_pc} |"
            )

    lines.extend([
        "",
        "## ✅ 完了済みエピソード（最新10件）",
        "",
        "| パターン | テーマID | タイトル | 執筆担当 (`written_by`) | 校閲 (`sff7020`) | 挿絵 (`kenomac-mini`) |",
        "|:---:|:---:|:---|:---:|:---:|:---:|",
    ])
    for t in list(reversed(completed))[:10]:
        w_by = t.get("written_by") or "rtx5060lp"
        w_date = str(t.get("written_at") or "")[:10]
        w_mark = f"✓ `{w_by}` ({w_date})" if t.get("md_file") else "-"
        r_mark = f"✓ ({t.get('reviewed_by')})" if t.get("reviewed_by") else "校閲済/対象"
        i_mark = f"🎨 ({t.get('illustrated_by')})" if t.get("png_file") else "-"
        lines.append(
            f"| **{t['pattern']}** | `{t['id']}` | {t['title']} | {w_mark} | {r_mark} | {i_mark} |"
        )

    TASKS_MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def resolve_writer_endpoints() -> Tuple[Optional[str], Optional[str]]:
    """Returns (rtx5060lp_url_or_None, sff7020_url_or_None)."""
    rtx_host = resolve_reachable_url(
        [
            os.getenv("OLLAMA_HOST", ""),
            "http://rtx5060lp:11434",
            "http://192.168.128.62:11434",
            "http://localhost:11434",
        ],
        "/api/tags",
    )
    sff_host = resolve_reachable_url(
        [
            os.getenv("LM_STUDIO_HOST", ""),
            "http://sff7020:1234",
            "http://192.168.128.16:1234",
            "http://localhost:1234",
        ],
        "/v1/models",
    )
    return rtx_host, sff_host


def run_alternating_writer_role(
    manifest: Dict[str, Any],
    history_mgr: HistoryManager,
    quota_override: Optional[int] = None,
    push_to_git: bool = True,
    target_node_filter: Optional[str] = None,
) -> int:
    """
    Executes queued (or next pending) story writing tasks stored on GitHub,
    alternating between Primary (`rtx5060lp` / `shosetsu`) and Secondary (`sff7020` / `google/gemma-4-26b-a4b-qat`).
    """
    rtx_host, sff_host = resolve_writer_endpoints()
    if not rtx_host and not sff_host:
        logger.info("[Writer] プライマリ (rtx5060lp:11434) と セカンダリ (sff7020:1234) の両方がオフラインのためスキップします。")
        return 0

    logger.info(
        f"[Writer Status] Primary (rtx5060lp/shosetsu): {rtx_host or 'OFFLINE'} | "
        f"Secondary (sff7020/gemma-4-26b-a4b-qat): {sff_host or 'OFFLINE'}"
    )

    queued_tasks = [t for t in manifest["tasks"] if t["status"] == "queued"]
    other_pending = [t for t in manifest["tasks"] if t["status"] in ("plot_ready", "pending")]

    if target_node_filter in ("rtx5060lp", "sff7020"):
        queued_tasks = [t for t in queued_tasks if t.get("assigned_writer") == target_node_filter]
        other_pending = [t for t in other_pending if t.get("assigned_writer") == target_node_filter]

    if quota_override is not None:
        max_to_write = quota_override
        candidates = (queued_tasks + other_pending)[:max_to_write]
    elif queued_tasks:
        # Process accumulated GitHub queued tasks (up to 4 per startup run to stay responsive)
        max_to_write = min(len(queued_tasks), 4)
        candidates = queued_tasks[:max_to_write]
        logger.info(f"[GitHub Queue] GitHubに蓄積されている実行待ちタスク {len(queued_tasks)} 件のうち {len(candidates)} 件を実行します。")
    else:
        # If no explicitly queued tasks exist yet, check daily quota (default 2: 1 primary + 1 secondary)
        today_str = datetime.now(JST).strftime("%Y-%m-%d")
        written_today = sum(
            1 for t in manifest["tasks"]
            if str(t.get("written_at") or "").startswith(today_str)
        )
        max_to_write = max(0, 2 - written_today)
        if max_to_write == 0:
            logger.info(f"[Writer] GitHub実行待ちキューは空で、本日の執筆ノルマ ({written_today}/2 話) も達成済みです。")
            return 0
        candidates = other_pending[:max_to_write]

    catalog_map = {t["id"]: t for t in build_interleaved_catalog(history_mgr)}
    written_count = 0
    content_dir = Path("content")
    today_str = datetime.now(JST).strftime("%Y-%m-%d")

    for task in candidates:
        topic = catalog_map.get(task["id"])
        if not topic:
            continue
        pat = topic.get("pattern", "A")
        tid = topic["id"]
        assigned = task.get("assigned_writer", "rtx5060lp")

        if assigned == "sff7020":
            if sff_host:
                active_host = sff_host
                active_model = "google/gemma-4-26b-a4b-qat"
                actual_writer = "sff7020"
            elif rtx_host:
                logger.info(f"[Failover] 担当 sff7020 がオフラインのため rtx5060lp (shosetsu) が代替執筆します: [{tid}]")
                active_host = rtx_host
                active_model = "shosetsu"
                actual_writer = "rtx5060lp"
            else:
                continue
        else:
            if rtx_host:
                active_host = rtx_host
                active_model = "shosetsu"
                actual_writer = "rtx5060lp"
            elif sff_host:
                logger.info(f"[Failover] 担当 rtx5060lp がオフラインのため sff7020 (gemma-4-26b-a4b-qat) が代替執筆します: [{tid}]")
                active_host = sff_host
                active_model = "google/gemma-4-26b-a4b-qat"
                actual_writer = "sff7020"
            else:
                continue

        generator = StoryGenerator(
            ollama_host=active_host,
            writer_model=active_model,
        )

        if task.get("plot_file") and Path(task["plot_file"]).exists():
            topic["_director_plot_blueprint"] = Path(task["plot_file"]).read_text(encoding="utf-8", errors="ignore")

        logger.info(
            f"\n=== [{actual_writer} ({active_model})] 小説執筆開始 ({written_count + 1}/{len(candidates)}): "
            f"[Pattern {pat} / {tid}] {topic.get('problem_title')} ==="
        )
        try:
            raw_md, title, _ = generator.generate_story(pat, topic, use_local_llm=True)
            safe_title = sanitize_filename(title)
            out_path = content_dir / f"{today_str}_pattern_{pat.lower()}_{tid.lower()}_{safe_title}.md"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(raw_md, encoding="utf-8")

            history_mgr.record_post({
                "title": title,
                "pattern": pat,
                "topic_id": tid,
                "category": topic.get("category", ""),
                "file_path": str(out_path).replace("\\", "/"),
                "written_by": actual_writer,
                "writer_model": active_model,
                "sent_to_wp": False,
                "sent_to_blogger": False,
                "status": "github_pages",
            })

            task["title"] = title
            task["md_file"] = str(out_path).replace("\\", "/")
            task["written_by"] = actual_writer
            task["written_at"] = datetime.now(JST).isoformat()
            task["status"] = "pending_illustration"
            written_count += 1

            manifest["updated_at"] = datetime.now(JST).isoformat()
            TASKS_JSON_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            write_tasks_markdown(manifest)
            build_github_pages(history_mgr)
            if push_to_git:
                git_commit_and_push(f"feat({actual_writer}): Write story [{tid}] via {active_model} & update task queue")
        except Exception as e:
            logger.error(f"[{actual_writer}] '{tid}' の執筆に失敗しました: {e}")

    return written_count


def run_illustrator_role(
    manifest: Dict[str, Any],
    history_mgr: HistoryManager,
    quota_override: Optional[int] = None,
    push_to_git: bool = True,
) -> int:
    role_cfg = manifest["roles"]["kenomac-mini"]
    quota = quota_override if quota_override is not None else int(role_cfg.get("daily_quota", 5))
    dt_host = resolve_reachable_url(
        [
            os.getenv("DRAW_THINGS_HOST", ""),
            role_cfg.get("host", "http://kenomac-mini:7860"),
            role_cfg.get("fallback_host", "http://192.168.128.59:7860"),
            "http://localhost:7860",
        ],
        "/sdapi/v1/options",
    )
    if not dt_host:
        logger.info("[kenomac-mini / illustrator] Draw Things サーバー (kenomac-mini:7860) がオフラインのためスキップします。")
        return 0

    generator = StoryGenerator(
        draw_things_host=dt_host,
    )

    all_stories = collect_all_stories(history_mgr)
    missing_stories = [s for s in reversed(all_stories) if not s["has_image"]]
    if not missing_stories:
        logger.info("[kenomac-mini / illustrator] 未挿絵のストーリーはありません。GitHub Pages を最新状態に同期します。")
        build_github_pages(history_mgr)
        return 0

    task_by_tid = {t["id"]: t for t in manifest["tasks"]}
    illustrated_count = 0

    for s in missing_stories[:quota]:
        md_file = s["md_path"]
        img_p = md_file.with_suffix(".png")
        tid = str(s["topic_id"]).upper()
        logger.info(f"[kenomac-mini / illustrator] FLUX.2 挿絵生成中 ({illustrated_count + 1}/{min(quota, len(missing_stories))}): [{tid}] {img_p.name}")
        topic_info = dict(s.get("catalog_item") or {})
        topic_info.update({
            "id": tid,
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
            illustrated_count += 1
            if tid in task_by_tid:
                task_by_tid[tid]["png_file"] = str(saved_img).replace("\\", "/")
                task_by_tid[tid]["illustrated_by"] = "kenomac-mini"
                task_by_tid[tid]["illustrated_at"] = datetime.now(JST).isoformat()
                task_by_tid[tid]["status"] = "completed"

            manifest["updated_at"] = datetime.now(JST).isoformat()
            TASKS_JSON_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            write_tasks_markdown(manifest)
            build_github_pages(history_mgr)
            if push_to_git:
                git_commit_and_push(f"feat(kenomac-mini): Add FLUX.2 illustration for [{tid}] & rebuild GitHub Pages")

    return illustrated_count


def detect_local_role() -> str:
    hostname = socket.gethostname().lower()
    if "rtx5060lp" in hostname:
        return "rtx5060lp"
    if "kenomac-mini" in hostname or "mac-mini" in hostname:
        return "illustrator"
    if "sff7020" in hostname:
        return "sff7020"
    return "lan-dispatch"


def main():
    parser = argparse.ArgumentParser(
        description="GitHub-Synced Distributed Local LLM Task Worker for solve-school-problems"
    )
    parser.add_argument(
        "--role",
        choices=[
            "auto",
            "startup",
            "lan-dispatch",
            "writer",
            "rtx5060lp",
            "sff7020",
            "illustrator",
            "kenomac-mini",
            "director",
            "enqueue",
            "sync",
        ],
        default="auto",
        help="Worker role to run (default: auto-detect or dispatch to online LAN servers)",
    )
    parser.add_argument("--quota", type=int, default=None, help="Override task quota for this run")
    parser.add_argument("--no-push", action="store_true", help="Do not git commit/push changes")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    setup_logging(args.verbose)
    push_to_git = not args.no_push

    if args.role not in ("enqueue", "sync"):
        if not acquire_worker_lock():
            return

    try:
        if push_to_git:
            git_pull_latest()

        history_mgr = HistoryManager()
        manifest = sync_tasks_manifest(history_mgr)

        role = args.role
        if role == "auto":
            role = detect_local_role()
            logger.info(f"ホスト名 '{socket.gethostname()}' から自動判定された実行モード: {role}")

        if role == "enqueue":
            count_to_add = args.quota if args.quota is not None else 2
            added = enqueue_daily_tasks(manifest, count=count_to_add)
            if added > 0 and push_to_git:
                git_commit_and_push(f"chore(tasks): Enqueue {added} new task(s) in GitHub task queue")
            return

        if role == "sync":
            if push_to_git:
                git_commit_and_push("chore(tasks): Sync distributed task queue manifest (data/tasks.json & data/TASKS.md)")
            return

        if role == "rtx5060lp":
            run_alternating_writer_role(
                manifest, history_mgr, quota_override=args.quota, push_to_git=push_to_git, target_node_filter="rtx5060lp"
            )
        elif role in ("sff7020", "director"):
            run_alternating_writer_role(
                manifest, history_mgr, quota_override=args.quota, push_to_git=push_to_git, target_node_filter="sff7020"
            )
        elif role == "writer":
            run_alternating_writer_role(
                manifest, history_mgr, quota_override=args.quota, push_to_git=push_to_git
            )
        elif role in ("illustrator", "kenomac-mini"):
            run_illustrator_role(manifest, history_mgr, quota_override=args.quota, push_to_git=push_to_git)
        elif role in ("lan-dispatch", "startup"):
            logger.info(
                "=== [PC Startup / LAN Dispatch] GitHubから蓄積タスクを読み取り、"
                "プライマリ(rtx5060lp/shosetsu) ＆ セカンダリ(sff7020/gemma-4-26b-a4b-qat) 交互執筆 ＋ "
                "kenomac-mini(FLUX.2) 挿絵生成を実行します ==="
            )
            # First backfill any missing illustrations
            run_illustrator_role(manifest, history_mgr, quota_override=args.quota, push_to_git=push_to_git)
            manifest = sync_tasks_manifest(history_mgr)
            # Next run alternating writer on queued tasks
            written = run_alternating_writer_role(manifest, history_mgr, quota_override=args.quota, push_to_git=push_to_git)
            if written > 0:
                manifest = sync_tasks_manifest(history_mgr)
                run_illustrator_role(manifest, history_mgr, quota_override=args.quota, push_to_git=push_to_git)
    finally:
        if args.role not in ("enqueue", "sync"):
            release_worker_lock()


if __name__ == "__main__":
    main()
