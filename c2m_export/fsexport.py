"""ファイルシステムエクスポート CLI エントリーポイント.

python -m c2m_export.fsexport
"""

import logging
import os
import sys

from c2m_export.config import FsExportConfig
from c2m_export.confluence import ConfluenceClient
from c2m_export.converter import MarkdownConverter
from c2m_export.fs_export.summary import write_summary
from c2m_export.fs_export.tree import build_page_tree
from c2m_export.fs_export.writer import export_tree_fs

logger = logging.getLogger(__name__)


def main():
    """ファイルシステムエクスポートのメイン処理関数."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        config = FsExportConfig()
        config.load()
        config.validate()
    except ValueError as ve:
        logger.error(
            f"現象: 設定の検証に失敗しました。 原因: {ve} 対処方法: --help または設定ファイルを確認してください。"
        )
        sys.exit(1)
    except Exception as e:
        logger.error(
            f"現象: 設定の読み込みに失敗しました。 原因: {e} 対処方法: 設定ファイル等の記述を確認してください。"
        )
        sys.exit(1)

    # フェイルファスト: 出力先書き込み・競合チェック
    out_dir = os.path.abspath(config.output_dir)
    if os.path.exists(out_dir) and os.listdir(out_dir) and not config.overwrite:
        logger.error(
            f"現象: 出力先ディレクトリ ({out_dir}) に既存のファイルが存在します。 原因: --overwrite オプションが指定されていません。 対処方法: 空のディレクトリを指定するか、--overwrite を指定してください。"
        )
        sys.exit(1)

    try:
        os.makedirs(out_dir, exist_ok=True)
        # 書き込み確認用のダミーテスト
        test_file = os.path.join(out_dir, ".c2m_write_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
    except Exception as e:
        logger.error(
            f"現象: 出力先ディレクトリ ({out_dir}) への書き込み権限がありません。 原因: {e} 対処方法: 出力先のアクセス権限を確認してください。"
        )
        sys.exit(1)

    client = ConfluenceClient(config.base_url, config.token, config.proxy)
    converter = MarkdownConverter(config.base_url)

    logger.info("Confluence からページツリー構造を取得しています...")
    root_nodes, renamed_map, visited_ids = build_page_tree(
        client=client,
        root_page_ids=config.root_page_ids,
        space_keys=config.space_keys,
        page_filename_mode=config.page_filename_mode,
        path_length_limit=config.path_length_limit,
    )

    if not root_nodes:
        logger.error(
            "現象: エクスポート対象の起点ページが1つも見つかりませんでした。 原因: 指定された root_page_id または space_key が存在しないか権限がありません。 対処方法: 対象 ID/Space キーおよびアクセストークンを確認してください。"
        )
        sys.exit(1)

    logger.info(f"ツリー探索完了: {len(root_nodes)} 個の起点ノード、全 {len(visited_ids)} ページを検出しました。")
    logger.info("ファイルシステム構造への書き込み・本文変換・添付保存を開始します...")

    result = export_tree_fs(
        client=client,
        converter=converter,
        output_dir=config.output_dir,
        root_nodes=root_nodes,
        attachment_dir_name=config.attachment_dir_name,
        attachment_link_mode=config.attachment_link_mode,
        single_file_max_mb=config.single_file_max_mb,
        exclude_extensions=config.exclude_extensions,
        frontmatter_fields=config.frontmatter_fields,
        base_url=config.base_url,
        renamed_nodes_map=renamed_map,
    )

    logger.info("サマリの出力と完了処理を実行しています...")
    write_summary(result, config.output_dir)

    logger.info("ファイルシステムエクスポートが完了しました。")


if __name__ == "__main__":
    main()
