# AI 連携機能（分析 CLI / Agent Skill / MCP サーバ）詳細

AI エージェント（GitHub Copilot, Kiro, 汎用 Agent Skills, MCP クライアント）から Confluence ワークスペースの分析結果を機械可読 JSON としてパース・利用するための機能群の詳細ガイドです。

---

## 1. 分析 CLI (`python -m c2m_export.analyze`)

標準出力 (stdout) に純粋な JSON のみを出力し、人間向けの進捗ログ・エラーメッセージは標準エラー出力 (stderr) に分離されます。

```bash
# 環境変数でトークンを設定（推奨）
export C2M_CONFLUENCE_TOKEN="your-confluence-pat"

# 分析 CLI の実行
python -m c2m_export.analyze \
  --base-url "https://confluence.example.com" \
  --space-key "DEV" \
  --usecase "stale" "restricted" "macros" \
  --mode "detail" \
  --limit 50
```

### 主要なオプション
- `--base-url`: Confluence ベース URL (必須)
- `--space-key` / `--root-page-id`: 分析対象の Space キーまたはルートページ ID (複数指定可)
- `--all-spaces`: 参照可能な全 Space を起点として分析
- `--cql`: 起点検索用または課題抽出用の CQL 文字列
- `--usecase`: 実行する分析ユースケース (`risk`, `stale`, `restricted`, `archives`, `empty_with_attachments`, `macros` / 既定: 全 6 種)
- `--mode`: 出力モード (`summary`: 集計値のみ, `detail`: 条件合致ページ/添付の個別一覧含む)
- `--limit`: `detail` モード時の項目抽出上限件数 (既定: 1000)
- `--stale-days` / `--stale-years`: 長期未更新ページの判定基準（日数または年数）
- `--min-body-bytes`: 添付あり空ページの判定基準バイト数 (既定: 200)
- `--archive-ext`: 圧縮形式とみなす拡張子リスト
- `--restrictions` / `--no-restrictions`: 個別制限権限分析の有効/無効化
- `--deep`: 詳細調査フェーズ（更新履歴・ラベル・コメント・ウォッチャー・実効制限・抽出テキスト・Space 権限）を一括有効化
- `--collect-history` / `--no-collect-history`: 更新履歴の個別収集制御
- `--collect-labels` / `--no-collect-labels`: ラベルの個別収集制御
- `--collect-comments` / `--no-collect-comments`: コメントの個別収集制御
- `--collect-watchers` / `--no-collect-watchers`: ウォッチャーの個別収集制御
- `--collect-effective-restrictions` / `--no-collect-effective-restrictions`: 実効アクセスの個別収集制御
- `--collect-extracted-text` / `--no-collect-extracted-text`: 抽出テキストの個別収集制御
- `--collect-space-permissions` / `--no-collect-space-permissions`: Space 権限の個別収集制御
- `--no-checkpoint`: チェックポイント永続化を無効化 (既定: 有効)
- `--resume`: 既存のチェックポイントから未収集分を再開
- `--checkpoint-interval`: チェックポイント flush 粒度 (件数, 既定: 1)
- `--checkpoint-dir`: チェックポイント保存先ディレクトリ (既定: `.c2m_analyze_checkpoint`)

### 中断耐性とレジューム機能
大規模ワークスペース分析時、1ページ収集ごとに JSONL 形式のチェックポイント（既定: `.c2m_analyze_checkpoint/<scope_hash>.jsonl`）へ自動保存されます。`SIGINT` (Ctrl+C) や通信エラーで中断した場合でも、収集済みデータで部分集計され `status: "partial"`（終了コード 6）が出力されます。次回実行時に `--resume` オプションを指定することで、同一スコープの未収集ページのみから処理を再開できます。正常完了時はチェックポイントファイルは自動削除されます。

### 終了コード規約
`0` (成功), `2` (パラメータ不正), `3` (認証失敗), `4` (対象未存在), `5` (APIエラー), `6` (部分成功 partial), `10` (内部エラー)。

---

## 2. Agent Skill (`SKILL.md`)

GitHub Copilot、Kiro、および汎用 Agent Skills で共通して利用可能な `SKILL.md` が提供されています。各ツールの自動検出・発火条件（`.kiro/skills/`: Kiro、`.github/skills/`: GitHub Copilot、`skills/`: 汎用 Agent Skills）に合わせて 3 箇所に配置しています。

- **正本ファイル**: `skills/confluence-analysis/SKILL.md`（および補助スクリプト `skills/confluence-analysis/scripts/run_analysis.py`）
- **複製配置先**:
  - GitHub Copilot 用: `.github/skills/confluence-analysis/SKILL.md`
  - Kiro 用: `.kiro/skills/confluence-analysis/SKILL.md`

※ SKILL.md を編集・更新する場合は、必ず正本 `skills/confluence-analysis/SKILL.md` を変更した上で他配置先へ同期（上書きコピー）を行ってください。

---

## 3. MCP サーバ (`c2m_export/mcp_server.py`)

Model Context Protocol (MCP) を経由して分析機能を FastMCP ツール `analyze_confluence` として公開できます。

### セットアップ・依存関係のインストール

```bash
pip install -r requirements-mcp.txt
```

### クライアント設定例 (stdio トランスポート)

MCP クライアント (Kiro、Claude Desktop 等) に本 MCP サーバを登録するための設定例です。

> **認証トークンに関する注意点**:
> トークンは MCP サーバプロセスの環境変数 (`C2M_CONFLUENCE_TOKEN` または `CONFLUENCE_TOKEN`) 経由で取得します。ツールの引数として渡すことはできません。

#### Kiro / MCP クライアントの設定例 (`mcp.json` / `mcpServers` 設定)

```json
{
  "mcpServers": {
    "c2m-export-analysis": {
      "command": "python",
      "args": ["-m", "c2m_export.mcp_server"],
      "env": {
        "C2M_CONFLUENCE_TOKEN": "your-confluence-pat-here"
      },
      "disabled": false
    }
  }
}
```
※ 汎用的な stdio MCP 設定形式を使用しています。ご利用の MCP クライアントの設定形式（`mcpServers` または `mcp` 等）に合わせてご記述ください。

### 公開ツールと引数仕様 (`analyze_confluence`)

| 引数名 | 型 | 必須/任意 | 説明 | 既定値 |
|---|---|---|---|---|
| `base_url` | 文字列 | **必須** | Confluence のベース URL (例: `https://confluence.example.com`) | なし |
| `space_keys` | 文字列リスト | 任意 | 対象 Space キー一覧 | `None` |
| `root_page_ids` | 文字列リスト | 任意 | 対象 ルートページ ID 一覧 | `None` |
| `all_spaces` | ブール値 | 任意 | 参照可能な全 Space を起点として分析するか | `False` |
| `cql` | 文字列 | 任意 | 起点検索用または課題抽出用の CQL 文字列 | `None` |
| `usecases` | 文字列リスト | 任意 | 実行する分析ユースケース (`risk`, `stale`, `restricted`, `archives`, `empty_with_attachments`, `macros`) | 全 6 種 |
| `mode` | 文字列 | 任意 | 出力モード (`summary` または `detail`) | `"summary"` |
| `limit` | 整数 | 任意 | `detail` モード時の上限取得件数 | `1000` |
| `stale_days` | 整数 | 任意 | 古いページの判定基準日数 | `365` |
| `stale_years` | 浮動小数点 | 任意 | 古いページの判定基準年数 (`stale_days` 優先) | `None` |
| `min_body_bytes` | 整数 | 任意 | 添付あり空ページの判定基準バイト数 | `200` |
| `archive_extensions` | 文字列リスト | 任意 | 圧縮ファイル拡張子一覧 | `None` |
| `analyze_restrictions` | ブール値 | 任意 | アクセス制限情報の収集可否 (3値: True/False/None) | `None` |
| `sort` | 文字列 | 任意 | `detail` モード時のソート順 | `None` |
| `deep` | ブール値 | 任意 | 詳細調査フェーズの情報を一括で有効化 | `False` |
| `collect_history` | ブール値 | 任意 | ページ更新履歴の個別収集 | `None` |
| `collect_labels` | ブール値 | 任意 | ラベル情報の個別収集 | `None` |
| `collect_comments` | ブール値 | 任意 | コメント情報の個別収集 | `None` |
| `collect_watchers` | ブール値 | 任意 | ウォッチャー情報の個別収集 | `None` |
| `collect_effective_restrictions` | ブール値 | 任意 | 実効アクセス制限の個別収集 | `None` |
| `collect_extracted_text` | ブール値 | 任意 | 抽出テキストの個別収集 | `None` |
| `collect_space_permissions` | ブール値 | 任意 | Space 権限情報の個別収集 | `None` |

### 動作確認手順

1. **ツール一覧の確認**:
   MCP クライアントから利用可能なツール一覧を表示し、`analyze_confluence` が認識されていることを確認します。
2. **ツールの実行試行**:
   テスト用の小規模な Space キーを指定し、`mode="summary"` で `analyze_confluence` を呼び出します。
   ```json
   {
     "base_url": "https://confluence.example.com",
     "space_keys": ["TEST"],
     "mode": "summary"
   }
   ```
3. **JSON 応答の確認**:
   応答 JSON の最上位に `"status": "ok"` (または `"partial"`) および `"schema_version": "1.2"`、`"summary"` などのブロックが含まれていることを確認します。

---

[READMEへ戻る](../README.md)
