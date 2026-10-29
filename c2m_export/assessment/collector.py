"""Confluence REST API を用いたメタデータ収集モジュール."""

import logging
from typing import List, Set, Tuple, Union

from c2m_export.analysis.macros import count_macros
from c2m_export.assessment.models import (
    AttachmentMeta,
    EnvironmentMeta,
    PageMeta,
    RawInventory,
    RestrictionMeta,
    SpaceMeta,
    VisibilityMeta,
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
        collect_history: bool = False,
        collect_labels: bool = False,
        collect_comments: bool = False,
        collect_watchers: bool = False,
        collect_effective_restrictions: bool = False,
        collect_extracted_text: bool = False,
        collect_space_permissions: bool = False,
    ):
        self.client = client
        self.analyze_restrictions = analyze_restrictions
        self.collect_macros = collect_macros
        self.collect_history = collect_history
        self.collect_labels = collect_labels
        self.collect_comments = collect_comments
        self.collect_watchers = collect_watchers
        self.collect_effective_restrictions = collect_effective_restrictions
        self.collect_extracted_text = collect_extracted_text
        self.collect_space_permissions = collect_space_permissions
        self.raw_inventory = RawInventory()

    def collect_workspace_overview(self, spaces: List[dict], root_ids: List[str]) -> None:
        """全体把握フェーズの情報を収集し、RawInventory に設定する."""
        space_metas: List[SpaceMeta] = []
        visible_space_keys: List[str] = []
        unavailable_apis: List[str] = []

        for sp in spaces:
            space_key = sp.get("key", "")
            if not space_key:
                continue
            visible_space_keys.append(space_key)

            name = sp.get("name", space_key)
            sp_type = sp.get("type", "global")
            status = sp.get("status", "current")
            description = (
                sp.get("description", {}).get("plain", {}).get("value")
                if isinstance(sp.get("description"), dict)
                else None
            )

            # Space labels
            label_count = 0
            try:
                sp_labels = self.client.get_space_labels(space_key)
                results = sp_labels.get("results", []) if isinstance(sp_labels, dict) else []
                label_count = len(results)
            except Exception as e:
                logger.warning(f"Space {space_key} のラベル取得に失敗しました: {e}")
                if "space_labels" not in unavailable_apis:
                    unavailable_apis.append("space_labels")

            # Page count preview
            page_count_preview: Union[int, None] = None
            try:
                root_pages = self.client.get_space_root_pages(space_key)
                total_preview = len(root_pages)
                any_success = False
                for rp in root_pages:
                    rp_id = str(rp.get("id", ""))
                    if rp_id:
                        try:
                            cnt_res = self.client.get_descendant_page_count(rp_id)
                            desc_cnt = cnt_res.get("count", 0) if isinstance(cnt_res, dict) else 0
                            total_preview += desc_cnt
                            any_success = True
                        except Exception as e:
                            logger.warning(f"ページ {rp_id} の子孫数取得に失敗しました: {e}")
                if any_success or len(root_pages) == 0:
                    page_count_preview = total_preview
            except Exception as e:
                logger.warning(f"Space {space_key} のルートページ取得に失敗しました: {e}")
                if "descendant_count" not in unavailable_apis:
                    unavailable_apis.append("descendant_count")

            space_metas.append(
                SpaceMeta(
                    space_key=space_key,
                    name=name,
                    type=sp_type,
                    status=status,
                    description=description,
                    label_count=label_count,
                    page_count_preview=page_count_preview,
                )
            )

        self.raw_inventory.spaces = space_metas

        # Current user & Memberof
        username: Union[str, None] = None
        display_name: Union[str, None] = None
        groups: List[str] = []

        try:
            cur_user = self.client.get_current_user()
            if isinstance(cur_user, dict):
                username = cur_user.get("username")
                display_name = cur_user.get("displayName")
        except Exception as e:
            logger.warning(f"実行ユーザー情報の取得に失敗しました: {e}")
            unavailable_apis.append("current_user")

        try:
            m_groups = self.client.get_user_memberof()
            if isinstance(m_groups, list):
                for g in m_groups:
                    if isinstance(g, dict) and "name" in g:
                        groups.append(g["name"])
        except Exception as e:
            logger.warning(f"所属グループ情報の取得に失敗しました: {e}")
            unavailable_apis.append("memberof")

        self.raw_inventory.visibility = VisibilityMeta(
            username=username,
            display_name=display_name,
            groups=groups,
            visible_space_keys=visible_space_keys,
            unavailable_apis=unavailable_apis,
        )

        # Access mode & Server information
        access_mode: Union[str, None] = None
        server_version: Union[str, None] = None
        build_number: Union[str, None] = None

        try:
            acc = self.client.get_access_mode()
            if isinstance(acc, dict):
                access_mode = acc.get("accessMode")
        except Exception as e:
            logger.warning(f"アクセスモード情報の取得に失敗しました: {e}")

        try:
            srv = self.client.get_server_information()
            if isinstance(srv, dict):
                server_version = srv.get("version")
                build_number = str(srv.get("buildNumber")) if srv.get("buildNumber") is not None else None
        except Exception as e:
            logger.warning(f"サーバー情報の取得に失敗しました: {e}")

        base_url = getattr(self.client, "base_url", None)
        self.raw_inventory.environment = EnvironmentMeta(
            access_mode=access_mode,
            server_version=server_version,
            build_number=build_number,
            base_url=base_url,
        )

    def collect_space_details(self, space_keys: List[str]) -> None:
        """解決済みSpace集合に対する per-space の詳細調査（権限照会・Spaceウォッチャー）を実行する."""
        if not self.collect_space_permissions and not self.collect_watchers:
            return

        space_map = {sp.space_key: sp for sp in self.raw_inventory.spaces}

        for skey in space_keys:
            sp_meta = space_map.get(skey)
            if sp_meta is None:
                sp_meta = SpaceMeta(space_key=skey, name=skey, type="global", status="current")
                self.raw_inventory.spaces.append(sp_meta)
                space_map[skey] = sp_meta

            # 1. Space 権限照会
            if self.collect_space_permissions:
                try:
                    p_res = self.client.get_space_permissions(skey)
                    if isinstance(p_res, dict):
                        entries = []
                        results = p_res.get("results", []) if isinstance(p_res.get("results"), list) else [p_res]
                        for r in results:
                            if isinstance(r, dict):
                                perm_type = r.get("type", "unknown")
                                principal = r.get("userName") or r.get("groupName") or "all"
                                entries.append(f"{perm_type}:{principal}")
                        sp_meta.permission_entries = entries
                    elif isinstance(p_res, list):
                        sp_meta.permission_entries = [str(item) for item in p_res]
                except Exception as e:
                    logger.warning(f"Space {skey} の権限照会に失敗しました: {e}")
                    self.raw_inventory.space_permission_failed_keys.append(skey)

            # 2. Space ウォッチャー照会
            if self.collect_watchers:
                try:
                    w_res = self.client.get_space_watchers(skey)
                    if isinstance(w_res, dict):
                        watchers_list = w_res.get("byUser", {}).get("results", []) or w_res.get("results", [])
                        sp_meta.watcher_count = len(watchers_list)
                except Exception as e:
                    logger.warning(f"Space {skey} のウォッチャー照会に失敗しました: {e}")
                    self.raw_inventory.space_watcher_failed_keys.append(skey)

    def collect(self, root_ids: List[str]) -> RawInventory:
        """指定されたルートページIDリストからDFS巡回し RawInventory を構築する."""
        inventory = self.raw_inventory
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

            # 3.5 詳細調査フェーズ (per-page オプトイン収集)
            created_by: Union[str, None] = None
            last_updated_by: Union[str, None] = None
            contributors: List[str] = []
            owner_unknown: bool = False
            if self.collect_history:
                try:
                    hist = self.client.get_content_history(page_id)
                    cb = hist.get("createdBy", {})
                    if isinstance(cb, dict):
                        created_by = cb.get("displayName") or cb.get("username")
                    lub = hist.get("lastUpdated", {}).get("by", {})
                    if isinstance(lub, dict):
                        last_updated_by = lub.get("displayName") or lub.get("username")
                    contribs = hist.get("contributors", {}).get("publishers", {}).get("users", [])
                    if isinstance(contribs, list):
                        for u in contribs:
                            if isinstance(u, dict):
                                uname = u.get("displayName") or u.get("username")
                                if uname and uname not in contributors:
                                    contributors.append(uname)
                    if not created_by and not last_updated_by:
                        owner_unknown = True
                except Exception as e:
                    logger.warning(f"ページ (ID: {page_id}) の更新履歴取得に失敗しました: {e}")
                    inventory.history_failed_page_ids.append(page_id)

            page_labels: List[str] = []
            if self.collect_labels:
                try:
                    lbls = self.client.get_labels(page_id)
                    for litem in lbls:
                        if isinstance(litem, dict) and "name" in litem:
                            page_labels.append(litem["name"])
                except Exception as e:
                    logger.warning(f"ページ (ID: {page_id}) のラベル取得に失敗しました: {e}")
                    inventory.label_failed_page_ids.append(page_id)

            comment_count: int = 0
            unresolved_comment_count: Union[int, None] = None
            inline_comment_count: Union[int, None] = None
            footer_comment_count: Union[int, None] = None
            if self.collect_comments:
                try:
                    cmts = self.client.get_comments(page_id)
                    comment_count = len(cmts)
                    u_cnt = 0
                    i_cnt = 0
                    f_cnt = 0
                    has_loc = False
                    has_res = False
                    for c in cmts:
                        exts = c.get("extensions", {}) if isinstance(c, dict) else {}
                        loc = exts.get("location")
                        if loc == "inline":
                            i_cnt += 1
                            has_loc = True
                        elif loc == "footer":
                            f_cnt += 1
                            has_loc = True

                        res = exts.get("resolution", {})
                        if isinstance(res, dict) and "status" in res:
                            has_res = True
                            if res.get("status") != "resolved":
                                u_cnt += 1
                    if has_loc:
                        inline_comment_count = i_cnt
                        footer_comment_count = f_cnt
                    if has_res:
                        unresolved_comment_count = u_cnt
                except Exception as e:
                    logger.warning(f"ページ (ID: {page_id}) のコメント取得に失敗しました: {e}")
                    inventory.comment_failed_page_ids.append(page_id)

            eff_restriction_meta: Union[RestrictionMeta, None] = None
            if self.collect_effective_restrictions:
                try:
                    raw_eff = self.client.get_relevant_view_restrictions(page_id)
                    r_users = [
                        u.get("username", "")
                        for u in raw_eff.get("read", {}).get("restrictions", {}).get("user", {}).get("results", [])
                        if u.get("username")
                    ]
                    r_groups = [
                        g.get("name", "")
                        for g in raw_eff.get("read", {}).get("restrictions", {}).get("group", {}).get("results", [])
                        if g.get("name")
                    ]
                    eff_restriction_meta = RestrictionMeta(
                        has_explicit=bool(r_users or r_groups),
                        read_users=r_users,
                        read_groups=r_groups,
                    )
                except Exception as e:
                    logger.warning(f"ページ (ID: {page_id}) の実効閲覧制限取得に失敗しました: {e}")
                    inventory.effective_restriction_failed_page_ids.append(page_id)

            if self.collect_watchers:
                try:
                    self.client.get_content_watchers(page_id)
                except Exception as e:
                    logger.warning(f"ページ (ID: {page_id}) のウォッチャー取得に失敗しました: {e}")
                    inventory.content_watcher_failed_refs.append(page_id)

            if self.collect_extracted_text:
                for att in attachments_meta:
                    att_id = att.filename  # identifier placeholder
                    try:
                        ext_res = self.client.get_attachment_extracted_text(page_id, att_id)
                        if isinstance(ext_res, dict):
                            text = ext_res.get("text") or ""
                            att.has_extracted_text = bool(text)
                            att.extracted_text_length = len(text)
                    except Exception as e:
                        logger.warning(f"添付 ({page_id}:{att_id}) の抽出テキスト取得に失敗しました: {e}")
                        inventory.extracted_text_failed_refs.append(f"{page_id}:{att_id}")

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
                created_by=created_by,
                last_updated_by=last_updated_by,
                contributors=contributors,
                owner_unknown=owner_unknown,
                labels=page_labels,
                comment_count=comment_count,
                unresolved_comment_count=unresolved_comment_count,
                inline_comment_count=inline_comment_count,
                footer_comment_count=footer_comment_count,
                effective_view_restrictions=eff_restriction_meta,
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
