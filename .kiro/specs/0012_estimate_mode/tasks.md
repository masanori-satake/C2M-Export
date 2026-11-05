# Implementation Plan

0012 事前見積もりモード `--estimate`（応答性改善フェーズ 2）の実装計画。前提として spec 0011（PR #70）がマージ済みであること。

- [x] 1. 見積もり本体を実装する
  - `c2m_export/analysis/estimate.py` を新規作成（起点解決の再利用、子孫数集計、収集モデル、レイテンシ実測、判定フィールド）。
  - `AnalysisResponse` に `estimate` フィールドを追加し、未設定時は出力から除外する。
  - _要件: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 5.1, 5.2_

- [x] 2. CLI 配線を行う
  - `AnalysisConfig` に `--estimate`（YAML `analysis.estimate` 含む）を追加し、`analyze.py` で見積もりへ分岐する。
  - _要件: 1.1_

- [x] 3. 補助スクリプトとスキル手順を更新する
  - `run_analysis.py`（正本＋複製2）: `--estimate` 実行時は既定 timeout を補わない。
  - `SKILL.md`（正本＋複製2）と `docs/ai_integration.md` / `README.md` / `README_DEV.md` に見積もり手順と閾値を明記。
  - _要件: 4.1, 4.2_

- [x] 4. テストを追加する
  - 見積もり本体（ページ総数・想定リクエスト数・max_pages 丸め・子孫数失敗の明示・エラー分類）と、補助スクリプトの `--estimate` 時の既定値非補完を検証。
  - _要件: 1.2, 1.3, 2.5, 4.2, 5.2_
