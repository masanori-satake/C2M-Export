# Requirements Document

## はじめに

confluence-analysis スキルの `SKILL.md` は 259 行・推定 5,509 トークン（tiktoken cl100k_base で計測）に達し、SkillMap-Solo の R5（SKILL.md 推定トークン上限）の既定値 5,000 トークンを超過している。実行のたびに読み込まれる本体には「毎回の判断に使う情報」だけを残し、「特定の場面でだけ要る情報」を references/ へ分離して、本体の読み込みコストを下げる。計測の内訳と分離案は `~/workspace/goals/kiro-and-copilot-skill-credit-minimisation/files/c2m-skill-token-breakdown-and-split-plan.md` に記録した。

現行の内訳（トークン順）: 入力パラメータ全表 1,709（31.6%）、Windows 注意事項 974（18.0%）、出力 JSON スキーマ 603（11.1%）、非同期実行手順 593（11.0%）、その他は手順と判断ルール。

## 要件

### 要件 1: references への分離

#### 受け入れ基準

1. THE オプション全表 SHALL `references/options.md` へ移し、本体には頻出オプションの抜粋のみを残す。
2. THE 出力 JSON スキーマの詳細と `schema_version` 互換性ポリシー SHALL `references/output_schema.md` へ移し、本体には「結果の読み方」の要点のみを残す。
3. THE Windows 注意事項 SHALL 本体に要点版を残し、詳細を `references/windows_notes.md` へ移す。
4. THE 本体 SHALL 各 references について「いつ読むか」を明記したポインタを持つ。

### 要件 2: 内容の保全

#### 受け入れ基準

1. THE 分離によって情報 SHALL 失われない（移した先に全量が存在すること）。
2. THE 手順・判断ルール（見積もりの読み方、大きな対象での判断、非同期実行の作法、終了コード規約）SHALL 本体に残り、従来どおり機能する。
3. THE 本体の推定トークン数 SHALL 分離後に 5,000 トークン（R5 既定上限）を下回る。

### 要件 3: 同期と整合

#### 受け入れ基準

1. THE references SHALL 正本 `skills/` から `.github/skills/` と `.kiro/skills/` へ、SKILL.md と同じく複製同期される。
2. THE SKILL.md 内の参照 SHALL 相対パスで記述し、参照切れを作らない。
