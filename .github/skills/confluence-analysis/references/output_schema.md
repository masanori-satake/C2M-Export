# 出力 JSON スキーマと結果構造（詳細）

分析結果 JSON の全フィールド仕様と、`schema_version` の互換性ポリシーです。SKILL.md 本体には結果の読み方の要点のみを載せています。結果 JSON の解釈に迷った場合に参照してください。

標準出力 (stdout) には、純粋な JSON のみが単独で出力されます。進捗ログや警告は標準エラー出力 (stderr) に分離されます。

```json
{
  "schema_version": "1.2",
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
    "unavailable_apis": [],
    "interrupted": false,
    "interrupted_reason": null,
    "collected_page_count": 120,
    "resumed_from_checkpoint": false,
    "checkpoint_reused_count": 0,
    "checkpoint_corrupted_line_count": 0
  }
}
```

## `schema_version` の互換性ポリシー

- 現在のバージョンは `"1.2"` です。
- キーの追加や非破壊的な変更（マイナー更新）では `schema_version` のメジャー番号は変更されません。
- 既存キーの削除や型の不互換な変更（メジャー更新）が行われる場合は、`schema_version` がインクリメントされます。
