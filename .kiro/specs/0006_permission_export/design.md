# Design Document

## 概要

本設計は、Confluence のページに設定されたアクセス権限（コンテンツ制限）を取得し、**Read / Read+Write の保有者（ユーザー・グループ）を Markdown として出力する**機能を C2M-Export に追加する。目的は、エクスポートしたコンテンツを配置先（SharePoint / OneDrive 等、特定サービスに限定しない）へ移行した後、管理者が同等のアクセス設定を再適用する際の**参照情報**を提供することにある。配置先への権限の自動適用は行わない（記録のみ）。

権限取得には 0003 で追加予定の `ConfluenceClient.get_restrictions`（Data Center の `/rest/api/content/{id}/restriction/byOperation`、read/update を 1 リクエストで取得）を再利用する。継承された制限は**実効権限へ展開せず**、個別制限を持たないページは「継承/制限なし」と記す（案A）。これにより、個別に権限が設定された箇所＝管理者が意図的に権限を操作した箇所が浮かび上がる。

本機能は独立したエントリーポイント `python -m c2m_export.permexport` として提供し、既存の結合モード・0004 のファイルシステム出力の挙動を変えない。単独でも 0004 と併用（権限レポートのローカルパスを 0004 の出力構造に対応付け）でも動作する。

### 設計原則（既存方針の踏襲）

- **既存非破壊 / オプトイン**: 指定時のみ動作。結合モード・0004 は不変。
- **部分成功・日本語ログ**: 個別ページの権限取得失敗は集計して継続、現象・原因・対処方法で報告。
- **設定優先順位**: CLI > env > YAML > デフォルト。
- **API 負荷抑制**: `byOperation` で read/update を一括取得（ページあたり 1 リクエスト）。

## アーキテクチャ

### モジュール構成

```
c2m_export/
├── confluence.py          # [再利用] get_restrictions（0003で追加）/ get_child_pages / get_space_root_pages
├── config.py              # [拡張] PermissionExportConfig を新設（独立。既存クラスは不変）
├── permexport.py          # [新規] 権限エクスポートのエントリーポイント（python -m c2m_export.permexport）
├── permission/            # [新規] 権限エクスポートロジック一式
│   ├── __init__.py
│   ├── models.py          # PagePermission / PermissionReport / PermissionResult
│   ├── collector.py       # DFS巡回で各ページの制限を取得（I/O）
│   ├── report.py          # Markdown レポート生成（集約/分散）・任意JSON（純粋ロジック）
│   └── summary.py         # 処理サマリ（ログ + 日時サフィックスファイル）
└── (既存ファイル)
```

設定方針: 権限エクスポートは単独実行もできる独立機能のため、**`PermissionExportConfig` を新設**する（既存 `Config` / `AssessConfig` / `FsExportConfig` は不変）。0004 と併用する場合のパス対応付けに必要な設定（出力先・添付ディレクトリ名・命名方式）は 0004 と同じ既定を共有する形で持つ。

### 責務分担

| モジュール | 責務 |
|---|---|
| `permexport.py` | エントリーポイント。設定ロード→クライアント初期化→起点解決→collector→report→summary。 |
| `PermissionExportConfig` | 権限エクスポートの設定の読み込み・検証・正規化。 |
| `confluence.py`（再利用） | `get_restrictions` で read/update のユーザー/グループを取得。 |
| `permission/collector.py` | DFS 巡回で各ページの `PagePermission` を収集（I/O 層）。部分成功。 |
| `permission/report.py` | `PermissionReport` から Markdown（集約/分散）と任意 JSON を生成（純粋関数）。 |
| `permission/summary.py` | 出力/個別制限/継承/失敗の集計、ログ + 日時サフィックスファイル出力。 |

I/O（collector）と純粋ロジック（report）を分離し、report は API モック不要でテストする。

### 全体フロー

```mermaid
flowchart TD
    Start([python -m c2m_export.permexport]) --> Load[PermissionExportConfig.load/validate]
    Load --> Init[ConfluenceClient 初期化]
    Init --> Resolve[起点解決: root_page_ids / space_keys]
    Resolve --> Collect[collector: DFS巡回で各ページ制限取得]
    Collect --> Build[PermissionReport 構築]
    Build --> Report[report: Markdown（集約/分散） + 任意JSON]
    Report --> Summary[summary: 件数集計 + ファイル出力]
    Summary --> End([完了])

    Collect -. 権限取得失敗 .-> Skip[失敗集計して継続]
```

## コンポーネントと実装詳細

### 1. 権限取得（collector.py / 要件1・3）

- 既存 DFS 骨格で巡回し、各ページについて `get_restrictions(page_id)` を呼ぶ。
- 現行 `get_restrictions` は `byOperation` の JSON をそのまま返す。Collector が read / update それぞれの `restrictions.user.results`（`username` / `userKey` / `displayName`）と `restrictions.group.results`（`name`）を参照し、下記「識別子表現」に従って表示用文字列へ変換する。
- **個別制限の有無判定（案A / 要件3）**: 権限取得に成功し、read・update ともにユーザー/グループが空なら「継承/制限なし」とする。識別子欠落ユーザーも対象として残し、いずれかに対象があれば「個別制限あり」。取得失敗時は `has_explicit` を判定に使わない。親をさかのぼる実効権限展開は行わない。
- 本文・添付は扱わない（権限のみ）。0004 と併用時も権限取得は独立に行う。

### 2. データモデル（models.py）

```python
@dataclass
class PagePermission:
    page_id: str
    title: str
    space_key: str
    url: str                      # Confluence オリジナル URL
    rel_path: Optional[str]       # 0004 併用時のローカル相対パス（単独時は None）
    has_explicit: bool            # 取得成功時のみ有効。個別制限あり=True / 継承・制限なし=False
    read_users: list[str]         # 下記の識別子契約で正規化した表示用文字列
    read_groups: list[str]
    readwrite_users: list[str]    # update 操作キー = Read+Write
    readwrite_groups: list[str]
    fetch_failed: bool = False
    fail_reason: str = ""

@dataclass
class PermissionReport:
    pages: list[PagePermission]

@dataclass
class PermissionResult:
    report: PermissionReport
    exported_count: int          # 権限取得に成功して出力したページ数（失敗ページを除く）
    explicit_count: int          # fetch_failed=False かつ has_explicit=True
    inherited_count: int         # fetch_failed=False かつ has_explicit=False
    failed_page_ids: list[str]
```

### 3. 識別子表現（要件4.5）

- **選択優先順位**: Collector は非空の `username`（ログイン名）を突き合わせキーとして優先し、欠落時のみ非空の `userKey` を使う。`displayName` は表示専用であり、突き合わせキーには使わない。両キーがある場合も `username` を選ぶ。
- **正規化**: 各フィールドは文字列の前後の空白だけを `strip()` で除去する。キー欠落・`null`・非文字列・空文字・空白のみは「欠落」とする。大文字小文字変換・Unicode 正規化・内部空白の圧縮は行わず、別アカウントの混同を避ける。
- **表示形式と欠落時の扱い**:

  | username | userKey | displayName | 出力するユーザー文字列 |
  |---|---|---|---|
  | `t.yamada` | 任意 | `山田太郎` | `山田太郎 (t.yamada)` |
  | `t.yamada` | 任意 | 欠落 | `t.yamada` |
  | 欠落 | `key-001` | `山田太郎` | `山田太郎 (userKey: key-001)` |
  | 欠落 | `key-001` | 欠落 | `userKey: key-001` |
  | 欠落 | 欠落 | `山田太郎` | `山田太郎 (識別子不明)` |
  | 欠落 | 欠落 | 欠落 | `識別子不明` |

- **識別子欠落ユーザーは除外しない**: Read / Read+Write の元の列に残し、`has_explicit=True` の判定対象にも含める。識別子欠落を日本語の警告に記録し、配置先との突き合わせは不可と明示する。表示名からキーを捏造したり、同じ表示名のユーザーを統合したりしない。機械的な識別子の併記を必須とした従来案に対し、欠落時だけは「識別子不明」を許容する。
- グループ: グループ名（`name`）を使う。ユーザーの `userKey` フォールバックは `userKey:` の種別表示を含め、ログイン名と区別する。この表示契約は Markdown と任意 JSON のユーザー配列で共通とする。
- **確認根拠と fixture の制約**: 既存の `tests/test_confluence_assess_client.py::test_get_restrictions` は `username` のみを持つモックであり、実環境採取 fixture ではない。[Data Center 9.2 公式スキーマ](https://developer.atlassian.com/server/confluence/9.2.0.swagger.v3.json) の `User` は `username` / `userKey` / `displayName` を定義している。上表の欠落ケースは本 spec で定めるフォールバック契約である。実環境の匿名化済みレスポンス fixture は現在未収録のため、実装前に採取してフィールド・欠落パターンを照合し、`tests/test_perm_collector.py` の入力として保存する。実レスポンスで検証済みとは扱わない。

### 4. レポート出力（report.py / 要件4）

純粋関数で `PermissionReport` から生成する。格納形態を設定で選択。

- **集約（既定 / `report_layout=aggregate`）**: 出力先ルート直下に俯瞰ファイル（例: `_permissions.md`）を 1 つ生成。全ページを表形式で一覧し、どのページにどの権限が付与されているかを俯瞰できる。個別制限ありページを上に集める、または「個別制限あり」列で絞り込める構成とする。
- **分散（`report_layout=per_page`）**: 各ページ対応ディレクトリ（0004 の `rel_path`）に権限ファイル（例: `_permissions.md`）を配置。0004 併用時のみ有効（`rel_path` が必要）。単独実行時は集約にフォールバックし、その旨を日本語で通知。
- Markdown 内容: ページごとに page_id / タイトル / Confluence URL /（併用時）ローカル相対パス、Read 権（ユーザー・グループ）、Read+Write 権（ユーザー・グループ）、または「継承/制限なし」。
- **取得失敗の表示優先順位**: 集約・分散・任意 JSON ともに `fetch_failed` を最初に評価する。`True` のページは `has_explicit` の値によらず「取得失敗」と日本語の `fail_reason` を出力し、「継承/制限なし」や確定した権限一覧として表示しない。JSON は `fetch_failed` / `fail_reason` を保持し、失敗時の `has_explicit` とユーザー/グループ配列は未確定値として扱う。
- **件数の契約**: 失敗ページの行/ファイルも出力するが、`explicit_count`・`inherited_count`・`exported_count` のすべてから除外し、`failed_page_ids` に一度だけ算入する。出力成功時は `exported_count = explicit_count + inherited_count`、`len(report.pages) = exported_count + len(failed_page_ids)`。集約/分散や出力形式の数によってページ件数を増やさない。
- 冒頭注記: 本レポートは Confluence 側権限の記録であり配置先への自動適用ではないこと、継承は展開せず個別制限のみを示すこと、を明示（要件4.8・3.4）。
- **任意 JSON（要件4.7）**: `report_formats` に `json` を含める場合、機械可読な権限データも出力（キー安定）。既定は Markdown のみ。

集約レポートの表イメージ:

```
| ページ | 個別制限/取得状態 | Read(ユーザー/グループ) | Read+Write(ユーザー/グループ) | URL | 失敗理由 |
|---|---|---|---|---|---|
| 設計方針 | あり | 山田太郎 (t.yamada) / dev-team | 鈴木 (suzuki) / — | https://... | — |
| 議事録   | 継承/制限なし | — | — | https://... | — |
| 運用手順 | 取得失敗 | 未確定 | 未確定 | https://... | 権限取得に失敗。原因: 権限不足。対処: 閲覧権限を確認。 |
```

### 5. 対象範囲と起点解決（要件2）

- `root_page_ids` / `space_keys` を 0004/0005 と一貫した形で受け取る。
- Space 指定時は `get_space_root_pages` でトップレベルを列挙し各々を起点に DFS。
- 0004 併用時は 0004 と同じ命名規約で `rel_path` を算出し、権限レポートのローカルパス対応に用いる（`permission` 側に 0004 の命名ユーティリティを再利用）。

### 6. 設定（PermissionExportConfig / config.py）

既存クラスは不変。新設。

| キー | CLI | 既定 | 用途 |
|---|---|---|---|
| `root_page_ids` | `--root-page-id`（複数可） | なし | 起点ページ |
| `space_keys` | `--space-key`（複数可） | なし | 起点 Space |
| `output_dir` | `--output-dir` | `.` | レポート出力先 |
| `report_layout` | `--report-layout` | `aggregate` | 集約/分散（aggregate/per_page） |
| `report_formats` | `--report-format` | `md` | md / json / both |
| `attachment_dir_name` | `--attachment-dir` | `_attachments` | per_page 時の rel_path 整合用（0004 と共有） |
| `page_filename_mode` | `--page-filename-mode` | `title` | 同上（rel_path 算出の整合用） |
| `overwrite` | `--overwrite` | false | 既存レポートの上書き |

`validate()`: `root_page_ids` と `space_keys` の少なくとも一方が必須、`base_url`・`token` 必須。`base_url` は rstrip 正規化。`report_layout=per_page` かつ 0004 出力が無い（単独実行）場合は集約にフォールバックして警告。`c2m_config_sample.yaml` に権限セクションを追記。

### 7. エントリーポイント（permexport.py）

骨格は既存 `cli.py` を踏襲（日本語ログ→Config→クライアント初期化→起点解決→フェイルファスト（出力先）→collector→report→summary）。

```python
def main():
    config = PermissionExportConfig(); config.load(); config.validate()
    client = ConfluenceClient(config.base_url, config.token, config.proxy)
    roots = resolve_roots(client, config)
    report = collect_permissions(client, config, roots)   # collector
    write_permission_report(report, config)               # report（集約/分散 + 任意JSON）
    write_summary(report, config)                         # ログ + 日時サフィックスファイル
```

## エラーハンドリング

| 失敗点 | 挙動 |
|---|---|
| 起点ページ/Space が存在しない・権限なし | フェイルファストで終了。 |
| 個別ページの権限取得失敗 | 本文処理と独立に、`fetch_failed=True`・理由を記録して継続（要件6.1〜6.3）。 |
| 出力先の書き込み不可・既存競合（overwrite 無） | フェイルファストで終了。 |
| per_page 指定だが 0004 出力なし | 集約へフォールバックし日本語で通知。 |
| サマリ/レポート書き込み失敗 | 現象・原因・対処を日本語で報告。 |

## テスト戦略

- `tests/test_perm_report.py`: `PermissionReport` から集約 Markdown / per_page Markdown / JSON を生成し、Read・Read+Write の区別、継承表記、識別子契約、自動適用でない旨の注記、キー安定性を検証。`fetch_failed=True` と `has_explicit=True/False` の両組合せで「取得失敗」・理由が優先され、確定した権限/継承として表示されないことも検証（API モック不要）。
- `tests/test_perm_collector.py`: `ConfluenceClient` をモックし、個別制限あり/継承判定、部分成功を検証。識別子表の全ケース、両キー存在時の優先順位、空白・null・非文字列、識別子欠落ユーザーを除外せず制限ありとすることを検証。実環境採取 fixture による照合は収録後に実施する。
- `tests/test_perm_summary.py`: 成功/失敗混在時の件数契約（失敗は成功3件数の対象外、`exported_count = explicit_count + inherited_count`）、失敗IDの重複なし、日時サフィックスファイル名形式。
- `tests/test_permexport_config.py`: 優先順位・rstrip・既定値・必須チェック・`report_layout`/`report_formats` 列挙値・per_page フォールバック。
- 既存（結合モード・0004）テストが不変で通ること（非破壊）。

## 設計上の決定事項（0006）

1. **継承は展開しない（案A）**: 個別制限を持たないページは「継承/制限なし」。意図的な権限操作箇所を浮かび上がらせる。
2. **格納形態**: 既定は集約（トップレベル俯瞰ファイル）、`per_page` も選択可（0004 併用時のみ有効、単独時は集約フォールバック）。
3. **識別子**: username → userKey の優先順、displayName は表示専用。前後空白のみ除去し、両キー欠落ユーザーは「識別子不明」として残す。
4. **独立性**: `PermissionExportConfig` を新設し単独実行可能。0004 併用時は命名規約を共有して `rel_path` を対応付け。
5. **API 負荷**: `byOperation` で read/update を 1 リクエスト取得。
6. **自動適用はしない**: 記録のみ。レポートに明示。
7. **取得失敗の優先**: fetch_failed を最優先で表示し、理由を記録。失敗ページは exported/explicit/inherited の成功件数に含めない。

## 未確定事項（実装時に詰める）

- 集約レポートが大規模ページ数で肥大化する場合の分割（Space 別ファイル等）の要否。
- スペース権限・グローバル権限を補足情報として併記するか（本 spec の主対象はページのコンテンツ制限）。
- 実環境の匿名化済み `get_restrictions` レスポンス fixture の収録・照合（識別子の優先順位・正規化・欠落時の表記契約は上記で確定）。
