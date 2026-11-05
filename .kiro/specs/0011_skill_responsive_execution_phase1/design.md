# Design Document

## 概要

フェーズ 1 は3点の小変更で構成する。新規依存は導入しない（標準 `threading` / `time` のみ）。

1. **スキル経由の上限既定**: 補助スクリプト `run_analysis.py` に純粋関数 `build_command(argv)` を切り出し、`-u` 付与と `--timeout-seconds` 既定 300 秒の補完をここに集約する。テストは `build_command` を対象に書ける。
2. **ハートビート**: 新規モジュール `c2m_export/analysis/progress.py` に `ProgressHeartbeat`（デーモンスレッド、既定 5 秒間隔、フェーズ名と任意の件数コールバックを保持）を置く。`run_analysis` が開始時に起動し、各フェーズ境界で `set_phase()` を呼び、ページ収集では `set_counter()` に `len(collector.raw_inventory.pages)` を渡す。終了は `run_analysis` の `finally` で `stop()` を必ず呼ぶことで担保する（正常・エラーの全経路）。
3. **リトライ可視化**: `ConfluenceClient._request` の2箇所のスリープについて、待機秒数を先に変数へ確定し、警告ログに含める。

## 配置

- `c2m_export/analysis/progress.py`（新規）
- `c2m_export/analysis/api.py`（ハートビートのライフサイクルとフェーズ境界ログ）
- `c2m_export/confluence.py`（リトライログ）
- `skills/confluence-analysis/scripts/run_analysis.py` ほか複製2箇所（`build_command` 化）
- `skills/confluence-tree/scripts/run_tree.py` ほか複製2箇所（`-u` のみ）
- `skills/confluence-analysis/SKILL.md` ほか複製2箇所・`docs/ai_integration.md`（既定 300 秒とハートビートの明記）

## 判断

- 既定 300 秒はスキル経由のみに適用し、CLI 本体の既定（無制限）は変えない。長時間の直接実行は利用者の明示判断に委ねる方が、既存の運用（大規模スペースの全件分析など）を壊さない。
- ハートビートは「無音を検知して出す」のではなく無条件に周期出力する。実装が単純で、フェーズログと重なっても害がない（stderr の情報ログ）。
- ハートビートのスレッドはデーモンとし、万一 `stop()` が呼ばれなくてもプロセス終了を妨げない。
