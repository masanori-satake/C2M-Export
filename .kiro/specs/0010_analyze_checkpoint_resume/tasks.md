# Implementation Plan

本計画は、分析モード（`python -m c2m_export.analyze` / assessment 収集層 `Collector`）に、**チェックポイント永続化・レジューム・部分成功（partial）出力・中断シグナル対応**を実装するものである。design.md の構成（新規 `analysis/checkpoint.py` → `Collector` への2点差し込み → `run_analysis` のライフサイクル統括 → CLI/スキーマ/設定/ドキュメント）に従い、下から積み上げる依存順で進める。

前提:

- 本計画の各タスクは「spec を書く」ものではなく「コードを実装する」タスクである。各タスクは対象ファイルのリポジトリ相対パスと、完了条件（要件番号への紐付け `_要件: N.M_`）を持つ。
- 0007（`analysis/`・`analyze.py`・`AnalysisResponse`・`AnalysisParams`・`AnalysisConfig`）/ 0008（収集層拡張・`Collector`・`RawInventory`・`PageMeta`）が実装済みであることを前提に、その上へ**追加のみ・後方互換**で積む。既存メソッド・既存フィールド・既存 CLI・既存挙動は変更しない。
- コメント・docstring・ログはすべて日本語（PEP 257 準拠）。Python 3.8 互換の型注釈（`typing.List/Dict/Set/Optional/Tuple/Callable`）。テスト実行は `$env:PYTHONPATH="."; python -m pytest`（PowerShell）。
- チェックポイント機構は収集層（I/O）に閉じ、分析純粋関数は不変。新規依存は導入しない（標準 `json` / `signal` / `hashlib` / `os` / `threading`）。

実装順序の方針（依存順）:

1. 純粋関数・`CheckpointStore`（`analysis/checkpoint.py`、I/O 最小・単体テスト容易）
2. スキーマ拡張（`AnalysisResponse.status="partial"`・`Uncertainties` 追加キー・`schema_version` 1.2）
3. `Collector` への差し込み（追記・resume スキップ・協調的中断）
4. `run_analysis` のライフサイクル統括（スコープ算出・復元・partial 構築）
5. `AnalysisParams` / `AnalysisConfig` のオプション追加（CLI/YAML）
6. CLI 層（シグナル・partial 出力・終了コード 6）
7. Skill / MCP / ドキュメント / 設定サンプル / steering 更新
8. 後方互換・認証非漏洩・全体品質チェック

---

## フェーズ 1: チェックポイント基盤（純粋関数 + CheckpointStore）

- [ ] 1. スコープハッシュ算出と PageMeta ⇔ レコード変換の純粋関数を実装する
  - `c2m_export/analysis/checkpoint.py` を新規作成し、以下を純粋関数として実装する（design §1.1, §1.2 の変換部）。
    - `compute_scope_hash(base_url, root_page_ids, space_keys, all_spaces, cql, collect_flags) -> str`: `base_url` の末尾スラッシュ除去、リストのソート、`collect_flags` のキー順整列で正規化し、`hashlib.sha256` の短縮ハッシュを返す。トークン・表示系（limit/sort/mode）は含めない。
    - `page_meta_to_record(page_meta) -> dict`: `PageMeta`（ネストした `AttachmentMeta` / `RestrictionMeta` を含む）を JSONL 1 レコード用 dict（`{"_type": "page", "page": {...}}`）へ変換する。
    - `record_to_page_meta(record) -> PageMeta`: 上記の逆変換。ネスト dataclass を明示再構築し型を保つ。
  - docstring は日本語（PEP 257）。API/ファイルに依存しない。
  - `tests/test_checkpoint_pure.py` を作成し、(a) 同一スコープで同一ハッシュ・異なるスコープで異なるハッシュ・引数順に非依存、(b) `page_meta_to_record` → `record_to_page_meta` の往復同値（添付・制限のネスト保全）を検証する。
  - 完了条件: スコープハッシュが安定かつスコープ差を反映し、PageMeta の往復変換が同値になる。
  - _要件: 1.2, 5.2, 8.6_

- [ ] 2. CheckpointStore（JSONL 追記・読込・スコープ照合・後始末）を実装する
  - `c2m_export/analysis/checkpoint.py` に `CheckpointStore` クラスを追加する（design §1.2）。
    - `__init__(path, scope_hash, scope_meta, interval=1)`。
    - `open_for_write(append)`: 追記モードで開き、新規時はヘッダ行（`{"_type":"header","scope_hash":...,"scope":...,"schema_version":...}`）を書く。
    - `append_page(page_meta)`: `page_meta_to_record` を 1 行追記し、`interval` 件ごと（および明示時）に `flush()`。
    - `flush()`: `file.flush()` + `os.fsync()`。
    - `load_collected() -> Tuple[List[PageMeta], Set[str], List[str]]`: 1 行ずつ読み、ヘッダを除く page レコードを復元。`json.loads` 失敗行・途中切れ最終行はスキップして破損行として記録し、(復元 PageMeta, 収集済み page_id 集合, 破損行リスト) を返す。
    - `scope_matches(scope_hash) -> bool`: ヘッダの `scope_hash` と比較。
    - `finalize(success)`: 成功時はファイル削除（既定）、失敗時は残置。
    - `close()`。
  - ディレクトリ不在時は作成し、作成・書込失敗時は現象/原因/対処の日本語で例外化またはログ報告する。
  - `tests/test_checkpoint_store.py` を作成し、一時ディレクトリで (a) 追記→再読込の同値、(b) スコープ不一致検出、(c) 破損行・途中切れからの部分復元、(d) `finalize(success=True)` でのファイル削除を検証する。
  - 完了条件: 追記・復元・スコープ照合・破損耐性・後始末が仕様どおり動作する。
  - _要件: 1.1, 1.2, 1.3, 1.5, 2.4, 5.1, 5.4, 5.5, 8.4_

## フェーズ 2: スキーマ拡張（後方互換）

- [ ] 3. AnalysisResponse / Uncertainties を partial・新キーへ拡張する
  - `c2m_export/analysis/response.py` を更新する（design §5.1, §5.2）。
    - `AnalysisResponse.status` の取りうる値に `"partial"` を加える（docstring/コメント更新）。`schema_version` の既定を `"1.1"` → `"1.2"` に更新する。
    - `Uncertainties` に既定値付きで追加: `interrupted: bool=False` / `interrupted_reason: Optional[str]=None` / `collected_page_count: int=0` / `resumed_from_checkpoint: bool=False` / `checkpoint_reused_count: int=0` / `checkpoint_corrupted_line_count: int=0`。
    - モジュール先頭の JSON スキーマ概要コメントに新キー・新 status・schema_version を反映する。
  - 既存キーの型・名称・意味・順序は変更しない。`run_analysis` 内の `schema_version="1.1"` リテラルも `"1.2"` に更新する。
  - `tests/test_response_partial.py`（または既存 response テスト）で、新キーが既定値で `to_dict()` に出力され、既存キーが不変であることを検証する。
  - 完了条件: `status="partial"` と新 `uncertainties` キーが後方互換で表現でき、`schema_version` が 1.2 になる。
  - _要件: 3.2, 8.1, 8.2_

## フェーズ 3: Collector への差し込み

- [ ] 4. Collector にチェックポイント追記・resume スキップ・協調的中断を組み込む
  - `c2m_export/assessment/collector.py` を更新する（design §2, §3.1）。
    - `Collector.__init__` に既定値付き引数を追加: `checkpoint_store=None` / `resume_collected_ids=None` / `interrupt_checker=None`。
    - `collect()` の `visited_page_ids` 初期化時に `resume_collected_ids` を投入し、収集済み page_id を再取得しない（子ページ探索は従来どおり行い未収集の子を積む）。
    - DFS ループ先頭で `interrupt_checker` が True を返したら、収集済み `raw_inventory` を保持したまま内部例外 `CollectInterrupted` を送出する（`checkpoint.py` か `collector.py` に定義）。
    - `inventory.pages.append(page_meta)` 直後に `if self.checkpoint_store: self.checkpoint_store.append_page(page_meta)` を追加する。
  - 既存の収集ロジック（ページ取得・添付・制限・詳細調査）は一切変更しない。
  - `tests/test_collector_checkpoint.py` を作成し、モック client で (a) 追記が収集件数ぶん呼ばれる、(b) `resume_collected_ids` のページがスキップされ未収集分のみ `pages` に追加される、(c) `interrupt_checker` が途中で True を返すと `CollectInterrupted` が送出され収集済みは保持される、を検証する。
  - 完了条件: 追記・resume スキップ・協調的中断が既存挙動を壊さずに機能する。
  - _要件: 1.1, 2.1, 2.2, 4.1_

## フェーズ 4: run_analysis のライフサイクル統括

- [ ] 5. run_analysis にチェックポイント生成・resume 復元・partial 構築を実装する
  - `c2m_export/analysis/api.py` の `run_analysis` を更新する（design §3）。
    - シグネチャに `interrupt_checker: Optional[Callable[[], bool]] = None` を追加（既定 None で既存挙動不変）。
    - 起点解決後に `compute_scope_hash(...)` を算出し、チェックポイント有効時に `checkpoint_dir / f"{scope_hash}.jsonl"` で `CheckpointStore` を生成する。
    - `resume` 指定かつストア存在かつ `scope_matches` が真なら `load_collected()` で復元し、復元 PageMeta を `collector.raw_inventory.pages` に先行投入、収集済み集合と破損行数を保持する。スコープ不一致時は復元せず日本語警告ログ。
    - `collector.collect()` を `interrupt_checker` 付きで実行。`CollectInterrupted` を捕捉したら partial 経路へ分岐する。
    - partial 経路: そこまでの `raw_inventory` で `analyze_inventory()` 以降を実行し、`status="partial"`、`uncertainties` に `interrupted=True` / `interrupted_reason`（`signal` or `error`）/ `collected_page_count` / `resumed_from_checkpoint` / `checkpoint_reused_count` / `checkpoint_corrupted_line_count` を設定する。
    - 正常完了経路: 従来どおり `status="ok"` を構築し、`finalize(success=True)` でチェックポイントを後始末する（新 uncertainties キーは既定値で埋める）。
    - 収集フェーズ中の回復不能エラーで収集済みが1件以上ある場合は partial（`interrupted_reason="error"`、元エラーは detail/ログ）、収集前の致命エラー（起点解決の 401/403/404・パラメータ不正）は従来どおり error（partial 化しない）。
  - `schema_version` リテラルを `1.2` に揃える（タスク 3 と整合）。既存の正常系・エラー系の分岐は壊さない。
  - `tests/test_run_analysis_checkpoint.py` を作成し、(a) 正常完了で `status="ok"` + チェックポイント削除、(b) `interrupt_checker` が True を返すと `status="partial"` + `uncertainties.interrupted`、(c) resume 復元で `checkpoint_reused_count`/`resumed_from_checkpoint` 反映、(d) スコープ不一致で復元しない、を検証する。
  - 完了条件: チェックポイントのライフサイクルと partial 判定が仕様どおり統括される。
  - _要件: 2.1, 2.3, 2.5, 3.1, 3.3, 3.4, 4.1, 5.5_

## フェーズ 5: パラメータ・設定の拡張

- [ ] 6. AnalysisParams / AnalysisConfig にチェックポイント設定を追加する
  - `c2m_export/analysis/params.py` の `AnalysisParams` に既定値付きで追加: `checkpoint_enabled: bool=True` / `resume: bool=False` / `checkpoint_interval: int=1` / `checkpoint_dir: str=".c2m_analyze_checkpoint"`。`validate()` に `checkpoint_interval >= 1` の境界チェックを追加する。
  - `c2m_export/config.py` の `AnalysisConfig` に同名属性を追加し、`load()` で以下を解決する（既存 0008 オプションと同じパターン）。
    - YAML `analysis` セクション: `checkpoint_enabled` / `resume` / `checkpoint_interval` / `checkpoint_dir`。
    - CLI 引数: `--no-checkpoint`（`checkpoint_enabled=False`）/ `--resume`（`resume=True`）/ `--checkpoint-interval N` / `--checkpoint-dir PATH`。既定は未指定で「チェックポイント ON・resume OFF・interval 1・既定ディレクトリ」。
  - 優先順位（CLI > 環境変数 > YAML > デフォルト）を踏襲する。
  - `tests/test_analyze_config_checkpoint.py`（または既存 config テスト）で、各経路の解決と既定値、`--no-checkpoint`/`--resume`/`--checkpoint-interval`/`--checkpoint-dir` の反映を検証する。
  - 完了条件: 新設定が全経路で正しく解決され、既定が仕様どおりになる。
  - _要件: 5.3, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

## フェーズ 6: CLI 層（シグナル・partial 出力・終了コード）

- [ ] 7. analyze.py にシグナル捕捉・partial 出力・終了コード 6 を実装する
  - `c2m_export/analyze.py` を更新する（design §4）。
    - モジュールスコープの中断フラグ（`threading.Event`）を用意し、`signal.signal(SIGINT, handler)` を登録。`SIGTERM` は `try/except` で登録可能なら登録（Windows ベストエフォート）。ハンドラはフラグをセットするのみ。
    - `AnalysisConfig` から `checkpoint_enabled`/`resume`/`checkpoint_interval`/`checkpoint_dir` を読み、`AnalysisParams` に渡す。`run_analysis(params, config, interrupt_checker=flag.is_set)` を呼ぶ。
    - `EXIT_CODES` に `CODE_PARTIAL`（新定数、`response.py` に追加）→ `6` を加える。`status == "partial"` のとき JSON を stdout に出力し、stderr に「部分成功結果を出力した・`--resume` で再開可能」と日本語案内して終了コード 6 で終了する。
    - `--no-checkpoint` 時は `CheckpointStore` を生成しない（run_analysis 側が checkpoint_enabled=False を尊重）。
  - 既存の `ok`/`error` 経路・サニタイズ（`sanitize_text`）・stdout/stderr 分離は不変。
  - `tests/test_analyze_cli_checkpoint.py` を作成し、(a) `--no-checkpoint` でストア未生成、(b) partial 時の終了コード 6 と stderr 案内、(c) `--resume`/`--checkpoint-*` のパラメータ伝播を検証する（run_analysis はモック/スタブ可）。
  - 完了条件: シグナルで partial 出力・終了コード 6・再開案内が成立し、既存経路が壊れない。
  - _要件: 3.5, 4.1, 4.2, 4.3, 4.4, 7.3_

## フェーズ 7: Skill / MCP / ドキュメント更新

- [ ] 8. Skill 定本・複製・MCP の記述を更新する
  - `skills/confluence-analysis/SKILL.md`（正本）を更新し、`--resume`/`--no-checkpoint`/`--checkpoint-interval`/`--checkpoint-dir` の説明、`status: "partial"` と終了コード 6、新 `uncertainties` キー、`schema_version` 1.2 を反映する。
  - 正本から `.github/skills/confluence-analysis/SKILL.md` と `.kiro/skills/confluence-analysis/SKILL.md` へ**上書きコピー**で同期する（structure ルールの「正本編集→複製へ同期」を厳守）。
  - `c2m_export/mcp_server.py` の分析ツール説明・スキーマ記述に partial・新キーを反映する（MCP は `interrupt_checker` 未指定で従来どおり ok/error のみとなる旨も明記）。
  - 完了条件: Skill 3 箇所と MCP が新オプション・新 status・新キーで一致する。
  - _要件: 8.5_

- [ ] 9. README・設定サンプル・steering を更新する
  - `README.md` / `README_DEV.md` に、チェックポイント既定 ON・`--resume` 再開・partial（終了コード 6）・flush 粒度・保存先、大規模スペースでの中断耐性の運用を追記する。
  - `c2m_config_sample.yaml` の `analysis` セクションに `checkpoint_enabled`/`resume`/`checkpoint_interval`/`checkpoint_dir` のサンプルを追加する。
  - `.gitignore` に `.c2m_analyze_checkpoint/` を追加する（出力副産物の除外）。
  - `.kiro/steering/*.md`（tech/structure/product）に、分析モードの新オプション・新モジュール `analysis/checkpoint.py`・終了コード 6 を反映する。
  - 完了条件: ドキュメント・サンプル・steering・gitignore が実装と一致する。
  - _要件: 8.5_

## フェーズ 8: 後方互換・安全性・全体品質

- [ ] 10. 後方互換・認証非漏洩・全体品質を検証する
  - 既存の analyze 系テスト（`tests/test_*analy*`・response/config/collector 既存テスト）が**変更なしで通る**ことを確認する（既定挙動は従来 + 追記のみ増加、出力 JSON の既存キー不変）。
  - チェックポイントファイルにトークン等の秘匿情報が含まれないことをテストで確認する（`page_meta_to_record` の出力にトークンフィールドが無いこと、ヘッダ `scope` に token を入れないこと）。_要件: 8.3, 8.4_
  - `status="partial"` でも stdout は JSON 単独・stderr にログ分離が保たれることを確認する。_要件: 3.5, 7.5_
  - チェックポイント書込失敗時に通常実行へフォールバックし、現象/原因/対処の日本語で報告されることを確認する。_要件: 5.4_
  - `$env:PYTHONPATH="."; python -m pytest` 全通過、`pre-commit run --all-files`（trailing-whitespace/end-of-file/check-yaml/mypy 等）通過を確認する。
  - 完了条件: 全テスト・pre-commit 通過、後方互換・秘匿非漏洩・出力分離・フォールバックが担保される。
  - _要件: 7.1, 7.2, 7.4, 7.5, 8.1, 8.2, 8.3_
