# Design: 子孫数取得の失敗可視化とタイムアウト延長（spec 0021）

## R1 全体把握の部分失敗の可視化（`c2m_export/assessment/collector.py`）

`_collect_space_overview_one` の子孫数取得ループで失敗件数を数える。

- 一部失敗（一部成功）: `unavailable` に `"descendant_count_partial"` を追加し、`SpaceMeta.page_count_preview_partial = True` とする。プレビュー件数は従来どおり成功分のみで公開するが、欠けていることが機械可読になる。
- 全件失敗（ルートページはあるが 1 件も成功しない）: プレビューは従来どおり `None` のままとし、`unavailable` に `"descendant_count"` を追加する（取得できなかった事実が残るようにする）。
- ルートページ一覧そのものの取得失敗: 従来どおり `"descendant_count"`（変更しない）。
- 失敗 0 件: `unavailable` にも SpaceMeta にも変化なし。

`SpaceMeta`（`c2m_export/assessment/models.py`）に `page_count_preview_partial: bool = False` を追加する。出力側（`c2m_export/analysis/workspace.py`）では、このキーは `True` のときだけ Space の辞書に含める。失敗がない通常ケースの JSON 出力は従来と完全同一に保つ。

## R2 見積もりの過小評価フラグ（`c2m_export/analysis/estimate.py`）

見積もり辞書に `"may_be_underestimated": bool(count_failed_root_page_ids)` を追加する。`count_failed_root_page_ids` と並んで常時出力される機械可読フラグで、スキル側は `is_large` と組み合わせて判断できる。既存の notes の文章（「過小評価の可能性があります」）は人間向けとして残す。

## R3 子孫数取得専用の読み取りタイムアウト

既存の connect / read タイムアウト（spec 0014）と同じ経路で新設定を通す。

- `c2m_export/config.py`: `AnalysisConfig` に `descendant_count_read_timeout_seconds: Optional[int] = None` を追加。CLI `--descendant-count-read-timeout-seconds`、YAML `analysis.descendant_count_read_timeout_seconds`、検証（1 以上の整数）は connect / read と同じ扱い。
- `c2m_export/analysis/api.py` / `c2m_export/analysis/estimate.py`: クライアント生成時に、設定があれば `client_kwargs["count_read_timeout"]` を渡す。
- `c2m_export/confluence.py`: `ConfluenceClient(count_read_timeout=...)` を追加。内部では接続タイムアウト部（分離指定時はその connect 値、分離なしの単一値のときはその値）と組み合わせた `(connect, count_read)` タプルを保持する。`_request` に 1 回限りのタイムアウト上書き引数を追加し、`get_descendant_page_count` だけがそれを使う。未指定時は `None` で、従来の `self._request_timeout` がそのまま使われる。

対象は分析経路（本実行・見積もり）のみとし、他のエントリーポイントのクライアント生成は変更しない（connect / read の扱いと揃える）。

## スキル文書の更新

- `references/options.md`: `--descendant-count-read-timeout-seconds` を追加（正本＋ `.github` / `.kiro` の複製）。
- `references/output_schema.md`: `unavailable_apis` の値に `descendant_count_partial`、Space 出力の `page_count_preview_partial`、見積もりの `may_be_underestimated` を追記。
- `SKILL.md`: 決定表の近くに、`may_be_underestimated` が true のときは `is_large` が false でも過小の可能性を断って判断する旨を 1 行追加する（フラグを判断に使うための最小の変更）。

## テスト

- collector: 部分失敗で `descendant_count_partial` と SpaceMeta のフラグが立つこと、全件失敗で `descendant_count` が記録されプレビューが `None` のこと、失敗なしでは出力（workspace 辞書）に新キーが現れないこと。
- estimate: 子孫数取得失敗時に `may_be_underestimated` が true、成功時は false であること。
- confluence: `count_read_timeout` 指定時に子孫数取得だけタイムアウトが上書きされ、他メソッドは従来どおりであること。config の YAML / CLI / 検証は既存の connect / read テストに倣う。
