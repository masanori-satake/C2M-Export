# Project Structure

```
C2M-Export/
├── c2m_export/            # メインパッケージ
│   ├── __init__.py        # パッケージ初期化
│   ├── cli.py             # CLI エントリーポイント (python -m c2m_export.cli)
│   ├── config.py          # 設定管理 (CLI引数 / YAML / 環境変数)
│   ├── confluence.py      # Confluence REST API クライアント (リトライ・Proxy対応)
│   ├── converter.py       # Storage Format → Markdown 変換 (マクロ処理含む)
│   ├── utils.py           # ユーティリティ (ファイル名サニタイズ, サイズ計算, Zip生成)
│   └── web.py             # Streamlit Web UI (python -m c2m_export.web)
├── tests/                 # テストディレクトリ
│   ├── test_cli_overwrite.py    # CLI 上書き動作テスト
│   ├── test_converter.py        # HTML→Markdown 変換テスト
│   ├── test_macros_extended.py  # マクロ変換テスト
│   └── test_utils.py            # ユーティリティ関数テスト
├── output/                # エクスポート出力先（gitignore対象）
├── c2m_config.yaml        # 実行用設定ファイル（gitignore対象）
├── c2m_config_sample.yaml # 設定ファイルのサンプル
├── requirements.txt       # 実行時依存
├── .pre-commit-config.yaml # pre-commit フック設定
├── AGENTS.md              # AI エージェント向け指示書
├── README.md              # ユーザー向けドキュメント
└── README_DEV.md          # 開発者向けドキュメント（設計・拡張ガイド）
```

## モジュールの責務

| モジュール | 責務 |
|---|---|
| `config.py` | 設定の読み込み・検証・正規化 |
| `confluence.py` | API通信、ページネーション、指数バックオフリトライ |
| `converter.py` | XHTML→Markdown変換、マクロハンドリング、テーブル処理 |
| `cli.py` | エントリーポイント、DFS探索、サイズ制限制御、ファイル出力 |
| `utils.py` | ファイル名生成、サイズユーティリティ、Zip圧縮 |
| `web.py` | Streamlit UI、排他制御、進捗表示 |

## 実行フロー

1. `Config.load()` → 設定を優先順位に従い統合
2. `Config.validate()` → 必須項目チェック・URL正規化
3. `ConfluenceClient` / `MarkdownConverter` 初期化
4. ルートページごとにフェイルファスト（存在確認・ファイル競合チェック）
5. `export_tree()` で DFS 巡回 → Markdown 統合
6. ファイル書き出し or Zip 圧縮
