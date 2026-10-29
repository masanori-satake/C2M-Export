# 権限エクスポート詳細

Confluence ページに設定されたアクセス権限（コンテンツ制限: Read / Read+Write）を単独またはファイルシステムエクスポートと対応付けて記録・出力する権限モード（`python -m c2m_export.permexport`）の詳細ガイドです。

---

## 1. 権限エクスポートモードの実行

Confluence ページに設定されたコンテンツ制限情報を収集しレポートとして出力したい場合は、以下のコマンドを実行します。

```cmd
python -m c2m_export.permexport
```

### 主要なオプション
- `--root-page-id`: 対象を開始するルートページの ID（複数指定可能）
- `--space-key`: 対象を開始する Space キー（複数指定可能）
- `--report-layout`: レポート格納形態 (`aggregate` 集約 | `per_page` 分散 / 既定: `aggregate`)
- `--report-format`: 出力形式 (`md` | `json` | `both` / 既定: `md`)
- `--attachment-dir`: 分散モード時の相対パス計算用添付ディレクトリ名 (既定: `_attachments`)
- `--page-filename-mode`: 分散モード時の相対パス計算用本文ファイル命名方式 (`title` | `index` / 既定: `title`)
- `--overwrite`: 既存のレポートを上書き許可する

---

## 2. レポートと仕様

実行後、指定したフォーマットのレポート (`_permissions.md`, `_permissions.json`) およびサマリファイル (`permexport_summary_<YYYYMMDD_HHMMSS>.txt`) が `output_dir` 配下に出力されます。

※本機能は Confluence 側の権限設定の**記録・参照情報の提供**を目的としており、移行先（SharePoint 等）への権限の自動適用は行いません。また、親からの権限継承の実効展開は行わず、個別制限が「あり」の箇所のみを明確化する設計（継承/制限なしと区別）となっています。

---

[READMEへ戻る](../README.md)
