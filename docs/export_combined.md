# 結合モード（統合エクスポート）詳細

特定ページ配下のページツリーを再帰的に取得し、全ページを 1 つの Markdown ファイルに統合して出力する基本モード（`python -m c2m_export.cli`）の詳細ガイドです。

---

## 1. 設定ファイルの準備と実行

リポジトリ直下の `c2m_config_sample.yaml` を `c2m_config.yaml` にコピーし、環境に合わせて内容を編集してください。

```cmd
copy c2m_config_sample.yaml c2m_config.yaml
```

`c2m_config.yaml` の例:
```yaml
base_url: "https://your-confluence/wiki"
token: "your_bearer_token_here"
root_page_ids:
  - "12345678"
  - "98765432"
output_dir: "."
max_mb: 100
stop_threshold_mb: 95
```

### 最も簡単な実行方法
設定ファイル（`c2m_config.yaml`）が準備されている場合、引数なしで実行可能です。

```cmd
python -m c2m_export.cli
```

※設定ファイルで `root_page_ids` が指定されていない場合や、別のページを書き出したい場合は、コマンドライン引数で指定します。

```cmd
python -m c2m_export.cli --root-page-id 98765432
```

複数のページ ID を一度に指定して実行することも可能です（スペース区切り）。

```cmd
python -m c2m_export.cli --root-page-id 12345678 98765432
```

### 設定を上書きして実行
コマンドライン引数を指定することで、設定ファイルの内容を一時的に上書きして実行できます。

```cmd
python -m c2m_export.cli --base-url https://other-confluence/wiki --token other_token --root-page-id 12345678 --proxy http://proxy.example.com:8080
```

---

## 2. Web UI での実行

Streamlit を使用したブラウザベースのインターフェースも利用可能です。

```cmd
python -m c2m_export.web
```

起動後、ブラウザで表示される URL（既定では `http://localhost:8501`）にアクセスしてください。
Web UI では、複数の Root Page ID の動的な追加、進捗のリアルタイム表示、およびエクスポート結果の Zip ダウンロードが可能です。

---

## 3. CLI パラメータ（共通）

- `--base-url`: Confluence のベース URL (例: `https://host/wiki`)
- `--root-page-id`: 起点となるページの ID（複数指定可能）
- `--output-dir`: 出力先ディレクトリ (既定: カレントディレクトリ)
- `--max-mb`: 出力ファイルの最大サイズ(MB) (既定: 100.0)
- `--stop-threshold-mb`: 処理を停止する閾値(MB) (既定: 95.0)
- `--proxy`: プロキシ URL
- `--config`: 設定ファイルパス (既定: `c2m_config.yaml`)
- `--token`: Bearer トークン
- `--zip`: エクスポート結果を Zip 圧縮する
- `--overwrite`: 既存ファイルを上書きする

---

## 4. ファイル名規則

出力ファイル名は以下の形式になります：
`【<spaceKey>】 <トップページタイトル>.md`

- **非上書きモード (`overwrite: False`)**: 既存ファイルとの衝突を回避するため、一括実行ごとに統一されたタイムスタンプサフィックス `_YYMMDD_HHMMSS` が付与されます。
- **上書きモード (`overwrite: True`)**: タイムスタンプサフィックスを付けず、同名ファイルが存在する場合は直接上書きされます。

---

[READMEへ戻る](../README.md)
