# Implementation Plan

0011 スキル実行の応答性改善フェーズ 1（上限既定・無バッファ・ハートビート）の実装計画。前提として PR #69（実行保護リミット）がマージ済みであること。

- [x] 1. `ProgressHeartbeat` を実装する
  - `c2m_export/analysis/progress.py` を新規作成（間隔・フェーズ・件数コールバック、start/stop、コンテキストマネージャ）。
  - `tests/test_progress_heartbeat.py` で周期出力・フェーズ切替・停止を検証。
  - _要件: 3.1, 3.2, 3.4_

- [x] 2. `run_analysis` にハートビートとフェーズ開始ログを組み込む
  - 起動はタイムアウト計測開始直後、停止は `finally`。フェーズ境界（Space 一覧取得 / 起点解決 / 概要収集 / ページ収集 / Space 詳細 / 集計）で `set_phase` し、ページ収集では収集済み件数を併記。
  - _要件: 3.1, 3.2, 3.3, 3.4_

- [x] 3. Confluence クライアントのリトライログに待機秒数を含める
  - `c2m_export/confluence.py` の `_request` 2箇所。
  - _要件: 4.1_

- [x] 4. 補助スクリプトを無バッファ化し、スキル経由の既定上限 300 秒を実装する
  - `run_analysis.py`（正本＋複製2）: `build_command` 純粋関数で `-u` と既定補完を集約。`tests/test_run_analysis_wrapper.py` で検証。
  - `run_tree.py`（正本＋複製2）: `-u` のみ追加。
  - _要件: 1.1, 1.2, 2.1_

- [x] 5. ドキュメントへ反映する
  - `skills/confluence-analysis/SKILL.md`（正本＋複製2）と `docs/ai_integration.md` に、既定 300 秒・ハートビート 5 秒間隔・partial 時の `--resume` 判断を明記。
  - _要件: 1.1, 3.1, 5.1_

- [x] 6. 後方互換の確認
  - stdout の純粋 JSON 契約と schema_version 1.2 の不変、CLI 本体の既定（無制限）の不変を既存テストで確認。
  - _要件: 5.1, 5.2, 5.3_
