"""退避ディレクトリ操作モジュール.

削除同期時にローカル出力を退避ディレクトリ (`_c2m_quarantine/<timestamp>/...`) へ構造ごと移動または物理削除・報告のみを行う。
"""

import logging
import os
import shutil
from datetime import datetime

logger = logging.getLogger(__name__)


def quarantine_path(
    rel_path: str,
    output_dir: str,
    deletion_policy: str = "quarantine",
    quarantine_dir_name: str = "_c2m_quarantine",
    timestamp: str = "",
) -> None:
    """指定されたローカル出力相対パスを、deletion_policy に従って移動・削除する.

    Args:
        rel_path: 出力ルートディレクトリからの相対パス (例: "【SPACE】ルート/子ページ")
        output_dir: エクスポート出力先ルートディレクトリ
        deletion_policy: 削除方針 ("quarantine" | "delete" | "report")
        quarantine_dir_name: 退避ルートディレクトリ名 (既定: "_c2m_quarantine")
        timestamp: 退避サブディレクトリ用のタイムスタンプ (未指定時は現在時刻 YYYYMMDD_HHMMSS)
    """
    # セキュリティ対策: パストラバーサル (Path Traversal) を防止するため、指定されたパスが出力ディレクトリ外を指していないか検証
    output_dir_abs = os.path.abspath(output_dir)
    target_abs = os.path.abspath(os.path.join(output_dir, rel_path))

    if os.path.commonpath([output_dir_abs, target_abs]) != output_dir_abs:
        logger.error(
            f"現象: 出力ディレクトリ外のパスが指定されました ({rel_path})。 原因: パストラバーサルの可能性があります。 対処方法: 正しい相対パスを指定してください。"
        )
        raise ValueError(f"無効な相対パスです (ディレクトリトラバーサルの検知): {rel_path}")

    if not os.path.exists(target_abs):
        logger.info(f"退避/削除対象のパスが存在しません (スキップ): {rel_path}")
        return

    if deletion_policy == "report":
        logger.info(f"[削除同期-報告のみ] Confluence 上で削除された項目を検知しました: {rel_path}")
        return

    if deletion_policy == "delete":
        try:
            if os.path.isdir(target_abs):
                shutil.rmtree(target_abs)
            else:
                os.remove(target_abs)
            logger.info(f"[削除同期-物理削除] ローカル出力を物理削除しました: {rel_path}")
        except Exception as e:
            logger.error(
                f"現象: ローカル出力 ({rel_path}) の物理削除に失敗しました。 原因: {e} 対処方法: ファイルのアクセス権限または他プロセスによるロックを確認してください。"
            )
        return

    # deletion_policy == "quarantine" (既定)
    if not timestamp:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    dest_dir = os.path.join(output_dir, quarantine_dir_name, timestamp, os.path.dirname(rel_path))
    dest_abs = os.path.join(dest_dir, os.path.basename(rel_path))

    try:
        os.makedirs(dest_dir, exist_ok=True)
        # 移設先に既存がある場合は退避先の衝突を回避する
        if os.path.exists(dest_abs):
            suffix = f"_{datetime.now().strftime('%H%M%S_%f')}"
            dest_abs = dest_abs + suffix

        shutil.move(target_abs, dest_abs)
        logger.info(
            f"[削除同期-退避] ローカル出力を退避先へ移動しました: {rel_path} -> {os.path.relpath(dest_abs, output_dir)}"
        )
    except Exception as e:
        logger.error(
            f"現象: 退避ディレクトリへの移動に失敗しました。 原因: {e} 対処方法: 出力先のアクセス権限とディスク空き容量を確認してください。"
        )
