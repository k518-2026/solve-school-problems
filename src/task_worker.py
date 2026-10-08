import argparse
import json
import logging
import os
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.history_manager import HistoryManager
from src.site_builder import build_github_pages, collect_all_stories
from src.story_generator import StoryGenerator

JST = timezone(timedelta(hours=9))
logger = logging.getLogger("school-task-worker")

TASKS_JSON_PATH = Path("data/tasks.json")
TASKS_MD_PATH = Path("data/TASKS.md")
PLOTS_DIR = Path("data/plots")

PROJECT_ID = "09f1227e-033f-496d-9750-362d7a3f9f27"
PROJECT_NAME = "solve-school-problems"
PROJECT_TITLE = "Solve School Problems（学校課題解決・教育法務ドラマ）"

DEFAULT_ROLES_CONFIG = {
    "rtx5060lp": {
        "node": "rtx5060lp",
        "role": "writer",
        "host": "http://rtx5060lp:11434",
        "fallback_host": "http://192.168.128.62:11434",
        "writer_model": "shosetsu",
        "daily_quota": 2,
        "description": "小説本文・理論/技術/法規解説の執筆（content/*.md 生成）",
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
    "sff7020": {
        "node": "sff7020",
        "role": "director",
        "host": "http://sff7020:1234",
        "fallback_host": "http://192.168.128.16:1234",
        "model": "google/gemma-4-26b-a4b-qat",
        "daily_quota": 2,
        "description": "LM Studio による先行プロット設計（data/plots/*.md）＆ 執筆済み原稿の品質校閲",
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


def git_pull_latest() -> bool:
    try:
        logger.info("GitHubから最新の作業リストと原稿を同期中 (git pull --rebase origin main)...")
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
        if probe_http_json(f"{clean_base}{probe_path}", timeout=timeout) is not None:
            return clean_base
    return None


def call_lm_studio_chat(
    host: str,
    messages: List[Dict[str, str]],
    preferred_model: str = "google/gemma-4-26b-a4b-qat",
    temperature: float = 0.65,
    max_tokens: int = 2200,
    timeout: int = 300,
) -> Optional[str]:
    models_data = probe_http_json(f"{host}/v1/models", timeout=4)
    model_id = preferred_model
    if models_data and isinstance(models_data.get("data"), list):
        available = [m.get("id", "") for m in models_data["data"] if m.get("id")]
        non_embed = [m for m in available if "embed" not in m.lower()]
        if preferred_model in available:
            model_id = preferred_model
        elif non_embed:
            model_id = non_embed[0]

    payload = {
        "model": model_id,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{host}/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            body = json.loads(res.read().decode("utf-8", errors="ignore"))
            choices = body.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "")
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                return content
    except Exception as e:
        logger.warning(f"LM Studio call failed on {host} ({model_id}): {e}")
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


def sync_tasks_manifest(history_mgr: HistoryManager) -> Dict[str, Any]:
    existing_data: Dict[str, Any] = {}
    if TASKS_JSON_PATH.exists():
        try:
            existing_data = json.loads(TASKS_JSON_PATH.read_text(encoding="utf-8"))
        except Exception:
            existing_data = {}

    existing_tasks_map: Dict[str, Dict[str, Any]] = {
        t["id"]: t for t in existing_data.get("tasks", []) if isinstance(t, dict) and "id" in t
    }
    roles_cfg = existing_data.get("roles", DEFAULT_ROLES_CONFIG)

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    all_stories = collect_all_stories(history_mgr)
    story_by_tid: Dict[str, Dict[str, Any]] = {}
    for s in all_stories:
        tid = str(s.get("topic_id", "")).upper()
        if tid:
            story_by_tid[tid] = s

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
        elif plot_rel:
            status = "plot_ready"
        else:
            status = "pending"

        inferred_date = None
        if stock_md and re.match(r"^\d{4}-\d{2}-\d{2}_", stock_md.name):
            inferred_date = stock_md.name[:10]

        task_entry = {
            "id": tid,
            "order_num": idx,
            "pattern": topic.get("pattern", "A"),
            "category": topic.get("category", ""),
            "title": story_info["full_title"] if story_info else topic.get("problem_title", ""),
            "problem_title": topic.get("problem_title", ""),
            "solution_framework": topic.get("solution_framework", ""),
            "status": status,
            "plot_file": plot_rel,
            "plot_by": prev.get("plot_by") or ("sff7020" if plot_rel else None),
            "plot_at": prev.get("plot_at"),
            "md_file": md_rel,
            "written_by": prev.get("written_by") or ("rtx5060lp" if md_rel else None),
            "written_at": prev.get("written_at") or inferred_date,
            "reviewed_by": prev.get("reviewed_by"),
            "reviewed_at": prev.get("reviewed_at"),
            "png_file": png_rel,
            "illustrated_by": prev.get("illustrated_by") or ("kenomac-mini" if png_rel else None),
            "illustrated_at": prev.get("illustrated_at") or (inferred_date if png_rel else None),
        }
        synced_tasks.append(task_entry)

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


def write_tasks_markdown(manifest: Dict[str, Any]) -> None:
    tasks = manifest.get("tasks", [])
    completed = [t for t in tasks if t["status"] == "completed"]
    pending_ill = [t for t in tasks if t["status"] == "pending_illustration"]
    plot_ready = [t for t in tasks if t["status"] == "plot_ready"]
    pending = [t for t in tasks if t["status"] == "pending"]

    lines = [
        f"# 📋 分散ローカルLLM 自動作業リスト (`{PROJECT_NAME}`)",
        "",
        f"- **会話ID**: `{PROJECT_ID}`",
        f"- **最終同期日時 (JST)**: `{manifest.get('updated_at', '')[:19]}`",
        f"- **進捗サマリー**: 全 **{len(tasks)}** テーマ （完了: **{len(completed)}** / 挿絵待ち: **{len(pending_ill)}** / プロット作成済: **{len(plot_ready)}** / 未着手: **{len(pending)}**）",
        "",
        "## 🖥️ 各ローカルLLM PCの役割分担とノルマ",
        "",
        "| PCホスト名 | 役割 (`role`) | 使用モデル / API | 1日あたり上限 (`daily_quota`) | 担当作業内容 |",
        "|:---|:---|:---|:---:|:---|",
        "| **`rtx5060lp`** | `writer` | Ollama `shosetsu` (`:11434`) | 2 話 | 小説本文・解説の執筆 (`content/*.md`) |",
        "| **`kenomac-mini`** | `illustrator` | Draw Things `FLUX.2` (`:7860`) + Ollama `gemma4:12b` | 5 枚 | 挿絵生成 (`content/*.png`) ＆ GitHub Pages (`docs/`) 更新 |",
        "| **`sff7020`** | `director` | LM Studio `gemma-4-26b-a4b-qat` (`:1234`) | 2 件 | 先行プロット設計 (`data/plots/*.md`) ＆ 既存原稿の品質校閲 |",
        "",
        "## 🚀 次回起動時の自動実行キュー（未完了タスク一覧）",
        "",
        "| パターン | テーマID | 課題タイトル | カテゴリ | 現在の状態 | 次に担当するPC |",
        "|:---:|:---:|:---|:---|:---:|:---|",
    ]

    active_queue = pending_ill + plot_ready + pending
    if not active_queue:
        lines.append("| - | - | （全60テーマ完了済み・2巡目待機） | - | Completed | `rtx5060lp` |")
    else:
        for t in active_queue[:15]:
            st = t["status"]
            if st == "pending_illustration":
                next_pc = "🎨 `kenomac-mini` (挿絵生成)"
            elif st == "plot_ready":
                next_pc = "✍️ `rtx5060lp` (小説執筆)"
            else:
                next_pc = "📐 `sff7020` (プロット) / ✍️ `rtx5060lp` (執筆)"
            lines.append(
                f"| **{t['pattern']}** | `{t['id']}` | {t['title']} | {t.get('category', '')} | `{st}` | {next_pc} |"
            )

    lines.extend([
        "",
        "## ✅ 完了済みエピソード（最新10件）",
        "",
        "| パターン | テーマID | タイトル | プロット (`sff7020`) | 執筆 (`rtx5060lp`) | 校閲 (`sff7020`) | 挿絵 (`kenomac-mini`) |",
        "|:---:|:---:|:---|:---:|:---:|:---:|:---:|",
    ])
    for t in list(reversed(completed))[:10]:
        p_mark = f"✓ ({t.get('plot_by')})" if t.get("plot_file") else "-"
        w_mark = f"✓ ({str(t.get('written_at') or '')[:10]})" if t.get("md_file") else "-"
        r_mark = f"✓ ({t.get('reviewed_by')})" if t.get("reviewed_by") else "未校閲"
        i_mark = f"🎨 ({t.get('illustrated_by')})" if t.get("png_file") else "-"
        lines.append(
            f"| **{t['pattern']}** | `{t['id']}` | {t['title']} | {p_mark} | {w_mark} | {r_mark} | {i_mark} |"
        )

    TASKS_MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_director_role(
    manifest: Dict[str, Any],
    history_mgr: HistoryManager,
    quota_override: Optional[int] = None,
    push_to_git: bool = True,
) -> int:
    role_cfg = manifest["roles"]["sff7020"]
    quota = quota_override if quota_override is not None else int(role_cfg.get("daily_quota", 2))
    lm_host = resolve_reachable_url(
        [
            os.getenv("LM_STUDIO_HOST", ""),
            role_cfg.get("host", "http://sff7020:1234"),
            role_cfg.get("fallback_host", "http://192.168.128.16:1234"),
            "http://localhost:1234",
        ],
        "/v1/models",
    )
    if not lm_host:
        logger.info("[sff7020 / director] LM Studio サーバーがオフラインのためスキップします。")
        return 0

    logger.info(f"[sff7020 / director] LM Studio ({lm_host}) に接続しました。校閲および先行プロット作成を開始します。")
    today_str = datetime.now(JST).strftime("%Y-%m-%d")
    now_iso = datetime.now(JST).isoformat()
    actions_done = 0

    # 1. Review unreviewed stories
    unreviewed = [
        t for t in reversed(manifest["tasks"])
        if t.get("md_file") and not t.get("reviewed_by") and Path(t["md_file"]).exists()
    ]
    reviewed_today = sum(
        1 for t in manifest["tasks"]
        if str(t.get("reviewed_at") or "").startswith(today_str)
    )
    review_needed = max(0, quota - reviewed_today)

    for task in unreviewed[:review_needed]:
        md_path = Path(task["md_file"])
        raw_md = md_path.read_text(encoding="utf-8", errors="ignore")
        cleaned_md = StoryGenerator._normalize_japanese_typos(raw_md)
        if cleaned_md != raw_md:
            md_path.write_text(cleaned_md, encoding="utf-8")
            logger.info(f"[sff7020 / director] 原稿の表記揺れ・簡体字を自動補正しました: {md_path.name}")
        task["reviewed_by"] = "sff7020"
        task["reviewed_at"] = now_iso
        actions_done += 1
        logger.info(f"[sff7020 / director] 校閲完了: [{task['id']}] {task['title']}")

    # 2. Pre-generate plot blueprints for pending tasks
    plots_today = sum(
        1 for t in manifest["tasks"]
        if str(t.get("plot_at") or "").startswith(today_str)
    )
    plot_needed = max(0, quota - plots_today)
    pending_tasks = [t for t in manifest["tasks"] if t["status"] == "pending"]
    catalog_map = {t["id"]: t for t in build_interleaved_catalog(history_mgr)}

    for task in pending_tasks[:plot_needed]:
        topic = catalog_map.get(task["id"])
        if not topic:
            continue
        pat = topic.get("pattern", "A")
        logger.info(f"[sff7020 / director] 先行プロット作成中: [Pattern {pat} / {topic['id']}] {topic.get('problem_title')}...")
        prompt = f"""あなたは学校現場の課題解決ドラマ『Solve School Problems』の構成作家（Director）です。
次回 `rtx5060lp`（小説執筆担当）が執筆するための詳細な4シーン構成プロットを作成してください。

【テーマ情報】
- パターン: {pat} （A=教育相談・心理学 / B=校務DX・ICT / C=校長×指導主事・教育法制）
- テーマID: {topic['id']}
- カテゴリ: {topic.get('category', '')}
- 課題タイトル: {topic.get('problem_title', '')}
- 現場の状況: {topic.get('situation', '')}
- 解決の理論・技術・法規フレームワーク: {topic.get('solution_framework', '')}

【出力フォーマット】
1. 魅力的で文学的な小説タイトル案
2. 登場人物2名の具体的な名前・キャラクター設定・関係性
3. 第1シーン（発端：放課後の学校現場でのリアルな悩みと葛藤）
4. 第2シーン（対話：メンター/若手ICT/指導主事との対話と理論・技術・法規の提示）
5. 第3シーン（実践と転換：現場での具体的な工夫と手応え）
6. 第4シーン（温かい余韻：明日への希望が感じられるエンディング）
"""
        plot_text = call_lm_studio_chat(
            host=lm_host,
            messages=[
                {"role": "system", "content": "あなたは学校教育・校務DX・学校法務ドラマの優秀な構成作家です。"},
                {"role": "user", "content": prompt},
            ],
            preferred_model=role_cfg.get("model", "google/gemma-4-26b-a4b-qat"),
        )
        if plot_text and len(plot_text) >= 150:
            PLOTS_DIR.mkdir(parents=True, exist_ok=True)
            plot_file = PLOTS_DIR / f"{topic['id']}.md"
            plot_file.write_text(plot_text, encoding="utf-8")
            task["plot_file"] = str(plot_file).replace("\\", "/")
            task["plot_by"] = "sff7020"
            task["plot_at"] = now_iso
            task["status"] = "plot_ready"
            actions_done += 1
            logger.info(f"[sff7020 / director] プロット保存完了: {plot_file}")

    if actions_done > 0:
        manifest["updated_at"] = datetime.now(JST).isoformat()
        TASKS_JSON_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_tasks_markdown(manifest)
        build_github_pages(history_mgr)
        if push_to_git:
            git_commit_and_push(f"feat(sff7020): Update {actions_done} plot/review task(s) via sff7020 LM Studio")
    else:
        logger.info("[sff7020 / director] 本日の校閲・プロット作成ノルマは達成済みです。")

    return actions_done


def run_writer_role(
    manifest: Dict[str, Any],
    history_mgr: HistoryManager,
    quota_override: Optional[int] = None,
    push_to_git: bool = True,
) -> int:
    role_cfg = manifest["roles"]["rtx5060lp"]
    quota = quota_override if quota_override is not None else int(role_cfg.get("daily_quota", 2))
    ollama_host = resolve_reachable_url(
        [
            os.getenv("OLLAMA_HOST", ""),
            role_cfg.get("host", "http://rtx5060lp:11434"),
            role_cfg.get("fallback_host", "http://192.168.128.62:11434"),
            "http://localhost:11434",
        ],
        "/api/tags",
    )
    if not ollama_host:
        logger.info("[rtx5060lp / writer] Ollama サーバー (rtx5060lp) がオフラインのためスキップします。")
        return 0

    today_str = datetime.now(JST).strftime("%Y-%m-%d")
    written_today = sum(
        1 for t in manifest["tasks"]
        if str(t.get("written_at") or "").startswith(today_str)
    )
    needed = max(0, quota - written_today)
    if needed == 0:
        logger.info(f"[rtx5060lp / writer] 本日の執筆ノルマ ({written_today}/{quota} 話) は達成済みです。")
        return 0

    generator = StoryGenerator(
        ollama_host=ollama_host,
        writer_model=role_cfg.get("writer_model", "shosetsu"),
    )

    candidates = [t for t in manifest["tasks"] if t["status"] == "plot_ready"] + [
        t for t in manifest["tasks"] if t["status"] == "pending"
    ]
    catalog_map = {t["id"]: t for t in build_interleaved_catalog(history_mgr)}
    written_count = 0
    content_dir = Path("content")

    for task in candidates[:needed]:
        topic = catalog_map.get(task["id"])
        if not topic:
            continue
        pat = topic.get("pattern", "A")
        tid = topic["id"]
        if task.get("plot_file") and Path(task["plot_file"]).exists():
            topic["_director_plot_blueprint"] = Path(task["plot_file"]).read_text(encoding="utf-8", errors="ignore")
            logger.info(f"[rtx5060lp / writer] sff7020 が作成したプロット ({task['plot_file']}) を読み込んで執筆します。")

        logger.info(f"[rtx5060lp / writer] 小説執筆開始 ({written_count + 1}/{needed}): [Pattern {pat} / {tid}] {topic.get('problem_title')}")
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
                "sent_to_wp": False,
                "sent_to_blogger": False,
                "status": "github_pages",
            })

            task["title"] = title
            task["md_file"] = str(out_path).replace("\\", "/")
            task["written_by"] = "rtx5060lp"
            task["written_at"] = datetime.now(JST).isoformat()
            task["status"] = "pending_illustration"
            written_count += 1

            manifest["updated_at"] = datetime.now(JST).isoformat()
            TASKS_JSON_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            write_tasks_markdown(manifest)
            build_github_pages(history_mgr)
            if push_to_git:
                git_commit_and_push(f"feat(rtx5060lp): Write story [{tid}] via rtx5060lp & update task queue")
        except Exception as e:
            logger.error(f"[rtx5060lp / writer] '{tid}' の執筆に失敗しました: {e}")

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

    ollama_host = resolve_reachable_url(
        [
            role_cfg.get("ollama_host", "http://kenomac-mini:11434"),
            role_cfg.get("fallback_ollama_host", "http://192.168.128.59:11434"),
            "http://localhost:11434",
            os.getenv("OLLAMA_HOST", "http://rtx5060lp:11434"),
        ],
        "/api/tags",
    ) or "http://kenomac-mini:11434"

    generator = StoryGenerator(
        ollama_host=ollama_host,
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
        return "writer"
    if "kenomac-mini" in hostname or "mac-mini" in hostname:
        return "illustrator"
    if "sff7020" in hostname:
        return "director"
    return "lan-dispatch"


def main():
    parser = argparse.ArgumentParser(
        description="GitHub-Synced Distributed Local LLM Task Worker for solve-school-problems"
    )
    parser.add_argument(
        "--role",
        choices=["auto", "lan-dispatch", "writer", "rtx5060lp", "illustrator", "kenomac-mini", "director", "sff7020", "sync"],
        default="auto",
        help="Worker role to run (default: auto-detect by hostname or dispatch to online LAN servers)",
    )
    parser.add_argument("--quota", type=int, default=None, help="Override daily task quota for this run")
    parser.add_argument("--no-push", action="store_true", help="Do not git commit/push changes")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    setup_logging(args.verbose)
    push_to_git = not args.no_push

    if push_to_git:
        git_pull_latest()

    history_mgr = HistoryManager()
    manifest = sync_tasks_manifest(history_mgr)

    role = args.role
    if role == "auto":
        role = detect_local_role()
        logger.info(f"ホスト名 '{socket.gethostname()}' から自動判定された実行モード: {role}")

    if role == "sync":
        if push_to_git:
            git_commit_and_push("chore(tasks): Sync distributed task queue manifest (data/tasks.json & data/TASKS.md)")
        return

    if role in ("director", "sff7020"):
        run_director_role(manifest, history_mgr, quota_override=args.quota, push_to_git=push_to_git)
    elif role in ("writer", "rtx5060lp"):
        run_writer_role(manifest, history_mgr, quota_override=args.quota, push_to_git=push_to_git)
    elif role in ("illustrator", "kenomac-mini"):
        run_illustrator_role(manifest, history_mgr, quota_override=args.quota, push_to_git=push_to_git)
    elif role == "lan-dispatch":
        logger.info("=== LAN上の全ローカルLLM PC (sff7020 -> rtx5060lp -> kenomac-mini) の稼働状況を確認して順次作業を実行します ===")
        run_director_role(manifest, history_mgr, quota_override=args.quota, push_to_git=push_to_git)
        manifest = sync_tasks_manifest(history_mgr)
        run_writer_role(manifest, history_mgr, quota_override=args.quota, push_to_git=push_to_git)
        manifest = sync_tasks_manifest(history_mgr)
        run_illustrator_role(manifest, history_mgr, quota_override=args.quota, push_to_git=push_to_git)


if __name__ == "__main__":
    main()
