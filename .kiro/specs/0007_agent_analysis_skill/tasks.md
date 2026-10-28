# Implementation Plan

本計画は、Confluence 内のワークスペース状況をエージェント（GitHub Copilot / Kiro / 汎用 Agent Skills / MCP）から把握・分析できる Skill と、それを支える CLI 改善を実装するためのものである。design.md の「Skill 形態 → 共通 JSON インターフェース層 → 既存 assess ロジック」構成に従い、下から積み上げる順序で進める。

実装順序の方針（依存順）:

1. 設定・環境変数・秘匿情報サニタイズ（全体の土台、認証安全性）
2. 共通 CLI / JSON インターフェース層のデータモデル（params / response）
3. 純粋ロジック（抽出 / 圧縮カテゴリ集約 / マクロ統計）
4. マクロ収集のための collector / models 拡張（追加のみ・後方互換）
5. 共通 1 層 `analysis_api.run_analysis` と CLI エントリーポイント `analyze.py`
6. ローカル Skill（GitHub Copilot / Kiro）
7. 汎用 Agent Skills 形式
8. MCP サーバ
9. ドキュメント・steering・設定サンプル更新
10. 後方互換・非破壊検証、認証情報の非漏洩検証、全体品質チェック

純粋関数（extractors / categories / macros / sanitize）を先に厚くテストし、I/O（collector / client / CLI）は `requests` モック・`capsys` で薄く検証する。すべてのコメント・docstring・ログは日本語（PEP 257 準拠）で記述する。Python 3.8 互換の型注釈（`typing.List/Dict/Set/Optional`）を用いる。テスト実行は `$env:PYTHONPATH="."; python -m pytest`（PowerShell）とする。

本計画の各タスクは「spec を書く」ものではなく「コードを実装する」タスクである。各タスクは対象ファイルのリポジトリ相対パスと、完了条件（受け入れ基準への紐付け `_要件: N.M_`）を持つ。

---

## フェーズ A: 設定・認証・秘匿情報の土台

- [ ] 1. トークンの環境変数読取を既存 Config に追加する（追加のみ・後方互換）
  - `c2m_export/config.py` の各 Config クラス（`Config` / `AssessConfig` / `FsExportConfig` / `PermissionExportConfig`）の `load()` に、トークンの環境変数読取を追加する。
  - 優先順位は `CLI --token` > 環境変数（`C2M_CONFLUENCE_TOKEN` → `CONFLUENCE_TOKEN` の順で参照）> YAML `token` > なし、とする（design §7）。
  - 既存の `HTTPS_PROXY` / `HTTP_PROXY` 読取、既存キー・既存優先順位・既存メッセージは一切変更しない（追加のみ）。
  - 既存 `AssessConfig` 等の属性命名ゆれを増やさない（例: 既存の単数形 `report_format` に揃える）。
  - docstring・コメントは日本語。トークン値はログに出さない。
  - 完了条件: CLI / env(`C2M_CONFLUENCE_TOKEN` → `CONFLUENCE_TOKEN`) / YAML の優先順位でトークンが解決され、Proxy の既存 env 読取が不変であること。
  - _要件: 11.4, 13.1, 13.5_

- [ ] 2. 秘匿情報サニタイズ関数を実装する（純粋ロジック）
  - `c2m_export/analysis/__init__.py` を新規作成する。
  - `c2m_export/analysis/sanitize.py` を新規作成し、`sanitize_text(text: str, secrets: Iterable[str]) -> str` を実装する。
  - 置換は 2 系統を適用する（design §7 の多層防御 2 段目）: (1) `secrets` に含まれるトークン実値の完全一致を `***REDACTED***` に置換、(2) 正規表現 `Bearer\s+\S+` および `Authorization` ヘッダ値をマスクする。
  - **no-op 条件**: `secrets` 要素が `None` または空文字の場合は置換を行わない（空文字での全文置換事故を防ぐ）。`secrets` が空なら完全一致置換は no-op（正規表現マスクは常に適用してよい）。
  - stdout / stderr へ出力する直前、`json.dumps` 後の**出力文字列全体に対して 1 回だけ**適用する想定で設計する（各フィールド個別ではない）。docstring は日本語。
  - `tests/test_analysis_sanitize.py` を作成し、トークン実値が `***REDACTED***` に置換されること、`Bearer <...>` / `Authorization` 値がマスクされること、空トークン集合・空文字トークンでは全文が無変更（no-op）であることを検証する。
  - 完了条件: `sanitize_text` がトークンと Bearer ヘッダを確実にマスクし、空 secrets では全文が不変。
  - _要件: 13.3, 13.4, 14.6_

- [ ] 3. 分析用設定（AnalysisConfig）を実装する
  - `c2m_export/config.py` に `AnalysisConfig` を追加する（既存 Config クラスは不変）。
  - 共通骨格（YAML → env → CLI の優先順位、`base_url` の `rstrip("/")` 正規化、proxy の env 取り込み、タスク 1 のトークン env 読取）を踏襲する。
  - 固有キー: `usecases` / `mode` / `limit`(1000) / `stale_days`(365) / `min_body_bytes`(200) / `archive_extensions` / `analyze_restrictions`(既定 None の 3 値動作)。`--stale-years` を受理し内部で `×365` 換算する。
  - `--restrictions`（`default=None`）/ `--no-restrictions`（`store_false`）は既存 `AssessConfig` と同一の 3 値動作に揃える。属性命名は既存に合わせ単数形で統一する（design §2）。
  - `validate()`: `base_url`・`token` 必須、`root_page_ids` と `space_keys` の少なくとも一方が必須。不正時は後続（タスク 11）の `INVALID_PARAM` に落とせるよう例外送出（`sys.exit` しない）。
  - **矛盾チェック（design §6.1）**: `usecases` に `restricted` が含まれ、かつ `analyze_restrictions` が明示的に `False`（`--no-restrictions`）の場合は `INVALID_PARAM` とし、日本語（現象/原因/対処）で「`restricted` の分析には権限収集が必要です。`--no-restrictions` を外すか `--usecase` から `restricted` を除外してください」と案内する。`analyze_restrictions` が未指定（`None`）のときはエラーにせず既定（`True`）を尊重する。
  - `tests/test_analysis_config.py` を作成し、トークンの `CLI > env(C2M_CONFLUENCE_TOKEN → CONFLUENCE_TOKEN) > YAML` 優先順位、`base_url` rstrip、`--stale-years` の年→日換算、既定値、必須チェック、`restricted` × `--no-restrictions` の `INVALID_PARAM`、既存 Config 挙動の不変（回帰）を検証する。
  - 完了条件: 優先順位・正規化・年換算・必須チェック・矛盾チェックがテストで確認でき、既存 Config の挙動が不変。
  - _要件: 2.4, 4.2, 5.3, 5.4, 6.4, 11.4, 11.5, 13.1_

## フェーズ B: 共通 JSON インターフェース層のデータモデル

- [ ] 4. 入力パラメータモデル（AnalysisParams）を実装する
  - `c2m_export/analysis/params.py` を新規作成し、`AnalysisParams` を `dataclass` で定義する（design §2 の表、§2.1 の受理値表）。
  - フィールド: `usecases: List[str]`（既定 全 6 種 `risk`/`stale`/`restricted`/`archives`/`empty_with_attachments`/`macros`）/ `mode: str`（既定 `"summary"`）/ `limit: int`(1000) / `stale_days: int`(365) / `min_body_bytes: int`(200) / `archive_extensions: Set[str]` / `analyze_restrictions: Optional[bool]` / `sort: Optional[str]`（未指定時は UC 別既定）。
  - `--usecase` 受理値・内部キー・UC 番号・既定 sort の対応は design §2.1 の表を唯一の正とする（`risk`→`risk_count` 降順 / `stale`→`days_since_modified` 降順 / `restricted`→`page_id` 昇順 / `archives`→集約で sort 無視 / `empty_with_attachments`→`attachment_count` 降順 / `macros`→集約で sort 無視）。`empty_with_attachments` の綴りを取り違えない。
  - `validate()` の境界規則（違反はすべて `INVALID_PARAM` / 終了コード 2、design §2）:
    - `usecases`: 許可集合のみ。未知値を含むとエラー。未指定時は全 6 種を既定実行するが、`--usecase` を**明示的に空集合**で指定した場合はエラー。
    - `mode`: `summary` / `detail` の 2 値のみ。
    - `limit`: 整数かつ `>= 1`（0 以下・非整数はエラー）。
    - `stale_days`: 整数かつ `>= 0`。`--stale-years` 指定時は `stale_days = years * 365`（閏年非考慮の単純近似、`years >= 0`）で換算し、`--stale-days` と `--stale-years` の両方指定時は `--stale-days` を優先する。
    - `min_body_bytes`: 整数かつ `>= 0`。
    - `archive_extensions`: 空集合を許容（空なら UC4 は 0 件で正常）。各要素は小文字・ドット無しに正規化する。
    - `analyze_restrictions`: 3 値（`None` / `True` / `False`）。`restricted` × `--no-restrictions` の矛盾チェックはタスク 3 の `AnalysisConfig.validate()`（design §6.1）で行う。
  - docstring は日本語。
  - `tests/test_analysis_params.py` を作成し、既定値・未知 usecase 拒否・明示的空 usecase 拒否・不正 mode 拒否・`limit<1` / `stale_days<0` / `min_body_bytes<0` 拒否・空 archive 許容・`--stale-days` と `--stale-years` 両指定時の `--stale-days` 優先・既定 sort の UC 対応を検証する。
  - 完了条件: design §2 の境界規則と §2.1 の受理値・既定 sort 対応がテストで担保される。
  - _要件: 2.1, 2.2, 2.4, 4.2_

- [ ] 5. 出力スキーマモデル（AnalysisResponse / ErrorObject）を実装する
  - `c2m_export/analysis/response.py` を新規作成し、冒頭コメントに JSON スキーマ定義（design §3.1〜3.3）を日本語で記載する。
  - `AnalysisResponse` を `dataclass` で定義する。トップレベル: `schema_version`（例 `"1.0"`）/ `status`（`ok`/`error`）/ `generated_at`（UTC ISO8601）/ `mode` / `scope`（`root_page_ids`/`space_keys`/`resolved_root_count`、トークンは含めない）/ `summary`（既存 `generate_json_report.summary` と同一キー）/ `usecases` / `uncertainties` / `error`。
  - `summary.level_distribution` は内部では `Dict[int, int]`（`analyzers.py`）だが `json.dumps` でキーが文字列化される（例 `{"1": 10}`）。これは既存 `generate_json_report` と同一の JSON 表現であり、`schema_version` が保証する安定対象に「文字列化されたキー」の JSON 表現を含める旨を冒頭コメントに明記する。dataclass では `Dict[str, int]` 相当として扱う。
  - `uncertainties` に既存 + 新規キーを持たせる: `skipped_page_ids` / `skipped_attachment_refs` / `restriction_failed_page_ids` / `size_meta_missing_count` / `macro_parse_failed_count` / `empty_space_keys`（トップレベルページ 0 件だった Space キー）/ `restrictions_disabled`（UC3 要求時に権限収集が無効だった真偽）。
  - UC2（`stale`）の `counts` は `stale_page_count` / `stale_threshold_days`（実効しきい値 = 換算後日数）/ `freshness_distribution` を持たせる。
  - `ErrorObject` を `dataclass` で定義する: `code` / `message`（日本語・現象/原因/対処、トークン非混入）/ `detail`（例外クラス名等の非機微情報）。エラーコード値 `INVALID_PARAM` / `AUTH_FAILED` / `TARGET_NOT_FOUND` / `API_ERROR` / `INTERNAL_ERROR` を定数として定義する。
  - サイズ系キーは `counts` / `items[]` の双方で `total_size_bytes` / `max_size_bytes`（バイト整数）に統一する。
  - 構造的にトークンを保持するフィールドを一切持たせない（一次防御、design §7）。
  - `dataclass` → dict へ変換するヘルパ（`to_dict`）を用意し、`None` の `error` 等は省略できるようにする。
  - `tests/test_analysis_response.py` を作成し、`schema_version` の付与、`to_dict` のキー構造（summary が既存 JSON の summary キーと一致）、`level_distribution` が文字列キーで出ること、`uncertainties` の新規キー、トークン用フィールドが存在しないことを検証する。
  - 完了条件: スキーマが design §3 と一致し、`level_distribution` の文字列キー表現と新規 `uncertainties` キーを持ち、トークンを保持できる構造が存在しない。
  - _要件: 1.3, 1.5, 10.1_

## フェーズ C: 純粋ロジック（抽出 / 圧縮カテゴリ / マクロ統計）

- [ ] 6. 個別一覧抽出の純粋関数を実装する（UC1/UC2/UC3/UC5）
  - `c2m_export/analysis/extractors.py` を新規作成する。API 非依存の純粋関数群として実装する。
  - **責務境界（design §1）**: 各関数は該当 UC の **全件レコード列**を返すだけとし、`sort` / `limit` の適用・`truncated` / `total_count` の算出・`counts`/`items` ブロックの組み立ては**行わない**（それらはタスク 11 の `run_analysis` / `_paginate` が担う）。
  - `extract_risk_pages(result, base_url)`（UC1）: `AssessmentResult.risk_items` を `page_id` でグルーピングし、`{page_id, title, url, risk_types[], risk_count, reasons[]}` の全件を返す。`title` は `raw_inventory.pages` の `page_id→title` 辞書で確定（無い場合は空文字 + `uncertainties` 報告）。`risk_types[]` は重複排除（値域は `PATH_LENGTH`/`INVALID_CHAR`/`BLOCKED_EXT`/`LARGE_FILE`/`DUPLICATE_NAME` の 5 種、`RESERVED_NAME` は現れない）。`reasons[]` は添付名を含む `reason` を保持。`url` は `base_url` を引数で受け取り page_id ベースで構築する。ソートはしない。
  - `extract_stale_pages(inventory, stale_days, reference_time)`（UC2）: 各 `PageMeta` について `analyzers.parse_iso_datetime(last_modified)` を再利用して日時をパースする。**tz 正規化（必須。最終整合レビュー HIGH 指摘）**: `parse_iso_datetime` は tz 無し文字列に naive な `datetime` を返すため、`analyze_inventory` と同一手順で `if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)` を適用してから `reference_time`（aware/UTC）と減算する（省くと aware×naive の `TypeError` で落ち、件数整合も壊れる）。`days_since_modified = (reference_time - dt).days >= stale_days` のページのみ `{page_id, title, last_modified, days_since_modified}` の全件を返す。`last_modified` が None またはパース失敗のページは一覧に含めない。URL を持たないため `base_url` は受け取らない。ソートはしない。`analyze_inventory` の判定式と同一であることで `stale_page_count` と detail 件数の一致を保証する。
  - `extract_restricted_pages(inventory, base_url)`（UC3）: `PageMeta.restriction.has_explicit=True` でフィルタし、`update_*` を `readwrite_*` にマッピングして `{page_id, title, url, read_users[], read_groups[], readwrite_users[], readwrite_groups[]}` の全件を返す。`url` は `base_url` から page_id ベースで構築。ソートはしない。
  - `extract_empty_with_attachments(inventory, min_body_bytes)`（UC5）: `len(attachments) > 0 かつ body_bytes < min_body_bytes` に合致するページを `{page_id, title, attachment_count, body_bytes}` の全件で返す。ソートはしない。
  - `tests/test_analysis_extractors.py` を作成し、固定 `RawInventory` 入力で UC1 のページ集約（`risk_count`・`risk_types` 重複排除）、UC2 の `last_modified=None`/パース失敗の「不明」除外・`reference_time` 共有・**naive な `last_modified`（tz 無し文字列）でも tz 正規化により `TypeError` を起こさず `days_since_modified` を算出できること**、UC3 の `readwrite` マッピング、UC5 の交差条件、いずれもソート/件数制限をしていないこと（全件返却）を検証する（API モック不要）。
  - 完了条件: 4 抽出関数が全件レコード列を返し（sort/limit 非適用）、UC2 の「不明」除外が担保される。
  - _要件: 2.3, 2.5, 3.1, 3.2, 4.1, 4.4, 5.1, 5.2, 7.1, 7.2, 7.4, 14.6_

- [ ] 7. 圧縮カテゴリ集約の純粋関数を実装する（UC4）
  - `c2m_export/analysis/categories.py` を新規作成する。
  - `DEFAULT_ARCHIVE_EXTENSIONS`（例: `zip`/`7z`/`rar`/`gz`/`tar`/`bz2`/`xz` 等、小文字・ドット無し）を定数定義する。
  - `DEFAULT_ARCHIVE_EXTENSIONS = {zip, 7z, rar, gz, tar, bz2, xz, tgz, lzh, cab}`（design 設計上の決定事項 5）を定数定義する。
  - `summarize_archives(inventory, archive_extensions)` を実装する。集計源は `extension_summary` ではなく `raw_inventory.pages[].attachments` の走査とする（design §3.2 archives 補足）。
  - 返り値: `file_count`（カテゴリ該当添付数）/ `total_size_bytes`（`file_size is not None` のみ合算）/ `size_meta_missing_count`（カテゴリ内で `file_size is None` の件数）/ 拡張子別内訳（`{extension, count, total_size_bytes, max_size_bytes}` を `total_size_bytes` 降順固定）。集約系のため `--sort` は受けず、`run_analysis` 側でも sort/limit は適用しない（design §1）。
  - `tar.gz` 等の複合拡張子は collector の `rsplit(".", 1)` 既存挙動（末尾トークン `gz`）に従って判定する。
  - `tests/test_analysis_categories.py` を作成し、カテゴリ集約、`tar.gz` の末尾トークン判定、`file_size=None` 除外とカテゴリ内欠落件数報告、`archive_extensions` 上書き、空集合指定時に 0 件を返すことを検証する。
  - 完了条件: 概算合計から欠落添付が除外され、その件数がカテゴリ単位で報告され、空集合でも 0 件で正常。
  - _要件: 6.1, 6.2, 6.3, 6.4, 6.5, 14.6_

- [ ] 8. マクロ統計・修復候補判定の純粋関数を実装する（UC6）
  - `c2m_export/analysis/macros.py` を新規作成する。冒頭に「converter の変換方針と対応する」旨の日本語コメントを残す（将来の乖離防止）。
  - `count_macros(body_storage)`: BeautifulSoup（`html.parser`、converter と同一パーサ）で解析し、`ac:structured-macro` の `ac:name` 属性と `conf-macro` クラス要素の `data-macro-name` 属性を集計してマクロ名→回数の dict を返す。空本文は空 dict。不正 XHTML でも例外を外に出さない（呼び出し元が捕捉できる前提で、関数内の防御も行う）。
  - `MACRO_REPAIR_RULES`: マクロ名 → `repair_category`（`content_loss`/`external_dependency`/`approximation`/`safe`）と定型日本語 `repair_reason` の静的テーブルを design §5.4 の表どおり定義する。未定義マクロは `unknown`（要確認）として定型文を付与する。
  - `summarize_macros(pages)`: 全ページの `macro_counts` を合算し、マクロ名ごとに `{name, count, repair_category, repair_reason}` の**全件レコード列**を返す（`repair_*` は常に付与）。`mode` に依存せず常に全件を返し、summary/detail の出し分け（summary は `{name, count}` のみ、detail は `repair_*` 込み）と `count` 降順ソートは `run_analysis` が行う（design §5.3 / §1 の責務境界、意図的な非対称）。
  - `tests/test_analysis_macros.py` を作成し、`count_macros` の structured-macro / legacy 両集計、`MACRO_REPAIR_RULES` の写像（content_loss/external_dependency/approximation/safe/unknown）、空本文・不正 XHTML での例外非送出、`summarize_macros` が全件に `repair_*` を付与して返す（ソート・出し分けをしない）ことを検証する。
  - 完了条件: マクロ別レコードが全件返り、修復区分と定型理由が design の表どおり付与される（ソート/出し分けは関数側で行わない）。
  - _要件: 8.1, 8.2, 8.3, 8.4, 14.6_

## フェーズ D: マクロ収集のための既存モジュール拡張（追加のみ・後方互換）

- [ ] 9. データモデルにマクロ用フィールドを追加する（追加のみ・後方互換）
  - `c2m_export/assessment/models.py` の `PageMeta` に `macro_counts: Dict[str, int] = field(default_factory=dict)` を末尾の既定値付きフィールドとして追加する。
  - `RawInventory` に `macro_parse_failed_count: int = 0` を追加する。
  - 既存フィールドの型・名称・順序は変更しない。docstring は日本語で追記する。
  - 完了条件: 既存の `PageMeta`/`RawInventory` 生成箇所・既存テストが未修正で通る（後方互換）。
  - _要件: 8.1, 8.5, 11.1_

- [ ] 10. Collector にマクロ収集を追加する（追加のみ・後方互換）
  - `c2m_export/assessment/collector.py` の `Collector.__init__` に `collect_macros: bool = False` を追加する（既定 False で既存挙動不変。assess からの呼び出しは引数を渡さず現状どおり）。
  - `collect()` 内、`body_bytes` 算出の直後に `collect_macros` が真のときだけ `macros.count_macros(body_storage)` を呼び、結果を `PageMeta.macro_counts` に格納する。本文が無い/解析失敗時はスキップし `RawInventory.macro_parse_failed_count` を加算して集計を継続する。
  - 解析失敗は日本語 warning を stderr（ログ）に出し、全体は止めない。
  - `tests/test_analysis_collector_macros.py` を作成し、`ConfluenceClient` をモックして `collect_macros=False` 時にマクロ収集が走らないこと（既存挙動）、`True` 時に `macro_counts` が埋まること、解析失敗時に `macro_parse_failed_count` が加算され継続することを検証する。
  - 完了条件: 既定でマクロ収集が無効（既存不変）で、有効時のみマクロ集計が行われ失敗は件数化される。
  - _要件: 8.1, 8.5, 11.1, 14.2_

## フェーズ E: 共通 1 層と CLI エントリーポイント

- [ ] 11. 共通 JSON インターフェース層（analysis_api.run_analysis）を実装する
  - `c2m_export/analysis/api.py` を新規作成し、`run_analysis(params: AnalysisParams, config, client: Optional[ConfluenceClient] = None) -> AnalysisResponse` を実装する（`client` 引数化でテスト時モック注入を可能にする）。
  - **独自例外クラスを本モジュールに定義する**: `AuthFailedError` / `TargetNotFoundError` / `ApiError`（design §1 手順 2）。これらと `INVALID_PARAM` / `INTERNAL_ERROR` を `run_analysis` 直下の最外 `try/except` で §3.3 の `code` と終了コードへ一元変換する。
  - **例外→エラーコードの分類（`confluence.py` の実例外仕様に基づく。design §1 手順 2 の擬似コード）**: API 呼び出しを次方針で分類する。
    - `requests.exceptions.HTTPError`: `e.response.status_code` が 401/403 → `AuthFailedError`（`AUTH_FAILED`/3）、404 → `TargetNotFoundError`（`TARGET_NOT_FOUND`/4）、その他 4xx → `ApiError`（`API_ERROR`/5）。
    - `requests.exceptions.RequestException`（ネットワーク系）→ `ApiError`（`API_ERROR`/5）。
    - 5xx リトライ尽き等の素の `Exception` → `ApiError`（`API_ERROR`/5）。
    - 想定外の例外 → `INTERNAL_ERROR`/10。パラメータ/設定不正 → `INVALID_PARAM`/2。
  - 処理手順（design §1）:
    1. `reference_time = datetime.now(timezone.utc)` を一度だけ生成し、`analyze_inventory` と `extract_stale_pages` の双方・`generated_at` に同値で渡す。
    2. 起点解決は `sys.exit` を使わない独自関数 `_resolve_roots(client, params)` を本モジュールに新規実装する（`assess.resolve_roots` は import も改変もしない）。`root_page_ids` + `space_keys` を重複排除する。起点が 404 の場合は `TargetNotFoundError` を送出。**部分失敗の扱い（design §1 手順 2）**: `space_keys` の一部が「存在するがトップレベルページ 0 件」の場合は致命とせず継続し、当該キーを `uncertainties.empty_space_keys` に列挙する。`TARGET_NOT_FOUND`（終了コード 4）に落とすのは**全起点の解決結果が空**のときのみ。`scope.resolved_root_count` に解決できた起点ページ数を反映する。
    3. `Collector(client, analyze_restrictions=..., collect_macros=(macros 要求時のみ))` で `RawInventory` を収集する。
    4. `analyze_inventory(inventory, ..., reference_time=reference_time)` で `AssessmentResult` を得る。
    5. 要求された `usecases` のみ、extractors / categories / macros を呼び、URL 構築関数には `config.base_url` を注入する。UC2 の `counts` に `stale_threshold_days`（= 換算後 `stale_days`）を含める。UC3 で `analyze_restrictions=False` のときは `counts` を 0 とし `uncertainties.restrictions_disabled=true` を立てる。
    6. `AnalysisResponse` を構築し `schema_version` を付与、トークンを含むフィールドを一切持たせない。
  - **ページネーション共通ヘルパ `_paginate(records, sort_key, limit)`（design §1「sort/limit/truncated/total_count の適用層」）**: 全ユースケース共通で (1) `sort_key`（§2.1 の UC 別既定、`--sort` 未指定時）で降順（`restricted` は `page_id` 昇順）ソート、(2) `total_count = len(records)`、(3) 先頭 `limit` 件に切り詰め、(4) `len(records) > limit` なら `truncated=true` を一括適用する。`mode == "summary"` のときは `items` 自体を省略し `counts` のみ出力（`total_count`/`truncated` も付けない）。集約系（`archives` / `macros`）は `--sort` を受理しても無視する（内訳/使用統計は固定順）。
  - 個別失敗（ページ/添付/権限/マクロ/日付）はスキップして `uncertainties` に集計し継続する（部分成功）。
  - `tests/test_analysis_api.py` を作成し、`ConfluenceClient` をモックして summary/detail 切替・usecase 選択・`_paginate` による `sort`/`limit`/`truncated`/`total_count`（純粋関数側でなく api 側で適用されること）・`schema_version` 付与・`reference_time` 共有・`stale_threshold_days`・`restrictions_disabled`・`empty_space_keys`（部分 Space 0 件で継続、全空でのみ `TARGET_NOT_FOUND`）・例外分類（HTTPError 401/403→AUTH_FAILED, 404→TARGET_NOT_FOUND, 他→API_ERROR, RequestException→API_ERROR）・`_resolve_roots` が `SystemExit` でなく独自例外を送出すること・トークン非混入を検証する。
  - 完了条件: 6 ユースケースが design どおり `AnalysisResponse` へ集約され、sort/limit/truncated/total_count が api 層で一括適用され、例外が §3.3 の code/終了コードへ正しく分類され、トークンが出力に混入しない。
  - _要件: 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 4.1, 4.3, 5.1, 5.2, 5.5, 6.2, 7.1, 7.2, 8.2, 10.5, 13.4, 14.1, 14.2_

- [ ] 12. 分析 CLI エントリーポイント（analyze.py）を実装する
  - `c2m_export/analyze.py` を新規作成し `main()` を実装する（`python -m c2m_export.analyze`）。design §4 で採用した案 B（専用エントリーポイント、assess は不変）に従う。
  - 引数: `--base-url` / `--token`（非推奨注記・環境変数推奨をヘルプ文に明記）/ `--proxy` / `--config` / `--root-page-id`(複数可) / `--space-key`(複数可) / `--usecase`(複数可, 既定全 6 種) / `--mode {summary,detail}`(既定 summary) / `--limit` / `--sort` / `--stale-days` / `--stale-years` / `--min-body-bytes` / `--archive-ext`(複数可) / `--restrictions`(`default=None`) / `--no-restrictions`。
  - フロー: 引数解析 → `AnalysisConfig.load/validate` → `AnalysisParams` 構築 → `ConfluenceClient` 初期化 → `run_analysis` → `AnalysisResponse.to_dict` を `json.dumps` して stdout に単独出力。進捗・警告・エラーの人間向け日本語ログは stderr に出す。
  - **サニタイズの適用点（design §7）**: `json.dumps` 後の**出力文字列全体に対して `sanitize_text(text, secrets=[解決済みトークン])` を 1 回だけ**適用してから stdout へ書き出す（各フィールド個別ではない）。stderr ログも出力直前に同様に通す。`secrets` が空/None 要素のみなら完全一致置換は no-op。
  - 終了コード: 正常 0、エラーは `ErrorObject.code` に対応（`INVALID_PARAM=2`/`AUTH_FAILED=3`/`TARGET_NOT_FOUND=4`/`API_ERROR=5`/`INTERNAL_ERROR=10`）。エラー時も可能な限り `status:"error"` の `AnalysisResponse` を stdout に出す。
  - 非対話: 標準入力を要求するプロンプトを一切出さない。必須欠落は即 `INVALID_PARAM`。冪等: Confluence への書き込み・添付ダウンロード・ファイル生成を行わない。
  - `tests/test_analyze_cli.py` を作成し、`capsys` で stdout が JSON 単独（ログ非混入）・stderr にログ分離、終了コード規約（0/2/4 等）、エラー時 ErrorObject、非対話（stdin 非要求）、`generated_at` を比較対象から除外（または固定 `reference_time` 注入）した安定テスト、起点非存在時に `TARGET_NOT_FOUND`/終了コード 4 になることを検証する。
  - 完了条件: stdout が純粋 JSON、ログは stderr、終了コードが規約どおり、トークンが stdout/stderr に出ない。
  - _要件: 1.1, 1.2, 1.3, 1.4, 9.1, 9.2, 9.3, 9.4, 10.1, 10.2, 10.3, 10.4, 10.5, 11.1, 11.2, 13.2, 13.3, 14.4_

## フェーズ F: Skill 提供形態（ローカル → 汎用 → MCP）

- [ ] 13. SKILL.md 正本（汎用 Agent Skills）を作成する
  - 配置確定（design 確定事項 §1）: 正本は `skills/confluence-analysis/SKILL.md`（+ `scripts/`）。GitHub Copilot / Kiro / 汎用の 3 形態はすべて同一の `SKILL.md` オープン標準に一本化する。
  - `skills/confluence-analysis/SKILL.md` を作成する。frontmatter は `name: confluence-analysis`（ディレクトリ名一致・小文字ハイフン）と `description`（何をするか / いつ使うか / 主な機能を 1〜3 文）を必須で書く。
  - 本文に、前提環境（Python 3.8 以上導入済み・本リポジトリ checkout 済み・`pip install -r requirements.txt` 実行済み）、トークンは環境変数 `C2M_CONFLUENCE_TOKEN` で渡す運用（定義ファイルにトークン値を書かない）、6 ユースケースの呼び出し手順（`C2M_CONFLUENCE_TOKEN` を設定 → `python -m c2m_export.analyze --base-url ... --space-key ... --usecase ... --mode ...` をサブプロセス起動 → stdout の JSON をパース）、入力・出力スキーマ（design §3）、終了コード規約（design §3.3）、`schema_version` の後方互換ポリシー（design 確定事項 §3）を自己完結の指示書として記述する。`--usecase` 受理値は design §2.1 の表に厳密一致させる（`empty_with_attachments` の綴り注意）。
  - `skills/confluence-analysis/scripts/run_analysis.*`（CLI をサブプロセス起動するだけの薄い補助スクリプト）を作成する。スクリプトはトークンを引数に取らず環境変数を参照する。ロジックは書かない（共通 1 層 / CLI を呼ぶだけ）。
  - 完了条件: 正本 `SKILL.md` + 補助スクリプトで、frontmatter 準拠かつ OSS 利用者が環境変数と CLI 呼び出しだけで 6 ユースケースを実行でき、トークン値を含まない。
  - _要件: 12.3, 12.5, 12.6, 13.2_

- [ ] 14. 正本 SKILL.md を Copilot / Kiro 配置先へ複製する
  - 配置確定（design 確定事項 §1）: タスク 13 の正本と**同一内容**を次の 2 箇所へ複製する。形式差は無い（いずれも SKILL.md 標準）。
    - GitHub Copilot プロジェクトスキル: `.github/skills/confluence-analysis/SKILL.md`（+ `scripts/`）。
    - Kiro スキル: `.kiro/skills/confluence-analysis/SKILL.md`（+ `scripts/`）。Kiro は description 一致で自動活性化／`/` でスラッシュコマンド起動する。
  - 3 箇所（正本・Copilot・Kiro）の内容が一致していることを確認する。将来の編集は正本を直し他 2 箇所へ複製する運用とし、その旨を正本 `SKILL.md` 冒頭コメントまたは README_DEV に明記する（タスク 16 で README_DEV に記載）。
  - 完了条件: `.github/skills/confluence-analysis/` と `.kiro/skills/confluence-analysis/` が正本と同一の SKILL.md（+ scripts）を持ち、両ランタイムから 6 ユースケースを呼び出せる。トークン値を含まない。
  - _要件: 12.1, 12.2, 12.5, 12.6, 13.2_

- [ ] 15. MCP サーバを実装する（ローカル Skill より低優先）
  - SDK 確定（design 確定事項 §2）: 公式 `mcp` パッケージ（FastMCP）を採用、トランスポートは **stdio を既定**。
  - `requirements-mcp.txt` を新規作成し `mcp` を記載する。**`requirements.txt` には追加しない**（必須依存 requests / beautifulsoup4 / PyYAML / streamlit を汚さない）。
  - `c2m_export/mcp_server.py` を新規作成し、FastMCP で各ユースケースを MCP ツール（例 `analyze_confluence`）として公開する。ツールハンドラは `analysis_api.run_analysis` を呼び `AnalysisResponse` を dict で返すだけの薄いアダプタとする。
  - トークンはサーバ起動環境の環境変数（`C2M_CONFLUENCE_TOKEN` → `CONFLUENCE_TOKEN`）から取得し、ツール引数には取らない。
  - `mcp` は**関数内で遅延 import** し、未導入環境でも他機能（CLI / 既存モード）に影響しないようにする。stdout を汚さない（MCP stdio トランスポートの注意点）。
  - `tests/test_mcp_server.py` を作成し、`analysis_api.run_analysis` をモックしてツールハンドラが dict を返すこと・トークンがツール引数に現れないことを検証する。MCP SDK 未導入時はスキップするテストマーカーを用いる。
  - 完了条件: MCP ツールが共通 1 層を呼ぶだけで分析結果を返し、SDK 未導入でも他機能に影響しない。`requirements.txt` は不変。
  - _要件: 12.4, 12.5, 13.1_

## フェーズ G: ドキュメント・steering・設定サンプル

- [ ] 16. ドキュメントと設定サンプル・steering を更新する
  - `c2m_config_sample.yaml` に分析（analysis）セクションのサンプルとコメント（新設キー: `usecases`/`mode`/`limit`/`stale_days`/`min_body_bytes`/`archive_extensions`/`analyze_restrictions`）を追記する。既存の他モードのサンプル記述は保持（全置換しない）。
  - `README.md` に分析モードの使い方（`python -m c2m_export.analyze`、主要オプション、6 ユースケース、stdout JSON、終了コード、トークンの環境変数推奨、`schema_version` の後方互換ポリシー）と各 Skill 形態の利用手順を追記する。Skill は `SKILL.md` 一本化で 3 箇所（`skills/` 正本・`.github/skills/`・`.kiro/skills/`）に配置される旨、MCP は `pip install -r requirements-mcp.txt` で optional 導入し stdio で起動する旨を記す。
  - `README_DEV.md` に本機能のアーキテクチャ（Skill 形態 → 共通 1 層 `analysis_api` → 既存 assess、純粋ロジックの責務分離、マクロ修復テーブルが converter 方針を写像する旨、秘匿情報サニタイズ）に加え、**SKILL.md は `skills/confluence-analysis/` を正本とし `.github/skills/` と `.kiro/skills/` に複製する運用**（編集は正本を直し複製する）、MCP の `requirements-mcp.txt` optional 依存・FastMCP・stdio を追記する。
  - `.kiro/steering/product.md` に分析 Skill / MCP 提供を主な機能として追記する。
  - `.kiro/steering/tech.md` に `python -m c2m_export.analyze` と MCP サーバ起動のコマンド、`C2M_CONFLUENCE_TOKEN` / `CONFLUENCE_TOKEN` 環境変数を追記する。
  - `.kiro/steering/structure.md` に新規 `c2m_export/analyze.py` / `c2m_export/analysis/` / `c2m_export/mcp_server.py` / `skills/confluence-analysis/`（正本）/ `.github/skills/confluence-analysis/`・`.kiro/skills/confluence-analysis/`（複製）/ `requirements-mcp.txt` と対応テストの責務を追記する。
  - 完了条件: AGENTS.md の README 保守ルールに従い、README/README_DEV/設定サンプル/steering が新機能・新キー・Skill 形態を反映している。
  - _要件: 11.2, 12.5, 12.6, 14.5_

## フェーズ H: 非破壊・認証安全性・全体検証

- [ ] 17. 既存 CLI の後方互換・非破壊を検証する
  - `c2m_export/config.py` の既存 Config クラス、`c2m_export/assessment/models.py` / `collector.py` への追加が既定値のみで既存生成箇所・既存呼び出しを変えていないことをテストで確認する。
  - 既存 CLI（結合エクスポート `cli.py` / assess `assess.py` / fsexport `fsexport.py` / permexport `permexport.py`）の挙動・引数・出力フォーマットが不変であることを、既存テストスイート全通過で確認する（新モード/新フラグを指定しない場合の非破壊）。
  - `tests/test_analysis_backward_compat.py` を作成し、`Collector(collect_macros 未指定)` が従来どおり動くこと、既存 `AssessConfig` のトークン解決既存挙動が env 追加後も不変であることを検証する。
  - 完了条件: 既存テストが全て未修正で通り、新フラグ未指定時の既存挙動が不変であることが示される。
  - _要件: 11.1, 11.2_

- [ ] 18. 認証情報がログ・出力に漏れないことを検証する
  - `tests/test_analysis_token_leak.py` を作成し、ダミートークンを CLI 引数 / 環境変数で与えた実行で、stdout の JSON（`AnalysisResponse`）・`ErrorObject`・stderr ログのいずれにもトークン文字列が現れないことを `capsys` で検証する。
  - 認証失敗（401/403）や API エラー経路で例外メッセージにトークンが混入しないこと（`sanitize_text` の二次防御と ErrorObject の分類が機能すること）を検証する。
  - `scope` に `base_url` は載るがトークンは載らないことを確認する。
  - 完了条件: 正常・異常いずれの経路でもトークンが stdout/stderr/JSON に出ないことがテストで担保される。
  - _要件: 13.1, 13.3, 13.4_

- [ ] 19. 全体の検証と品質チェックを行う
  - `$env:PYTHONPATH="."; python -m pytest` で全テストを実行し、既存テストが壊れていないこと（既存 CLI の非破壊）を確認する。MCP テストは SDK 未導入時スキップマーカーで扱う。
  - `mypy` で型検査を通す（Python 3.8 互換の型注釈）。
  - `pre-commit run --all-files` でフォーマット・YAML チェック・末尾空白・EOF・大容量ファイル検査を通す。
  - 一時ファイルを残さない。
  - 完了条件: pytest / mypy / pre-commit がすべて通過する。
  - _要件: 1.4, 11.1, 14.6_
