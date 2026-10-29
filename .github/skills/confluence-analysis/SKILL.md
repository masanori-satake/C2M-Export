---
name: confluence-analysis
description: Confluence のワークスペース状況（古いページ、個別アクセス制限、移設リスク、圧縮ファイル、添付あり空ページ、マクロ使用統計）を分析し、機械可読な JSON レポートを返します。
---

<!--
NOTE: 正本は skills/confluence-analysis/SKILL.md です。
各ツールの検出・発火条件（.kiro/skills/: Kiro、.github/skills/: GitHub Copilot、skills/: 汎用 Agent Skills）に合わせて 3 箇所に複製配置されています。
SKILL.md や scripts を修正・更新する場合は、必ず正本を編集し、複製先へ同期（上書きコピー）を行ってください。
-->

# Confluence Workspace Analysis Skill

この Skill は、Confluence のページ階層・スペースの状況を分析し、AI ナレッジ化や移行に向けた課題（古いコンテンツ、権限設定、圧縮ファイル、マクロ統計等）を機械可読な JSON で出力します。

## 前提要件

- **Python**: Python 3.8 以上が導入されていること。
- **リポジトリ**: C2M-Export のソースコードがローカル環境にチェックアウトされており、依存ライブラリがインストールされていること。
  ```bash
  pip install -r requirements.txt
  ```
- **認証情報**: Confluence 個人用アクセスアクセストークン（PAT）を環境変数 `C2M_CONFLUENCE_TOKEN`（推奨）または `CONFLUENCE_TOKEN` に設定していること。
  ```bash
  export C2M_CONFLUENCE_TOKEN="your-confluence-pat"
  ```
  ※ トークンをコマンドライン引数（`--token`）で直接渡すと、プロセス一覧やシェル履歴に記載が残るため推奨されません。

## 実行方法

本 Skill は、サブプロセスとして CLI エントリーポイント `python -m c2m_export.analyze` または補助スクリプト `python skills/confluence-analysis/scripts/run_analysis.py` を呼び出して動作します。

### 基本的なコマンド

```bash
python -m c2m_export.analyze \
  --base-url "https://confluence.example.com" \
  --space-key "DEV" \
  --usecase "risk" "stale" "restricted" \
  --mode "summary"
```

または補助スクリプトを使用:

```bash
python skills/confluence-analysis/scripts/run_analysis.py \
  --base-url "https://confluence.example.com" \
  --space-key "DEV" \
  --usecase "stale" \
  --mode "detail" \
  --limit 50
```

## 入力パラメータ（CLI オプション）

| オプション | 型 | 説明 | 既定値 |
|---|---|---|---|
| `--base-url` | 文字列 (必須) | Confluence のベース URL (例: `https://confluence.example.com`) | なし |
| `--space-key` | 文字列リスト | 対象の Confluence Space キー (複数指定可) | なし |
| `--root-page-id` | 文字列リスト | 対象のルートページ ID (複数指定可) | なし |
| `--all-spaces` | フラグ | 参照可能な全 Space を起点として分析 | `False` |
| `--cql` | 文字列 | 起点検索用または課題抽出用の CQL 文字列 | なし |
| `--usecase` | 文字列リスト | 分析ユースケース (`risk`, `stale`, `restricted`, `archives`, `empty_with_attachments`, `macros`) | 全 6 種 |
| `--mode` | 文字列 | 出力モード (`summary`: 集計サマリのみ, `detail`: 個別一覧含む) | `summary` |
| `--limit` | 整数 | `detail` モード時の個別項目抽出上限件数 | `1000` |
| `--stale-days` | 整数 | 古いページの判定基準日数 | `365` |
| `--stale-years` | 浮動小数点/整数 | 古いページの判定基準年数 (`--stale-days` と両方指定時は `--stale-days` 優先) | なし |
| `--min-body-bytes` | 整数 | 添付あり空ページの判定基準バイト数 | `200` |
| `--archive-ext` | 文字列リスト | 圧縮形式とみなす拡張子一覧 | `zip 7z rar gz tar bz2 xz tgz lzh cab` |
| `--restrictions` / `--no-restrictions` | フラグ | アクセス制限（権限）情報の収集可否 | 自動収集 (有効) |
| `--deep` | フラグ | 詳細調査フェーズの情報を一括で有効化 | `False` |
| `--collect-history` / `--no-collect-history` | フラグ | ページ更新履歴の個別収集制御 | `deep` に依存 |
| `--collect-labels` / `--no-collect-labels` | フラグ | ラベル情報の個別収集制御 | `deep` に依存 |
| `--collect-comments` / `--no-collect-comments` | フラグ | コメント情報の個別収集制御 | `deep` に依存 |
| `--collect-watchers` / `--no-collect-watchers` | フラグ | ウォッチャー情報の個別収集制御 | `deep` に依存 |
| `--collect-effective-restrictions` / `--no-collect-effective-restrictions` | フラグ | 実効アクセス制限の個別収集制御 | `deep` に依存 |
| `--collect-extracted-text` / `--no-collect-extracted-text` | フラグ | 抽出テキストの個別収集制御 | `deep` に依存 |
| `--collect-space-permissions` / `--no-collect-space-permissions` | フラグ | Space 権限情報の個別収集制御 | `deep` に依存 |
| `--proxy` | 文字列 | HTTP/HTTPS プロキシ URL | なし |
| `--config` | 文字列 | 設定ファイルのパス | `c2m_config.yaml` |
| `--token` | 文字列 | Confluence Bearer トークン (環境変数推奨) | なし |

※ `--space-key`、`--root-page-id`、`--all-spaces`、`--cql` の少なくとも 1 つが必須です。

## 分析ユースケース一覧

1. `risk`: 移設リスクが高いページ（パス長超過、不正文字、ブロック拡張子、大容量ファイル等）
2. `stale`: 一定期間（既定 1 年）以上更新されていない古いページ
3. `restricted`: 親からの継承ではなく、個別のアクセス制限が設定されているページ
4. `archives`: zip / 7z / tar などの圧縮形式ファイルの個数と概算合計サイズ
5. `empty_with_attachments`: 添付ファイルは存在するが、本文がほとんど空（既定 200 バイト未満）のページ
6. `macros`: 使用されている Confluence マクロの統計と手作業修復候補カテゴリ（Markdown 変換時影響）

## 出力 JSON スキーマと結果構造

標準出力 (stdout) には、純粋な JSON のみが単独で出力されます。進捗ログや警告は標準エラー出力 (stderr) に分離されます。

```json
{
  "schema_version": "1.1",
  "status": "ok",
  "generated_at": "2026-03-31T00:00:00Z",
  "mode": "detail",
  "scope": {
    "root_page_ids": [],
    "space_keys": ["DEV"],
    "resolved_root_count": 10
  },
  "workspace": {
    "total_spaces": 1,
    "spaces": []
  },
  "visibility": {
    "anonymous_access": false,
    "unavailable_apis": []
  },
  "environment": {
    "confluence_version": "9.2.0"
  },
  "summary": {
    "total_pages": 120,
    "total_attachments": 45,
    "total_attachment_bytes": 10485760
  },
  "usecases": {
    "stale": {
      "counts": {
        "stale_page_count": 15,
        "stale_threshold_days": 365
      },
      "items": [
        {
          "page_id": "123456",
          "title": "古い設計書",
          "last_modified": "2023-01-01T00:00:00Z",
          "days_since_modified": 1185
        }
      ],
      "truncated": false,
      "total_count": 15
    }
  },
  "uncertainties": {
    "skipped_page_ids": [],
    "skipped_attachment_refs": [],
    "restriction_failed_page_ids": [],
    "size_meta_missing_count": 0,
    "macro_parse_failed_count": 0,
    "empty_space_keys": [],
    "restrictions_disabled": false,
    "history_failed_count": 0,
    "label_failed_count": 0,
    "comment_failed_count": 0,
    "effective_restriction_failed_count": 0,
    "extracted_text_failed_count": 0,
    "content_watcher_failed_count": 0,
    "space_watcher_failed_count": 0,
    "space_permission_failed_count": 0,
    "cql_failed": false,
    "unavailable_apis": []
  }
}
```

## 終了コード規約

- `0`: 成功 (`ok`)
- `2`: パラメータ不正 (`INVALID_PARAM`)
- `3`: 認証失敗 (`AUTH_FAILED`)
- `4`: 対象未存在 (`TARGET_NOT_FOUND`)
- `5`: Confluence API / ネットワークエラー (`API_ERROR`)
- `10`: 内部エラー (`INTERNAL_ERROR`)

エラー発生時も、標準出力に `status: "error"` の構造化 JSON (ErrorObject) が出力されます（標準エラー出力には日本語詳細メッセージが出力されます）。

## `schema_version` の互換性ポリシー

- 現在のバージョンは `"1.1"` です。
- キーの追加や非破壊的な変更（マイナー更新）では `schema_version` のメジャー番号は変更されません。
- 既存キーの削除や型の不互換な変更（メジャー更新）が行われる場合は、`schema_version` がインクリメントされます。
