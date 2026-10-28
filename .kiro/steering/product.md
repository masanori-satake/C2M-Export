# Product Overview

C2M-Export は、Confluence Data Center のページツリーを REST API で再帰的に取得し、AI ナレッジベース向けに Markdown ファイルへ統合エクスポートする Python CLI ツールです。

## 主な機能

- Confluence Data Center 9.2 以降の REST API によるページツリー取得（DFS）
- Storage Format (XHTML) から Markdown への変換（BeautifulSoup 使用）
- 各ページにメタデータ（Page ID, Space Key, URL）を付与
- HTTP/HTTPS Proxy（CONNECT トンネル）対応
- 出力サイズ制限（`max_mb` / `stop_threshold_mb`）による肥大化防止
- 複数ルートページ ID の一括処理
- エクスポート結果の Zip 圧縮オプション
- Streamlit による Web UI（排他制御付き）
- コンテンツ分析（アセスメント）: メタデータベースで規模・構造・移設リスク・権限・鮮度を Markdown/JSON 出力
- ファイルシステムエクスポート: ページ階層をディレクトリ/ファイル化、添付バイナリ保存、Frontmatter、添付リンク書き換え（relative/original）
- 差分同期・レジューム: マニフェストによる追加/変更/削除/移動・改名の追従と中断再開
- 権限エクスポート: コンテンツ制限（Read/Read+Write）の記録・レポート出力

## 姉妹プロジェクト

J2M-Export（Jira → Markdown）および G2M-Export（Google → Markdown）と CLI 引数や振る舞いの一貫性を維持する設計方針です。

## 対象ユーザー

社内 Confluence のナレッジを LLM に取り込みたい開発者・運用者。
