"""処理サマリ (summary) モジュール.

権限エクスポート処理結果 (PermissionResult) を集計し、
標準出力ログへの結果表示および日時サフィックス付きテキストファイルへの書き出しを行う。
"""

import logging
import os
from datetime import datetime

from c2m_export.permission.models import PermissionResult

logger = logging.getLogger(__name__)


def write_summary(result: PermissionResult, output_dir: str) -> str:
    """処理サマリをログ出力し、日時サフィックス付きファイルへ書き出す.

    Args:
        result: PermissionResult インスタンス
        output_dir: 出力先ディレクトリ

    Returns:
        作成されたサマリファイルのパス
    """
    now = datetime.now()
    timestamp_str = now.strftime("%Y%m%d_%H%M%S")
    formatted_now = now.strftime("%Y-%m-%d %H:%M:%S")

    summary_lines = [
        "==================================================",
        " Confluence 権限エクスポート 実行サマリ",
        "==================================================",
        f"実行日時: {formatted_now}",
        f"処理ページ総数: {result.exported_count} 件",
        f"  - 個別制限あり: {result.explicit_count} 件",
        f"  - 継承/制限なし: {result.inherited_count} 件",
        f"  - 取得失敗: {len(result.failed_page_ids)} 件",
    ]

    if result.failed_page_ids:
        summary_lines.append("")
        summary_lines.append("【取得失敗ページ ID 一覧】")
        for pid in result.failed_page_ids:
            summary_lines.append(f"  - {pid}")

    summary_lines.append("==================================================")
    summary_text = "\n".join(summary_lines)

    # ログ出力
    for line in summary_lines:
        logger.info(line)

    # サマリファイル出力
    os.makedirs(output_dir, exist_ok=True)
    summary_filename = f"permexport_summary_{timestamp_str}.txt"
    summary_path = os.path.join(output_dir, summary_filename)

    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary_text + "\n")

    logger.info(f"サマリファイルを保存しました: {summary_path}")
    return summary_path
