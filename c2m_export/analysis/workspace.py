"""スペース一覧・可視範囲・環境コンテキストの集約純粋関数."""

from typing import Dict, List, Optional

from c2m_export.assessment.models import (
    EnvironmentMeta,
    RawInventory,
    SpaceMeta,
    VisibilityMeta,
)


def summarize_spaces(spaces: List[SpaceMeta]) -> Dict:
    """スペース一覧を整形・集計する."""
    space_list = []
    global_cnt = 0
    personal_cnt = 0
    archived_cnt = 0

    for sp in spaces:
        if sp.type == "personal":
            personal_cnt += 1
        else:
            global_cnt += 1

        if sp.status == "archived":
            archived_cnt += 1

        space_list.append(
            {
                "space_key": sp.space_key,
                "name": sp.name,
                "type": sp.type,
                "status": sp.status,
                "description": sp.description,
                "label_count": sp.label_count,
                "page_count_preview": sp.page_count_preview,
                "watcher_count": sp.watcher_count,
                "permission_entries": sp.permission_entries,
            }
        )

    return {
        "spaces": space_list,
        "space_count": len(spaces),
        "global_space_count": global_cnt,
        "personal_space_count": personal_cnt,
        "archived_space_count": archived_cnt,
    }


def build_visibility(visibility: Optional[VisibilityMeta], inventory: RawInventory) -> Dict:
    """可視範囲自己診断情報を構築する."""
    username = visibility.username if visibility else None
    display_name = visibility.display_name if visibility else None
    groups = visibility.groups if visibility else []
    visible_space_keys = visibility.visible_space_keys if visibility else []

    unavailable_set = set(visibility.unavailable_apis if visibility else [])

    if inventory.history_failed_page_ids:
        unavailable_set.add("history")
    if inventory.label_failed_page_ids:
        unavailable_set.add("labels")
    if inventory.comment_failed_page_ids:
        unavailable_set.add("comments")
    if inventory.effective_restriction_failed_page_ids:
        unavailable_set.add("effective_restrictions")
    if inventory.extracted_text_failed_refs:
        unavailable_set.add("extracted_text")
    if inventory.content_watcher_failed_refs or inventory.space_watcher_failed_keys:
        unavailable_set.add("watchers")
    if inventory.space_permission_failed_keys:
        unavailable_set.add("space_permissions")
    if inventory.cql_failed:
        unavailable_set.add("cql")

    note = (
        "管理者特権が無いため、権限により参照できないページ/スペースは本結果に含まれていない可能性があります。"
        "unavailable_apis に挙がった情報は取得できなかったため欠落しています。"
    )

    return {
        "username": username,
        "display_name": display_name,
        "groups": groups,
        "visible_space_keys": visible_space_keys,
        "unavailable_apis": sorted(list(unavailable_set)),
        "note": note,
    }


def build_environment(environment: Optional[EnvironmentMeta]) -> Dict:
    """環境コンテキストを構築する."""
    if not environment:
        return {
            "access_mode": None,
            "server_version": None,
            "build_number": None,
        }

    return {
        "access_mode": environment.access_mode,
        "server_version": environment.server_version,
        "build_number": environment.build_number,
    }
