# Confluence to Markdown Exporter (C2M-Export)

Confluence Data Center 9.2 のページツリーを REST API で取得し、AIナレッジ向けに Markdown へ統合エクスポートするローカルCLIツールです。

特定ページ配下のドキュメント群を 1 つの Markdown ファイルにまとめる基本機能（結合モード）のほか、大規模移行向けの分析・ファイルシステム出力・権限出力・差分同期機能を提供しています。

---

## クイックスタート（最短手順）

設定ファイル（`c2m_config.yaml`）を作成せずに、特定ページ配下をまとめて 1 つの Markdown ファイルに統合出力する最短手順です。

1. **依存関係のインストール**
   ```cmd
   pip install -r requirements.txt
   ```

2. **コマンドの実行**
   `--base-url`、`--token`、`--root-page-id` を指定して実行します（アクセストークンは環境変数 `C2M_CONFLUENCE_TOKEN` または `CONFLUENCE_TOKEN` での指定も可能です）。
   ```cmd
   python -m c2m_export.cli --base-url https://your-confluence/wiki --token <TOKEN> --root-page-id 12345678
   ```

3. **出力の確認**
   実行完了後、カレントディレクトリに `【<spaceKey>】 <タイトル>.md` の形式で 1 つの Markdown ファイルが出力されます。

---

## ユースケース別ガイド

目的に応じて以下の詳細ドキュメントを参照してください。

- **1 ページ配下を 1 ファイルで取得したい（基本）**
  - 上記の [クイックスタート（最短手順）](#クイックスタート最短手順) を参照するか、詳細な手順は [結合モード詳細](docs/export_combined.md) を参照してください。
  - ブラウザから GUI で操作したい場合は [結合モード詳細: Web UI での実行](docs/export_combined.md#2-web-ui-での実行) を参照してください。
- **大規模移行・構造分析・アクセス権限・フォルダ階層出力を行いたい（応用）**
  - [アセスメント詳細](docs/assessment.md)、[ファイルシステムエクスポート詳細](docs/filesystem_export.md)、[権限エクスポート詳細](docs/permission_export.md) を参照してください。推奨する作業手順は [アセスメント詳細: 推奨ワークフロー](docs/assessment.md#1-推奨ワークフロー) を確認できます。
- **AI エージェント（Copilot / Kiro / Agent Skills / MCP）から分析を行いたい**
  - [AI 連携詳細](docs/ai_integration.md) を参照してください。

---

## 主な機能（モード）

1. **統合エクスポート（結合モード / `cli`）**:
   - ページツリーを再帰的に取得し、全ページを 1 つの Markdown ファイルに結合して出力します（サイズ制限・Zip 圧縮・Web UI 対応）。 [詳細ガイド](docs/export_combined.md)
2. **分析 CLI（`analyze`）および Agent Skill / MCP サーバ**:
   - ワークスペースの状況分析結果（移設リスク、古いページ、個別アクセス制限、マクロ利用等）を構造化 JSON として出力します。Agent Skills や MCP サーバとしても機能します。 [詳細ガイド](docs/ai_integration.md)
3. **コンテンツ分析（アセスメントモード / `assess`）**:
   - 添付バイナリをダウンロードせずに高速にメタデータを収集し、規模・構造・移設リスク・権限・鮮度のレポート（Markdown & JSON）を出力します。 [詳細ガイド](docs/assessment.md)
4. **ファイルシステムエクスポート（ファイルシステムモード / `fsexport`）**:
   - Confluence のページツリーを OS のディレクトリ/ファイル構造に再現し、ページ本文（YAML Frontmatter 付き Markdown）と添付バイナリを保存します。差分同期・レジュームに対応します。 [詳細ガイド](docs/filesystem_export.md)
5. **権限エクスポート（権限モード / `permexport`）**:
   - Confluence のページに設定されたコンテンツ制限 (Read / Read+Write) を収集し、管理者向けの参照用権限レポート（Markdown & JSON）を出力します。 [詳細ガイド](docs/permission_export.md)
6. **ページツリー表示（ツリーモード / `tree`）**:
   - ページ階層を樹形図（テキスト / Markdown / JSON）として可視化出力します。オプトインで個別アクセス制限・マクロ種別数・添付数・最終更新日を併記できます。 [詳細ガイド](docs/tree_visualization.md)

---

## ドキュメント案内（詳細目次）

各機能の仕様やパラメータ等の詳細は、`docs/` 配下の各ドキュメントを参照してください。

| ドキュメント | 主な内容 |
|---|---|
| [結合モード詳細](docs/export_combined.md) | 設定ファイル (`c2m_config.yaml`)、CLI パラメータ、Web UI、ファイル名規則 |
| [アセスメントモード詳細](docs/assessment.md) | 規模・構造・移設リスク分析、推奨ワークフロー |
| [ファイルシステムエクスポート詳細](docs/filesystem_export.md) | OS ディレクトリ構造出力、差分同期 (`--sync`)・レジューム (`--resume`)・削除ポリシー |
| [権限エクスポート詳細](docs/permission_export.md) | コンテンツ制限収集、集約/分散レポート形式 |
| [ツリー可視化モード詳細](docs/tree_visualization.md) | 樹形図出力 (text/markdown/json)、付帯情報マーク (🔒/📎N/⚙N)・別表、探索制御 |
| [AI 連携機能詳細](docs/ai_integration.md) | 分析 CLI (`analyze`)、Agent Skill (`SKILL.md`)、MCP サーバ (`mcp_server.py`) |
| [変換方針・サポート表現](docs/conversion.md) | AI ナレッジ利用最優先方針、Markdown 変換対応表、部分成功・エラー挙動 |

---

## 共通仕様・特徴

- Confluence Data Center 9.2 対応 (REST API)
- HTTP/HTTPS Proxy (CONNECT トンネル) 対応
- Windows ファイル名制約に基づいたサニタイズ・衝突回避採番
- 表・リスト・引用・コードブロック・各種マクロなど幅広い Confluence 表現の Markdown 変換対応（[変換方針詳細](docs/conversion.md)）
- 一部ページの取得・変換に失敗しても処理を止めず、取得できた分を出力する「部分成功」設計
- 認証トークン実値・`Authorization`/`Bearer` ヘッダー・URL クエリパラメータ (`token`, `access_token`, `api_key`, `secret`, `password` 等) の自動マスク (`***REDACTED***`) による多層防御 (分析 CLI および MCP 応答の返却経路全体に適用)

---

## セットアップ

Python 3.8 以上が必要です。

```cmd
# 依存関係のインストール
pip install -r requirements.txt
```

※ MCP サーバを利用する場合は `pip install -r requirements-mcp.txt` も実行してください（[AI 連携詳細](docs/ai_integration.md) 参照）。

---

## よくあるエラーと終了コード

### HTTP ステータスと共通エラー

API 通信・添付ダウンロードの最終失敗時は、URL や元の例外メッセージを含まないエラーを返します。HTTP エラーではステータスコードを確認できます。5xx も最終試行では再試行の待機を行わず、ステータスコードを保持した HTTP エラーを返します。
401・403・404 は再試行や待機をせず、直ちに失敗します。429・5xx・通信エラーは指数バックオフで再試行します。

- **401/403**: トークンが無効か権限がありません（現象）。詳細: 認証エラー（原因）。正しいトークンが設定されているか確認してください（対処方法）。
- **404**: ページIDまたはURLが間違っています（現象）。詳細: リソース未発見（原因）。ベースURLに `/wiki` などのコンテキストパスが含まれているか確認してください（対処方法）。
- **Proxy Error**: プロキシ設定が正しくないか、ネットワークが遮断されています（現象）。詳細: 接続失敗（原因）。プロキシURLの設定やネットワーク接続を確認してください（対処方法）。

### モード別終了コード (Exit Codes)

各コマンド実行時のプロセスの終了コード（Exit Code）は以下の通りです。

| 実行モード | コマンド / エントリーポイント | 正常終了 | エラー時終了コードと意味 |
|---|---|---|---|
| **結合モード** | `python -m c2m_export.cli` | `0` | **`1`**: 設定・取得・出力などの全般エラー |
| **ファイルシステムモード** | `python -m c2m_export.fsexport` | `0` | **`1`**: 設定・起点未発見・出力権限等のエラー |
| **アセスメントモード** | `python -m c2m_export.assess` | `0` | **`1`**: 設定・起点未発見・レポート出力等のエラー |
| **権限モード** | `python -m c2m_export.permexport` | `0` | **`1`**: 設定・取得・レポート出力等の致命的エラー |
| **分析モード** | `python -m c2m_export.analyze` | `0` | **`2`**: `INVALID_PARAM` (設定・引数エラー)<br>**`3`**: `AUTH_FAILED` (401/403 認証失敗)<br>**`4`**: `TARGET_NOT_FOUND` (404 対象未発見)<br>**`5`**: `API_ERROR` (API通信エラー)<br>**`6`**: `PARTIAL` (シグナル中断・途中エラーによる部分成功)<br>**`10`**: `INTERNAL_ERROR` (内部例外エラー) |
| **ツリーモード** | `python -m c2m_export.tree` | `0` | **`2`**: `INVALID_PARAM` (設定・引数エラー)<br>**`3`**: `AUTH_FAILED` (401/403 認証失敗)<br>**`4`**: `TARGET_NOT_FOUND` (404 対象未発見)<br>**`5`**: `API_ERROR` (API通信エラー)<br>**`10`**: `INTERNAL_ERROR` (内部例外エラー) |
