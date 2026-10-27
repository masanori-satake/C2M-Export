"""処理サマリの生成とファイル出力モジュール.

エクスポート実行結果 (ExportResult) から成功数・総サイズ・各スキップの内訳・失敗/スキップ個別一覧を含めたテキストサマリを生成し、
標準出力ログへの報告および実行日時サフィックス付きサマリファイルへの書き出しを行う。
"""

import logging
import os
from datetime import datetime
from typing import Optional, Tuple

from c2m_export.fs_export.models import ExportResult
from c2m_export.utils import bytes_to_gb, bytes_to_mb

logger = logging.getLogger(__name__)


def generate_summary_text(
    result: ExportResult,
    timestamp_str: str,
    diff_counts: Optional[dict] = None,
) -> str:
    """エクスポート実行結果から日本語サマリテキストを生成する.

    Args:
        result: エクスポート実行結果オブジェクト
        timestamp_str: 実行日時文字列 (YYYY-MM-DD HH:MM:SS)
        diff_counts: 差分判定件数ディクショナリ (追加, 変更, 削除, 移動/改名, 未変更, 失敗)

    Returns:
        サマリ本文テキスト
    """
    total_mb = bytes_to_mb(result.total_bytes)
    total_gb = bytes_to_gb(result.total_bytes)

    lines = [
        "==================================================",
        " Confluence ファイルシステムエクスポート 実行サマリ",
        "==================================================",
        f"実行日時: {timestamp_str}",
    ]

    if diff_counts:
        lines.extend(
            [
                f"新規追加ページ数: {diff_counts.get('add', 0)}",
                f"変更更新ページ数: {diff_counts.get('change', 0)}",
                f"移動・改名ページ数: {diff_counts.get('move_rename', 0)}",
                f"削除同期ページ数: {diff_counts.get('delete', 0)}",
                f"再利用（未変更スキップ）ページ数: {diff_counts.get('unchanged', 0)}",
            ]
        )

    lines.extend(
        [
            f"出力成功ページ数: {result.total_pages}",
            f"出力成功添付ファイル数: {result.total_attachments}",
            f"総出力サイズ: {total_mb:.2f} MB ({total_gb:.2f} GB)",
            f"スキップ・失敗ページ数: {len(result.skipped_pages)}",
            f"スキップ・失敗添付ファイル数: {len(result.skipped_attachments)}",
            f"相対リンク未解決件数: {result.unresolved_links_count}",
            f"名称衝突等のリネームノード数: {len(result.renamed_nodes)}",
            "",
        ]
    )

    if result.renamed_nodes:
        lines.append("【名称衝突・リネーム一覧】")
        for p_id, info in result.renamed_nodes.items():
            lines.append(f"  - ページ ID {p_id}: {info}")
        lines.append("")

    if result.skipped_pages:
        lines.append("【スキップ・失敗ページ一覧】")
        for rec in result.skipped_pages:
            lines.append(f"  - [{rec.target_id}] {rec.title_or_name} (パス: {rec.path}): {rec.reason}")
        lines.append("")

    if result.skipped_attachments:
        lines.append("【スキップ・失敗添付ファイル一覧】")
        for rec in result.skipped_attachments:
            sz_info = f", {bytes_to_mb(rec.size_bytes):.2f} MB" if rec.size_bytes > 0 else ""
            lines.append(f"  - [{rec.target_id}] {rec.title_or_name}{sz_info} (パス: {rec.path}): {rec.reason}")
        lines.append("")

    lines.append("==================================================")
    return "\n".join(lines)


def write_summary(
    result: ExportResult,
    output_dir: str,
    execution_dt: Optional[datetime] = None,
    diff_counts: Optional[dict] = None,
) -> Tuple[str, str]:
    """サマリテキストを標準出力ログに出力し、実行日時サフィックス付きファイルとして書き出す.

    Args:
        result: エクスポート実行結果
        output_dir: 出力先ディレクトリ
        execution_dt: 実行日時 (未指定時は現在日時)

    Returns:
        Tuple[サマリ本文テキスト, サマリファイルパス]
    """
    if execution_dt is None:
        execution_dt = datetime.now()

    formatted_time = execution_dt.strftime("%Y-%m-%d %H:%M:%S")
    suffix_time = execution_dt.strftime("%Y%m%d_%H%M%S")

    summary_text = generate_summary_text(result, formatted_time, diff_counts=diff_counts)

    # ログ出力
    logger.info("\n" + summary_text)

    # ファイル書き出し (例: fsexport_summary_20260201_120000.txt)
    file_name = f"fsexport_summary_{suffix_time}.txt"
    file_path = os.path.join(output_dir, file_name)

    try:
        os.makedirs(output_dir, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(summary_text)
        logger.info(f"実行サマリをファイルに出力しました: {file_path}")
    except Exception as e:
        logger.error(
            f"現象: サマリファイルの書き込みに失敗しました ({file_path})。 原因: {e} 対処方法: 出力先ディレクトリのパーミッションを確認してください。"
        )

    return summary_text, file_path
