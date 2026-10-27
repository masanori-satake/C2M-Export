# Implementation Plan

実装は依存関係とテスト容易性を考慮し、「データモデル → API 拡張（添付DL含む）→ 純粋ロジック（frontmatter / links / 命名・パス）→ ツリー巡回 → 書き込み → サマリ → 設定 → エントリーポイント → ドキュメント → 検証」の順で進める。純粋関数（frontmatter / links / 命名規約 / パス構築）を先に厚くテストし、I/O（client / tree / writer）は `requests`・クライアントのモックで薄く検証する。すべてのコメント・docstring・ログは日本語（PEP 257 準拠）で記述し、エラーは「現象・原因・対処方法」構成とする。

> 前提: 0003（分析）で `ConfluenceClient` の `get_page` expand 引数化・`get_attachments`・`get_space_root_pages` が既に追加済みの場合は再利用する。未追加の場合は本 spec のタスク 2 で追加する（いずれも既存 `_request` ベース・後方互換）。`download_attachment` は本 spec 固有の新規実装。

- [ ] 1. ファイルシステム出力パッケージの骨格とデータモデルを作成する
  - `c2m_export/fs_export/__init__.py` を新規作成する。
  - `c2m_export/fs_export/models.py` に `PageNode`（page_id/title/level/相対パス/子）、`AttachmentRef`（元ファイル名/保存名/保存可否/download パス/サイズ）、`SkipRecord`（対象/種別/理由/サイズ）、`ExportResult`（成功・失敗・各スキップの集計と個別一覧）を `dataclass` で定義する。
  - docstring で各モデルの責務と、成功/失敗/スキップの区別方針を日本語で記述する。
  - _要件: 6_

- [ ] 2. ConfluenceClient に添付取得・添付ダウンロード・Space 列挙を追加する
  - [ ] 2.1 `get_page` の `expand` を引数化する（0003 未実装時のみ）
    - 既定 `expand="body.storage,space"` を保ち、既存 `cli.py` 呼び出しに影響しないことを担保する。本モードでは Frontmatter 用に version / ancestors / history.lastUpdated 等を追加展開する。
    - _要件: 1, 2_
  - [ ] 2.2 `get_attachments(page_id)` を追加する（0003 未実装時のみ）
    - `/rest/api/content/{id}/child/attachment` を `expand=extensions,version` 付きでページング全件取得し、`filename`/`title`/`extensions.fileSize`/`extensions.mediaType`/`_links.download` を抽出する。
    - _要件: 4, 5, 8_
  - [ ] 2.3 `download_attachment(download_path, dest_file, max_bytes=None)` を新規実装する
    - `session.get(stream=True)` でチャンク単位にストリーミング保存し、メモリ肥大を避ける。
    - `max_bytes` 指定時、受信が上限を超えた時点で中断し、部分ファイルを削除して超過を通知する。
    - 5xx・ネットワーク例外に対し指数バックオフで再試行する（JSON 用 `_request` とは別経路。Proxy・認証は session 継承）。
    - `_links.download`（コンテキストパス相対）を `base_url` と結合して URL を得る。
    - _要件: 4, 5, 8_
  - [ ] 2.4 `get_space_root_pages(space_key)` を追加する（0003 未実装時のみ）
    - Space 内トップレベルページを `depth=root` 相当でページング全件取得する。
    - _要件: 2_
  - [ ] 2.5 クライアント拡張のテストを作成する
    - `tests/test_fs_client.py` を作成し、`requests` をモックして、`download_attachment` のストリーミング保存・`max_bytes` 超過時の中断と部分ファイル削除・リトライ、`get_attachments` のページング全件取得、`get_page` expand 引数化後の既存呼び出し不変を検証する。
    - _要件: 1, 2, 4, 5, 8_

- [ ] 3. ファイル名・ディレクトリ名・パスのユーティリティを実装する
  - `c2m_export/utils.py` に、GB 表示ヘルパ、同一階層での一意名採番（連番サフィックス付与）、相対パス構築（祖先タイトル正規化＋`/`連結）を追加する（既存 `sanitize_filename` を再利用）。
  - 既存関数のシグネチャ・挙動は変更しない（既存テストの非破壊）。
  - `tests/test_utils_fsexport.py`（または既存 `test_utils.py` への追記）で、採番の安定性・パス構築・GB 表示の境界を検証する。
  - _要件: 3_

- [ ] 4. Frontmatter 生成を実装する（純粋ロジック）
  - `c2m_export/fs_export/frontmatter.py` を作成し、元ページ情報から YAML フロントマターを生成する純粋関数を実装する。
  - 最低限 `confluence_url`（オリジナルリンク）を必ず含める。項目は `frontmatter_fields` 設定で増減可能にする。
  - `---` デリミタで囲む定型形式とし、完全移行後に先頭フロントマターブロックを機械的に剥離できる構造にする。
  - `tests/test_fs_frontmatter.py` を作成し、`confluence_url` の必須性・項目設定による増減・剥離可能性を検証する。
  - _要件: 4_

- [ ] 5. 添付参照のリンク書き換え（リンクリゾルバ）を実装する（純粋ロジック）
  - `c2m_export/fs_export/links.py` を作成し、変換済み本文・添付マップ・リンクモードを入力に、本文中の添付参照を書き換える純粋関数を実装する。
  - `relative` モード（既定）: 参照を `<添付サブディレクトリ名>/<正規化保存名>` に置換する。元ファイル名→保存名マップで突き合わせ、同名採番にも対応する。マップに一致しない（未保存）参照は元のファイル名参照のまま残し、未解決一覧に記録する。
  - `original` モード: ローカル保存の有無に依存せず、Confluence 添付への絶対リンク（`_links.download` を `base_url` と結合）に置換する。
  - 外部 URL（`http(s)://`・`<...>` 囲み絶対参照）は据え置く。
  - `tests/test_fs_links.py` を作成し、両モード（相対の保存名一致・未保存据え置き・外部 URL 据え置き・未解決報告、オリジナルの絶対リンク生成）を検証する。
  - _要件: 4_

- [ ] 6. ツリー巡回とローカルパス割当を実装する
  - `c2m_export/fs_export/tree.py` を作成する。既存 `export_tree` と同じ DFS 骨格で巡回し、各ページに「ディレクトリ＋本文ファイル」のローカル相対パスを割り当てる。
  - 命名方式 `page_filename_mode`（`title` 既定／`index`）に対応する。`title` 方式のファイル名変換は要件 3 の正規化・衝突回避ルールと一元化する。
  - 同一親の子群で正規化後ディレクトリ名が重複する場合は安定順で連番採番し、採用名が元タイトルと異なる場合は対応（page_id/元タイトル/採用名）を記録する。
  - `path_length_limit`（既定 400）超過見込みの相対パスを検出して記録する（既定は警告＋継続、短縮はしない）。
  - 複数起点（root_page_ids / space_keys）と訪問済み集合による二重処理防止に対応する。
  - `tests/test_fs_tree.py` を作成し、命名方式・同名衝突採番・禁止文字正規化・パス長検出・部分成功を検証する。
  - _要件: 2, 3, 8_

- [ ] 7. 書き込み（本文＋Frontmatter／添付保存）を実装する
  - `c2m_export/fs_export/writer.py` を作成する。
  - ページごとに本文を `MarkdownConverter` で変換し、Frontmatter を付与し、リンクリゾルバ（タスク5）を適用して、ページディレクトリ直下に UTF-8 で書き込む。
  - 添付処理: 一覧取得 → `exclude_extensions` 除外 → 単一ファイル上限判定（メタサイズでの DL 前判定、メタ欠落時は `max_bytes` 付き DL 後判定）→ 添付サブディレクトリへ保存。保存結果から添付マップ（元名→保存名・保存可否・download パス）を構築しリンクリゾルバに渡す。
  - 個別失敗（ページ取得/変換/書き込み、添付 DL）・上限超過・除外を区別して `SkipRecord`／失敗一覧に記録し、処理を継続する（部分成功）。
  - 進捗（出力済みページ数・添付数）を日本語ログで定期報告する。
  - `tests/test_fs_writer.py` を作成し、クライアント/コンバータをモックして、本文書き込み・添付保存・上限（DL前/後）・除外拡張子・リンクモード連携・部分成功を検証する。
  - _要件: 2, 4, 5, 6, 8_

- [ ] 8. 処理サマリの生成と出力を実装する
  - `c2m_export/fs_export/summary.py` を作成する。入力は `ExportResult`。
  - 内容: 出力ページ数・出力添付数・総出力サイズ（MB/GB）・各スキップ件数に加え、成功一覧と失敗/スキップ個別一覧（識別子＝page_id/ファイル名・パス・理由）、相対リンク未解決件数を含める。
  - 出力: 標準出力（ログ）＋ 実行日時サフィックス付きファイル（年月日・時分秒、ミリ秒なし。例 `fsexport_summary_YYMMDD_HHMMSS.txt`）を `output_dir` 配下に生成する。サマリファイル書き込み失敗時も現象・原因・対処を日本語で報告し、ログ出力自体は行う。
  - `tests/test_fs_summary.py` を作成し、成功/失敗/スキップ集計・失敗個別一覧の存在・日時サフィックス形式を検証する。
  - _要件: 5, 6_

- [ ] 9. ファイルシステムモードの設定（FsExportConfig）を実装する
  - `c2m_export/config.py` に `FsExportConfig` を追加する（既存 `Config`・`AssessConfig` は不変）。
  - 共通骨格（YAML → env → CLI の優先順位、`base_url` の rstrip 正規化、proxy の env 取り込み）を踏襲する。
  - 本モードのキーを実装する: `root_page_ids` / `space_keys` / `output_dir` / `overwrite` / `attachment_dir_name`(`_attachments`) / `attachment_link_mode`(`relative`) / `page_filename_mode`(`title`) / `single_file_max_mb`(250) / `exclude_extensions` / `path_length_limit`(400) / `frontmatter_fields`。既存キー（`base_url`/`token`/`proxy`）も踏襲。
  - `validate()`: `root_page_ids` と `space_keys` の少なくとも一方が必須、`base_url`・`token` 必須。
  - `tests/test_fsexport_config.py` を作成し、優先順位・rstrip・既定値・必須チェック・列挙値（link_mode/filename_mode）の検証を行う。
  - _要件: 1, 3, 4, 5, 7, 9_

- [ ] 10. エントリーポイント（fsexport.py）とフェイルファストを実装する
  - `c2m_export/fsexport.py` を作成し `main()` を実装する（`python -m c2m_export.fsexport`）。
  - 骨格は既存 `cli.py` を踏襲: 日本語ログ設定 → `FsExportConfig.load/validate` → `ConfluenceClient`/`MarkdownConverter` 初期化 → 起点解決（`resolve_roots`: root_page_ids / space_keys）→ フェイルファスト（出力先の書き込み可否・既存競合、`overwrite` 制御）→ tree 巡回 → writer 書き込み → summary 出力。
  - 起点が存在しない/権限なし・出力先競合はフェイルファストで日本語（現象・原因・対処）出力して終了する。
  - `tests/test_fsexport_main.py` を作成し、クライアント/tree/writer をモックして起点解決・フェイルファスト・サマリ出力を検証する。
  - _要件: 1, 2, 6, 7, 9_

- [ ] 11. ドキュメントと設定サンプルを更新する
  - `c2m_config_sample.yaml` にファイルシステムモードのセクション（本モード固有キーのサンプルとコメント）を追記する。既存の結合モード・他モードのサンプル記述は保持したまま、本モード用セクションを追加する（全置換しない）。
  - `README.md` に本モードの使い方（`python -m c2m_export.fsexport`、主要オプション、出力構造＝ページディレクトリ＋本文＋添付サブディレクトリ、リンクモード、Frontmatter、サマリファイル）を追記する。
  - `README_DEV.md` に本モードのアーキテクチャ（`fs_export/` のモジュール責務、変換器を分岐させずリンク後処理する方針、添付 DL の別経路実装、部分成功・サマリ設計）を追記する。
  - _要件: 9_

- [ ] 12. 全体の検証と品質チェックを行う
  - `PYTHONPATH=. python -m pytest` で全テストを実行し、既存テスト（結合モード）が壊れていないこと（非破壊）を確認する。
  - `mypy` で型検査を通す。
  - `pre-commit run --all-files` でフォーマット・YAML チェック等を通す。
  - _要件: 1, 9_
