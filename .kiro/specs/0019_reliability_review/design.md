# Design: 信頼性レビュー（spec 0019）

## 方法

- 各観点について、対象モジュールの実装を読み、対応するテストがその壊れ方をカバーしているかを確認する。
- 静的確認で判断できないものは、小さな再現スクリプト（モック Confluence クライアントまたは実プロセス）で挙動を確かめる。
- 所見は本 spec の review.md に観点ごとに記録する（確認済み / 問題あり / 仕様として許容、の3区分と根拠）。

## 対象モジュール

- V1: `c2m_export/analysis/jobs.py`、`c2m_export/analyze.py` のジョブディスパッチ
- V2: `c2m_export/assessment/collector.py` のチェックポイント読み書きと resume 適用箇所、`c2m_export/analysis/api.py`
- V3: `c2m_export/assessment/collector.py` の先読み経路と `c2m_export/confluence.py` の子孫取得
- V4: `c2m_export/analysis/api.py` の全体把握並列化、`c2m_export/confluence.py` のスレッドローカルセッション
- V5: `c2m_export/analysis/estimate.py`
- V6: `tests/` 全体（特に test_jobs / test_speedup / test_collector_checkpoint）
- V7: ジョブ保存・チェックポイント保存・ログ出力の各経路と sanitize の適用範囲

## 修正方針

- 修正は「確認された問題」に対してのみ、最小限で行う。ついでのリファクタリングはしない。
- 修正には必ず回帰テストを付ける。テスト追加でカバーできる問題は、まずテストで再現を固定してから直す。
