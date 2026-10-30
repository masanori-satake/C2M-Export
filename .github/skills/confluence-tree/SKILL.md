---
name: confluence-tree
description: Confluence のページ階層を樹形図（ページツリー）としてテキスト / Markdown / JSON 形式で出力し、個別アクセス制限やマクロ・添付数・更新日などの付帯情報を視覚化します。
---

<!--
NOTE: 正本は skills/confluence-tree/SKILL.md です。
各ツールの検出・発火条件（.kiro/skills/: Kiro、.github/skills/: GitHub Copilot、skills/: 汎用 Agent Skills）に合わせて 3 箇所に複製配置されています。
SKILL.md や scripts を修正・更新する場合は、必ず正本を編集し、複製先へ同期（上書きコピー）を行ってください。
-->

# Confluence Page Tree Visualization Skill

この Skill は、Confluence のページ階層構造を樹形図（ページツリー）として可視化し、テキスト・Markdown・JSON の 3 形式で提供します。また、個別アクセス制限・マクロ使用種別数・添付数・最終更新日などの付帯情報（annotation）をノード行にインライン併記、または構造化データとして出力できます。

## 前提要件

- **Python**: Python 3.8 以上が導入されていること。
- **リポジトリ**: C2M-Export のソースコードがローカル環境にチェックアウトされており、依存ライブラリがインストールされていること。
  ```bash
  pip install -r requirements.txt
  ```
- **認証情報**: Confluence 個人用アクセストークン（PAT）を環境変数 `C2M_CONFLUENCE_TOKEN`（推奨）または `CONFLUENCE_TOKEN` に設定していること。
  ```bash
  export C2M_CONFLUENCE_TOKEN="your-confluence-pat"
  ```
  ※ トークンをコマンドライン引数（`--token`）で直接渡すと、プロセス一覧やシェル履歴に記載が残るため推奨されません。

## 実行方法

本 Skill は、サブプロセスとして CLI エントリーポイント `python -m c2m_export.tree` または補助スクリプト `python skills/confluence-tree/scripts/run_tree.py` を呼び出して動作します。

### 基本的なコマンド

```bash
python -m c2m_export.tree \
  --base-url "https://confluence.example.com" \
  --space-key "DEV" \
  --format "text"
```

または補助スクリプトを使用:

```bash
python skills/confluence-tree/scripts/run_tree.py \
  --base-url "https://confluence.example.com" \
  --space-key "DEV" \
  --format "markdown" \
  --include restriction macros attachments last_modified
```

## 入力パラメータ（CLI オプション）

| オプション | 型 | 説明 | 既定値 |
|---|---|---|---|
| `--base-url` | 文字列 (必須) | Confluence のベース URL (例: `https://confluence.example.com`) | なし |
| `--space-key` | 文字列リスト | 起点とする Space キー (複数指定可) | なし |
| `--root-page-id` | 文字列リスト | 起点とするルートページ ID (複数指定可) | なし |
| `--format` | 文字列 | 出力フォーマット (`text`, `markdown`, `json`) | `text` |
| `--include` | 文字列リスト | 付帯情報 (`restriction`, `macros`, `attachments`, `last_modified`, `all`) | なし (付帯情報なし) |
| `--ascii` | フラグ | 絵文字の代わりに ASCII マーク (`[R]`, `att:N`, `mac:N`) を使用 | `False` |
| `--max-depth` | 整数 | 探索する最大階層深さ (指定なし/0で無制限) | 無制限 |
| `--output` | 文字列 | 結果の保存先ファイルパス (省略時は標準出力) | なし |
| `--overwrite` | フラグ | `--output` 指定ファイルが存在する場合に上書き許可 | `False` |
| `--proxy` | 文字列 | HTTP/HTTPS プロキシ URL | なし |
| `--config` | 文字列 | 設定ファイルのパス | `c2m_config.yaml` |
| `--token` | 文字列 | Confluence Bearer トークン (環境変数推奨) | なし |

※ `--space-key` または `--root-page-id` の少なくとも 1 つが必須です。

## 付帯情報（--include）と表示マーク一覧

- `restriction`: 個別アクセス制限ありのノードに 🔒 (ASCII: `[R]`) を表示。Markdown / JSON では詳細（Read / Read+Write 対象者）も出力。
- `attachments`: 添付ファイルが存在するノードに 📎N (ASCII: `att:N`) を表示（N は添付件数）。
- `macros`: マクロが使用されているノードに ⚙N (ASCII: `mac:N`) を表示（N はマクロ種別数）。Markdown / JSON ではマクロ名ごとの回数を個別一覧表示。
- `last_modified`: 最終更新日 `(YYYY-MM-DD)` を表示（不明時は `(?)`）。

※ 付帯情報未指定時は追加 API 呼び出しを一切行わず、高速にページタイトルと ID のみのツリーを取得します。

## 終了コード規約

- `0`: 成功 (`ok`)
- `2`: パラメータ不正 (`INVALID_PARAM`)
- `3`: 認証失敗 (`AUTH_FAILED`)
- `4`: 対象未存在 (`TARGET_NOT_FOUND`)
- `5`: Confluence API / ネットワークエラー (`API_ERROR`)
- `10`: 内部エラー (`INTERNAL_ERROR`)
