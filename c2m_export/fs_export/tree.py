"""ツリー巡回とローカルパス割当モジュール.

Confluence REST API を用いて DFS でページツリーを探索し、各ノードに OS 安全なローカルディレクトリパス・本文ファイル名を割り当てる。
"""

import logging
from typing import Dict, List, Optional, Set, Tuple

from c2m_export.confluence import ConfluenceClient
from c2m_export.fs_export.models import PageNode, SkipRecord
from c2m_export.utils import generate_unique_name, sanitize_filename

logger = logging.getLogger(__name__)


def build_page_tree(
    client: ConfluenceClient,
    root_page_ids: List[str],
    space_keys: List[str],
    page_filename_mode: str = "title",
    path_length_limit: int = 400,
    skipped_pages: Optional[List[SkipRecord]] = None,
) -> Tuple[List[PageNode], Dict[str, str], Set[str]]:
    """指定された起点から DFS でページツリーを探索・構築する.

    Args:
        client: ConfluenceClient インスタンス
        root_page_ids: 起点となるルートページ ID のリスト
        space_keys: 起点となる Space キーのリスト
        page_filename_mode: 本文ファイル命名方式 ("title" または "index")
        path_length_limit: パス長警告しきい値
        skipped_pages: 探索中の取得失敗を追記するリスト（指定時は呼び出し元で集計可能）

    Returns:
        Tuple[
            ルート PageNode のリスト,
            採番等で名称変更された記録マッピング (page_id -> "元タイトル -> 採用ディレクトリ名"),
            訪問済みページ ID の集合
        ]
    """
    visited_ids: Set[str] = set()
    root_nodes: List[PageNode] = []
    renamed_nodes: Dict[str, str] = {}
    if skipped_pages is None:
        skipped_pages = []

    # 起点ターゲットのリスト (type, key_or_id)
    targets: List[Tuple[str, str]] = []
    if root_page_ids:
        for r_id in root_page_ids:
            targets.append(("page", r_id))
    if space_keys:
        for s_key in space_keys:
            targets.append(("space", s_key))

    for target_type, target_val in targets:
        if target_type == "page":
            if target_val in visited_ids:
                continue
            try:
                page_data = client.get_page(target_val)
                node = _traverse_dfs(
                    client=client,
                    page_data=page_data,
                    parent_rel_dir="",
                    level=1,
                    visited_ids=visited_ids,
                    renamed_nodes=renamed_nodes,
                    page_filename_mode=page_filename_mode,
                    path_length_limit=path_length_limit,
                    skipped_pages=skipped_pages,
                )
                if node:
                    root_nodes.append(node)
            except Exception as e:
                skipped_pages.append(
                    SkipRecord(
                        target_id=target_val,
                        target_type="page",
                        title_or_name=target_val,
                        reason=f"ルートページ取得失敗 ({e})",
                    )
                )
                logger.warning(
                    f"現象: ルートページ {target_val} の取得に失敗しました。 原因: {e} 対処方法: ページIDまたは権限を確認してください。"
                )
        elif target_type == "space":
            try:
                space_roots = client.get_space_root_pages(target_val)
                for root_data in space_roots:
                    p_id = root_data.get("id")
                    if p_id and p_id not in visited_ids:
                        node = _traverse_dfs(
                            client=client,
                            page_data=root_data,
                            parent_rel_dir="",
                            level=1,
                            visited_ids=visited_ids,
                            renamed_nodes=renamed_nodes,
                            page_filename_mode=page_filename_mode,
                            path_length_limit=path_length_limit,
                            skipped_pages=skipped_pages,
                        )
                        if node:
                            root_nodes.append(node)
            except Exception as e:
                skipped_pages.append(
                    SkipRecord(
                        target_id=target_val,
                        target_type="space",
                        title_or_name=f"Space {target_val}",
                        reason=f"Space ルートページ一覧取得失敗 ({e})",
                    )
                )
                logger.warning(
                    f"現象: Space {target_val} のルートページ一覧取得に失敗しました。 原因: {e} 対処方法: Space キーまたは権限を確認してください。"
                )

    return root_nodes, renamed_nodes, visited_ids


def _traverse_dfs(
    client: ConfluenceClient,
    page_data: Dict,
    parent_rel_dir: str,
    level: int,
    visited_ids: Set[str],
    renamed_nodes: Dict[str, str],
    page_filename_mode: str,
    path_length_limit: int,
    skipped_pages: List[SkipRecord],
) -> PageNode:

    page_id = page_data["id"]
    visited_ids.add(page_id)

    title = page_data.get("title", "untitled")
    space_key = ""
    if "space" in page_data and isinstance(page_data["space"], dict):
        space_key = page_data["space"].get("key", "")

    # ルートレベルのディレクトリ名プレフィックス
    if level == 1:
        base_dir_name = f"【{space_key or 'UNKNOWN'}】 {sanitize_filename(title)}"
    else:
        base_dir_name = sanitize_filename(title)

    if not base_dir_name:
        base_dir_name = "untitled"

    # 同一親ディレクトリ内での既存子ディレクトリ名を取得・衝突回避 (呼び出し側で解決)
    # parent_rel_dir と結合
    if parent_rel_dir:
        dir_path = f"{parent_rel_dir}/{base_dir_name}"
    else:
        dir_path = base_dir_name

    if len(dir_path) > path_length_limit:
        logger.warning(
            f"現象: 相対パス長 ({len(dir_path)} 文字) が制限値 ({path_length_limit}) を超えています ({dir_path})。 原因: 深い階層構造または長いタイトル。 対処方法: 必要に応じて path_length_limit を変更してください。"
        )

    # 本文ファイル名の決定
    if page_filename_mode == "index":
        body_file_name = "index.md"
    else:
        body_file_name = f"{sanitize_filename(title) or 'untitled'}.md"

    node = PageNode(
        page_id=page_id,
        title=title,
        level=level,
        relative_dir_path=dir_path,
        body_file_name=body_file_name,
    )

    # 子ページの取得
    try:
        children_data = client.get_child_pages(page_id)
        existing_child_dir_names: List[str] = []

        for child_data in children_data:
            c_id = child_data.get("id")
            if not c_id or c_id in visited_ids:
                continue

            c_title = child_data.get("title", "untitled")
            c_base_name = sanitize_filename(c_title) or "untitled"

            # 子ディレクトリ名の衝突回避採番
            unique_c_name = generate_unique_name(c_base_name, existing_child_dir_names)
            existing_child_dir_names.append(unique_c_name)

            if unique_c_name != c_title:
                renamed_nodes[c_id] = f"{c_title} -> {unique_c_name}"

            # 子ノードの再帰構築
            c_node = _traverse_dfs_child(
                client=client,
                page_data=child_data,
                parent_rel_dir=dir_path,
                assigned_dir_name=unique_c_name,
                level=level + 1,
                visited_ids=visited_ids,
                renamed_nodes=renamed_nodes,
                page_filename_mode=page_filename_mode,
                path_length_limit=path_length_limit,
                skipped_pages=skipped_pages,
            )
            if c_node:
                node.children.append(c_node)
    except Exception as e:
        skipped_pages.append(
            SkipRecord(
                target_id=page_id,
                target_type="page",
                title_or_name=title,
                reason=f"子ページ取得失敗 ({e})",
                path=dir_path,
            )
        )
        logger.warning(
            f"現象: ページ {page_id} ({title}) の子ページ取得に失敗しました。 原因: {e} 対処方法: ネットワーク状態を確認してください。"
        )

    return node


def _traverse_dfs_child(
    client: ConfluenceClient,
    page_data: Dict,
    parent_rel_dir: str,
    assigned_dir_name: str,
    level: int,
    visited_ids: Set[str],
    renamed_nodes: Dict[str, str],
    page_filename_mode: str,
    path_length_limit: int,
    skipped_pages: List[SkipRecord],
) -> PageNode:
    page_id = page_data["id"]
    visited_ids.add(page_id)
    title = page_data.get("title", "untitled")

    dir_path = f"{parent_rel_dir}/{assigned_dir_name}"

    if len(dir_path) > path_length_limit:
        logger.warning(
            f"現象: 相対パス長 ({len(dir_path)} 文字) が制限値 ({path_length_limit}) を超えています ({dir_path})。 原因: 深い階層構造または長いタイトル。 対処方法: 必要に応じて path_length_limit を変更してください。"
        )

    if page_filename_mode == "index":
        body_file_name = "index.md"
    else:
        body_file_name = f"{assigned_dir_name}.md"

    node = PageNode(
        page_id=page_id,
        title=title,
        level=level,
        relative_dir_path=dir_path,
        body_file_name=body_file_name,
    )

    try:
        children_data = client.get_child_pages(page_id)
        existing_child_dir_names: List[str] = []

        for child_data in children_data:
            c_id = child_data.get("id")
            if not c_id or c_id in visited_ids:
                continue

            c_title = child_data.get("title", "untitled")
            c_base_name = sanitize_filename(c_title) or "untitled"

            unique_c_name = generate_unique_name(c_base_name, existing_child_dir_names)
            existing_child_dir_names.append(unique_c_name)

            if unique_c_name != c_title:
                renamed_nodes[c_id] = f"{c_title} -> {unique_c_name}"

            c_node = _traverse_dfs_child(
                client=client,
                page_data=child_data,
                parent_rel_dir=dir_path,
                assigned_dir_name=unique_c_name,
                level=level + 1,
                visited_ids=visited_ids,
                renamed_nodes=renamed_nodes,
                page_filename_mode=page_filename_mode,
                path_length_limit=path_length_limit,
                skipped_pages=skipped_pages,
            )
            if c_node:
                node.children.append(c_node)
    except Exception as e:
        skipped_pages.append(
            SkipRecord(
                target_id=page_id,
                target_type="page",
                title_or_name=title,
                reason=f"子ページ取得失敗 ({e})",
                path=dir_path,
            )
        )
        logger.warning(
            f"現象: ページ {page_id} ({title}) の子ページ取得に失敗しました。 原因: {e} 対処方法: ネットワーク状態を確認してください。"
        )

    return node
