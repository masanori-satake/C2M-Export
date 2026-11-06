# Tasks: 子孫数取得の失敗可視化とタイムアウト延長（spec 0021）

- [x] T1 collector: 子孫数取得の失敗件数を数え、部分失敗は `descendant_count_partial`、全件失敗は `descendant_count` を unavailable に記録する。SpaceMeta に `page_count_preview_partial` を追加し、workspace 出力では true のときだけキーを含める
- [x] T2 estimate: 見積もり辞書に `may_be_underestimated` を追加する
- [x] T3 timeout: config（CLI / YAML / 検証）→ api・estimate の client_kwargs → ConfluenceClient の `count_read_timeout` を通し、`get_descendant_page_count` だけに適用する
- [x] T4 テスト: collector / estimate / confluence / config に回帰テストを追加し、全件実行と ruff・mypy を確認する
- [x] T5 文書: README.md / README_DEV.md、スキル文書（options.md / output_schema.md / SKILL.md）を更新し、正本と複製先の同期を確認する
