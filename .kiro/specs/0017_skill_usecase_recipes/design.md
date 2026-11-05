# Design: ユースケース別レシピ集（spec 0017）

- 新規ファイル `references/usecases.md`（3 箇所同期）。冒頭に「いつ読むか」と共通前提（見積もり→決定表）を置く。
- レシピの見どころは `c2m_export/analysis/api.py` の実装に基づく実在キーで記述する:
  - risk: `counts.total_risk_pages`、`counts.risk_summary`（種別内訳）
  - stale: `counts.stale_page_count`、`counts.freshness_distribution`、items の `days_since_modified`
  - restricted: `counts.explicit_restriction_count`、`unique_users_count`、`unique_groups_count`。制限収集なし（`--no-restrictions`）では常に0件になる注意を明記する
  - archives: `file_count`、`total_size_bytes`、`extensions`（拡張子別内訳）、`size_meta_missing_count`
  - empty_with_attachments: `counts.empty_with_attachments_count`、閾値は `--min-body-bytes`
  - macros: `total_macro_types`、detail の `repair_category` / `repair_reason`
- SKILL.md 本体は「分析ユースケース一覧」の末尾にポインタ1行のみ追加する。
