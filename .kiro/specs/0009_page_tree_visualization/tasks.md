# Implementation Plan

本計画は、Confluence のページ階層を樹形図として出力する新モード（`python -m c2m_export.tree`）と、それを呼び出す Skill `confluence-tree` を実装するためのものである。design.md の「設定 → データモデル → 純粋ロジック（builder / annotations / renderers）→ I/O 層（collector）→ CLI エントリーポイント → Skill → ドキュメント」の順で、依存の下から積み上げる。

実装方針:

- **I/O 層と純粋ロジックを分離**し、純粋ロジック（builder / renderers / annotations）を先に厚く単体テストする。collector は `ConfluenceClient` をモックして薄く検証する。
- **付帯情報は opt-in**。付帯情報未指定時は子ページ一覧取得のみでツリーが完成すること（追加 API ゼロ）を保証する。
- すべてのコメント・docstring・ログは日本語（PEP 257 準拠）。Python 3.8 互換の型注釈（`typing.List/Dict/Optional` 等）を用いる。
- テスト実行は PowerShell で `$env:PYTHONPATH="."; python -m pytest`。
- 既存モジュールは追加変更のみ（`config.py` に新クラス追加、エントリーポイント新設）。既存 CLI の挙動は変更しない。
- 各タスクは対象ファイルのリポジトリ相対パスと、受け入れ基準への紐付け（`_要件: N.M_`）を持つ。

---

## フェーズ A: 設定

- [ ] 1. `TreeConfig` を追加する（`c2m_export/config.py`）
  - `AnalysisConfig` を参考に、`base_url` / `root_page_ids` / `space_keys` / `proxy` / `token` を持つ `TreeConfig` を追加する（追加のみ・既存クラスは不変）。
  - 本モード固有設定を追加: `format`（既定 `"text"`）/ `include`（集合、既定空）/ `ascii`（既定 False）/ `output`（既定 None=stdout）/ `overwrite`（既定 False）/ `max_depth`（既定 None=無制限）。
  - `load()` は優先順位「CLI 引数 > 環境変数（`C2M_CONFLUENCE_TOKEN` → `CONFLUENCE_TOKEN`、`HTTPS_PROXY`/`HTTP_PROXY`）> YAML > デフォルト」で解決する。YAML は `tree:` セクションから `format` / `include` / `max_depth` を読む。
  - `--include all` は 4 種（`restriction` / `macros` / `attachments` / `last_modified`）へ展開する。未知の include 値は INVALID_PARAM。
  - `validate()` は base_url 必須、`root_page_ids` / `space_keys` のいずれか必須、token 必須、base_url の rstrip 正規化、`format` の値域チェックを行い、不足時は現象・原因・対処方法の日本語メッセージを送出する。
  - 完了条件: 優先順位解決・必須チェック・`--include all` 展開・`--format` 値域チェックが機能する。
  - _要件: 1.4, 1.5, 3.1, 3.2, 11.2, 11.3, 11.4, 13.1, 13.3_

## フェーズ B: データモデルと純粋ロジック

- [ ] 2. データモデルを定義する（`c2m_export/page_tree/__init__.py`, `c2m_export/page_tree/models.py`）
  - `page_tree/__init__.py` を新規作成。
  - design §データモデルの `Annotation` / `TreeNode` / `TreeResult` を dataclass で実装する。未取得は `None`、取得失敗は `failed_fields` で区別できるようにする。
  - 完了条件: 3 データクラスが定義され、デフォルトで最小ノード（title + page_id）を表現できる。
  - _要件: 1.2, 4.3, 4.5_

- [ ] 3. 付帯情報の集約・マーク生成を実装する（`c2m_export/page_tree/annotations.py`、純粋ロジック）
  - `aggregate_macros(storage_xhtml: str) -> Dict[str, int]`: structured-macro の `ac:name` と legacy `conf-macro` の `data-macro-name` を集計（spec `0007` の集計方式を踏襲）。解析失敗時は例外を送出し、呼び出し側で failed 扱いにできるようにする。
  - `classify_restriction(restrictions_json: dict) -> Tuple[bool, List[str], List[str]]`: `get_restrictions` の byOperation レスポンスから、個別制限の有無・Read 権 subjects・Read+Write 権 subjects を抽出する。
  - `inline_marks(annotation, ascii: bool) -> str`: design の規則で inline 表記を生成（`🔒`/`📎N`/`⚙N`/`(YYYY-MM-DD)`/不明 `(?)`、ASCII 時は `[R]`/`att:N`/`mac:N`）。0 件・未取得は非表示。
  - 完了条件: マクロ集計・制限分類・inline マーク生成が純粋関数として単体テスト可能。
  - _要件: 4.1, 4.4, 5.2, 5.3, 6.1, 7.2, 8.2_

- [ ] 4. ツリー構築を実装する（`c2m_export/page_tree/builder.py`、純粋ロジック）
  - `build_tree(roots, children_map, annotations_map, max_depth) -> List[TreeNode]`: ルート群と「page_id -> 子 page_id リスト」の写像、及び「page_id -> Annotation」から `TreeNode` 木を構築する。
  - 訪問済み page_id を集合管理し、循環が生じても無限再帰しない防御を入れる（design §循環参照対策）。
  - `max_depth` 指定時は深さで打ち切る。総ノード数を数える。
  - API には一切依存しない（入力は収集済みの dict のみ）。
  - 完了条件: ネスト構築・深さ制限・循環防御・総数カウントが単体テストで検証できる。
  - _要件: 1.1, 14.4_

- [ ] 5. レンダラを実装する（`c2m_export/page_tree/renderers.py`、純粋ロジック）
  - `render_text(result, ascii) -> str`: 罫線（`├──`/`└──`/`│`）ツリー。各行に inline マークを併記。
  - `render_markdown(result, ascii) -> str`: ネスト箇条書きツリー + 付帯情報の別表（`restriction` 詳細表、`macros` 詳細表）。別表は要求された include にのみ対応して出力し、page_id 列で突き合わせ可能にする。
  - `render_json(result) -> str`: `TreeResult` を design のスキーマ（`schema_version` 含む）で `json.dumps`（`ensure_ascii=False`）。
  - 完了条件: 3 フォーマットの出力が design の例と整合し、単体テストで検証できる。
  - _要件: 2.2, 2.3, 2.4, 2.5, 4.1, 4.2, 4.3_

## フェーズ C: I/O 層（collector）

- [ ] 6. ツリー収集を実装する（`c2m_export/page_tree/collector.py`、I/O 層）
  - `collect_tree(client, roots_or_spaces, include, max_depth) -> (roots, children_map, annotations_map, uncertainties, total)` を実装する。
  - 階層探索は常に `get_space_root_pages` / `get_child_pages` のみを使用する。付帯情報は `include` に含まれる種類だけ、ページ単位で対応 API を呼ぶ:
    - `restriction` → `get_restrictions`
    - `macros` → `get_page(expand="body.storage,version")`
    - `attachments` → `get_child_attachments`
    - `last_modified` → `get_page` の `version.when`（macros と併用時は同一レスポンス再利用）、単独時は `get_content_history` または `get_page(expand="version")`
  - 各付帯情報の取得失敗はページ単位で握りつぶし、`Annotation.failed_fields` と `uncertainties`（`restriction_failed` / `macro_failed` / `attachment_failed` / `history_failed`）に積んで探索を継続する。
  - 付帯情報が空集合の場合、`get_space_root_pages` / `get_child_pages` 以外の API を一切呼ばないこと（要件 3.3 / 14.6）。
  - 完了条件: `ConfluenceClient` モックで、opt-in に応じた API のみ呼ばれ、失敗時に uncertainties が積まれ継続することを検証できる。
  - _要件: 3.3, 3.4, 3.5, 5.1, 5.4, 6.4, 7.1, 7.5, 8.1, 8.4, 14.1, 14.2, 14.6_

## フェーズ D: CLI エントリーポイント

- [ ] 7. CLI エントリーポイントを実装する（`c2m_export/tree.py`）
  - `python -m c2m_export.tree` として動作する `main()` を実装する。design §処理フローに従い、`TreeConfig.load()/validate()` → `ConfluenceClient` 初期化 → 起点解決（space / root 両対応、複数可）→ `collect_tree` → `build_tree` → `render_*` → 出力。
  - `--format json` のとき JSON を stdout に単独出力し、進捗・情報ログは stderr へ振り分ける。他フォーマットは結果を stdout（`--output` 指定時はファイル、`--overwrite` 無しでの既存ファイルは拒否）。
  - エラーは design のコード規約（0/2/3/4/5/10）で終了コードを返す。json 形式ではエラーオブジェクト JSON を stdout、日本語詳細を stderr。
  - トークンをログ・出力・エラーに含めない。
  - 完了条件: 実際の引数解析〜出力までが通し、`capsys` で stdout/stderr 振り分けと終了コードを検証できる。
  - _要件: 1.3, 1.6, 2.1, 2.6, 2.7, 9.1, 9.2, 9.3, 9.4, 10.1, 10.2, 10.3, 10.4, 10.5, 13.2_

## フェーズ E: Skill 定義（confluence-tree）

- [ ] 8. 正本スキルを作成する（`skills/confluence-tree/SKILL.md`, `skills/confluence-tree/scripts/run_tree.py`）
  - `run_tree.py` は `skills/confluence-analysis/scripts/run_analysis.py` と同形で、`python -m c2m_export.tree` に `sys.argv[1:]` を素通しするサブプロセスラッパ。`confluence-setup/scripts/diagnose.py` と同じ上方向探索で `PYTHONPATH` 非依存にする。
  - `SKILL.md` は先頭に正本/複製/同期ルールのコメント（既存 2 スキルと同形式）を置き、前提環境・入力（起点・`--format`・`--include`）・出力（text/markdown/json）・トークンは環境変数推奨、を記述する。
  - 完了条件: `python skills/confluence-tree/scripts/run_tree.py --help` 相当が `tree.py` のヘルプへ素通しされる。
  - _要件: 12.1, 12.3, 12.4, 12.5, 13.2_

- [ ] 9. 正本を複製先へ同期する（`.kiro/skills/confluence-tree/`, `.github/skills/confluence-tree/`）
  - 正本 `skills/confluence-tree/` を 2 箇所へ上書きコピーする（既存スキルの同期手順に従う）。
  - 3 箇所の `SKILL.md` / `run_tree.py` のハッシュ一致を確認する。
  - 完了条件: 3 箇所が一致し、複製先からも `run_tree.py` が動作する。
  - _要件: 12.2_

## フェーズ F: ドキュメント・設定サンプル・steering

- [ ] 10. ドキュメントと設定サンプルを更新する
  - `README.md` / `README_DEV.md` に新モード（`python -m c2m_export.tree`）の使い方・`--format` / `--include` / inline マーク規則・出力例を追記する。
  - `c2m_config_sample.yaml` に `tree:` セクションのサンプル（`format` / `include` / `max_depth`）を追加する。
  - `.kiro/steering/structure.md` のプロジェクト構造ツリーと責務表に `c2m_export/tree.py` / `c2m_export/page_tree/` / `skills/confluence-tree/`（+ 複製先）を追記する。
  - 完了条件: ドキュメント・サンプル・steering が実装と整合する。
  - _要件: 11.1, 14.5_

## フェーズ G: テストと検証

- [ ] 11. 単体テストを追加する（`tests/test_tree_*.py`）
  - `test_tree_builder.py`: ネスト構築・深さ制限・循環防御・総数カウント。
  - `test_tree_renderers.py`: text 罫線・markdown ネスト/別表・json スキーマ（`schema_version` 含む）。
  - `test_tree_annotations.py`: マクロ集計・制限分類・inline マーク生成・ASCII フォールバック。
  - `test_tree_collector.py`: `ConfluenceClient` モックで opt-in の API 呼び分け・失敗時継続・付帯情報空での追加 API ゼロ。
  - `test_tree_config.py`: 優先順位・必須チェック・`--include all` 展開・`--format` 値域。
  - 完了条件: `$env:PYTHONPATH="."; python -m pytest` で新規テストが通る。
  - _要件: 3.3, 14.4, 14.6_

- [ ] 12. 後方互換・非破壊と品質チェック
  - 既存 CLI（結合エクスポート / analyze / assess / fsexport / permexport）の挙動が不変であることを確認する（既存テストが全て通る）。
  - トークンが stdout / stderr / 出力 / エラーに現れないことを確認する。
  - pre-commit（trailing-whitespace / end-of-file-fixer / check-yaml / check-added-large-files）と mypy を通す。
  - 完了条件: 既存テスト + 新規テストが全て通り、pre-commit / mypy がパスする。
  - _要件: 9.4, 11.1, 13.2_
