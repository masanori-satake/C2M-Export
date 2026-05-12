# 開発者向けドキュメント (README_DEV.md)

このドキュメントは、C2M-Export の内部構造、設計思想、および拡張方法について解説します。

## システム概要

C2M-Export は、Confluence Data Center のページツリーを再帰的に取得し、1つの Markdown ファイルに統合する Python ベースの CLI ツールです。特に AI（LLM）のナレッジベース作成に最適化されており、メタデータの付与や階層構造に応じた見出しの調整を行います。

## システム構成図

システムの主要コンポーネントと外部接続の構成を以下に示します。

```mermaid
graph TD
    subgraph "Local Environment"
        CLI[cli.py: Main Logic]
        Config[config.py: Config Management]
        Client[confluence.py: API Client]
        Converter[converter.py: Markdown Converter]
        Utils[utils.py: Utilities]
        Output[.md File]
    end

    subgraph "External"
        Confluence[Confluence Data Center]
        Proxy[HTTP/HTTPS Proxy]
    end

    CLI --> Config
    CLI --> Client
    CLI --> Converter
    CLI --> Utils
    Client --> Proxy
    Proxy --> Confluence
    CLI --> Output
```

## クラス図

主要なクラスとその責務、および関係性を以下に示します。

```mermaid
classDiagram
    class Config {
        +base_url: str
        +root_page_id: str
        +token: str
        +proxy: str
        +max_mb: float
        +load()
        +validate()
    }

    class ConfluenceClient {
        +base_url: str
        +session: requests.Session
        +get_page(page_id: str)
        +get_child_pages(page_id: str)
        -_request(method, path, params)
    }

    class MarkdownConverter {
        +base_url: str
        +convert(html_content: str, level: int)
        -_walk(node, level)
        -_process_tag(tag, level)
        -_handle_macro(tag)
        -_handle_structured_macro(tag)
    }

    class CLI {
        +export_tree()
        +main()
    }

    CLI ..> Config : uses
    CLI ..> ConfluenceClient : uses
    CLI ..> MarkdownConverter : uses
```

## 処理シーケンス

全体の実行フローは以下の通りです。

```mermaid
sequenceDiagram
    participant User
    participant CLI
    participant Config
    participant Client as ConfluenceClient
    participant Conv as MarkdownConverter

    User->>CLI: python -m c2m_export.cli
    CLI->>Config: load() & validate()
    Config-->>CLI: Config Data
    CLI->>Client: Initialize(base_url, token, proxy)
    CLI->>Conv: Initialize(base_url)

    CLI->>Client: get_page(root_page_id)
    Client-->>CLI: Root Page Info (Title, Space)

    Note over CLI, Client: export_tree (DFS Traversal)
    loop pages in stack
        CLI->>Client: get_page(page_id)
        Client-->>CLI: Page Data (Storage Format)
        CLI->>Conv: convert(body, level)
        Conv-->>CLI: Markdown String
        CLI->>Client: get_child_pages(page_id)
        Client-->>CLI: Child List
        Note right of CLI: Check Size Limit
    end

    CLI->>CLI: Write combined MD to file
    CLI-->>User: Done (File Path)
```

## 探索アルゴリズムのフローチャート

`export_tree` 関数における深さ優先探索（DFS）とサイズ制限の処理フローです。

```mermaid
flowchart TD
    Start([開始]) --> Init[スタックにルートIDを追加]
    Init --> Pop{スタックは空か?}
    Pop -- No --> Fetch[ページ情報を取得]
    Fetch --> Convert[Markdownに変換]
    Convert --> CheckSize{サイズ閾値を超えたか?}

    CheckSize -- Yes --> Warning[/警告ログを出力/]
    Warning --> Combine[それまでの内容を統合]

    CheckSize -- No --> AddMD[リストに追加 & サイズ更新]
    AddMD --> GetChildren[子ページ一覧を取得]
    GetChildren --> Push[逆順にスタックへ追加]
    Push --> Pop

    Pop -- Yes --> Combine
    Combine --> Save([ファイル保存して終了])
```

## 拡張ポイント

### 新しいマクロの変換サポート
`c2m_export/converter.py` の `MarkdownConverter` クラスにハンドラを追加します。

1.  `_handle_structured_macro` または `_handle_macro` 内にマクロ名の判定を追加。
2.  BeautifulSoup を使用してマクロのパラメータやボディを抽出。
3.  Markdown 形式の文字列を返す。

### API呼び出しの追加
`c2m_export/confluence.py` の `ConfluenceClient` にメソッドを追加します。共通の `_request` メソッドを使用することで、リトライロジックやProxy設定が自動的に適用されます。

## テスト方法

`pytest` を使用してテストを実行します。

```bash
# プロジェクトルートで実行
PYTHONPATH=. pytest
```

### 主要なテストファイル
- `tests/test_converter.py`: HTMLからMarkdownへの変換ロジックを検証。
- `tests/test_utils.py`: ファイル名サニタイズやサイズ計算のロジックを検証。
