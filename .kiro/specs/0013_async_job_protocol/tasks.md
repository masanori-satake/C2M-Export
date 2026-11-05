# Implementation Plan

0013 非同期ジョブプロトコル（応答性改善フェーズ 3）の実装計画。前提として spec 0011 / 0012（PR #70 / #71）がマージ済みであること。

- [x] 1. ジョブ基盤を実装する
  - `c2m_export/analysis/jobs.py`: ID 生成・検証、原子書き込み、status / result 要約、ワーカー起動、キャンセルフラグ。
  - `ProgressHeartbeat` に `on_tick` を追加し、`run_analysis` の `progress_sink` から渡す。
  - _要件: 1.1, 1.2, 2.1, 2.4, 3.1_

- [x] 2. CLI 配線を行う
  - `AnalysisConfig` にジョブ関連オプションを追加。`analyze.py` に操作コマンド / detach / ワーカーの分岐を実装（操作コマンドは設定検証の前に処理）。
  - _要件: 1.1, 2.2, 2.3, 3.2, 4.1, 5.3_

- [x] 3. スキル手順と補助スクリプトを更新する
  - `run_analysis.py`（正本＋複製2）: ジョブ操作コマンド時は既定 timeout を補わない。
  - `SKILL.md`（正本＋複製2）と `docs/ai_integration.md` / `README.md` / `README_DEV.md` に非同期手順を明記。
  - _要件: 5.1, 5.2_

- [x] 4. テストを追加する
  - ジョブ基盤（ID 検証・原子書き込み・status の stale 判定・result 要約・キャンセル）、ハートビートの on_tick、CLI の detach（Popen モック）/ ワーカー実行 / status・result の一連の流れを検証。
  - _要件: 1.1, 2.2, 3.2, 4.1_
