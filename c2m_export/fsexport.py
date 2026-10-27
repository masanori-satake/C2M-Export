"""ファイルシステムエクスポート CLI エントリーポイント.

python -m c2m_export.fsexport
"""

import logging
import os
import sys
from datetime import datetime

from c2m_export.config import FsExportConfig
from c2m_export.confluence import ConfluenceClient
from c2m_export.converter import MarkdownConverter
from c2m_export.fs_export.diff import compute_diff
from c2m_export.fs_export.manifest import (
    Manifest,
    ManifestCorruptedError,
    ManifestRoots,
    ManifestScopeMismatchError,
    load_manifest,
    save_manifest,
    verify_scope,
)
from c2m_export.fs_export.models import ExportResult
from c2m_export.fs_export.summary import write_summary
from c2m_export.fs_export.sync import collect_inventory, execute_sync
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

    # 差分同期 / レジューム実行モードの判定
    use_sync = (config.sync or config.resume) and not config.full

    # フェイルファスト: 出力先書き込み・競合チェック (sync/resume 時は既存ディレクトリをそのまま使用可能)
    out_dir = os.path.abspath(config.output_dir)
    if os.path.exists(out_dir) and os.listdir(out_dir) and not config.overwrite and not use_sync:
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

    if use_sync:
        logger.info("差分同期・レジュームモードで実行します...")

        # マニフェストの読み込み
        try:
            manifest = load_manifest(out_dir, manifest_name=config.manifest_name)
        except ManifestCorruptedError as mce:
            logger.error(str(mce))
            sys.exit(1)

        if manifest:
            # スコープ検証
            try:
                verify_scope(
                    manifest,
                    current_base_url=config.base_url,
                    current_root_page_ids=config.root_page_ids,
                    current_space_keys=config.space_keys,
                )
            except ManifestScopeMismatchError as msme:
                logger.error(str(msme))
                sys.exit(1)
        else:
            logger.info("既存のマニフェストが存在しないため、新規マニフェストを作成して収集を開始します。")
            manifest = Manifest(
                base_url=config.base_url,
                roots=ManifestRoots(root_page_ids=config.root_page_ids, space_keys=config.space_keys),
                started_at=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            )

        logger.info("Confluence サーバからメタデータ（軽量インベントリ）を収集しています...")
        inventory = collect_inventory(client, root_page_ids=config.root_page_ids, space_keys=config.space_keys)

        logger.info("前回状態と現在インベントリの差分判定を行っています...")
        plan = compute_diff(manifest, inventory)

        diff_counts = {
            "add": plan.add_count,
            "change": plan.change_count,
            "move_rename": plan.move_rename_count,
            "delete": plan.delete_count,
            "unchanged": plan.unchanged_count,
        }

        logger.info(
            f"差分判定結果: 追加={plan.add_count}, 変更={plan.change_count}, 移動/改名={plan.move_rename_count}, 削除={plan.delete_count}, 未変更スキップ={plan.unchanged_count}"
        )

        result = execute_sync(
            client=client,
            converter=converter,
            output_dir=out_dir,
            manifest=manifest,
            inventory=inventory,
            plan=plan,
            attachment_dir_name=config.attachment_dir_name,
            attachment_link_mode=config.attachment_link_mode,
            single_file_max_mb=config.single_file_max_mb,
            exclude_extensions=config.exclude_extensions,
            frontmatter_fields=config.frontmatter_fields,
            base_url=config.base_url,
            deletion_policy=config.deletion_policy,
            quarantine_dir_name=config.quarantine_dir_name,
            manifest_name=config.manifest_name,
            page_filename_mode=config.page_filename_mode,
            resume=config.resume,
        )

        logger.info("サマリの出力と完了処理を実行しています...")
        write_summary(result, config.output_dir, diff_counts=diff_counts)
        logger.info("ファイルシステムエクスポート（差分同期・レジューム）が完了しました。")

    else:
        logger.info("Confluence からページツリー構造を取得しています...")
        tree_result = ExportResult()
        root_nodes, renamed_map, visited_ids = build_page_tree(
            client=client,
            root_page_ids=config.root_page_ids,
            space_keys=config.space_keys,
            page_filename_mode=config.page_filename_mode,
            path_length_limit=config.path_length_limit,
            skipped_pages=tree_result.skipped_pages,
        )

        if not root_nodes:
            write_summary(tree_result, config.output_dir)
            logger.error(
                "現象: エクスポート対象の起点ページが1つも見つかりませんでした。 原因: 指定された root_page_id または space_key が存在しないか権限がありません。 対処方法: 対象 ID/Space キーおよびアクセストークンを確認してください。"
            )
            sys.exit(1)

        logger.info(f"ツリー探索完了: {len(root_nodes)} 個の起点ノード、全 {len(visited_ids)} ページを検出しました。")
        logger.info("ファイルシステム構造への書き込み・本文変換・添付保存を開始します...")

        manifest = Manifest(
            base_url=config.base_url,
            roots=ManifestRoots(root_page_ids=config.root_page_ids, space_keys=config.space_keys),
            started_at=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
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
            manifest_pages=manifest.pages,
        )
        result.skipped_pages.extend(tree_result.skipped_pages)

        # フル出力完了時にもマニフェストを新規保存しておく（次回 sync/resume 用）
        try:
            manifest.completed = True
            manifest.finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
            save_manifest(manifest, config.output_dir, config.manifest_name)
        except Exception as me:
            logger.warning(f"フル出力完了後のマニフェスト初期保存に失敗しました: {me}")

        logger.info("サマリの出力と完了処理を実行しています...")
        write_summary(result, config.output_dir)

        logger.info("ファイルシステムエクスポートが完了しました。")


if __name__ == "__main__":
    main()
