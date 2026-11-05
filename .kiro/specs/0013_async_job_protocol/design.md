# Design Document

## 構成

- `c2m_export/analysis/jobs.py`（新規）: ジョブ ID 生成・検証、パスの解決、原子書き込み、ジョブ記録の作成、status / result 要約の構築、ワーカーの起動（`start_job`）、キャンセルフラグ。
- `c2m_export/analysis/progress.py`（変更）: `ProgressHeartbeat` に `on_tick` コールバック（フェーズ・経過・収集済み件数）を追加。ログ出力の振る舞いは不変。
- `c2m_export/analysis/api.py`（変更）: `run_analysis` に `progress_sink` 引数を追加し、ハートビートへ渡す。
- `c2m_export/config.py`（変更）: `--detach` / `--job-status` / `--job-result` / `--job-cancel` / `--job-dir` と、内部用の `--async-worker` / `--job-id`（help 非表示）を追加。これらは CLI 専用とし YAML には載せない。
- `c2m_export/analyze.py`（変更）: 起動フローに分岐を追加。
  1. ジョブ操作コマンド（status / result / cancel）は設定検証（base_url 等）の前に処理し、ファイルだけを読んで即座に返す。
  2. `--detach` は検証後に `jobs.start_job` でワーカーを起動し、開始 JSON を返して終了する。ワーカーのコマンドラインは元の引数から `--detach` を除き `--async-worker --job-id <id>` を加えたもの。
  3. ワーカーモード（`--async-worker`）では、見積もり（推定総ページ数）→ 本実行（progress_sink で進捗書き込み、キャンセルフラグも中断条件に合成）→ 結果ファイル書き出し → 進捗の最終化、を行う。標準出力は親がジョブディレクトリ内のログファイルへリダイレクトする。

## 進捗ファイル

`progress.json` の主なフィールド: `job_id`, `state`（running / done / partial / error）, `phase`, `elapsed_seconds`, `processed`, `estimated_total`, `last_collected_page_id`, `last_update`（ISO 8601）, `started_at`, `finished_at`, `result_file`。status はこれを読み、state=running かつ `last_update` が 90 秒より古ければ `stale: true` と注記を付ける。

## セキュリティ上の配慮

- ジョブ ID は英数字・ハイフン・アンダースコアのみ許可し、パスの要素として安全な形に限定する（status 等の引数検証）。
- ジョブ記録・進捗にトークンを含めない。結果ファイルは本実行の出力（サニタイズ済み JSON）と同一。
- ワーカーのログファイルには stderr の進捗ログが入る（トークンは含まれない。クライアントのログには URL や認証情報を出さない既存方針に従う）。

## MCP について

計画では3ツール化を「検討」としていた。検討結果として本フェーズでは見送る。理由: MCP サーバは常駐プロセスで、ジョブの寿命（サーバ再起動をまたぐか）と結果ファイルの受け渡しモデルの決定が別途必要になるため。今回のファイルベース基盤は MCP からも参照可能であり、将来の追加を妨げない。
