"""権限収集（collector）モジュール.

指定された起点（root_page_ids / space_keys）から DFS でページ階層を巡回し、
各ページのコンテンツ制限 (Read/Read+Write) を取得して PagePermission を構築する。
0004 (ファイルシステムエクスポート) と同一のツリー構築ロジックを用いてローカル相対パス (rel_path) を紐付ける。
個別の権限取得エラーが発生した場合は、全体を中断せずエラー内容を記録して継続する（部分成功）。
"""

import logging
from typing import Dict, List, Optional, Set, Tuple

from c2m_export.confluence import ConfluenceClient
from c2m_export.fs_export.models import PageNode, SkipRecord
from c2m_export.fs_export.tree import build_page_tree
from c2m_export.permission.models import PagePermission, PermissionReport, PermissionResult

logger = logging.getLogger(__name__)


def extract_permission_holders(data: Dict) -> Tuple[List[str], List[str]]:
    """単一の操作タイプ (read または update) のレスポンスからユーザーおよびグループのリストを抽出する.

    Args:
        data: `restriction.get("read")` または `restriction.get("update")` の辞書

    Returns:
        Tuple[ユーザー表示文字列リスト, グループ名リスト]
    """
    users: List[str] = []
    groups: List[str] = []

    if not isinstance(data, dict):
        return users, groups

    restrictions = data.get("restrictions", {})
    if not isinstance(restrictions, dict):
        return users, groups

    # ユーザー一覧の抽出
    user_data = restrictions.get("user", {})
    if isinstance(user_data, dict):
        for u in user_data.get("results", []):
            if isinstance(u, dict):
                display_name = u.get("displayName", "").strip()
                username = u.get("username", "").strip()
                if display_name and username and display_name != username:
                    users.append(f"{display_name} ({username})")
                elif display_name:
                    users.append(display_name)
                elif username:
                    users.append(username)

    # グループ一覧の抽出
    group_data = restrictions.get("group", {})
    if isinstance(group_data, dict):
        for g in group_data.get("results", []):
            if isinstance(g, dict):
                name = g.get("name", "").strip()
                if name:
                    groups.append(name)

    return users, groups


def _fetch_page_permission(
    client: ConfluenceClient,
    node: PageNode,
    base_url: str,
) -> PagePermission:
    """単一ページの権限情報を Confluence API から取得し PagePermission インスタンスを生成する.

    API 呼び出し失敗時は fetch_failed=True および失敗理由を設定する。
    """
    page_id = node.page_id
    title = node.title
    rel_path = node.relative_dir_path

    # Page 情報の補完（URL, space_key 等の取得）
    url = f"{base_url.rstrip('/')}/pages/viewpage.action?pageId={page_id}"
    space_key = ""

    try:
        page_info = client.get_page(page_id, expand="space")
        if isinstance(page_info, dict):
            if "space" in page_info and isinstance(page_info["space"], dict):
                space_key = page_info["space"].get("key", "")
            _links = page_info.get("_links", {})
            if isinstance(_links, dict) and "base" in _links and "webui" in _links:
                url = f"{_links['base']}{_links['webui']}"
    except Exception as e:
        logger.warning(
            f"現象: ページ {page_id} の基本情報取得に失敗しました。 原因: {e} 対処方法: ネットワーク状態または権限を確認してください。"
        )

    # 権限情報 (restriction/byOperation) の取得
    try:
        restrictions_data = client.get_restrictions(page_id)
        read_users, read_groups = extract_permission_holders(restrictions_data.get("read", {}))
        readwrite_users, readwrite_groups = extract_permission_holders(restrictions_data.get("update", {}))

        has_explicit = bool(read_users or read_groups or readwrite_users or readwrite_groups)

        return PagePermission(
            page_id=page_id,
            title=title,
            space_key=space_key,
            url=url,
            rel_path=rel_path,
            has_explicit=has_explicit,
            read_users=read_users,
            read_groups=read_groups,
            readwrite_users=readwrite_users,
            readwrite_groups=readwrite_groups,
            fetch_failed=False,
            fail_reason="",
        )
    except Exception as e:
        reason = f"コンテンツ制限の取得に失敗しました ({e})"
        logger.warning(
            f"現象: ページ {page_id} ({title}) の権限取得に失敗しました。 原因: {e} 対処方法: 権限を確認してください。"
        )
        return PagePermission(
            page_id=page_id,
            title=title,
            space_key=space_key,
            url=url,
            rel_path=rel_path,
            has_explicit=False,
            fetch_failed=True,
            fail_reason=reason,
        )


def _collect_from_node_tree(
    client: ConfluenceClient,
    node: PageNode,
    base_url: str,
    permissions_list: List[PagePermission],
    visited_ids: Set[str],
) -> None:
    """PageNode ツリーを DFS 順で順次巡回し、権限を収集する."""
    if node.page_id in visited_ids:
        return
    visited_ids.add(node.page_id)

    perm = _fetch_page_permission(client, node, base_url)
    permissions_list.append(perm)

    for child in node.children:
        _collect_from_node_tree(client, child, base_url, permissions_list, visited_ids)


def collect_permissions(
    client: ConfluenceClient,
    base_url: str,
    root_page_ids: Optional[List[str]] = None,
    space_keys: Optional[List[str]] = None,
    page_filename_mode: str = "title",
) -> PermissionResult:
    """指定された起点から DFS で階層を巡回し全ページの権限情報を収集する.

    Args:
        client: ConfluenceClient インスタンス
        base_url: Confluence のベース URL
        root_page_ids: 起点となるルートページ ID リスト
        space_keys: 起点となる Space キーリスト
        page_filename_mode: ローカル相対パス計算用の命名モード

    Returns:
        PermissionResult (全ページの権限レポートおよび集計サマリ)
    """
    skipped_pages: List[SkipRecord] = []
    root_nodes, _, _ = build_page_tree(
        client=client,
        root_page_ids=root_page_ids or [],
        space_keys=space_keys or [],
        page_filename_mode=page_filename_mode,
        skipped_pages=skipped_pages,
    )

    permissions: List[PagePermission] = []
    visited_collector_ids: Set[str] = set()

    for root_node in root_nodes:
        _collect_from_node_tree(
            client=client,
            node=root_node,
            base_url=base_url,
            permissions_list=permissions,
            visited_ids=visited_collector_ids,
        )

    exported_count = len(permissions)
    explicit_count = sum(1 for p in permissions if p.has_explicit and not p.fetch_failed)
    inherited_count = sum(1 for p in permissions if not p.has_explicit and not p.fetch_failed)
    failed_page_ids = [p.page_id for p in permissions if p.fetch_failed]

    report = PermissionReport(pages=permissions)

    logger.info(
        f"権限収集完了: 合計 {exported_count} 件 (個別制限あり: {explicit_count} 件, 継承/制限なし: {inherited_count} 件, 失敗: {len(failed_page_ids)} 件)"
    )

    return PermissionResult(
        report=report,
        exported_count=exported_count,
        explicit_count=explicit_count,
        inherited_count=inherited_count,
        failed_page_ids=failed_page_ids,
    )
