# ユースケース別レシピ

目的別の推奨パラメータ・コマンド例・結果の見どころです。依頼の目的がはっきりしている場合に、該当するレシピを参照してください。

どのレシピでも、まず `--estimate` で規模を確認し、SKILL.md 本体の決定表に従って実行方法（同期 / 非同期 / 分割の提示）を決めてください。コマンド例は補助スクリプト経由の形で示します（`--base-url` は実際の URL に置き換えてください）。

## 古いページの棚卸し（stale）

- 目的: 長期間更新されていないページの洗い出し。
- コマンド例:
  ```bash
  python skills/confluence-analysis/scripts/run_analysis.py \
    --base-url "https://confluence.example.com" \
    --space-key "DEV" \
    --usecase "stale" --mode "detail"
  ```
  判定基準を変える場合は `--stale-days`（既定 365）を指定します。
- 見どころ: `counts.stale_page_count`（該当件数）と `counts.freshness_distribution`（鮮度の分布）。個別一覧では `days_since_modified`（最終更新からの日数）が大きいものから確認します。

## 移設リスクの洗い出し（risk）

- 目的: 移行先で問題になりやすいページ（パス長超過、不正文字、ブロック拡張子、大容量ファイル等）の特定。
- 進め方: まず `--mode "summary"` で種別ごとの件数を見て、対象種別が分かったら `--mode "detail"` で個別一覧を取得します。
- 見どころ: `counts.total_risk_pages` と `counts.risk_summary`（種別内訳）。

## 個別制限の棚卸し（restricted）

- 目的: 親からの継承ではなく個別にアクセス制限が設定されたページと、関係するユーザー / グループの把握。
- 注意: 制限情報を収集しない実行（`--no-restrictions`）では件数が常に 0 になり、この usecase は意味を持ちません。必ず制限収集ありで実行してください。制限収集はコストが高いため、見積もりとセットで規模を判断してください。
- 見どころ: `counts.explicit_restriction_count`（個別制限のあるページ数）、`counts.unique_users_count` / `counts.unique_groups_count`（関係するユーザー / グループの種類数）。

## 圧縮ファイルの把握（archives）

- 目的: zip / 7z / tar などの圧縮ファイルの総量把握（移行時の展開・保管コストの見積もり）。
- 見どころ: `file_count` と `total_size_bytes`、`extensions`（拡張子別の件数・合計サイズ・最大サイズ）。`size_meta_missing_count` が大きい場合、合計サイズは過小評価になっている点に注意してください。

## 添付あり空ページの検出（empty_with_attachments）

- 目的: 本文がほとんど空で添付ファイルだけがあるページの検出（移行漏れや置き場化の発見）。
- コマンド例: `--usecase "empty_with_attachments" --mode "detail"`。本文の閾値は `--min-body-bytes`（既定 200 バイト未満）で変更できます。
- 見どころ: `counts.empty_with_attachments_count`。

## マクロの移行影響調査（macros）

- 目的: Markdown 変換で影響を受ける Confluence マクロの把握と、手作業修復が必要な箇所の見積もり。
- 進め方: まず `--mode "summary"` でマクロ名と件数の一覧を見て、`--mode "detail"` では修復候補の分類まで確認します。
- 見どころ: `total_macro_types`（マクロの種類数）と件数上位のマクロ。detail の各レコードにある `repair_category`（手作業修復候補の分類）と `repair_reason`（理由）が見積もりの材料になります。

## ワークスペース全体把握（--all-spaces）

- 目的: 全スペースの概要を掴み、深掘りする対象の当たりを付ける。
- コマンド例:
  ```bash
  python skills/confluence-analysis/scripts/run_analysis.py \
    --base-url "https://confluence.example.com" \
    --all-spaces --mode "summary"
  ```
- 見どころ: `workspace.total_spaces` とスペース別概要、`summary` の総ページ数・添付総数。規模が大きい場合は、スペース単位に分割して個別のレシピで深掘りしてください。
