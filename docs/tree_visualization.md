# ページツリー表示（ツリーモード / tree）詳細ガイド

Confluence のページ階層を樹形図（ページツリー）としてテキスト・Markdown・JSON 形式で出力する機能（`python -m c2m_export.tree`）に関する詳細ドキュメントです。

---

## 概要

ツリーモードは、指定された Confluence スペースまたはルートページを起点として、親子関係を保持した階層構造を出力する読み取り専用モードです。

既定ではタイトルとページ ID のみの最小ツリーを高速に出力しますが、オプトイン（`--include`）により以下の付帯情報（annotation）をノード行にインライン併記、または詳細別表 / 構造化フィールドとして出力できます。

- **個別アクセス制限 (`restriction`)**: 親からの継承ではない明示的なコンテンツ閲覧・編集制限
- **使用マクロ (`macros`)**: ページ本文で使用されている Confluence マクロ種別数と使用回数
- **添付ファイル数 (`attachments`)**: ページに添付されているファイル数
- **最終更新日 (`last_modified`)**: ページの最終更新日時

---

## CLI の使用例

### 1. テキスト形式（デフォルト）での基本実行

```bash
python -m c2m_export.tree \
  --base-url "https://confluence.example.com/wiki" \
  --space-key "DEV"
```

出力例:
```text
ホーム  [id:19127895]
├── 設計メモ  [id:84916196]
└── 作業中  [id:84923420]
    └── 環境構築  [id:84910567]
```

### 2. オプトイン付帯情報付き Markdown 出力

```bash
python -m c2m_export.tree \
  --base-url "https://confluence.example.com/wiki" \
  --space-key "DEV" \
  --format "markdown" \
  --include restriction attachments last_modified \
  --output "tree_report.md" \
  --overwrite
```

出力例:
```markdown
- ホーム `19127895` (2025-08-20)
  - 設計メモ `84916196` 🔒 📎2 (2024-11-01)
  - 作業中 `84923420` (2025-07-15)
    - 環境構築 `84910567` 📎1 (?)

## アクセス制限詳細

| page_id | title | Read | Read+Write |
|---|---|---|---|
| 84916196 | 設計メモ | group:dev | user:alice |
```

### 3. 全付帯情報を含む JSON 出力

```bash
python -m c2m_export.tree \
  --base-url "https://confluence.example.com/wiki" \
  --root-page-id "19127895" \
  --format "json" \
  --include all
```

---

## パラメータ仕様

| 引数 / オプション | 型 | 説明 | 既定値 |
|---|---|---|---|
| `--base-url` | 文字列 | Confluence のベース URL (例: `https://host/wiki`) | 設定ファイル/環境変数 |
| `--space-key` | 文字列リスト | 起点とする Space キー (複数指定可) | なし |
| `--root-page-id` | 文字列リスト | 起点とするルートページ ID (複数指定可) | なし |
| `--format` | 文字列 | 出力フォーマット (`text`, `markdown`, `json`) | `text` |
| `--include` | 文字列リスト | 取得・表示する付帯情報 (`restriction`, `macros`, `attachments`, `last_modified`, `all`) | なし (付帯情報なし) |
| `--ascii` | フラグ | 絵文字の代わりに ASCII マーク (`[R]`, `att:N`, `mac:N`) を使用 | `False` |
| `--max-depth` | 整数 | 探索する最大階層深さ (指定なし/0で無制限) | 無制限 |
| `--output` | 文字列 | 結果の保存先ファイルパス (省略時は標準出力) | なし (stdout) |
| `--overwrite` | フラグ | `--output` 指定ファイルが存在する場合に無確認で上書き | `False` |
| `--proxy` | 文字列 | HTTP/HTTPS プロキシ URL | なし |
| `--config` | 文字列 | 設定ファイルのパス | `c2m_config.yaml` |
| `--token` | 文字列 | Confluence Bearer トークン (環境変数推奨) | なし |

---

## マーク規則（インライン表記）

`--include` オプションで有効化した項目に応じて、ノード行に以下のマークが付与されます。

| 付帯情報項目 | 絵文字表記 (既定) | ASCII 表記 (`--ascii`) | 説明 |
|---|---|---|---|
| **個別アクセス制限** | `🔒` | `[R]` | 親からの継承ではなく、該当ページに個別の閲覧・編集制限が設定されていることを示します。 |
| **添付ファイル数** | `📎N` | `att:N` | ページに添付されたファイル数 (N) を示します (0 件時は非表示)。 |
| **使用マクロ種別数** | `⚙N` | `mac:N` | ページ本文で使用されている Confluence マクロの種類数 (N) を示します。 |
| **最終更新日** | `(YYYY-MM-DD)` | `(YYYY-MM-DD)` | ページの最終更新日を示します。 |
| **取得失敗 / 不明** | `(?)` または `📎?` 等 | `(?)` または `att:?` 等 | API 通信失敗等で該当付帯情報の取得に失敗した場合に表示されます。 |

---

## 設定ファイル（c2m_config.yaml）の記法

`c2m_config.yaml` の `tree:` セクションでツリーモードの既定動作を設定できます。

```yaml
tree:
  format: "text"
  include:
    - restriction
    - macros
    - attachments
    - last_modified
  ascii: false
  max_depth: 3
```

優先順位: **CLI 引数 > 環境変数 (`C2M_CONFLUENCE_TOKEN` 等) > YAML 設定ファイル > デフォルト値**
