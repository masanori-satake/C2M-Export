# Design Document

## 施策 1: ルート確認

`analysis/api.py` の `_resolve_roots` で `client.get_page(rid, expand="version")` に変えるだけの最小変更。戻り値は使っていない（存在確認のみ）ため影響はない。

## 施策 2: 子ページ先読み

`Collector.collect` の冒頭で `_prefetch_children(root_ids)` を呼ぶ:

- 起点ごとに `client.get_descendants(rid, type_="page", expand="ancestors", limit=200)` を取得する。開始前に中断判定を行い、中断済みなら `CollectInterrupted`。
- 戻り値が list で非空の場合のみ採用する。各子孫について `ancestors` の末尾を直接の親とし、`children_map[parent].append({"id": ...})` を作る。採用した起点と子孫 ID の集合を「確定済み（covered）」とする。
- DFS の子ページ取得では、対象ページが covered に含まれれば `children_map.get(page_id, [])` を使い、含まれなければ従来の `get_child_pages` を呼ぶ。covered 内のページについては、その子は子孫一覧に必ず現れるため、空リストも正しい答えになる。
- 失敗・空・非 list の場合はその起点を covered に入れず、全てフォールバックする。MagicMock 等の想定外の戻りでも壊れない。
- 子の並びは子孫一覧内の出現順を保持する。収集されるページ集合と階層は並びに依存しないが、巡回順序はこの並びに従う（サーバーの一覧順が子の並びと一致する前提）。

## 施策 3: 全体把握の並列化とセッション分離

- `ConfluenceClient` にスレッドローカルセッションを導入する。`_request` と `download_attachment` は `_get_session()` 経由でスレッド専用セッションを使う（ヘッダ・プロキシは生成時に引き継ぐ）。既存の `self.session` は互換のため残し、メインスレッドのセッションとして初期化する。
- `collect_workspace_overview` の Space 単位処理を `_collect_space_overview_one(sp)` に切り出し、(SpaceMeta, unavailable 種別リスト) を返す純粋な形にする（共有状態へは触らない）。本体は並列度に応じて直列 / `ThreadPoolExecutor` を選び、結果を入力順に inventory へ反映する。中断判定は結果の消費前に行う。
- 並列度は `Collector(concurrency=...)`。解決は params > config > 既定 4（run_analysis で検証: 1 以上の整数）。

## 施策 4: timeout 分離

- `ConfluenceClient.__init__` に `connect_timeout` / `read_timeout`（秒、任意）を追加。どちらか指定があれば `_request` の timeout を `(connect or 10, read or 30)` のタプルにする。未指定なら従来の単一値 30 秒。
- 分析側は `AnalysisConfig` に `--connect-timeout-seconds` / `--read-timeout-seconds`（YAML `analysis.connect_timeout_seconds` / `read_timeout_seconds`）を追加し、`run_analysis` と `estimate_analysis` のクライアント生成時に渡す。他モードは未指定のまま従来動作。

## 並列度と負荷について

既定 4 は計画ドキュメントの案を採用した。対象 Confluence の負荷許容が小さい環境では `--concurrency 1`〜`2` に落とせる。429 時はリクエスト単位のバックオフ・リトライが働くが、並列全体でのレート制御（共有トークンバケット等）は今回入れず、今後の課題とする。
