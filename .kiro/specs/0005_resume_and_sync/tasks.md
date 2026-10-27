# Implementation Plan

実装は依存関係とテスト容易性を考慮し、「マニフェストモデル/スキーマ → マニフェスト永続化（原子的・スコープ検証）→ 差分判定（純粋）→ 退避 → 同期実行（レジューム含む）→ 設定 → エントリーポイント分岐 → ドキュメント → 検証」の順で進める。純粋関数（`diff`）を先に厚くテストし、I/O（`manifest`/`sync`/`quarantine`）はクライアント・ファイルシステムのモック/一時ディレクトリで検証する。すべてのコメント・docstring・ログは日本語（PEP 257 準拠）で記述し、エラーは「現象・原因・対処方法」構成とする。

> 前提: 0004（ファイルシステムエクスポート）が実装済みであること。本 spec は 0004 の `fs_export`（`tree`/`writer`/`frontmatter`/`links`/`summary`/`models`）と `FsExportConfig`、`ConfluenceClient`（`get_page`/`get_attachments`/`get_space_root_pages`）を再利用・拡張する。本機能はオプトイン（`--sync`/`--resume`）であり、未指定時は 0004 のフル出力と結合モードの挙動を変更しない。

- [ ] 1. マニフェストのデータモデルとスキーマを定義する
  - `c2m_export/fs_export/manifest.py` を新規作成し、マニフェストのスキーマ（`schema_version` / `base_url` / `roots` / `completed` / `started_at` / `finished_at` / `pages{page_id: {version,title,parent_id,rel_path,body_file,state,attachments{...}}}`）を表す型（`dataclass` または TypedDict）を定義する。
  - page_id を不変キーとする方針、添付の識別子（attachment id 優先・filename フォールバック）を docstring で日本語明記する。
  - _要件: 1, 5_

- [ ] 2. マニフェストの永続化・破損検出・スコープ検証を実装する
  - [ ] 2.1 ロード/セーブ（原子的書き込み）を実装する
    - `output_dir` 直下 `.c2m_manifest.json` を読み書きする。保存は一時ファイルへ書き出し `os.replace` で置換し、途中中断でも旧マニフェストが保全されるようにする。
    - _要件: 1, 6_
  - [ ] 2.2 破損・欠落検出とフォールバック通知を実装する
    - JSON パース失敗・`schema_version` 不一致・必須キー欠落を検出し、日本語（現象・原因・対処）で報告。`--full` による全件フル取得フォールバックを案内する。
    - _要件: 1, 6_
  - [ ] 2.3 スコープ検証を実装する
    - 記録済み `base_url` と `roots`（root_page_ids / space_keys 集合）を実行指定と照合する。完全一致で続行、不一致（別サーバ/別対象/部分集合）は破壊的操作を一切せず安全停止し、別 `output_dir` 使用か `--full` を日本語で案内する。
    - _要件: 1_
  - [ ] 2.4 マニフェスト永続化のテストを作成する
    - `tests/test_sync_manifest.py` を作成し、一時ディレクトリで、ロード/セーブ往復・原子的置換・破損検出・schema_version 不一致・スコープ検証（一致で続行／別サーバ・別対象・部分集合で安全停止し破壊的操作をしない）を検証する。
    - _要件: 1, 6_

- [ ] 3. 現在インベントリの軽量収集を実装する
  - `c2m_export/fs_export/sync.py`（または収集用の補助）に、差分判定に必要な軽量メタのみを収集する処理を実装する。
  - ページは DFS で `page_id`/`version.number`/`title`/親（`ancestors` 末尾）を最小 expand（`version,ancestors`）で取得し、添付は `get_attachments` のメタ（version/size/識別子）を取得する。本文・バイナリは取得しない。
  - 収集で個別失敗した page_id を記録し（後段の削除誤認防止に渡す）、スキップして継続する。
  - `tests/test_sync_inventory.py` を作成し、`ConfluenceClient` をモックして軽量収集・部分成功・失敗 page_id の記録を検証する。
  - _要件: 3, 4, 8_

- [ ] 4. 差分判定（diff）を実装する（純粋ロジック）
  - `c2m_export/fs_export/diff.py` を作成し、前回マニフェストと現在インベントリ（＋収集失敗 page_id 集合）を入力に `DiffPlan`（追加/変更/削除/移動/改名/未変更）を算出する純粋関数を実装する。
  - 分類規則: 現在のみ=追加、両方・version同一・親/タイトル同一=未変更、両方・version相違=変更、両方・親orタイトル相違=移動/改名、前回のみ=削除。添付も page 内で同様に分類する。
  - 削除誤認防止: 収集失敗した page_id は削除判定から除外し前回状態を維持する。
  - `tests/test_sync_diff.py` を作成し、全分類・添付差分・削除誤認防止を固定入力で網羅検証する（API/FS モック不要）。
  - _要件: 3, 4, 5_

- [ ] 5. 退避ディレクトリ操作（quarantine）を実装する
  - `c2m_export/fs_export/quarantine.py` を作成し、削除・置換対象のローカル出力（ページディレクトリ/添付ファイル）を退避先 `output_dir/<quarantine_dir_name>/<実行日時>/<元 rel_path>` へ構造ごと移動する。
  - 退避先に既存がある等の競合時は安全側（上書きしない）で処理する。退避・物理削除（`delete`）・報告のみ（`report`）の方針に対応する。
  - `tests/test_sync_quarantine.py` を作成し、一時ディレクトリで退避先命名・構造・競合時の安全処理を検証する。
  - _要件: 4_

- [ ] 6. 同期実行（sync）とレジュームを実装する
  - `c2m_export/fs_export/sync.py` に、`DiffPlan` を適用する実行器を実装する。実出力は 0004 の `tree`/`writer` を再利用する。
  - アクション: 追加/変更=writer で取得・出力しマニフェスト更新、移動/改名=page_id 追跡で旧 `rel_path` から新パス（現在のタイトル/親で再算出）へローカル出力を移設（version 相違時は本文も更新）、削除=quarantine（既定）、未変更=再取得しない。
  - レジューム: `completed=false` を中断とみなし、`state=pending|failed` を未処理として差分に合流。書きかけ整合（`state=done` だが実体なし/一時ファイル残）は未処理に戻して再取得。`completed=true` かつ差分なしは何もしない。
  - マニフェストを逐次・原子的に更新する。個別失敗は `state=failed` で記録し継続（次回再開対象）。進捗を日本語ログで定期報告する。
  - `tests/test_sync_apply.py` を作成し、クライアント/writer をモックして各アクション（追加/変更/移動/改名/削除/未変更）とレジューム（pending/failed 再開・書きかけ整合）を検証する。
  - _要件: 2, 3, 4, 5, 6, 8_

- [ ] 7. マニフェストとファイルシステムの整合回復を実装する
  - `sync` 内で、記録あり・実体なし=未処理扱いで再取得、実体あり・記録なし=報告し既存を壊さない（安全側）を実装する。
  - `--full` 指定時はマニフェストを無視して全件フル取得にフォールバックする経路を用意する。
  - `tests/test_sync_reconcile.py`（または `test_sync_apply.py` に統合）で整合回復ケースを検証する。
  - _要件: 6_

- [ ] 8. 設定（FsExportConfig 拡張）を実装する
  - `c2m_export/config.py` の `FsExportConfig` に本機能のキーを追加する（既存キー・既存クラスは不変）: `sync`(false) / `resume`(false) / `full`(false) / `deletion_policy`(`quarantine`) / `quarantine_dir_name`(`_c2m_quarantine`) / `manifest_name`(内部既定 `.c2m_manifest.json`)。
  - CLI（`--sync`/`--resume`/`--full`/`--deletion-policy`/`--quarantine-dir`）と YAML・env の優先順位で解決する。`deletion_policy` の列挙値（quarantine/delete/report）を検証する。
  - `tests/test_fsexport_sync_config.py` を作成し、既定・優先順位・列挙値・`sync`+`resume` 併用を検証する。
  - _要件: 7_

- [ ] 9. エントリーポイント分岐（fsexport.py 拡張）を実装する
  - `c2m_export/fsexport.py` に、`full` または `sync`/`resume` 未指定時は 0004 のフル出力経路、指定時は manifest ロード → スコープ検証 → インベントリ収集 → diff → sync の経路、の分岐を実装する。
  - フル出力経路でも完了時にマニフェストを新規保存し、次回から sync/resume が使える基盤を作る。
  - サマリ出力は 0004 の `summary` と整合させる（追加/変更/削除/移動・改名/再利用/失敗の件数と対象、日時サフィックス付きファイル）。
  - `tests/test_fsexport_sync_main.py` を作成し、分岐（フル/sync/resume/full フォールバック）・スコープ不一致時の安全停止・サマリ内容をモックで検証する。
  - _要件: 2, 4, 5, 7, 9_

- [ ] 10. サマリ拡張を実装する
  - 0004 の `fs_export/summary.py` を拡張し、差分同期の結果（追加・変更・削除・移動/改名・再利用（スキップ）・失敗の各件数と対象一覧）をログと日時サフィックス付きサマリファイルに出力する。
  - `tests/test_sync_summary.py`（または `test_fs_summary.py` 拡張）で差分サマリの件数・対象一覧・ファイル名形式を検証する。
  - _要件: 9_

- [ ] 11. ドキュメントと設定サンプルを更新する
  - `c2m_config_sample.yaml` に sync/resume 関連キー（`sync`/`resume`/`deletion_policy`/`quarantine_dir_name` 等）のサンプルとコメントを追記する。既存の結合モード・ファイルシステムモード等のサンプル記述は保持したまま、本機能用の記述を追加する（全置換しない）。
  - `README.md` に使い方（`--sync`/`--resume`/`--full`、1 出力先＝1 対象の運用前提、削除同期の既定=退避、スコープ不一致時の挙動）を追記する。
  - `README_DEV.md` に本機能のアーキテクチャ（マニフェスト・原子的更新・スコープ検証、diff の純粋ロジック、移動/改名の page_id 追跡、退避方針、レジュームと差分の統一経路）を追記する。
  - 変更検知の基準（version 主・更新日時補助）をドキュメントで明示する。
  - _要件: 3, 9_

- [ ] 12. 全体の検証と品質チェックを行う
  - `PYTHONPATH=. python -m pytest` で全テストを実行し、0004・結合モードの既存テストが壊れていないこと（非破壊）を確認する。
  - `mypy` で型検査を通す。
  - `pre-commit run --all-files` でフォーマット・YAML チェック等を通す。
  - _要件: 7, 9_
