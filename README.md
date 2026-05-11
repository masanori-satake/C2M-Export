# Confluence to Markdown Exporter (C2M-Export)

Confluence Data Center 9.2 のページツリーを REST API で取得し、AIナレッジ向けに Markdown へ統合エクスポートするローカルCLIツールです。

## 特徴
- Confluence Data Center 9.2 対応 (REST API)
- ページツリーを再帰的に取得し、1つの Markdown ファイルに統合
- HTTP/HTTPS Proxy (CONNECTトンネル) 対応
- Windows ファイル名制約に基づいたサニタイズ
- 出力ファイルサイズ制限機能 (既定100MB)
- 基本的なマクロ (Code, PlantUML) の変換対応

## セットアップ

Python 3.8以上が必要です。

```cmd
# 依存関係のインストール
pip install -r requirements.txt
```

## 実行方法

### 基本的な実行 (コマンドプロンプト / PowerShell)

```cmd
# 環境変数でトークンを指定 (推奨)
set CONFLUENCE_TOKEN=your_bearer_token_here

# 実行
python -m c2m_export.cli --base-url https://your-confluence/wiki --root-page-id 12345678 --proxy http://proxy.example.com:8080
```

### パラメータ
- `--base-url`: ConfluenceのベースURL (例: `https://host/wiki`)
- `--root-page-id`: 起点となるページのID
- `--output-dir`: 出力先ディレクトリ (既定: カレントディレクトリ)
- `--max-mb`: 出力ファイルの最大サイズ(MB) (既定: 100)
- `--stop-threshold-mb`: 処理を停止する閾値(MB) (既定: 95)
- `--proxy`: プロキシURL
- `--config`: 設定ファイルパス (既定: `%USERPROFILE%\.confluence_exporter.yaml`)
- `--token`: Bearerトークン (環境変数 `CONFLUENCE_TOKEN` でも指定可)

## 設定ファイルによる実行

`%USERPROFILE%\.confluence_exporter.yaml` に既定値を保存できます。

```yaml
base_url: "https://your-confluence/wiki"
proxy: "http://proxy.example.com:8080"
max_mb: 100
stop_threshold_mb: 95
output_dir: "./exports"
```

この状態で以下のように実行可能です：
```cmd
python -m c2m_export.cli --root-page-id 12345678
```

## ファイル名規則
出力ファイル名は以下の形式になります：
`【<spaceKey>】 <トップページタイトル>.md`

ファイルが既に存在する場合、衝突を避けるために `(<pageId>)` が付与されます。
例: `【SPACE】 Title (12345).md`

## サイズ制限の挙動
- 出力ファイルの合計サイズが `--stop-threshold-mb` (既定95MB) を超える見込みになった時点で、新しいページの取得を停止し、それまで取得した内容をファイルに書き出します。
- 最終的なファイルサイズが `--max-mb` (既定100MB) を超えた場合は警告ログが出力されます。

## よくあるエラー
- **401/403**: トークンが無効か権限がありません。
- **404**: ページIDまたはURLが間違っています。ベースURLに `/wiki` などのコンテキストパスが含まれているか確認してください。
- **Proxy Error**: プロキシ設定が正しいか、ネットワークがつながっているか確認してください。
