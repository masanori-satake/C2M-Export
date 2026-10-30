# Design Document

## 概要

ページツリー可視化モードを、既存の `analyze` / `assess` / `fsexport` / `permexport` と同列の CLI モードとして追加する。本文の変換やファイル実体化は行わず、**ページ階層の構築 → 付帯情報の選択的収集 → 3 フォーマットへの描画**という読み取り専用のパイプラインで構成する。

設計の基本方針は既存プロジェクトの原則を踏襲する。

- **I/O 層と純粋ロジック層の分離**: Confluence API 呼び出し（I/O）と、ツリー構築・付帯情報集約・描画（純粋ロジック）を分離し、純粋ロジックを単体テスト可能にする（`assessment/` が `collector.py`(I/O) と `analyzers.py`(純粋) を分けている構成に倣う）。
- **設定の優先順位**: CLI 引数 > 環境変数 > YAML > デフォルト。
- **付帯情報は opt-in**: 既定ではタイトル + page_id のみ。指定された付帯情報の種類だけ追加 API を呼ぶ。
- **json は stdout 単独、ログは stderr**: `analyze` と同じ振り分け。

## アーキテクチャ

### モジュール構成（新規）

```
c2m_export/
├── tree.py                 # 新: CLI エントリーポイント (python -m c2m_export.tree)
└── page_tree/              # 新: ページツリー機能パッケージ
    ├── __init__.py
    ├── models.py           # TreeNode / Annotation / TreeResult データモデル
    ├── collector.py        # I/O 層: ルート/子ページ探索と付帯情報の選択的収集
    ├── builder.py          # 純粋ロジック: 収集結果から TreeNode ツリーを構築
    ├── annotations.py      # 純粋ロジック: マクロ名集計・制限判定・inline マーク生成
    └── renderers.py        # 純粋ロジック: text / markdown / json への描画
```

`config.py` には `TreeConfig`（または `AnalysisConfig` に準じた新クラス）を追加する。既存 `AnalysisConfig` と同じく `base_url` / `root_page_ids` / `space_keys` / `proxy` / `token` を持ち、本モード固有の設定（`format` / `include` / `limit` 等）を加える。

### 処理フロー

```
tree.py (main)
  1. TreeConfig.load() / validate()        # 設定解決・必須チェック・URL 正規化
  2. ConfluenceClient 初期化                # base_url / token / proxy
  3. collector.collect_tree(...)            # ルート解決 → 子ページ再帰探索（付帯情報は opt-in で収集）
       - get_space_root_pages / get_child_pages  … 階層（常に実行）
       - get_restrictions                         … include に restriction がある時のみ
       - get_page(expand=body.storage)            … include に macros がある時のみ
       - get_child_attachments                    … include に attachments がある時のみ
       - get_content_history                      … include に last_modified がある時のみ
  4. builder.build_tree(...)                # 収集 dict 群 → TreeNode 木（純粋）
  5. renderers.render(tree, format, ...)    # text / markdown / json（純粋）
  6. 出力                                   # text/markdown は stdout、json は stdout 単独、ログは stderr
```

付帯情報を 1 つも指定しない場合、ステップ 3 は `get_space_root_pages` / `get_child_pages` のみを呼び、ステップ 4 以降は最小ノードで進む（要件 3.3 / 14.6）。

## 確定事項（設計判断）

- **既定フォーマット**: `text`（要件 2.6）。
- **付帯情報の選択**: `--include` に `restriction` / `macros` / `attachments` / `last_modified` を空白区切りで複数指定。`--include all` で全 4 種。未指定なら付帯情報なし。
- **inline マーク規則**（要件 4.4）:
  - 個別アクセス制限あり: `🔒`
  - 添付: `📎N`（N は件数、0 件は非表示）
  - マクロ: `⚙N`（N はマクロ種別数、0 は非表示）
  - 最終更新日: `(YYYY-MM-DD)`
  - 取得失敗/不明: 該当項目を `?` で表す（例: 更新日不明 `(?)`）
  - 絵文字を使えない環境向けに、ASCII フォールバック（`--ascii`）で `[R]` / `att:N` / `mac:N` を使用可能とする。
- **Markdown 別表**: `macros`（全マクロ名）と `restriction`（Read / Read+Write とユーザー/グループ）は情報量が多いため、ツリー本体には軽量表記のみ inline 併記し、詳細はツリーの後ろにテーブルとして出力、page_id で突き合わせる（要件 4.2）。
- **json スキーマ**: 全付帯情報を各ノードに格納。`schema_version` を含める。初期値 `"1.0"`。
- **最終更新日の取得元**: 第一候補は `get_page` の `version.when`（ツリー探索時に `get_page` を呼ぶ場合は再利用できる）。マクロ取得で既に `get_page(expand="body.storage,version")` を呼ぶなら、同一レスポンスから更新日も取れるため、`macros` と `last_modified` を併用する場合は API 呼び出しを 1 回に集約する（最適化）。`last_modified` 単独指定時は `get_content_history` または `get_page(expand="version")`。
- **エラーコード**（`analyze` の規約に合わせる）: `0` 成功 / `2` INVALID_PARAM / `3` AUTH_FAILED / `4` TARGET_NOT_FOUND / `5` API_ERROR / `10` INTERNAL_ERROR。
- **循環参照対策**: 訪問済み page_id を集合で管理し、万一ループが生じても再帰が無限化しないようにする（通常 Confluence の親子は木構造だが防御的に実装）。

## データモデル（`page_tree/models.py`）

```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Annotation:
    """ノードの付帯情報。未取得の項目は None、取得失敗は failed フラグで区別する。"""

    has_restriction: Optional[bool] = None  # 個別制限の有無（未取得=None）
    read_subjects: List[str] = field(default_factory=list)  # Read 権のユーザー/グループ
    readwrite_subjects: List[str] = field(default_factory=list)
    macros: Optional[Dict[str, int]] = None  # マクロ名 -> 回数（未取得=None）
    attachment_count: Optional[int] = None  # 添付件数（未取得=None）
    last_modified: Optional[str] = None  # ISO 8601（未取得/不明=None）
    failed_fields: List[str] = field(default_factory=list)  # 取得失敗した項目名


@dataclass
class TreeNode:
    page_id: str
    title: str
    children: List["TreeNode"] = field(default_factory=list)
    annotation: Annotation = field(default_factory=Annotation)


@dataclass
class TreeResult:
    schema_version: str
    status: str  # "ok" | "error"
    roots: List[TreeNode]
    total_pages: int
    included_annotations: List[str]  # 要求された付帯情報の種類
    uncertainties: Dict[str, int]  # 項目別の取得失敗件数など
    scope: Dict[str, object]  # space_keys / root_page_ids / resolved_root_count
```

## 各フォーマットの出力例

### text（`--include restriction attachments last_modified`）

```
~user@example.com
└── ホーム  [id:19127895]  (2025-08-20)
    ├── 設計メモ 🔒  [id:84916196]  📎2  (2024-11-01)
    └── 作業中  [id:84923420]  (2025-07-15)
        └── 環境構築  [id:84910567]  📎1  (?)
```

### markdown（ツリー本体 + 別表）

```markdown
# ページツリー: ~user@example.com

- ホーム `19127895` (2025-08-20)
  - 設計メモ 🔒 `84916196` 📎2 (2024-11-01)
  - 作業中 `84923420` (2025-07-15)
    - 環境構築 `84910567` 📎1 (?)

## アクセス制限詳細

| page_id | title | Read | Read+Write |
|---|---|---|---|
| 84916196 | 設計メモ | group:dev | user:alice |

## マクロ使用（--include macros 指定時）

| page_id | title | マクロ（回数） |
|---|---|---|
| 84916196 | 設計メモ | code(3), plantuml(1) |
```

### json

```json
{
  "schema_version": "1.0",
  "status": "ok",
  "scope": { "space_keys": ["~user@example.com"], "root_page_ids": [], "resolved_root_count": 1 },
  "included_annotations": ["restriction", "attachments", "last_modified"],
  "total_pages": 4,
  "roots": [
    {
      "page_id": "19127895",
      "title": "ホーム",
      "annotation": {
        "has_restriction": false,
        "attachment_count": 0,
        "last_modified": "2025-08-20T10:00:00.000Z"
      },
      "children": [
        {
          "page_id": "84916196",
          "title": "設計メモ",
          "annotation": {
            "has_restriction": true,
            "read_subjects": ["group:dev"],
            "readwrite_subjects": ["user:alice"],
            "attachment_count": 2,
            "last_modified": "2024-11-01T09:00:00.000Z"
          },
          "children": []
        }
      ]
    }
  ],
  "uncertainties": { "restriction_failed": 0, "macro_failed": 0, "attachment_failed": 0, "history_failed": 1 }
}
```

エラー時（json 形式）:

```json
{
  "schema_version": "1.0",
  "status": "error",
  "error": { "code": "TARGET_NOT_FOUND", "message_en": "space not found", "exit_code": 4 }
}
```

## CLI 引数（`tree.py`）

| 引数 | 説明 | 既定 |
|---|---|---|
| `--base-url` | Confluence ベース URL | YAML / 環境 |
| `--space-key` | 起点 Space キー（複数可） | なし |
| `--root-page-id` | 起点ルートページ ID（複数可） | なし |
| `--format` | `text` / `markdown` / `json` | `text` |
| `--include` | `restriction` `macros` `attachments` `last_modified` `all`（複数可） | なし（付帯情報なし） |
| `--ascii` | 絵文字を使わず ASCII マークで表記 | `False` |
| `--output` | 出力先ファイル（省略時 stdout） | stdout |
| `--overwrite` | 出力ファイルの上書き許可 | `False` |
| `--max-depth` | 探索の最大深さ（0/未指定で無制限） | 無制限 |
| `--proxy` / `--config` / `--token` | 既存共通引数 | 既存踏襲 |

`--space-key` / `--root-page-id` のいずれも無い場合は INVALID_PARAM（exit 2）で日本語エラー。

## Skill 定義（`confluence-tree`）

- 正本: `skills/confluence-tree/SKILL.md` + `skills/confluence-tree/scripts/run_tree.py`
- `run_tree.py` は `confluence-analysis` の `run_analysis.py` と同形で、`python -m c2m_export.tree` に引数を素通しするサブプロセスラッパ。リポジトリルート探索で `PYTHONPATH` 非依存とする（`confluence-setup/diagnose.py` と同方式）。
- 複製先: `.kiro/skills/confluence-tree/` と `.github/skills/confluence-tree/`（正本からの上書きコピー）。
- SKILL.md 先頭に正本/複製/同期ルールのコメントを入れる（既存 2 スキルと同形式）。

## テスト方針

- **純粋ロジック（API 非依存）**: `builder.build_tree`（ネスト構築・循環防御）、`renderers`（text 罫線・markdown ネスト/別表・json 構造）、`annotations`（マクロ集計・制限判定・inline マーク生成・ASCII フォールバック）をフィクスチャ入力で単体テスト。
- **collector**: `ConfluenceClient` をモックし、opt-in 指定に応じて該当 API のみ呼ばれること、取得失敗時に `failed_fields` / `uncertainties` が積まれツリーが継続することを検証。
- **config**: CLI > 環境 > YAML > デフォルトの優先順位、必須チェック、`--include all` 展開、`--format` 検証。
- 既存テスト（`tests/`）の命名・配置規約に合わせ、`tests/test_tree_*.py` を追加。

## 既存コードへの影響

- 追加のみ。既存モジュールの変更は最小限（`config.py` に新クラス追加、エントリーポイント新設）。
- 既存 `fs_export/tree.py` は変更しない（目的が異なるため流用せず、可視化用に `page_tree/` を新設）。
- `README.md` / `README_DEV.md` / `c2m_config_sample.yaml` に新モードの記述・設定サンプルを追記。
- `.kiro/steering/structure.md` のツリー・責務表に `page_tree/` / `tree.py` / `confluence-tree` スキルを追記。
