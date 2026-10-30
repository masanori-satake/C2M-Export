<!--
NOTE: 正本は skills/confluence-setup/SKILL.md です。
各ツールの検出・発火条件（.kiro/skills/: Kiro、.github/skills/: GitHub Copilot、skills/: 汎用 Agent Skills）に合わせて 3 箇所に複製配置されています。
SKILL.md や scripts を修正・更新する場合は、必ず正本を編集し、複製先へ同期（上書きコピー）を行ってください。
-->

# Confluence Setup Support Skill

この Skill は、C2M-Export の各機能（分析 CLI・MCP・エクスポート）を「使える状態」にするまでのセットアップを支援します。環境・認証・設定・ネットワークの各要因を上流から下流へ順に切り分け、どこで詰まっているかを素早く特定して対処方法を提示します。

`confluence-analysis` Skill が実行時にエラーになる・ハングする・空の結果を返すといった場合、まずこの Skill で原因を切り分けてください。

## このスキルが解決する課題

- トークンを設定したのに認証が通らない（環境変数の反映漏れ・変数名違い）
- 実行するとハングして返ってこない（プロキシ経路・ファイアウォール）
- `401/403/404` が返る（認証失敗・権限・base_url 誤り）
- スペースキーに記号（`~` `@` `/` など）を含む場合の挙動が不安
- 設定ファイル（`c2m_config.yaml`）が意図どおり読まれているか不明

## 前提要件

- **Python**: 3.8 以上。
- **リポジトリ**: C2M-Export をローカルにチェックアウトし、依存をインストール済みであること。
  ```bash
  pip install -r requirements.txt
  ```
- **認証情報**: Confluence 個人用アクセストークン (PAT) を環境変数で設定していること。
  - 推奨: ユーザー環境変数 `C2M_CONFLUENCE_TOKEN`（代替: `CONFLUENCE_TOKEN`）。
  - GitHub Copilot など他ツールと共有する場合も、OS のユーザー環境変数に一度登録しておくと一元管理できます。
  - **注意**: 環境変数は登録時点で起動済みのプロセスには反映されません。登録後は Kiro / ターミナルを再起動してください。

## 使い方

### 1. 一括診断（推奨の起点）

セットアップ要因を上流（環境）から下流（API 応答）まで順に検査します。

```bash
python skills/confluence-setup/scripts/diagnose.py
```

特定のスペースキーだけを検査対象にする場合:

```bash
python skills/confluence-setup/scripts/diagnose.py --space-key "~user@example.com" "DEV"
```

ネットワークに出られない環境で、環境・設定だけ確認する場合:

```bash
python skills/confluence-setup/scripts/diagnose.py --skip-network
```

### 検査項目（実行順）

| # | 検査 | 失敗時に疑うこと |
|---|---|---|
| 1 | Python バージョン (>= 3.8) | Python の導入・バージョン |
| 2 | 必須依存 (requests / bs4 / yaml) | `pip install -r requirements.txt` 未実行 |
| 3 | トークン環境変数の有無 | 変数名違い・再起動していない |
| 4 | 設定ファイル読み込み (base_url / space_keys / token) | `c2m_config.yaml` の記載・配置 |
| 5 | プロキシの最終解決値 | 環境変数プロキシが設定ファイルを上書き |
| 6 | Confluence 疎通 (`/rest/api/space`) | ハング=プロキシ経路 / 401,403=認証 / 404=base_url |
| 7 | スペースキー解決（記号キーのエスケープ検証） | キーの権限・存在、URL エスケープ |

- 出力は `[OK]` / `[WARN]` / `[NG]` で表示されます。`[NG]` が 1 つでもあると終了コードは `1` です。
- 秘匿情報（トークン本体）は出力しません。有無と長さのみ表示します。

### 2. 切り分けの指針

- **ハングして返らない** → 項目 6 がタイムアウトする場合はプロキシ経路の問題。`c2m_config.yaml` の `proxy`、または環境変数 `HTTPS_PROXY` / `HTTP_PROXY` を確認してください（C2M-Export は環境変数を設定ファイルより優先します）。
- **401 / 403** → トークンが無効・期限切れ・権限不足。PAT を再発行し環境変数を更新、再起動。
- **404** → `base_url` の誤り。`/wiki` などのコンテキストパスの有無を確認（REST API は内部で `{base_url}/rest/api/...` として呼ばれます。`base_url` に `/rest/api` は含めない）。
- **特定スペースだけ失敗** → そのスペースへの閲覧権限、またはスペースキーの綴り。項目 7 がエスケープ版で成功した場合は URL エスケープの不足を示します。

### 3. 設定ファイルの最小構成

`c2m_config.yaml`（`.gitignore` 対象。トークンは記載せず環境変数で管理）:

```yaml
base_url: "https://confluence.example.com/wiki"
space_keys:
  - "~user@example.com"
  - "DEV"
proxy: "http://proxy.example.com:8080"   # 社内環境で必要な場合
analysis:
  mode: "summary"
```

## 診断が通った後

すべて `[OK]`（終了コード 0）になれば、`confluence-analysis` Skill が利用可能です。分析の実行方法は `confluence-analysis` の SKILL.md を参照してください。大規模スペースの分析は時間がかかるため、スペース単位・ユースケース単位で絞るか、バックグラウンド実行を検討してください。

## 既知の注意点

- **環境変数プロキシの優先**: C2M-Export は `HTTPS_PROXY` / `HTTP_PROXY` を設定ファイルの `proxy` より優先します。意図しないプロキシが効いていないか項目 5 で確認してください。
- **スペースキーのエスケープ**: `~` `@` `.` を含むキーは、`requests` の URL 正規化により現状のコードでも通常は成功します。ただし `#` `?` を含むキーは正規化だけでは壊れ得るため、そのようなキーで失敗する場合は項目 7 のエスケープ版の結果を確認してください。
