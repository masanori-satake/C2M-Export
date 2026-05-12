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

### 1. 設定ファイルの準備

リポジトリ直下の `c2m_config_sample.yaml` を `c2m_config.yaml` にコピーし、環境に合わせて内容を編集してください。

```cmd
copy c2m_config_sample.yaml c2m_config.yaml
```

`c2m_config.yaml` の例:
```yaml
base_url: "https://your-confluence/wiki"
token: "your_bearer_token_here"
root_page_id: "12345678"
output_dir: "."
max_mb: 100
stop_threshold_mb: 95
```

### 2. 実行

#### 最も簡単な実行方法
設定ファイル（`c2m_config.yaml`）が準備されている場合、引数なしで実行可能です。

```cmd
python -m c2m_export.cli
```

※設定ファイルで `root_page_id` が指定されていない場合や、別のページを書き出したい場合は、コマンドライン引数で指定します。

```cmd
python -m c2m_export.cli --root-page-id 98765432
```

複数のページIDを一度に指定して実行することも可能です（スペース区切り）。

```cmd
python -m c2m_export.cli --root-page-id 12345678 98765432
```

#### 設定を上書きして実行
コマンドライン引数を指定することで、設定ファイルの内容を一時的に上書きして実行できます。

```cmd
python -m c2m_export.cli --base-url https://other-confluence/wiki --token other_token --root-page-id 12345678 --proxy http://proxy.example.com:8080
```

### パラメータ
- `--base-url`: ConfluenceのベースURL (例: `https://host/wiki`)
- `--root-page-id`: 起点となるページのID（複数指定可能）
- `--output-dir`: 出力先ディレクトリ (既定: カレントディレクトリ)
- `--max-mb`: 出力ファイルの最大サイズ(MB) (既定: 100.0)
- `--stop-threshold-mb`: 処理を停止する閾値(MB) (既定: 95.0)
- `--proxy`: プロキシURL
- `--config`: 設定ファイルパス (既定: `c2m_config.yaml`)
- `--token`: Bearerトークン

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
