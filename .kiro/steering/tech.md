# Tech Stack

## 言語・ランタイム

- Python 3.8 以上

## 依存ライブラリ（requirements.txt）

| ライブラリ | 用途 |
|---|---|
| requests | Confluence REST API 呼び出し |
| beautifulsoup4 | Storage Format (XHTML) → Markdown 変換 |
| PyYAML | YAML 設定ファイルの読み書き |
| streamlit | Web UI |

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

```powershell
python -m c2m_export.cli
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
