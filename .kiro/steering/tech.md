# Tech Stack

## 言語・ランタイム

- Python 3.8 以上

## 依存ライブラリ（requirements.txt / requirements-mcp.txt）

| ライブラリ | 用途 | 依存種別 |
|---|---|---|
| requests | Confluence REST API 呼び出し | 必須 (requirements.txt) |
| beautifulsoup4 | Storage Format (XHTML) → Markdown 変換 | 必須 (requirements.txt) |
| PyYAML | YAML 設定ファイルの読み書き | 必須 (requirements.txt) |
| streamlit | Web UI | 必須 (requirements.txt) |
| mcp | FastMCP による MCP サーバ機能 | 任意 (requirements-mcp.txt) |

## 開発ツール

- pytest: テストフレームワーク
- pre-commit: コード品質チェック（trailing-whitespace, end-of-file-fixer, check-yaml, check-added-large-files）
- mypy: 静的型検査（`.mypy_cache` 利用）

## コマンド一覧

### 依存関係のインストール

```powershell
pip install -r requirements.txt
```

### CLI 実行

結合モード:
```powershell
python -m c2m_export.cli
```

分析 CLI モード:
```powershell
python -m c2m_export.analyze --base-url https://confluence.example.com --space-key DEV --usecase stale --mode summary
```

分析 CLI モード（レジューム再開）:
```powershell
python -m c2m_export.analyze --base-url https://confluence.example.com --space-key DEV --usecase stale --resume
```

MCP サーバ起動:
```powershell
python -m c2m_export.mcp_server
```

アセスメントモード:
```powershell
python -m c2m_export.assess
```

ファイルシステムエクスポートモード:
```powershell
python -m c2m_export.fsexport
```

権限エクスポートモード:
```powershell
python -m c2m_export.permexport
```

### Web UI 起動

```powershell
python -m c2m_export.web
```

### テスト実行

```powershell
$env:PYTHONPATH = "."; python -m pytest
```

### pre-commit フック実行

```powershell
pre-commit run --all-files
```

## 設定の優先順位

CLI 引数 > 環境変数 > YAML 設定ファイル（`c2m_config.yaml`）> デフォルト値

## 認証方式

Bearer トークン（`Authorization: Bearer <token>`）
環境変数 `C2M_CONFLUENCE_TOKEN`（推奨）または `CONFLUENCE_TOKEN` によるトークン設定をサポート。
