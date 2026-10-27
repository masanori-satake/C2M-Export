"""アセスメントレポート（Markdown および JSON）生成モジュール."""

import json
from pathlib import Path
from typing import Any, Dict

from c2m_export.assessment.models import AssessmentResult
from c2m_export.utils import bytes_to_mb


def bytes_to_gb(b: int) -> float:
    """バイト数をギガバイト（GB）表記の浮動小数に変換する."""
    return b / (1024 * 1024 * 1024)


def format_size(b: int) -> str:
    """バイト数を人間が読みやすい形式（MB/GB）の文字列にフォーマットする."""
    if b >= 1024 * 1024 * 1024:
        return f"{bytes_to_gb(b):.2f} GB ({b:,} bytes)"
    return f"{bytes_to_mb(b):.2f} MB ({b:,} bytes)"


def generate_markdown_report(result: AssessmentResult) -> str:
    """AssessmentResult から Markdown 形式のアセスメントレポート文字列を生成する."""
    lines: list[str] = []

    lines.append("# Confluence アセスメントレポート")
    lines.append("")
    lines.append("> **注意・前提事項**:")
    lines.append(
        "> 本レポートの集計値は Confluence REST API のメタデータに基づいた**概算値**です。"
    )
    lines.append(
        "> 添付ファイルのサイズはメタデータ（実測と同等）から算出していますが、"
        "ページ本文のサイズは Storage Format (XHTML) のUTF-8バイト数から試算しているため、"
        "実際の Markdown 変換後のファイルサイズはタグ削除等により縮小し、やや過大（安全側）に見積もられます。"
    )
    lines.append("")

    # 1. 規模サマリ
    lines.append("## 1. 規模サマリ")
    lines.append(f"- **総ページ数**: {result.total_pages:,} ページ")
    lines.append(f"- **総添付ファイル数**: {result.total_attachments:,} 件")
    lines.append(f"- **推定本文総サイズ**: {format_size(result.estimated_body_bytes)}")
    lines.append(f"- **添付ファイル総サイズ**: {format_size(result.total_attachment_bytes)}")
    lines.append(
        f"- **推定データ総容量**: {format_size(result.estimated_body_bytes + result.total_attachment_bytes)}"
    )
    lines.append(f"- **最大階層深さ**: Level {result.max_depth}")
    lines.append("")

    # Space別内訳
    lines.append("### Space別内訳")
    lines.append("| Space Key | ページ数 | 添付数 | 添付総サイズ |")
    lines.append("|---|---|---|---|")
    for space_key, sdata in sorted(result.space_summary.items()):
        att_bytes_str = format_size(sdata["attachment_bytes"])
        lines.append(
            f"| {space_key} | {sdata['pages']:,} | {sdata['attachments']:,} | {att_bytes_str} |"
        )
    lines.append("")

    # 2. 構造・階層分布
    lines.append("## 2. 構造・階層分布")
    lines.append("| 階層レベル | ページ数 | 割合 |")
    lines.append("|---|---|---|")
    for level, count in sorted(result.level_distribution.items()):
        pct = (count / result.total_pages * 100) if result.total_pages > 0 else 0.0
        lines.append(f"| Level {level} | {count:,} | {pct:.1f}% |")
    lines.append("")

    # 3. 添付ファイル種別集計
    lines.append("## 3. 添付ファイル種別集計（拡張子別・サイズ降順）")
    lines.append("| 拡張子 | 件数 | 合計サイズ | 最大単体サイズ |")
    lines.append("|---|---|---|---|")
    for ext_info in result.extension_summary:
        ext_name = str(ext_info["extension"])
        cnt = int(str(ext_info["count"]))
        tot_size = format_size(int(str(ext_info["total_size"])))
        max_size = format_size(int(str(ext_info["max_size"])))
        lines.append(f"| {ext_name} | {cnt:,} | {tot_size} | {max_size} |")
    lines.append("")

    # 4. 移設リスク・制約の検出（SharePoint / OneDrive 向け）
    lines.append("## 4. 移設リスク・制約の検出")
    lines.append("### リスク種別ごとの件数サマリ")
    if result.risk_summary_counts:
        for rtype, rcnt in sorted(result.risk_summary_counts.items()):
            lines.append(f"- **{rtype}**: {rcnt:,} 件")
    else:
        lines.append("検出されたリスク項目はありません。")
    lines.append("")

    lines.append("### 検出された個別リスク項目一覧")
    if result.risk_items:
        lines.append("| ページID | 対象名 | 種別 | リスク理由 | 想定相対パス |")
        lines.append("|---|---|---|---|---|")
        for item in result.risk_items:
            lines.append(
                f"| {item.page_id} | {item.item_name} | {item.risk_type} | {item.reason} | `{item.target_path}` |"
            )
    else:
        lines.append("検出されたリスク項目はありません。")
    lines.append("")

    # 5. 権限サマリ
    lines.append("## 5. 権限分析サマリ")
    lines.append(f"- **個別アクセス制限ありページ数**: {result.explicit_restriction_count:,} ページ")
    lines.append(f"  - **Read権限のみ設定**: {result.read_only_restriction_count:,} ページ")
    lines.append(f"  - **Read+Write(編集)制限設定**: {result.read_write_restriction_count:,} ページ")
    lines.append(f"- **制限に登場するユニークユーザー数**: {len(result.unique_restriction_users):,} 名")
    if result.unique_restriction_users:
        lines.append(f"  - ユーザー一覧: {', '.join(result.unique_restriction_users[:30])}" + ("..." if len(result.unique_restriction_users) > 30 else ""))
    lines.append(f"- **制限に登場するユニークグループ数**: {len(result.unique_restriction_groups):,} グループ")
    if result.unique_restriction_groups:
        lines.append(f"  - グループ一覧: {', '.join(result.unique_restriction_groups[:30])}" + ("..." if len(result.unique_restriction_groups) > 30 else ""))
    lines.append("")

    # 6. 鮮度・棚卸し分析
    lines.append("## 6. 鮮度・棚卸し分析")
    lines.append(f"- **長期未更新ページ数（1年以上未更新）**: {result.stale_page_count:,} ページ")
    lines.append(f"- **空/極小ページ数（200バイト未満）**: {result.empty_page_count:,} ページ")
    lines.append("")
    lines.append("### 最終更新日時の経過分布")
    fdist = result.freshness_distribution
    lines.append(f"- **30日以内更新**: {fdist.get('within_30_days', 0):,} ページ")
    lines.append(f"- **90日以内更新**: {fdist.get('within_90_days', 0):,} ページ")
    lines.append(f"- **180日以内更新**: {fdist.get('within_180_days', 0):,} ページ")
    lines.append(f"- **1年(365日)以内更新**: {fdist.get('within_365_days', 0):,} ページ")
    lines.append(f"- **1年以上前更新**: {fdist.get('over_365_days', 0):,} ページ")
    lines.append(f"- **更新日時不明**: {fdist.get('unknown', 0):,} ページ")
    lines.append("")

    # 7. 不確実性・スキップ情報
    lines.append("## 7. 不確実性・スキップサマリ")
    inv = result.raw_inventory
    lines.append(f"- **スキップされたページ数**: {len(inv.skipped_page_ids):,} 件")
    lines.append(f"- **添付一覧取得失敗参照数**: {len(inv.skipped_attachment_refs):,} 件")
    lines.append(f"- **権限情報取得失敗ページ数**: {len(inv.restriction_failed_page_ids):,} 件")
    lines.append(f"- **fileSize メタデータ欠落添付数**: {inv.size_meta_missing_count:,} 件")
    lines.append("")

    return "\n".join(lines)


def generate_json_report(result: AssessmentResult) -> Dict[str, Any]:
    """AssessmentResult から機械可読な JSON 用辞書オブジェクトを構築する."""
    data: Dict[str, Any] = {
        "summary": {
            "total_pages": result.total_pages,
            "total_attachments": result.total_attachments,
            "estimated_body_bytes": result.estimated_body_bytes,
            "total_attachment_bytes": result.total_attachment_bytes,
            "max_depth": result.max_depth,
            "level_distribution": result.level_distribution,
            "space_summary": result.space_summary,
        },
        "attachments": {
            "extension_summary": result.extension_summary,
            "mime_summary": result.mime_summary,
            "size_meta_missing_count": result.raw_inventory.size_meta_missing_count,
        },
        "risks": {
            "summary_counts": result.risk_summary_counts,
            "items": [
                {
                    "page_id": item.page_id,
                    "item_name": item.item_name,
                    "target_path": item.target_path,
                    "risk_type": item.risk_type,
                    "reason": item.reason,
                }
                for item in result.risk_items
            ],
        },
        "restrictions": {
            "explicit_restriction_count": result.explicit_restriction_count,
            "read_only_restriction_count": result.read_only_restriction_count,
            "read_write_restriction_count": result.read_write_restriction_count,
            "unique_users": result.unique_restriction_users,
            "unique_groups": result.unique_restriction_groups,
            "fetch_failed_count": len(result.raw_inventory.restriction_failed_page_ids),
        },
        "freshness": {
            "stale_page_count": result.stale_page_count,
            "empty_page_count": result.empty_page_count,
            "freshness_distribution": result.freshness_distribution,
        },
        "uncertainties": {
            "skipped_page_ids": result.raw_inventory.skipped_page_ids,
            "skipped_attachment_refs": result.raw_inventory.skipped_attachment_refs,
            "restriction_failed_page_ids": result.raw_inventory.restriction_failed_page_ids,
        },
    }
    return data


def write_reports(
    result: AssessmentResult,
    output_dir: str,
    base_filename: str,
    report_format: str = "both",
    overwrite: bool = False,
) -> tuple[Path, Path]:
    """Markdown および JSON レポートを出力ディレクトリに書き出す.

    returns: (markdown_path, json_path)
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    md_path = out_dir / f"{base_filename}.md"
    json_path = out_dir / f"{base_filename}.json"

    if not overwrite:
        if (report_format in ("both", "md") and md_path.exists()) or (
            report_format in ("both", "json") and json_path.exists()
        ):
            raise FileExistsError(
                f"現象: 出力先レポートファイルが既に存在します。\n"
                f"原因: {md_path} または {json_path} が存在し、上書き（overwrite）が有効になっていません。\n"
                f"対処方法: 既存ファイルを削除するか、--overwrite オプションを指定して再実行してください。"
            )

    if report_format in ("both", "md"):
        md_text = generate_markdown_report(result)
        md_path.write_text(md_text, encoding="utf-8")

    if report_format in ("both", "json"):
        json_data = generate_json_report(result)
        json_path.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8")

    return md_path, json_path
