"""書き込み・エクスポート実行モジュール.

割り当てられた PageNode ツリーに従って、本文 (Markdown + Frontmatter) の書き込みおよび添付ファイルの保存・サイズ制限判定を行う。
"""

import logging
import os
from typing import List, Optional, Set

from c2m_export.confluence import ConfluenceClient
from c2m_export.converter import MarkdownConverter
from c2m_export.fs_export.frontmatter import generate_frontmatter
from c2m_export.fs_export.links import rewrite_attachment_links
from c2m_export.fs_export.models import AttachmentRef, ExportResult, PageNode, SkipRecord
from c2m_export.fs_export.tree import build_page_tree
from c2m_export.utils import generate_unique_name, mb_to_bytes, sanitize_filename

logger = logging.getLogger(__name__)


def export_tree_fs(
    client: ConfluenceClient,
    converter: MarkdownConverter,
    output_dir: str,
    root_nodes: List[PageNode],
    attachment_dir_name: str = "_attachments",
    attachment_link_mode: str = "relative",
    single_file_max_mb: float = 250.0,
    exclude_extensions: Optional[List[str]] = None,
    frontmatter_fields: Optional[List[str]] = None,
    base_url: str = "",
    renamed_nodes_map: Optional[dict] = None,
) -> ExportResult:
    """PageNode ツリーに従ってファイルシステムへの出力・変換・添付DLを実行する.

    Args:
        client: ConfluenceClient
        converter: MarkdownConverter
        output_dir: 出力先ルートディレクトリ
        root_nodes: 構築済み PageNode のリスト
        attachment_dir_name: 添付サブディレクトリ名
        attachment_link_mode: 添付参照のリンク書き換えモード ("relative" | "original")
        single_file_max_mb: 単一ファイルサイズ上限 (MB)
        exclude_extensions: 除外する拡張子のリスト (小文字・ドットなし、例: ["exe", "zip"])
        frontmatter_fields: Frontmatter フィールドリスト
        base_url: Confluence ベース URL
        renamed_nodes_map: ノード改名記録マップ

    Returns:
        ExportResult: 実行サマリ結果
    """
    result = ExportResult()
    if renamed_nodes_map:
        result.renamed_nodes = renamed_nodes_map

    max_bytes = mb_to_bytes(single_file_max_mb)
    exclude_ext_set: Set[str] = set()
    if exclude_extensions:
        exclude_ext_set = {ext.strip().lstrip(".").lower() for ext in exclude_extensions if ext.strip()}

    for root in root_nodes:
        _process_node(
            client=client,
            converter=converter,
            output_dir=output_dir,
            node=root,
            result=result,
            attachment_dir_name=attachment_dir_name,
            attachment_link_mode=attachment_link_mode,
            max_bytes=max_bytes,
            single_file_max_mb=single_file_max_mb,
            exclude_ext_set=exclude_ext_set,
            frontmatter_fields=frontmatter_fields,
            base_url=base_url,
        )

    return result


def _process_node(
    client: ConfluenceClient,
    converter: MarkdownConverter,
    output_dir: str,
    node: PageNode,
    result: ExportResult,
    attachment_dir_name: str,
    attachment_link_mode: str,
    max_bytes: int,
    single_file_max_mb: float,
    exclude_ext_set: Set[str],
    frontmatter_fields: Optional[List[str]],
    base_url: str,
):
    # 1. ページ詳細の取得
    try:
        page_detail = client.get_page(
            node.page_id,
            expand="body.storage,space,version,ancestors,history.lastUpdated",
        )
    except Exception as e:
        logger.warning(
            f"現象: ページ {node.page_id} ({node.title}) の取得に失敗したためスキップします。 原因: {e} 対処方法: 権限や通信状態を確認してください。"
        )
        result.skipped_pages.append(
            SkipRecord(
                target_id=node.page_id,
                target_type="page",
                title_or_name=node.title,
                reason=f"ページ詳細取得失敗 ({e})",
                path=node.relative_dir_path,
            )
        )
        # 子ノードもスキップするか、個別に試行するか。ここでは継続試行する
        for child in node.children:
            _process_node(
                client,
                converter,
                output_dir,
                child,
                result,
                attachment_dir_name,
                attachment_link_mode,
                max_bytes,
                single_file_max_mb,
                exclude_ext_set,
                frontmatter_fields,
                base_url,
            )
        return

    # 2. 添付ファイル一覧の処理
    att_refs: List[AttachmentRef] = []
    try:
        raw_atts = client.get_attachments(node.page_id)
        saved_names: List[str] = []

        for att in raw_atts:
            orig_title = att.get("title", "unnamed")
            file_size = att.get("extensions", {}).get("fileSize", 0)
            links = att.get("_links", {})
            dl_path = links.get("download", "")

            # 拡張子チェック
            ext = os.path.splitext(orig_title)[1].lstrip(".").lower()
            if ext in exclude_ext_set:
                result.skipped_attachments.append(
                    SkipRecord(
                        target_id=att.get("id", orig_title),
                        target_type="attachment",
                        title_or_name=orig_title,
                        reason=f"除外拡張子 (.{ext}) に該当",
                        size_bytes=file_size,
                        path=f"{node.relative_dir_path}/{attachment_dir_name}/{orig_title}",
                    )
                )
                att_refs.append(
                    AttachmentRef(
                        original_filename=orig_title,
                        saved_filename=orig_title,
                        saved=False,
                        download_path=dl_path,
                        size_bytes=file_size,
                        skip_reason="除外拡張子",
                    )
                )
                continue

            # 単一ファイル上限判定 (事前メタデータチェック)
            if file_size > max_bytes:
                logger.warning(
                    f"現象: 添付ファイル {orig_title} ({file_size} バイト) は単一ファイル上限 ({single_file_max_mb} MB) を超えているためスキップします。 原因: 設定された上限サイズ超過。 対処方法: 必要に応じて single_file_max_mb を変更してください。"
                )
                result.skipped_attachments.append(
                    SkipRecord(
                        target_id=att.get("id", orig_title),
                        target_type="attachment",
                        title_or_name=orig_title,
                        reason=f"単一ファイルサイズ上限超過 ({single_file_max_mb} MB 超)",
                        size_bytes=file_size,
                        path=f"{node.relative_dir_path}/{attachment_dir_name}/{orig_title}",
                    )
                )
                att_refs.append(
                    AttachmentRef(
                        original_filename=orig_title,
                        saved_filename=orig_title,
                        saved=False,
                        download_path=dl_path,
                        size_bytes=file_size,
                        skip_reason="サイズ上限超過",
                    )
                )
                continue

            # 保存用ファイル名の正規化と採番
            safe_att_name = sanitize_filename(orig_title) or "unnamed"
            unique_att_name = generate_unique_name(safe_att_name, saved_names)
            saved_names.append(unique_att_name)

            dest_att_path = os.path.join(
                output_dir, node.relative_dir_path, attachment_dir_name, unique_att_name
            )

            # ダウンロードと保存
            try:
                written_b = client.download_attachment(
                    download_path=dl_path, dest_file=dest_att_path, max_bytes=max_bytes
                )
                result.total_attachments += 1
                result.total_bytes += written_b
                att_refs.append(
                    AttachmentRef(
                        original_filename=orig_title,
                        saved_filename=unique_att_name,
                        saved=True,
                        download_path=dl_path,
                        size_bytes=written_b,
                    )
                )
            except ValueError as ve:
                # DL中上限超過中断
                result.skipped_attachments.append(
                    SkipRecord(
                        target_id=att.get("id", orig_title),
                        target_type="attachment",
                        title_or_name=orig_title,
                        reason=str(ve),
                        size_bytes=file_size,
                        path=f"{node.relative_dir_path}/{attachment_dir_name}/{unique_att_name}",
                    )
                )
                att_refs.append(
                    AttachmentRef(
                        original_filename=orig_title,
                        saved_filename=unique_att_name,
                        saved=False,
                        download_path=dl_path,
                        size_bytes=file_size,
                        skip_reason="ダウンロード中サイズ上限超過",
                    )
                )
            except Exception as de:
                logger.warning(
                    f"現象: 添付ファイル {orig_title} のダウンロードに失敗しました。 原因: {de} 対処方法: ネットワーク接続等を確認してください。"
                )
                result.skipped_attachments.append(
                    SkipRecord(
                        target_id=att.get("id", orig_title),
                        target_type="attachment",
                        title_or_name=orig_title,
                        reason=f"ダウンロードエラー ({de})",
                        size_bytes=file_size,
                        path=f"{node.relative_dir_path}/{attachment_dir_name}/{unique_att_name}",
                    )
                )
                att_refs.append(
                    AttachmentRef(
                        original_filename=orig_title,
                        saved_filename=unique_att_name,
                        saved=False,
                        download_path=dl_path,
                        size_bytes=file_size,
                        skip_reason="ダウンロードエラー",
                    )
                )
    except Exception as ae:
        logger.warning(
            f"現象: ページ {node.page_id} の添付ファイル一覧取得に失敗しました。 原因: {ae} 対処方法: 権限を確認してください。"
        )

    node.attachments = att_refs

    # 3. 本文の変換と Frontmatter 付与
    try:
        storage_html = page_detail.get("body", {}).get("storage", {}).get("value", "")
        raw_markdown = converter.convert(storage_html, level=1)

        # リンク書き換え
        final_markdown, unresolved_cnt = rewrite_attachment_links(
            content=raw_markdown,
            attachments=att_refs,
            attachment_dir_name=attachment_dir_name,
            link_mode=attachment_link_mode,
            base_url=base_url,
        )
        result.unresolved_links_count += unresolved_cnt

        # Frontmatter 生成
        version_num = page_detail.get("version", {}).get("number")
        last_modified = page_detail.get("history", {}).get("lastUpdated", {}).get("when")
        space_key = page_detail.get("space", {}).get("key", "")

        frontmatter_str = generate_frontmatter(
            page_id=node.page_id,
            space_key=space_key,
            base_url=base_url,
            title=node.title,
            version=version_num,
            last_modified=last_modified,
            fields=frontmatter_fields,
        )

        full_content = frontmatter_str + final_markdown

        # ファイル書き込み
        page_dir = os.path.join(output_dir, node.relative_dir_path)
        os.makedirs(page_dir, exist_ok=True)
        body_filepath = os.path.join(page_dir, node.body_file_name)

        encoded_bytes = full_content.encode("utf-8")
        with open(body_filepath, "wb") as f:
            f.write(encoded_bytes)

        result.total_pages += 1
        result.total_bytes += len(encoded_bytes)

    except Exception as pe:
        logger.warning(
            f"現象: ページ {node.page_id} ({node.title}) の書き込みに失敗しました。 原因: {pe} 対処方法: 書き込み権限を確認してください。"
        )
        result.skipped_pages.append(
            SkipRecord(
                target_id=node.page_id,
                target_type="page",
                title_or_name=node.title,
                reason=f"書き込みエラー ({pe})",
                path=node.relative_dir_path,
            )
        )

    # 進捗ログ報告 (定期)
    if result.total_pages > 0 and result.total_pages % 10 == 0:
        logger.info(
            f"エクスポート進行中: 成功ページ数={result.total_pages}, 成功添付ファイル数={result.total_attachments}"
        )

    # 4. 子ノード処理
    for child in node.children:
        _process_node(
            client,
            converter,
            output_dir,
            child,
            result,
            attachment_dir_name,
            attachment_link_mode,
            max_bytes,
            single_file_max_mb,
            exclude_ext_set,
            frontmatter_fields,
            base_url,
        )
