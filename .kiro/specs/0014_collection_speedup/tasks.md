# Implementation Plan

0014 収集の高速化（応答性改善フェーズ 4）の実装計画。前提として spec 0011〜0013（PR #70〜#72）がマージ済みであること。

- [x] 1. ルート確認を `expand=version` に軽量化する
  - `analysis/api.py` の `_resolve_roots`。
  - _要件: 1.1_

- [x] 2. 子ページの一括先読みを実装する
  - `assessment/collector.py` の `collect` に先読みとフォールバックを追加。
  - _要件: 2.1, 2.2, 2.3_

- [x] 3. セッション分離と全体把握の並列化を実装する
  - `confluence.py` にスレッドローカルセッションを導入。`collect_workspace_overview` を Space 単位に切り出して並列化（並列度は Collector 引数、解決・検証は run_analysis と設定側）。
  - _要件: 3.1, 3.2, 3.3, 3.4, 5.1_

- [x] 4. timeout の connect / read 分離を実装する
  - `ConfluenceClient` の任意引数と、分析設定（CLI / YAML）からの引き渡し。
  - _要件: 4.1, 4.2_

- [x] 5. ドキュメントとテストを整備する
  - README / README_DEV / ai_integration / SKILL.md へ反映。先読み・並列・timeout・セッション分離の単体テストと、巡回結果が先読みの有無で不変であることの検証。
  - _要件: 2.3, 3.2, 5.2_
