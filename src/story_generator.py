import os
import re
import json
import time
import random
import base64
import logging
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional, Callable

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))

SYSTEM_PROMPT_A = """あなたは学校教育・学級経営に精通した実力派教育作家であり、教育学・教育心理学・教育哲学の学術研究者です。
新米教員が学校現場や教室で直面する切実な悩み・トラブルを、先輩教員の温かく鋭い学術的助言によって解決へ導く、感動的かつ実践的な教育小説（本文約3,500〜4,000文字）を執筆してください。

【執筆の厳格な要件（パターンA：教育相談・学術理論アプローチ）】
1. **登場人物と対話のリアリティ**:
   - 新米教員（若手・初任者〜数年目）と、経験豊富で学識ある先輩教員（指導教諭、主幹教諭、ベテラン教員など）の生き生きとした対話劇を中心に描いてください。
   - 教室での子どもたちの生々しい反応や職員室の空気感、新米教員の焦りや戸惑い、先輩教員の受容と的確な洞察をドラマチックに描写してください。
   - 発言者が誰かわかるよう、ト書き（「〜と若葉先生はうなだれた」「〜と神崎先生は穏やかにカップを置いた」等）を自然に添えてください。
2. **【起】【承】【転】【結】などの記号・見出しや「パターンA：〜」等のラベルは本文中に入れないこと**:
   - 物語の冒頭や途中に「パターンA：新米教員 × 先輩教員」「【起】」「【承】」といったラベルや見出しを絶対に入れないでください。自然な小説本文から直接開始してください。
   - シーン転換には、空行または「* * *」を用いてください。
3. **学術的エビデンス・理論の自然な導入**:
   - 先輩教員のアドバイスには、教育学、教育心理学、教育哲学における実在の学術論文、古典的名著、認知・行動科学の理論（自己決定理論、足場かけ、認知的負荷理論、成長マインドセット、ケアの倫理、対話主義等）を具体的に織り込んでください。
   - ただし、単なる講釈や説教にならず、新米教員が「明日からの教室ですぐに試せる具体的な行動・声かけ」に翻訳されたアドバイスにしてください。
4. **全体の構成（三部構成）**:
   - **第一部：小説本文**（約3,500〜4,000文字、起承転結を内包した深みのあるストーリー）
   - **第二部：【作中理論・教育学のやさしい解説（Theoretical Commentary）】**
     （作中に登場した教育学・教育心理学・教育哲学の理論について、一般読者や教員志望者にもわかりやすく要点と実践のポイントを解説してください）
   - **第三部：【引用・参考文献（Academic References）】**
     （実在する学術論文、著者名、論文タイトル、ジャーナル名/書籍名、発表年、およびクリック可能な正規URLを明記してください。**URLリンクは必ず「参考文献の手がかり」に提示された検証済みURLをそのまま使用し、それ以外の文献には独自の推測URLや括弧付きの古いDOIを絶対に付与しないでください（書誌情報のみ記載）**）
"""

SYSTEM_PROMPT_B = """あなたは学校教育と最新のコンピュータ技術・ネットワーク工学に精通したIT教育作家であり、校務DXコンサルタントです。
年配教員が学校現場の煩雑な事務作業や機器トラブルで途方に暮れているところへ、若手教員がコンピュータ技術やネットワークの知見を活かして鮮やかに解決する、痛快で心温まる校務DX小説（本文約3,500〜4,000文字）を執筆してください。

【執筆の厳格な要件（パターンB：校務DX・ICTネットワーク解決）】
1. **登場人物と対話のリアリティ**:
   - 長年学校を支えてきたがデジタル化や煩雑な手作業に悩む年配教員（教務主任、学年主任、副校長など）と、IT技術やプログラミング、ネットワークに明るい若手教員の対話劇を描いてください。
   - 若手教員は年配教員の教育的知恵や生徒への熱意を敬い、年配教員は若手の技術とスピード感に感銘を受けるという、世代間のリスペクトと温かい協働を描いてください。
   - 発言者が誰かわかるよう、ト書き（「〜と大山先生は老眼鏡を押し上げた」「〜と水野先生は画面を指さした」等）を自然に添えてください。
2. **【起】【承】【転】【結】などの記号・見出しや「パターンB：〜」等のラベルは本文中に入れないこと**:
   - 物語の冒頭や途中に「パターンB：年配教員 × 若手教員」「【起】」「【承】」といったラベルや見出しを絶対に入れないでください。自然な小説本文から直接開始してください。
   - シーン転換には、空行または「* * *」を用いてください。
3. **具体的で実用的なテクノロジー・ネットワーク知見**:
   - Google Apps Script (GAS)、Google Workspace、Excel/VBA、Python、正規表現、Wi-Fi周波数帯（2.4GHz/5GHz/Wi-Fi 6E/DFS）、ネットワークACL、バージョン管理、クラウド連携、QRコードなど、現場で実際に使える最新のコンピュータ・ネットワーク技術を論理的に解説・適用してください。
4. **全体の構成（三部構成）**:
   - **第一部：小説本文**（約3,500〜4,000文字、業務の壁を技術で突破する爽快なストーリー）
   - **第二部：【作中技術・ITネットワークのやさしい解説（Technical Commentary）】**
     （作中に登場したコンピュータ技術、スクリプト、ネットワーク規格の仕組みを、ITが苦手な教員でも理解できるよう丁寧に解説してください）
   - **第三部：【引用・参考文献（Technical References & Domestic Guidelines）】**
     （文部科学省のGIGAスクール・校務DXガイドライン、総務省・デジタル庁・IPAの公的資料、GoogleやMicrosoftの公式日本語サポートなど、日本の学校教員が実際にアクセスして役立つ国内の公式URL `[https://...](https://...)` を明記してください。学校現場の教員向けとして不適切なため、IEEE、Cisco、RFC、NIST等の英語・専門的すぎる海外ネットワーク規格サイトは絶対に掲載しないでください）
"""

SYSTEM_PROMPT_C = """あなたは学校法務および教育行政に精通した実力派作家であり、教育法学・学校マネジメントの研究者です。
校長先生が学校現場で起こった困難なトラブルや判断に迷う重大課題に直面し、指導主事や教育委員会に問い合わせ・相談しながら、教育基本法や学校教育法、いじめ防止対策推進法などの法律・法規・判例に基づき、適法かつ毅然とした判断・問題解決へ導く、重厚で示唆に富む教育法務小説（本文約3,500〜4,000文字）を執筆してください。

【執筆の厳格な要件（パターンC：校長×指導主事・教育法制アプローチ）】
1. **登場人物と対話のリアリティ**:
   - 学校の最終責任者として苦悩する校長先生と、法規・行政実務に精通した教育委員会（指導主事・管理主事等）の緊迫感と信頼感ある対話劇を描いてください。
   - 校内での教職員や保護者の反応、学校現場でありがちな「前例踏襲」や「穏便に済ませたい心理」と、法令に基づく公正・適法な判断との間の葛藤をリアルに描写してください。
   - 発言者が誰かわかるよう、ト書き（「〜と青木校長は受話器を握りしめた」「〜と黒田指導主事は静かに条文を読み上げた」等）を自然に添えてください。
2. **【起】【承】【転】【結】などの記号・見出しや「パターンC：〜」等のラベルは本文中に入れないこと**:
   - 物語の冒頭や途中に「パターンC：校長先生 × 指導主事」「【起】」「【承】」といったラベルや見出しを絶対に入れないでください。自然な小説本文から直接開始してください。
   - シーン転換には、空行または「* * *」を用いてください。
3. **具体的な法律・条文・判例・文科省ガイドラインの適用**:
   - 教育基本法、学校教育法、いじめ防止対策推進法、学校保健安全法、地方公務員法、児童虐待防止法、教育機会確保法などの実在する条文番号や判例法理を物語の中で明快に位置づけ、校長が法的確信を持って決断・行動する根拠としてください。
4. **全体の構成（三部構成）**:
   - **第一部：小説本文**（約3,500〜4,000文字、法的判断により子どもと学校を守る重厚なストーリー）
   - **第二部：【作中法規・教育法制のやさしい解説（Legal Commentary）】**
     （作中に登場した法律の条文趣旨、学校現場における解釈の要点、校長・教職員が留意すべきポイントをわかりやすく解説してください）
   - **第三部：【引用・参考文献（Legal References & e-Gov Links）】**
     （実在する法律のe-Gov法令検索リンク `[https://laws.e-gov.go.jp/document?lawid=...](https://laws.e-gov.go.jp/document?lawid=...)` や文部科学省公式ガイドラインの正規URLを明記してください）
"""

DEFAULT_OLLAMA_HOST = "http://192.168.128.59:11434"
DEFAULT_WRITER_MODEL = "gemma4:12b"
DEFAULT_DRAW_THINGS_HOST = "http://192.168.128.59:7860"

LOCAL_FALLBACK_MODELS = [
    "gemma4:12b",
    "qwen3.5:9b",
    "qwen2.5:14b",
    "gemma2:9b",
]


class StoryGenerator:
    """
    Generates school problem solving stories using Mac mini M4 Local LLM via Ollama (no external AI APIs),
    and generates 512x512 illustrations via Mac mini Ollama (gemma4:12b) + Draw Things HTTP API (FLUX.2 [klein] 4B).
    Alternates between Pattern A (Pedagogy/Psychology), Pattern B (ICT/Networking), and Pattern C (School Law).
    Outputs rich Markdown with Frontmatter, Technical/Legal Commentary, and Verified References.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        ollama_host: Optional[str] = None,
        writer_model: Optional[str] = None,
        draw_things_host: Optional[str] = None,
    ):
        self.api_key = None  # External AI APIs are disabled
        self.ollama_host = (ollama_host or os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)).rstrip("/")
        self.writer_model = writer_model or os.getenv("OLLAMA_WRITER_MODEL", DEFAULT_WRITER_MODEL)
        self.draw_things_host = (draw_things_host or os.getenv("DRAW_THINGS_HOST", DEFAULT_DRAW_THINGS_HOST)).rstrip("/")

    def _get_local_model_candidates(self, available_models: List[str]) -> List[str]:
        """Returns ordered list of local Ollama models to try."""
        candidates = [self.writer_model]
        for m in LOCAL_FALLBACK_MODELS:
            if m not in candidates and (not available_models or m in available_models):
                candidates.append(m)
        return candidates

    def _ensure_frontmatter(self, text: str, pattern: str, topic: Dict[str, Any]) -> Tuple[str, str]:
        """Ensures the generated Markdown starts with valid YAML frontmatter and extracts the clean title."""
        default_title = topic.get("problem_title", "学校の課題を解決する物語")
        tid = topic.get("id", f"{pattern}01")
        cat = topic.get("category", "学校課題解決")
        if pattern == "A":
            tags_str = '["教育学", "教育心理学", "学級経営", "生徒指導", "若手教員育成", "Aパターン"]'
        elif pattern == "B":
            tags_str = '["校務DX", "学校ICT", "業務効率化", "プログラミング", "ネットワーク", "Bパターン"]'
        else:
            tags_str = '["学校法制", "教育法規", "教育委員会", "学校管理職", "校長", "Cパターン"]'

        title_match = re.search(r'title:\s*["\']?(.*?)["\']?\s*\n', text)
        if not title_match:
            h1_match = re.search(r'^#\s+(.+)$', text, flags=re.MULTILINE)
            title = h1_match.group(1).strip().strip("『』\"'") if h1_match else default_title
        else:
            title = title_match.group(1).strip().strip("『』\"'")

        if not text.lstrip().startswith("---"):
            safe_title = title.replace('"', '\\"')
            fm = (
                f"---\n"
                f'title: "{safe_title}"\n'
                f'pattern: "{pattern}"\n'
                f'category: "{cat}"\n'
                f"tags: {tags_str}\n"
                f'topic_id: "{tid}"\n'
                f"---\n\n"
            )
            text = fm + text.lstrip()
        return text, title

    def _build_anti_duplication_prompt(self, topic: Dict[str, Any]) -> str:
        """Builds explicit instructions to prevent overlapping with previously published stories."""
        repeat_count = topic.get("_repeat_count", 0)
        same_topic_titles = topic.get("_same_topic_past_titles", [])
        recent_titles = topic.get("_recent_pattern_titles", [])

        parts = []
        if recent_titles:
            joined_recent = "\n".join(f"  - 『{t}』" for t in recent_titles)
            parts.append(
                f"\n【過去の配信済み記事タイトル一覧（重複・類似表現の厳禁）】\n"
                f"これまでに同パターンで以下の記事が配信されています。タイトル、比喩表現、導入シーン、結末の演出がこれら過去の記事と重ならないよう、完全に独自の新しい切り口・タイトルで執筆してください:\n"
                f"{joined_recent}\n"
            )

        if repeat_count > 0 or same_topic_titles:
            joined_same = ", ".join(f"『{t}』" for t in same_topic_titles) if same_topic_titles else "過去記事"
            parts.append(
                f"\n【最重要：新シチュエーション・新キャラクター創出指示（第{repeat_count + 1}巡目）】\n"
                f"- このテーマ領域（{topic.get('id')}）では、過去に {joined_same} が執筆されています。\n"
                f"- 過去の記事と内容が絶対に重ならないよう、上記の基本設定にある「登場人物の名前」「学年・校種（小学校・中学校・高校・特別支援学級）」「教科・行事・部活動」「トラブルの具体的なきっかけ」を**すべて新しく作り変えて（刷新して）**執筆してください。\n"
                f"- 拠って立つ理論・技術・法令の核心（{topic.get('solution_framework', '')}）は活かしつつ、まったく別の学校・別の先生・別の具体的なエピソードとして、読者が『全く新しい物語だ』と新鮮に感動できるオリジナルストーリーを構築してください。\n"
            )

        return "".join(parts)

    def generate_story(
        self,
        pattern: str,
        topic: Dict[str, Any],
        use_local_llm: bool = False,
    ) -> Tuple[str, str, List[str]]:
        """
        Generates a complete story based on pattern ('A', 'B', or 'C') and topic info
        using Mac mini M4 Local LLM via Ollama (no external AI APIs).
        Returns: (markdown_content, title, list_of_references)
        """
        if not use_local_llm:
            logger.info("Offline/unit-test mode (use_local_llm=False). Returning built-in template story.")
            return self._generate_fallback(pattern, topic)

        anti_dup_block = self._build_anti_duplication_prompt(topic)

        if pattern == "A":
            system_instruction = SYSTEM_PROMPT_A
            user_prompt = f"""以下の教育現場の課題と理論をもとに、新米教員と先輩教員の教育相談短編小説（本文約3,500〜4,000文字＋理論解説＋参考文献）を執筆してください。

【今回の課題テーマ（パターンA：教育相談・学術理論アプローチ）】
- テーマID: {topic.get('id', 'A01')}
- カテゴリ: {topic.get('category', '学級経営')}
- 相談内容: {topic.get('problem_title', '生徒が指示待ちになってしまう')}
- 登場人物設定:
  - 新米教員: {topic.get('roles', {}).get('novice', '初任者教員')}
  - 先輩教員: {topic.get('roles', {}).get('senior', '指導教諭')}
- 教室の具体的状況: {topic.get('situation', '')}
- 拠って立つ学術理論・エビデンス: {topic.get('solution_framework', '')}
- キー理論・概念: {', '.join(topic.get('key_theories', []))}
- 参考文献の手がかり: {', '.join(topic.get('reference_hints', []))}
{anti_dup_block}
【必須ルール】
1. タイトルは過去の記事と絶対に重ならない、魅力的で文学的なものにしてください。
2. 本文中に【起】【承】【転】【結】などの記号や見出しは一切入れないでください。シーン転換は空行または「* * *」を使用してください。
3. 新米教員の等身大の焦りと、先輩教員の深い学術的見識に基づく具体的助言を、リアルな対話劇として描写してください。
4. 本文は約3,500〜4,000文字のスケールにしてください。
5. 本文の後に必ず【作中理論・教育学のやさしい解説（Theoretical Commentary）】を設け、一般読者にもわかりやすく要点と実践のポイントを解説してください。
6. 最後に必ず【引用・参考文献（Academic References）】を設け、実在する学術論文、DOIハイパーリンク `[https://doi.org/...](https://doi.org/...)` または公的URLを明記してください。海外論文・洋書のリンク切れを防ぐため、架空のDOIや推測URLは絶対に記載せず、「参考文献の手がかり」に示された実在論文や検証済みの正規DOIリンクを最優先してください。
7. 冒頭にYAML Frontmatterを配置してください:
---
title: "タイトル"
pattern: "A"
category: "{topic.get('category', '学級経営')}"
tags: ["教育学", "教育心理学", "学級経営", "生徒指導", "若手教員育成", "Aパターン"]
topic_id: "{topic.get('id', 'A01')}"
---
"""
        elif pattern == "B":
            system_instruction = SYSTEM_PROMPT_B
            user_prompt = f"""以下の学校現場の校務課題とIT技術をもとに、年配教員と若手教員の校務DX短編小説（本文約3,500〜4,000文字＋技術解説＋参考文献）を執筆してください。

【今回の課題テーマ（パターンB：校務DX・ICTネットワーク解決）】
- テーマID: {topic.get('id', 'B01')}
- カテゴリ: {topic.get('category', '校務自動化')}
- 課題内容: {topic.get('problem_title', '成績処理の手計算ミス')}
- 登場人物設定:
  - 年配教員: {topic.get('roles', {}).get('veteran', '年配教諭')}
  - 若手教員: {topic.get('roles', {}).get('young', '若手教諭')}
- 職員室の具体的状況: {topic.get('situation', '')}
- 解決に用いる技術・ネットワーク知見: {topic.get('solution_framework', '')}
- キーテクノロジー: {', '.join(topic.get('key_technologies', []))}
- 参考文献の手がかり: {', '.join(topic.get('reference_hints', []))}
{anti_dup_block}
【必須ルール】
1. タイトルは過去の記事と絶対に重ならない、魅力的で技術と情熱が伝わるものにしてください。
2. 本文中に【起】【承】【転】【結】などの記号や見出し、および「パターンB：〜」等のラベルは一切入れないでください。シーン転換は空行または「* * *」を使用してください。
3. 年配教員の苦労と教育愛をリスペクトしつつ、若手教員がIT技術とネットワークの力で鮮やかに負担を激減させる爽快な協働ドラマを描いてください。
4. 本文は約3,500〜4,000文字のスケールにしてください。
5. 本文の後に必ず【作中技術・ITネットワークのやさしい解説（Technical Commentary）】を設け、ITが苦手な方にもわかりやすく技術の仕組みと実践法を解説してください。
6. 最後に必ず【引用・参考文献（Technical References & Domestic Guidelines）】を設け、日本の学校教員が実務で役立てられる【国内の公的機関（文部科学省、総務省、デジタル庁、IPA等）のガイドライン】や【Google/Microsoftの日本語公式ヘルプ・マニュアル】の正規URL `[https://...](https://...)` を明記してください。学校教員が読んでも意味のないIEEE、Cisco、RFC等の英語・専門的すぎる海外規格サイトは絶対に避け、「参考文献の手がかり」に示された国内公的資料・公式日本語マニュアルを活用してください。
7. 冒頭にYAML Frontmatterを配置してください:
---
title: "タイトル"
pattern: "B"
category: "{topic.get('category', '校務自動化')}"
tags: ["校務DX", "学校ICT", "業務効率化", "プログラミング", "ネットワーク", "Bパターン"]
topic_id: "{topic.get('id', 'B01')}"
---
"""
        else:
            system_instruction = SYSTEM_PROMPT_C
            user_prompt = f"""以下の学校現場の重大課題と教育法制をもとに、校長先生と指導主事・教育委員会の教育法務短編小説（本文約3,500〜4,000文字＋法規解説＋法律リンク）を執筆してください。

【今回の課題テーマ（パターンC：校長×指導主事・教育法制アプローチ）】
- テーマID: {topic.get('id', 'C01')}
- カテゴリ: {topic.get('category', '学校法制・いじめ防止')}
- 課題内容: {topic.get('problem_title', '重大事態の疑いがあるいじめ問題への対応')}
- 登場人物設定:
  - 校長先生: {topic.get('roles', {}).get('principal', '校長先生')}
  - 指導主事/教育委員会: {topic.get('roles', {}).get('supervisor', '教育委員会指導主事')}
- 学校現場の具体的状況: {topic.get('situation', '')}
- 拠って立つ教育法規・判例・指針: {topic.get('solution_framework', '')}
- キー法令・条文: {', '.join(topic.get('key_laws', []))}
- 参考文献の手がかり: {', '.join(topic.get('reference_hints', []))}
{anti_dup_block}
【必須ルール】
1. タイトルは過去の記事と絶対に重ならない、重厚で法と教育の葛藤と決断が伝わるものにしてください。
2. 本文中に【起】【承】【転】【結】などの記号や見出し、および「パターンC：〜」等のラベルは一切入れないでください。シーン転換は空行または「* * *」を使用してください。
3. 学校の最終責任者である校長の責任と苦悩、そして指導主事による法規に基づいた客観的かつ心強い法的助言を、緊迫感ある対話劇として描写してください。
4. 本文は約3,500〜4,000文字のスケールにしてください。
5. 本文の後に必ず【作中法規・教育法制のやさしい解説（Legal Commentary）】を設け、教育基本法や学校教育法等の条文趣旨と現場での判断ポイントをわかりやすく解説してください。
6. 最後に必ず【引用・参考文献（Legal References & e-Gov Links）】を設け、実在する法律のe-Gov法令検索リンク `[https://laws.e-gov.go.jp/document?lawid=...](https://laws.e-gov.go.jp/document?lawid=...)` や文部科学省公式ガイドラインの正規URLを明記してください。
7. 冒頭にYAML Frontmatterを配置してください:
---
title: "タイトル"
pattern: "C"
category: "{topic.get('category', '学校法制・いじめ防止')}"
tags: ["学校法制", "教育法規", "教育委員会", "学校管理職", "校長", "Cパターン"]
topic_id: "{topic.get('id', 'C01')}"
---
"""

        last_error = None
        ollama_status = self.check_ollama_connection()
        if ollama_status.get("online"):
            candidates = self._get_local_model_candidates(ollama_status.get("models", []))
            for model_name in candidates:
                try:
                    logger.info(f"[Ollama: {model_name}] Generating story via Mac mini M4 Local LLM...")
                    raw_text = self.call_ollama_chat(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": user_prompt},
                        ],
                        temperature=0.72,
                        num_predict=6000,
                        num_ctx=8192,
                        timeout=600,
                    )
                    text = raw_text.strip()
                    if text.startswith("```markdown"):
                        text = text[len("```markdown"):].strip()
                    if text.startswith("```"):
                        text = text[3:].strip()
                    if text.endswith("```"):
                        text = text[:-3].strip()
                    if len(text) >= 1200:
                        text = self._verify_and_sanitize_links(text)
                        text, title = self._ensure_frontmatter(text, pattern, topic)
                        refs = re.findall(r'\((https?://[^\s\)]+)\)', text)
                        logger.info(
                            f"Successfully generated story using Mac mini M4 Ollama '{model_name}'! "
                            f"Title: {title}, Length: {len(text)} chars"
                        )
                        return text, title, refs
                    else:
                        logger.warning(f"Ollama model '{model_name}' output too short ({len(text)} chars). Trying next...")
                except Exception as e:
                    last_error = e
                    logger.warning(f"Ollama story generation with '{model_name}' failed: {e}")

        logger.error(f"Local LLM attempts exhausted or offline ({last_error}). Falling back to template.")
        return self._generate_fallback(pattern, topic)

    def _sanitize_url(self, url: str) -> str:
        """Removes stray backslashes and percent-encodes parentheses and non-ASCII chars in URLs."""
        url = url.replace("\\", "").strip()
        try:
            parts = urllib.parse.urlsplit(url)
            path = urllib.parse.quote(urllib.parse.unquote(parts.path), safe="/:@&=+$,-_.!~*'")
            query = urllib.parse.quote(urllib.parse.unquote(parts.query), safe="/:@&=+$,-_.!~*'*?")
            fragment = urllib.parse.quote(urllib.parse.unquote(parts.fragment), safe="/:@&=+$,-_.!~*'")
            return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, fragment))
        except Exception:
            return url

    def _check_egov_lawid(self, lawid: str) -> bool:
        """Checks if an e-Gov lawid actually exists via the official e-Gov Law API."""
        api_url = f"https://laws.e-gov.go.jp/api/1/lawdata/{urllib.parse.quote(lawid)}"
        try:
            req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as res:
                if res.getcode() == 200:
                    body = res.read().decode("utf-8", errors="ignore")
                    return "<Code>0</Code>" in body
        except urllib.error.HTTPError as e:
            if e.code in (400, 404, 410, 500):
                return False
            return True
        except Exception:
            return True
        return False

    def _resolve_egov_lawid(self, lawid: str) -> Optional[str]:
        """
        Verifies an e-Gov lawid and, if invalid, automatically attempts common
        Cabinet-bill vs Member-bill (AC0000000 <-> AC1000000) or ministerial code corrections.
        """
        if self._check_egov_lawid(lawid):
            return lawid

        candidates = []
        if "AC0000000" in lawid:
            candidates.append(lawid.replace("AC0000000", "AC1000000"))
        elif "AC1000000" in lawid:
            candidates.append(lawid.replace("AC1000000", "AC0000000"))

        for m_from, m_to in [("M50000", "M40000"), ("M40000", "M50000"), ("M60000", "M50000")]:
            if m_from in lawid:
                candidates.append(lawid.replace(m_from, m_to))

        for cand in candidates:
            if self._check_egov_lawid(cand):
                logger.info(f"Auto-corrected e-Gov lawid '{lawid}' -> '{cand}' via e-Gov API.")
                return cand

        return None

    def _is_url_alive(self, url: str) -> bool:
        """Verifies DOIs via official Handle API, e-Gov laws via e-Gov API, and regular URLs via HTTP request."""
        try:
            # 1. If e-Gov link, verify via official e-Gov API (since SPA shell always returns 200)
            egov_match = re.search(r'laws\.e-gov\.go\.jp/(?:document\?lawid=|law/)([A-Za-z0-9_]+)', url, re.I)
            if egov_match:
                return self._resolve_egov_lawid(egov_match.group(1)) is not None

            # 2. If DOI link, check official Handle API (fast, immune to publisher anti-bot 403)
            doi_match = re.match(r'^https?://(?:dx\.)?doi\.org/(10\.\d{4,9}/.+)$', url, re.I)
            if doi_match:
                doi_raw = urllib.parse.unquote(doi_match.group(1))
                api_url = f"https://doi.org/api/handles/{urllib.parse.quote(doi_raw, safe='/')}"
                req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=8) as res:
                    data = json.loads(res.read().decode("utf-8", errors="ignore"))
                    return data.get("responseCode") == 1

            # 3. Regular web URL: check HTTP status
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=8) as res:
                return 200 <= res.getcode() < 400
        except urllib.error.HTTPError as e:
            if e.code in (404, 410, 500):
                return False
            # 403/429 on non-DOI academic portals may be bot protection, keep if not 404
            return e.code not in (404, 410)
        except urllib.error.URLError:
            return False
        except Exception:
            return True

    def _verify_and_sanitize_links(self, text: str) -> str:
        """Sanitizes parentheses in all markdown links, auto-corrects e-Gov lawids, and strips dead/404 links."""
        def _replacer(match):
            label = match.group(1).replace("\\(", "(").replace("\\)", ")")
            raw_url = match.group(2)
            safe_url = self._sanitize_url(raw_url)

            # Auto-correct e-Gov lawid if Cabinet vs Member bill code was swapped
            egov_match = re.search(r'laws\.e-gov\.go\.jp/(?:document\?lawid=|law/)([A-Za-z0-9_]+)', safe_url, re.I)
            if egov_match:
                orig_id = egov_match.group(1)
                resolved_id = self._resolve_egov_lawid(orig_id)
                if resolved_id:
                    safe_url = safe_url.replace(orig_id, resolved_id)
                    label = label.replace(orig_id, resolved_id)
                    return f"[{label}]({safe_url})"
                logger.warning(f"Stripping invalid e-Gov law URL from generated story: {raw_url}")
                if label.startswith("http://") or label.startswith("https://"):
                    return ""
                return label

            if self._is_url_alive(safe_url):
                return f"[{label}]({safe_url})"
            logger.warning(f"Stripping dead/unreachable URL from generated story: {raw_url}")
            if label.startswith("http://") or label.startswith("https://"):
                return ""
            return label

        return re.sub(
            r"\[([^\]]+)\]\((https?://(?:[^\s\(\)]|\\?\([^\s\(\)]*\\?\))+)\)",
            _replacer,
            text
        )

    def _generate_fallback(self, pattern: str, topic: Dict[str, Any]) -> Tuple[str, str, List[str]]:
        """Provides a high-quality pre-written story template if offline or API key is absent."""
        if pattern == "A":
            title = "教室の沈黙と自己決定――新米教員が学ぶ内発的動機づけの理論"
            content = f"""---
title: "{title}"
pattern: "A"
category: "{topic.get('category', '学級経営・内発的動機づけ')}"
tags: ["教育学", "教育心理学", "学級経営", "自己決定理論", "若手教員育成", "Aパターン"]
topic_id: "{topic.get('id', 'A01')}"
---

初夏の風が吹き抜ける放課後の第二職員室。静まり返った室内で、初任者の若葉先生は、机の上に広げた学級日誌を前に深いため息をついた。
教員になって二ヶ月。中学二年生の担任を任された若葉は、クラスをまとめようと懸命だった。規律を正し、提出物の期限を厳守させ、授業中の私語をなくすため、毎日のように注意を重ねてきた。だが、その結果生まれたのは、整然とした秩序ではなく、重苦しい沈黙だった。
生徒たちは指示されたこと以外は一切口を開かず、質問を投げかけても誰一人として目を合わせようとしない。係活動も「言われたからやる」だけの形骸化した作業になっていた。

「若葉先生、まだ残っていたのかい」
温かいコーヒーの香りと共に声をかけてきたのは、学年主任であり教職二十年目を迎えるベテランの神崎先生だった。
「あ、神崎先生……お疲れ様です。実は、クラスのことで……」
若葉は堰を切ったように、ここ数週間の苦悩を吐露した。規律を守らせようとすればするほど、生徒たちの瞳から活気が失われ、まるで操り人形のようになってしまったことへの焦燥感。

神崎先生はコーヒーカップを口元に運び、静かに微笑んだ。
「若葉先生、よく頑張っているね。君が生徒たちを想って真摯に向き合っているからこその悩みだ。だがね、人は外からの強い力で縛られれば縛られるほど、内側にあるエンジンの火を消してしまうものなんだよ」
「外からの力、ですか……」
「そう。心理学者のエドワード・デシとリチャード・ライアンが提唱した『自己決定理論（Self-Determination Theory）』を知っているかい？」
神崎先生は手元のメモ用紙にペンを走らせ、三角形を描いた。

「人間が何かに熱中し、自ら進んで行動する『内発的動機づけ』には、三つの基本的心理欲求が満たされる必要がある。一つ目は**自律性の欲求（Autonomy）**――自分の意思で選択し行動しているという感覚。二つ目は**有能感の欲求（Competence）**――自分にはできる、成長しているという手応え。そして三つ目が**関係性の欲求（Relatedness）**――周囲に認められ、安心できるつながりがあるという感覚だ」
神崎先生は若葉の目をまっすぐに見つめた。
「若葉先生、君のこれまでの指導は、善意から出たものであっても、生徒たちの『自律性』を奪う『統制型の指導（Controlling Style）』になっていたのかもしれない。ルールを守らせるために罰や評価をちらつかせると、生徒は『怒られないためにやる』という最も外発的な動機に縛られてしまうんだ」

若葉の胸に、鋭い痛みが走った。確かに、自分は「こうしなさい」「なぜやらないの」と指示ばかりを出し、生徒自身が選ぶ余地を一切与えていなかった。
「では、私はどうすれば……」
「明日から、指導を『自律性支援型（Autonomy-Supportive Style）』へとシフトしてみよう。方法はシンプルだ。まず第一に、ルールを一方的に押し付けるのではなく、『なぜそのルールが必要なのか』の意味と価値を丁寧に説明すること。第二に、小さなことでもいいから、生徒たち自身に選択肢を与えること。『掃除のやり方を班で決めてごらん』『この課題の提出方法はAとBのどちらが良いかい？』とね。そして第三に、生徒が否定的な感情を抱いたとき、それを頭ごなしに叱るのではなく『そう感じるのも無理はないね』と一度受け止めることだ」

神崎先生のアドバイスを胸に、若葉は翌日の学級活動に臨んだ。
教室の教壇に立った若葉は、深呼吸をして生徒たちを見渡した。
「みんな、いつも先生が指示ばかり出して、窮屈な思いをさせてしまっていたね。ごめんなさい」
生徒たちが驚いたように顔を上げた。
「来週の合唱コンクールの自由曲についてだけど、先生が決めるのではなく、各パートのリーダーとみんなで話し合って決めてほしい。どの曲が自分たちのクラスに合っているか、みんなの意見を聞かせてほしいんだ」
最初は戸惑っていた生徒たちだったが、一人が「この曲、歌詞がすごくいいと思う」と声を上げたのを皮切りに、教室に生き生きとした意見の交わし合いが広がっていった。
教壇の脇でその様子を見つめながら、若葉は確信した。子どもたちの中には、最初から自ら燃え上がる火種があったのだ。自分はその火を囲う壁を作るのではなく、風を送る存在になればよかったのだと。

* * *

### 【作中理論・教育学のやさしい解説（Theoretical Commentary）】

本作で先輩教員が紹介した理論は、現代の教育心理学およびモチベーション研究において世界標準となっているエビデンスに基づくアプローチです。

1. **自己決定理論（Self-Determination Theory: SDT）**
   エドワード・デシ（Edward L. Deci）とリチャード・ライアン（Richard M. Ryan）によって体系化された動機づけの包括的理論です。人間は生まれながらに心理的成長と統合を目指す能動的な存在であり、以下の「3つの基本的心理欲求」が満たされることで自発的な学習意欲（内発的動機づけ）が高まります。
   - **自律性（Autonomy）**: 自らの行動を自分自身で決定・コントロールしているという感覚。
   - **有能感（Competence）**: 適切な挑戦を通じて自分の能力を発揮し、成長できているという感覚。
   - **関係性（Relatedness）**: 教員や仲間から無条件に受け入れられ、信頼されているという感覚。

2. **自律性支援型指導（Autonomy-Supportive Style）と統制型指導（Controlling Style）**
   ジョンマーシャル・リーヴ（Johnmarshall Reeve）らの研究によると、教員が命令や脅迫、罪悪感の喚起によって生徒を行動させる「統制型」の指導を行うと、一時的な服従は得られるものの、長期的には学習意欲の減退、ストレスの増大、指示待ち人間の固定化を招きます。
   対照的に、選択肢の提示、活動の教育的意義の説明、生徒の視点・感情への共感を行う「自律性支援型」の指導は、生徒の学力向上、主体的探究心、ウェルビーイングを著しく向上させることが実証されています。

---

### 【引用・参考文献（Academic References）】

1. Deci, E. L., & Ryan, R. M. (2000). The "what" and "why" of goal pursuits: Human needs and the self-determination of behavior. *Psychological Inquiry*, 11(4), 227-268.
   DOI: [https://doi.org/10.1207/S15327965PLI1104_01](https://doi.org/10.1207/S15327965PLI1104_01)

2. Reeve, J. (2009). Why teachers adopt a controlling motivating style toward students and how they can become more autonomy supportive. *Educational Psychologist*, 44(3), 159-175.
   DOI: [https://doi.org/10.1080/00461520903028990](https://doi.org/10.1080/00461520903028990)

3. Ryan, R. M., & Deci, E. L. (2017). *Self-determination theory: Basic psychological needs in motivation, development, and wellness*. Guilford Publications.
   DOI: [https://doi.org/10.1521/978.14625/28806](https://doi.org/10.1521/978.14625/28806)
"""
            return content, title, [
                "https://doi.org/10.1207/S15327965PLI1104_01",
                "https://doi.org/10.1080/00461520903028990",
                "https://doi.org/10.1521/978.14625/28806"
            ]
        elif pattern == "B":
            title = "深夜の成績集計とスプレッドシートの奇跡――年配教員を救うGASと配列数式"
            content = f"""---
title: "{title}"
pattern: "B"
category: "{topic.get('category', '校務自動化・スプレッドシート/GAS')}"
tags: ["校務DX", "学校ICT", "業務効率化", "Google Apps Script", "Bパターン"]
topic_id: "{topic.get('id', 'B01')}"
---

時計の針が夜の八時半を回った頃、職員室の片隅で、教務主任の大山先生が眉間に深いシワを寄せていた。
教職二十八年目。学校の生き字引として誰からも頼りにされる大山だったが、この時期ばかりは毎年地獄のような疲労に襲われる。学期末の全校生徒三百人分の総合成績一覧表の作成だ。
机の上には各教科担任から提出された紙の成績表の束。大山は老眼鏡を押し上げながら、電卓のテンキーをカチカチと叩き、その数値をパソコンの表計算ソフトに手動で転記していた。

「大山先生、まだ残っていらっしゃったんですか」
通りかかったのは、情報担当教諭として着任して三年目の若手、水野先生だった。
大山は疲れ切った顔で苦笑いを浮かべた。
「ああ、水野先生。なに、学期の締めくくりだからね。点数の合計や平均、欠席日数の照合を手計算で確認しているんだが……数字が合わなくてね。もう三回もやり直しているよ。目がかすんで数字が躍って見える」
大山の机のモニタを見ると、セルの一つひとつに手打ちの数字が並び、数式も使われずに合計欄に固定値が直接入力されていた。

「大山先生、それ、もしかして全員分の合計と平均を手作業で計算して転記されているんですか？」
「そうだよ。教科ごとに配点が違うし、不受験者の扱いもあるからね。コンピュータ任せにすると間違いが起きそうで怖くてな」
水野は深く頷いた。大山が長年の責任感から、子どもたちの成績に瑕疵があってはならないと一人で重圧を背負い込んでいることが痛いほど伝わってきた。
「大山先生、その責任感は本当に尊敬します。でも、人間の集中力には限界がありますし、手入力こそ転記ミスの温床になってしまいます。もしよろしければ、この作業、十分で終わるように自動化してみませんか？」

「じ、十分？ 三百人分もあるんだぞ？」
水野は大山の隣に椅子を引き寄せ、手際よくノートPCを開いた。
「まず、各教科の先生方から上がってきたデータをGoogleスプレッドシートに統合します。そして、この関数を使います」
水野はキーボードを叩き、一つのセルに数式を入力した。
`=BYROW(C4:G303, LAMBDA(row, IF(COUNTA(row)=0, "", SUM(row))))`
「これは配列数式（LAMBDA / BYROW）です。これ一つで、三百人分の合計が一瞬で縦一列に展開されます。行の追加や点数の修正があっても、自動でリアルタイムに再計算されるので、手で再計算する必要は二度とありません」
大山は目を丸くした。「なんと……一瞬で全部の合計が入ったぞ……」

「さらに、Google Apps Script（GAS）で簡単なチェックプログラムを動かしましょう」
水野はエディタを開き、数行のスクリプトを走らせた。
「ほら、見てください。百点満点のはずなのに『120点』と誤入力されているセルや、欠席なのに点数が入っている矛盾箇所が、赤色の背景で一瞬でハイライトされました。外れ値検知とデータ入力規則（Data Validation）の仕組みです」
「おお……！ 探していた数字のズレはこれだったのか！ 私が二時間探しても見つからなかったミスが、一秒で……」
大山は思わず身を乗り出し、感嘆の声を上げた。

「大山先生が今まで電卓でなさっていた厳密な照合のルールを、そのままプログラムに教え込んだだけですよ。先生のチェック基準という『知恵』があってこその自動化です」
水野の謙虚な言葉に、大山の強張っていた表情がふっと緩んだ。
「水野先生……ありがとう。私はどこかで、最新の技術を毛嫌いして、苦労して時間をかけることこそが誠意だと思い込んでいたのかもしれん。だが、この時間があれば、明日悩んでいる生徒の話をゆっくり聞いてやることができるな」
「まさにそれがICTの真の目的です。先生、今日はもう帰りましょう。明日の朝、印刷ボタンをワンクリックするだけで、完璧な帳票が出力されますから」
二人は笑顔で職員室の明かりを消した。校舎を出ると、夜空には澄んだ星が輝いていた。

* * *

### 【作中技術・ITネットワークのやさしい解説（Technical Commentary）】

作中で若手教員が導入した技術は、特別な有料ソフトを導入することなく、Google Workspace等の標準機能で誰でも現場に導入できる強力な校務効率化技術です。

1. **Google Apps Script（GAS）**
   Google Workspace（スプレッドシート、フォーム、Gmail、ドライブ等）をクラウド上で自動化するためのJavaScriptベースのスクリプト環境です。サーバー構築不要でブラウザ上ですぐに実行でき、定期的な自動実行やエラー検知メールの送信、帳票作成の完全自動化が可能です。

2. **現代の配列数式（ARRAYFORMULA / BYROW / LAMBDA）**
   従来のExcelやスプレッドシートでは、計算式を一番下の行までコピー＆ペーストする必要があり、途中の行で数式が壊れるリスクがありました。最新のスプレッドシートに搭載されたLAMBDA関数やBYROW関数を使うと、最上部のセルにたった1行数式を書くだけで、データ全体の計算を自動走査して結果を展開できます。

3. **データ入力規則（Data Validation）と条件付き書式のバリデーション**
   人間による手入力ミス（タイポや範囲外の数値）を根絶するため、入力可能な値の範囲（例: 0〜100）を制限し、不正な値が入力された瞬間に背景色を警告表示（赤色等）にする仕組みです。

---

### 【引用・参考文献（Technical References & Documentation）】

1. Microsoft Support (2024). *XLOOKUP 関数 – Microsoft サポート*.
   URL: [https://support.microsoft.com/ja-jp/office/xlookup-function-b7fd680e-6d10-43e6-84f9-88eae8bf5929](https://support.microsoft.com/ja-jp/office/xlookup-function-b7fd680e-6d10-43e6-84f9-88eae8bf5929)

2. 文部科学省 (2021). *教育情報セキュリティの確保（教育情報セキュリティポリシーに関するガイドライン）*.
   URL: [https://www.mext.go.jp/a_menu/shotou/zyouhou/detail/1397369.htm](https://www.mext.go.jp/a_menu/shotou/zyouhou/detail/1397369.htm)

3. Google ドキュメント エディタ ヘルプ. *Google スプレッドシートの関数リスト*.
   URL: [https://support.google.com/docs/table/25273?hl=ja](https://support.google.com/docs/table/25273?hl=ja)
"""
            return content, title, [
                "https://support.microsoft.com/ja-jp/office/xlookup-function-b7fd680e-6d10-43e6-84f9-88eae8bf5929",
                "https://www.mext.go.jp/a_menu/shotou/zyouhou/detail/1397369.htm",
                "https://support.google.com/docs/table/25273?hl=ja"
            ]
        else:
            title = "疑いと報告のあいだ――校長が学ぶいじめ防止対策推進法と重大事態の判断"
            content = f"""---
title: "{title}"
pattern: "C"
category: "{topic.get('category', '学校法制・いじめ防止')}"
tags: ["学校法制", "教育法規", "いじめ防止対策推進法", "学校管理職", "校長", "Cパターン"]
topic_id: "{topic.get('id', 'C01')}"
---

初冬の朝、校長室の重い扉を閉めた青木校長は、机の上に置かれた「事故等速報（案）」の用紙を前に、深く眉をひそめていた。
校長就任二年目。全校生徒六百人を預かる最高責任者として、学校の平穏を守ることに全身全霊を注いできた。だが今、青木の前に立ちはだかっているのは、学校の存亡を揺るがしかねない極めて困難な問題だった。
二年生の男子生徒が、先週から「体調不良」を理由に欠席を続けている。昨日、母親から激しい口調で電話が入った。「息子は特定のグループから継続的に私物を隠され、プロレス技と称して蹴られていた。学校に行くのが怖いと泣いている。これは立派ないじめだ。重大事態として調査してほしい」と。

朝の打ち合わせ後、学年主任と生徒指導主事は青木にこう報告していた。
「相手の生徒たちに聞き取りましたが、『ただの悪ふざけ、仲が良いからじゃれ合っていただけ』と言っています。男子の間ではよくあることで、いじめとまでは言えないかと……。重大事態として教育委員会に上げると、マスコミや地域に知られて大騒ぎになります。まずは校内で生徒同士を仲直りさせ、穏便に収めるべきです」
教職員たちの「学校を守りたい、騒ぎにしたくない」という心理は痛いほど分かった。だが、欠席が続いている生徒の心の傷はどうなるのか。学校だけで抱え込んでいいのか。

青木は意を決して、市教育委員会の生徒指導担当・黒田指導主事に電話をかけた。
黒田は長年、困難校の生徒指導や法務対応を専門にしてきた頼れる指導主事だった。
「黒田指導主事、お忙しいところ恐れ入ります。実は、生徒の欠席といじめの訴えについて、判断に迷っておりまして……」
青木はこれまでの経緯と、校内の「大事にしたくない」という空気を包み隠さず伝えた。

電話の向こうで、黒田指導主事は静かに、しかし毅然とした声で応じた。
「青木校長先生、お電話ありがとうございます。まず結論から申し上げます。**その事案は、直ちに『いじめ防止対策推進法第28条第1項』に基づく重大事態の疑いとして、教育委員会へ正式報告し、学校いじめ対策組織を稼働させてください**」
「やはり、重大事態ですか……。しかし、相手の生徒は『じゃれ合いだった』と主張しており、事実関係がまだ確定していません。それでも報告義務があるのでしょうか」

「そこが、多くの学校管理職が誤解しやすい重要な法解釈のポイントです」
黒田は受話器越しに、条文の趣旨を噛み砕くように語りかけた。
「平成25年に施行された『いじめ防止対策推進法』第2条において、いじめの定義は『児童生徒が心身の苦痛を感じているもの』と規定されています。加害側の意図や『悪ふざけ』という認識は一切関係ありません。被害生徒が苦痛を感じ、現に登校できない状態にあるならば、客観的にいじめとして扱わなければなりません」
黒田の声には、一切の迷いがなかった。

「さらに第28条の重大事態には二つの要件があります。生命・心身・財産に重大な被害が生じた疑い、そして『相当の期間（年間30日を目安とし、児童生徒が一定期間連続して欠席している場合を含む）学校を欠席することを余儀なくされている疑い』です。ここで法律上極めて重要な文言は、**『疑いがあるとき』**と明記されている点です。事実が確定していなくても、『疑い』が生じた時点で、学校設置者（教育委員会）への報告と、事実関係を明確にするための調査を行う法的義務が学校に発生するのです」
「『疑い』の段階で義務が発生する……」
青木は手帳にペンを走らせながら、胸のつかえが取れていくのを感じた。

「校長先生、重大事態の認定や教育委員会への報告は、学校の『敗北』や『不祥事』ではありません。法律が求めているのは、学校が一人で密室に抱え込んで傷口を広げるのではなく、教育委員会や専門家とチームを組んで、公正中立な事実調査を行い、何よりも被害生徒の教育を受ける権利を守ることです。前例踏襲や体裁にとらわれず、法に基づき迅速に動くことこそが、結果として学校と教職員を守ることにつながるのです」
「黒田先生、よくわかりました。法が何のためにあるのか、校長としての私の責務がどこにあるのか、目が覚めました」

電話を切った青木校長は、すぐに職員室へ向かった。教頭、学年主任、生徒指導主事を校長室に招集し、強い眼差しで告げた。
「先生方、この件は『いじめ防止対策推進法第28条』の重大事態の疑いとして、直ちに市教育委員会へ正式報告します。そして、本校の『学校いじめ対策組織』を立ち上げ、客観的な事実調査に入ります。生徒同士の仲直りで幕引きを図ることはしません。被害生徒の苦痛に寄り添い、法に基づいて真実を明らかにすることが、教育者としての私たちの誠意です。全責任は私が取ります」
校長の揺るぎない決断に、主任たちの迷いは消え、職員室は適法な解決に向けて力強く動き始めた。

* * *

### 【作中法規・教育法制のやさしい解説（Legal Commentary）】

作中で指導主事が助言した内容は、学校管理職および教職員が遵守すべき教育法規（いじめ防止対策推進法）の極めて重要な基本原則です。

1. **いじめの定義（いじめ防止対策推進法 第2条第1項）**
   児童生徒に対して、当該児童生徒が在籍する学校の内外を問わず、一定の人間関係がある他の児童生徒が行う心理的・物理的な影響を与える行為であって、**当該行為の対象となった児童生徒が心身の苦痛を感じているもの**と定義されています。加害側の「いじめの意図」や「遊び半分だった」という主観的弁解に関わらず、被害生徒の主観と苦痛を起点に判断されます。

2. **重大事態の判断と調査義務（第28条第1項）**
   以下のいずれかに該当する「疑い」があると認めるとき、学校および教育委員会は直ちに事実関係を明確にするための調査に着手しなければなりません。
   - **第1号**: いじめにより当該学校の児童生徒の生命、心身又は財産に重大な被害が生じた疑い。
   - **第2号**: いじめにより当該学校の児童生徒が相当の期間（年間30日を目安とするが、連続欠席など児童生徒の状況を勘案）学校を欠席することを余儀なくされている疑い。
   文部科学省のガイドラインでは、「事実が確定してから動く」のではなく、**「疑いが生じた段階」で速やかに報告・調査を開始すること**が厳格に義務付けられています。

3. **学校いじめ対策組織の常設（第22条）**
   いじめの早期発見・対処を行うため、学校には校長、教頭、生徒指導主事、養護教諭、スクールカウンセラー等で構成される組織を常設することが法的に義務付けられています。担任一人の抱え込みを防ぎ、組織的かつ法的に適切な対応を行うための基盤となります。

---

### 【引用・参考文献（Legal References & e-Gov Links）】

1. いじめ防止対策推進法（平成二十五年法律第七十一号）
   e-Gov法令検索: [https://laws.e-gov.go.jp/document?lawid=425AC1000000071](https://laws.e-gov.go.jp/document?lawid=425AC1000000071)

2. 学校教育法（昭和二十二年法律第二十六号）
   e-Gov法令検索: [https://laws.e-gov.go.jp/document?lawid=322AC0000000026](https://laws.e-gov.go.jp/document?lawid=322AC0000000026)

3. 教育基本法（平成十八年法律第百二十号）
   e-Gov法令検索: [https://laws.e-gov.go.jp/document?lawid=418AC0000000120](https://laws.e-gov.go.jp/document?lawid=418AC0000000120)
"""
            return content, title, [
                "https://laws.e-gov.go.jp/document?lawid=425AC1000000071",
                "https://laws.e-gov.go.jp/document?lawid=322AC0000000026",
                "https://laws.e-gov.go.jp/document?lawid=418AC0000000120"
            ]

    def check_draw_things_connection(self) -> Dict[str, Any]:
        """Checks connection to Mac mini Draw Things HTTP API server (/sdapi/v1/options)."""
        try:
            req = urllib.request.Request(f"{self.draw_things_host}/sdapi/v1/options")
            with urllib.request.urlopen(req, timeout=5) as res:
                if res.getcode() == 200:
                    data = json.loads(res.read().decode("utf-8", errors="ignore"))
                    return {
                        "online": True,
                        "host": self.draw_things_host,
                        "model": data.get("model", "flux_2_klein_base_4b_i8x.ckpt"),
                    }
        except Exception as e:
            return {
                "online": False,
                "host": self.draw_things_host,
                "error": str(e),
            }
        return {"online": False, "host": self.draw_things_host}

    def check_ollama_connection(self) -> Dict[str, Any]:
        """Checks connection to Mac mini Ollama server (/api/tags)."""
        try:
            req = urllib.request.Request(f"{self.ollama_host}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as res:
                if res.getcode() == 200:
                    data = json.loads(res.read().decode("utf-8", errors="ignore"))
                    models = [m.get("name", "") for m in data.get("models", [])]
                    return {
                        "online": True,
                        "host": self.ollama_host,
                        "models": models,
                    }
        except Exception as e:
            return {
                "online": False,
                "host": self.ollama_host,
                "error": str(e),
            }
        return {"online": False, "host": self.ollama_host}

    def call_ollama_chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.65,
        num_predict: int = 250,
        num_ctx: int = 4096,
        timeout: int = 120,
    ) -> str:
        """Calls Mac mini Ollama /api/chat endpoint."""
        url = f"{self.ollama_host}/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": num_predict,
                "num_ctx": num_ctx,
            },
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as res:
            body = json.loads(res.read().decode("utf-8", errors="ignore"))
            msg = body.get("message", {})
            content = msg.get("content", "")
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            return content

    def generate_english_image_prompt(
        self,
        pattern: str,
        topic: Dict[str, Any],
        story_body: str = "",
        title: str = "",
    ) -> str:
        """
        Uses `gemma4:12b` on Mac mini Ollama to translate the story's most visually iconic school scene
        into a concise, descriptive English image generation prompt for FLUX.2 [klein] 4B.
        """
        clean_pattern = (pattern or "A").strip().upper()
        story_excerpt = story_body[:1600] if story_body else topic.get("situation", "")

        if clean_pattern == "A":
            setting_hint = "a warm Japanese school classroom or staffroom at sunset, a young novice teacher and a gentle veteran mentor teacher discussing a classroom pedagogy notebook by the window"
        elif clean_pattern == "B":
            setting_hint = "a modern Japanese school staffroom, an experienced older teacher and a bright young ICT teacher smiling together in front of a laptop screen with glowing clean data charts and school network diagrams"
        else:
            setting_hint = "a dignified Japanese school principal's office with warm sunlight, a thoughtful school principal and an education board supervisor reviewing a law statute book with determination and hope"

        prompt = f"""You are an expert anime light novel art director.
Based on the following Japanese school drama story (Pattern {clean_pattern}), write a single, vivid, highly descriptive **English image generation prompt** (60-95 words) for the FLUX.2 image model to depict the most iconic, heartwarming scene of the story.

[Story Info]
- Title: {title or topic.get('problem_title', '')}
- Pattern: Pattern {clean_pattern}
- Category: {topic.get('category', '')}
- Core Theme: {topic.get('problem_title', '')} / {topic.get('solution_framework', '')}
- Visual Setting Hint: {setting_hint}

[Story Excerpt]
{story_excerpt}

[Rules for Output]
1. Output ONLY the raw English prompt paragraph. Do NOT include explanations, markdown formatting, quotes, or Japanese text.
2. Start with: "Bright, vibrant anime light novel illustration of Japanese school teachers in ..."
3. Visually describe the characters' warm expressions, the authentic Japanese school atmosphere bathed in clear natural daylight (blackboard, windows, blue sky, notebooks, or laptop screen), and the emotional moment of insight and collaboration. Avoid dark night or gloomy scenes.
4. End with: "masterpiece anime art style, Makoto Shinkai and Kyoto Animation inspired luminous daylight, crisp details, rich vivid colors, clear contrast, cheerful uplifting atmosphere."
"""
        try:
            logger.info(f"[Ollama: {self.writer_model}] Generating English illustration prompt for FLUX.2...")
            raw_en = self.call_ollama_chat(
                model=self.writer_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional prompt engineer for FLUX.2 anime light novel illustrations. Output ONLY the English prompt text.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.65,
                num_predict=250,
                num_ctx=4096,
                timeout=120,
            )
            cleaned_en = raw_en.strip(" \"'`\n")
            cleaned_en = re.sub(r"^(?:Prompt|English Prompt)\s*[:：]\s*", "", cleaned_en, flags=re.IGNORECASE).strip()
            cleaned_en = " ".join(cleaned_en.splitlines()).strip()
            if len(cleaned_en) >= 30 and re.search(r"[a-zA-Z]{4,}", cleaned_en):
                logger.info(f"  -> Generated English prompt: {cleaned_en[:120]}...")
                return cleaned_en
        except Exception as e:
            logger.warning(f"Failed to generate English prompt via Ollama ({e}), using fallback English prompt.")

        return (
            f"Bright, vibrant anime light novel illustration of Japanese school teachers in {setting_hint}, "
            f"clear natural sunlight streaming through school windows, blue sky outside, expressive eyes filled with hope and insight, "
            f"masterpiece anime art style, Makoto Shinkai and Kyoto Animation inspired luminous daylight, crisp details, rich vivid colors, clear contrast, cheerful uplifting atmosphere."
        )

    def generate_illustration(
        self,
        pattern: str,
        topic: Dict[str, Any],
        output_image_path: Path,
        story_body: str = "",
        title: str = "",
        custom_english_prompt: Optional[str] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Tuple[Optional[Path], str]:
        """
        Generates a 512x512 light novel illustration using Draw Things HTTP API
        (`http://192.168.128.59:7860/sdapi/v1/txt2img`, model `flux_2_klein_base_4b_i8x.ckpt`)
        with an English prompt created by `gemma4:12b`.
        Returns (saved_image_path_or_None, english_prompt_used).
        """
        dt_conn = self.check_draw_things_connection()
        if not dt_conn.get("online"):
            logger.warning(
                f"Draw Things HTTP API server ({self.draw_things_host}) is not reachable: {dt_conn.get('error')}. Skipping image generation."
            )
            return None, ""

        if custom_english_prompt and custom_english_prompt.strip():
            en_prompt = custom_english_prompt.strip()
        else:
            if progress_callback:
                progress_callback(f"Ollama ({self.writer_model}) が小説本文から英語の挿絵プロンプトを作成中...")
            en_prompt = self.generate_english_image_prompt(
                pattern=pattern,
                topic=topic,
                story_body=story_body,
                title=title,
            )

        if progress_callback:
            progress_callback(f"Draw Things ({self.draw_things_host}) で挿絵画像を生成中 (FLUX.2 [klein] 4B)...")
        logger.info(
            f"[Draw Things: {self.draw_things_host}] Generating 512x512 illustration "
            f"(steps=12, guidance=4.0, sampler='Euler A Trailing')..."
        )

        url = f"{self.draw_things_host}/sdapi/v1/txt2img"
        payload = {
            "prompt": en_prompt,
            "negative_prompt": "dark, gloomy, night, dim lighting, heavy shadows, lowkey, monochrome, horror, washed out, overexposed, whiteout, faded, desaturated, low contrast",
            "width": 512,
            "height": 512,
            "steps": 12,
            "guidance_scale": 4.0,
            "sampler": "Euler A Trailing",
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            start_t = time.time()
            with urllib.request.urlopen(req, timeout=600) as res:
                body = json.loads(res.read().decode("utf-8", errors="ignore"))
                images = body.get("images", [])
                if images and images[0]:
                    b64_str = re.sub(r"^data:image/[^;]+;base64,", "", images[0])
                    img_bytes = base64.b64decode(b64_str)
                    output_image_path.parent.mkdir(parents=True, exist_ok=True)
                    output_image_path.write_bytes(img_bytes)
                    elapsed = time.time() - start_t
                    logger.info(
                        f"[Draw Things Complete] Saved illustration to {output_image_path} "
                        f"({len(img_bytes)} bytes in {elapsed:.1f}s)"
                    )
                    return output_image_path, en_prompt
                else:
                    logger.warning("Draw Things returned empty images list.")
        except Exception as e:
            logger.error(f"Draw Things image generation failed: {e}")

        return None, en_prompt
