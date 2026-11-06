# CLI オプション全表

confluence-analysis スキル（`python -m c2m_export.analyze` および補助スクリプト `scripts/run_analysis.py`）の全オプションです。SKILL.md 本体には頻出オプションの抜粋のみを載せています。本体に無いオプションが必要な場合や、既定値を確認したい場合に参照してください。

| オプション | 型 | 説明 | 既定値 |
|---|---|---|---|
| `--base-url` | 文字列 (必須) | Confluence のベース URL (例: `https://confluence.example.com`) | なし |
| `--space-key` | 文字列リスト | 対象の Confluence Space キー (複数指定可) | なし |
| `--root-page-id` | 文字列リスト | 対象のルートページ ID (複数指定可) | なし |
| `--all-spaces` | フラグ | 参照可能な全 Space を起点として分析 | `False` |
| `--cql` | 文字列 | 起点検索用または課題抽出用の CQL 文字列 | なし |
| `--usecase` | 文字列リスト | 分析ユースケース (`risk`, `stale`, `restricted`, `archives`, `empty_with_attachments`, `macros`) | 全 6 種 |
| `--mode` | 文字列 | 出力モード (`summary`: 集計サマリのみ, `detail`: 個別一覧含む) | `summary` |
| `--limit` | 整数 | `detail` モード時の個別項目抽出上限件数 | `1000` |
| `--stale-days` | 整数 | 古いページの判定基準日数 | `365` |
| `--stale-years` | 浮動小数点/整数 | 古いページの判定基準年数 (`--stale-days` と両方指定時は `--stale-days` 優先) | なし |
| `--min-body-bytes` | 整数 | 添付あり空ページの判定基準バイト数 | `200` |
| `--archive-ext` | 文字列リスト | 圧縮形式とみなす拡張子一覧 | `zip 7z rar gz tar bz2 xz tgz lzh cab` |
| `--restrictions` / `--no-restrictions` | フラグ | アクセス制限（権限）情報の収集可否 | 自動収集 (有効) |
| `--deep` | フラグ | 詳細調査フェーズの情報を一括で有効化 | `False` |
| `--collect-history` / `--no-collect-history` | フラグ | ページ更新履歴の個別収集制御 | `deep` に依存 |
| `--collect-labels` / `--no-collect-labels` | フラグ | ラベル情報の個別収集制御 | `deep` に依存 |
| `--collect-comments` / `--no-collect-comments` | フラグ | コメント情報の個別収集制御 | `deep` に依存 |
| `--collect-watchers` / `--no-collect-watchers` | フラグ | ウォッチャー情報の個別収集制御 | `deep` に依存 |
| `--collect-effective-restrictions` / `--no-collect-effective-restrictions` | フラグ | 実効アクセス制限の個別収集制御 | `deep` に依存 |
| `--collect-extracted-text` / `--no-collect-extracted-text` | フラグ | 抽出テキストの個別収集制御 | `deep` に依存 |
| `--collect-space-permissions` / `--no-collect-space-permissions` | フラグ | Space 権限情報の個別収集制御 | `deep` に依存 |
| `--no-checkpoint` | フラグ | チェックポイント永続化を無効化 | 自動保持 (有効) |
| `--resume` | フラグ | 既存のチェックポイントから未収集分を再開 | `False` |
| `--checkpoint-interval` | 整数 | チェックポイント flush 粒度 (件数) | `1` |
| `--checkpoint-dir` | 文字列 | チェックポイント保存先ディレクトリ | `.c2m_analyze_checkpoint` |
| `--timeout-seconds` | 整数 | 走査・分析処理の最大実行時間（秒） | なし (無制限) |
| `--max-pages` | 整数 | 走査する最大ページ数上限 | なし (無制限) |
| `--estimate` | フラグ | 本実行を行わず、対象ページ数と推定所要のみを見積もって返す | オフ |
| `--detach` | フラグ | 分析を別プロセスで開始し、job_id を即座に返す | オフ |
| `--job-status` | 文字列 | 指定ジョブの進捗を即座に返す | なし |
| `--job-result` | 文字列 | 指定ジョブの結果要約と結果ファイルのパスを返す | なし |
| `--job-cancel` | 文字列 | 指定ジョブに中断を要求する | なし |
| `--job-dir` | 文字列 | ジョブの保存先ディレクトリ | `.c2m_analyze_jobs` |
| `--concurrency` | 整数 | 全体把握フェーズの並列度（負荷を抑えたい場合は 1〜2） | `4` |
| `--connect-timeout-seconds` | 整数 | API 接続 timeout（秒） | 従来動作 |
| `--read-timeout-seconds` | 整数 | API 読み取り timeout（秒） | 従来動作 |
| `--descendant-count-read-timeout-seconds` | 整数 | 子孫数取得 API 専用の読み取り timeout（秒）。大きなツリーで子孫数取得が timeout する場合に延長する | 従来動作 |
| `--proxy` | 文字列 | HTTP/HTTPS プロキシ URL | なし |
| `--config` | 文字列 | 設定ファイルのパス | `c2m_config.yaml` |
| `--token` | 文字列 | Confluence Bearer トークン (環境変数推奨) | なし |

※ `--space-key`、`--root-page-id`、`--all-spaces`、`--cql` の少なくとも 1 つが必須です。
