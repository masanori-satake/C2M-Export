# Project Structure

```
C2M-Export/
├── c2m_export/            # メインパッケージ
│   ├── analysis/          # 分析純粋ロジック・共通 API 層パッケージ
│   │   ├── __init__.py
│   │   ├── api.py         # 共通 1 層 (run_analysis) と例外・エラーコード分類
│   │   ├── categories.py # 圧縮形式カテゴリ集約純粋ロジック
│   │   ├── extractors.py  # ユースケース別個別一覧抽出 (API 非依存)
│   │   ├── macros.py      # マクロ解析・集計・修復区分判定
│   │   ├── params.py      # 分析パラメータモデル・境界検証
│   │   ├── provenance.py  # provenance 付与（enrich_stale / enrich_restricted / enrich_empty_with_attachments など）
│   │   ├── response.py    # レスポンス・ErrorObject スキーマモデル
│   │   ├── checkpoint.py  # チェックポイント永続化・復元・スコープハッシュ (純粋関数 + CheckpointStore)
│   │   ├── sanitize.py    # 秘匿情報サニタイズ（多層防御マスク）
│   │   └── workspace.py   # workspace / visibility / environment 集計
│   ├── assessment/        # アセスメント（分析）パッケージ
│   │   ├── __init__.py
│   │   ├── analyzers.py   # 分析純粋ロジック (規模・構造・リスク等)
│   │   ├── collector.py   # メタデータ収集 (I/O層)
│   │   ├── models.py      # データモデル定義
│   │   ├── report.py      # レポート生成 (Markdown/JSON)
│   │   └── rules.py       # 移設リスク判定ルール
│   ├── fs_export/         # ファイルシステムエクスポートパッケージ
│   │   ├── __init__.py
│   │   ├── diff.py        # 差分判定ロジック
│   │   ├── frontmatter.py # YAMLフロントマター生成
│   │   ├── links.py       # 添付リンク書き換え
│   │   ├── manifest.py    # マニフェスト管理 (保存・読み込み・検証)
│   │   ├── models.py      # データモデル定義
│   │   ├── quarantine.py  # 退避ディレクトリ操作
│   │   ├── summary.py     # 実行結果サマリ生成
│   │   ├── sync.py        # 差分同期・レジューム処理
│   │   ├── tree.py        # 階層ツリー構築・ローカルパス割り当て
│   │   └── writer.py      # 本文・添付ファイル出力
│   ├── page_tree/         # ページツリー表示パッケージ
│   │   ├── __init__.py
│   │   ├── annotations.py # 付帯情報集約・マーク生成（純粋ロジック）
│   │   ├── builder.py     # ツリー構造構築（純粋ロジック）
│   │   ├── collector.py   # メタデータ・付帯情報収集 (I/O層)
│   │   ├── models.py      # データモデル定義
│   │   └── renderers.py   # text / markdown / json 描画（純粋ロジック）
│   ├── permission/        # 権限エクスポートパッケージ
│   │   ├── __init__.py
│   │   ├── collector.py   # コンテンツ制限情報収集 (I/O層)
│   │   ├── models.py      # データモデル定義
│   │   ├── report.py      # 権限レポート生成
│   │   └── summary.py     # 実行結果サマリ生成
│   ├── __init__.py        # パッケージ初期化
│   ├── analyze.py         # 分析 CLI エントリーポイント (python -m c2m_export.analyze)
│   ├── assess.py          # アセスメント CLI エントリーポイント (python -m c2m_export.assess)
│   ├── cli.py             # 結合エクスポート CLI エントリーポイント (python -m c2m_export.cli)
│   ├── config.py          # 設定管理 (CLI引数 / YAML / 環境変数)
│   ├── confluence.py      # Confluence REST API クライアント (リトライ・Proxy対応)
│   ├── converter.py       # Storage Format → Markdown 変換 (マクロ処理含む)
│   ├── fsexport.py        # ファイルシステムエクスポート CLI エントリーポイント (python -m c2m_export.fsexport)
│   ├── mcp_server.py      # MCP サーバエントリーポイント (python -m c2m_export.mcp_server)
│   ├── permexport.py      # 権限エクスポート CLI エントリーポイント (python -m c2m_export.permexport)
│   ├── tree.py            # ページツリー表示 CLI エントリーポイント (python -m c2m_export.tree)
│   ├── utils.py           # ユーティリティ (ファイル名サニタイズ, サイズ計算, Zip生成)
│   └── web.py             # Streamlit Web UI (python -m c2m_export.web)
├── skills/                # Agent Skill 正本ディレクトリ
│   ├── confluence-analysis/ # 分析 Skill 正本 (SKILL.md + scripts/)
│   ├── confluence-setup/    # セットアップ支援 Skill 正本 (SKILL.md + scripts/)
│   └── confluence-tree/     # ページツリー Skill 正本 (SKILL.md + scripts/)
├── .github/skills/        # GitHub Copilot 用 Agent Skill 複製ディレクトリ
│   ├── confluence-analysis/ # SKILL.md 複製
│   └── confluence-setup/    # SKILL.md + scripts/ 複製
├── .kiro/skills/          # Kiro 用 Agent Skill 複製ディレクトリ
│   ├── confluence-analysis/ # SKILL.md 複製
│   └── confluence-setup/    # SKILL.md + scripts/ 複製
├── tests/                 # テストディレクトリ
│   ├── conftest.py                   # Pytest 共通フィクスチャ
│   ├── test_assess_config.py         # アセスメント設定テスト
│   ├── test_assess_main.py           # アセスメントメインフローテスト
│   ├── test_assessment_analyzers.py  # 分析ロジックテスト
│   ├── test_assessment_collector.py  # アセスメント収集テスト
│   ├── test_assessment_report.py     # アセスメントレポート出力テスト
│   ├── test_assessment_rules.py      # 移設リスク判定ルールテスト
│   ├── test_cli_overwrite.py         # CLI 上書き動作テスト
│   ├── test_confluence_assess_client.py # Confluence API クライアント拡張テスト
│   ├── test_converter.py             # HTML→Markdown 変換テスト
│   ├── test_converter_extended.py    # 拡張 HTML→Markdown 変換テスト
│   ├── test_fs_client.py             # FS API クライアント拡張テスト
│   ├── test_fs_frontmatter.py        # フロントマター生成テスト
│   ├── test_fs_links.py              # 添付リンク書き換えテスト
│   ├── test_fs_summary.py            # FS サマリ出力テスト
│   ├── test_fs_tree.py               # FS ツリー構築テスト
│   ├── test_fs_writer.py             # FS ファイル出力テスト
│   ├── test_fsexport_config.py       # FS 設定解決テスト
│   ├── test_fsexport_main.py         # FS メインフローテスト
│   ├── test_fsexport_sync_config.py  # FS 同期設定テスト
│   ├── test_fsexport_sync_main.py    # FS 同期メインフローテスト
│   ├── test_macros_extended.py       # マクロ変換テスト
│   ├── test_perm_collector.py        # 権限収集テスト
│   ├── test_perm_report.py           # 権限レポート生成テスト
│   ├── test_perm_summary.py          # 権限サマリ出力テスト
│   ├── test_permexport_config.py     # 権限エクスポート設定テスト
│   ├── test_permexport_main.py       # 権限エクスポートメインフローテスト
│   ├── test_robustness.py            # 堅牢性・例外伝播防止テスト
│   ├── test_sync_apply.py            # 差分適用テスト
│   ├── test_sync_diff.py             # 差分計算テスト
│   ├── test_sync_inventory.py        # インベントリ収集テスト
│   ├── test_sync_manifest.py         # マニフェスト管理テスト
│   ├── test_sync_paths.py            # 同期パス計算テスト
│   ├── test_sync_quarantine.py       # 退避処理テスト
│   ├── test_utils.py                 # ユーティリティ関数テスト
│   ├── test_utils_fsexport.py        # FS ユーティリティテスト
│   └── test_web.py                   # Web UI テスト
├── output/                # エクスポート出力先（gitignore対象）
├── c2m_config.yaml        # 実行用設定ファイル（gitignore対象）
├── c2m_config_sample.yaml # 設定ファイルのサンプル
├── requirements.txt       # 実行時依存
├── requirements-mcp.txt   # MCP 追加依存 (mcp)
├── .pre-commit-config.yaml # pre-commit フック設定
├── AGENTS.md              # AI エージェント向け指示書
├── README.md              # ユーザー向けドキュメント
└── README_DEV.md          # 開発者向けドキュメント（設計・拡張ガイド）
```

## モジュールの責務

| モジュール / パッケージ | 責務 |
|---|---|
| `config.py` | 設定の読み込み・検証・正規化（結合・アセスメント・FS・権限の各設定クラス含む） |
| `confluence.py` | API通信、ページネーション、指数バックオフリトライ、メタデータ/制限取得 |
| `converter.py` | XHTML→Markdown変換、マクロハンドリング、テーブル処理 |
| `cli.py` | 結合モードエントリーポイント、DFS探索、サイズ制限制御、単一 Markdown ファイル出力 |
| `assess.py` / `assessment/` | アセスメントエントリーポイント、メタデータ収集、規模/リスク/権限/鮮度分析、レポート出力 |
| `fsexport.py` / `fs_export/` | FS エクスポートエントリーポイント、ディレクトリ/ファイル構造化、Frontmatter、添付保存、差分同期・レジューム処理 |
| `permexport.py` / `permission/` | 権限エクスポートエントリーポイント、アクセス制限（Read/Read+Write）収集、レポート出力 |
| `analyze.py` / `analysis/` | 分析 CLI エントリーポイント、抽出・集約・マクロ統計純粋ロジック、共通 1 層 `run_analysis`、JSONL チェックポイント永続化/レジューム (`checkpoint.py`) |
| `tree.py` / `page_tree/` | ページツリー表示 CLI エントリーポイント、付帯情報選択収集、3フォーマット描画 |
| `mcp_server.py` | MCP サーバエントリーポイント (FastMCP) |
| `skills/confluence-analysis/` | Agent Skill 定義の正本 (`SKILL.md` + `scripts/run_analysis.py`) |
| `skills/confluence-tree/` | Agent Skill 定義の正本 (`SKILL.md` + `scripts/run_tree.py`) |
| `skills/confluence-setup/` | Agent Skill 定義の正本 (`SKILL.md` + `scripts/diagnose.py`) |
| `.github/skills/` / `.kiro/skills/` | Agent Skill 定義の Copilot / Kiro 用複製先 (正本 `skills/` からのコピーを厳守) |
| `utils.py` | ファイル名生成・サニタイズ、サイズユーティリティ、Zip圧縮 |
| `web.py` | Streamlit UI、排他制御、進捗表示 |

## 実行フロー

### 結合エクスポートモード (`cli.py`)
1. `Config.load()` → 設定を優先順位に従い統合
2. `Config.validate()` → 必須項目チェック・URL正規化
3. `ConfluenceClient` / `MarkdownConverter` 初期化
4. ルートページごとにフェイルファスト（存在確認・ファイル競合チェック）
5. `export_tree()` で DFS 巡回 → Markdown 統合
6. ファイル書き出し or Zip 圧縮

### アセスメントモード (`assess.py`)
1. `AssessConfig.load()` → 設定読み込み・検証
2. `ConfluenceClient` / `Collector` 初期化
3. 起点（`root_page_ids` / `space_keys`）解決
4. `Collector.collect()` で DFS メタデータ（ページ/添付/権限/更新情報）収集
5. `analyzers.analyze_inventory()` で規模・構造・リスク・鮮度を分析
6. Markdown / JSON レポート出力

### ファイルシステムエクスポートモード (`fsexport.py`)
- **通常（フル）出力**:
  1. `FsExportConfig.load()` → 設定読み込み・検証
  2. `build_page_tree()` で DFS 巡回・ローカルパス割り当て・重複回避
  3. 各ページの Markdown 本文変換・Frontmatter 付与・添付リンク書き換え
  4. ファイル/ディレクトリ書き出しおよび添付バイナリのダウンロード
  5. マニフェスト（`.c2m_manifest.json`）の書き出しとサマリ出力
- **差分同期 (`--sync`) / レジューム (`--resume`)**:
  1. 既存マニフェストの読み込み・スコープ検証
  2. 軽量インベントリ収集
  3. `compute_diff()` で差分判定（追加・変更・移動/改名・削除・未変更）
  4. 差分適用（移動・改名追従、削除/退避、変更・追加ページの再取得）
  5. マニフェスト更新とサマリ出力

### 権限エクスポートモード (`permexport.py`)
1. `PermissionExportConfig.load()` → 設定読み込み・検証
2. `ConfluenceClient` / `PermissionCollector` 初期化
3. DFS 巡回で各ページの閲覧・編集制限（Read / Read+Write）収集
4. レポートレイアウト（集約 `aggregate` / ページ別 `per_page`）に応じた Markdown / JSON 出力
5. サマリ出力
