"""権限エクスポート CLI エントリーポイント.

実行コマンド:
    python -m c2m_export.permexport [オプション]
"""

import logging
import sys

from c2m_export.config import PermissionExportConfig
from c2m_export.confluence import ConfluenceClient
from c2m_export.permission.collector import collect_permissions
from c2m_export.permission.report import write_permission_report
from c2m_export.permission.summary import write_summary

logger = logging.getLogger(__name__)


def main():
    """権限エクスポート処理のメイン関数."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    logger.info("Confluence 権限エクスポート処理を開始します。")

    config = PermissionExportConfig()
    try:
        config.load()
        config.validate()
    except Exception as e:
        logger.error(
            f"現象: 設定の読み込みまたは検証に失敗しました。 原因: {e} 対処方法: 引数または c2m_config.yaml を確認してください。"
        )
        sys.exit(1)

    try:
        client = ConfluenceClient(
            base_url=config.base_url,
            token=config.token,
            proxy=config.proxy,
        )

        logger.info(f"Confluence サーバー ({config.base_url}) に接続中...")

        # 権限情報の収集
        result = collect_permissions(
            client=client,
            base_url=config.base_url,
            root_page_ids=config.root_page_ids,
            space_keys=config.space_keys,
            page_filename_mode=config.page_filename_mode,
        )

        # レポート出力
        saved_reports = write_permission_report(
            report=result.report,
            output_dir=config.output_dir,
            report_layout=config.report_layout,
            report_formats=config.report_formats,
            overwrite=config.overwrite,
        )

        for report_file in saved_reports:
            logger.info(f"権限レポートを出力しました: {report_file}")

        # サマリ出力
        write_summary(result=result, output_dir=config.output_dir)

        logger.info("権限エクスポート処理が正常に完了しました。")

    except Exception as e:
        logger.error(
            f"現象: 権限エクスポート処理中に致命的なエラーが発生しました。 原因: {e} 対処方法: エラー詳細およびネットワーク・設定状態を確認してください。"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
