---
name: confluence-analysis
description: Confluence のワークスペース状況（古いページ、個別アクセス制限、移設リスク、圧縮ファイル、添付あり空ページ、マクロ使用統計）を分析し、機械可読な JSON レポートを返します。
---

<!--
NOTE: 正本は skills/confluence-analysis/SKILL.md です。
各ツールの検出・発火条件（.kiro/skills/: Kiro、.github/skills/: GitHub Copilot、skills/: 汎用 Agent Skills）に合わせて 3 箇所に複製配置されています。
SKILL.md・references・scripts を修正・更新する場合は、必ず正本を編集し、複製先へ同期（上書きコピー）を行ってください。
-->

# Confluence Workspace Analysis Skill

この Skill は、Confluence のページ階層・スペースの状況を分析し、AI ナレッジ化や移行に向けた課題（古いコンテンツ、権限設定、圧縮ファイル、マクロ統計等）を機械可読な JSON で出力します。

本書は実行手順と判断ルールに絞った要点版です。詳細情報は references に分けてあり、各節のポインタから辿れます。

## 前提要件

- **Python**: Python 3.11 以上が導入されていること。
- **リポジトリ**: C2M-Export のソースコードがローカル環境にチェックアウトされており、依存ライブラリがインストールされていること。
  ```bash
  pip install -r requirements.txt
  ```
- **認証情報**: Confluence 個人用アクセストークン（PAT）を環境変数 `C2M_CONFLUENCE_TOKEN`（推奨）または `CONFLUENCE_TOKEN` に設定していること。
  ```bash
  export C2M_CONFLUENCE_TOKEN="your-confluence-pat"
  ```
  ※ トークンをコマンドライン引数（`--token`）で直接渡すと、プロセス一覧やシェル履歴に記載が残るため推奨されません。

## Windows (PowerShell / cmd.exe) 実行時の要点

- **bash 構文を使わない**: `/dev/null` や bash のパイプ・`export` は使えません。環境変数は PowerShell では `$env:VAR="..."`、cmd.exe では `set VAR=...` の形式で指定してください。
- **出力は捨てない**: CLI の標準出力は純粋な JSON のみ、進捗・警告は stderr に分離されています。リダイレクトで破棄せず、そのまま実行して終了コードと stdout の JSON を取得してください。
- **実行時間の上限を必ず意識する**: 補助スクリプト経由では、どこからも指定がなければ既定の上限 **300秒** が自動で補われます。直接コマンド（`python -m c2m_export.analyze`）で長時間実行する場合は、利用者への確認なしに無制限で実行せず、`--timeout-seconds` を明示してください。上限到達時は部分結果（`partial`）が返ります。
- **ハートビートは継続の合図**: 実行中は 5 秒間隔で進捗（現在のフェーズ・経過秒数・収集済み件数）が stderr に出力されます。出続けている間はハングではなく処理継続中です。

詳細（出力の捨て方、上限の適用範囲と再開時の扱い、環境変数の形式）は [references/windows_notes.md](references/windows_notes.md) を参照してください。

## 実行方法

本 Skill は、サブプロセスとして CLI エントリーポイント `python -m c2m_export.analyze` または補助スクリプト `python skills/confluence-analysis/scripts/run_analysis.py` を呼び出して動作します。

### 基本的なコマンド

**まず事前見積もりを実行してください**（本実行の前に、対象の規模と見込み時間を確認します）:

```bash
python skills/confluence-analysis/scripts/run_analysis.py \
  --base-url "https://confluence.example.com" \
  --space-key "DEV" \
  --estimate
```

見積もり結果（`estimate` フィールド）の読み方:

- `target_pages`: 対象ページ総数。`estimated_seconds`: 推定所要秒数（実測レイテンシに基づく下限寄りの目安）。
- `is_large` が `true`（推定 120 秒超または 500 ページ超）の場合は、そのまま本実行せず、対象分割 / usecase の絞り込み / `--no-restrictions` / `--mode summary` のいずれか（または併用）を利用者に提示し、判断を仰いでください。**自動で対象を絞らないでください。**
- `exceeds_skill_default_timeout` が `true` の場合は、既定上限 300 秒では partial になる見込みです。本実行時に `--timeout-seconds` の明示指定（延長）を提案してください。

### 大きな対象では非同期実行を使う

見積もりで `is_large` が `true` の場合、本実行は同期ではなく **非同期ジョブ** で開始してください（開始コマンドは即座に返るため、エージェント側のターミナルを長時間占有しません）:

```bash
# 開始（job_id が即座に返ります。--timeout-seconds はワーカー側の上限として効きます）
python skills/confluence-analysis/scripts/run_analysis.py \
  --base-url "https://confluence.example.com" \
  --space-key "DEV" \
  --detach

# 進捗確認（30〜60 秒間隔で確認し、phase / processed / estimated_total を利用者へ伝えてください）
python skills/confluence-analysis/scripts/run_analysis.py --job-status <job_id>

# 完了したら結果の要約だけを取得（全量は result_file にあります。必要な場合のみファイルを読んでください）
python skills/confluence-analysis/scripts/run_analysis.py --job-result <job_id>

# 中断したい場合（収集済み分は partial として残り、--resume で再開できます）
python skills/confluence-analysis/scripts/run_analysis.py --job-cancel <job_id>
```

`--job-status` の `state` が `done` / `partial` / `error` になったら完了です。`stale` が `true` の場合はワーカーが異常終了した可能性があるため、`log_file`（worker.log）を確認してください。

見積もり後に本実行します（同期実行の場合）:

```bash
python -m c2m_export.analyze \
  --base-url "https://confluence.example.com" \
  --space-key "DEV" \
  --usecase "risk" "stale" "restricted" \
  --mode "summary"
```

または補助スクリプトを使用:

```bash
python skills/confluence-analysis/scripts/run_analysis.py \
  --base-url "https://confluence.example.com" \
  --space-key "DEV" \
  --usecase "stale" \
  --mode "detail" \
  --limit 50
```

## 主要オプション（抜粋）

通常の調査分析で使うオプションの抜粋です。**全オプションと既定値の確認は [references/options.md](references/options.md)** を参照してください。

| オプション | 型 | 説明 | 既定値 |
|---|---|---|---|
| `--base-url` | 文字列 (必須) | Confluence のベース URL (例: `https://confluence.example.com`) | なし |
| `--space-key` | 文字列リスト | 対象の Confluence Space キー (複数指定可) | なし |
| `--root-page-id` | 文字列リスト | 対象のルートページ ID (複数指定可) | なし |
| `--all-spaces` | フラグ | 参照可能な全 Space を起点として分析 | `False` |
| `--cql` | 文字列 | 起点検索用または課題抽出用の CQL 文字列 | なし |
| `--usecase` | 文字列リスト | 分析ユースケース (`risk`, `stale`, `restricted`, `archives`, `empty_with_attachments`, `macros`) | 全 6 種 |
| `--mode` | 文字列 | 出力モード (`summary`: 集計サマリのみ, `detail`: 個別一覧含む) | `summary` |
| `--stale-days` | 整数 | 古いページの判定基準日数 | `365` |
| `--restrictions` / `--no-restrictions` | フラグ | アクセス制限（権限）情報の収集可否 | 自動収集 (有効) |
| `--deep` | フラグ | 詳細調査フェーズの情報を一括で有効化 | `False` |
| `--resume` | フラグ | 既存のチェックポイントから未収集分を再開 | `False` |
| `--timeout-seconds` | 整数 | 走査・分析処理の最大実行時間（秒） | なし (無制限) |
| `--max-pages` | 整数 | 走査する最大ページ数上限 | なし (無制限) |
| `--estimate` | フラグ | 本実行を行わず、対象ページ数と推定所要のみを見積もって返す | オフ |
| `--detach` | フラグ | 分析を別プロセスで開始し、job_id を即座に返す | オフ |
| `--concurrency` | 整数 | 全体把握フェーズの並列度（負荷を抑えたい場合は 1〜2） | `4` |

※ `--space-key`、`--root-page-id`、`--all-spaces`、`--cql` の少なくとも 1 つが必須です。

## 分析ユースケース一覧

1. `risk`: 移設リスクが高いページ（パス長超過、不正文字、ブロック拡張子、大容量ファイル等）
2. `stale`: 一定期間（既定 1 年）以上更新されていない古いページ
3. `restricted`: 親からの継承ではなく、個別のアクセス制限が設定されているページ
4. `archives`: zip / 7z / tar などの圧縮形式ファイルの個数と概算合計サイズ
5. `empty_with_attachments`: 添付ファイルは存在するが、本文がほとんど空（既定 200 バイト未満）のページ
6. `macros`: 使用されている Confluence マクロの統計と手作業修復候補カテゴリ（Markdown 変換時影響）

## 結果の読み方（要点）

- 標準出力は純粋な JSON です。まず `status`（`ok` / `partial` / `error`）と `uncertainties` を確認してください。
- `status` が `partial` の場合は、`uncertainties.interrupted_reason` と `collected_page_count` を見て、利用者へ「どこまで終わったか」を伝えたうえで `--resume` での再開を提案してください。
- 取得できなかった情報は `uncertainties` の各失敗フィールドと `unavailable_apis` に集約されています。「データが無い」ことと「取得に失敗した」ことを混同しないでください。
- 全フィールドの仕様は [references/output_schema.md](references/output_schema.md) を参照してください。

## 終了コード規約

- `0`: 成功 (`ok`)
- `2`: パラメータ不正 (`INVALID_PARAM`)
- `3`: 認証失敗 (`AUTH_FAILED`)
- `4`: 対象未存在 (`TARGET_NOT_FOUND`)
- `5`: Confluence API / ネットワークエラー (`API_ERROR`)
- `6`: 部分成功 (`partial`)
- `10`: 内部エラー (`INTERNAL_ERROR`)

エラー発生時も、標準出力に `status: "error"` の構造化 JSON (ErrorObject) が出力されます（標準エラー出力には日本語詳細メッセージが出力されます）。
