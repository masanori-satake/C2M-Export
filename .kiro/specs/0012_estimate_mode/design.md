# Design Document

## 概要

新規モジュール `c2m_export/analysis/estimate.py` に `estimate_analysis(params, config, client=None, interrupt_checker=None)` を置き、`analysis/api.py` の `_resolve_roots` を再利用する。CLI は `AnalysisConfig.estimate`（`--estimate` / YAML `analysis.estimate`）で分岐し、`analyze.py` が見積もり関数を呼ぶ。

## レイテンシ実測

見積もりで使うクライアントを数え上げ用の薄いプロキシ（`_CountingClient`）で包み、呼び出し件数と経過時間から平均レイテンシを求める。プロキシはメソッド呼び出しを透過し、件数だけを数える。

## 推定モデル

- 対象ページ数: 起点ごとに `1 + descendant_count` の合計。起点同士の重なりは検出できないため二重計数の可能性を notes に明記する。
- 1ページあたりリクエスト数: 基本3件（`get_page` / `get_attachments` / `get_child_pages`）+ `analyze_restrictions`（既定有効）1件 + 有効な収集フラグ（history / labels / comments / watchers / effective_restrictions）各1件。フラグ解決は本実行の `_resolve_flag` と同じ規則（params > config > deep）。`collect_extracted_text` は添付単位のため換算せず notes に明記する。
- 固定リクエスト数: 5件（利用者・アクセスモード・サーバ情報等）+ 全体把握の Space 単位コスト 2件 × 参照可能 Space 数 + Space 詳細（権限・ウォッチャー有効時に対象 Space 数 × 有効フラグ数）。
- 想定リクエスト数 = 固定 + 有効ページ数 × 1ページあたり件数。有効ページ数は `max_pages` 指定時に上限で丸める。
- 推定所要秒数 = 想定リクエスト数 × 実測平均レイテンシ。本実行は本文取得を含むため重く、下限寄りの目安であることを notes とドキュメントで明示する。

## 出力

`AnalysisResponse` に `estimate: Optional[Dict]` を追加し、`to_dict()` では未設定時にキーを除外する（`error` と同じ扱い）。見積もり時は status は `ok`、scope は通常実行と同じく解決結果を入れ、summary / usecases は空とする。

## 判断

- 見積もりでも Space 一覧取得を行う。本実行の全体把握フェーズは全 Space を走査するため、その規模を見積もりに含めないと過小評価になる。
- 閾値（120 秒 / 500 ページ）と既定上限（300 秒）は見積もりモジュールの定数とし、判定結果をフィールドで返す。スキル側の手順はこの判定を参照する。
- MCP への見積もりツール追加は本フェーズの対象外（CLI + スキルで効果を検証してから判断する）。
