"""Confluence アセスメント（分析モード）のエントリーポイント."""

import logging
import sys
from datetime import datetime
from typing import List

from c2m_export.assessment.analyzers import analyze_inventory
from c2m_export.assessment.collector import Collector
from c2m_export.assessment.report import write_reports
from c2m_export.config import AssessConfig
from c2m_export.confluence import ConfluenceClient
from c2m_export.utils import bytes_to_mb

logger = logging.getLogger(__name__)


def resolve_roots(client: ConfluenceClient, config: AssessConfig) -> List[str]:
    """root_page_ids および space_keys から最終的なルートページID群を解決する."""
    resolved_ids: List[str] = list(config.root_page_ids)

    for space_key in config.space_keys:
        logger.info(f"Space キー '{space_key}' のトップレベルページを取得中...")
        try:
            root_pages = client.get_space_root_pages(space_key)
            if not root_pages:
                logger.warning(
                    f"Space キー '{space_key}' にトップレベルページが見つかりませんでした。"
                )
            for page in root_pages:
                resolved_ids.append(str(page["id"]))
        except Exception as e:
            logger.error(
                f"現象: Space キー '{space_key}' のトップレベルページ取得に失敗しました。\n"
                f"原因: {e}\n"
                f"対処方法: 指定された Space キーが存在するか、権限があるかを確認してください。"
            )
            sys.exit(1)

    # 重複排除
    seen = set()
    deduped_ids = []
    for x in resolved_ids:
        if x not in seen:
            seen.add(x)
            deduped_ids.append(x)
    return deduped_ids


def main():
    """アセスメントモードのメインエントリーポイント."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    config = AssessConfig()
    try:
        config.load()
        config.validate()
    except Exception as e:
        logger.error(
            f"現象: 設定の読み込みまたは検証に失敗しました。\n"
            f"原因: {e}\n"
            f"対処方法: CLI引数または設定ファイル（c2m_config.yaml）の記述を確認してください。"
        )
        sys.exit(1)

    client = ConfluenceClient(config.base_url, config.token, config.proxy)

    logger.info("アセスメント開始: 分析対象の起点を解決中...")
    root_ids = resolve_roots(client, config)

    if not root_ids:
        logger.error(
            "現象: 分析対象の起点となるページIDが指定されていません。\n"
            "原因: --root-page-id または --space-key のいずれの解決結果も空でした。\n"
            "対処方法: 有効な root_page_id または space_key を指定してください。"
        )
        sys.exit(1)

    logger.info(f"分析起点ページ数: {len(root_ids)} 件。メタデータ収集を開始します...")
    collector = Collector(client, analyze_restrictions=config.analyze_restrictions)
    inventory = collector.collect(root_ids)

    logger.info("メタデータ収集完了。各種ルール判定とリスク集計を実行中...")
    result = analyze_inventory(
        inventory,
        single_file_max_mb=config.single_file_max_mb,
        path_length_limit=config.path_length_limit,
        blocked_extensions=config.blocked_extensions,
        attachment_dir_name=config.attachment_dir_name,
        stale_days=config.stale_days,
        min_body_bytes=config.min_body_bytes,
    )

    timestamp_suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_filename = f"confluence_assessment_{timestamp_suffix}"

    logger.info("分析結果のレポート（Markdown / JSON）を出力中...")
    try:
        md_path, json_path = write_reports(
            result,
            output_dir=config.output_dir,
            base_filename=base_filename,
            report_format=config.report_format,
            overwrite=config.overwrite,
        )
    except Exception as e:
        logger.error(f"レポートの出力に失敗しました: {e}")
        sys.exit(1)

    logger.info("=== アセスメント完了サマリ ===")
    logger.info(f"- 総ページ数: {result.total_pages:,} ページ")
    logger.info(f"- 総添付ファイル数: {result.total_attachments:,} 件")
    total_data_bytes = result.estimated_body_bytes + result.total_attachment_bytes
    logger.info(f"- 推定データ総容量: {bytes_to_mb(total_data_bytes):.2f} MB")
    logger.info(f"- 検出リスク項目数: {len(result.risk_items):,} 件")
    logger.info(f"- スキップされたページ数: {len(inventory.skipped_page_ids):,} 件")
    logger.info(f"- 出力レポート: {md_path} / {json_path}")


if __name__ == "__main__":
    main()
