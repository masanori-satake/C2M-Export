# Implementation Plan

0015 SKILL.md の references 分離の実装計画。

- [x] 1. references 3ファイルを作成する
  - options.md（全表）、output_schema.md（スキーマ詳細＋互換性ポリシー）、windows_notes.md（Windows 詳細）。
  - _要件: 1.1, 1.2, 1.3, 2.1_

- [x] 2. SKILL.md を要点版に再構成する
  - Windows 要点版、オプション抜粋、結果の読み方の要点、各 references へのポインタ（いつ読むか付き）。
  - _要件: 1.1, 1.2, 1.3, 1.4, 2.2_

- [x] 3. 複製先へ同期し、効果を計測する
  - `.github/skills/` と `.kiro/skills/` へ SKILL.md と references を同期。分離後の本体トークンを計測し R5 上限以下を確認。README_DEV のスキル管理方針を更新。
  - _要件: 2.3, 3.1, 3.2_
