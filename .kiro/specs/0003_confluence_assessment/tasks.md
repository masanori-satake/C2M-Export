# Implementation Plan

実装は依存関係とテスト容易性を考慮し、「データモデル → API 拡張 → 収集 → 純粋ロジック（分析・ルール）→ レポート → 設定 → エントリーポイント → ドキュメント」の順で進める。純粋関数（analyzers / rules / report）を先に厚くテストし、I/O（collector / client）は `requests` モックで薄く検証する。すべてのコメント・docstring・ログは日本語（PEP 257 準拠）で記述する。

- [ ] 1. 分析パッケージの骨格とデータモデルを作成する
  - `c2m_export/assessment/__init__.py` を新規作成する。
  - `c2m_export/assessment/models.py` に `AttachmentMeta` / `RestrictionMeta` / `PageMeta` / `RawInventory` / `AssessmentResult` を `dataclass` として定義する。
  - 各フィールドは JSON 出力と集計で扱いやすいプリミティブ中心とし、サイズ欠落は `Optional[int]` で表現する。
  - docstring に各モデルの責務を日本語で記述する。
  - _要件: 3, 4, 6, 7_

- [ ] 2. ConfluenceClient に分析用の API メソッドを追加する
  - [ ] 2.1 `get_page` の `expand` を引数化する（既定値は現行と同一で後方互換）
    - 既定 `expand="body.storage,space"` を保ち、既存 `cli.py` の呼び出しに影響しないことを担保する。
    - _要件: 1, 9_
  - [ ] 2.2 `get_attachments(page_id)` を追加する
    - `/rest/api/content/{id}/child/attachment` を `expand=extensions,version` 付きでページング全件取得する。
    - レスポンスから `filename` / `extensions.fileSize` / `extensions.mediaType` / `version.number` を抽出する。
    - 既存 `_request` を用い、リトライ・Proxy・認証を自動適用する。
    - _要件: 3, 4, 9_
  - [ ] 2.3 `get_restrictions(page_id)` を追加する
    - `/rest/api/content/{id}/restriction/byOperation` を取得し、`read` / `update` それぞれの `restrictions.user.results`（username / displayName）と `restrictions.group.results`（name）を抽出する。
    - _要件: 6_
  - [ ] 2.4 `get_space_root_pages(space_key)` を追加する
    - Space 内トップレベルページを `depth=root` 相当でページング全件取得する。
    - _要件: 2_
  - [ ] 2.5 クライアント拡張のテストを作成する
    - `tests/test_confluence_assess_client.py` を作成し、`requests` をモックして 2.1〜2.4 を検証する（ページング全件取得・read/update 抽出・expand 引数化後の既存呼び出し不変）。
    - _要件: 1, 2, 3, 4, 6, 9_

- [ ] 3. 移設リスク判定ルールを実装する（純粋ロジック）
  - `c2m_export/assessment/rules.py` を作成する。
  - SharePoint/OneDrive の既定制約を定数化する: パス長上限 400、禁止文字 `" * : < > ? / \ |` と制御文字、予約語集合（`utils.sanitize_filename` の集合を流用）、末尾ドット/スペース、ブロック拡張子の既定リスト。
  - 判定関数を実装する: パス長超過判定、禁止文字/予約語/末尾記号判定、ブロック拡張子判定、単一ファイル巨大判定（`single_file_max_mb`）。
  - 相対パス算出ヘルパ（`ancestors_titles + title` を正規化して `/` 連結、添付は `+ attachment_dir_name + filename`）を実装する。
  - `tests/test_assessment_rules.py` を作成し、各判定を境界値込みで検証する。
  - _要件: 5_

- [ ] 4. 集計・分布・リスク集約を実装する（純粋ロジック）
  - [ ] 4.1 規模・構造・拡張子別・鮮度の集計関数を実装する
    - `c2m_export/assessment/analyzers.py` を作成する。
    - 規模: 総ページ数・総添付数・推定総サイズ（本文概算 + 添付メタサイズ合計）。
    - 構造: 最大深さ・階層レベル別ページ数分布・Space 別内訳。
    - 添付: 拡張子別の個数/合計サイズ/最大サイズ（サイズ降順）、拡張子不明の区別、MIME 別集計。
    - 鮮度: 更新日の期間別ビン、`stale_days` 以上の件数、`min_body_bytes` 未満の件数、日付解釈失敗件数。
    - _要件: 3, 4, 7_
  - [ ] 4.2 権限サマリと同名衝突・不確実性の集約を実装する
    - 権限: 個別制限ありページ数、ユニークなユーザー/グループ一覧、Read / Read+Write 区別、継承/制限なしの区別、取得失敗件数。
    - 同名衝突: 同一親の子ページ正規化名の重複、同一ページ内の添付正規化名の重複を検出。
    - 不確実性: `size_meta_missing_count` とスキップ件数を集約。
    - `RawInventory`（+ rules の判定結果）から `AssessmentResult` を構築する関数を実装する。
    - _要件: 5, 6, 8_
  - [ ] 4.3 分析ロジックのテストを作成する
    - `tests/test_assessment_analyzers.py` を作成し、固定の `RawInventory` 入力に対する全集計を検証する（API モック不要）。
    - _要件: 3, 4, 5, 6, 7_

- [ ] 5. メタデータ収集（Collector）を実装する
  - `c2m_export/assessment/collector.py` を作成する。
  - 既存 `export_tree` と同じ DFS 骨格を用いるが本文変換は行わず、`get_page`（分析用 expand）/ `get_attachments` /（有効時）`get_restrictions` を呼んで `PageMeta` を構築する。
  - 本文サイズは Storage Format の UTF-8 バイト長で概算する（変換器は回さない）。
  - 訪問済み `page_id` 集合で二重集計を防ぎ、複数起点に対応する。
  - 個別失敗（ページ/添付/権限/日付）はスキップして継続し、`skipped_page_ids` / `skipped_attachment_refs` / `restriction_failed_page_ids` / `size_meta_missing_count` に集計する。
  - 進捗（処理済みページ数）を日本語ログで定期報告する。
  - `tests/test_assessment_collector.py` を作成し、`ConfluenceClient` をモックして DFS 巡回・部分成功・二重集計防止を検証する。
  - _要件: 2, 3, 4, 6, 7, 9_

- [ ] 6. レポート生成（Markdown + JSON）を実装する
  - `c2m_export/assessment/report.py` を作成する。入力は `AssessmentResult` のみ（API 非依存）。
  - Markdown: 概算注記、規模サマリ、Space 別内訳、階層分布、添付拡張子別（サイズ降順）、移設リスク一覧、権限サマリ、鮮度サマリ、スキップ・不確実性サマリの各セクションを出力する。
  - サイズ表示: `utils.bytes_to_mb` を流用し、GB 表示用のヘルパを `utils` に追加する。
  - JSON: キーが安定した構造化データ（集計値 + 個別リスク項目: page_id / 名前 / パス / 理由）を出力する。スキーマ概要を冒頭コメントに記載する。
  - 出力先・命名（既定 `confluence_assessment_<yyyymmdd_HHMMSS>.md` / `.json`）と `overwrite` 未指定時のフェイルファストを実装する。
  - `tests/test_assessment_report.py` を作成し、JSON のキー安定性と Markdown の主要セクション存在を検証する。
  - _要件: 6, 8_

- [ ] 7. 分析用設定（AssessConfig）を実装する
  - `c2m_export/config.py` に `AssessConfig` を追加する（既存 `Config` は不変）。
  - 共通骨格（YAML → env → CLI の優先順位、`base_url` の rstrip 正規化、proxy の env 取り込み）を踏襲する。
  - 分析固有キーを実装する: `space_keys` / `analyze_restrictions` / `single_file_max_mb`(250) / `path_length_limit`(400) / `blocked_extensions` / `attachment_dir_name`(`_attachments`) / `stale_days`(365) / `min_body_bytes`(200) / `report_formats`(both)。既存キー（`base_url`/`token`/`proxy`/`output_dir`/`root_page_ids`/`overwrite`）も受け付ける。
  - `validate()`: `root_page_ids` と `space_keys` の少なくとも一方が必須、`base_url`・`token` 必須。
  - `tests/test_assess_config.py` を作成し、優先順位・rstrip・既定値・必須チェックを検証する。
  - _要件: 2, 5, 6, 7, 8, 10_

- [ ] 8. エントリーポイント（assess.py）を実装する
  - `c2m_export/assess.py` を作成し `main()` を実装する（`python -m c2m_export.assess`）。
  - 骨格は既存 `cli.py` を踏襲: 日本語ログ設定 → `AssessConfig.load/validate` → `ConfluenceClient` 初期化 → 起点解決（`resolve_roots`: root_page_ids / space_keys）→ `Collector.collect` → `analyze` → `write_reports` → 完了サマリ。
  - 起点が存在しない/権限なしはフェイルファストで日本語（現象・原因・対処）出力して終了する。
  - 完了サマリに総ページ数・総添付数・推定総サイズ・検出リスク件数・スキップ件数を含める。
  - `tests/test_assess_main.py` を作成し、クライアント/コレクタをモックして起点解決・サマリ出力・フェイルファストを検証する。
  - _要件: 1, 2, 9, 10_

- [ ] 9. ドキュメントと設定サンプルを更新する
  - `c2m_config_sample.yaml` に分析セクション（分析固有キーのサンプルとコメント）を追記する。既存の結合モード・他モードのサンプル記述は保持したまま、分析用セクションを追加する（全置換しない）。
  - `README.md` に分析モードの使い方（`python -m c2m_export.assess`、主要オプション、出力レポート）を追記する。
  - `README_DEV.md` に分析機能のアーキテクチャ（モジュール構成・収集/分析/レポートの責務分離・サイズ概算の偏りの説明）を追記する。
  - 概算が実測に対しどちら側に偏るか（添付はほぼ一致、本文はやや過大＝安全側）をドキュメントに明記する。
  - _要件: 6, 8, 10_

- [ ] 10. 全体の検証と品質チェックを行う
  - `PYTHONPATH=. python -m pytest` で全テストを実行し、既存テストが壊れていないこと（結合モードの非破壊）を確認する。
  - `mypy` で型検査を通す。
  - `pre-commit run --all-files` でフォーマット・YAML チェック等を通す。
  - _要件: 1, 10_
