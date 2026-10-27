# Implementation Plan

実装は依存関係とテスト容易性を考慮し、「データモデル → 権限取得クライアント確認 → 収集（I/O）→ レポート生成（純粋）→ サマリ → 設定 → エントリーポイント → ドキュメント → 検証」の順で進める。純粋関数（`report`）を先に厚くテストし、I/O（`collector`）は `ConfluenceClient` モックで検証する。すべてのコメント・docstring・ログは日本語（PEP 257 準拠）で記述し、エラーは「現象・原因・対処方法」構成とする。

> 前提: 0003（分析）で `ConfluenceClient.get_restrictions`（`/rest/api/content/{id}/restriction/byOperation` の JSON を返す）が追加済みの場合は再利用する。未追加の場合は本 spec のタスク 2 で追加する。`get_child_pages` / `get_space_root_pages` も再利用する。本機能はオプトインであり、未指定時は 0004 のファイルシステム出力・結合モードの挙動を変更しない。継承は展開せず「継承/制限なし」と記す方針（案A）に従う。

- [ ] 1. 権限エクスポートパッケージの骨格とデータモデルを作成する
  - `c2m_export/permission/__init__.py` を新規作成する。
  - `c2m_export/permission/models.py` に `PagePermission`（page_id/title/space_key/url/rel_path/has_explicit/read_users/read_groups/readwrite_users/readwrite_groups/fetch_failed/fail_reason）、`PermissionReport`、`PermissionResult`（出力数/個別制限数/継承数/失敗一覧）を `dataclass` で定義する。
  - 継承を展開しない方針（has_explicit の意味）・Read+Write が API の `update` に対応することを docstring で日本語明記する。
  - _要件: 1, 3_

- [ ] 2. ConfluenceClient の権限取得を確認/追加する
  - 既存 `get_restrictions(page_id)` は `/rest/api/content/{id}/restriction/byOperation` の JSON を返す。未実装の場合のみ同じ契約で追加する。既存 `_request` を用いてリトライ・Proxy・認証を自動適用する。ユーザー/グループの抽出と識別子表現は Collector が担当する。
  - `tests/test_perm_client.py`（0003 で済なら不要）を作成し、`requests` をモックして read/update 抽出・空（制限なし）応答の扱いを検証する。
  - _要件: 1, 7_

- [ ] 3. 権限収集（collector）を実装する
  - `c2m_export/permission/collector.py` を作成し、既存 DFS 骨格で巡回しながら各ページの `get_restrictions` を呼び `PagePermission` を構築する。
  - ユーザー識別子は design.md の契約に従い username → userKey の優先順とする。displayName は表示専用、前後空白のみ除去、両キー欠落も「識別子不明」として残し制限あり判定に含める。実環境の匿名化済みレスポンス fixture を収録・照合し、優先順位・正規化・全欠落パターンを検証する（既存 fixture はモックのみで照合未完了）。
  - 個別制限判定（案A）: 取得成功時だけ read・update ともに空なら `has_explicit=False`（継承/制限なし）、いずれかに対象があれば `True`。失敗時は has_explicit を判定に使わない。親さかのぼりの実効権限展開は行わない。
  - 複数起点（root_page_ids / space_keys）と訪問済み集合による二重処理防止に対応する。
  - 権限取得失敗は本文処理と独立に `fetch_failed=True`・理由を記録して継続（部分成功）。進捗を日本語ログで定期報告する。
  - 0004 併用時の `rel_path` 算出のため、0004 の命名ユーティリティ（タイトル正規化・相対パス構築）を再利用する（単独時は rel_path=None）。
  - `tests/test_perm_collector.py` を作成し、`ConfluenceClient` をモックして個別制限あり/継承判定・部分成功・二重処理防止を検証する。
  - _要件: 1, 2, 3, 6, 7_

- [ ] 4. レポート生成（report）を実装する（純粋ロジック）
  - `c2m_export/permission/report.py` を作成する。入力は `PermissionReport` のみ（API 非依存）。
  - **集約（既定）**: 出力先ルート直下に俯瞰ファイル（`_permissions.md`）を生成。全ページを表形式（ページ/個別制限有無/Read 保有者/Read+Write 保有者/URL）で一覧し、個別制限ありを識別しやすくする。
  - **分散（per_page）**: 各ページ対応ディレクトリ（`rel_path`）に権限ファイルを配置。`rel_path` が無い（単独実行）場合は集約にフォールバックし日本語で通知する。
  - 各ページ出力に page_id / タイトル / Confluence URL /（併用時）ローカル相対パス、Read 権・Read+Write 権（ユーザー/グループ）または「継承/制限なし」を含める。
  - 識別子は design.md の表示形式（username 優先、userKey フォールバック、識別子不明）・グループ名を使う。冒頭に「Confluence 側権限の記録であり配置先への自動適用ではない」「継承は展開していない」旨の注記を入れる。
  - 集約・分散・JSON ともに `fetch_failed` を `has_explicit` より優先する。失敗ページは「取得失敗」と `fail_reason` を出力し、確定した権限や「継承/制限なし」として扱わない。両方の has_explicit 値との組合せを検証する。
  - 任意 JSON 出力（`report_formats` に json 指定時）をキー安定な構造で生成する。
  - `tests/test_perm_report.py` を作成し、Read/Read+Write 区別・継承表記・識別子併記・注記・集約/分散/JSON の各出力・キー安定性を検証する。
  - _要件: 3, 4_

- [ ] 5. 処理サマリ（summary）を実装する
  - `c2m_export/permission/summary.py` を作成する。入力は `PermissionResult`。
  - 権限を出力したページ数・個別制限ありページ数・継承/制限なしページ数・取得失敗件数（対象 page_id）を集計する。失敗ページは exported_count / explicit_count / inherited_count から除外し、failed_page_ids に一度だけ記録する。`exported_count = explicit_count + inherited_count` を検証する。
  - 標準出力（ログ）＋ 実行日時サフィックス付きファイル（年月日・時分秒、ミリ秒なし。例 `permexport_summary_YYMMDD_HHMMSS.txt`）を `output_dir` 配下に出力する（0004/0005 のサマリ方針と整合）。
  - `tests/test_perm_summary.py` を作成し、件数集計・失敗一覧・日時サフィックス形式を検証する。
  - _要件: 6, 8_

- [ ] 6. 設定（PermissionExportConfig）を実装する
  - `c2m_export/config.py` に `PermissionExportConfig` を追加する（既存 `Config`/`AssessConfig`/`FsExportConfig` は不変）。
  - 共通骨格（YAML → env → CLI の優先順位、`base_url` の rstrip 正規化、proxy の env 取り込み）を踏襲する。
  - キー: `root_page_ids` / `space_keys` / `output_dir` / `report_layout`(`aggregate`) / `report_formats`(`md`) / `attachment_dir_name`(`_attachments`) / `page_filename_mode`(`title`) / `overwrite`。既存キー（`base_url`/`token`/`proxy`）も踏襲。
  - `validate()`: `root_page_ids` と `space_keys` の少なくとも一方が必須、`base_url`・`token` 必須。`report_layout`/`report_formats` の列挙値を検証。`per_page` 指定かつ単独実行時は集約フォールバックの警告方針を明示。
  - `tests/test_permexport_config.py` を作成し、優先順位・rstrip・既定値・必須チェック・列挙値・フォールバックを検証する。
  - _要件: 2, 4, 5, 8_

- [ ] 7. エントリーポイント（permexport.py）を実装する
  - `c2m_export/permexport.py` を作成し `main()` を実装する（`python -m c2m_export.permexport`）。
  - 骨格は既存 `cli.py` を踏襲: 日本語ログ設定 → `PermissionExportConfig.load/validate` → `ConfluenceClient` 初期化 → 起点解決（root_page_ids / space_keys）→ 出力先フェイルファスト → collector → report → summary。
  - 起点が存在しない/権限なし・出力先競合はフェイルファストで日本語（現象・原因・対処）出力して終了する。
  - `tests/test_permexport_main.py` を作成し、クライアント/collector をモックして起点解決・フェイルファスト・レポート/サマリ呼び出しを検証する。
  - _要件: 1, 2, 5, 6, 8_

- [ ] 8. ドキュメントと設定サンプルを更新する
  - `c2m_config_sample.yaml` に権限エクスポートのセクション（`report_layout`/`report_formats` 等のサンプルとコメント）を追記する。既存の結合モード・他モードのサンプル記述は保持したまま、権限エクスポート用セクションを追加する（全置換しない）。
  - `README.md` に使い方（`python -m c2m_export.permexport`、主要オプション、集約/分散レポート、識別子表記、0004 併用時のパス対応）を追記する。
  - `README_DEV.md` に本機能のアーキテクチャ（collector/report/summary の責務分離、継承を展開しない方針=案A、`byOperation` による一括取得、自動適用しない方針）を追記する。
  - 継承を展開しない方針（個別制限箇所を浮かび上がらせる意図）と、記録のみで自動適用しないことをドキュメントで明示する。
  - _要件: 3, 4, 8_

- [ ] 9. 全体の検証と品質チェックを行う
  - `PYTHONPATH=. python -m pytest` で全テストを実行し、既存（結合モード・0004）テストが壊れていないこと（非破壊）を確認する。
  - `mypy` で型検査を通す。
  - `pre-commit run --all-files` でフォーマット・YAML チェック等を通す。
  - _要件: 5, 8_
