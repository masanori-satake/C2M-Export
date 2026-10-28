"""Confluence REST API を用いたメタデータ収集モジュール."""

import logging
from typing import List, Set, Tuple, Union

from c2m_export.analysis.macros import count_macros
from c2m_export.assessment.models import (
    AttachmentMeta,
    PageMeta,
    RawInventory,
    RestrictionMeta,
)
from c2m_export.confluence import ConfluenceClient

logger = logging.getLogger(__name__)


class Collector:
    """DFS巡回によりページ・添付・権限・更新情報のメタデータを収集するクラス."""

    def __init__(
        self,
        client: ConfluenceClient,
        analyze_restrictions: bool = True,
        collect_macros: bool = False,
    ):
        self.client = client
        self.analyze_restrictions = analyze_restrictions
        self.collect_macros = collect_macros

    def collect(self, root_ids: List[str]) -> RawInventory:
        """指定されたルートページIDリストからDFS巡回し RawInventory を構築する."""
        inventory = RawInventory()
        visited_page_ids: Set[str] = set()

        # (page_id, level, ancestors_titles) のスタック
        stack: List[Tuple[str, int, List[str]]] = [(rid, 1, []) for rid in reversed(root_ids)]

        processed_count = 0

        while stack:
            page_id, level, ancestors_titles = stack.pop()

            if page_id in visited_page_ids:
                continue
            visited_page_ids.add(page_id)

            processed_count += 1
            if processed_count % 50 == 0 or processed_count == 1:
                logger.info(f"アセスメント収集進捗: {processed_count} ページ処理中... (現在のID: {page_id})")

            # 1. ページ詳細取得
            try:
                page_data = self.client.get_page(page_id, expand="body.storage,space,version,history.lastUpdated")
            except Exception as e:
                logger.warning(f"ページ (ID: {page_id}) のメタデータ取得に失敗しました。スキップします: {e}")
                inventory.skipped_page_ids.append(page_id)
                continue

            title = page_data.get("title", f"Untitled_{page_id}")
            space_key = page_data.get("space", {}).get("key", "UNKNOWN")

            # Storage Format 生サイズ
            body_storage = page_data.get("body", {}).get("storage", {}).get("value", "")
            body_bytes = len(body_storage.encode("utf-8")) if body_storage else 0

            # マクロ収集（有効時）
            macro_counts_dict = {}
            if self.collect_macros and body_storage:
                try:
                    macro_counts_dict = count_macros(body_storage)
                except Exception as e:
                    logger.warning(f"ページ (ID: {page_id}) のマクロ解析に失敗しました: {e}")
                    inventory.macro_parse_failed_count += 1

            # 最終更新日時 (version.when や history.lastUpdated.when)
            last_modified = page_data.get("version", {}).get("when") or page_data.get("history", {}).get(
                "lastUpdated", {}
            ).get("when")

            # 2. 添付ファイルメタデータ取得
            attachments_meta: List[AttachmentMeta] = []
            try:
                raw_attachments = self.client.get_attachments(page_id)
                for att in raw_attachments:
                    att_filename = att.get("title", "")
                    extensions = att.get("extensions", {})
                    file_size = extensions.get("fileSize")
                    media_type = extensions.get("mediaType", "")
                    att_version = att.get("version", {}).get("number")

                    if file_size is None:
                        inventory.size_meta_missing_count += 1

                    # 拡張子抽出 (ドット無しの小文字)
                    ext = ""
                    if "." in att_filename:
                        ext = att_filename.rsplit(".", 1)[1].lower()

                    attachments_meta.append(
                        AttachmentMeta(
                            page_id=page_id,
                            filename=att_filename,
                            extension=ext,
                            media_type=media_type,
                            file_size=file_size if isinstance(file_size, int) else None,
                            version=att_version,
                        )
                    )
            except Exception as e:
                logger.warning(f"ページ (ID: {page_id}) の添付ファイル一覧取得に失敗しました: {e}")
                inventory.skipped_attachment_refs.append(f"{page_id}:all")

            # 3. 権限メタデータ取得 (有効時)
            restriction_meta: Union[RestrictionMeta, None] = None
            if self.analyze_restrictions:
                try:
                    raw_restrictions = self.client.get_restrictions(page_id)
                    read_users = [
                        u.get("username", "")
                        for u in raw_restrictions.get("read", {})
                        .get("restrictions", {})
                        .get("user", {})
                        .get("results", [])
                        if u.get("username")
                    ]
                    read_groups = [
                        g.get("name", "")
                        for g in raw_restrictions.get("read", {})
                        .get("restrictions", {})
                        .get("group", {})
                        .get("results", [])
                        if g.get("name")
                    ]
                    update_users = [
                        u.get("username", "")
                        for u in raw_restrictions.get("update", {})
                        .get("restrictions", {})
                        .get("user", {})
                        .get("results", [])
                        if u.get("username")
                    ]
                    update_groups = [
                        g.get("name", "")
                        for g in raw_restrictions.get("update", {})
                        .get("restrictions", {})
                        .get("group", {})
                        .get("results", [])
                        if g.get("name")
                    ]

                    has_explicit = bool(read_users or read_groups or update_users or update_groups)
                    restriction_meta = RestrictionMeta(
                        has_explicit=has_explicit,
                        read_users=read_users,
                        read_groups=read_groups,
                        update_users=update_users,
                        update_groups=update_groups,
                    )
                except Exception as e:
                    logger.warning(f"ページ (ID: {page_id}) の制限情報取得に失敗しました: {e}")
                    inventory.restriction_failed_page_ids.append(page_id)
                    restriction_meta = RestrictionMeta(has_explicit=False, fetch_failed=True)

            page_meta = PageMeta(
                page_id=page_id,
                title=title,
                space_key=space_key,
                level=level,
                body_bytes=body_bytes,
                last_modified=last_modified,
                ancestors_titles=ancestors_titles,
                attachments=attachments_meta,
                restriction=restriction_meta,
                macro_counts=macro_counts_dict,
            )
            inventory.pages.append(page_meta)

            # 4. 子ページ取得
            try:
                child_pages = self.client.get_child_pages(page_id)
                next_ancestors = ancestors_titles + [title]
                for child in reversed(child_pages):
                    cid = str(child["id"])
                    if cid not in visited_page_ids:
                        stack.append((cid, level + 1, next_ancestors))
            except Exception as e:
                logger.warning(f"ページ (ID: {page_id}) の子ページ一覧取得に失敗しました: {e}")

        logger.info(f"アセスメント収集完了: 総処理ページ数 {len(inventory.pages)}")
        return inventory
