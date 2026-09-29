# 🏫 Solve School Problems

> **教育学の叡智と最先端テクノロジーの両輪で、学校現場のあらゆる課題を鮮やかに解決する。**
> 新米教員への学術的アドバイス（Aパターン）と、年配教員を支える校務DX（Bパターン）を交互に自動生成し、WordPressへメール投稿するシステムです。

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-Automated-purple.svg)](https://github.com/features/actions)

---

## 📖 コンセプトと2つのストーリーパターン

学校教育の現場では、**「教室内の人間関係・生徒指導の悩み」** と **「煩雑な校務事務・デジタル化の壁」** という2大課題が日々発生しています。本システムは、この2つの課題に焦点を当てた短編小説を**交代（オルタネーション）で自動生成**し、WordPressブログ等へ定期配信します。

```mermaid
flowchart LR
    subgraph Alternation [交代配信サイクル]
        direction TB
        A["📘 パターンA\n新米教員 × 先輩教員\n（教育学・教育心理学・教育哲学）"]
        B["💻 パターンB\n年配教員 × 若手教員\n（校務DX・コンピュータ・ネットワーク）"]
        A -->|次回| B
        B -->|次回| A
    end

    LLM["Google Gemini API\n(gemini-3.8-flash)"]
    WP["WordPress\n(Jetpack / Postie)"]
    GH["GitHub Actions\n(定期実行・履歴管理)"]

    Alternation --> LLM
    LLM --> Formatter["リッチHTML/プレーンテキスト成形\n（専門用語解説 ＋ 参考文献URL）"]
    Formatter --> Mail["SMTP メール送信"]
    Mail --> WP
    Formatter --> GH
```

### 📘 Aパターン：教育相談・学術理論アプローチ
- **登場人物**: 新米教員（若手・初任者） × 先輩教員（指導教諭・ベテラン）
- **シチュエーション**: 
  - クラス経営、生徒の指示待ち、荒れや私語、不登校傾向、グループワークの形骸化、テストの挫折、保護者対応など。
- **解決の道筋**:
  - 先輩教員が、**教育学（デューイ、ヴィゴツキー等）**、**教育心理学（自己決定理論、認知的負荷理論、成長マインドセット等）**、**教育哲学（ケアの倫理、対話主義等）**の実在する論文・学術的知見を紐解きながら、明日から現場で実践できる具体的な声かけ・行動を温かくアドバイスします。

### 💻 Bパターン：校務DX・ICTネットワーク解決
- **登場人物**: 年配教員（教務主任・学年主任・ベテラン） × 若手教員（情報担当・IT得意教員）
- **シチュエーション**:
  - 学期末の成績手計算・転記、保護者アンケートの紙集計、校内Wi-Fiの通信途絶、共有ファイルの誤上書き・消失、通知表所見の字数・表記ゆれチェック、部活動の連絡網など。
- **解決の道筋**:
  - 若手教員が、**Google Apps Script (GAS)**、**スプレッドシート配列数式（LAMBDA/BYROW）**、**Python自動化**、**Wi-Fi 6 / 周波数帯・AP最適化**、**クラウド版管理・アクセス権限設計（RBAC）**、**正規表現（RegEx）**などの技術を駆使し、手作業の苦行をあっという間にスマートかつ安全に解決します。

---

## 📑 記事の構成（neo-sf-aozora 準拠）

すべての記事は、以下の三部構成で統一されています：

1. **第一部：小説本文**
   - 現場の臨場感あふれる会話劇（約3,500〜4,000文字）。
   - 登場人物の心理描写と具体的な指導・解決ステップ。
2. **第二部：【作中理論・技術のやさしい解説（Commentary）】**
   - 作中に登場した教育理論やコンピュータ技術の仕組みを、専門知識がない読者にもわかりやすく丁寧に解説。
3. **第三部：【引用・参考文献（References & Documentation）】**
   - 実在する学術論文（DOIハイパーリンク `https://doi.org/...`）や、公式技術ドキュメント（Google Workspace API、RFC、Microsoft Learn等）のクリック可能なURLリンクを記載。

---

## 🛠️ システム機能

- **A/Bパターンの自動交代**: `data/history.json` を参照し、前回がAなら次はB、前回がBなら次はAを自動判定。
- **リッチHTML＆メール送信**:
  - スマートフォンやPCメーラーで美しく表示されるインラインCSS付きHTML。
  - WordPressの「メール投稿（Jetpack Post by Email または Postie）」に対応。
  - 記事タイトル（メール件名）、カテゴリ、タグ（ショートコード付与）、投稿ステータス（publish / draft）を完全制御。
- **多彩なトピックカタログ**: `data/topic_catalog.json` に豊富な現場課題を定義。使われていないトピックを優先的に選択。
- **GitHub Actions 自動化**:
  - 毎日定時（朝の通勤前 06:30 JST / 夕方の放課後 17:30 JST）に自動投稿。
  - 生成されたMarkdownファイルや履歴ログ（`POSTED_STORIES.md`）を自動コミット＆プッシュ。
- **手動実行（workflow_dispatch）対応**:
  - パターンの強制指定（`auto` / `A` / `B`）、Dry-Run（シミュレーション）、下書き保存（`draft`）をGitHubブラウザ画面からワンクリック実行可能。

---

## 🚀 セットアップ手順

### 1. リポジトリのクローン & 依存パッケージ導入

```bash
git clone https://github.com/k518-2026/solve-school-problems.git
cd solve-school-problems

# 仮想環境の作成と有効化
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 依存ライブラリのインストール
pip install -r requirements.txt
```

### 2. 環境変数の設定

`.env.example` をコピーして `.env` を作成し、必要なキーを入力します：

```bash
cp .env.example .env
```

`.env` の設定項目：
```ini
# Google Gemini API
GEMINI_API_KEY=AIzaSy...
GEMINI_TEXT_MODEL=gemini-3.8-flash

# WordPress メール投稿設定
WP_POST_EMAIL=your-secret-email@post.wordpress.com
DEFAULT_POST_STATUS=publish
USE_JETPACK_SHORTCODES=true

# SMTP 送信サーバー（例: Gmail）
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_specific_password
SMTP_USE_TLS=true
SMTP_USE_SSL=false
MAIL_FROM_NAME=Solve School Problems
```

> **Gmailを使う場合の注意点**: Googleアカウントの「2段階認証」を有効にし、「アプリパスワード（16桁）」を生成して `SMTP_PASSWORD` に設定してください。

---

## 💻 コマンドラインでの使い方

```bash
# 1. 自動交代でストーリーを生成し、メール送信（Dry-Run: 実際には送らない）
python -m src.main --dry-run

# 2. 生成結果のHTMLをブラウザでプレビュー確認
python -m src.main --dry-run --preview-html
# ブラウザで preview_output.html を開いてデザインを確認できます

# 3. パターンを明示的に指定して実行
python -m src.main --pattern A --dry-run   # Aパターン（教育学）
python -m src.main --pattern B --dry-run   # Bパターン（校務DX）

# 4. 特定のトピックIDを指定して実行
python -m src.main --topic-id A03 --dry-run

# 5. 実際に WordPress にメール投稿する（本番送信）
python -m src.main --send

# 6. ユニットテストの実行
python -m unittest discover tests
```

---

## ⚙️ GitHub Actions の設定（自動定期配信）

GitHubリポジトリの **[Settings] -> [Secrets and variables] -> [Actions]** で以下のシークレットを登録してください：

| Secret名 | 説明 | 例 |
|:---|:---|:---|
| `GEMINI_API_KEY` | Google AI Studio の Gemini APIキー | `AIzaSy...` |
| `WP_POST_EMAIL` | WordPressメール投稿用の秘密メールアドレス | `xxxx@post.wordpress.com` |
| `SMTP_USER` | 送信用メールアドレス | `your_account@gmail.com` |
| `SMTP_PASSWORD` | 送信用SMTPパスワード / アプリパスワード | `abcd efgh ijkl mnop` |
| `SMTP_HOST` (任意) | SMTPホスト（デフォルト: `smtp.gmail.com`） | `smtp.gmail.com` |
| `SMTP_PORT` (任意) | SMTPポート（デフォルト: `587`） | `587` |

### 手動トリガー（workflow_dispatch）
GitHub上の **[Actions]** タブ -> **[Solve School Problems - Auto Story Publisher to WordPress]** -> **[Run workflow]** から、ブラウザ上でいつでも実行できます。

---

## 📁 ディレクトリ構成

```text
solve-school-problems/
├── .github/
│   └── workflows/
│       └── publish.yml         # GitHub Actions ワークフロー（定期配信＆手動実行）
├── content/                    # 生成されたストーリーMarkdownの保管先
├── data/
│   ├── topic_catalog.json      # Aパターン・Bパターンの豊富なテーマ定義カタログ
│   ├── history.json            # 実行履歴・直前のパターン（A/B交代判定用）
│   └── POSTED_STORIES.md       # 自動生成される投稿済み一覧Markdown表
├── src/
│   ├── __init__.py
│   ├── config.py               # 設定・環境変数パーサー
│   ├── history_manager.py      # A/B交代ロジックおよび履歴管理
│   ├── story_generator.py      # Gemini API プロンプト構築＆ストーリー生成
│   ├── post_formatter.py       # Markdown -> リッチHTML / プレーンテキスト変換
│   ├── mail_sender.py          # SMTP による WordPress 宛メール送信
│   └── main.py                 # CLI メインエントリーポイント
├── tests/                      # 各種ユニットテスト
├── requirements.txt            # 依存関係
├── .env.example                # 環境設定テンプレート
├── .gitignore
└── README.md
```

---

## 📜 ライセンス

MIT License
