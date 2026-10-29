## 2026/10/29 - 添付ファイルダウンロード時の Bearer Token 漏洩および SSRF の防止

**Vulnerability:** `ConfluenceClient.download_attachment` において、外部ホストや不正な IP（例: `https://attacker.com` や `http://169.254.169.254`）を指す絶対 URL が指定された場合、`requests.Session` が `Authorization: Bearer <token>` ヘッダーを付与したままリクエストを送信し、トークンが外部へ漏洩する脆弱性および SSRF リスクが存在した。

**Learning:** API レスポンスに含まれる URL リンク（`_links.download` など）を認証付きセッションでそのまま取得する際、ターゲットのホスト名が設定済みの `base_url` と一致するか検証しないと、第三者サーバーへクレデンシャルが露出するリスクがある。

**Prevention:** 動的な API メタデータで指定されたエンドポイントに認証付きリクエストを実行する前に、必ず `urllib.parse.urlparse` を使用してターゲット URL のホスト名を検証する。

## 2026/10/30 - URL クエリパラメータに含まれる機密トークンのマスク処理強化

**Vulnerability:** 分析機能（`analyze` CLI / MCP サーバー）のサニタイズ処理において `Authorization` ヘッダはマスクされていたが、URL クエリパラメータとして渡される認証情報（例: `token=...`, `access_token=...`, `api_key=...`）がマスクされずにログや出力 JSON に露出するリスクが存在した。

**Learning:** 認可・認証文字列は HTTP ヘッダー（`Authorization`）だけでなく、API のレスポンスリンクやリダイレクト URL、Web UI のクエリ文字列に埋め込まれて出力されるケースがあるため、URL パラメータパターンの網羅的サニタイズが必要となる。

**Prevention:** `sanitize_text` にて `Authorization` ヘッダーの除去に加えて、`token`, `access_token`, `api_key`, `secret`, `password` 等の機密キーパターンに対する URL クエリパラメータの正規表現マスク処理を共通層として追加・適用する。
