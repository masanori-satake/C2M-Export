"""ツリー構造構築の純粋ロジックモジュール."""

from typing import Any, Dict, List, Optional, Set, Tuple

from c2m_export.page_tree.models import Annotation, TreeNode


def build_tree(
    root_ids: List[str],
    children_map: Dict[str, List[Dict[str, Any]]],
    annotations_map: Dict[str, Annotation],
    page_titles_map: Dict[str, str],
    max_depth: Optional[int] = None,
) -> Tuple[List[TreeNode], int]:
    """収集済みのデータ構造から TreeNode の木構造を再帰的に構築する.

    Args:
        root_ids: 起点となるルートページ ID リスト
        children_map: page_id -> 子ページ情報の辞書リスト [{"id": ..., "title": ...}, ...]
        annotations_map: page_id -> Annotation オブジェクト
        page_titles_map: page_id -> ページタイトルのマッピング
        max_depth: 探索の最大深さ（1 から開始。1 はルートのみ。None または <= 0 で無制限）

    Returns:
        (roots: List[TreeNode], total_pages_count: int)
    """
    counted_page_ids: Set[str] = set()

    def _build_node(page_id: str, depth: int, current_visited: Set[str]) -> Optional[TreeNode]:
        if page_id in current_visited:
            # 単一ルートツリー内での循環参照防止
            return None

        current_visited.add(page_id)
        counted_page_ids.add(page_id)

        title = page_titles_map.get(page_id, f"Page {page_id}")
        ann = annotations_map.get(page_id, Annotation())

        node = TreeNode(
            page_id=page_id,
            title=title,
            annotation=ann,
            children=[],
        )

        # 深さ制限チェック
        if max_depth is not None and max_depth > 0 and depth >= max_depth:
            return node

        child_list = children_map.get(page_id, [])
        for c in child_list:
            c_id = str(c.get("id"))
            if c_id:
                # 子のタイトルを page_titles_map に保存（あれば）
                if "title" in c:
                    page_titles_map[c_id] = str(c["title"])
                child_node = _build_node(c_id, depth + 1, current_visited)
                if child_node is not None:
                    node.children.append(child_node)

        return node

    roots: List[TreeNode] = []
    for r_id in root_ids:
        visited_ids_per_root: Set[str] = set()
        r_node = _build_node(r_id, depth=1, current_visited=visited_ids_per_root)
        if r_node is not None:
            roots.append(r_node)

    return roots, len(counted_page_ids)
