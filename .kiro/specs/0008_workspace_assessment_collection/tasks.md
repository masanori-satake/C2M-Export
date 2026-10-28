# Implementation Plan

本計画は、C2M-Export を「ワークスペースレベルで状況把握・詳細調査し、他ストレージへの移設課題抽出・計画立案を支援する」ツールへ成長させるための、**Confluence REST API 収集層（I/O）の拡張**を実装するものである。design.md の「2 段収集（全体把握＝軽量・既定 ON / 詳細調査＝重量・オプトイン）→ 0007 の共通 1 層 `run_analysis` / `AnalysisResponse` へ追加のみで接続」構成に従い、下から積み上げる依存順で進める。

前提:

- 本計画の各タスクは「spec を書く」ものではなく「コードを実装する」タスクである。各タスクは対象ファイルのリポジトリ相対パスと、完了条件（要件番号への紐付け `_要件: N.M_`）を持つ。
- 0007（`analysis/`・`analyze.py`・`AnalysisResponse`・`AnalysisParams`・`AnalysisConfig`・`Collector` 拡張点・Skill/MCP）が実装済みであることを前提に、その上へ**追加のみ・後方互換**で積む。既存メソッド・既存フィールド・既存 CLI・0007 の既存挙動は変更しない。
- コメント・docstring・ログはすべて日本語（PEP 257 準拠）。Python 3.8 互換の型注釈（`typing.List/Dict/Set/Optional`）。テスト実行は `$env:PYTHONPATH="."; python -m pytest`（PowerShell）。
- 2 段収集は横断機構のため、まずクライアント・モデルを用意し、次に全体把握フェーズ、次に詳細調査フェーズ（オプトイン）、最後に抽出/スキーマ/CLI/Skill/doc/テストの順に積む。各フェーズは独立レビュー・段階マージ可能な粒度とする（design「規模と分割の判断」）。

> イテレーション 2 の反映: `.review.json` の全 finding を反映済み。特に per-space 収集（スペース権限 `collect_space_permissions`・スペースウォッチャー `collect_watchers`）を `Collector.collect_space_details(space_keys)` に明示化し（タスク 5）、全体把握収集は `Collector.collect_workspace_overview()` に確定（タスク 4）、`list_spaces` は run_analysis で 1 回取得して共有（タスク 4/10）、ウォッチャー失敗は content/space を分離して count も分離（タスク 3/8）した。詳細は design.md「レビュー指摘への対応」節を参照。

実装順序の方針（依存順）:

1. `ConfluenceClient` への A〜D メソッド追加（I/O 土台）
2. `models` へのフィールド追加（追加のみ・後方互換）
3. 全体把握フェーズ収集（軽量・既定 ON）
4. 詳細調査フェーズ収集（重量・オプトイン）
5. 抽出純粋関数（workspace / provenance）
6. 0007 スキーマ拡張（`AnalysisResponse` 新ブロック・既存 UC 追加フィールド・`schema_version` 1.1）
7. 共通 1 層 `run_analysis` / `_resolve_roots` 拡張と CLI/設定拡張
8. Skill（SKILL.md 3 箇所）/ MCP の記述更新
9. ドキュメント・設定サンプル・steering 更新
10. 後方互換・認証非漏洩・全体品質チェック

---

## フェーズ A: ConfluenceClient の API メソッド追加（I/O 土台）

- [ ] 1. 全体把握フェーズ（A/C/D）の API メソッドを追加する
  - `c2m_export/confluence.py` の `ConfluenceClient` に、既存 `_request`（Bearer・ページング・5xx 指数バックオフ・Proxy）を再利用して以下を追加する（design §1 の表）。
    - `list_spaces(type_=None, status=None, label=None, content_label=None, expand=None, limit=25)`（`GET /rest/api/space`、`start`/`limit` ページングで全件）。
    - `get_space(space_key, expand=None)`（`GET /rest/api/space/{spaceKey}`）。
    - `get_space_labels(space_key)`（`GET /rest/api/space/{spaceKey}/labels`）。
    - `get_descendant_page_count(page_id)`（`GET /rest/api/content/{id}/descendant/page/count`）。
    - `scan_content(space_key, type_="page", status=None, expand=None, cursor=None, limit=100)`（`GET /rest/api/content/scan`、`_links.next`/`cursor` を辿り全件）。
    - `get_descendants(page_id, type_="page", expand=None, limit=25)`（`GET /rest/api/content/{id}/descendant/{type}`、`start`/`limit` 全件）。
    - `get_current_user(expand=None)`（`GET /rest/api/user/current`）。
    - `get_user_memberof()`（`GET /rest/api/user/memberof`、ページング全件）。
    - `get_access_mode()`（`GET /rest/api/accessmode`）。
    - `get_server_information()`（`GET /rest/api/server-information`）。
  - 取得可否が実機依存のメソッドも I/O では分類せず、`_request` が送出する例外（`requests.exceptions.HTTPError` 等）を**そのまま上位へ送出**する（致命/欠落の判断は Collector / run_analysis 側）。
  - docstring は日本語。トークンはログに出さない。
  - `tests/test_confluence_0008_client.py` を作成し、各メソッドの path/params、ページング・scan のカーソル追従（`_links.next` 消滅で終了）を `requests` モックで検証する。
  - 完了条件: 全体把握系メソッドが正しい path/params を組み、ページング/カーソルで全件取得でき、例外を素通しする。
  - _要件: 2.1, 2.2, 3.1, 3.2, 3.3, 10.6, 12.1, 12.2, 16.5_

- [ ] 2. 詳細調査フェーズ（B/C）の API メソッドを追加する
  - `c2m_export/confluence.py` の `ConfluenceClient` に以下を追加する（design §1 の表）。
    - `get_content_history(page_id, expand="lastUpdated,contributors")`（`GET /rest/api/content/{id}/history`）。
    - `get_labels(page_id, prefix=None, limit=200)`（`GET /rest/api/content/{id}/label`、ページング全件）。
    - `search_cql(cql, expand="history,space,version", limit=50)`（`GET /rest/api/content/search`、ページング全件）。
    - `get_comments(page_id, depth="all", expand="extensions.location,extensions.resolution")`（`GET /rest/api/content/{id}/child/comment`、ページング全件）。既定 expand で各コメントの `extensions.location`（inline/footer）と `extensions.resolution.status`（未解決判定）を取得する。`location` クエリ引数は設けず、`depth=all` で全件取得して分類する（design §1 表・§2.1）。
    - `get_attachment_extracted_text(page_id, attachment_id, limit=None)`（`GET /rest/api/content/{id}/child/attachment/{attachmentId}/extractedtext`）。
    - `get_relevant_view_restrictions(page_id)`（`GET /rest/api/content/{id}/restriction/relevantViewRestrictions`）。
    - `get_space_permissions(space_key)`（`GET /rest/api/space/{spaceKey}/permissions` GET 系のみ）。
    - `get_content_watchers(content_id)`（`GET /rest/api/content/{contentId}/watchers`）。
    - `get_space_watchers(space_key)`（`GET /rest/api/space/{spaceKey}/watchers`）。
  - 管理者 API（`admin/*`・`backup-restore/*`・グローバル `permissions` PUT・`index/reindex`・`webhooks`・`cluster/nodes`・`audit`・`instance-metrics`）に対応するメソッドは**追加しない**。
  - 取得可否が実機依存のメソッドは例外を素通しする（致命/欠落の判断は呼び出し側）。docstring は日本語。
  - `tests/test_confluence_0008_client.py` に、各メソッドの path/params・ページング・CQL の `expand` 既定・404/403 の例外素通しを追記する。
  - 完了条件: 詳細調査系メソッドが正しい path/params を組み全件取得でき、管理者 API を一切呼ばない。
  - _要件: 4.1, 5.1, 5.2, 6.1, 6.2, 7.1, 8.1, 9.1, 10.1, 10.3, 10.4, 16.5_

## フェーズ B: データモデルの拡張（追加のみ・後方互換）

- [ ] 3. models に A〜D 用のフィールドと新 dataclass を追加する
  - `c2m_export/assessment/models.py` に、既存フィールドの型・名称・順序・意味を変えず、以下を**末尾に既定値付きで追加**する（design §2）。
    - `PageMeta`: `created_by: Optional[str]=None` / `last_updated_by: Optional[str]=None` / `contributors: List[str]=[]` / `owner_unknown: bool=False` / `labels: List[str]=[]` / `comment_count: int=0` / `unresolved_comment_count: Optional[int]=None` / `inline_comment_count: Optional[int]=None` / `footer_comment_count: Optional[int]=None` / `effective_view_restrictions: Optional[RestrictionMeta]=None`。コメント内訳 3 フィールド（unresolved / inline / footer）は取得不能時 None（design §2.1、要件 7.2・7.3）。
    - `AttachmentMeta`: `has_extracted_text: Optional[bool]=None` / `extracted_text_length: Optional[int]=None`。
    - `RawInventory`: `spaces: List[SpaceMeta]=[]` / `history_failed_page_ids` / `label_failed_page_ids` / `comment_failed_page_ids` / `effective_restriction_failed_page_ids` / `extracted_text_failed_refs` / `content_watcher_failed_refs`（コンテンツウォッチャー失敗 = page_id）/ `space_watcher_failed_keys`（スペースウォッチャー失敗 = space_key）/ `space_permission_failed_keys` / `cql_failed: bool=False` / `visibility: Optional[VisibilityMeta]=None` / `environment: Optional[EnvironmentMeta]=None`。ウォッチャー失敗はコンテンツ単位とスペース単位を**別リストに分離**する（design §2.3・§5.4、finding 5）。
  - 新 dataclass を追加する: `SpaceMeta`（`space_key`/`name`/`type`/`status`/`description`/`label_count`/`page_count_preview`/`watcher_count: Optional[int]=None`/`permission_entries: Optional[List[str]]=None`）、`VisibilityMeta`（`username`/`display_name`/`groups`/`visible_space_keys`/`unavailable_apis`）、`EnvironmentMeta`（`access_mode`/`server_version`/`build_number`/`base_url`）。すべて既定値付き。`SpaceMeta.page_count_preview` はスペース配下ページ総数の見積もり（トップレベルページ群の子孫数合計 + トップレベル数。起点ページ 1 つの子孫数ではない。design §2.3、finding 12）。`watcher_count`/`permission_entries` は per-space 詳細調査 ON 時のみ値が入る。
  - 実効閲覧制限は既存 `RestrictionMeta` を再利用する（新しい制限型は作らない）。docstring は日本語で追記する。
  - 完了条件: 既存の `PageMeta`/`AttachmentMeta`/`RawInventory` 生成箇所・既存テストが未修正で通る（後方互換）。新 dataclass が既定値付きで利用可能。
  - _要件: 4.2, 5.3, 7.2, 8.2, 9.3, 10.1, 10.5, 11.1, 12.3, 14.1_

## フェーズ C: 全体把握フェーズの収集（軽量・既定 ON）

- [ ] 4. Collector に全体把握フェーズ収集メソッド `collect_workspace_overview` を追加する
  - `c2m_export/assessment/collector.py` に、DFS 本体（既存 `collect`）を変えずに全体把握収集を行う公開メソッド `collect_workspace_overview(spaces, root_ids) -> None`（`RawInventory` を埋める）を追加する（design §3.2 手順 1・決定 11、finding 6）。収集の起動は run_analysis（タスク 10/11）から行う。
  - **`list_spaces` は run_analysis が 1 回だけ取得した結果を `spaces` 引数で受け取り、本メソッド内で `list_spaces` を再呼び出ししない**（design §3.2・決定 12、finding 4）。
    - 渡された各スペースに対し `get_space` / `get_space_labels` で `SpaceMeta[]` を構築し `RawInventory.spaces` に格納（`label_count` はスペースラベル数＝全体把握で取得、finding 8）。`page_count_preview` は当該スペースのトップレベルページ群（`get_space_root_pages`）に `get_descendant_page_count` を適用した**合計 + トップレベルページ数**とし、`get_descendant_page_count` が全滅した場合のみ `None`（design §2.3、finding 12）。**`get_space_root_pages` 自体が失敗した場合も `page_count_preview=None` とし、該当スペースは欠落扱いで継続する**（`unavailable_apis`／`uncertainties` に反映、design §3.2 手順 1、finding 5）。
    - `get_current_user` / `get_user_memberof` で `VisibilityMeta`（username/display_name/groups/visible_space_keys）を構築し `RawInventory.visibility` に格納。
    - `get_access_mode` / `get_server_information` で `EnvironmentMeta` を構築し `RawInventory.environment` に格納。
  - 各取得失敗は**致命化せず欠落扱い**とし、該当を None/空にして `VisibilityMeta.unavailable_apis` に API 種別を加え、日本語 warning を stderr に出して継続する（design §4・§7）。
  - 既存 assess からの呼び出し互換を壊さないため、全体把握収集は **run_analysis からのみ呼ぶ新メソッドに閉じ込め**、既存 `collect()` の挙動は不変とする。
  - `tests/test_collector_0008.py` を作成し、`ConfluenceClient` をモックして spaces/visibility/environment が `RawInventory` に載ること（`list_spaces` を本メソッドが呼ばず引数の結果を使うこと）、個別取得失敗時に欠落扱いで継続し `unavailable_apis` に記録されること、既存 `collect()` 単独呼び出しが従来どおり動く（回帰）ことを検証する。
  - 完了条件: `collect_workspace_overview` が引数のスペース結果を使って `RawInventory.spaces`/`visibility`/`environment` を埋め、`list_spaces` を再呼び出しせず、失敗は欠落扱いで継続し、既存 `collect()` が不変。
  - _要件: 1.2, 2.1, 2.2, 2.4, 3.1, 5.2, 10.6, 11.1, 11.3, 12.1, 12.2, 12.4, 13.1_

## フェーズ D: 詳細調査フェーズの収集（重量・オプトイン）

- [ ] 5. Collector に詳細調査フェーズ（per-page・per-space）収集フラグとオプトイン収集を追加する
  - `c2m_export/assessment/collector.py` の `Collector.__init__` に、以下を**既定 False で追加**する（既存・0007 の呼び出しは引数を渡さず挙動不変。design §3.1、finding 1）。
    - per-page: `collect_history` / `collect_labels` / `collect_comments` / `collect_watchers` / `collect_effective_restrictions` / `collect_extracted_text`。
    - per-space: `collect_space_permissions`。
    - `collect_watchers` はコンテンツ単位（per-page）とスペース単位（per-space）の**双方を有効化する単一フラグ**とする。
  - **per-page 収集**: `collect()` の各ページ処理内で、対応フラグが真のときだけ per-page API を呼び結果を格納する（design §3.2 手順 2）。
    - `collect_history` → `get_content_history` → `created_by`/`last_updated_by`/`contributors`/`owner_unknown`（作成者・更新者とも取得不能なら True）。失敗は `history_failed_page_ids`。
    - `collect_labels` → `get_labels` → `PageMeta.labels`。失敗は `label_failed_page_ids`。
    - `collect_comments` → `get_comments`（`depth=all` + `expand=extensions.location,extensions.resolution`） → `comment_count`（総数）/ `inline_comment_count`・`footer_comment_count`（各コメントの `extensions.location` で分類）/ `unresolved_comment_count`（`extensions.resolution.status` が resolved でない件数）。ロケーション区分・resolved 判定が取得できない DC バージョンでは該当内訳フィールドを None、総数は可能な限り継続（design §2.1、要件 7.2・7.3）。失敗は `comment_failed_page_ids`。
    - `collect_effective_restrictions` → `get_relevant_view_restrictions` → `effective_view_restrictions`（`RestrictionMeta` に整形）。失敗は `effective_restriction_failed_page_ids`。
    - `collect_extracted_text` → 各添付へ `get_attachment_extracted_text` → `AttachmentMeta.has_extracted_text`/`extracted_text_length`（本文は保持しない）。取得失敗/未対応の添付は `has_extracted_text=None` のまま載せ `extracted_text_failed_refs` に `"page_id:attachmentId"` を記録（design §5.2、finding 9）。
    - `collect_watchers` → `get_content_watchers`（コンテンツ単位。取得失敗は `content_watcher_failed_refs` = page_id）。
  - **per-space 収集**: DFS per-page ループの外で、解決済みスペース集合に対しスペースごとに 1 回ずつ収集する公開メソッド `collect_space_details(space_keys) -> None` を追加する（design §3.2 手順 3・決定 11、finding 1/2）。run_analysis が `collect_space_permissions` または `collect_watchers` が真のときに呼ぶ。
    - `collect_space_permissions` → `get_space_permissions(space_key)` → 対応 `SpaceMeta.permission_entries`（権限エントリ要約。生レスポンス全体は載せない）。失敗/未対応は `space_permission_failed_keys` に `space_key` を追加。
    - `collect_watchers` → `get_space_watchers(space_key)` → 対応 `SpaceMeta.watcher_count`。失敗は `space_watcher_failed_keys` に `space_key` を追加。
    - いずれも致命化せず欠落扱い、`VisibilityMeta.unavailable_apis` と該当失敗リストに記録して継続する（要件 10.2, 10.5, 13.3）。
  - 各 per-page 取得失敗は**そのページ全体をスキップせず**、該当情報のみ欠落として `RawInventory` の対応 `*_failed_*` に集計し、日本語 warning を stderr に出して継続する（design §7、要件 13.3/13.5）。
  - `tests/test_collector_0008.py` に、各 per-page `collect_*` 既定 False で既存挙動不変、True 時に対応フィールドが埋まること、per-page 失敗時にページ全体を落とさず該当 `*_failed_*` に集計して継続すること、`collect_space_details` が `collect_space_permissions`/`collect_watchers` ON 時にスペースごとに 1 回ずつ `get_space_permissions`/`get_space_watchers` を呼び `SpaceMeta.permission_entries`/`watcher_count` を埋め、失敗時に `space_permission_failed_keys`/`space_watcher_failed_keys` に記録して継続すること、コンテンツウォッチャー失敗（`content_watcher_failed_refs`）とスペースウォッチャー失敗（`space_watcher_failed_keys`）が別リストに分離されることを追記する。
  - 完了条件: per-page フラグが既定 OFF で既存不変・ON 時のみ per-page 収集し、per-space 収集 `collect_space_details` がスペース単位で 1 回ずつ呼ばれ、個別失敗は部分欠落として件数化され継続する。
  - _要件: 1.2, 1.3, 1.4, 1.5, 4.1, 4.2, 4.3, 4.4, 5.1, 5.3, 5.4, 7.1, 7.2, 7.3, 8.1, 8.2, 8.3, 8.4, 9.1, 9.3, 9.4, 10.1, 10.2, 10.3, 10.4, 10.5, 13.1, 13.3, 13.5_

## フェーズ E: 抽出純粋関数（workspace / provenance）

- [ ] 6. 全体把握系の集約純粋関数（workspace）を実装する
  - `c2m_export/analysis/workspace.py` を新規作成する。API 非依存の純粋関数群として実装する（API モック不要で単体テスト可能）。
  - `summarize_spaces(spaces: List[SpaceMeta]) -> dict`: `spaces` を整形し `space_count` / `global_space_count` / `personal_space_count` / `archived_space_count` と各 `SpaceMeta` の提示用レコードを返す（design §5.1）。
  - `build_visibility(visibility: Optional[VisibilityMeta], inventory: RawInventory) -> dict`（2 引数。`uncertainties` は別引数で受け取らない。finding 7）: `username`/`display_name`/`groups`/`visible_space_keys` に加え、`inventory` の各 `*_failed_*`（`content_watcher_failed_refs`/`space_watcher_failed_keys` を 1 つの `watchers` に集約）/`cql_failed`/`visibility.unavailable_apis` から `unavailable_apis[]` を導出し（導出表は design §7）、定型日本語 `note`（design §5.1 の注記文）を常時付与する（要件 11.2/11.3）。
  - `build_environment(environment: Optional[EnvironmentMeta]) -> dict`: `access_mode`/`server_version`/`build_number` を整形（`base_url` は非機微だが environment 出力には含めない方針＝design §5.1 の `environment` ブロックに合わせる）。
  - いずれもソート/件数制限はしない（提示用の整形のみ。ページネーションは run_analysis の責務）。
  - `tests/test_analysis_workspace.py` を作成し、種別/状態カウント、`unavailable_apis` 導出、`note` 付与、環境整形を固定入力で検証する。
  - 完了条件: workspace 集約が design §5.1 の `workspace`/`visibility`/`environment` ブロックの素データを純粋に生成する。
  - _要件: 2.5, 3.4, 11.1, 11.2, 11.3, 12.3, 14.4_

- [ ] 7. 来歴・分類・制限の集約純粋関数（provenance）を実装する
  - `c2m_export/analysis/provenance.py` を新規作成する。API 非依存の純粋関数群として実装する。0007 の責務境界（純粋関数は全件レコード列へ追加キーを合成するだけ、sort/limit/truncated/counts/items 組み立ては run_analysis）を踏襲する（design §5.2）。
  - `enrich_stale(stale_records, inventory) -> list`: 0007 の `extract_stale_pages` が返す全件レコードに `last_updated_by`/`created_by`/`owner_unknown` を合成する（UC2）。
  - `enrich_restricted(restricted_records, inventory, base_url) -> list`: 0007 の `extract_restricted_pages` の全件レコードに `effective_read_users[]`/`effective_read_groups[]`/`effective_restriction_present` を合成する（UC3、実効制限は byOperation と別キー）。
  - `enrich_empty_with_attachments(empty_records, inventory) -> list`: 0007 の `extract_empty_with_attachments` の全件レコードに `attachments_extracted_text[]`（`{filename, has_extracted_text, extracted_text_length}`）を合成する（UC5）。
  - （任意）`extract_owner_unknown_pages(inventory) -> list`: オーナー不明ページの全件レコード（独立 UC 化する場合のみ。design §5.3 の推奨。既定は UC2 への `owner_unknown` 付与で代替）。
  - いずれもソート/件数制限はしない。
  - `tests/test_analysis_provenance.py` を作成し、来歴付与・`owner_unknown` 判定、実効制限併記（byOperation と別キー）、抽出テキスト有無/長さ付与、いずれも全件にキー合成するだけでソート/制限しないことを固定入力で検証する。
  - 完了条件: enrich 系が 0007 抽出レコードに 0008 のキーを合成するだけの純粋関数として動く。
  - _要件: 4.2, 4.3, 8.2, 9.2, 9.3, 14.4_

## フェーズ F: 0007 スキーマ拡張（追加のみ・schema_version 1.1）

- [ ] 8. AnalysisResponse に新ブロック・新 uncertainties キーを追加し schema_version を更新する
  - `c2m_export/analysis/response.py` を拡張する（追加のみ、既存トップレベル構造・既存キー不変）。
  - トップレベルに新ブロックを追加する（design §5.1）: `workspace`（spaces[各 space に `label_count`/`page_count_preview`/`watcher_count`/`permission_entries` を含む]/各種 space_count）/ `visibility`（username/display_name/groups/visible_space_keys/unavailable_apis/note）/ `environment`（access_mode/server_version/build_number）。新オプション未指定時は空/省略を許容。
  - 既存 UC ブロックの detail `items[]` に追加フィールドを許容する（design §5.2）: UC2 に `last_updated_by`/`created_by`/`owner_unknown`、UC3 に `effective_read_users[]`/`effective_read_groups[]`/`effective_restriction_present`、UC5 に `attachments_extracted_text[]`（`has_extracted_text` は未取得時 `null`、中身なし時 `false`、finding 9）、UC5 のページ items にコメント内訳 `comment_count`/`unresolved_comment_count`/`inline_comment_count`/`footer_comment_count`（取得不能な内訳は `null`、要件 7.2・7.3）を許容する。コメント収集が無効または未取得のページは既定値（`comment_count=0`、内訳 `null`）で出力する。
  - `uncertainties` に新キーを追加する（design §5.4、finding 5）: `history_failed_count`/`label_failed_count`/`comment_failed_count`/`effective_restriction_failed_count`/`extracted_text_failed_count`/`content_watcher_failed_count`/`space_watcher_failed_count`/`space_permission_failed_count`/`cql_failed`/`unavailable_apis[]`。すべて既定値（0/false/空）。各 `*_failed_count` は対応する `RawInventory` のリスト長から導出する（`content_watcher_failed_count=len(content_watcher_failed_refs)`、`space_watcher_failed_count=len(space_watcher_failed_keys)` のようにコンテンツ/スペースは分離し合算しない。導出表は design §5.4）。
  - `schema_version` を `"1.0"` → `"1.1"`（キー追加＝後方互換なマイナー、0007 確定事項 3）。冒頭コメントに「0008 のフィールド追加はマイナー更新。削除・リネーム・意味変更はしない」旨を日本語で明記する。
  - トークンを保持するフィールドを一切持たせない（0007 一次防御を維持）。
  - `tests/test_analysis_response_0008.py` を作成し、新ブロック・新 uncertainties キーの `to_dict` 構造、`schema_version=="1.1"`、0007 既存キーが不変（回帰）、トークン保持フィールドが無いことを検証する。
  - 完了条件: 新ブロック/キーが追加され `schema_version` が 1.1 になり、0007 既存キーが不変でトークンを保持できる構造が無い。
  - _要件: 2.5, 4.2, 8.2, 9.2, 9.3, 11.1, 12.3, 14.1, 14.2_

## フェーズ G: 共通 1 層と CLI/設定の拡張

- [ ] 9. AnalysisConfig / AnalysisParams に 0008 オプションを追加する
  - `c2m_export/config.py` の `AnalysisConfig`（0007 で新設済み）と `c2m_export/analysis/params.py` の `AnalysisParams` を**拡張（追加のみ）**する。新設の独立 Config は作らない（design §6、要件 15.1）。
  - 追加パラメータ（design §6.1）: `all_spaces: bool=False` / `cql: Optional[str]=None` / `deep: bool=False` / `collect_history`/`collect_labels`/`collect_comments`/`collect_watchers`/`collect_effective_restrictions`/`collect_extracted_text`/`collect_space_permissions`（各 3 値 `Optional[bool]=None`）。
  - 命名は既存 `AssessConfig`/0007 の規約（単数形・3 値フラグの `default=None`/`store_false`）に揃える。
  - `validate()`: 空文字のみの `cql` は `INVALID_PARAM`、`all_spaces` と既存起点の併用は許容（design §6.2）。実機依存 API フラグの有効化は `INVALID_PARAM` にしない。既定（未指定）で全体把握のみ＝軽量（要件 15.5）。既存 0007 のバリデーション（`limit>=1`・`restricted`×`--no-restrictions` 等）は不変。
  - 優先順位（CLI > env > YAML > デフォルト）とトークン環境変数（`C2M_CONFLUENCE_TOKEN`/`CONFLUENCE_TOKEN`）運用を踏襲する（要件 15.4）。
  - `tests/test_analysis_config_0008.py` を作成し、新オプションの優先順位、既定が軽量・無効、空 CQL の `INVALID_PARAM`、既存 Config 挙動不変（回帰）を検証する。
  - 完了条件: 新オプションが優先順位どおり解決され、既定が軽量、空 CQL がエラー、既存 Config 不変。
  - _要件: 1.1, 1.3, 6.3, 15.1, 15.3, 15.4, 15.5_

- [ ] 10. 共通 1 層 run_analysis / _resolve_roots に起点供給と収集フェーズ制御を追加する
  - `c2m_export/analysis/api.py` の `run_analysis` と `_resolve_roots`（0007 で新規実装済み）を**拡張（追加のみ）**する。0007 の処理手順・責務境界・ページネーション（`_paginate`）・例外分類は不変。
  - **`list_spaces` を run_analysis で 1 回だけ取得**し、その結果を `_resolve_roots`（`all_spaces` 起点供給）と `collect_workspace_overview`（タスク 4）の双方へ渡して共有する（design §3.2・§4・決定 12、finding 4）。`_resolve_roots` / `collect_workspace_overview` 内で `list_spaces` を再呼び出ししない。
  - `_resolve_roots` に供給源を追加する（design §4、0007 将来拡張 1）: `params.all_spaces` 真なら共有済み `list_spaces` 結果の各スペースの `get_space_root_pages`（既存）で ID 供給、`params.cql` 指定時は `search_cql` の結果 ID 供給。全起点（`root_page_ids`+`space_keys`+`all_spaces`+`cql`）が空のときのみ `TargetNotFoundError`→`TARGET_NOT_FOUND`/4。一部スペース 0 件は `uncertainties.empty_space_keys`、CQL 拒否は `cql_failed=True` で継続（要件 6.4, 11.4）。
  - `--deep` と個別 3 値フラグの合成規則（design §6.1）を `AnalysisParams` 構築時に一括解決する: 個別フラグ明示を最優先、未指定は `deep` 値、`deep` 未指定は全 False。解決済みフラグ（`collect_space_permissions` 含む）を `Collector(collect_history=..., collect_space_permissions=..., ...)` へ渡す。
  - 全体把握フェーズ収集（タスク 4 の `collect_workspace_overview`）を `collect()` 前に実行し `RawInventory` を埋める。per-space 詳細調査が有効（`collect_space_permissions` または `collect_watchers` が真）なら、解決済みスペース集合を渡して `collect_space_details(space_keys)`（タスク 5）を per-page DFS の外で実行する。実機依存 API の 403/空/未対応は**致命化せず欠落扱い**（起点解決中の 401/403/404 のみ致命）とする（design §4・§7、要件 13.3）。
  - `AnalysisResponse` 構築時に、`workspace.summarize_spaces` / `workspace.build_visibility` / `workspace.build_environment` の結果を新ブロックへ、`provenance.enrich_*` の結果を既存 UC の `items[]` に合成する（sort/limit は従来どおり `_paginate`）。`uncertainties` に新 `*_failed_count`/`unavailable_apis` を集約する。`schema_version` は response 側で 1.1。
  - トークン非混入（0007 サニタイズ一次防御＝response にトークンフィールド無し）を維持する。
  - `tests/test_analysis_api_0008.py` を作成し、`all_spaces`/`cql` 供給と全起点空でのみ `TARGET_NOT_FOUND`、CQL 拒否で `cql_failed` 継続、実機依存 API 失敗が欠落扱い（致命化しない）、新ブロック・`schema_version==1.1`・既存 UC への追加フィールド、`--deep`×個別フラグ合成、トークン非混入を `ConfluenceClient` モックで検証する。
  - 完了条件: 起点供給が `_resolve_roots` に閉じて下流無改変、収集フェーズ/情報オン・オフが制御され、新情報が `AnalysisResponse` に後方互換で載り、実機依存 API 失敗が欠落扱いになる。
  - _要件: 1.1, 1.2, 1.3, 1.4, 1.5, 2.3, 2.5, 3.4, 4.2, 6.1, 6.4, 8.2, 9.2, 9.3, 10.1, 10.2, 10.4, 11.1, 11.3, 11.4, 12.3, 13.1, 13.2, 13.3, 14.3_

- [ ] 11. analyze.py に 0008 の CLI 引数を追加する
  - `c2m_export/analyze.py`（0007 の専用エントリーポイント）に §6.1 の引数を**追加**する（design §6.3）: `--all-spaces` / `--cql` / `--deep` / `--collect-history`・`--no-collect-history` / `--collect-labels`・`--no-...` / `--collect-comments`・`--no-...` / `--collect-watchers`・`--no-...` / `--collect-effective-restrictions`・`--no-...` / `--collect-extracted-text`・`--no-...` / `--collect-space-permissions`・`--no-...`。各 `--collect-*` は `default=None`/`store_false` の 3 値。
  - 実機依存 API のフラグには「取得可否は実機依存（権限/インスタンス設定/添付種別により取得できない場合がある）」旨をヘルプ文に日本語で明記する。
  - stdout は JSON 単独、ログは stderr、終了コード規約・サニタイズ（出力文字列全体に 1 回）・非対話・冪等（読み取り専用）はすべて 0007 を踏襲する。新 API も読み取り専用で冪等。
  - `tests/test_analyze_cli_0008.py` を作成し、新引数が `AnalysisParams`/`AnalysisConfig` に反映されること、`capsys` で stdout が JSON 単独（新ブロック含む）・ログが stderr、起点非存在時に `TARGET_NOT_FOUND`/終了コード 4 を検証する。
  - 完了条件: 新引数が解析され設定に反映され、stdout が純粋 JSON・ログが stderr、既定（新引数なし）で 0007 と実質同一出力（`schema_version` 以外）になる。
  - _要件: 1.1, 1.3, 6.3, 8.4, 9.1, 15.2, 15.3, 16.1, 16.2_

## フェーズ H: Skill / MCP の記述更新

- [ ] 12. SKILL.md 正本と複製、MCP サーバ記述を 0008 に合わせて更新する
  - 正本 `skills/confluence-analysis/SKILL.md` を更新し、2 段収集（全体把握＝既定/詳細調査＝オプトイン）、新オプション（`--all-spaces`/`--cql`/`--deep`/各 `--collect-*`）、新出力ブロック（`workspace`/`visibility`/`environment`）と既存 UC への追加フィールド、`schema_version` が `1.1`（キー追加＝後方互換）になった旨、取得可否が実機依存の情報がある旨を記述する。トークン値は書かず環境変数運用を維持する。
  - 同一内容を `.github/skills/confluence-analysis/SKILL.md` と `.kiro/skills/confluence-analysis/SKILL.md`（+ `scripts/`）へ複製する（0007 の 3 箇所同期運用を踏襲、正本を編集し複製）。
  - `c2m_export/mcp_server.py` のツール説明（docstring / description）に 0008 の新オプションと新出力ブロックを追記する。枠組み（FastMCP・stdio・遅延 import・`run_analysis` を呼ぶだけ）は不変。`requirements-mcp.txt` は変更しない（新 SDK 不要）。
  - `tests/test_mcp_server.py`（0007）があれば、0008 オプションを渡しても `run_analysis` モックに正しく伝わることを追記検証する（SDK 未導入時はスキップマーカー）。
  - 完了条件: 3 箇所の SKILL.md が一致し 0008 の新機能を説明し、MCP ツール説明が更新され、トークン値を含まない。
  - _要件: 14.5, 15.2, 16.3_

## フェーズ I: ドキュメント・設定サンプル・steering

- [ ] 13. README / README_DEV / 設定サンプル / steering を更新する
  - `c2m_config_sample.yaml` の分析（analysis）セクションに 0008 の新設キー（`all_spaces`/`cql`/`deep`/各 `collect_*`）のサンプルとコメントを**追記**する（既存記述は保持）。
  - `README.md` に、2 段収集（全体把握＝軽量・既定/詳細調査＝重量・オプトイン。per-page と per-space の別も）、新オプション、新出力ブロック（`workspace`/`visibility`/`environment`）、取得可否が実機依存である旨、ワークスペースレベル把握（`--all-spaces`）/CQL 起点の使い方を追記し、推奨ワークフロー（分析 → ルール決定 → エクスポート）の「分析」段を精緻化する位置づけを記す（要件 1.6）。
  - `README_DEV.md` に、0008 のアーキテクチャ（2 段収集・`ConfluenceClient` 追加メソッド一覧・`workspace.py`/`provenance.py` の責務・`_resolve_roots` への起点供給追加・`schema_version` 1.1・実機依存 API の欠落扱い）と、0007 将来拡張 3 点への対応を追記する。
  - `.kiro/steering/product.md` にワークスペースレベル把握・移設課題抽出・2 段収集・新 API 収集を主な機能として追記する。
  - `.kiro/steering/tech.md` に `python -m c2m_export.analyze` の 0008 新オプション、取得する REST API 群（A〜D）を追記する。
  - `.kiro/steering/structure.md` に新規 `c2m_export/analysis/workspace.py` / `provenance.py` と対応テスト、`confluence.py`/`models.py`/`collector.py`/`api.py`/`response.py`/`config.py`/`params.py`/`analyze.py` への 0008 拡張点を追記する。
  - 完了条件: AGENTS.md の README 保守ルールに従い、README/README_DEV/設定サンプル/steering が 0008 の 2 段収集・新 API・新キー・新ブロックを反映している。
  - _要件: 1.6, 15.4, 16.4_

## フェーズ J: 後方互換・認証安全性・全体検証

- [ ] 14. 後方互換・非破壊を検証する
  - `c2m_export/assessment/models.py`・`collector.py`・`analysis/*`・`config.py` への追加がすべて既定値付き・追加のみで、既存生成箇所・既存呼び出しを変えていないことをテストで確認する。
  - 既存 CLI（結合 `cli.py` / assess `assess.py` / fsexport / permexport）および 0007 の分析モードの挙動・引数・出力フォーマットが不変であることを、既存テストスイート全通過（0001〜0007 分）で確認する。
  - `tests/test_0008_backward_compat.py` を作成し、`Collector`（0008 フラグ未指定）が従来どおり動くこと、新オプション未指定の `run_analysis` が 0007 と実質同一出力（`schema_version` 以外・新ブロックは空/省略）であることを検証する。
  - 完了条件: 既存テストが全て未修正で通り、新オプション未指定時の挙動が 0007 と同等であることが示される。
  - _要件: 14.1, 14.2, 14.3_

- [ ] 15. 認証情報の非漏洩を検証する
  - `tests/test_0008_token_leak.py` を作成し、ダミートークンを CLI 引数/環境変数で与えた実行で、0008 の新 API 経路（spaces/visibility/environment/history/labels/comments/watchers/effective-restrictions/extracted-text/cql）でも stdout JSON・`ErrorObject`・stderr ログにトークンが現れないことを `capsys` で検証する。
  - 新 API のエラー経路（403/空/未対応・CQL 拒否）で例外メッセージにトークンが混入しないこと（0007 `sanitize_text` 二次防御と ErrorObject 分類が機能すること）を検証する。
  - `visibility`/`environment` に `base_url` 等の非機微情報は載るがトークンは載らないことを確認する。
  - 完了条件: 正常・異常・実機依存欠落いずれの経路でもトークンが出力に出ないことがテストで担保される。
  - _要件: 13.3, 16.3_

- [ ] 16. 全体の検証と品質チェックを行う
  - `$env:PYTHONPATH="."; python -m pytest` で全テストを実行し、既存テスト（0001〜0007）が壊れていないこと（後方互換）と 0008 の新規テストが通ることを確認する。MCP テストは SDK 未導入時スキップマーカーで扱う。
  - `mypy` で型検査を通す（Python 3.8 互換の型注釈、新 dataclass・新メソッド含む）。
  - `pre-commit run --all-files` でフォーマット・YAML チェック・末尾空白・EOF・大容量ファイル検査を通す。
  - 一時ファイルを残さない。
  - 完了条件: pytest / mypy / pre-commit がすべて通過する。
  - _要件: 14.1, 14.4, 16.4_
