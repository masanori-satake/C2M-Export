# Design Document

## 分離の原則

- 本体 = 毎回の実行で判断に使う情報（前提、手順、判断ルール、頻出オプションの抜粋、結果の読み方の要点、終了コード）。
- references = 必要なときだけ引く情報（オプション全表、出力スキーマ詳細、Windows 注意事項の詳細）。
- 各 references へのポインタには「いつ読むか」を併記し、エージェントが必要な場面でだけ開くよう誘導する。

## ファイル構成（分離後）

```
skills/confluence-analysis/
  SKILL.md                （要点版、実測 3,692 トークン / 156 行）
  references/
    options.md            （オプション全表、実測 1,820 トークン）
    output_schema.md      （出力スキーマ詳細＋互換性ポリシー、実測 828 トークン）
    windows_notes.md      （Windows 注意事項の詳細、実測 1,025 トークン）
  scripts/                （変更なし）
```

実測結果（tiktoken cl100k_base）: 本体は 5,509 → 3,692 トークン（−1,817、−33%）、259 行 → 156 行。R5 既定上限 5,000 を下回った。ポインタは専用節ではなく各節の末尾・冒頭に inline で配置した（Windows 節→windows_notes、オプション節→options、結果の読み方→output_schema）。

複製先（`.github/skills/confluence-analysis/`、`.kiro/skills/confluence-analysis/`）にも references/ を含めて同一構成で同期する。README_DEV のスキル管理方針にも references の同期を明記する。

## 本体に残すオプション抜粋の選定

通常の調査分析で使うものに絞る: 対象指定（base-url / space-key / root-page-id / all-spaces / cql）、usecase、mode、limit、stale-days、restrictions の有無、deep、resume、timeout-seconds、max-pages、estimate、detach とジョブ操作（job-status / job-result / job-cancel）、concurrency、token。その他のオプション（collect 系の個別制御、checkpoint 系、stale-years、min-body-bytes、archive-ext、timeout 分離、proxy、config、job-dir）は references/options.md に全量を残す。

## 効果の見込みと限界

- 典型的な実行では references は読まれず、1回あたり約 1,800 トークンの削減（実測ベース）。
- 全 references を読む最悪ケースでも現行とほぼ同等で、悪化しない。
- 効果はエージェントがポインタに従う前提であり、分離後にクレジット計測の標準テストで実測して確認する（本 spec の範囲外）。
